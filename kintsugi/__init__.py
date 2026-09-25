"""Kintsugi: photograph what broke, print what fits."""

from pathlib import Path

__version__ = "0.1.0"

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent
VENDOR_DIR = REPO_DIR / "vendor"
TEMPLATES_DIR = REPO_DIR / "templates"
