"""Seeded, connected designs that never ask a judge to rank the whole pool."""

from __future__ import annotations

import random
from collections import Counter
from itertools import combinations

from .store import ZermeloError, digest, evidence_hash, identifier


def components(entrant_ids, pairs):
    parent = {key: key for key in entrant_ids}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for a, b in pairs:
        parent[find(a)] = find(b)
    groups = {}
    for key in sorted(parent):
        groups.setdefault(find(key), []).append(key)
    return sorted(groups.values(), key=lambda group: group[0])


def make_design(state, batch_id, chunk_size=5, rounds=3, seed=0):
    identifier(batch_id)
    if batch_id in state["batches"]:
        raise ZermeloError("duplicate_batch", f"Batch already exists: {batch_id}")
    entrants = sorted(state["entrants"], key=lambda row: row["id"])
    if len(entrants) < 2:
        raise ZermeloError("too_few_entrants", "Register at least two entrants")
    if type(chunk_size) is not int or chunk_size < 2 or type(rounds) is not int or rounds < 1:
        raise ZermeloError("invalid_design", "chunk_size must be at least 2 and rounds at least 1")
    size = min(chunk_size, len(entrants))
    rng = random.Random(seed)
    tasks = []
    # Each round is a chain of full groups sharing an entrant. The last group
    # wraps to the beginning if needed. All entrants are covered in every round.
    for round_index in range(rounds):
        order = [e["id"] for e in entrants]
        rng.shuffle(order)
        start = 0
        while True:
            selected = [order[index % len(order)] for index in range(start, start + size)]
            rng.shuffle(selected)
            tasks.append({"id": f"{batch_id}-t{len(tasks) + 1:06d}", "round": round_index + 1,
                          "entrants": selected})
            if start + size >= len(order):
                break
            start += size - 1
    appearances = Counter(e for task in tasks for e in task["entrants"])
    pairs = Counter(tuple(sorted(pair)) for task in tasks for pair in combinations(task["entrants"], 2))
    design = {"schema_version": 1, "batch_id": batch_id, "criterion": state["criterion"],
              "entrants": entrants, "chunk_size": size, "requested_chunk_size": chunk_size,
              "rounds": rounds, "seed": seed, "tasks": tasks,
              "coverage": {"appearances": dict(sorted(appearances.items())), "unique_pairs": len(pairs),
                           "possible_pairs": len(entrants) * (len(entrants) - 1) // 2,
                           "components": components(appearances, pairs)}}
    design["design_hash"] = digest(design)
    return design


def adaptive_design(state, batch_id, chunk_size=5, rounds=1, seed=0, *, strategy="neighborhood",
                    bridge_fraction=.1, task_count=None, only_new=False):
    """Plan a connected wave, then spend optional tasks near uncertain ranks.

    Mandatory coverage/bridging is explicit and counted before optional tasks.
    Local information is a scheduling proxy, not a posterior variance.
    """
    import math

    from .diagnostics import ranking_ballots
    from .scoring import score

    design = make_design(state, batch_id, chunk_size, rounds, seed)
    if strategy not in {"random", "neighborhood"} or not math.isfinite(bridge_fraction) or not 0 <= bridge_fraction <= 1:
        raise ZermeloError("invalid_design", "Choose random or neighborhood and a bridge fraction in [0, 1]")
    ids = [e["id"] for e in design["entrants"]]
    ballots = ranking_ballots(state)
    seen = {key for row in ballots for key in row["ranking"]}
    new = sorted(set(ids) - seen)
    if only_new and not new:
        raise ZermeloError("no_new_entrants", "All entrants have ranking ballots; omit --only-new to refine the pool")
    ordered = ids[:]
    fit = None
    if ballots and (strategy == "neighborhood" or only_new):
        fit = score([e for e in state["entrants"] if e["id"] in seen], ballots, method="pl")
        ordered = [row["id"] for row in fit["rankings"]] + new
    k = design["chunk_size"]
    rng = random.Random(seed)
    selected = []
    if only_new and seen:
        anchors = [key for key in ordered if key in seen]
        for r in range(rounds):
            for key in new:
                # Evenly spread anchors across the current ranking; rotate across rounds.
                count = min(k - 1, len(anchors))
                chosen = [anchors[(int(i * len(anchors) / count) + r) % len(anchors)] for i in range(count)]
                remainder = [other for other in new if other != key]
                rng.shuffle(remainder)
                selected.append((r + 1, [key] + chosen + remainder[:k - 1 - count], "new-with-anchors"))
    elif strategy == "neighborhood" and fit:
        # A full chain avoids disconnecting tiers even when random bridges are disabled.
        for r in range(rounds):
            # Shift block boundaries on later rounds, retaining sorted neighborhoods.
            order = ordered[r % len(ordered):] + ordered[:r % len(ordered)]
            start = 0
            while True:
                selected.append((r + 1, [order[i % len(order)] for i in range(start, start + k)], "coverage-chain"))
                if start + k >= len(order):
                    break
                start += k - 1
    else:
        selected = [(t["round"], t["entrants"][:], "coverage-chain") for t in design["tasks"]]
    minimum = len(selected)
    if task_count is not None and (type(task_count) is not int or task_count < minimum):
        raise ZermeloError("insufficient_tasks", f"This wave needs at least {minimum} tasks for requested coverage")
    total = task_count if task_count is not None else minimum + math.ceil(minimum * bridge_fraction)
    remaining = total - minimum
    random_count = min(remaining, math.ceil(total * bridge_fraction))
    # Diagonal pairwise logistic information (unit ballot exposure) is a cheap
    # proxy. It ignores covariance and is never exposed as a fitted sigma.
    information = Counter()
    if fit:
        theta = {row["id"]: row["strength"] for row in fit["rankings"]}
        for row in ballots:
            for a, b in combinations(row["ranking"], 2):
                d = max(-700, min(700, theta[a] - theta[b]))
                p = 1 / (1 + math.exp(-d))
                amount = p * (1 - p) / (len(row["ranking"]) - 1)
                information[a] += amount
                information[b] += amount
    centers = new if only_new else ordered
    center_weights = [1 / (1 + information[key]) for key in centers]
    positions = {key: i for i, key in enumerate(ordered)}
    for i in range(remaining):
        center = rng.choices(centers, weights=center_weights, k=1)[0]
        if i < random_count or not fit or strategy == "random":
            if only_new:
                others = [key for key in ids if key != center]
                group = [center] + rng.sample(others, k - 1)
            else:
                group = rng.sample(ids, k)
            kind = "random-bridge"
        else:
            start = max(0, min(len(ordered) - k, positions[center] - rng.randrange(k)))
            group = ordered[start:start + k]
            kind = "neighborhood"
        selected.append((rounds + 1, group, kind))
    tasks = []
    for r, group, kind in selected:
        rng.shuffle(group)
        tasks.append({"id": f"{batch_id}-t{len(tasks) + 1:06d}", "round": r,
                      "entrants": group, "selection": kind})
    appearances = Counter(key for task in tasks for key in task["entrants"])
    pairs = {tuple(sorted(pair)) for task in tasks for pair in combinations(task["entrants"], 2)}
    observed = {tuple(sorted(pair)) for row in ballots for pair in combinations(row["ranking"], 2)}
    connected = components(ids, pairs | observed)
    if len(connected) != 1:
        raise ZermeloError("disconnected_design", "Observed comparisons plus this wave must connect every entrant")
    design.update({"tasks": tasks, "purpose": "ranking", "selection": {
        "strategy": strategy, "only_new": only_new, "new_entrants": new,
        "bridge_fraction_requested": bridge_fraction, "random_bridge_tasks": random_count,
        "mandatory_tasks": minimum, "total_tasks": total, "base_input_hash": evidence_hash(state),
        "fit": "pl" if fit else None, "regularization": 1.0 if fit else None,
        "priority": "inverse regularized diagonal pairwise information; scheduling proxy, not posterior variance"},
        "coverage": {"appearances": dict(sorted(appearances.items())), "unique_pairs": len(pairs),
                     "possible_pairs": len(ids) * (len(ids) - 1) // 2,
                     "components": components(ids, pairs), "combined_observed_planned_components": connected}})
    design.pop("design_hash")
    design["design_hash"] = digest(design)
    return design
