#!/usr/bin/env bash
# Compute a semantic version from conventional-commit history — the canonical,
# copy-able versioning scheme for every app deployed on aurora (à la flowos
# scripts/version.py, but dependency-free: pure bash + git).
#
# Usage:
#   app-version.sh [REPO_DIR] [--json]
#     REPO_DIR  git repo to inspect (default: current dir)
#     --json    print {"version":"X.Y.Z"} instead of bare X.Y.Z
#
# How the version is derived (this is what "names itself" during a build):
#   base   = most recent reachable tag matching vX.Y.Z (else 0.0.0)
#   each commit since the base bumps the version by its conventional-commit type
#   (oldest→newest, so a higher bump resets the lower fields):
#     <type>!: ...  or subject starting "BREAKING CHANGE" → MAJOR (reset min+patch)
#     feat: / refactor:                          → MINOR  (reset patch)
#     fix:/docs:/chore:/perf:/ci:/… or anything  → PATCH
#   No commit is a no-op — version reflects the COUNT and CONTENT of commits.
#
# The Aurora self-hosted runner runs this against each app's checkout and tags
# the built image v<version> (see .github/workflows/deploy-runner.yml). Copy it
# into your app repo (scripts/app-version.sh) to compute the same version locally.
set -euo pipefail

dir="."
json=0
for a in "$@"; do
  case "$a" in
    --json) json=1 ;;
    *) dir="$a" ;;
  esac
done
cd "$dir"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "0.0.0"; exit 0
fi

base_tag="$(git describe --tags --abbrev=0 --match 'v[0-9]*.[0-9]*.[0-9]*' 2>/dev/null || true)"
if [ -n "$base_tag" ] && [[ "$base_tag" =~ ^v?([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
  maj="${BASH_REMATCH[1]}"; min="${BASH_REMATCH[2]}"; pat="${BASH_REMATCH[3]}"
  range="${base_tag}..HEAD"
else
  maj=0; min=0; pat=0; range="HEAD"
fi

# Oldest → newest so a major/minor bump correctly resets the lower fields.
while IFS= read -r subj; do
  [ -n "$subj" ] || continue
  if [[ "$subj" =~ ^[a-zA-Z]+(\([^\)]*\))?!: ]] || [[ "$subj" =~ ^BREAKING[\ -]CHANGE ]]; then
    maj=$((maj + 1)); min=0; pat=0
  elif [[ "$subj" =~ ^(feat|refactor)(\([^\)]*\))?: ]]; then
    min=$((min + 1)); pat=0
  else
    pat=$((pat + 1))
  fi
# --first-parent: count main-line commits only (a squash/merge of a feature
# branch is one bump), so the version tracks main, not every merged sub-commit.
done < <(git log --first-parent --reverse --format='%s' "$range" 2>/dev/null || true)

ver="${maj}.${min}.${pat}"
if [ "$json" = 1 ]; then
  printf '{"version":"%s"}\n' "$ver"
else
  printf '%s\n' "$ver"
fi
