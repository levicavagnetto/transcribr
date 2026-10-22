"""Run every check the project relies on: `uv run scripts/check.py`.

Backend: ruff lint, ruff format check, pyright, pytest. Frontend: TypeScript, Vitest.
Exits non-zero on the first failure, naming the step.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def npm() -> str:
    found = shutil.which("npm")
    if found is None:
        sys.exit("check: npm was not found on PATH")
    return found


STEPS: list[tuple[str, list[str], Path]] = [
    ("backend lint", ["uv", "run", "ruff", "check", "."], BACKEND),
    ("backend format", ["uv", "run", "ruff", "format", "--check", "."], BACKEND),
    ("backend types", ["uv", "run", "pyright"], BACKEND),
    ("backend tests", ["uv", "run", "pytest", "-q"], BACKEND),
    ("frontend types", [npm(), "run", "--silent", "typecheck"], FRONTEND),
    ("frontend tests", [npm(), "run", "--silent", "test"], FRONTEND),
]


def main() -> int:
    # `uv run` exports this script's own environment; the backend steps must use backend/.venv.
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    for name, command, cwd in STEPS:
        print(f"\n== {name} ==", flush=True)
        result = subprocess.run(command, cwd=cwd, env=env, check=False)  # noqa: S603
        if result.returncode != 0:
            print(f"\ncheck: FAILED at '{name}' (exit {result.returncode})", flush=True)
            return result.returncode
    print("\ncheck: all steps passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
