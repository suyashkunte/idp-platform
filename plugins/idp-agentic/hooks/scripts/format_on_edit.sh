#!/usr/bin/env bash
# PostToolUse: format the edited file through the repo's Make contract (`make format FILES=...`), whatever the language.
# Never blocks: formatting problems surface later in `make verify`.
set -u
input=$(cat)
file=$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("file_path",""))' 2>/dev/null)
cwd=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("cwd",""))' 2>/dev/null)
[ -n "$file" ] && [ -f "$file" ] || exit 0
root=$(git -C "${cwd:-.}" rev-parse --show-toplevel 2>/dev/null) || exit 0
if grep -qE '^format:' "$root/Makefile" 2>/dev/null; then
  make -s -C "$root" format FILES="$file" >/dev/null 2>&1 || true
fi
exit 0
