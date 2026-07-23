"""Keep the last position snapshot confirmed by both exchanges."""

from copy import deepcopy
from threading import Lock


class TrustedPositionSnapshot:
    def __init__(self):
        self._positions = []
        self._lock = Lock()

    def store(self, positions):
        with self._lock:
            self._positions = deepcopy(positions)

    def resolve(self, positions, complete):
        if complete:
            self.store(positions)
            return deepcopy(positions), False
        with self._lock:
            return deepcopy(self._positions), True
