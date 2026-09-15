"""Information ceilings and block perturbation diagnostics, without accuracy promises."""

from __future__ import annotations

import math
from collections import defaultdict
from itertools import combinations

import numpy as np
from scipy.stats import kendalltau

from .design import components
from .scoring import score
from .store import ZermeloError, digest


def ranking_ballots(state):
    return [row for row in state["ballots"].values()
            if state["batches"][row["batch_id"]]["design"].get("purpose", "ranking") == "ranking"]


def observed_graph(state):
    ids = [e["id"] for e in state["entrants"]]
    ballots = ranking_ballots(state)
    pairs = {tuple(sorted(pair)) for row in ballots for pair in combinations(row["ranking"], 2)}
    seen = {key for row in ballots for key in row["ranking"]}
    return {"components": components(ids, pairs), "unique_pairs": len(pairs),
            "unobserved": sorted(set(ids) - seen), "ranking_ballots": len(ballots)}


def information_budget(n, k, calls=0, cost_per_call=None, budget=None):
    if type(n) is not int or n < 2 or type(k) is not int or k < 2 or k > n:
        raise ZermeloError("invalid_budget", "Require 2 <= chunk size <= entrant count")
    if type(calls) is not int or calls < 0:
        raise ZermeloError("invalid_budget", "Calls must be a nonnegative integer")
    for label, value in [("cost_per_call", cost_per_call), ("budget", budget)]:
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ZermeloError("invalid_budget", f"{label} must be finite and nonnegative")
    if budget is not None and (cost_per_call is None or cost_per_call <= 0):
        raise ZermeloError("invalid_budget", "A dollar budget requires a positive cost per call")
    bits = math.lgamma(n + 1) / math.log(2)
    per_call = math.lgamma(k + 1) / math.log(2)
    return {"entrants": n, "chunk_size": k, "exact_sort_bits": bits,
            "max_bits_per_noiseless_call": per_call, "exact_sort_call_lower_bound": math.ceil(bits / per_call),
            "calls": calls, "transcript_capacity_ceiling_bits": calls * per_call,
            "estimated_cost": None if cost_per_call is None else calls * cost_per_call,
            "cost_per_call_assumption": cost_per_call, "budget": budget,
            "affordable_calls": None if budget is None else math.floor(budget / cost_per_call),
            "limitations": ["Decision-tree lower bound for an arbitrary noiseless total order, not a sufficient sample size.",
                            "Transcript capacity is not information learned: overlap, noise and repeated answers reduce it.",
                            "No conversion to rank tolerance is identified without assumptions about truth and noise.",
                            "Cost is user-supplied, excludes retries, and is not a service spending cap."]}


def perturbation(entrants, ballots, fitted, *, draws=200, cluster="task", seed=0, regularization=1.0,
                 weighting="entrant"):
    """Positive, normalized exponential weights preserve observed graph support.

    All answers for a task move together (or all answers from a judge). These
    conditional multiplier-bootstrap ranges are sensitivity diagnostics, not
    calibrated posterior probabilities or independent-pair confidence intervals.
    """
    if type(draws) is not int or draws < 20 or cluster not in {"task", "judge"}:
        raise ZermeloError("invalid_bootstrap", "Use at least 20 draws and cluster task or judge")
    if fitted["method"] not in {"pl", "bt"}:
        raise ZermeloError("invalid_bootstrap", "Bootstrap supports likelihood fits pl and bt, not online Elo")
    ballots = sorted(ballots, key=lambda row: row["key"])
    blocks = defaultdict(list)
    for row in ballots:
        key = (row["batch_id"], row["task_id"]) if cluster == "task" else row["judge_id"]
        blocks[key].append(row["key"])
    if len(blocks) < 2:
        raise ZermeloError("too_few_clusters", "At least two resampling clusters are required")
    ordered = [row["id"] for row in fitted["rankings"]]
    rng = np.random.default_rng(seed)
    strengths, ranks = [], []
    for _ in range(draws):
        weights = rng.exponential(size=len(blocks))
        weights = np.maximum(weights, np.finfo(float).tiny)
        weights *= len(blocks) / weights.sum()
        multipliers = {key: float(w) for keys, w in zip(blocks.values(), weights) for key in keys}
        sample = score(entrants, ballots, method=fitted["method"], regularization=regularization,
                       weighting=weighting, ballot_weights=multipliers)
        by_id = {row["id"]: row for row in sample["rankings"]}
        strengths.append([by_id[key]["strength"] for key in ordered])
        ranks.append([by_id[key]["rank"] for key in ordered])
    strengths, ranks = np.array(strengths), np.array(ranks)
    deviations = np.max(np.abs(ranks - np.array([row["rank"] for row in fitted["rankings"]])), axis=1)
    adjacent = (strengths[:, :-1] <= strengths[:, 1:]).mean(axis=0)
    entries = {}
    for i, key in enumerate(ordered):
        entries[key] = {"strength_sd": float(strengths[:, i].std(ddof=1)),
                        "rank_p025": float(np.quantile(ranks[:, i], .025)),
                        "rank_p975": float(np.quantile(ranks[:, i], .975))}
    return {"method": "normalized exponential cluster multiplier bootstrap", "cluster": cluster,
            "clusters": len(blocks), "draws": draws, "seed": seed, "entrants": entries,
            "adjacent_reversal_frequencies": [
                {"higher": a, "lower": b, "frequency": float(p)}
                for a, b, p in zip(ordered, ordered[1:], adjacent)],
            "expected_adjacent_reversals_under_perturbation": float(adjacent.sum()),
            "max_rank_movement_p95": float(np.quantile(deviations, .95)),
            "limitations": ["Conditional on this design, fitted model, regularization and chosen clustering.",
                            "Positive weights preserve connectivity; these are sensitivity ranges, not calibrated coverage guarantees.",
                            "Task clusters keep all judges and iterations together; judge clusters keep all of a judge's answers together.",
                            "Neither clustering captures every dependence in an adaptive design or establishes accuracy."]}


def assess_snapshot(state, previous, current, tolerance=.02):
    if not math.isfinite(tolerance) or not 0 <= tolerance <= 1:
        raise ZermeloError("invalid_tolerance", "Tolerance must be a fraction from zero to one")
    if previous.get("criterion") != state["criterion"]:
        raise ZermeloError("incompatible_snapshot", "Snapshots must use the same criterion")
    old = {r["id"]: r for r in previous["rankings"]}
    new = {r["id"]: r for r in current["rankings"]}
    if set(old) != set(new) or previous.get("settings") != current.get("settings"):
        raise ZermeloError("incompatible_snapshot", "Snapshots must have the same entrant IDs and fit settings")
    old_panels = {b.get("panel_hash") for b in previous.get("batch_settings", [])}
    new_panels = {b.get("panel_hash") for b in current.get("batch_settings", [])}
    if old_panels != new_panels:
        raise ZermeloError("incompatible_snapshot", "Snapshots must use the same model and judge definitions")
    old_cells, new_cells = previous.get("ballot_hashes"), current.get("ballot_hashes")
    if not old_cells or not new_cells or any(new_cells.get(k) != v for k, v in old_cells.items()):
        raise ZermeloError("incompatible_snapshot", "Previous ballots must be an unchanged subset of current ballots")
    added = len(new_cells) - len(old_cells)
    if added <= 0:
        raise ZermeloError("no_new_results", "Import new ranking ballots before assessing stability")
    if not current["complete"] or not previous["complete"]:
        raise ZermeloError("incomplete_results", "Stability assessment requires complete snapshots")
    ids = sorted(old)
    tau = float(kendalltau([old[k]["rank"] for k in ids], [new[k]["rank"] for k in ids]).statistic)
    movement = max(abs(old[k]["rank"] - new[k]["rank"]) for k in ids)
    uncertainty = current.get("uncertainty", {})
    spread = uncertainty.get("max_rank_movement_p95")
    threshold = tolerance * len(ids)
    return {"new_ballots": added, "kendall_tau": tau if math.isfinite(tau) else None,
            "max_rank_movement": movement, "tolerance_fraction": tolerance, "tolerance_positions": threshold,
            "stable_between_snapshots": movement <= threshold,
            "perturbation_within_tolerance": None if spread is None else spread <= threshold,
            "review_for_stopping": movement <= threshold and spread is not None and spread <= threshold,
            "previous_input_hash": previous.get("input_hash"), "current_input_hash": digest(state),
            "limitations": ["A diagnostic for reviewing whether to stop, not an accuracy guarantee or automated spending policy.",
                            "Repeated snapshots share data. Stability does not establish a correct ranking.",
                            "A tolerance of .02 means movement within .02 times the number of entrants, not error relative to truth."]}
