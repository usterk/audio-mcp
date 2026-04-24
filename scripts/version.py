#!/usr/bin/env python3
"""Print `<pyproject version>+<short-sha>` for CI tag calculation."""
from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path


def main() -> int:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    version = pyproject["project"]["version"]
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        sha = "nogit"
    print(f"{version}+{sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
