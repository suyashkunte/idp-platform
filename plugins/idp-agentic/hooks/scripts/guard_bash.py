#!/usr/bin/env python3
"""PreToolUse guard for Bash: block commands that bypass human checkpoints or change shared state (exit 2 = block).

Defence in depth behind the permission deny-list and GitHub rulesets. Stdlib only, Python 3.9+.

Spec approval (IDP-14) is judged by what a command runs or writes, not by text it only mentions. A small lexer
replaces heredoc bodies and quoted text with a DATA mark, then each simple command is checked. Any mention still
blocks, as before IDP-14, when the lexer is unsure (unterminated quotes or heredocs, backticks, complex expansions),
when text may reach a shell or interpreter, or when data goes to a command that does not only print or record it.
"""

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

# Spec approval (IDP-14)
APPROVE_WHY = "spec approval is a human checkpoint (A)"
MARKER_WHY = "the APPROVED marker is written only by `make approve-spec`, run by a human"
# Fail-closed view, used when the lexer is unsure: any mention blocks (covers both pre-IDP-14 rules).
MENTION = re.compile(r"approve-spec|specs/[^/\s]+/APPROVED", re.IGNORECASE)
UNSURE = "unsure"  # verdict for a simple command where only the mention check is safe
DATA = "\x00"  # stands for quoted text and for a skipped heredoc body
MAX_DEPTH = 8  # nested $( ) levels the lexer follows
KEEP_ESCAPED = "-_./=+,:@%~"  # escaped characters that stay part of a word (besides letters, digits, blanks)

KEYWORDS = frozenset({"if", "then", "else", "elif", "do", "while", "until", "coproc"})
RUNNERS = frozenset({"make", "gmake", "idp"})
MAKES = frozenset({"make", "gmake"})
WRITERS = frozenset({"cp", "dd", "install", "ln", "mv", "rm", "rsync", "tee", "touch", "truncate"})
GIT_WRITERS = frozenset({"add", "apply", "checkout", "mv", "restore", "rm", "stage", "update-index"})
PRINTERS = frozenset(
    {
        "cat",
        "echo",
        "printf",
        "tee",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "head",
        "tail",
        "wc",
        "jq",
        "test",
        "[",
        "[[",
        "sort",
        "diff",
        "true",
        ":",
    }
)
GIT_PRINTERS = frozenset({"commit", "diff", "grep", "log", "notes", "show", "stash", "status", "tag"})
GH_OBJECTS = frozenset({"issue", "pr", "release"})
GH_PRINTERS = frozenset({"close", "comment", "create", "edit", "list", "reopen", "view"})

# Lexer
_PLAIN = re.compile(r"[^\\'\"$`#<>()\n]+")
_DQ_SPECIAL = re.compile(r'[\\"$`]')
_ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.DOTALL)
_SIMPLE_PARAM = re.compile(r"\$\{(?:#?[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-])\}")
_HEREDOC = re.compile(r"<<-?[ \t]*")
_CASE = re.compile(r"(?:^|[\s;&|(])case\s")
_NOT_A_WORD = re.compile(r"[\s;&|<>(){}`!]")

# Analysis of the masked text (words are lower-cased)
_SEPARATORS = re.compile(r"[\n;&|(){}`!]")
_REDIRECT = re.compile(r">[>|&]?[ \t]*([^\s<>;&|()]+)")
_NOISE = re.compile(r"\$(?=['\"])|['\"\\\x00]")
_ASSIGNMENT = re.compile(r"[a-z_][a-z0-9_]*\+?=")
_REDIRECT_OP = re.compile(r"[0-9]*[<>]+[-&|]?")
_REDIRECT_WORD = re.compile(r"[0-9]*[<>]")
_MARKER = re.compile(r"(?:^|[/=])approved$")
_SED_IN_PLACE = re.compile(r"-[a-z]*i|--in-place")
_MAKE_READS_TEXT = re.compile(r"-[a-z]*[ef]|--(?:file|makefile|eval)")
_GIT_RUNS_TEXT = re.compile(r"-c|--config-env.*|-x|--exec.*|bisect|foreach|filter-branch")
_INTERPRETER = re.compile(
    r"(?:ba|z|da|k|c|tc|fi|mk|)sh|eval|source|\.|xargs|parallel|su|ssh|script|at|batch|crontab|alias|"
    r"python[0-9.]*|pypy[0-9.]*|perl|ruby|node|deno|bun|php|lua|tclsh|expect|osascript|pwsh|busybox|[gmn]?awk"
)


class _Unsure(Exception):
    """Raised when the lexer cannot tell code from data."""


class _State:
    """Lexer position plus the heredocs whose bodies start after the next newline."""

    def __init__(self, text):
        self.s = text
        self.i = 0
        self.heredocs = []  # (delimiter, strip_tabs, literal)


def _quoted(content):
    """Quoted text: a plain word stays visible without its quotes; anything else becomes DATA."""
    word = content.strip()
    return DATA if _NOT_A_WORD.search(word) else word


def _scan(st, depth, nested):
    """Mask text from st.i to the end, or (nested) to the `)` that closes a substitution."""
    s, out, parens = st.s, [], 0
    while st.i < len(s):
        i = st.i
        plain = _PLAIN.match(s, i)
        if plain:
            out.append(plain.group())
            st.i = plain.end()
            continue
        c = s[i]
        st.i = i + 1
        if c == "\\":
            nxt = s[i + 1 : i + 2]
            st.i = i + 2
            if nxt != "\n":  # backslash-newline joins lines
                out.append(nxt if nxt.isalnum() or nxt.isspace() or nxt in KEEP_ESCAPED else "_")
        elif c == "'":
            end = s.find("'", st.i)
            if end < 0:
                raise _Unsure
            out.append(_quoted(s[st.i : end]))
            st.i = end + 1
        elif c == '"':
            out.append(_double(st, depth))
        elif c == "$":
            out.append(_dollar(st, depth))
        elif c == "`":
            raise _Unsure
        elif c == "#" and (i == 0 or s[i - 1] in " \t\n;&|()<>"):
            end = s.find("\n", i)
            st.i = len(s) if end < 0 else end  # a comment runs to the end of the line
        elif c in "<>":
            out.append(_angle(st, depth))
        elif c == "(":
            parens += 1
            out.append(c)
        elif c == ")" and nested and parens == 0:
            if st.heredocs:
                raise _Unsure
            return "".join(out)
        elif c == ")":
            parens = max(parens - 1, 0)
            out.append(c)
        elif c == "\n":
            out.append(c)
            _skip_bodies(st)
        else:  # `#` inside a word
            out.append(c)
    if nested or st.heredocs:
        raise _Unsure
    return "".join(out)


def _double(st, depth):
    """Double-quoted text after its opening quote: $( ) inside is code, the rest is data."""
    s, parts, text = st.s, [], []
    while True:
        special = _DQ_SPECIAL.search(s, st.i)
        if not special:
            raise _Unsure
        j = special.start()
        text.append(s[st.i : j])
        c = s[j]
        st.i = j + 1
        if c == '"':
            parts.append(_quoted("".join(text)))
            return "".join(parts)
        if c == "\\":
            text.append(s[j + 1 : j + 2])
            st.i = j + 2
        elif c == "`" or s.startswith("$((", j):
            raise _Unsure
        elif s.startswith("$(", j):
            parts.append(_quoted("".join(text)))
            text = []
            st.i = j + 2
            parts.append("$(" + _substitution(st, depth) + ")")
        elif s.startswith("${", j):
            param = _SIMPLE_PARAM.match(s, j)
            if not param:
                raise _Unsure
            text.append(param.group())
            st.i = param.end()
        else:
            text.append(c)


def _dollar(st, depth):
    """`$` at st.i - 1: ANSI-C or locale quotes, a substitution, a simple parameter, or a plain `$`."""
    s, i = st.s, st.i - 1
    if s.startswith("$'", i):
        ansi = _ANSI_C.match(s, i)
        if not ansi:
            raise _Unsure
        st.i = ansi.end()
        return _quoted(ansi.group(1))
    if s.startswith('$"', i):
        st.i = i + 2
        return _double(st, depth)
    if s.startswith("$((", i):
        raise _Unsure
    if s.startswith("$(", i):
        st.i = i + 2
        return "$(" + _substitution(st, depth) + ")"
    if s.startswith("${", i):
        param = _SIMPLE_PARAM.match(s, i)
        if not param:
            raise _Unsure
        st.i = param.end()
        return param.group()
    return "$"


def _angle(st, depth):
    """`<` or `>` at st.i - 1: process substitution, here-string, heredoc or a plain redirection."""
    s, i = st.s, st.i - 1
    if s.startswith(("<(", ">("), i):
        st.i = i + 2
        return s[i] + "(" + _substitution(st, depth) + ")"
    if s.startswith("<<<", i):
        st.i = i + 3
        return "<<<"
    if s.startswith("<<", i):
        return _heredoc(st, i)
    return s[i]


def _heredoc(st, i):
    """Read a heredoc operator and its delimiter; the body follows the next newline."""
    s = st.s
    j = _HEREDOC.match(s, i).end()
    strip_tabs = s.startswith("<<-", i)
    word, literal = [], False
    while j < len(s) and s[j] not in " \t\n;&|<>()":
        c = s[j]
        if c in ("'", '"'):
            end = s.find(c, j + 1)
            if end < 0:
                raise _Unsure
            word.append(s[j + 1 : end])
            literal, j = True, end + 1
        elif c == "\\":
            word.append(s[j + 1 : j + 2])
            literal, j = True, j + 2
        elif c in "$`":
            raise _Unsure
        else:
            word.append(c)
            j += 1
    delimiter = "".join(word)
    if not delimiter:
        raise _Unsure
    st.heredocs.append((delimiter, strip_tabs, literal))
    st.i = j
    return s[i:j] + DATA


def _skip_bodies(st):
    """Skip the bodies of the heredocs opened on the line that just ended."""
    s = st.s
    for delimiter, strip_tabs, literal in st.heredocs:
        start = st.i
        while True:
            if st.i >= len(s):
                raise _Unsure  # no terminator line
            line_start = st.i
            end = s.find("\n", line_start)
            end = len(s) if end < 0 else end
            st.i = end + 1
            line = s[line_start:end]
            if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                break
        if not literal and any(x in s[start:line_start] for x in ("$(", "`", "${", "\\")):
            raise _Unsure  # the shell expands this body
    st.heredocs = []


def _substitution(st, depth):
    """Code inside $( ), <( ) or >( ) up to its closing parenthesis."""
    if depth >= MAX_DEPTH:
        raise _Unsure
    inner = _scan(st, depth + 1, True)
    if _CASE.search(inner):
        raise _Unsure  # a `case` pattern's `)` would end the substitution too early
    return inner


def _mask(command):
    """The command with heredoc bodies and quoted text replaced by DATA (plain quoted words are kept)."""
    return _scan(_State(command), 0, False)


def _norm(word):
    return _NOISE.sub("", word).lower()


def _base(word):
    """Command name without its directory (and without zsh's `=` path expansion)."""
    return word.lstrip("=").rsplit("/", 1)[-1]


def _command(words):
    """The words of a simple command after leading keywords, assignments and redirections."""
    i = 0
    while i < len(words):
        word = words[i]
        if word in KEYWORDS or _ASSIGNMENT.match(word):
            i += 1
        elif _REDIRECT_OP.fullmatch(word):
            i += 2
        elif _REDIRECT_WORD.match(word):
            i += 1
        else:
            break
    return words[i:]


def _prints_only(cmd):
    """True for commands that only print, search or record text, so quoted text and heredocs are data for them."""
    name = _base(cmd[0])
    if name == "git":
        return len(cmd) > 1 and cmd[1] in GIT_PRINTERS
    if name == "gh":
        return len(cmd) > 2 and cmd[1] in GH_OBJECTS and cmd[2] in GH_PRINTERS
    return name in PRINTERS


def _is_marker(cmd, k):
    """cmd[k] names an APPROVED file and is not a commit message (`-m APPROVED`)."""
    word = cmd[k]
    is_message = word.startswith("--message=") or (k > 0 and cmd[k - 1] in ("-m", "--message"))
    return not is_message and _MARKER.search(word) is not None


def _verdict(words, has_data):
    """APPROVE_WHY, MARKER_WHY, UNSURE or None for one simple command, given as normalised words."""
    cmd = _command(words)
    if not cmd:
        return UNSURE if has_data else None
    printer = _prints_only(cmd)
    approve = max((k for k, w in enumerate(cmd) if w == "approve-spec"), default=-1)
    marker = max((k for k in range(len(cmd)) if _is_marker(cmd, k)), default=-1)
    makes_text = any(_MAKE_READS_TEXT.match(w) for w in cmd)
    git_runs_text = any(_GIT_RUNS_TEXT.fullmatch(w) for w in cmd)
    in_place = any(_SED_IN_PLACE.match(w) for w in cmd)
    git_writes = not GIT_WRITERS.isdisjoint(cmd)
    for k, word in enumerate(cmd[:1] if printer else cmd):
        name = _base(word)
        if _INTERPRETER.fullmatch(name) or (name in MAKES and makes_text) or (name == "git" and git_runs_text):
            return UNSURE
        if name in RUNNERS and k < approve:
            return APPROVE_WHY
        if k < marker and (name in WRITERS or (name == "sed" and in_place) or (name == "git" and git_writes)):
            return MARKER_WHY
    return UNSURE if has_data and not printer else None


def _mention(command):
    """Fail-closed check used when the lexer is unsure: any mention blocks (the pre-IDP-14 behaviour)."""
    found = MENTION.search(command)
    if not found:
        return None
    return APPROVE_WHY if found.group().lower() == "approve-spec" else MARKER_WHY


def approval_violation(command):
    """Block running spec approval or writing an APPROVED marker; mentions alone pass unless the lexer is unsure."""
    try:
        masked = _mask(command)
    except _Unsure:
        return _mention(command)
    for target in _REDIRECT.findall(masked):
        if _MARKER.search(_norm(target)):
            return MARKER_WHY
    unsure = False
    for segment in _SEPARATORS.split(masked):
        words = [w for w in map(_norm, segment.split()) if w]
        verdict = _verdict(words, DATA in segment)
        if verdict == UNSURE:
            unsure = True
        elif verdict:
            return verdict
    return _mention(command) if unsure else None


def check(command):
    for rx, why in COMPILED:
        if rx.search(command):
            return why
    return approval_violation(command)


def main():
    data = json.load(sys.stdin)
    command = (data.get("tool_input") or {}).get("command") or ""
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
