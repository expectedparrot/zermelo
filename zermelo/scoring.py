"""Whole-ranking Plackett–Luce, pairwise Bradley–Terry, and batch Elo."""

from __future__ import annotations

import math
from collections import Counter
from itertools import combinations

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logsumexp

from .design import components
from .store import ZermeloError


def score(entrants, ballots, *, method="bt", regularization=1.0, k_factor=32.0, weighting="entrant", ballot_weights=None):
    """Each strict ranking implies a win for every earlier/later pair.

    Default weight 1/(k-1) keeps an entrant's total exposure per ballot at one.
    This is a composite likelihood: implied wins within a ballot are dependent.
    """
    if method not in {"pl", "bt", "elo"} or weighting not in {"entrant", "pair"}:
        raise ZermeloError("invalid_method", "Use pl, bt or elo and entrant or pair weighting")
    if not math.isfinite(regularization) or regularization <= 0:
        raise ZermeloError("invalid_regularization", "Regularization must be finite and positive")
    if not math.isfinite(k_factor) or k_factor <= 0:
        raise ZermeloError("invalid_k_factor", "Elo K factor must be finite and positive")
    if not ballots:
        raise ZermeloError("no_results", "Import rankings before calculating scores")
    ids = sorted(e["id"] for e in entrants)
    index = {key: i for i, key in enumerate(ids)}
    wins, losses, appearances, weighted = Counter(), Counter(), Counter(), Counter()
    ballots = sorted(ballots, key=lambda row: row["key"])
    multipliers = ballot_weights or {}
    if any(not math.isfinite(w) or w <= 0 for w in multipliers.values()):
        raise ZermeloError("invalid_weights", "Ballot multipliers must be finite and positive")
    for ballot in ballots:
        ranking = ballot["ranking"]
        weight = 1 / (len(ranking) - 1) if weighting == "entrant" else 1.0
        appearances.update(ranking)
        for winner, loser in combinations(ranking, 2):
            wins[winner] += 1
            losses[loser] += 1
            weighted[winner, loser] += weight * multipliers.get(ballot["key"], 1.0)
    groups = components(ids, weighted)
    if len(groups) != 1:
        raise ZermeloError("disconnected_comparisons", f"An overall ranking is unidentified across {len(groups)} "
                       f"disconnected groups: {groups}. Collect overlapping comparisons first.")
    if method in {"pl", "bt"}:
        pairs = sorted(weighted)
        left = np.array([index[a] for a, _ in pairs])
        right = np.array([index[b] for _, b in pairs])
        weights = np.array([weighted[pair] for pair in pairs])

        if method == "bt":
            def objective(theta):
                delta = theta[left] - theta[right]
                value = np.dot(weights, np.logaddexp(0.0, -delta)) + regularization * np.dot(theta, theta) / 2
                residual = -weights * expit(-delta)
                gradient = regularization * theta
                np.add.at(gradient, left, residual)
                np.add.at(gradient, right, -residual)
                return value, gradient
        else:
            # Aggregate identical permutations, then vectorize by group size.
            permutations = Counter()
            for ballot in ballots:
                permutations[tuple(index[key] for key in ballot["ranking"])] += multipliers.get(ballot["key"], 1.0)
            blocks = []
            for size in sorted({len(order) for order in permutations}):
                orders = [order for order in permutations if len(order) == size]
                blocks.append((np.array(orders), np.array([permutations[order] for order in orders])))

            def objective(theta):
                value = regularization * np.dot(theta, theta) / 2
                gradient = regularization * theta.copy()
                for orders, counts in blocks:
                    for stage in range(orders.shape[1] - 1):
                        remaining = orders[:, stage:]
                        strengths = theta[remaining]
                        normalizer = logsumexp(strengths, axis=1)
                        value += np.dot(counts, normalizer - strengths[:, 0])
                        residual = counts[:, None] * np.exp(strengths - normalizer[:, None])
                        residual[:, 0] -= counts
                        np.add.at(gradient, remaining.ravel(), residual.ravel())
                return value, gradient

        fit = minimize(objective, np.zeros(len(ids)), jac=True, method="L-BFGS-B",
                       options={"maxiter": 10000, "gtol": 1e-8, "ftol": 1e-12})
        if not fit.success or not np.all(np.isfinite(fit.x)):
            raise ZermeloError("fit_failed", str(fit.message))
        strengths = fit.x - np.mean(fit.x)
        ratings = 1500 + strengths * 400 / math.log(10)
        fit_info = {"converged": True, "iterations": int(fit.nit), "objective": float(fit.fun),
                    "regularization": regularization,
                    "likelihood": "whole-ranking Plackett-Luce" if method == "pl" else "pairwise composite"}
    else:
        ratings = np.full(len(ids), 1500.0)
        for ballot in ballots:
            ranking = ballot["ranking"]
            weight = 1 / (len(ranking) - 1) if weighting == "entrant" else 1.0
            changes = np.zeros(len(ids))
            # Update simultaneously within a ballot: artificial pair enumeration
            # order must not decide which item receives a larger Elo increment.
            for a, b in combinations(ranking, 2):
                i, j = index[a], index[b]
                probability = expit((ratings[i] - ratings[j]) * math.log(10) / 400)
                change = k_factor * weight * (1 - probability)
                changes[i] += change
                changes[j] -= change
            ratings += changes
        strengths = (ratings - 1500) * math.log(10) / 400
        fit_info = {"k_factor": k_factor, "order": "batch/task/judge/iteration key; simultaneous within ballot"}
    names = {e["id"]: e["name"] for e in entrants}
    rows = [{"id": key, "name": names[key], "rating": float(ratings[i]), "strength": float(strengths[i]),
             "ballots": appearances[key], "wins": wins[key], "losses": losses[key]}
            for i, key in enumerate(ids)]
    rows.sort(key=lambda row: (-row["rating"], row["id"]))
    rank = 0
    previous = None
    for position, row in enumerate(rows, 1):
        if previous is None or not math.isclose(row["rating"], previous, rel_tol=0, abs_tol=1e-7):
            rank = position
        previous = row["rating"]
        row["rank"] = rank
    return {"schema_version": 1, "method": method, "weighting": "whole-ballot" if method == "pl" else weighting, "rankings": rows,
            "diagnostics": {"ballots": len(ballots), "implied_wins": sum(wins.values()),
                            "weighted_wins": sum(weighted.values()), "components": groups,
                            "unique_pairs": len({tuple(sorted(pair)) for pair in weighted}),
                            "fit": fit_info},
            "limitations": ["Scores pool the selected agents and models; they are not population preference estimates.",
                            "Wins implied by the same ranking are dependent; no independent-pair confidence intervals are reported.",
                            "A single strength score cannot represent preference cycles or all differences between judges."]}
