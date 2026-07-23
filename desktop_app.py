"""Windows desktop entry point for the Polymarket/Kalshi trading desk."""

from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

import certifi


ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
BACKEND = ROOT / "backend"
if not BACKEND.exists():
    BACKEND = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("ARB_BOT_DESKTOP", "1")
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

from app_paths import DATA_DIR  # noqa: E402
from credential_store import apply_credentials_to_environment  # noqa: E402


_mutex = None


def _single_instance() -> bool:
    global _mutex
    if sys.platform != "win32":
        return True
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\PolymarketKalshiTrader")
    return ctypes.windll.kernel32.GetLastError() != 183


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError("本机交易服务启动超时")


def main() -> int:
    if not _single_instance():
        ctypes.windll.user32.MessageBoxW(None, "程序已经在运行。", "PM-KS交易桌面", 0x40)
        return 0

    apply_credentials_to_environment()
    import uvicorn
    from api import app

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    config = uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="local-api", daemon=True)
    thread.start()
    _wait_for_server(url)

    import webview

    window = webview.create_window(
        "PM-KS 交易桌面",
        url,
        width=1480,
        height=920,
        min_size=(1180, 720),
        background_color="#030712",
    )

    def _shutdown() -> None:
        try:
            import auto_trade
            auto_trade.stop()
        finally:
            server.should_exit = True

    window.events.closed += _shutdown
    webview.start(private_mode=False, storage_path=str(DATA_DIR), debug=False)
    thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
