"""Cross-platform application paths for server and desktop builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "PolymarketKalshiTrader"
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent


def _default_data_dir() -> Path:
    override = os.environ.get("ARB_BOT_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / APP_NAME


DATA_DIR = _default_data_dir()
CONFIG_FILE = DATA_DIR / "bot_config.json"
CREDENTIALS_FILE = DATA_DIR / "credentials.dat"
CREDENTIAL_KEY_FILE = DATA_DIR / "credentials.key"
KALSHI_KEY_FILE = DATA_DIR / "kalshi_key.pem"
LOG_FILE = DATA_DIR / "api.log"
HISTORY_FILE = DATA_DIR / "trade_history.json"
AUTO_STATUS_FILE = DATA_DIR / "auto_trade_enabled"
AUTO_STATE_FILE = DATA_DIR / "auto_trade_state.json"


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def bundled_frontend_dir() -> Path:
    """Locate static frontend files in development and PyInstaller builds."""
    frozen_root = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
    candidates = [
        frozen_root / "frontend_out",
        frozen_root / "frontend" / "out",
        PROJECT_DIR / "frontend" / "out",
    ]
    return next((path for path in candidates if path.exists()), candidates[-1])


ensure_data_dir()
