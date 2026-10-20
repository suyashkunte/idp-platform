---
ticket: IDP-14
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: medium
mode: guided
---

# IDP-14: guard_bash false positive: blocks commands that only mention approve-spec or APPROVED as text

## Context
The IDP-13 dry run found the problem. The Bash guard searches the whole raw command for `approve-spec` and
`specs/*/APPROVED`. So it blocked the PR composer from saving a PR body (heredoc) that only *mentions* the approval
command, and it also blocked a notes update. The agent switched to Write/Edit, which was legitimate here. But false
positives teach agents to route around guards. Separately, the `pr-generate` skill prescribes a fixed
`Co-Authored-By: Claude <noreply@anthropic.com>` trailer, while the environment supplies a model-specific one; the
skill should defer to the environment. Labels: risk:medium, spec:guided, repo:idp-platform.
Dependency: `plugins/idp-agentic/hooks/**` is a protected path, so the hook change is a human task (H1).

Facts checked in the repository (2026-10-20, branch `feature/IDP-14-guard-bash-false-positive`, at b4db326):
- `plugins/idp-agentic/hooks/scripts/guard_bash.py`: `RULES` is a list of `(regex, why)`. `check()` runs
  `re.search` (IGNORECASE) for each rule over the raw command and returns the first `why`. `main()` exits 2 with
  `BLOCKED by idp-agentic: <why>.` on stderr. Two rules cause this ticket:
  - `\b(make|uv\s+run\s+make)\s+approve-spec\b|\bidp\s+approve-spec\b`;
  - `specs/[^/\s]+/APPROVED`.
- Neither rule distinguishes running from mentioning. Both also miss real bypasses, for example
  `make -s approve-spec`, `make KEY=X approve-spec`, `make 'approve-spec'`, `cd specs/X && touch APPROVED`.
- The last rule (protected paths: `>`/`tee`/`sed -i`/`cp`/`mv`/`rm` ... `.github/` etc.) has the same false-positive
  pattern. So do the raw `git push ... main`, `gh pr merge` and other rules when a PR body quotes them. These rules are
  not in the ACs (Q1).
- `plugins/idp-agentic/hooks/hooks.json` runs the hook as `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/guard_bash.py"`
  with a 10 s timeout. `CLAUDE_PLUGIN_ROOT` is the installed plugin from the `idp-platform` GitHub marketplace
  (`.claude/settings.json`), not this checkout (Q4). On macOS, `/usr/bin/python3` is 3.9, hence the 3.9 constraint.
- Other layers: `.claude/settings.json` denies `Bash(make approve-spec:*)` and `Bash(uv run idp approve-spec:*)`
  (prefix rules) and `Edit(specs/*/APPROVED)`. `protect_paths.py` blocks Edit/Write of `specs/*/APPROVED`.
  `idp approve-spec` refuses when `CLAUDECODE` or `CLAUDE_CODE_ENTRYPOINT` is set (`approve_spec.py`). guard_bash is
  defence in depth.
- `tests/plugin/test_hooks.py`: `test_dangerous_commands_are_blocked` (16 commands) and
  `test_normal_commands_are_allowed` (10 commands), both tagged `IDP-10:AC-3`, both run via `run_hook`
  (`tests/plugin/conftest.py`: `subprocess.run([sys.executable, SCRIPTS / script], ...)` from the repo checkout).
- `idp spec-trace` (`spec_trace.py`) needs at least one test tagged `@pytest.mark.ac("IDP-14:AC-n")` per AC. It
  reads every string argument of every `ac` mark, and marks can be stacked (precedent:
  `tests/plugin/test_structure.py::test_marketplace_lists_plugin_with_matching_manifest`).
- `plugins/idp-agentic/skills/pr-generate/SKILL.md` lines 8-9 hold the hard-coded trailer. No other file in the
  repository contains `Co-Authored-By` or `noreply@anthropic.com`.
- Tooling: ruff (`line-length = 120`, hooks ignore `UP`, `S603`, `S607`). mypy, coverage and bandit cover `packages`
  only. `make validate-plugin` runs `tests/plugin`.

## Amendment 1 (2026-10-20, after review loop 1)
State: the spec was approved (cb63815), H1 is committed (d1c83f5), the T1 tests are committed (1b11b14) and the T2
SKILL.md change is done (57c8532).

Review loop 1 found 14 confirmed regressions. Each is blocked on main, allowed by the H1 hook, and really runs the
approval or writes the marker in bash or zsh. Payloads are in the review scratchpad (`review/p*.json`). The H1 design
decided by itself that some commands were safe ("not a runner", "not a writer"), so every gap in its model became a
bypass.

**Decision (human): relax-only.** The base is again the pre-IDP-14 idea that a mention blocks. The lexer may only
*relax* specific mentions; it never decides on its own that a command is safe.

**Invariant:** every raw mention must lie inside a relaxed span that the lexer found, or the command blocks.
- **Raw mention:** a case-insensitive match, over the raw command, of `approve-spec` or of a word whose last path
  component is `APPROVED`. The regex is `approve-spec|(?<![\w.-])approved(?![\w.-])`, so
  `cd specs/IDP-1 && touch APPROVED` still blocks. Match spans (offsets) are recorded.
- **Relaxed spans** (the only ones):
  - (a) **DATA:** a heredoc body, or the interior of a quoted string, given to a narrow printer command. All of
    these must hold:
    - (i) text the shell expands (double quotes, unquoted-delimiter heredoc bodies) contains no `$(`, backtick or
      `${`; otherwise it is code. Single quotes, `$'...'` and quoted-delimiter heredoc bodies are literal, so
      backticks in them are data (ASSUMPTION A9);
    - (ii) the printer has no output-writing or command-running option: a word matching
      `-o.*|--output.*|of=.*|-w|--pre.*|-O.*|--open-files-in-pager.*`. `sort` is not a printer;
    - (iii) its output cannot reach code. Every simple command in the whole input must be "inert" (Q8; amendment 2:
      not `test`, `[` or `[[`): a printer, a reader, `tee`, `cd`, `mkdir`, `pwd`, `false`, `git log|show|status|diff|grep|commit|tag|notes` or
      `gh pr|issue|release`. Its head must be a plain unquoted word, with no `VAR=x` prefix. So `| sh`, `| $SHELL`,
      `| sudo -s`, `| xargs`, `; bash x.sh`, `$m ...`, compound commands (`if`, `for`, `{ }`) and assignments disable
      every DATA relaxation;
    - (iv) the data is not a redirect target. Text inside `$( )` counts only if that `$( )` is itself in a DATA
      position of an outer printer, as in `git commit -m "$(cat <<'EOF' ... EOF\n)"`.

    Printers and their DATA positions:
    - `cat`, `echo`, `printf`, `grep`, `egrep`, `fgrep`, `rg`, `head`, `tail`, `wc`, `jq`, `test`, `[`, `[[`,
      `true`, `:`: every argument, and heredoc stdin. (Amendment 2: `test`, `[` and `[[` are removed, and `printf`
      with a `-v` word gives no DATA.)
    - `tee`: heredoc stdin only (its file arguments are never relaxed);
    - `git log|show|status|diff|grep`: every argument after the subcommand;
    - `git commit|tag|notes`: only the value of `-m`/`--message` (`--message=`). A quoted pathspec is never data;
    - `gh pr|issue|release create|edit|comment`: the values of `--body`/`--title`/`-b`/`-t`, and heredoc stdin when
      `--body-file -` or `-F -` is given.
  - (b) **READ:** a plain unquoted word, not starting with `-` and not a redirect target, that is an argument of a
    read command. Read commands are `cat`, `ls`, `head`, `tail`, `wc`, `grep`, `egrep`, `fgrep`, `rg`,
    `test`/`[`/`[[` (only right after `-f`, `-e` or `-s`) and `git status|diff|log|show`, each without an option
    from (ii). READ relaxes marker mentions only, never `approve-spec` (ASSUMPTION A11). It does not depend on (iii),
    because reading the marker cannot run anything.
- **Never relaxed:**
  - comments;
  - words of any other command (`make`, `touch`, `curl`, `patch`, `sort`, a `git commit` pathspec, `$m`, ...);
  - redirect targets;
  - assignment values;
  - anything when the lexer is unsure. Unsure means: unterminated quote or heredoc, `((`, `$((`, complex `${...}`,
    a backtick outside literal text, `<(`/`>(`, more than 8 nested `$( )`, a `case` command, a heredoc delimiter
    containing `$`, a heredoc pending across `$( )` levels, or an unquoted-delimiter heredoc body containing a
    backslash. Unsure means nothing is relaxed at all, which is the pre-IDP-14 behaviour.
- **Writers:** a writer list is no longer needed. A mention in any command that is not listed above simply blocks.
- **Reason:** `spec approval is a human checkpoint (A)` if any unrelaxed mention is `approve-spec`, otherwise the
  APPROVED-marker reason.
- **Unchanged:** the other `RULES` (AC-4), which still run first on the raw command. Also unchanged: stdlib-only
  Python 3.9, under 1 s, ruff-clean.
- **Non-string command:** a non-string `command` (review c06: a JSON list crashed the hook, which exits 1 and
  therefore does not block) is now turned into its JSON text first, so a mention in it blocks (ASSUMPTION A10).

Review payloads, all handled by the invariant. Placement in the tests is in plan.md.
- Must block (the 14 regressions):
  - p01 `echo \ #; make approve-spec KEY=IDP-1`, p02 (the same with an escaped tab), p03 `echo x\` + newline +
    `#; make approve-spec ...`: the lexer tracks word boundaries, so `#` after an escape or a line continuation is
    not a comment. In any case a mention in a comment is never relaxed;
  - p04 `(( x = 1 << 2 ))` + newline + `make approve-spec ...` and p04b `(( cat << 2 ))` + newline +
    `make approve-spec ...`: `((` makes the lexer unsure;
  - p05 `> "'" make approve-spec ...` and p06 `> $'\'' make approve-spec ...`: the mention is an argument of `make`;
  - p07 `touch -m specs/IDP-1/APPROVED`, p08 `sort -o specs/IDP-1/APPROVED /dev/null`,
    p13 `curl -o specs/IDP-1/APPROVED https://example.com/x`, p14 `patch specs/IDP-1/APPROVED /tmp/p.diff`: not read
    commands;
  - p15 `git commit -m x -- specs/IDP-1/APPROVED`: a pathspec is not READ, and `commit` is not a read subcommand;
  - p16 `git diff --output=specs/IDP-1/APPROVED`: an output option disables READ;
  - p09 `echo 'make approve-spec KEY=IDP-1' | $SHELL` and p10 `... | sudo -s`: a non-inert command disables DATA.
- Must now block too (allowed on main; a raw mention in a non-printer):
  - p11 `make {approve-spec,}`;
  - p17 `m=make; $m approve-spec`.
- Residual risk, as on main: p12 `make $'\x61pprove-spec'` has no raw mention, so nothing blocks it. The backstops
  are the `CLAUDECODE` refusal in `idp approve-spec` and the deny-list.

### Amendment log
- Amendment 1 (2026-10-20, after review loop 1): relax-only design and invariant. AC-1..AC-5 text unchanged; the
  AC-1..AC-3 sub-bullets get an "Amendment 1" note. Q2 superseded. A3, A4 and A5 superseded. The `-m` sub-rule of
  AC-2 superseded. A9-A11 and Q7-Q8 added. NFR timing cases updated. Four MENTIONS_ONLY cases change (see
  "MENTIONS_ONLY under amendment 1"). H2 and T4 added.

### MENTIONS_ONLY under amendment 1
Every case in `tests/plugin/test_hooks.py::MENTIONS_ONLY` was checked against the new rules. 23 stay allowed as
they are. Four would now block and change as follows (none is silently dropped):
- `grep -rn approve-spec docs`: an unquoted mention, and READ covers only the marker. It becomes
  `grep -rn 'approve-spec' docs` in MENTIONS_ONLY. The original moves to UNSURE_MENTIONS (expected:
  `spec approval is a human checkpoint`).
- `echo make approve-spec`: unquoted. It becomes `echo 'make approve-spec'`; the original moves to UNSURE_MENTIONS
  (approval reason).
- `echo ok # make approve-spec KEY=IDP-14`: comments are never relaxed. It moves to the new comment test (blocks).
- `test -f specs/IDP-14/APPROVED && echo approved`: the marker path is relaxed (READ), but the bare word `approved`
  is itself a marker mention (case-insensitive) given to `echo` unquoted. It becomes
  `test -f specs/IDP-14/APPROVED && echo present`; the original moves to UNSURE_MENTIONS (marker reason).

Q7 asks whether unquoted plain words given to printers should be relaxed too, which would keep the first, second
and fourth cases unchanged.

## Amendment 2 (2026-10-20, after review loop 2)
State: amendment 1 approved (cf33b1e), H2 placed (d4353ba), T4 tests committed (eabb846).

**Finding.** Review loop 2 confirmed 5 regressions. Each is an AC-1 bypass: H2 allows it, main blocks it, and bash
really runs `make` (checked with a fake `make` on bash 3.2 (macOS) and bash 5.2 (Debian)). The cause is that bash
evaluates array subscripts arithmetically, and that arithmetic expands the `$( )` written inside a single-quoted
argument of a builtin that H2 treats as a printer:
1. `[[ 'a[$(make approve-spec)]' -eq 0 ]]` (bash 3.2 and 5.2)
2. `test -v 'a[$(make approve-spec)]'` (bash >= 4.2)
3. `[ -v 'a[$(make approve-spec)]' ]`
4. `[[ -v 'a[$(make approve-spec)]' ]]`
5. `printf -v 'a[$(make approve-spec)]' x`

Not executed on bash 5.2: `test 'a[$(...)]' -eq 0`, `[ ... -eq 0 ]`, `printf '%d' 'a[$(...)]'`, `head -n`, `wc`. The
design still does not rely on per-operator lists for `test`/`[`/`[[`.

**Decision (human; smallest fix).**
- `test`, `[` and `[[` are removed from the DATA printers entirely. Their quoted arguments are never data.
  - Their plain read form (`test -f/-e/-s <marker>`, `[ -f <marker> ]`, `[[ -e <marker> ]]`) stays relaxed through
    READ only. READ relaxes unquoted plain marker words, never `approve-spec` and never quoted text.
  - A plain unquoted word contains no `$`, so it cannot carry a substitution.
- `test`, `[` and `[[` are also removed from the inert set (Q8). So `[[ ... ]] && echo 'approve-spec'` and
  `test -f <marker> && echo 'approve-spec'` block: a non-inert command disables every DATA relaxation.
- `printf` with a `-v` option (`-v name` or `-vname` glued, that is any word starting with `-v`) gives no DATA
  relaxation. The check is specific to `printf`, so `grep -v 'approve-spec'` keeps its relaxation. `printf` without
  `-v` stays a printer (`printf '%s\n' '...' > notes.md`).
- Nothing in the lexer handles `]` or `]]` specially: they are ordinary words. Only `_reads` uses `TESTS` (the
  `-f`/`-e`/`-s` rule), and that stays.

**Verdict changes.**
- None of the committed test cases in `tests/plugin/test_hooks.py` (eabb846) changes verdict:
  - `test -f specs/IDP-14/APPROVED && echo present` stays allowed: the marker path is relaxed by READ, and the other
    words hold no mention;
  - `test -f specs/IDP-14/APPROVED && echo approved` stays blocked (marker reason);
  - no other case uses `test`, `[`, `[[` or `printf -v`.
- New behaviour outside the tests: quoted mentions given to `test`/`[`/`[[` (`[ "$x" = 'approve-spec' ]`), and any
  mention-only DATA in a command that also contains `test`/`[`/`[[` or `printf -v`, now block. This is the same as
  on main.

### Amendment log (continued)
- Amendment 2 (2026-10-20, after review loop 2): `test`/`[`/`[[` removed from the DATA printers and from the inert
  set; `printf -v` disables DATA. AC-1..AC-5 text unchanged; AC-3 gets an "Amendment 2" note. H3 and T5 added. No
  committed test case changes verdict.

## Requirements
- **AC-1** Given a command that _executes_ `make approve-spec`, `uv run idp approve-spec` or `idp approve-spec` (at command start, or after `;`, `&&`, `||`, `|` or `$(`), when guard_bash runs, then it blocks.
  - "Executes" is judged per simple command, after a small lexer has removed heredoc bodies and quoted text (plan.md
    "Design"). A simple command blocks with `spec approval is a human checkpoint (A)` when a word whose base name is
    `make`, `gmake` or `idp` comes before a word `approve-spec` (case-insensitive) in it. The words before it do not
    matter, unless the command is a known printer (see AC-3). That covers:
    - command positions: start of the command, after `;`, `&`, `&&`, `|`, `||`, newline, `(`, `{`, `!`, `$(`, `<(`,
      `>(`, and after the keywords `if`, `then`, `else`, `elif`, `do`, `while`, `until`, `coproc`;
    - prefixes that still execute: `VAR=x` assignments, redirections such as `> out make approve-spec`, and wrappers
      (`env`, `command`, `nohup`, `time`, `sudo`, `exec`, `timeout`, `uv run`, `cd x && ...`, and any other word
      before the runner);
    - spellings: a path (`.venv/bin/idp`), zsh's `=make`, upper case (`MAKE`, for case-insensitive file systems),
      quoted or escaped plain words (`make 'approve-spec'`, `m\ake approve-spec`), and options or variables before
      the target (`make -s approve-spec`, `make KEY=X approve-spec`).
  - Text that may run as code falls back to the mention check (any `approve-spec` or `specs/<x>/APPROVED` in the raw
    command blocks, as before IDP-14):
    - shells and interpreters at any word position of a non-printer command: `sh`, `bash`, `zsh`, `dash`, `ksh`,
      `fish`, `eval`, `source`, `.`, `xargs`, `python*`, `perl`, `ruby`, `node`, `awk` and others (full list in
      plan.md);
    - `make` reading makefile text (`-f`, `-e`/`-E`, `--eval`, `--file`);
    - `git` running text (`-c`, `-x`, `--exec`, `bisect`, `foreach`, `filter-branch`).
    So `sh -c '...'`, `bash -c "..."`, `zsh -c`, `eval '...'`, `echo '...' | sh`, `bash <<'EOF'` and
    `xargs idp approve-spec` block when they mention approval. Inside those, nothing is treated as mere text (Q2).
  - Verified by `test_running_spec_approval_is_blocked` (each form above, also nested `$( )` and wrappers) and
    `test_approval_check_fails_closed_when_unsure`.
  - Amendment 1: the bullets above describe the H1 design and are superseded. AC-1 now holds because every
    `approve-spec` mention blocks unless it lies in a DATA span (see "Amendment 1"). A runner never gets a relaxed
    position. All forms listed above still block, and so do p01-p06, p09-p11 and p17. Also verified by
    `test_mentions_in_comments_block`.
- **AC-2** Given a command that writes, copies, moves, tees or redirects INTO `specs/<KEY>/APPROVED`, when guard_bash runs, then it blocks.
  - Blocks with ``the APPROVED marker is written only by `make approve-spec`, run by a human`` when, after lexing:
    - a redirection `>`, `>>`, `>|`, `&>`, `n>` targets a marker word, also quoted (`> "specs/X/APPROVED"`) or with a
      variable (`> "specs/$KEY/APPROVED"`);
    - or a simple command runs `cp`, `mv`, `install`, `ln`, `touch`, `truncate`, `dd`, `tee` (also `tee -a`), `rm`,
      `rsync`, `sed` with `-i`/`--in-place`, or `git` with `add`, `rm`, `mv`, `checkout`, `restore`, `stage`,
      `update-index` or `apply`, and a marker word comes after it (`dd of=...` included).
  - A marker word is a word whose last path component is `APPROVED` (case-insensitive), so `specs/X/APPROVED`,
    `./specs/X/APPROVED` and a bare `APPROVED` after `cd specs/X` all count. The value of `-m`/`--message` is never a
    marker word.
  - Interpreters writing the file (`python3 -c "open('specs/X/APPROVED','w')"`) hit the AC-1 fallback.
  - Reading stays allowed: `cat`, `ls`, `head`, `wc`, `test -f`, `grep`, `rg`, `git status`, `git diff`, `git log`,
    `git show`. Today's guard blocks these (fixed false positive).
  - `git add` of the marker stays blocked by design. `rm`/`git rm` of the marker and copying *from* it with
    `cp`/`mv`/`rsync`/`ln` also block (ASSUMPTION A3).
  - Verified by `test_writing_the_approved_marker_is_blocked`.
  - Amendment 1: the writer list and the "`-m` value is never a marker word" rule are superseded. A marker mention
    blocks unless it is DATA or READ. A redirect target is never relaxed, and READ excludes options, so
    `touch -m`, `sort -o`, `curl -o`, `patch`, `git commit ... -- <marker>` and `git diff --output=<marker>` block
    (p07, p08, p13-p16). Copying from the marker and `rm` of it still block (they are not read commands).
- **AC-3** Given a heredoc or quoted string that only mentions `make approve-spec` or `APPROVED` as text (e.g. `cat > pr.md <<'EOF' ... run make approve-spec ... EOF`, `git commit -m "... APPROVED ..."`), when guard_bash runs, then it is allowed.
  - Heredoc bodies are data when the delimiter is quoted (`<<'EOF'`, `<<"EOF"`, `<<\EOF`), and also when it is not
    quoted, provided the body contains no `$(`, backtick, `${` or backslash (bash would expand those). `<<-` (tab
    stripping) is supported.
  - Quoted text (`'...'`, `"..."`, `$'...'`, `$"..."`) is data when it contains a blank or a shell metacharacter. A
    plain quoted word (`'approve-spec'`) stays visible, so it cannot hide a command word. Inside `"..."`, `$( )` is
    still code and is checked.
  - Data counts as text only for commands that just print, search or record it ("printers"):
    - `cat`, `echo`, `printf`, `tee`, `grep`, `egrep`, `fgrep`, `rg`, `head`, `tail`, `wc`, `jq`, `test`, `[`,
      `[[`, `sort`, `diff`, `true`, `:`;
    - `git commit|tag|notes|log|show|diff|grep|status|stash`;
    - `gh pr|issue|release create|edit|comment|view|list|close|reopen`.
    For any other command that gets data, the mention check decides, as before IDP-14 (Q2).
  - So these are allowed:
    - `cat > pr.md <<'EOF'` with a PR body that quotes `make approve-spec` (with backticks) and `specs/IDP-14/APPROVED`;
    - `git commit -m "... APPROVED ..."`;
    - the `git commit -m "$(cat <<'EOF' ... EOF\n)"` pattern;
    - `gh pr create --body "..."` and `--body-file - <<'EOF'`;
    - `grep -rn 'make approve-spec' docs`, `printf ... > notes.md`.
  - Plain unquoted mentions given to a printer (`echo make approve-spec`, `grep -rn approve-spec docs`) are allowed
    too: they do not execute anything (ASSUMPTION A4).
  - Comments (`# ...` at the start of a word) are removed before the check, as the shell ignores them.
  - The other `RULES` still run on the raw command (AC-4). A PR body that quotes `.github/`, `gh pr merge` or
    `git push origin main` is still blocked by those rules (Q1). The AC-3 test bodies avoid them.
  - Verified by `test_mentioning_approval_as_text_is_allowed`.
  - Amendment 1: the printer list and conditions are now those of rule (a) in "Amendment 1". `sort`, `diff`,
    `git stash` and the `gh view|list|close|reopen` verbs are dropped, and `git commit|tag|notes` is limited to the
    message value.
    - Plain quoted words (`'approve-spec'`) are data again; that is safe because a printer only prints them.
    - Unquoted mentions given to printers and mentions in comments now block (A4 superseded, Q7).
    - Four MENTIONS_ONLY cases change (see "MENTIONS_ONLY under amendment 1"); all others stay allowed.
  - Amendment 2: `test`, `[` and `[[` are no longer printers or inert. Their marker paths are relaxed only through
    READ. `printf -v` gives no DATA. Verified by the amendment 2 cases in `test_running_spec_approval_is_blocked`,
    `test_approval_check_fails_closed_when_unsure` and `test_mentioning_approval_as_text_is_allowed`.
- **AC-4** Given the existing blocked/allowed command lists in `tests/plugin/test_hooks.py`, then they all still pass.
  - The two lists and both test bodies stay unchanged (no command added, removed or edited). Each test gains a stacked
    `@pytest.mark.ac("IDP-14:AC-4")` next to its existing `IDP-10:AC-3` mark, so `idp spec-trace IDP-14` sees AC-4.
    This is the simplest honest option: those two tests are exactly the evidence AC-4 asks for, and the mark changes
    nothing they run.
  - Every rule in `RULES` other than the two approval rules stays byte-for-byte the same and still runs on the raw
    command first.
  - The whole `tests/plugin` suite (`make validate-plugin`) stays green.
- **AC-5** Given the `pr-generate` skill, then it tells the agent to use the Co-Authored-By trailer supplied by the environment/harness, not a hard-coded one.
  - Step 1 of `plugins/idp-agentic/skills/pr-generate/SKILL.md` no longer names any trailer value. It tells the
    agent to end each commit message with the `Co-Authored-By` trailer supplied by the environment (the harness or
    its system instructions), copied exactly, and never to hard-code or invent one. If none is supplied, the agent
    adds none (ASSUMPTION A7). Exact wording in plan.md.
  - Verified by `test_pr_generate_uses_environment_co_author_trailer`: `noreply@anthropic.com` and
    `Co-Authored-By: Claude` are absent, and the environment-supplied wording is present (whitespace normalised).

## Edge cases and assumptions
- Unterminated quotes, unterminated heredocs (no terminator line), a heredoc started on the last line, an unclosed
  `$(`, backticks anywhere outside literal text, `$((`, `${...}` other than `${NAME}`/`${#NAME}`/`${1}`, more than 8
  nested `$( )` levels, and `case` inside `$( )` all make the lexer "unsure". When it is unsure, the mention check
  decides (block if the raw text contains `approve-spec` or `specs/<x>/APPROVED`), which is the pre-IDP-14
  behaviour (Q3).
- An unquoted heredoc whose body has backticks (`cat > pr.md <<EOF` with markdown code spans) is unsure and blocks if
  it mentions approval. That is correct: bash runs backticks in such a body. PR composers must quote the delimiter
  (they already do in the template workflow).
- A backslash-escaped character outside quotes counts as the character itself if it is a letter, digit, blank or
  one of `-_./=+,:@%~`. Anything else becomes a neutral character, so `\;` and `\>` create neither a separator nor a
  redirection.
- Words glued to data (`x"a b"y`) lose the data part. At worst this produces a false block, never a missed one,
  because data is never code.
- Indirection is out of reach for a lexical check, as it is today: variables (`m=make; $m approve-spec`), aliases,
  shell functions defined earlier, scripts, Makefile targets that call approval, and globs (`APPROVE?`). The
  backstops are the `CLAUDECODE` refusal in `idp approve-spec`, the deny-list, `protect_paths.py` and human PR
  review.
- `ls .`, `find . ...` and similar commands with a `.` word count as "may run text" (`.` is `source`). They only
  block when they also mention approval.
- ASSUMPTION A1: the Bash tool runs commands with `bash -c` or `zsh -c`. The lexer models the quoting, escapes,
  comments, heredocs and `$( )` that both shells share. zsh's `=cmd` is handled. Other zsh-only expansions either make
  the lexer unsure or are residual risk.
- ASSUMPTION A2: AC-1's "executes" includes the wrapper, path, case and quoted/escaped-word forms listed under AC-1.
  It also includes text that may reach a shell or interpreter; that text is handled by the fallback, not by
  interpretation.
- Amendment 1: the edge-case bullets above about the unsure fallback and escapes describe H1. Under the new design:
  - unsure means "relax nothing";
  - escapes are kept as part of the word (so `#` after them is not a comment);
  - the `.`-word rule is gone (non-inert commands simply disable DATA).
  The indirection bullet still holds (p12 and other forms without a raw mention). p17 (`$m approve-spec`) now
  blocks, because the raw mention is not relaxed.
- ASSUMPTION A3 (superseded by amendment 1: no writer list; any marker mention outside DATA/READ blocks, so `rm`,
  copying from the marker and any unlisted writer block): AC-2 deliberately also blocks `rm`/`git rm` of the marker (blocked today), copying from it with
  `cp`/`mv`/`rsync`/`ln` (a marker word anywhere after the writer), and writing any file named `APPROVED` (also
  relative to the current directory). All of these are fail-closed choices; reading stays allowed.
- ASSUMPTION A4 (superseded by amendment 1: unquoted mentions given to printers block; see Q7): unquoted mentions
  given to printers are allowed, because they do not execute. AC-3 names only heredocs and quoted strings, but AC-1
  blocks only execution.
- ASSUMPTION A5 (superseded by amendment 1: the mention regex is now the base check for every command, matching
  `approve-spec` anywhere and any word whose last path component is `APPROVED`, case-insensitive): the fallback
  mention check is slightly broader than the old rule 1. It matches `approve-spec` anywhere, not only after
  `make`/`idp`, so `echo approve-spec | xargs make` blocks.
- ASSUMPTION A6: the protected-path rule and the other raw rules are unchanged (AC-4). Their false positives on
  quoted or heredoc text are a separate decision (Q1).
- ASSUMPTION A7: if the environment supplies no `Co-Authored-By` trailer, the agent adds none. The PR's AI disclosure
  and the `ai-assisted` label still record AI involvement.
- ASSUMPTION A8: the running session uses the installed plugin copy (`CLAUDE_PLUGIN_ROOT`). So the fix reaches agent
  sessions only after merge and a plugin update; the tests exercise the repository copy (Q4, Q5).
- ASSUMPTION A9 (amendment 1): rule (a)(i) ("no `$(`, backtick or `${`") applies only to text the shell expands:
  double-quoted strings and bodies of heredocs whose delimiter is unquoted. Single-quoted strings, `$'...'` and
  quoted-delimiter heredoc bodies are literal for the shell, so backticks in them (markdown in PR bodies) are data.
  Read literally, (i) would block every PR body with code spans, which is the ticket's main case.
- ASSUMPTION A10 (amendment 1): a non-string `tool_input.command` is turned into its JSON text before checking,
  instead of crashing (exit 1 does not block).
- ASSUMPTION A11 (amendment 1): READ (rule b) relaxes only marker mentions, as the decision says ("an unquoted marker
  word"). An unquoted `approve-spec` given to a read command (for example as a grep pattern) blocks.

## Non-functional requirements
- The hook stays stdlib-only (`json`, `re`, `sys`) and Python 3.9-compatible: no `match`, no `X | Y` types, no
  `str.removeprefix`, no 3.10+ APIs. H1 checks this by running the smoke commands with `/usr/bin/python3` (3.9 on
  macOS) and by `ast.parse(..., feature_version=(3, 9))`.
- Runs in under 1 s. `check()` on each of these finishes in under 1.0 s in-process
  (`test_large_command_is_checked_within_a_second`):
  - a 200 KB quoted heredoc;
  - a 200 KB single line;
  - 40 000 words after one command;
  - a 200 KB unterminated quote;
  - 2 000 nested `$(`;
  - 2 000 heredocs on one line.
  Amendment 1: the cases are now:
  - the 200 KB quoted heredoc (allowed);
  - 200 KB of mentions inside one quoted string (allowed);
  - 20 000 quoted mention words (allowed);
  - 200 KB of unquoted mentions (blocked);
  - 40 000 words without a mention (allowed);
  - a 200 KB unterminated quote holding a mention (blocked);
  - 2 000 nested `$(` (blocked);
  - 2 000 heredocs whose bodies mention approval (allowed).

  Mentions are checked against the relaxed spans with `bisect`, so many mentions times many spans stays fast. A
  command with no raw mention skips the lexer. `test_hook_parses_as_python_39` checks the Python 3.9 syntax.
  The lexer and all regexes are linear (no nested unbounded quantifiers; heredoc terminators are found line by line).
  The end-to-end hook (interpreter start included) stays far below the 10 s `hooks.json` timeout. The test does not
  time subprocess start-up, which would make it flaky.
- `ruff check` and `ruff format --check` are clean on the hook and the tests. `make verify` is green, including
  `idp spec-trace IDP-14` and `idp test-quality-lint` on the changed test files.
- No new dependencies. No change to `hooks.json`, `.claude/settings.json` or other hooks.

## Out of scope
- Full shell parsing (ticket). Variable, alias, function and script indirection (see edge cases).
- The false positives of the other raw rules (protected paths, `git push ... main`, `gh pr merge`, ...) (Q1).
- Plugin versioning and install/update mechanics (Q4, Q5).
- Changes to `.claude/settings.json`, `protect_paths.py`, `approve_spec.py` or the iteration record in
  `docs/plan/iterations/01-platform-skeleton.md`.

## Open questions
- Q1 (scope): the protected-path rule, and every other raw rule (`git push ... main`, `gh pr merge`,
  `terraform apply`, ...), still blocks a heredoc or quoted string that only mentions it. Example:
  `cat > pr.md <<'EOF' ... .github/workflows ... EOF`. Fix it here with the same lexer, or in a follow-up?
  Recommendation: a follow-up ticket (another human-led hook session) that applies the masked view to all rules, with
  its own ACs and AC-4-style regression lists. This ticket stays limited to the approval rules: the smallest change,
  matching AC-1..AC-3. Alternative: about 10 more lines in H1 for the protected-path rule only, plus a new AC (ticket
  change).
- Q2 (superseded by amendment 1, resolved: relax-only, so there is no writer list or interpreter list any more.
  Only the printer, reader and inert lists remain, and a missing entry can only cause a false positive, never a
  bypass): please confirm three lists in plan.md:
  - the "may run text" list (shells, interpreters, `xargs`, `eval`, `source`, `.`, `ssh`, `su`, `script`, `at`,
    `crontab`, `alias`, `make -f/-E/--eval`, `git -c/-x/--exec/bisect/foreach/filter-branch`);
  - the printer allow-list;
  - the writer list.
  Recommendation: accept them as they are. A command missing from the printer list only causes a false positive
  (fallback to today's behaviour). A missing writer is caught whenever the path contains `specs/<x>/APPROVED` and the
  lexer is unsure, but not otherwise. A missing interpreter that reads text from a pipe or stdin is residual risk.
  Extend the lists later as needed.
- Q3 (unsure behaviour): for unterminated quotes or heredocs and the other unsure cases, fall back to the mention
  check: block if the raw text contains `approve-spec` or `specs/<x>/APPROVED`. Recommendation: yes. It is today's
  behaviour, slightly broadened (A5), and never weaker. (Resolved by amendment 1: unsure relaxes nothing, so every
  raw mention blocks.)
- Q4 (installed copy): hooks run from `${CLAUDE_PLUGIN_ROOT}` (installed from the marketplace), while the tests run
  the repository copy. Add a plugin-side check that the hook a session runs equals the repo one? Recommendation: not
  in this ticket. The install path is per machine and absent in CI. Note "update the plugin after merge" in the
  CHANGELOG and PR, and consider a follow-up (for example a SessionStart warning when the installed hooks differ from
  `plugins/idp-agentic/hooks/` in the current repo).
- Q5 (version bump): bump `idp-agentic` from 0.1.0 to 0.1.1 so installed copies refresh? It needs both
  `plugins/idp-agentic/.claude-plugin/plugin.json` and the protected root `.claude-plugin/marketplace.json` (the
  structure test requires equal versions), so it would be human work. Recommendation: yes, as an optional final step
  of H1, if Claude Code refreshes plugins only on a version change. Please confirm how you update the plugin.
- Q6 (no trailer supplied): if the environment supplies no `Co-Authored-By` trailer, add none? Recommendation: yes
  (A7). Inventing one is exactly what AC-5 removes.
- Q7 (amendment 1, unquoted words): should a plain unquoted word given to a printer or read command also be relaxed
  (DATA), for example `echo make approve-spec`, `grep -rn approve-spec docs` or `echo approved`? Recommendation: no.
  Keep the human's narrow rule; quoting costs the agent two characters, and every extra relaxation is another place
  where the lexer must match the shell exactly. The three MENTIONS_ONLY cases change to quoted forms instead.
- Q8 (amendment 1, inert-all rule): the decision's (a)(iii) names pipelines. The plan widens it: DATA relaxation is
  allowed only if every simple command in the input is inert. That also covers writing a script and running it in
  the same command (`echo 'make approve-spec' > x.sh; sh x.sh`), groups and loops piped into a shell
  (`{ echo '...'; } | sh`, `for ...; done | sh`), and commands whose head is computed (`$SHELL`, `$m`).
  Recommendation: yes. It is simpler than tracking pipelines and groups, and it only costs false positives when a
  mention-only command is combined with another command (for example `make verify && git commit -m "..."`, which
  still blocks, as on main).

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | tests/plugin/test_hooks.py::test_running_spec_approval_is_blocked, tests/plugin/test_hooks.py::test_approval_check_fails_closed_when_unsure, tests/plugin/test_hooks.py::test_mentions_in_comments_block (amendment 1) |
| AC-2 | tests/plugin/test_hooks.py::test_writing_the_approved_marker_is_blocked, tests/plugin/test_hooks.py::test_approval_check_fails_closed_when_unsure, tests/plugin/test_hooks.py::test_mentions_in_comments_block (amendment 1) |
| AC-3 | tests/plugin/test_hooks.py::test_mentioning_approval_as_text_is_allowed, tests/plugin/test_hooks.py::test_large_command_is_checked_within_a_second (NFR), tests/plugin/test_hooks.py::test_large_heredoc_is_allowed_by_the_hook, tests/plugin/test_hooks.py::test_hook_parses_as_python_39 (NFR, amendment 1) |
| AC-4 | tests/plugin/test_hooks.py::test_dangerous_commands_are_blocked, tests/plugin/test_hooks.py::test_normal_commands_are_allowed (lists unchanged; `IDP-14:AC-4` mark stacked) |
| AC-5 | tests/plugin/test_structure.py::test_pr_generate_uses_environment_co_author_trailer |
