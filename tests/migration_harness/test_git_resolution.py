from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.migration_harness import runtime_executor
from tools.migration_harness.runtime_executor import RuntimeEvidenceError, capture_git_metadata


class GitResolutionTests(unittest.TestCase):
    @staticmethod
    def _fake_git(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("git fixture\n", encoding="utf-8")
        return path

    def test_explicit_environment_path_has_priority_over_path_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            explicit = self._fake_git(root / "env-git.exe")
            path_git = self._fake_git(root / "path-git.exe")
            with patch.dict(
                os.environ,
                {"JCFB_V4_GIT_EXE": str(explicit), "PATH": ""},
                clear=True,
            ), patch.object(runtime_executor.shutil, "which", return_value=str(path_git)) as which:
                resolved = runtime_executor._resolve_git_executable()
            self.assertEqual(str(explicit.resolve()), resolved)
            which.assert_not_called()

    def test_path_lookup_is_used_when_no_explicit_override_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            path_git = self._fake_git(Path(directory) / "path-git.exe")

            def fake_which(command_name: str):
                return str(path_git) if command_name == "git" else None

            with patch.dict(os.environ, {"PATH": ""}, clear=True), patch.object(
                runtime_executor.shutil, "which", side_effect=fake_which
            ):
                resolved = runtime_executor._resolve_git_executable()
            self.assertEqual(str(path_git.resolve()), resolved)

    def test_windows_common_install_path_is_used_as_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            program_files = root / "Program Files"
            common_git = self._fake_git(program_files / "Git" / "cmd" / "git.exe")
            environment = {
                "ProgramFiles": str(program_files),
                "ProgramW6432": str(root / "unused-w6432"),
                "ProgramFiles(x86)": str(root / "unused-x86"),
                "LocalAppData": str(root / "AppData" / "Local"),
                "PATH": "",
            }
            with patch.dict(os.environ, environment, clear=True), patch.object(
                runtime_executor.shutil, "which", return_value=None
            ), patch.object(runtime_executor.os, "name", "nt"):
                resolved = runtime_executor._resolve_git_executable()
            self.assertEqual(str(common_git.resolve()), resolved)

    def test_missing_git_fails_closed_with_source_categories_only(self):
        with patch.dict(os.environ, {"PATH": ""}, clear=True), patch.object(
            runtime_executor.shutil, "which", return_value=None
        ), patch.object(runtime_executor, "_windows_common_git_candidates", return_value=()), patch.object(
            runtime_executor.os, "name", "nt"
        ):
            with self.assertRaises(RuntimeEvidenceError) as context:
                runtime_executor._resolve_git_executable()
        self.assertEqual("GIT_EXECUTABLE_NOT_FOUND", context.exception.code)
        message = str(context.exception)
        self.assertIn("GIT_EXECUTABLE_NOT_FOUND", message)
        self.assertIn("JCFB_V4_GIT_EXE environment override", message)
        self.assertIn("PATH via shutil.which", message)
        self.assertIn("Windows common Git installation paths", message)
        self.assertNotRegex(message, r"(?i)(?:[A-Z]:\\Users\\|/Users/)")

    def test_capture_uses_resolved_fake_executable_for_head_branch_and_clean_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fake_git = self._fake_git(root / "fake-git.exe")
            head = "a" * 40
            outputs = {
                ("rev-parse", "--show-toplevel"): str(root),
                ("rev-parse", "HEAD"): head,
                ("branch", "--show-current"): "feature/git-resolution",
                ("status", "--porcelain", "--untracked-files=all"): "",
            }
            calls = []

            def fake_run(command, **kwargs):
                command = list(command)
                calls.append(command)
                return SimpleNamespace(returncode=0, stdout=outputs[tuple(command[3:])])

            with patch.object(runtime_executor, "_resolve_git_executable", return_value=str(fake_git)), patch.object(
                runtime_executor.subprocess, "run", side_effect=fake_run
            ):
                metadata = capture_git_metadata(root)

            self.assertEqual(
                {
                    "git_head": head,
                    "git_branch": "feature/git-resolution",
                    "working_tree_clean": True,
                    "repo_root": root.as_posix(),
                },
                metadata,
            )
            self.assertEqual(
                [
                    [str(fake_git), "-C", str(root), "rev-parse", "--show-toplevel"],
                    [str(fake_git), "-C", str(root), "rev-parse", "HEAD"],
                    [str(fake_git), "-C", str(root), "branch", "--show-current"],
                    [str(fake_git), "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                ],
                calls,
            )


if __name__ == "__main__":
    unittest.main()
