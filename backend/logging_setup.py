"""UTF-8 log stream that cannot crash trading threads on Windows consoles."""

from __future__ import annotations

import io
from pathlib import Path


class TeeLogger:
    def __init__(self, log_path: Path, terminal=None):
        self.log_file = log_path.open("a", encoding="utf-8", errors="replace", buffering=1)
        self.terminal = terminal

    def write(self, text):
        value = str(text)
        try:
            self.log_file.write(value)
        except Exception:
            pass
        if self.terminal is not None:
            try:
                self.terminal.write(value)
            except (UnicodeEncodeError, UnicodeError):
                encoding = getattr(self.terminal, "encoding", None) or "utf-8"
                safe = value.encode(encoding, errors="replace").decode(encoding, errors="replace")
                try:
                    self.terminal.write(safe)
                except Exception:
                    pass
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


def read_log(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
