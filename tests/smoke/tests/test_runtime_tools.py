#!/usr/bin/env python
"""
Validate that package manager tooling is unavailable in runtime images.
"""

import subprocess
import unittest


class TestRuntimeTools(unittest.TestCase):
    """
    Verify runtime hardening constraints for package manager tools.
    """

    @staticmethod
    def _run_shell(command: str) -> subprocess.CompletedProcess[str]:
        """
        Execute a shell command and capture its output.
        """
        return subprocess.run(["sh", "-lc", command], capture_output=True, text=True, check=False)

    def test_pip_not_available(self) -> None:
        """
        Ensure pip entrypoints and module are unavailable at runtime.
        """
        for tool in ["pip", "pip3"]:
            with self.subTest(tool=tool):
                result = self._run_shell(f"command -v {tool}")
                assert result.returncode != 0, f"Unexpectedly found '{tool}' at: {result.stdout.strip()}"

        result = self._run_shell("python -m pip --version")
        assert result.returncode != 0, "'python -m pip' unexpectedly succeeded"
        assert "No module named pip" in result.stderr, (
            "Expected missing pip module error when invoking 'python -m pip', "
            f"got stderr: {result.stderr!r}"
        )

    def test_apt_not_available(self) -> None:
        """
        Ensure apt entrypoints are unavailable at runtime.
        """
        for tool in ["apt", "apt-get"]:
            with self.subTest(tool=tool):
                result = self._run_shell(f"command -v {tool}")
                assert result.returncode != 0, f"Unexpectedly found '{tool}' at: {result.stdout.strip()}"


if __name__ == "__main__":
    unittest.main()
