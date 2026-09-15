import itertools
import math
import random

import pytest

from zermelo.design import components, make_design
from zermelo.scoring import score
from zermelo.store import ZermeloError


def entrants(n):
    return [{"id": f"e{i:03d}", "name": f"Entrant {i}", "description": str(i)} for i in range(n)]


@pytest.mark.parametrize("n", [2, 3, 6, 20, 101, 1000])
@pytest.mark.parametrize("size", [2, 3, 5, 7])
def test_design_is_connected_complete_and_bounded(n, size):
    state = {"entrants": entrants(n), "criterion": "Prefer quality", "batches": {}}
    design = make_design(state, "pilot", chunk_size=size, rounds=3, seed=27)
    assert design == make_design(state, "pilot", chunk_size=size, rounds=3, seed=27)
    ids = {row["id"] for row in state["entrants"]}
    for round_id in range(1, 4):
        groups = [task["entrants"] for task in design["tasks"] if task["round"] == round_id]
        assert set(itertools.chain.from_iterable(groups)) == ids
        assert all(len(group) == len(set(group)) == min(size, n) for group in groups)
        pairs = itertools.chain.from_iterable(itertools.combinations(group, 2) for group in groups)
        assert len(components(ids, pairs)) == 1
    assert len({task["id"] for task in design["tasks"]}) == len(design["tasks"])


def test_20_entrants_need_15_small_tasks():
    state = {"entrants": entrants(20), "criterion": "Quality", "batches": {}}
    design = make_design(state, "pilot")
    assert len(design["tasks"]) == 15


def test_bt_recovers_known_latent_strengths_and_is_order_invariant():
    rng = random.Random(7)
    items = entrants(6)
    strengths = [1.5, 0.9, 0.3, -0.3, -0.9, -1.5]
    ballots = []
    for i, j in itertools.combinations(range(6), 2):
        p = 1 / (1 + math.exp(strengths[j] - strengths[i]))
        for _ in range(300):
            ranking = [items[i]["id"], items[j]["id"]]
            if rng.random() > p:
                ranking.reverse()
            ballots.append({"key": str(len(ballots)), "ranking": ranking})
    fitted = score(items, ballots)
    assert [row["id"] for row in fitted["rankings"]] == [row["id"] for row in items]
    assert [row["strength"] for row in fitted["rankings"]] == pytest.approx(strengths, abs=0.2)
    rng.shuffle(ballots)
    assert score(items, ballots) == fitted


@pytest.mark.parametrize("method", ["bt", "elo"])
def test_rankings_create_every_implied_win_and_preserve_rating_mean(method):
    rows = entrants(3)
    fitted = score(rows, [{"key": "one", "ranking": [row["id"] for row in rows]}], method=method)
    assert [row["id"] for row in fitted["rankings"]] == [row["id"] for row in rows]
    assert fitted["diagnostics"]["implied_wins"] == 3
    assert fitted["diagnostics"]["weighted_wins"] == 1.5
    assert [row["wins"] for row in fitted["rankings"]] == [2, 1, 0]
    assert sum(row["rating"] for row in fitted["rankings"]) == pytest.approx(4500)
    if method == "elo":
        assert [row["rating"] for row in fitted["rankings"]] == [1516, 1500, 1484]


def test_symmetric_cycle_has_equal_bt_rank():
    rows = entrants(3)
    ids = [row["id"] for row in rows]
    ballots = [{"key": str(i), "ranking": [ids[i], ids[(i + 1) % 3]]} for i in range(3)]
    assert [row["rank"] for row in score(rows, ballots)["rankings"]] == [1, 1, 1]


def test_regularization_handles_undefeated_and_always_losing_entrants():
    rows = entrants(3)
    ballots = [{"key": str(i), "ranking": [row["id"] for row in rows]} for i in range(30)]
    fitted = score(rows, ballots)
    assert all(math.isfinite(row["rating"]) for row in fitted["rankings"])
    stronger_penalty = score(rows, ballots, regularization=100)
    assert stronger_penalty["rankings"][0]["rating"] < fitted["rankings"][0]["rating"]


def test_disconnected_or_unobserved_entrants_are_rejected():
    with pytest.raises(ZermeloError, match="disconnected"):
        score(entrants(4), [{"key": "one", "ranking": ["e000", "e001"]},
                            {"key": "two", "ranking": ["e002", "e003"]}])
    with pytest.raises(ZermeloError, match="disconnected"):
        score(entrants(3), [{"key": "one", "ranking": ["e000", "e001"]}])


@pytest.mark.parametrize("penalty", [0, -1, float("nan"), float("inf")])
def test_invalid_regularization(penalty):
    with pytest.raises(ZermeloError, match="finite and positive"):
        score(entrants(2), [{"key": "one", "ranking": ["e000", "e001"]}], regularization=penalty)
