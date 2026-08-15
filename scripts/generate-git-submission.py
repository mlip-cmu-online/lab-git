#!/usr/bin/env python3
"""Generate the Lab 2 Git submission report and machine-readable manifest."""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit


REPORT_NAME = "git-report.html"
MANIFEST_NAME = "git-manifest.json"
EXPECTED_PR = re.compile(r"^/mlip-cmu-online/lab-git/pull/[1-9][0-9]*/?$")


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def resolve_commit(name: str) -> Optional[str]:
    result = git("rev-parse", "--verify", f"{name}^{{commit}}", check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def is_in_head_history(commit: Optional[str]) -> bool:
    if commit is None:
        return False
    return git("merge-base", "--is-ancestor", commit, "HEAD", check=False).returncode == 0


def short_commit(commit: Optional[str]) -> str:
    if commit is None:
        return "not found"
    return git("rev-parse", "--short=12", commit).stdout.strip()


def sanitize_url(value: str) -> str:
    """Remove URL credentials and query parameters before writing evidence."""
    if value.lower().startswith(("http://", "https://", "ssh://")):
        try:
            parsed = urlsplit(value)
            host = parsed.hostname or ""
            port = parsed.port
        except ValueError:
            return "invalid-url-redacted"
        if port:
            host = f"{host}:{port}"
        if parsed.scheme == "ssh" and parsed.username == "git":
            host = f"git@{host}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))

    scp_style = re.match(r"^([^@/:]+)@([^:]+):(.+)$", value)
    if scp_style:
        user, host, path = scp_style.groups()
        safe_user = "git" if user == "git" else "credentials-redacted"
        return f"{safe_user}@{host}:{path}"

    return value.split("?", 1)[0].split("#", 1)[0]


def sanitized_remotes() -> tuple[str, set[str]]:
    result = git("remote", "-v", check=False)
    if result.returncode != 0:
        return "", set()

    lines: list[str] = []
    names: set[str] = set()
    for raw_line in result.stdout.splitlines():
        match = re.match(r"^(\S+)\s+(\S+)(\s+\([^)]+\))$", raw_line)
        if not match:
            continue
        name, url, suffix = match.groups()
        names.add(name)
        lines.append(f"{name}\t{sanitize_url(url)}{suffix}")
    return "\n".join(lines), names


def valid_pr_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and EXPECTED_PR.fullmatch(parsed.path) is not None
    )


def check(
    name: str,
    present: bool,
    location: str,
    identifier: str,
    detail: str,
) -> dict[str, str]:
    return {
        "name": name,
        "status": "present" if present else "missing",
        "location": location,
        "identifier": identifier,
        "detail": detail,
    }


def render_report(
    learner: str,
    generated_at: str,
    pr_url: str,
    head: str,
    remotes: str,
    history: str,
    named_commits: dict[str, str],
    checks: list[dict[str, str]],
    pr_is_valid: bool,
) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(item['name'])}</td>"
        f"<td class=\"{item['status']}\">{item['status']}</td>"
        f"<td>{html.escape(item['identifier'])}</td>"
        f"<td>{html.escape(item['detail'])}</td>"
        "</tr>"
        for item in checks
    )
    commits = "\n".join(
        f"<li><strong>{html.escape(label)}</strong>: "
        f"<code>{html.escape(value)}</code></li>"
        for label, value in named_commits.items()
    )
    overall = (
        "complete"
        if all(item["status"] == "present" for item in checks)
        else "incomplete"
    )
    safe_pr = html.escape(pr_url)
    pr_cell = f'<a href="{safe_pr}">{safe_pr}</a>' if pr_is_valid else safe_pr
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lab 2 Git Submission Report</title>
  <style>
    body {{ color: #17202a; font: 16px/1.45 system-ui, sans-serif; margin: 2rem auto; max-width: 72rem; padding: 0 1rem; }}
    h1, h2 {{ color: #102a43; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #bcccdc; padding: .55rem; text-align: left; vertical-align: top; }}
    th {{ background: #f0f4f8; }}
    pre {{ background: #f5f7fa; border: 1px solid #bcccdc; overflow-x: auto; padding: 1rem; white-space: pre; }}
    code {{ overflow-wrap: anywhere; }}
    .present, .complete {{ color: #176b3a; font-weight: 700; }}
    .missing, .incomplete {{ color: #a61b1b; font-weight: 700; }}
    .note {{ background: #fffbea; border-left: .3rem solid #d69e2e; padding: .7rem 1rem; }}
  </style>
</head>
<body>
  <h1>Lab 2: Git Submission Report</h1>
  <table>
    <tr><th>Learner</th><td>{html.escape(learner)}</td></tr>
    <tr><th>Generated</th><td>{html.escape(generated_at)}</td></tr>
    <tr><th>Overall completeness</th><td class="{overall}">{overall}</td></tr>
    <tr><th>Pull request</th><td>{pr_cell}</td></tr>
    <tr><th>Current commit SHA</th><td><code>{html.escape(head)}</code></td></tr>
    <tr><th>Checker version</th><td>1.0</td></tr>
  </table>

  <h2>Completeness</h2>
  <table>
    <thead><tr><th>Required evidence</th><th>Status</th><th>Identifier</th><th>Detail</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>

  <h2>Named commits</h2>
  <ul>{commits}</ul>

  <h2 id="remotes">Remotes</h2>
  <pre>{html.escape(remotes or 'No remotes found.')}</pre>

  <h2 id="history">History graph</h2>
  <pre>{html.escape(history or 'No history found.')}</pre>

  <h2>Audit evidence</h2>
  <p>The pull request and the repository at commit <code>{html.escape(head)}</code> are the raw audit evidence.</p>
  <p class="note">This checker verifies objective completeness only. Complete the history and collaboration interpretation spot checks separately in Canvas.</p>

  <h2>Safety check</h2>
  <p>Credentials and URL query parameters are removed from remote URLs before this report is written. Review the report before uploading it and do not add tokens or other secrets.</p>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Lab 2 Git HTML report and JSON manifest."
    )
    parser.add_argument("--learner", required=True, help="Learner name shown in the report")
    parser.add_argument("--pr-url", required=True, help="PR into mlip-cmu-online/lab-git")
    parser.add_argument(
        "--conflict-commit", required=True, help="Conflict-resolution merge commit"
    )
    parser.add_argument("--bad-commit", required=True, help="Intentional bad commit")
    parser.add_argument(
        "--revert-commit", required=True, help="Commit that reverts the bad commit"
    )
    parser.add_argument(
        "--output-dir",
        default="submission",
        type=Path,
        help="Output directory (default: submission)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if git("rev-parse", "--show-toplevel", check=False).returncode != 0:
        print("Run this command from inside the lab-git repository.", file=sys.stderr)
        return 2

    head = git("rev-parse", "HEAD").stdout.strip()
    history = git("log", "--oneline", "--graph", "--decorate").stdout.rstrip()
    remotes, remote_names = sanitized_remotes()

    supplied = {
        "Conflict-resolution merge": args.conflict_commit,
        "Intentional bad commit": args.bad_commit,
        "Revert commit": args.revert_commit,
    }
    resolved = {label: resolve_commit(value) for label, value in supplied.items()}
    displayed = {label: short_commit(value) for label, value in resolved.items()}
    pr_is_valid = valid_pr_url(args.pr_url)
    safe_pr_url = sanitize_url(args.pr_url)

    report_location = REPORT_NAME
    checks = [
        check(
            "pull_request_url",
            pr_is_valid,
            report_location,
            safe_pr_url,
            (
                "PR URL targets mlip-cmu-online/lab-git."
                if pr_is_valid
                else "Expected an HTTPS GitHub PR URL into mlip-cmu-online/lab-git."
            ),
        ),
        check("current_commit_sha", bool(head), report_location, head, "Captured from HEAD."),
        check(
            "origin_and_upstream_remotes",
            {"origin", "upstream"}.issubset(remote_names),
            f"{report_location}#remotes",
            ", ".join(sorted(remote_names)) or "none",
            "Captured sanitized output from git remote -v.",
        ),
        check(
            "history_graph",
            bool(history),
            f"{report_location}#history",
            head,
            "Captured from git log --oneline --graph --decorate.",
        ),
    ]
    for label, key in (
        ("Conflict-resolution merge", "conflict_commit_present"),
        ("Intentional bad commit", "bad_commit_present"),
        ("Revert commit", "revert_commit_present"),
    ):
        commit = resolved[label]
        present = is_in_head_history(commit)
        checks.append(
            check(
                key,
                present,
                f"{report_location}#history",
                displayed[label],
                (
                    "Named commit is reachable from HEAD."
                    if present
                    else "Named commit was not found in the submitted HEAD history."
                ),
            )
        )

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    complete = all(item["status"] == "present" for item in checks)
    manifest = {
        "schema_version": "1.0",
        "checker_version": "1.0",
        "lab": "Lab 2: Git",
        "learner": args.learner,
        "generated_at": generated_at,
        "complete": complete,
        "report": REPORT_NAME,
        "identifiers": {
            "pull_request_url": safe_pr_url,
            "current_commit_sha": head,
            "conflict_commit": displayed["Conflict-resolution merge"],
            "bad_commit": displayed["Intentional bad commit"],
            "revert_commit": displayed["Revert commit"],
        },
        "evidence": {"remotes": remotes, "history_graph": history},
        "checks": checks,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / REPORT_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    report_path.write_text(
        render_report(
            args.learner,
            generated_at,
            safe_pr_url,
            head,
            remotes,
            history,
            displayed,
            checks,
            pr_is_valid,
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {report_path}")
    print(f"Wrote {manifest_path}")
    print(
        "Submission evidence is complete."
        if complete
        else "Submission evidence is incomplete; review the missing checks."
    )
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
