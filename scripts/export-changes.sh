#!/usr/bin/env bash
#
# export-changes.sh — bundle this branch's changes vs the baseline snapshot into a
# zip the other devs can review and fold into the official repo by hand.
#
# The bundle is NOT a working checkout: no venv, no deps, no history.
# It carries: a migration guide, a reference patch, full copies of every touched
# file, and a PowerShell script that creates just the brand-new files/dirs
# (Windows, no admin). Modified files are merged by hand.
#
# Usage:  scripts/export-changes.sh [base-ref]
#   base-ref  commit to diff against (default: the repo's root commit = the
#             baseline snapshot that matches the official repo's develop branch).
#
set -euo pipefail

CODENAME="jack"                       # stand-in name — keep the real product name out of the bundle
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

BASE="${1:-$(git rev-list --max-parents=0 HEAD | tail -1)}"
DATE="$(date +%Y%m%d)"
NAME="${CODENAME}-back-changes-${DATE}"
OUT="$REPO_ROOT/exports/$NAME"

# Files that must never leave the sandbox: local dev values, secrets, and the
# "local-run adaptations" commit (CDN swagger, public PyPI, scrubbed BdF refs) —
# the official repo already has the real versions of these.
EXCLUDE=(
  ':(exclude).env'
  ':(exclude).gitignore'
  ':(exclude)scripts/**'                         # this bundling script itself
  ':(exclude)*.sh'                               # shell scripts stay in the sandbox, wherever they live
  ':(exclude)README.md'                          # sandbox: scrubbed clone URL + contacts
  ':(exclude)docs/python-env-setup.md'           # sandbox: internal PyPI index removed
  ':(exclude)pyproject.toml'                     # sandbox: authors/deps/index tweaked
  ':(exclude)uv.lock'                            # sandbox: BdF artifactory -> pypi.org
  ':(exclude)sonar-project.properties'           # sandbox: the official Sonar config is not ours to change
  ':(exclude)src/adam_api/main.py'               # sandbox: swagger from CDN, /static mount removed
)

rm -rf "$OUT" "$OUT.zip"
mkdir -p "$OUT/files"

# --- manifest: A (added) / M (modified) / D (deleted) + path ---
git diff --name-status "$BASE" -- . "${EXCLUDE[@]}" > "$OUT/manifest.txt"

if [[ ! -s "$OUT/manifest.txt" ]]; then
  echo "No changes vs $BASE — nothing to export." >&2
  rm -rf "$OUT"
  exit 1
fi

# --- patch: apply with `git apply changes.patch` from the target repo root ---
git diff "$BASE" -- . "${EXCLUDE[@]}" > "$OUT/changes.patch"

# --- full copies of every added/modified file, at their real paths ---
NEW_FILES=()
while IFS=$'\t' read -r status path; do
  case "$status" in
    D*) continue ;;                       # deletions: described in the guide, no file to ship
    A*) NEW_FILES+=("$path") ;;
  esac
  mkdir -p "$OUT/files/$(dirname "$path")"
  cp "$path" "$OUT/files/$path"
done < "$OUT/manifest.txt"

printf '%s\n' "${NEW_FILES[@]:-}" | sed '/^$/d' > "$OUT/new-files.txt"

# --- helper: create just the brand-new files in the target repo (Windows, no admin) ---
cat > "$OUT/create-new-files.ps1" <<'PS1'
#Requires -Version 5
<#
  create-new-files.ps1 — create the files that are NEW in this bundle (folders
  included). No admin. Modified files are NOT touched — merge those yourself.

  Run from the ROOT of the target repo:

      powershell -ExecutionPolicy Bypass -File .\create-new-files.ps1

  (-ExecutionPolicy Bypass is per-process, not a machine setting — no admin.)

  -Force   overwrite new-file paths that already exist
#>
param([switch]$Force)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path -LiteralPath '.git')) {
  throw 'Run this from the root of the target repo (no .git here).'
}

Get-Content -LiteralPath (Join-Path $here 'new-files.txt') |
  ForEach-Object { $_.Trim() } | Where-Object { $_ } | ForEach-Object {
    $rel  = $_ -replace '/', [IO.Path]::DirectorySeparatorChar
    $src  = Join-Path $here (Join-Path 'files' $rel)
    $dest = Join-Path (Get-Location) $rel
    if ((Test-Path -LiteralPath $dest) -and -not $Force) {
      Write-Host "skip (exists): $rel"; return
    }
    $dir = Split-Path -Parent $dest
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
      New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dest -Force
    Write-Host "wrote: $rel"
  }
PS1

# --- migration guide ---
GEN_DATE="$(date +%Y-%m-%d)"
# skip commits whose changes are all in EXCLUDE'd paths (sandbox-local, tooling)
COMMITS="$(git log --reverse --format='- **%s**%n%n%w(0,2,2)%b' "$BASE"..HEAD \
  --invert-grep --grep='local-run adaptations' --grep='export-changes.sh' \
  | sed -E '/^[[:space:]]*(Co-Authored-By|Claude-Session|Co-authored-by):/d' \
  | cat -s)"
{
  cat <<MD
# ${CODENAME^} backend — change bundle (${GEN_DATE})

Not a repo — no venv, no deps, no history. This folds a sandbox dev session
into the official repo.

Baseline: the official \`develop\` snapshot. Diff base: \`$(git rev-parse --short "$BASE")\`.

## Contents

| file | what |
|------|------|
| \`MIGRATION.md\` | this guide |
| \`changes.patch\` | \`git diff\` vs baseline — apply from the target repo root |
| \`files/\` | full copy of every added/modified file at its real path |
| \`create-new-files.ps1\` | creates just the NEW files + dirs (Windows, no admin) |
| \`new-files.txt\` / \`manifest.txt\` | file lists (A/M/D + path) |

## How to apply

From the target repo root, on a clean branch:

\`\`\`bash
git apply --3way changes.patch      # or: git apply changes.patch
\`\`\`

If a hunk rejects, the full post-change file is in \`files/<path>\` for
copy-paste. New files (if any):

\`\`\`powershell
powershell -ExecutionPolicy Bypass -File \\path\\to\\${NAME}\\create-new-files.ps1
\`\`\`

Then \`pytest\` (the touched routers are covered by \`tests/unit/\`).

## Not included (sandbox-local, official repo already has the real versions)

- \`.env\`, \`README.md\`, \`docs/python-env-setup.md\`, \`pyproject.toml\`, \`uv.lock\`
- \`src/adam_api/main.py\` — swagger UI is pointed at a CDN and the \`/static\`
  mount is dropped here because the sandbox has no bundled swagger assets;
  keep the upstream version.

## Changes

$COMMITS
MD
} > "$OUT/MIGRATION.md"

# --- zip ---
( cd "$REPO_ROOT/exports" && zip -qr "$NAME.zip" "$NAME" )

echo "bundle:  exports/$NAME.zip"
echo "staging: exports/$NAME/"
git diff --stat "$BASE" -- . "${EXCLUDE[@]}" | tail -1
