"""Kintsugi: photograph what broke, print what fits."""

from pathlib import Path

import os

__version__ = "0.2.0"

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent
VENDOR_DIR = REPO_DIR / "vendor"
TEMPLATES_DIR = REPO_DIR / "templates"
# Everything the server writes (sessions, the saved settings) lives under KIN_DATA_DIR — a mounted volume in a deployment,
# the working directory on a laptop.
DATA_DIR = Path(os.environ.get("KIN_DATA_DIR") or ".").resolve()
ENV_FILE = Path(os.environ.get("KIN_ENV_FILE") or (DATA_DIR / ".env"))


def load_dotenv(paths: tuple[Path, ...] = (ENV_FILE, Path(".env"), REPO_DIR / ".env")) -> list[str]:
    """Load KEY=VALUE lines from a .env file without overriding variables already set. Returns the keys loaded."""
    loaded: list[str] = []
    for p in paths:
        try:
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:].lstrip()
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
                    loaded.append(k)
            break
        except OSError:
            continue
    return loaded


load_dotenv()
