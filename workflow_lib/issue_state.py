"""SQLite checkpoints plus process locks; unknown writes require reconciliation."""

import fcntl
import hashlib
import json
import sqlite3
from pathlib import Path


class Cancelled(RuntimeError):
    pass


class Busy(RuntimeError):
    pass


class State:
    def __init__(self, path, key, inputs):
        self.path = Path(path)
        self.key = key
        self.inputs = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
        self.connection = None
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError("state path cannot be a symlink")
        lock_path = self.path.parent / (hashlib.sha256(self.key.encode()).hexdigest() + ".lock")
        self.handle = lock_path.open("a")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.handle.close()
            raise Busy("one active run per identity") from error
        self.connection = sqlite3.connect(self.path, timeout=10)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS runs(key TEXT PRIMARY KEY,inputs TEXT NOT NULL,status TEXT NOT NULL,cancelled INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS steps(run_key TEXT NOT NULL,name TEXT NOT NULL,status TEXT NOT NULL,value TEXT,PRIMARY KEY(run_key,name));
        """)
        row = self.connection.execute("SELECT inputs FROM runs WHERE key=?", (self.key,)).fetchone()
        if row and row[0] != self.inputs:
            self.__exit__(None, None, None)
            raise ValueError("run input/policy digest changed; use new explicit identity")
        self.connection.execute(
            "INSERT OR IGNORE INTO runs(key,inputs,status) VALUES(?,?,'NEW')",
            (self.key, self.inputs),
        )
        self.connection.commit()
        return self

    def __exit__(self, kind=None, error=None, traceback=None):
        if self.connection and error is not None:
            status = (
                "CANCELLED"
                if isinstance(error, Cancelled)
                else "HUMAN_REQUIRED"
                if type(error).__name__ == "BudgetExceeded"
                else "BLOCKED_ENVIRONMENT"
                if isinstance(error, OSError) or type(error).__module__.startswith("cao_workflow")
                else "BLOCKED_SPEC"
                if "BLOCKED_SPEC" in str(error)
                else "FAILED"
            )
            self.set_status(status)
        if self.connection:
            self.connection.close()
        if self.handle:
            self.handle.close()

    def check(self):
        if self.connection.execute(
            "SELECT cancelled FROM runs WHERE key=?", (self.key,)
        ).fetchone()[0]:
            raise Cancelled("operator cancelled run")

    def set_status(self, status):
        self.connection.execute("UPDATE runs SET status=? WHERE key=?", (status, self.key))
        self.connection.commit()

    def get(self, name):
        row = self.connection.execute(
            "SELECT status,value FROM steps WHERE run_key=? AND name=?", (self.key, name)
        ).fetchone()
        return json.loads(row[1]) if row and row[0] == "DONE" else None

    def put(self, name, value):
        encoded = json.dumps(value, sort_keys=True)
        self.connection.execute(
            "INSERT OR REPLACE INTO steps VALUES(?,?,'DONE',?)", (self.key, name, encoded)
        )
        self.connection.commit()
        return value

    def once(self, name, perform, *, reconcile=None, replay_safe=False, cache_if=None):
        self.check()
        row = self.connection.execute(
            "SELECT status,value FROM steps WHERE run_key=? AND name=?", (self.key, name)
        ).fetchone()
        if row and row[0] == "DONE":
            return json.loads(row[1])
        if row:
            value = reconcile() if reconcile else None
            if value is not None:
                return self.put(name, value)
            if not replay_safe:
                raise ValueError("unknown completion: reconcile external state before retry")
        self.connection.execute(
            "INSERT OR REPLACE INTO steps VALUES(?,?,'STARTED',NULL)", (self.key, name)
        )
        self.connection.commit()
        value = perform()
        if cache_if is not None and not cache_if(value):
            self.connection.execute(
                "DELETE FROM steps WHERE run_key=? AND name=?", (self.key, name)
            )
            self.connection.commit()
            return value
        return self.put(name, value)

    @staticmethod
    def cancel(path, key):
        with sqlite3.connect(path) as connection:
            connection.execute(
                "UPDATE runs SET cancelled=1,status=? WHERE key=?", ("CANCELLED", key)
            )

    @staticmethod
    def status(path, key=None):
        with sqlite3.connect(path) as connection:
            connection.row_factory = sqlite3.Row
            query = "SELECT key,status,cancelled FROM runs"
            rows = connection.execute(
                query + (" WHERE key=?" if key else ""), (key,) if key else ()
            )
            return [dict(row) for row in rows]
