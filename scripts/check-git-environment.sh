#!/usr/bin/env bash

set -u

failures=0

pass() {
  printf '[ok] %s\n' "$1"
}

fail() {
  printf '[fix] %s\n' "$1" >&2
  failures=$((failures + 1))
}

if command -v git >/dev/null 2>&1; then
  pass "$(git --version)"
else
  fail "Git is not installed or is not on PATH."
fi

if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 8))'; then
    pass "$(python3 --version)"
  else
    fail "Python 3.8 or newer is required to generate the submission report."
  fi
else
  fail "Python 3.8 or newer is required to generate the submission report."
fi

if command -v gh >/dev/null 2>&1; then
  pass "$(gh --version | head -n 1)"
else
  if [[ "${CODESPACES:-false}" == "true" ]]; then
    fail "GitHub CLI (gh) is missing from this Codespace."
  else
    printf '[note] GitHub CLI is optional on the local path; you can use GitHub in a browser.\n'
  fi
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  pass "Current directory is a Git working tree."
else
  fail "Run this check from the root of the lab-git repository."
fi

origin_url="$(git remote get-url origin 2>/dev/null || true)"
if [[ -n "$origin_url" ]]; then
  pass "origin is configured: $origin_url"
else
  fail "The origin remote is not configured."
fi

if [[ -n "$origin_url" ]] && git ls-remote --exit-code origin HEAD >/dev/null 2>&1; then
  pass "The origin remote is reachable."
else
  fail "The origin remote is not reachable; check your network and remote URL."
fi

author_name="$(git config user.name || true)"
author_email="$(git config user.email || true)"
if [[ -n "$author_name" && -n "$author_email" ]]; then
  pass "Git commits will use $author_name <$author_email>."
else
  fail "Configure user.name and user.email before creating commits."
fi

if [[ "${CODESPACES:-false}" == "true" ]]; then
  pass "Codespaces environment detected."
  if command -v gh >/dev/null 2>&1 && gh auth status --hostname github.com >/dev/null 2>&1; then
    github_user="$(gh api user --jq .login 2>/dev/null || true)"
    if [[ -n "$github_user" ]]; then
      pass "GitHub CLI is authenticated as $github_user."
    else
      fail "GitHub CLI is authenticated but could not read the current account."
    fi
  else
    fail "GitHub CLI is not authenticated. Restart the Codespace, then rerun this check."
  fi
elif command -v gh >/dev/null 2>&1; then
  if gh auth status --hostname github.com >/dev/null 2>&1; then
    pass "GitHub CLI is authenticated (optional on the local path)."
  else
    printf '[note] GitHub CLI is not authenticated. Use the browser, or run: gh auth login\n'
  fi
fi

if (( failures > 0 )); then
  printf '\nEnvironment check found %d item(s) to fix.\n' "$failures" >&2
  exit 1
fi

printf '\nEnvironment check passed. Continue with Exercise 1.\n'
