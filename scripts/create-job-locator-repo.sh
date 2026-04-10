#!/usr/bin/env bash
# Create https://github.com/<owner>/job-locator and push this branch as main.
# One-time: brew install gh && gh auth login
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OWNER="${GITHUB_OWNER:-seeing-in-color}"
NAME="${JOB_LOCATOR_NAME:-job-locator}"
BRANCH="${JOB_LOCATOR_BRANCH:-JobLocator}"
URL="https://github.com/${OWNER}/${NAME}.git"

if ! command -v gh >/dev/null 2>&1; then
  echo "Install GitHub CLI and log in:"
  echo "  brew install gh"
  echo "  gh auth login"
  exit 1
fi

if gh repo view "${OWNER}/${NAME}" >/dev/null 2>&1; then
  echo "Repo already exists: ${URL}"
else
  echo "Creating ${URL} …"
  gh repo create "${OWNER}/${NAME}" \
    --private \
    --description "Job Locator — job search & apply tooling"
fi

if git remote get-url job-locator >/dev/null 2>&1; then
  echo "Remote job-locator OK ($(git remote get-url job-locator))"
else
  git remote add job-locator "${URL}"
fi

echo "Pushing ${BRANCH} → job-locator main …"
git push -u job-locator "${BRANCH}:main"

echo "Done: https://github.com/${OWNER}/${NAME}"
