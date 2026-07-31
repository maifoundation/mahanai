from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

import mahanai


class ReleaseIdentityTests(unittest.TestCase):
    def test_runtime_and_package_versions_are_9_0_0(self) -> None:
        pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
        with pyproject_path.open("rb") as handle:
            package_version = tomllib.load(handle)["project"]["version"]

        self.assertEqual("9.0.0", mahanai.__version__)
        self.assertEqual("9.0.0", package_version)


if __name__ == "__main__":
    unittest.main()
