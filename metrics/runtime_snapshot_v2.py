import threading
from pathlib import Path
from datetime import datetime
import json


class _SnapshotContext(threading.local):
    def __init__(self):
        self.snapshot = None


_ctx = _SnapshotContext()


class RuntimeSnapshot:

    def __init__(self):
        self._data = {}

    def set(self, module: str, key: str, value):
        if module not in self._data:
            self._data[module] = {}

        self._data[module][key] = value

    def get(self, module: str, key: str, default=None):
        return self._data.get(module, {}).get(key, default)

    def dump(self):
        return self._data


# -------- lifecycle --------

def start_snapshot():
    _ctx.snapshot = RuntimeSnapshot()


def get_snapshot() -> RuntimeSnapshot:
    if _ctx.snapshot is None:
        raise RuntimeError("Snapshot not started")
    return _ctx.snapshot


def end_snapshot() -> RuntimeSnapshot:
    snap = _ctx.snapshot
    _ctx.snapshot = None

    if snap is None:
        raise RuntimeError("Snapshot not started")

    return snap


# -------- writer --------

def write_snapshot(snapshot: RuntimeSnapshot, state_dir: str, config_tag: str):

    if not state_dir:
        raise RuntimeError("state_dir is not set")

    data = snapshot.dump()
    if not data:
        return

    state_file = Path(state_dir) / f"{config_tag}.state"

    now = datetime.now().strftime("%H:%M:%S")

    state = {
        "last_update": now,
        "runtime": data
    }

    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
    except Exception as e:
        raise RuntimeError(f"Snapshot write failed: {e}")