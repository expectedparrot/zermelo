"""Register immutable native EDSL AgentLists and preserve their original bytes."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from .fielding import edsl_imports, load_agents
from .store import ZermeloError, digest


def registered_path(store, state):
    registration = state.get("ranker_list")
    if registration is None:
        return None
    path = store.root / registration["path"]
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != registration["sha256"]:
        raise ZermeloError("rankers_changed", "Registered AgentList is missing or changed; restore its preserved snapshot")
    return path


def add_rankers(store, state, connection, path):
    path = Path(path)
    if path.suffix.lower() != ".ep":
        raise ZermeloError("invalid_rankers", "Rankers must be a native EDSL AgentList .ep file")
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    incoming = load_agents(path)
    current_path = registered_path(store, state)
    current = list(load_agents(current_path)) if current_path else []
    by_id = {agent.traits["elo_judge_id"]: agent for agent in current}
    added, duplicates = [], []
    for agent in incoming:
        key = agent.traits["elo_judge_id"]
        if key in by_id:
            if digest(by_id[key].to_dict(add_edsl_version=False)) != digest(agent.to_dict(add_edsl_version=False)):
                raise ZermeloError("conflicting_ranker", f"Ranker {key} already has a different definition; use a new ID")
            duplicates.append(key)
        else:
            by_id[key] = agent
            added.append(key)
    if added:
        edsl = edsl_imports()
        combined = edsl.AgentList([by_id[key] for key in sorted(by_id)])
        definition_hash = digest(combined.to_dict())
        parent = store.root / "rankers"
        parent.mkdir(parents=True, exist_ok=True)
        output = parent / definition_hash
        if output.exists():
            raise ZermeloError("already_exists", f"Refusing to replace ranker snapshot: {output}")
        with tempfile.TemporaryDirectory(prefix=".building-", dir=parent) as temp:
            staging = Path(temp)
            snapshot = staging / "agent_list.ep"
            combined.git.save(snapshot, message="Register Zermelo rankers")
            loaded = edsl.AgentList.git.load(snapshot)
            if digest(loaded.to_dict()) != definition_hash:
                raise ZermeloError("artifact_verification_failed", "AgentList failed native save/load verification")
            snapshot_bytes = snapshot.read_bytes()
            snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
            staging.rename(output)
        registration = {"path": str((output / "agent_list.ep").relative_to(store.root)),
                        "sha256": snapshot_hash, "definition_hash": definition_hash, "ids": sorted(by_id)}
        state["ranker_list"] = registration
        connection.execute("INSERT OR IGNORE INTO sources VALUES (?, ?, ?)",
                           (snapshot_hash, "registered-agent_list.ep", snapshot_bytes))
    connection.execute("INSERT OR IGNORE INTO sources VALUES (?, ?, ?)", (source_hash, path.name, raw))
    source = {"source_path": str(path.resolve()), "source_sha256": source_hash,
              "added": added, "duplicates": duplicates, "snapshot": state["ranker_list"]}
    state.setdefault("ranker_sources", []).append(source)
    return {"added": len(added), "duplicates": len(duplicates), "total": len(by_id),
            "ranker_ids": sorted(by_id), "agent_list": str(store.root / state["ranker_list"]["path"]),
            "source_sha256": source_hash, "snapshot_sha256": state["ranker_list"]["sha256"]}
