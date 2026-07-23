"""UTF-8 log stream that cannot crash trading threads on Windows consoles."""

from __future__ import annotations

import io
from pathlib import Path


class TeeLogger:
    def __init__(self, log_path: Path, terminal=None):
        self.log_file = log_path.open("a", encoding="utf-8", errors="replace", buffering=1)
        self.terminal = terminal

    def _safe_terminal_write(self, value):
        if self.terminal is None:
            return
        try:
            self.terminal.write(value)
            return
        except Exception:
            pass
        # Any exception on the terminal: try replacing with '?', else give up silently.
        encoding = getattr(self.terminal, "encoding", None) or "utf-8"
        try:
            safe = value.encode(encoding, errors="replace").decode(encoding, errors="replace")
        except Exception:
            safe = value.encode("ascii", errors="replace").decode("ascii", errors="replace")
        try:
            self.terminal.write(safe)
        except Exception:
            pass

    def write(self, text):
        value = str(text)
        try:
            self.log_file.write(value)
        except Exception:
            pass
        self._safe_terminal_write(value)
        return len(value)

    def flush(self):
        try:
            self.log_file.flush()
        except Exception:
            pass
        if self.terminal is not None:
            try:
                self.terminal.flush()
            except Exception:
                pass

    def isatty(self):
        return bool(self.terminal and getattr(self.terminal, "isatty", lambda: False)())

    @property
    def encoding(self):
        return "utf-8"


def read_log(log_path: "Path | str", max_bytes: int = 5 * 1024 * 1024) -> str:
    """Return up to ``max_bytes`` of the most recent log content.

    Used by the dashboard to tail ``api.log``. Must tolerate missing files,
    partial writes and encoding errors so the trading threads are never blocked.
    """
    try:
        path = Path(log_path)
        if not path.exists():
            return ""
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                # Drop the partial first line.
                fh.readline()
            data = fh.read()
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""
