"""Run TierMem's offline suite or the optional live DeepSeek integration suite."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def astrbot_python(astrbot_root: Path) -> Path:
    candidates = (
        astrbot_root / ".venv" / "Scripts" / "python.exe",
        astrbot_root / "venv" / "Scripts" / "python.exe",
        astrbot_root / ".venv" / "bin" / "python",
        astrbot_root / "venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(
        f"AstrBot Python not found under {astrbot_root}. Set ASTRBOT_ROOT in .env."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live", action="store_true", help="run the real DeepSeek integration tests"
    )
    args = parser.parse_args()
    values = load_dotenv(ROOT / ".env")
    env = os.environ.copy()
    python = Path(sys.executable)

    if args.live:
        raw_astrbot_root = env.get(
            "ASTRBOT_ROOT", values.get("ASTRBOT_ROOT", "")
        ).strip()
        if not raw_astrbot_root:
            raise SystemExit("Set ASTRBOT_ROOT in .env before running --live.")
        astrbot_root = Path(raw_astrbot_root).expanduser()
        python = astrbot_python(astrbot_root)
        env.update(values)
        env["TIERMEM_RUN_LIVE_TESTS"] = "1"
        existing_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(ROOT), str(astrbot_root), existing_path) if part
        )
    else:
        env["TIERMEM_RUN_LIVE_TESTS"] = "0"

    command = [
        str(python),
        "-m",
        "unittest",
        "discover",
        "-s",
        str(ROOT / "tests"),
        "-v",
    ]
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
