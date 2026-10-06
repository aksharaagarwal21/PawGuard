#!/usr/bin/env bash
# Shared tool resolution for the demo scripts (sourced, not run). Works when PATH lacks uv or pnpm, e.g. when
# Git Bash is started from PowerShell.

if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "This is WSL's Linux bash, which cannot use the Windows tools this project was installed with." >&2
  echo "From PowerShell run:  .\\scripts\\demo_up.ps1   (or open Git Bash and run: bash scripts/demo_up.sh)" >&2
  exit 1
fi

# Project-local tools first, then common user-level install locations.
export PATH="$HOME/bin:$PATH"
for d in "$HOME/anaconda3/Scripts" "$HOME/miniconda3/Scripts" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
  [ -d "$d" ] && PATH="$PATH:$d"
done

# pyrun <program> [args…] — run a program from the project's Python environment.
if command -v uv >/dev/null 2>&1; then
  pyrun() { uv run "$@"; }
elif [ -x ".venv/Scripts/python.exe" ]; then
  pyrun() { local p="$1"; shift; ".venv/Scripts/$p.exe" "$@"; }
else
  echo "Neither uv nor the project's .venv was found. Install uv and run 'uv sync' first." >&2
  exit 1
fi

# pnpm, else the version pinned in package.json through corepack (bundled with Node.js).
if command -v pnpm >/dev/null 2>&1; then PNPM="pnpm"; else PNPM="corepack pnpm"; fi
export PNPM
