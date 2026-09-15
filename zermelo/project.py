"""Project selection through an explicit flag, environment, or workspace marker."""

from __future__ import annotations

import os
from pathlib import Path

from .store import ZermeloError, read_json

MARKER = ".zermelo-project"


def resolve_project(explicit=None, *, cwd=None):
    cwd = Path(cwd or Path.cwd()).resolve()
    if explicit is not None:
        return Path(explicit).expanduser().resolve(), "--project"
    if os.environ.get("ZERMELO_PROJECT"):
        return Path(os.environ["ZERMELO_PROJECT"]).expanduser().resolve(), "ZERMELO_PROJECT"
    for directory in (cwd, *cwd.parents):
        marker = directory / MARKER
        if marker.is_file():
            data = read_json(marker)
            if not isinstance(data, dict) or not isinstance(data.get("project"), str) or not data["project"].strip():
                raise ZermeloError("invalid_project_selection", f"Invalid project marker: {marker}")
            return (directory / data["project"]).resolve(), str(marker)
        if any((directory / name).is_file() for name in ("zermelo.sqlite3", "elo.sqlite3")):
            return directory, "containing project"
    return cwd, "current directory"
