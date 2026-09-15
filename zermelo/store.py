"""Transactional project storage and immutable artifact helpers."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path


class ZermeloError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data):
    return hashlib.sha256(canonical(data).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_new(path, data, *, raw=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x") as handle:
            handle.write(data if raw else json.dumps(data, indent=2, allow_nan=False) + "\n")
    except FileExistsError as exc:
        raise ZermeloError("already_exists", f"Refusing to overwrite {path}") from exc


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", value):
        raise ZermeloError("invalid_id", "IDs must start with a letter and contain at most 80 letters, digits, _ or -")
    return value


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ZermeloError("invalid_input", f"{label} must be a nonempty string")
    return value


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        current = self.root / "zermelo.sqlite3"
        legacy = self.root / "elo.sqlite3"
        if current.exists() and legacy.exists():
            raise ZermeloError("ambiguous_project", "Both zermelo.sqlite3 and elo.sqlite3 exist; select one project explicitly")
        self.path = legacy if legacy.exists() else current

    def initialize(self, criterion):
        nonempty(criterion, "criterion")
        self.root.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidentally initializing over another project.
        try:
            self.path.touch(exist_ok=False)
        except FileExistsError as exc:
            raise ZermeloError("already_exists", f"Project already exists: {self.root}") from exc
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE state (id INTEGER PRIMARY KEY CHECK (id=1), data TEXT NOT NULL);
                CREATE TABLE events (id INTEGER PRIMARY KEY, created TEXT, action TEXT, state_hash TEXT);
                CREATE TABLE sources (sha256 TEXT PRIMARY KEY, filename TEXT, content BLOB NOT NULL);
            """)
            state = {"schema_version": 1, "criterion": criterion, "entrants": [], "batches": {}, "ballots": {}}
            connection.execute("INSERT INTO state VALUES (1, ?)", (canonical(state),))
        return state

    def connect(self):
        if not self.path.is_file():
            raise ZermeloError("not_initialized", f"Initialize a project first: {self.root}")
        return sqlite3.connect(self.path, timeout=30)

    def load(self):
        with closing(self.connect()) as connection:
            state = json.loads(connection.execute("SELECT data FROM state WHERE id=1").fetchone()[0])
        if state.get("schema_version") != 1:
            raise ZermeloError("unsupported_schema", "Unsupported project schema")
        return state

    @contextmanager
    def update(self, action):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = json.loads(connection.execute("SELECT data FROM state WHERE id=1").fetchone()[0])
            if state.get("schema_version") != 1:
                raise ZermeloError("unsupported_schema", "Unsupported project schema")
            yield state, connection
            connection.execute("UPDATE state SET data=? WHERE id=1", (canonical(state),))
            connection.execute("INSERT INTO events(created, action, state_hash) VALUES (?, ?, ?)",
                               (datetime.now(timezone.utc).isoformat(), action, digest(state)))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()


def register_entrants(state, rows):
    if not isinstance(rows, list) or not rows:
        raise ZermeloError("invalid_entrants", "Supply a nonempty list of entrants")
    existing = {e["id"] for e in state["entrants"]}
    validated = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"id", "name", "description"}:
            raise ZermeloError("invalid_entrants", "Each entrant has id, name, and optional description fields")
        entrant_id = identifier(row.get("id"))
        if entrant_id in existing:
            raise ZermeloError("duplicate_entrant", f"Entrant already registered or repeated: {entrant_id}")
        name = nonempty(row.get("name"), "entrant name")
        description = row.get("description", "")
        if not isinstance(description, str):
            raise ZermeloError("invalid_entrants", "Entrant description must be a string")
        validated.append({"id": entrant_id, "name": name, "description": description})
        existing.add(entrant_id)
    state["entrants"].extend(validated)
    return {"added": len(validated), "total": len(state["entrants"])}
