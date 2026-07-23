"""Encrypted local credential storage.

Windows uses DPAPI, which binds ciphertext to the current Windows account.
Development platforms use a local Fernet key with owner-only permissions.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app_paths import CREDENTIAL_KEY_FILE, CREDENTIALS_FILE, KALSHI_KEY_FILE, ensure_data_dir


ENV_MAP = {
    "polymarket_private_key": "POLYMARKET_PRIVATE_KEY",
    "polymarket_funder": "POLYMARKET_FUNDER",
    "polymarket_signature_type": "POLYMARKET_SIGNATURE_TYPE",
    "kalshi_api_key_id": "KALSHI_API_KEY_ID",
}
SECRET_FIELDS = {"polymarket_private_key", "kalshi_private_key_pem"}


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_DataBlob, Any]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _dpapi_encrypt(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "PM-KS Trader", None, None, None, 0, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)
        del source_buffer


def _dpapi_decrypt(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)
        del source_buffer


def _fallback_fernet() -> Fernet:
    ensure_data_dir()
    if CREDENTIAL_KEY_FILE.exists():
        key = CREDENTIAL_KEY_FILE.read_bytes()
    else:
        key = Fernet.generate_key()
        CREDENTIAL_KEY_FILE.write_bytes(key)
        try:
            CREDENTIAL_KEY_FILE.chmod(0o600)
        except OSError:
            pass
    return Fernet(key)


def _encrypt(data: bytes) -> bytes:
    if sys.platform == "win32":
        return b"DPAPI1\n" + base64.b64encode(_dpapi_encrypt(data))
    return b"FERNET1\n" + _fallback_fernet().encrypt(data)


def _decrypt(data: bytes) -> bytes:
    scheme, payload = data.split(b"\n", 1)
    if scheme == b"DPAPI1":
        return _dpapi_decrypt(base64.b64decode(payload))
    if scheme == b"FERNET1":
        return _fallback_fernet().decrypt(payload)
    raise ValueError("Unsupported credential storage format")


def load_credentials() -> dict[str, str]:
    if not CREDENTIALS_FILE.exists():
        return {}
    try:
        payload = json.loads(_decrypt(CREDENTIALS_FILE.read_bytes()).decode("utf-8"))
        return {str(k): str(v) for k, v in payload.items() if v is not None}
    except Exception as exc:
        raise RuntimeError("本机API凭据无法解密，请重新配置") from exc


def save_credentials(updates: dict[str, Any]) -> dict[str, str]:
    ensure_data_dir()
    current = load_credentials()
    for key, value in updates.items():
        if key not in ENV_MAP and key != "kalshi_private_key_pem":
            continue
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            current[key] = normalized
    CREDENTIALS_FILE.write_bytes(_encrypt(json.dumps(current).encode("utf-8")))
    try:
        CREDENTIALS_FILE.chmod(0o600)
    except OSError:
        pass
    apply_credentials_to_environment(current)
    return current


def create_transfer_bundle(credentials: dict[str, Any], password: str) -> bytes:
    """Create a password-encrypted, cross-platform credential transfer bundle."""
    password_bytes = str(password or "").encode("utf-8")
    if len(password_bytes) < 12:
        raise ValueError("备份密码至少需要12个字符")
    salt = os.urandom(16)
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password_bytes)
    fernet_key = base64.urlsafe_b64encode(key)
    allowed = {key: str(value) for key, value in credentials.items()
               if (key in ENV_MAP or key == "kalshi_private_key_pem") and value}
    payload = Fernet(fernet_key).encrypt(json.dumps(allowed).encode("utf-8"))
    return b"PMKSBACKUP1\n" + base64.b64encode(salt) + b"\n" + payload


def import_transfer_bundle(bundle: bytes | str, password: str) -> dict[str, str]:
    """Decrypt a transfer bundle and save it using this machine's native encryption."""
    raw = bundle.encode("utf-8") if isinstance(bundle, str) else bundle
    try:
        marker, encoded_salt, payload = raw.strip().split(b"\n", 2)
        if marker != b"PMKSBACKUP1":
            raise ValueError("wrong marker")
        salt = base64.b64decode(encoded_salt)
        key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(
            str(password or "").encode("utf-8"))
        decoded = Fernet(base64.urlsafe_b64encode(key)).decrypt(payload)
        credentials = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise ValueError("备份文件或密码不正确") from exc
    if not isinstance(credentials, dict):
        raise ValueError("备份文件格式不正确")
    return save_credentials(credentials)


def clear_credentials() -> None:
    for path in (CREDENTIALS_FILE, KALSHI_KEY_FILE):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    for env_name in ENV_MAP.values():
        os.environ.pop(env_name, None)


def apply_credentials_to_environment(credentials: dict[str, str] | None = None) -> dict[str, str]:
    credentials = credentials if credentials is not None else load_credentials()
    for field, env_name in ENV_MAP.items():
        value = credentials.get(field, "").strip()
        if value:
            os.environ[env_name] = value
    pem = credentials.get("kalshi_private_key_pem", "").replace("\\n", "\n").strip()
    if pem:
        KALSHI_KEY_FILE.write_text(pem + "\n", encoding="utf-8")
        try:
            KALSHI_KEY_FILE.chmod(0o600)
        except OSError:
            pass
        os.environ["KALSHI_PRIVATE_KEY_FILE"] = str(KALSHI_KEY_FILE)
    return credentials


def credential_status() -> dict[str, Any]:
    credentials = load_credentials()
    funder = credentials.get("polymarket_funder", "")
    kalshi_id = credentials.get("kalshi_api_key_id", "")
    return {
        "polymarket_configured": bool(credentials.get("polymarket_private_key") and funder),
        "kalshi_configured": bool(credentials.get("kalshi_private_key_pem") and kalshi_id),
        "funder_hint": (funder[:6] + "..." + funder[-4:]) if len(funder) >= 12 else "",
        "kalshi_key_hint": (kalshi_id[:5] + "..." + kalshi_id[-4:]) if len(kalshi_id) >= 10 else "",
        "signature_type": credentials.get("polymarket_signature_type", "0"),
    }
