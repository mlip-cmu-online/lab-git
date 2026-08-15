import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Optional


SCRIPT = Path(__file__).parents[1] / "scripts" / "generate-git-submission.py"


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class GenerateGitSubmissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        run("git", "init", "-b", "main", cwd=self.repo)
        run("git", "config", "user.name", "Test Learner", cwd=self.repo)
        run("git", "config", "user.email", "learner@example.com", cwd=self.repo)
        run(
            "git",
            "remote",
            "add",
            "origin",
            "https://secret-value@github.com/learner/lab-git.git?token=also-secret",
            cwd=self.repo,
        )
        run(
            "git",
            "remote",
            "add",
            "upstream",
            "https://github.com/mlip-cmu-online/lab-git.git",
            cwd=self.repo,
        )

        self.file = self.repo / "example.txt"
        self.file.write_text("base\n", encoding="utf-8")
        run("git", "add", "example.txt", cwd=self.repo)
        run("git", "commit", "-m", "initial", cwd=self.repo)

        run("git", "checkout", "-b", "merge-conflict", cwd=self.repo)
        self.file.write_text("feature\n", encoding="utf-8")
        run("git", "commit", "-am", "feature change", cwd=self.repo)
        run("git", "checkout", "main", cwd=self.repo)
        self.file.write_text("main\n", encoding="utf-8")
        run("git", "commit", "-am", "main change", cwd=self.repo)
        run("git", "merge", "merge-conflict", cwd=self.repo, check=False)
        self.file.write_text("resolved\n", encoding="utf-8")
        run("git", "add", "example.txt", cwd=self.repo)
        run("git", "commit", "-m", "resolve merge conflict", cwd=self.repo)
        self.conflict = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()

        self.file.write_text("resolved\ndebug=true\n", encoding="utf-8")
        run("git", "commit", "-am", "intentional bad change", cwd=self.repo)
        self.bad = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        run("git", "revert", "--no-edit", self.bad, cwd=self.repo)
        self.revert = run("git", "rev-parse", "HEAD", cwd=self.repo).stdout.strip()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def generate(
        self,
        conflict: Optional[str] = None,
        pr_url: str = "https://github.com/mlip-cmu-online/lab-git/pull/123",
    ) -> subprocess.CompletedProcess[str]:
        return run(
            "python3",
            str(SCRIPT),
            "--learner",
            "Test Learner",
            "--pr-url",
            pr_url,
            "--conflict-commit",
            conflict or self.conflict,
            "--bad-commit",
            self.bad,
            "--revert-commit",
            self.revert,
            cwd=self.repo,
            check=False,
        )

    def test_generates_complete_report_and_matching_manifest(self) -> None:
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)

        manifest_path = self.repo / "submission" / "git-manifest.json"
        report_path = self.repo / "submission" / "git-report.html"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        report = report_path.read_text(encoding="utf-8")

        self.assertTrue(manifest["complete"])
        self.assertTrue(all(item["status"] == "present" for item in manifest["checks"]))
        self.assertIn(self.conflict[:12], report)
        self.assertIn(self.bad[:12], report)
        self.assertIn(self.revert[:12], report)
        self.assertNotIn("secret-value", report)
        self.assertNotIn("also-secret", report)
        self.assertNotIn("secret-value", json.dumps(manifest))

    def test_writes_incomplete_outputs_when_named_commit_is_missing(self) -> None:
        result = self.generate(conflict="not-a-commit")
        self.assertEqual(result.returncode, 1)
        manifest = json.loads(
            (self.repo / "submission" / "git-manifest.json").read_text(encoding="utf-8")
        )
        checks = {item["name"]: item["status"] for item in manifest["checks"]}
        self.assertFalse(manifest["complete"])
        self.assertEqual(checks["conflict_commit_present"], "missing")

    def test_rejects_and_redacts_a_pr_url_containing_credentials(self) -> None:
        result = self.generate(
            pr_url=(
                "https://secret-pr-value@github.com/"
                "mlip-cmu-online/lab-git/pull/123?token=also-secret-pr"
            )
        )
        self.assertEqual(result.returncode, 1)
        manifest_text = (self.repo / "submission" / "git-manifest.json").read_text(
            encoding="utf-8"
        )
        report = (self.repo / "submission" / "git-report.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("secret-pr-value", manifest_text + report)
        self.assertNotIn("also-secret-pr", manifest_text + report)


if __name__ == "__main__":
    unittest.main()
