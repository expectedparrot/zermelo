"""Plan repeated, shuffled subsets and measure within-judge rank disagreement."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from itertools import combinations

from . import fielding
from .design import components, make_design
from .store import ZermeloError, digest, identifier


def kendall_distance(left, right):
    """Fraction of unordered pairs whose relative order differs (0..1)."""
    if len(left) < 2 or len(set(left)) != len(left) or set(left) != set(right) or len(left) != len(right):
        raise ZermeloError("invalid_ranking", "Kendall distance requires permutations of the same at least two IDs")
    positions = {key: i for i, key in enumerate(right)}
    return sum(positions[a] > positions[b] for a, b in combinations(left, 2)) / math.comb(len(left), 2)


def plan_calibration(state, calibration_id, sizes, *, sample=40, subsets=10, repeats=3, seed=0):
    identifier(calibration_id)
    if calibration_id in state.get("calibrations", {}):
        raise ZermeloError("duplicate_calibration", "Calibration ID already exists")
    if not sizes or len(set(sizes)) != len(sizes) or any(type(k) is not int or k < 2 for k in sizes):
        raise ZermeloError("invalid_calibration", "Supply distinct batch sizes of at least two")
    if any(type(x) is not int for x in (sample, subsets, repeats)) or sample < 2 or subsets < 2 or repeats < 2:
        raise ZermeloError("invalid_calibration", "Sample, subsets and repeats must each be at least two")
    ids = sorted(e["id"] for e in state["entrants"])
    if max(sizes) > min(sample, len(ids)):
        raise ZermeloError("invalid_calibration", "Every candidate size must fit in the sampled entrant pool")
    rng = random.Random(seed)
    pool = rng.sample(ids, min(sample, len(ids)))
    # Nested subsets make candidates share content without asserting that the
    # different list lengths have an identical comparison difficulty.
    panels = [rng.sample(pool, max(sizes)) for _ in range(subsets)]
    designs = []
    for k in sorted(sizes):
        batch_id = f"{calibration_id}-k{k}"
        design = make_design(state, batch_id, k, 1, seed)
        tasks = []
        for group, panel in enumerate(panels):
            for repeat in range(repeats):
                selected = panel[:k]
                rng.shuffle(selected)
                tasks.append({"id": f"{batch_id}-t{len(tasks) + 1:06d}", "round": repeat + 1,
                              "entrants": selected, "calibration_group": group, "replicate": repeat})
        appearances = Counter(key for task in tasks for key in task["entrants"])
        pairs = {tuple(sorted(pair)) for task in tasks for pair in combinations(task["entrants"], 2)}
        design.update({"purpose": "calibration", "calibration_id": calibration_id, "tasks": tasks,
                       "rounds": repeats, "coverage": {"appearances": dict(sorted(appearances.items())),
                       "unique_pairs": len(pairs), "possible_pairs": len(ids) * (len(ids) - 1) // 2,
                       "components": components(ids, pairs)}})
        design.pop("design_hash")
        design["design_hash"] = digest(design)
        designs.append(design)
    plan = {"id": calibration_id, "sample_ids": pool, "subsets": subsets, "repeats": repeats,
            "sizes": sorted(sizes), "seed": seed, "batch_ids": [d["batch_id"] for d in designs],
            "criterion": state["criterion"], "entrant_snapshot_hash": digest(state["entrants"]),
            "tasks_per_size_per_judge": subsets * repeats,
            "execution": "Export each batch with identical judges/model/settings; run each ep command externally.",
            "limitations": ["Repeated subsets estimate self-consistency, not error relative to truth.",
                            "Replicate markers and shuffled positions avoid identical cached prompts; independence is not guaranteed."]}
    for design in designs:
        state["batches"][design["batch_id"]] = {"design": design, "fielding": None, "imports": []}
    state.setdefault("calibrations", {})[calibration_id] = plan
    return plan


def analyze_calibration(state, calibration_id, *, max_disagreement=.1, costs=None, reference=None):
    if not math.isfinite(max_disagreement) or not 0 <= max_disagreement <= 1:
        raise ZermeloError("invalid_calibration", "Disagreement threshold must lie in [0, 1]")
    try:
        plan = state["calibrations"][calibration_id]
    except KeyError as exc:
        raise ZermeloError("unknown_calibration", "No calibration with this ID") from exc
    if costs is not None and (not isinstance(costs, dict) or set(costs) != {str(k) for k in plan["sizes"]}
                              or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                                     for v in costs.values())):
        raise ZermeloError("invalid_calibration", "Costs must map every candidate size to a positive dollar cost per call")
    if reference is not None:
        snapshot = state["batches"][plan["batch_ids"][0]]["design"]["entrants"]
        if (not isinstance(reference, list) or any(not isinstance(k, str) for k in reference)
                or len(reference) != len(snapshot) or set(reference) != {e["id"] for e in snapshot}):
            raise ZermeloError("invalid_reference", "Reference must rank every entrant in the calibration snapshot exactly once")
    settings = set()
    reports = []
    all_complete = True
    for batch_id in plan["batch_ids"]:
        batch = state["batches"][batch_id]
        manifest = batch["fielding"]
        coverage = fielding.coverage(state, batch_id)
        all_complete &= coverage["complete"]
        if manifest:
            settings.add(digest({key: manifest[key] for key in ("model", "judges", "iterations")}))
        tasks = {t["id"]: t for t in batch["design"]["tasks"]}
        groups = defaultdict(list)
        truth_distances = []
        for row in state["ballots"].values():
            if row["batch_id"] != batch_id:
                continue
            groups[tasks[row["task_id"]]["calibration_group"], row["judge_id"]].append(row["ranking"])
            if reference is not None:
                truth_distances.append(kendall_distance(row["ranking"], [key for key in reference if key in row["ranking"]]))
        distances = [sum(kendall_distance(a, b) for a, b in combinations(rows, 2)) / math.comb(len(rows), 2)
                     for rows in groups.values() if len(rows) >= 2]
        k = batch["design"]["chunk_size"]
        d = sum(distances) / len(distances) if distances else None
        gold = sum(truth_distances) / len(truth_distances) if truth_distances else None
        per_judge = {}
        for (_, judge), rows in groups.items():
            if len(rows) >= 2:
                per_judge.setdefault(judge, []).append(
                    sum(kendall_distance(a, b) for a, b in combinations(rows, 2)) / math.comb(len(rows), 2))
        reports.append({"batch_id": batch_id, "chunk_size": k, "coverage": coverage,
                        "subset_judge_groups": len(distances), "mean_kendall_disagreement": d,
                        "by_judge": {key: sum(ds) / len(ds) for key, ds in sorted(per_judge.items())},
                        "mean_reference_error": gold,
                        "cost_per_call": None if costs is None else costs[str(k)],
                        "eligible": coverage["complete"] and d is not None and d <= max_disagreement
                        and (reference is None or gold is not None and gold <= max_disagreement)})
    if len(settings) > 1:
        raise ZermeloError("calibration_settings_mismatch", "Candidate sizes must use identical model settings, judges and iterations")
    eligible = [r for r in reports if r["eligible"]] if all_complete else []
    # Outcome-alphabet capacity is a transparent tie-breaking heuristic, never
    # labeled measured information or a channel-capacity estimate.
    def utility(row):
        capacity = math.lgamma(row["chunk_size"] + 1) / math.log(2)
        return capacity / (row["cost_per_call"] or 1)
    best = max(eligible, key=utility) if eligible else None
    return {"calibration_id": calibration_id, "complete": all_complete, "candidates": reports,
            "max_disagreement": max_disagreement, "recommended_chunk_size": best["chunk_size"] if best else None,
            "recommendation_rule": "Among sizes below the disagreement (and optional reference-error) threshold, "
                                   "maximize log2(k!)/supplied cost; without costs choose the largest eligible size.",
            "cost_source": "user estimates, not service billing" if costs else "not supplied; per-call comparison only",
            "input_hash": digest(state), "plan": plan, "settings_hashes": sorted(settings),
            "costs": costs, "reference": reference,
            "source_hashes": sorted({row["source_sha256"] for row in state["ballots"].values()
                                     if row["batch_id"] in plan["batch_ids"]}),
            "limitations": ["Disagreement mixes repeat variability and display-order sensitivity; it is not accuracy.",
                            "Consistency can be perfect for a consistently wrong model. Reference truth must be justified externally.",
                            "Recommendations are screening heuristics, not optimal batch-size or useful-bits estimates.",
                            "Overlapping subsets and within-group pair distances are dependent; no independent-pair error bars.",
                            "Calibration ballots are excluded from production ranks and adaptive scheduling."]}
