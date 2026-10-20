# IDP-14: plan

## Approach
The smallest design that meets AC-1..AC-3 without weakening the guard:
- Keep every rule in `RULES` except the two approval rules unchanged, running on the raw command first (AC-4).
- Replace the two approval rules with `approval_violation(command)`. It has two parts:
  1. A small lexer masks the command:
     - heredoc bodies are dropped;
     - quoted text that contains a blank or a shell metacharacter becomes a `DATA` mark (`\x00`);
     - plain quoted words lose their quotes;
     - comments are removed;
     - `$( )`, `<( )` and `>( )` are lexed recursively as code.
  2. The masked text is split into simple commands. For each one:
     - block when it runs `make`/`gmake`/`idp` with a later `approve-spec` word (AC-1);
     - block when it redirects into, or writes with a known writer to, a word whose last component is `APPROVED`
       (AC-2).
- Fail closed: in each of these cases, the old-style mention check on the raw command decides (any `approve-spec` or
  `specs/<x>/APPROVED` blocks):
  - the lexer is unsure (unterminated quotes or heredocs, backticks, complex `${...}`, `$((`, depth > 8, `case`
    inside `$( )`);
  - a non-printer command contains a shell or interpreter word (or `make -f/-e/--eval`, `git -c/-x/--exec/...`);
  - `DATA` goes to a command that is not a known printer.

  So the change only removes blocks for commands we can show are mention-only (spec Q2, Q3).
- Masking applies only to the approval checks, not to the other rules (spec Q1, A6). This is the smallest behaviour
  change, and AC-4 holds by construction.

Work split:
- H1 (human, protected path): replace `plugins/idp-agentic/hooks/scripts/guard_bash.py` with the code below.
- T1 (agent): the tests.
- T2 (agent): the `pr-generate` SKILL.md edit with its test (AC-5).
- T3 (agent): CHANGELOG.

## H1: replacement for `plugins/idp-agentic/hooks/scripts/guard_bash.py`
Complete file. It is stdlib-only and Python 3.9-compatible (no `match`, no `X | Y`, no `removeprefix`, no
walrus), and it is written to be ruff-clean and ruff-format-stable. `check()` and `main()` keep their signatures and
the stderr message format.

```python
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
```

### H1 steps (human, in your own terminal, right after `make approve-spec KEY=IDP-14`)
1. On `feature/IDP-14-guard-bash-false-positive`, replace the whole content of
   `plugins/idp-agentic/hooks/scripts/guard_bash.py` with the block above. Editing the existing file in place keeps
   its executable bit, which `test_hooks_reference_existing_executable_scripts` checks.
2. Check:
   ```bash
   ls -l plugins/idp-agentic/hooks/scripts/guard_bash.py          # still -rwxr-xr-x
   uv run ruff format --check plugins/idp-agentic/hooks/scripts/guard_bash.py
   uv run ruff check plugins/idp-agentic/hooks/scripts/guard_bash.py
   /usr/bin/python3 --version                                      # 3.9.x on macOS
   /usr/bin/python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read(), feature_version=(3, 9))' \
     plugins/idp-agentic/hooks/scripts/guard_bash.py && echo "3.9 syntax ok"
   /usr/bin/python3 plugins/idp-agentic/hooks/scripts/guard_bash.py <<'JSON'; echo "exit $?"
   {"tool_input": {"command": "cat > pr.md <<'EOF'\nRun `make approve-spec KEY=IDP-14` first.\nEOF"}}
   JSON
   /usr/bin/python3 plugins/idp-agentic/hooks/scripts/guard_bash.py <<'JSON'; echo "exit $?"
   {"tool_input": {"command": "cd specs && make approve-spec KEY=IDP-14"}}
   JSON
   make validate-plugin
   ```
   Expected results:
   - ruff: no changes and no findings. If `ruff format --check` reports a diff, run `uv run ruff format` on the file;
     it only changes layout.
   - First smoke command: `exit 0`. Second: `BLOCKED by idp-agentic: spec approval is a human checkpoint (A).` and
     `exit 2`.
   - `make validate-plugin`: green (the existing lists, AC-4).
3. Commit only that file:
   `git add plugins/idp-agentic/hooks/scripts/guard_bash.py && git commit -m "IDP-14: judge spec approval by what a command runs or writes"`.
4. Optional (spec Q5, if confirmed): bump `"version"` to `0.1.1` in `plugins/idp-agentic/.claude-plugin/plugin.json`
   and in both places in `.claude-plugin/marketplace.json` (`metadata.version`, `plugins[0].version`), in the same
   or a second commit. Then run `make validate-plugin` again.
5. If any check fails, stop and tell the agent; the spec is revised (re-approval needed).

## Tests (agent; T1 and T2)
`tests/plugin/test_hooks.py`. Reuse `run_hook`. Add a helper `bash(command) -> dict` returning
`{"tool_name": "Bash", "tool_input": {"command": command}}`, and module-level case lists. Every new test is tagged
`@pytest.mark.ac("IDP-14:AC-n")`. Because H1 lands first, these tests pass when written. The red-first evidence is
collected in T1 against the pre-H1 hook (see tasks.md).
- `test_running_spec_approval_is_blocked` (AC-1), parametrized over `RUNS_APPROVAL`. Assert returncode 2 and
  `"spec approval is a human checkpoint"` in stderr:
  ```python
  RUNS_APPROVAL = [
      "cd specs && make approve-spec KEY=IDP-1",
      "make verify; make approve-spec KEY=IDP-1",
      "false || make approve-spec KEY=IDP-1",
      "echo y | make approve-spec KEY=IDP-1",
      "make verify\nmake approve-spec KEY=IDP-1",
      "echo $(make approve-spec KEY=IDP-1)",
      'echo "$(make approve-spec KEY=IDP-1)"',
      "x=$(uv run idp approve-spec IDP-1)",
      "(make approve-spec KEY=IDP-1)",
      "{ make approve-spec KEY=IDP-1; }",
      "! make approve-spec KEY=IDP-1",
      "if true; then make approve-spec KEY=IDP-1; fi",
      "KEY=IDP-1 make approve-spec",
      "> out.txt make approve-spec KEY=IDP-1",
      "env FOO=1 make approve-spec KEY=IDP-1",
      "command make approve-spec KEY=IDP-1",
      "nohup make approve-spec KEY=IDP-1 &",
      "time make approve-spec KEY=IDP-1",
      "sudo -u me make approve-spec KEY=IDP-1",
      "timeout 5 uv run idp approve-spec IDP-1",
      "caffeinate make approve-spec KEY=IDP-1",
      "idp approve-spec IDP-1",
      ".venv/bin/idp approve-spec IDP-1",
      "=make approve-spec KEY=IDP-1",
      "MAKE approve-spec KEY=IDP-1",
      "make -s approve-spec KEY=IDP-1",
      "make KEY=IDP-1 approve-spec",
      "make 'approve-spec' KEY=IDP-1",
      "m\\ake approve-spec KEY=IDP-1",
      'git commit -m "$( (true); make approve-spec KEY=IDP-1 )"',
      "cat <(make approve-spec KEY=IDP-1)",
      "sh -c 'make approve-spec KEY=IDP-1'",
      'bash -c "cd x; uv run idp approve-spec IDP-1"',
      "zsh -c 'idp approve-spec IDP-1'",
      "eval 'make approve-spec KEY=IDP-1'",
      "echo 'make approve-spec KEY=IDP-1' | sh",
      "bash <<'EOF'\nmake approve-spec KEY=IDP-1\nEOF",
      "echo IDP-1 | xargs idp approve-spec",
      "printf 'approve-spec' | xargs make",
      "python3 -c 'import os; os.system(\"make approve-spec KEY=IDP-1\")'",
      "make -f - x <<'EOF'\nx:\n\tidp approve-spec IDP-1\nEOF",
      "make --eval='x: ; idp approve-spec IDP-1' x",
      "git -c alias.x='!make approve-spec KEY=IDP-1' x",
      "env -S 'make approve-spec KEY=IDP-1'",
      "find . -exec make approve-spec KEY=IDP-1 \\;",
  ]
  ```
- `test_writing_the_approved_marker_is_blocked` (AC-2), parametrized over `WRITES_MARKER`. Assert returncode 2 and
  `"APPROVED marker"` in stderr:
  ```python
  WRITES_MARKER = [
      "echo ok >specs/IDP-1/APPROVED",
      "echo ok >> specs/IDP-1/APPROVED",
      'echo ok > "specs/IDP-1/APPROVED"',
      "echo ok > 'specs/IDP-1/APPROVED'",
      'echo ok > "specs/$KEY/APPROVED"',
      "printf x >| specs/IDP-1/APPROVED",
      "echo ok &> specs/IDP-1/APPROVED",
      "echo ok 1>specs/IDP-1/APPROVED",
      "cat /tmp/a > ./specs/IDP-1/APPROVED",
      "echo ok > specs/IDP-1/approved",
      "cat > specs/IDP-1/APPROVED <<'EOF'\n{}\nEOF",
      "echo ok | tee specs/IDP-1/APPROVED",
      "echo ok | tee -a specs/IDP-1/APPROVED",
      "sudo tee specs/IDP-1/APPROVED < /tmp/a",
      "cp /tmp/a specs/IDP-1/APPROVED",
      "mv /tmp/a specs/IDP-1/APPROVED",
      "install -m 644 /tmp/a specs/IDP-1/APPROVED",
      "ln -s /tmp/a specs/IDP-1/APPROVED",
      "touch specs/IDP-1/APPROVED",
      "truncate -s 0 specs/IDP-1/APPROVED",
      "dd if=/tmp/a of=specs/IDP-1/APPROVED",
      "rsync /tmp/a specs/IDP-1/APPROVED",
      "sed -i '' 's/a/b/' specs/IDP-1/APPROVED",
      "sed -i.bak s/a/b/ specs/IDP-1/APPROVED",
      "git add specs/IDP-1/APPROVED",
      "git add -f specs/IDP-1/APPROVED",
      "git checkout main -- specs/IDP-1/APPROVED",
      "git restore --source=main specs/IDP-1/APPROVED",
      "cd specs/IDP-1 && touch APPROVED",
      "cd specs/IDP-1 && echo ok > APPROVED",
      "python3 -c \"open('specs/IDP-1/APPROVED', 'w')\"",
  ]
  ```
- `test_mentioning_approval_as_text_is_allowed` (AC-3), parametrized over `MENTIONS_ONLY`. Assert returncode 0
  (message `f"{command}: {result.stderr}"`). The bodies avoid text that the unchanged raw rules match (`.github/`,
  `gh pr merge`, `git push ... main`; spec Q1):
  ```python
  PR_BODY = (
      "## Spec\n"
      "Spec: `specs/IDP-14/spec.md` (approval: run `make approve-spec KEY=IDP-14` before merge).\n"
      "make approve-spec KEY=IDP-14\n"
      "The marker specs/IDP-14/APPROVED records the spec hash; `uv run idp approve-spec IDP-14` is refused here.\n"
  )
  MENTIONS_ONLY = [
      f"cat > pr.md <<'EOF'\n{PR_BODY}EOF",
      f'cat > pr.md <<"EOF"\n{PR_BODY}EOF',
      f"cat > pr.md <<\\EOF\n{PR_BODY}EOF",
      "cat > pr.md <<EOF\nRun make approve-spec KEY=IDP-14, which writes specs/IDP-14/APPROVED.\nEOF",
      "cat > notes.md <<-EOF\n\tmake approve-spec KEY=IDP-14\n\tEOF",
      "cat >> notes.md <<'EOF'\nmake approve-spec KEY=IDP-14\necho ok > specs/IDP-14/APPROVED\nEOF\n",
      "tee pr.md <<'EOF' >/dev/null\nmake approve-spec KEY=IDP-14\nEOF",
      'git commit -m "IDP-14: guard allows APPROVED and make approve-spec as text"',
      "git commit -m 'IDP-14: mention specs/IDP-14/APPROVED in docs'",
      'git commit -m "IDP-14: run make approve-spec; then commit APPROVED"',
      "git commit -m \"$(cat <<'EOF'\nIDP-14: fix guard\n\nRun make approve-spec KEY=IDP-14 first.\nEOF\n)\"",
      "gh pr create --draft --title 'IDP-14: x' --body \"Run make approve-spec KEY=IDP-14 after review\"",
      "gh pr create --draft --title x --body-file - <<'EOF'\nmake approve-spec KEY=IDP-14\nEOF",
      "grep -rn 'make approve-spec' docs plugins",
      "grep -rn approve-spec docs",
      "rg 'specs/.*/APPROVED' docs",
      "printf '%s\\n' 'make approve-spec KEY=IDP-14' > notes.md",
      "echo 'run make approve-spec when ready'",
      "echo make approve-spec",
      "echo ok # make approve-spec KEY=IDP-14",
      "cat specs/IDP-14/APPROVED",
      "ls specs/*/APPROVED",
      "head -c 200 specs/IDP-14/APPROVED",
      "test -f specs/IDP-14/APPROVED && echo approved",
      "git status --short specs/IDP-14/APPROVED",
      "git diff -- specs/IDP-14/APPROVED",
      "git log --oneline -- specs/IDP-14/APPROVED",
  ]
  ```
- `test_approval_check_fails_closed_when_unsure` (tagged `IDP-14:AC-1` and `IDP-14:AC-2`, spec Q3), parametrized
  over `UNSURE_MENTIONS`. Assert returncode 2:
  ```python
  UNSURE_MENTIONS = [
      "echo 'unterminated make approve-spec KEY=IDP-14",
      'echo "unterminated > specs/IDP-14/APPROVED',
      "cat > pr.md <<'EOF'\nmake approve-spec KEY=IDP-14\n",
      "cat > pr.md <<EOF\nRun `make approve-spec KEY=IDP-14` first.\nEOF",
      'echo "`date`: make approve-spec KEY=IDP-14"',
      "echo ${X:-make approve-spec}",
      "echo $(( 1 + 2 )) make approve-spec",
      'x="$(case y in y) make approve-spec;; esac)"',
      "echo " + "$(" * 9 + "make approve-spec" + ")" * 9,
      "uv run pytest -k 'make approve-spec'",
      "sed 's/x/make approve-spec/e' notes.md",
      "python3 - <<'EOF'\nprint('make approve-spec')\nEOF",
  ]
  ```
- `test_large_command_is_checked_within_a_second` (AC-3, NFR):
  - load the hook in-process with `importlib.util.spec_from_file_location("guard_bash", SCRIPTS / "guard_bash.py")`
    (the `__main__` guard keeps `main()` from running) and time `guard.check(command)` with `time.perf_counter()`;
  - parametrized `("command", "blocked")`, with a module-level `LARGE_BODY`: the line
    ``Run `make approve-spec KEY=IDP-14`; it writes specs/IDP-14/APPROVED.`` plus a newline, repeated 2900 times
    (about 200 KB);
  - cases:
    - `(f"cat > pr.md <<'EOF'\n{LARGE_BODY}EOF\n", False)`;
    - `("echo " + "make approve-spec " * 11_000, False)`;
    - `("ls " + "make " * 40_000, False)`;
    - `("echo '" + "x" * 200_000, False)`;
    - `("echo " + "$(" * 2_000 + "make approve-spec" + ")" * 2_000, True)`;
    - `("cat" + " <<E" * 2_000 + "\n" + "body\nE\n" * 2_000, False)`;
  - assert `(why is not None) == blocked` and `elapsed < 1.0`. Subprocess start-up is not timed (flaky); the
    `hooks.json` 10 s timeout is the hard cap.
- `test_large_heredoc_is_allowed_by_the_hook` (AC-3): `run_hook` with the 200 KB heredoc case, returncode 0 (end to
  end through `main()` and JSON).
- AC-4: add `@pytest.mark.ac("IDP-14:AC-4")` above the existing `@pytest.mark.ac("IDP-10:AC-3")` on
  `test_dangerous_commands_are_blocked` and `test_normal_commands_are_allowed`. Do not change the lists or the bodies.
- `tests/plugin/test_structure.py::test_pr_generate_uses_environment_co_author_trailer` (AC-5, T2):
  ```python
  @pytest.mark.ac("IDP-14:AC-5")
  def test_pr_generate_uses_environment_co_author_trailer():
      text = " ".join((PLUGIN / "skills" / "pr-generate" / "SKILL.md").read_text().split())
      assert "noreply@anthropic.com" not in text
      assert "Co-Authored-By: Claude" not in text
      assert "`Co-Authored-By` trailer supplied by the environment" in text
      assert "never hard-code or invent one" in text
  ```

## AC-5: `pr-generate` SKILL.md step 1 (T2)
Replace lines 8-9 with:
```
1. Make sure the work is committed in logical commits, titled `<KEY>: <imperative summary>`. End each commit message
   with the `Co-Authored-By` trailer supplied by the environment (the harness or its system instructions give the one
   for the model you are running as). Copy it exactly; never hard-code or invent one. If the environment supplies
   none, add none.
```
Steps 2-5 and the front matter are unchanged (`test_every_skill_has_name_and_description` stays green).

## Changes
| File | Change | Who |
|------|--------|-----|
| plugins/idp-agentic/hooks/scripts/guard_bash.py | The two approval rules are replaced by the lexer plus `approval_violation`; `check()` calls it after `RULES`; docstring updated. (AC-1, AC-2, AC-3, AC-4, NFR) | Human (H1) |
| tests/plugin/test_hooks.py | `bash()` helper; case lists; the five new tests; `IDP-14:AC-4` marks on the two existing tests. (AC-1..AC-4) | Agent (T1) |
| plugins/idp-agentic/skills/pr-generate/SKILL.md | Step 1 trailer text. (AC-5) | Agent (T2) |
| tests/plugin/test_structure.py | `test_pr_generate_uses_environment_co_author_trailer`. (AC-5) | Agent (T2) |
| CHANGELOG.md | New `### Fixed` under `[Unreleased]`: `- IDP-14: the Bash guard blocks running spec approval (also via wrappers, subshells, $( ), quoted or escaped command words) and writing an APPROVED marker (redirects, tee, cp/mv/install/ln/touch/dd/truncate/rsync, sed -i, git add/checkout/restore), but no longer blocks heredocs or quoted text that only mention them, or reading the marker; when unsure it falls back to the old mention check. The pr-generate skill uses the Co-Authored-By trailer supplied by the environment. Takes effect in agent sessions after the plugin is updated.` | Agent (T3) |
| (optional, Q5) plugins/idp-agentic/.claude-plugin/plugin.json, .claude-plugin/marketplace.json | Version 0.1.1. | Human (H1 step 4) |

Unchanged: `hooks.json`, `protect_paths.py`, `definition_of_done.py`, `format_on_edit.sh`, `.claude/settings.json`,
every other `RULES` entry, `approve_spec.py`.

## Interfaces and data
- Hook contract unchanged: JSON on stdin, exit 0 or 2, the same stderr format and the same two reason strings.
- Behaviour:
  - fewer blocks: mention-only heredocs and quoted text given to printers; unquoted mentions given to printers;
    reading the marker;
  - more blocks: bypass forms the old regexes missed (`make -s approve-spec`, `make 'approve-spec'`,
    `cd specs/X && touch APPROVED`, `cat <(make approve-spec)`, ...) and the broader fallback (`approve-spec`
    anywhere when unsure, spec A5).
- New module-level names: `approval_violation`, `APPROVE_WHY`, `MARKER_WHY`, `MENTION`. Tests use only `check()`.

## Telemetry
None (local hook). The operator signal is the unchanged `BLOCKED by idp-agentic: <why>` message.

## Risks, rollout and rollback
- Risk: a new bypass, where the lexer treats code as data. Mitigation:
  - data is honoured only for known printers;
  - everything uncertain, and any shell or interpreter word, falls back to the old mention check;
  - unquoted heredoc bodies with expansions are never data;
  - `$( )` inside double quotes stays code.
  Detection: the AC-1/AC-2 bypass lists and the security review. Residual risk is indirection (variables, aliases,
  functions, scripts), unchanged from today. Backstops: the `CLAUDECODE` refusal, the deny-list, `protect_paths.py`
  and human review.
- Risk: a false positive remains for mentions given to non-printers or inside unsure constructs (for example markdown
  backticks in an unquoted heredoc). This is acceptable and documented; agents should quote heredoc delimiters.
- Risk: other rules still block quoted mentions (spec Q1). Detection: the next dry run. Mitigation: a follow-up
  ticket.
- Risk: performance. The lexer and regexes are linear and the timing test covers the pathological shapes. The
  pre-existing protected-path rule backtracks per `>`. That rule is unchanged; a 200 KB body with very many `>`
  characters is a pre-existing cost.
- Risk: a paste error in H1. Detection: the H1 ruff, 3.9 and smoke checks, `make validate-plugin`, then T1's tests.
- Risk: sessions keep running the old installed copy (spec Q4, Q5). Mitigation: the CHANGELOG note; update the plugin
  after merge.
- Rollout: H1 commit on the feature branch, PR, merge, plugin update.
- Rollback: revert the PR (or only the H1 commit, by a human). No data or config to undo.

## Amendment 1 (2026-10-20, after review loop 1): relax-only (H2, T4)
H1's verdict is superseded (spec "Amendment 1"). The design above is kept as history; the sections below replace it
wherever they differ.

### Approach
1. `check()` runs the unchanged `RULES` first (AC-4).
2. `approval_violation()` collects every raw mention span with
   `MENTION = approve-spec|(?<![\w.-])approved(?![\w.-])` (case-insensitive). With no mention it returns `None`
   without lexing.
3. `_Lexer.scan()` splits the command the way bash does into simple commands at every `$( )` level. Each command
   has words, and each word records:
   - its literal text (for names and options);
   - `plain` (only unquoted, unescaped characters);
   - `data`: the interior spans of `'...'`, `$'...'`, and `"..."` without `$(`;
   - `inner`: data spans accepted inside its `$( )`.

   Each command also records the spans of its heredoc bodies that are literal, or expanding without `$(`, backtick
   or `${`. Redirect targets are read but not kept. Comments are skipped (never relaxed). Anything the lexer cannot
   follow raises `_Unsure`.
4. Relaxed spans:
   - DATA (`_accepted`): only if every simple command is `_inert`. Then each printer contributes the data and inner
     spans of its DATA-position words (`_data_positions`), plus its heredoc bodies when stdin is data.
   - READ (`_reads`): plain arguments of read commands, used for marker mentions only.
5. A mention that is not inside a relaxed span (checked with `bisect`) blocks. The reason is the approval reason if
   any such mention is `approve-spec`, otherwise the marker reason. `_Unsure` means no relaxed spans at all.
6. `main()` turns a non-string `command` into its JSON text (review c06).

Compared with H1, these are gone: `WRAPPERS`/heads scanning, the writer lists, the interpreter regex, the `UNSURE`
verdict, the `-m` marker exemption, the masking output, the escape rewriting and the `.` heuristic.

### H2: replacement for `plugins/idp-agentic/hooks/scripts/guard_bash.py`
Complete file. It is stdlib-only (`bisect`, `json`, `re`, `sys`) and Python 3.9-compatible (no `match`, no `X | Y`,
no walrus, no `zip(strict=)`). Constants are set literals, lines are at most 120 characters, and it is written to be
ruff-format-stable. `RULES`, `check()`'s order and the stderr format are unchanged.

```python
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

TESTS = {"test", "[", "[["}
READERS = {"cat", "ls", "head", "tail", "wc", "grep", "egrep", "fgrep", "rg"} | TESTS
PRINTERS = READERS - {"ls"} | {"echo", "printf", "jq", "true", ":"}
INERT = PRINTERS | READERS | {"tee", "cd", "mkdir", "pwd", "false"}
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
```

### H2 steps (human, in your own terminal, after re-approval of the amended spec)
1. On `feature/IDP-14-guard-bash-false-positive`, replace the whole content of
   `plugins/idp-agentic/hooks/scripts/guard_bash.py` with the block above. Edit in place to keep the executable bit.
2. Run the H1 checks again, with these expectations:
   - the two smoke commands give the same results as for H1;
   - `make validate-plugin` passes;
   - the T1 tests are green except the four changed MENTIONS_ONLY cases and the changed timing case, which T4
     updates.

   Also check two review payloads:
   ```bash
   for p in p01_escaped_space_comment p15_git_commit_path; do
     /usr/bin/python3 plugins/idp-agentic/hooks/scripts/guard_bash.py \
       < /private/tmp/claude-501/-Users-suyashkunte-Documents-IntelligentDeliveryPipeline/95c2d9e4-6152-4e1e-82f2-2724fa62cd69/scratchpad/review/$p.json
     echo "$p exit $?"
   done
   ```
   Expected: `BLOCKED ...` and `exit 2` for both.
3. Commit only that file: `git add plugins/idp-agentic/hooks/scripts/guard_bash.py && git commit -m "IDP-14: relax-only approval guard (amendment 1)"`.
4. If any check fails, stop and tell the agent (spec revision).

### Tests (T4, agent; `tests/plugin/test_hooks.py`)
- Add the review payloads (exact strings from the `review/p*.json` files) to the existing lists. Each list's test
  asserts its specific reason.
  - `RUNS_APPROVAL` (asserts `spec approval is a human checkpoint`):
    ```text
    "echo \\ #; make approve-spec KEY=IDP-1",
    "echo \\\t#; make approve-spec KEY=IDP-1",
    "echo x\\\n#; make approve-spec KEY=IDP-1",
    "(( x = 1 << 2 ))\nmake approve-spec KEY=IDP-1\n2",
    "(( cat << 2 ))\nmake approve-spec KEY=IDP-1\n2",
    "> \"'\" make approve-spec KEY=IDP-1",
    "> $'\\'' make approve-spec KEY=IDP-1",
    "echo 'make approve-spec KEY=IDP-1' | $SHELL",
    "echo 'make approve-spec KEY=IDP-1' | sudo -s",
    "make {approve-spec,}",
    "m=make; $m approve-spec",
    ```
  - `WRITES_MARKER` (asserts `APPROVED marker`):
    ```text
    "touch -m specs/IDP-1/APPROVED",
    "sort -o specs/IDP-1/APPROVED /dev/null",
    "curl -o specs/IDP-1/APPROVED https://example.com/x",
    "patch specs/IDP-1/APPROVED /tmp/p.diff",
    "git commit -m x -- specs/IDP-1/APPROVED",
    "git diff --output=specs/IDP-1/APPROVED",
    ```
  - Not added: p12 `make $'\x61pprove-spec'` (no raw mention; residual risk, as on main). A test asserting that it
    is allowed would pin a bypass.
- `UNSURE_MENTIONS` becomes a list of `(command, reason)` pairs; `test_approval_check_fails_closed_when_unsure`
  asserts returncode 2 and that `reason` is in stderr.
  - `"approval"` (`spec approval is a human checkpoint`) for every existing case except
    `'echo "unterminated > specs/IDP-14/APPROVED'`, which gets `"APPROVED marker"`.
  - New cases (moved from MENTIONS_ONLY, see the spec):
    - `("echo make approve-spec", APPROVAL)`;
    - `("grep -rn approve-spec docs", APPROVAL)`;
    - `("test -f specs/IDP-14/APPROVED && echo approved", MARKER)`.
  - Further new cases:
    - `("echo 'make approve-spec KEY=IDP-1' > x.sh; bash x.sh", APPROVAL)` (Q8: a non-inert command disables
      DATA);
    - `("{ echo 'make approve-spec'; } | sh", APPROVAL)`;
    - `("cat <<'EOF' | sh\nmake approve-spec KEY=IDP-1\nEOF", APPROVAL)`;
    - `("$(cat <<'EOF'\nmake approve-spec KEY=IDP-1\nEOF\n)", APPROVAL)` (a substitution at command position is
      not a DATA position);
    - `("git commit -m x -- 'specs/IDP-1/APPROVED'", MARKER)` (a quoted pathspec is not data);
    - `("tee 'specs/IDP-1/APPROVED' <<'EOF'\nx\nEOF", MARKER)` (tee file arguments are never data);
    - `("rg --pre 'make approve-spec' x", APPROVAL)` (an output or run option disables DATA).
- `MENTIONS_ONLY` changes:
  - `"grep -rn approve-spec docs"` becomes `"grep -rn 'approve-spec' docs"`;
  - `"echo make approve-spec"` becomes `"echo 'make approve-spec'"`;
  - `"echo ok # make approve-spec KEY=IDP-14"` is removed (it moves to the comment test);
  - `"test -f specs/IDP-14/APPROVED && echo approved"` becomes `"test -f specs/IDP-14/APPROVED && echo present"`.

  Add `"echo 'approved'"` and `"cat specs/IDP-14/APPROVED | head -c 10"`. All other cases stay unchanged.
- `test_mentions_in_comments_block` (tagged `IDP-14:AC-1` and `IDP-14:AC-2`), parametrized `(command, reason)`.
  Every case must block with its reason:
  - `("echo ok # make approve-spec KEY=IDP-14", APPROVAL)`;
  - `("# approve-spec", APPROVAL)`;
  - `("cat README.md # specs/IDP-14/APPROVED", MARKER)`;
  - `("cat > pr.md <<'EOF'\nok\nEOF\n# make approve-spec", APPROVAL)`;
  - `("echo 'x' # it's approve-spec time", APPROVAL)`;
  - `("git commit -m 'x' # APPROVED", MARKER)`.
- `test_hook_parses_as_python_39` (tagged `IDP-14:AC-3`, NFR):
  `ast.parse((SCRIPTS / "guard_bash.py").read_text(), feature_version=(3, 9))` raises nothing, and no
  `ast.Match` node is present.
- `test_large_command_is_checked_within_a_second`: the cases become (same ids where unchanged):
  - `(LARGE_HEREDOC, False)`;
  - `("echo '" + "make approve-spec " * 11_000 + "'", False)`, id `200kb-quoted-mentions`;
  - `("echo " + "'approve-spec' " * 20_000, False)`, id `20k-quoted-words`;
  - `("echo " + "make approve-spec " * 11_000, True)`, id `200kb-unquoted-mentions`;
  - `("ls " + "make " * 40_000, False)`;
  - `("echo 'approve-spec " + "x" * 200_000, True)`, id `200kb-unterminated-quote`;
  - `("echo " + "$(" * 2_000 + "make approve-spec" + ")" * 2_000, True)`;
  - `("cat" + " <<E" * 2_000 + "\n" + "approve-spec\nE\n" * 2_000, False)`, id `2k-heredocs-with-mentions`.
- RUNS_APPROVAL, WRITES_MARKER, the AC-4 lists and the remaining MENTIONS_ONLY and UNSURE_MENTIONS cases must pass
  unchanged with H2. If one does not, stop and report (spec revision), rather than editing the case.

### Changes (amendment 1)
| File | Change | Who |
|------|--------|-----|
| plugins/idp-agentic/hooks/scripts/guard_bash.py | Replaced by the H2 file: relax-only span accounting; non-string command coerced. (AC-1, AC-2, AC-3, AC-4, NFR) | Human (H2) |
| tests/plugin/test_hooks.py | Review payloads added; UNSURE_MENTIONS with reasons; four MENTIONS_ONLY changes plus two new allowed cases; comment test; Python 3.9 parse test; timing cases updated. (AC-1, AC-2, AC-3) | Agent (T4) |
| CHANGELOG.md | T3 entry, worded for the relax-only design: `- IDP-14: the Bash guard still blocks any mention of approve-spec or an APPROVED file, except quoted or heredoc text given to commands that only print or record it (cat, echo, printf, grep, git commit -m, gh pr create --body, ...) and plain marker paths given to read-only commands (cat, ls, head, test -f, git status/diff/log/show); comments, unquoted mentions and anything the lexer cannot follow still block. The pr-generate skill uses the Co-Authored-By trailer supplied by the environment. Takes effect in agent sessions after the plugin is updated.` | Agent (T3) |

### Risks (amendment 1)
- Risk: the lexer misreads where bash's quotes or heredocs end, and so relaxes text that bash runs. Mitigations:
  - relaxation needs a printer head, an all-inert command and a matching quote or heredoc;
  - every known divergence raises `_Unsure`: arithmetic, complex `${}`, backticks, process substitution, `case`,
    heredoc edge cases;
  - comments follow bash's word-start rule.

  Detection: the review payloads, T4's lists and review loop 2.
- Risk: more false positives than H1, for unquoted mentions, mentions in comments, and mention-only commands combined
  with other commands (Q7, Q8). All of these block on main too, so nothing is worse than before IDP-14.
- Risk: residual indirection with no raw mention (p12 and similar). This is unchanged from main; the backstops are
  as before.

## Amendment 2 (2026-10-20, after review loop 2): no DATA for test/[/[[ or printf -v (H3, T5)
H2 is committed (d4353ba) and equals the H2 block above. H3 changes only these points (spec "Amendment 2"):
1. `PRINTERS = (READERS - {"ls"} - TESTS) | {...}`: `test`, `[` and `[[` are no longer DATA printers.
2. `INERT = PRINTERS | (READERS - TESTS) | {...}`: they are no longer inert either (Q8). A command containing them
   gets no DATA relaxation anywhere.
3. `_data_positions`: `printf` with any word starting with `-v` returns `([], False)`.
4. One explanatory comment above the constants.

Unchanged: `TESTS` stays in `READERS`, so `_reads` keeps relaxing plain marker paths after `-f`/`-e`/`-s`. The
lexer, `_reads`, `_inert`'s logic, `_accepted`, `approval_violation`, `RULES` and `main` are unchanged, and `]`/`]]`
need no handling (they are ordinary words).

### H3: replacement for `plugins/idp-agentic/hooks/scripts/guard_bash.py`
Complete file. Stdlib-only and Python 3.9-compatible as before. Constants are set literals, lines are at most 120
characters, and it is ruff-format-stable.

```python
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
```

### H3 steps (human, in your own terminal, after re-approval of the amended spec)
1. On `feature/IDP-14-guard-bash-false-positive`, replace the whole content of
   `plugins/idp-agentic/hooks/scripts/guard_bash.py` with the H3 block (edit in place to keep the executable bit).
   Optional: `git diff` should show only the comment, the `PRINTERS` and `INERT` lines, and the two `printf` lines in
   `_data_positions`.
2. Check:
   ```bash
   uv run ruff format --check plugins/idp-agentic/hooks/scripts/guard_bash.py
   uv run ruff check plugins/idp-agentic/hooks/scripts/guard_bash.py
   /usr/bin/python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read(), feature_version=(3, 9))' \
     plugins/idp-agentic/hooks/scripts/guard_bash.py && echo "3.9 syntax ok"
   /usr/bin/python3 plugins/idp-agentic/hooks/scripts/guard_bash.py <<'JSON'; echo "exit $?"
   {"tool_input": {"command": "[[ 'a[$(make approve-spec)]' -eq 0 ]]"}}
   JSON
   /usr/bin/python3 plugins/idp-agentic/hooks/scripts/guard_bash.py <<'JSON'; echo "exit $?"
   {"tool_input": {"command": "test -f specs/IDP-14/APPROVED && echo present"}}
   JSON
   make validate-plugin
   ```
   Expected:
   - ruff: clean;
   - the first smoke command blocks (`spec approval is a human checkpoint (A)`, `exit 2`); the second gives
     `exit 0`;
   - `make validate-plugin`: green. All committed T4 cases keep their verdicts; spec "Amendment 2, Verdict changes"
     lists none.
3. Commit only that file:
   `git add plugins/idp-agentic/hooks/scripts/guard_bash.py && git commit -m "IDP-14: no data relaxation for test, [, [[ and printf -v (amendment 2)"`.
4. If any check fails, stop and tell the agent (spec revision).

### Tests (T5, agent; `tests/plugin/test_hooks.py`)
- Append to `RUNS_APPROVAL` (each asserts `spec approval is a human checkpoint`):
  ```text
  "[[ 'a[$(make approve-spec)]' -eq 0 ]]",
  "test -v 'a[$(make approve-spec)]'",
  "[ -v 'a[$(make approve-spec)]' ]",
  "[[ -v 'a[$(make approve-spec)]' ]]",
  "printf -v 'a[$(make approve-spec)]' x",
  "printf -v'a[$(make approve-spec)]' x",
  ```
  The last one is the glued `-v<name>` form.
- Append to `UNSURE_MENTIONS`. These block although bash 5.2 does not run them; they are fail-closed by design:
  ```text
  ("test 'a[$(make approve-spec)]' -eq 0", APPROVAL),
  ("[ 'a[$(make approve-spec)]' -eq 0 ]", APPROVAL),
  ("[ \"$x\" = 'approve-spec' ]", APPROVAL),
  ("[[ -f specs/IDP-14/APPROVED ]] && echo 'approve-spec'", APPROVAL),
  ("test -f specs/IDP-14/APPROVED && echo 'make approve-spec'", APPROVAL),
  ```
  The last two hold because `test`/`[[` are no longer inert. Use the module's existing `APPROVAL` and `MARKER`
  constant names.
- Append to `MENTIONS_ONLY` (READ still relaxes the marker path for the test forms):
  ```text
  "[ -f specs/IDP-14/APPROVED ] && echo present",
  "[[ -e specs/IDP-14/APPROVED ]]",
  "test -s specs/IDP-14/APPROVED",
  "grep -v 'approve-spec' notes.md",
  "printf '%s\\n' 'approve-spec'",
  ```
  `grep -v` shows that the `-v` rule applies to `printf` only.
- No other case changes. If a committed case changes verdict with H3, stop and report.
- Red-first evidence for the PR: the six new `RUNS_APPROVAL` cases and the last two new `UNSURE_MENTIONS` cases are
  allowed by the H2 hook (`git show d4353ba:plugins/idp-agentic/hooks/scripts/guard_bash.py` into the scratchpad).
- Run `uv run pytest tests/plugin --no-cov`, `uv run ruff check tests/plugin`,
  `uv run ruff format --check tests/plugin` and `uv run idp test-quality-lint tests/plugin/test_hooks.py`.

### Changes (amendment 2)
| File | Change | Who |
|------|--------|-----|
| plugins/idp-agentic/hooks/scripts/guard_bash.py | H3: `test`/`[`/`[[` out of `PRINTERS` and `INERT`; `printf -v` gives no DATA; one comment. (AC-1, AC-3) | Human (H3) |
| tests/plugin/test_hooks.py | T5 cases above. (AC-1, AC-3) | Agent (T5) |
| CHANGELOG.md | T3 entry as in "Changes (amendment 1)", with `test, [, [[` removed from the printer list if named. | Agent (T3) |
