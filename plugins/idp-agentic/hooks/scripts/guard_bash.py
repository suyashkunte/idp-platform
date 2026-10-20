#!/usr/bin/env python3
"""PreToolUse guard for Bash: block commands that bypass human checkpoints or change shared state (exit 2 = block).

Defence in depth behind the permission deny-list and GitHub rulesets. Stdlib only, Python 3.9+.

Spec approval (IDP-14) is relax-only: every mention of `approve-spec` or of an `APPROVED` file in the raw command
blocks, unless a small lexer shows that the mention is quoted or heredoc data given to a command that only prints or
records it, or (for the marker) a plain argument of a read-only command. When the lexer cannot follow the shell,
nothing is relaxed.
"""

import bisect
import json
import re
import sys

RULES = [
    (r"\bgit\s+push\b[^;&|]*\s(--force(-with-lease)?|-f)\b", "force-push is never allowed"),
    (r"\bgit\s+push\b[^;&|]*\b(HEAD:|refs/heads/)?(main|master)\b", "push to main: changes reach main only via a PR"),
    (r"\bgit\s+(commit|push)\b[^;&|]*--no-verify\b", "skipping git hooks is not allowed"),
    (r"\bgit\s+config\b[^;&|]*core\.hooksPath", "changing git hook configuration is not allowed"),
    (r"\bgh\s+pr\s+merge\b", "merging is a human decision (checkpoint B)"),
    (r"\bgh\s+pr\s+review\b[^;&|]*(--approve|\s-a\b)", "approving PRs is a human decision"),
    (
        r"\bgh\s+api\b[^;&|]*(/merge\b|/reviews\b|/rulesets\b|/branches/[^ ]+/protection)",
        "merge/approve/protection via API",
    ),
    (
        r"\bterraform\s+(apply|destroy|import|state\s+(rm|mv|push|replace-provider))\b",
        "infrastructure changes run in CI",
    ),
    (
        r"\bkubectl\s+(apply|create|delete|edit|patch|replace|scale|label|annotate|drain|cordon|"
        r"rollout\s+(restart|undo))\b",
        "cluster changes are made by the pipeline, not the agent",
    ),
    (r"\bhelm\s+(install|upgrade|uninstall|delete|rollback)\b", "deployments are made by the pipeline"),
    (
        r"\baws\s+\S+\s+(create|delete|put|update|terminate|modify|attach|detach|run|start|stop|reboot|remove|add|"
        r"associate|disassociate|enable|disable|tag|untag)-",
        "mutating AWS calls are made by the pipeline",
    ),
    (r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+(/|~|\$HOME|\.)(\s|$)", "recursive delete of a root, home or repo directory"),
    (r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba|z)?sh\b", "piping downloads into a shell"),
    (
        r"(>|\btee\b|\bsed\s+-i|\bcp\b|\bmv\b|\brm\b)[^;&|]*"
        r"(\.github/|\.claude/settings\.json|\.claude/idp-protected-paths)",
        "writing protected paths via the shell",
    ),
]
COMPILED = [(re.compile(p, re.IGNORECASE), why) for p, why in RULES]

# Spec approval (IDP-14): a raw mention blocks unless it lies in a span the lexer relaxed.
APPROVE_WHY = "spec approval is a human checkpoint (A)"
MARKER_WHY = "the APPROVED marker is written only by `make approve-spec`, run by a human"
MENTION = re.compile(r"approve-spec|(?<![\w.-])approved(?![\w.-])", re.IGNORECASE)
MAX_DEPTH = 8  # nested $( ) levels the lexer follows

# test, [ and [[ only relax plain marker paths (READ) and are neither printers nor inert: bash evaluates array
# subscripts such as 'a[$(cmd)]' in their arguments, and in the variable name of printf -v (IDP-14 amendment 2).
TESTS = {"test", "[", "[["}
READERS = {"cat", "ls", "head", "tail", "wc", "grep", "egrep", "fgrep", "rg"} | TESTS
PRINTERS = (READERS - {"ls"} - TESTS) | {"echo", "printf", "jq", "true", ":"}
INERT = PRINTERS | (READERS - TESTS) | {"tee", "cd", "mkdir", "pwd", "false"}
GIT_READ = {"log", "show", "status", "diff"}
GIT_DATA = GIT_READ | {"grep"}
GIT_MESSAGE = {"commit", "tag", "notes"}
GH_OBJECTS = {"issue", "pr", "release"}
GH_VERBS = {"create", "edit", "comment"}

_PLAIN = re.compile(r"[^ \t\n;&|()<>\\'\"$`]+")
_DQ_SPECIAL = re.compile(r'[\\"$`]')
_ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.DOTALL)
_SIMPLE_PARAM = re.compile(r"\$\{(?:#?[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-])\}")
_OUTPUT = re.compile(r"-o.*|--output.*|of=.*|-w|--pre.*|-O.*|--open-files-in-pager.*")


class _Unsure(Exception):
    """The lexer cannot follow the shell here, so nothing is relaxed."""


class _Word:
    """One shell word: its literal text (for names and options) and the raw spans that may be relaxed."""

    def __init__(self, start):
        self.start = start
        self.end = start
        self.text = ""
        self.plain = True  # only unquoted, unescaped characters
        self.data = []  # spans of quoted text that the shell does not expand
        self.inner = []  # spans relaxed inside a $( ) of this word


class _Command:
    """One simple command: its words and the spans of its heredoc bodies that are literal data."""

    def __init__(self):
        self.words = []
        self.bodies = []


class _Lexer:
    """Splits a command into simple commands the way bash does, or raises _Unsure."""

    def __init__(self, text):
        self.s = text
        self.i = 0
        self.commands = []  # every simple command, at every nesting level
        self.pending = []  # heredocs waiting for the end of the line: (delimiter, strip_tabs, literal, command, depth)

    def scan(self, depth):
        """Simple commands up to the end of the text, or (depth > 0) up to the `)` closing a substitution."""
        s, cmds, cmd, parens = self.s, [], _Command(), 0
        while True:
            self.blanks()
            if self.i >= len(s):
                if depth or self.pending:
                    raise _Unsure
                self.finish(cmd, cmds)
                return cmds
            c = s[self.i]
            if c == "#":  # a comment: skipped, so its mentions are never relaxed
                end = s.find("\n", self.i)
                self.i = len(s) if end < 0 else end
            elif c in "<>" or s.startswith("&>", self.i):
                self.redirect(cmd, depth)
            elif c in ";&|\n()":
                if s.startswith("((", self.i):
                    raise _Unsure  # arithmetic
                self.i += 1
                cmd = self.finish(cmd, cmds)
                if c == "\n":
                    self.bodies(depth)
                elif c == "(":
                    parens += 1
                elif c == ")" and depth and not parens:
                    if self.pending:
                        raise _Unsure
                    return cmds
                elif c == ")":
                    parens -= 1
            else:
                cmd.words.append(self.word(depth))

    def blanks(self):
        s = self.s
        while self.i < len(s) and (s[self.i] in " \t" or s.startswith("\\\n", self.i)):
            self.i += 1 if s[self.i] in " \t" else 2

    def finish(self, cmd, cmds):
        """Close a simple command and return a fresh one."""
        if cmd.words:
            if cmd.words[0].text == "case":
                raise _Unsure  # `case` patterns end in `)`
            cmds.append(cmd)
            self.commands.append(cmd)
        return _Command()

    def redirect(self, cmd, depth):
        """A redirection, whose target is never relaxed; `<<` and `<<-` start a heredoc."""
        s = self.s
        if s.startswith(("<(", ">("), self.i):
            raise _Unsure  # process substitution
        if s.startswith("<<", self.i) and not s.startswith("<<<", self.i):
            strip_tabs = s.startswith("<<-", self.i)
            self.i += 3 if strip_tabs else 2
            self.blanks()
            start = self.i
            delimiter = self.word(depth)
            if not delimiter.text or "$" in s[start : self.i]:
                raise _Unsure
            self.pending.append((delimiter.text, strip_tabs, not delimiter.plain, cmd, depth))
            return
        while self.i < len(s) and s[self.i] in "<>&|":
            self.i += 1
        self.blanks()
        target = self.word(depth)
        if target.end == target.start:
            raise _Unsure  # a redirection without a target

    def bodies(self, depth):
        """Read the heredoc bodies that start after the newline just passed."""
        s, pending, self.pending = self.s, self.pending, []
        for delimiter, strip_tabs, literal, cmd, level in pending:
            if level != depth:
                raise _Unsure
            start = line_start = self.i
            while True:
                if self.i >= len(s):
                    raise _Unsure  # no terminator line
                line_start = self.i
                end = s.find("\n", line_start)
                end = len(s) if end < 0 else end
                self.i = end + 1
                line = s[line_start:end]
                if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                    break
            body = s[start:line_start]
            if not literal and "\\" in body:
                raise _Unsure  # a backslash-newline could move the terminator line
            if literal or not any(x in body for x in ("$(", "`", "${")):
                cmd.bodies.append((start, line_start))

    def word(self, depth):
        """One word; quoted literal text is recorded as data, and $( ) inside it is scanned as code."""
        s, w, text = self.s, _Word(self.i), []
        while self.i < len(s):
            plain = _PLAIN.match(s, self.i)
            if plain:
                text.append(plain.group())
                self.i = plain.end()
                continue
            c = s[self.i]
            if c in " \t\n;&|()<>":
                break
            w.plain = False
            if c == "\\":
                text.append(s[self.i + 1 : self.i + 2].strip("\n"))
                self.i += 2
            elif c == "'":
                end = s.find("'", self.i + 1)
                if end < 0:
                    raise _Unsure
                w.data.append((self.i + 1, end))
                text.append(s[self.i + 1 : end])
                self.i = end + 1
            elif c == '"':
                text.append(self.double(w, depth))
            elif c == "`":
                raise _Unsure
            elif s.startswith("$'", self.i):
                ansi = _ANSI_C.match(s, self.i)
                if not ansi:
                    raise _Unsure
                w.data.append(ansi.span(1))
                text.append(ansi.group(1))
                self.i = ansi.end()
            elif s.startswith('$"', self.i):
                self.i += 1
                text.append(self.double(w, depth))
            else:
                self.dollar(w, depth)
        w.end, w.text = self.i, "".join(text)
        return w

    def double(self, w, depth):
        """Double-quoted text from its opening quote: data unless it holds $( ), which is scanned as code."""
        s, start = self.s, self.i + 1
        self.i, code = start, False
        while True:
            special = _DQ_SPECIAL.search(s, self.i)
            if not special:
                raise _Unsure
            self.i = special.start()
            c = s[self.i]
            if c == '"':
                break
            if c == "\\":
                self.i += 2
            elif c == "`":
                raise _Unsure
            else:
                code = self.dollar(w, depth) or code
        if not code:
            w.data.append((start, self.i))
        self.i += 1
        return s[start : self.i - 1]

    def dollar(self, w, depth):
        """`$` here: a $( ) substitution (scanned; returns True), a simple parameter, or a plain `$`."""
        s, i = self.s, self.i
        if s.startswith("$((", i):
            raise _Unsure  # arithmetic
        if s.startswith("$(", i):
            if depth >= MAX_DEPTH:
                raise _Unsure
            self.i = i + 2
            w.inner.extend(_accepted(self.scan(depth + 1)))
            return True
        param = _SIMPLE_PARAM.match(s, i)
        if s.startswith("${", i) and not param:
            raise _Unsure
        self.i = param.end() if param else i + 1
        return False


def _values(words, options):
    """Words that are the value of one of the options (`-m msg`, `--message=msg`)."""
    return [
        w for k, w in enumerate(words) if k and (words[k - 1].text in options or w.text.split("=", 1)[0] in options)
    ]


def _data_positions(cmd):
    """(words whose quoted text is data, whether heredoc bodies are data) for a printer command (rule a)."""
    words = cmd.words
    if not words[0].plain or any(_OUTPUT.fullmatch(w.text) for w in words):
        return [], False
    name, sub = words[0].text, [w.text for w in words[1:3]]
    if name == "printf" and any(w.text.startswith("-v") for w in words):
        return [], False  # printf -v assigns to a variable, and bash evaluates a subscript in its name
    if name in PRINTERS:
        return words[1:], True
    if name == "tee":
        return [], True
    if name == "git" and sub and sub[0] in GIT_DATA:
        return words[2:], False
    if name == "git" and sub and sub[0] in GIT_MESSAGE:
        return _values(words, {"-m", "--message"}), False
    if name == "gh" and len(sub) == 2 and sub[0] in GH_OBJECTS and sub[1] in GH_VERBS:
        stdin = any(words[k].text in {"--body-file", "-F"} and words[k + 1].text == "-" for k in range(len(words) - 1))
        return _values(words, {"--body", "--title", "-b", "-t"}), stdin
    return [], False


def _accepted(cmds):
    """Relaxed data spans of these commands, including data printed inside a $( ) that is itself data."""
    spans = []
    for cmd in cmds:
        words, stdin = _data_positions(cmd)
        if stdin:
            spans.extend(cmd.bodies)
        for w in words:
            spans.extend(w.data + w.inner)
    return spans


def _inert(cmd):
    """True for commands that cannot run text or files as code."""
    head = cmd.words[0]
    sub = cmd.words[1].text if len(cmd.words) > 1 else ""
    if not head.plain:
        return False
    if head.text == "git":
        return sub in GIT_DATA | GIT_MESSAGE
    if head.text == "gh":
        return sub in GH_OBJECTS
    return head.text in INERT


def _reads(cmd):
    """Spans of plain arguments of read-only commands (rule b; relaxes marker mentions only)."""
    words = cmd.words
    if not words[0].plain or any(_OUTPUT.fullmatch(w.text) for w in words):
        return []
    name = words[0].text
    if name == "git":
        first = 2 if len(words) > 1 and words[1].text in GIT_READ else len(words)
    else:
        first = 1 if name in READERS else len(words)
    return [
        (w.start, w.end)
        for k, w in enumerate(words[first:], first)
        if w.plain and not w.text.startswith("-") and (name not in TESTS or words[k - 1].text in {"-f", "-e", "-s"})
    ]


def _covered(spans, start, end):
    """True if [start, end) lies inside one of the sorted, disjoint spans."""
    k = bisect.bisect_right(spans, (start, float("inf"))) - 1
    return k >= 0 and spans[k][1] >= end


def approval_violation(command):
    """Block a mention of spec approval or of the APPROVED marker unless the lexer relaxed its position."""
    mentions = [(m.start(), m.end(), m.group().lower() == "approve-spec") for m in MENTION.finditer(command)]
    if not mentions:
        return None
    data, reads = [], []
    try:
        lexer = _Lexer(command)
        cmds = lexer.scan(0)
        reads = [span for cmd in lexer.commands for span in _reads(cmd)]
        if all(_inert(cmd) for cmd in lexer.commands):
            data = _accepted(cmds)
    except _Unsure:
        data, reads = [], []
    data.sort()
    marker_spans = sorted(data + reads)
    left = [run for start, end, run in mentions if not _covered(data if run else marker_spans, start, end)]
    if not left:
        return None
    return APPROVE_WHY if any(left) else MARKER_WHY


def check(command):
    for rx, why in COMPILED:
        if rx.search(command):
            return why
    return approval_violation(command)


def main():
    data = json.load(sys.stdin)
    command = (data.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        command = json.dumps(command)  # never crash: a crash (exit 1) would not block
    why = check(command)
    if why:
        sys.stderr.write(
            "BLOCKED by idp-agentic: {}.\nCommand: {}\nAgents prepare work; people merge, approve and deploy. "
            "Explain to the user what you wanted to do instead.\n".format(why, command)
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
