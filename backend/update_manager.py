"""Signed-by-hash online update checks for the Windows desktop build."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

import requests

from app_paths import DATA_DIR, ensure_data_dir


APP_VERSION = "1.3.1"
DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "paradise95271314/pm-ks-trader-releases/main/update.json"
)


def _version(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(value).lstrip("v").split(".")[:4])
    except Exception:
        return (0,)


def version_info() -> dict[str, str]:
    return {"version": APP_VERSION}


def get_manifest_url(config: dict[str, Any] | None = None) -> str:
    if os.environ.get("UPDATE_MANIFEST_URL", "").strip():
        return os.environ["UPDATE_MANIFEST_URL"].strip()
    configured = str((config or {}).get("update_manifest_url", "")).strip()
    return configured or DEFAULT_MANIFEST_URL


def check_update(manifest_url: str) -> dict[str, Any]:
    if not manifest_url:
        return {"configured": False, "current_version": APP_VERSION,
                "message": "尚未配置更新清单地址"}
    response = requests.get(manifest_url, timeout=15, headers={"User-Agent": "PM-KS-Trader"})
    response.raise_for_status()
    manifest = response.json()
    if not isinstance(manifest, dict) or not manifest.get("version") or not manifest.get("url"):
        raise ValueError("更新清单缺少version或url")
    latest = str(manifest["version"])
    return {"configured": True, "current_version": APP_VERSION, "latest_version": latest,
            "available": _version(latest) > _version(APP_VERSION),
            "url": str(manifest["url"]), "sha256": str(manifest.get("sha256", "")).lower(),
            "notes": str(manifest.get("notes", "")), "manifest_url": manifest_url}


def stage_update(info: dict[str, Any], process_id: int) -> dict[str, Any]:
    if not info.get("available") or not info.get("url"):
        return {"staged": False, "error": "当前没有可用更新"}
    expected = str(info.get("sha256", "")).lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        return {"staged": False, "error": "更新缺少有效SHA-256校验值"}
    ensure_data_dir()
    update_dir = DATA_DIR / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    installer = update_dir / ("PM-KS-Trader-Update-" + str(info["latest_version"]) + ".exe")
    with requests.get(info["url"], stream=True, timeout=60,
                      headers={"User-Agent": "PM-KS-Trader"}) as response:
        response.raise_for_status()
        with installer.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    output.write(chunk)
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    if digest != expected:
        installer.unlink(missing_ok=True)
        return {"staged": False, "error": "更新包SHA-256校验失败"}
    if sys.platform != "win32":
        return {"staged": True, "path": str(installer), "can_apply": False,
                "message": "已下载；只有Windows桌面程序可以自动安装"}

    script = update_dir / "apply_update.ps1"
    script.write_text(
        "$ErrorActionPreference='Stop'\n"
        f"$appPid={int(process_id)}\n"
        f"$installer='{str(installer).replace(chr(39), chr(39) + chr(39))}'\n"
        "while (Get-Process -Id $appPid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 300 }\n"
        "Start-Process -FilePath $installer -ArgumentList '/SILENT'\n"
        "Start-Sleep -Seconds 5\n"
        "Remove-Item -Force -ErrorAction SilentlyContinue $installer, $PSCommandPath\n",
        encoding="utf-8",
    )
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                      "-File", str(script)], creationflags=0x08000000)
    threading.Timer(1.0, lambda: os._exit(0)).start()
    return {"staged": True, "can_apply": True, "message": "更新已下载，程序即将退出并安装新版"}
