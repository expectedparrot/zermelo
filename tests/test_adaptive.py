"""Statistical recovery and workflow invariants for adaptive ranking."""

import copy
import itertools
import json
import math

import numpy as np
import pytest
from click.testing import CliRunner

from zermelo import fielding
from zermelo.calibration import analyze_calibration, kendall_distance, plan_calibration
from zermelo.cli import fit_project, main
from zermelo.design import adaptive_design, components, make_design
from zermelo.diagnostics import assess_snapshot, information_budget, observed_graph, perturbation
from zermelo.scoring import score
from zermelo.store import Store, ZermeloError, digest, register_entrants


def state_with_results(n=12, rounds=3):
    state = {"schema_version": 1, "criterion": "Quality", "batches": {}, "ballots": {},
             "entrants": [{"id": f"e{i:03}", "name": str(i), "description": ""} for i in range(n)]}
    design = make_design(state, "first", 4, rounds, 9)
    state["batches"]["first"] = {"design": design, "imports": [], "fielding": {
        "judges": {"j": {}}, "iterations": 1, "model": {"model": "test", "inference_service": "test"}}}
    for t in design["tasks"]:
        key = fielding.ballot_key("first", t["id"], "j", 0)
        state["ballots"][key] = {"key": key, "batch_id": "first", "task_id": t["id"], "judge_id": "j",
                                  "iteration": 0, "ranking": sorted(t["entrants"]),
                                  "source_format": "manual-json", "source_sha256": "fixture"}
    return state


def test_pl_recovers_strengths_from_random_partial_rankings():
    rng = np.random.default_rng(73)
    state = state_with_results(8)
    ids = [e["id"] for e in state["entrants"]]
    theta = np.linspace(1.4, -1.4, 8)
    ballots = []
    for i in range(2000):
        subset = rng.choice(8, 5, replace=False)
        utility = theta[subset] + rng.gumbel(size=5)
        order = subset[np.argsort(-utility)]
        ballots.append({"key": str(i), "ranking": [ids[j] for j in order]})
    fitted = score(state["entrants"], ballots, method="pl")
    by_id = {r["id"]: r["strength"] for r in fitted["rankings"]}
    assert [by_id[key] for key in ids] == pytest.approx(theta, abs=.15)
    assert score(state["entrants"], list(reversed(ballots)), method="pl") == fitted
    assert fitted["weighting"] == "whole-ballot"


def test_two_way_pl_equals_bt_and_penalty_stabilizes_separation():
    state = state_with_results(2)
    ballots = list(state["ballots"].values())
    pl = score(state["entrants"], ballots, method="pl")
    bt = score(state["entrants"], ballots, method="bt")
    assert [r["strength"] for r in pl["rankings"]] == pytest.approx([r["strength"] for r in bt["rankings"]])
    assert all(math.isfinite(r["strength"]) for r in pl["rankings"])
    assert sum(r["strength"] for r in pl["rankings"]) == pytest.approx(0)


def test_pl_symmetric_full_permutations_are_tied():
    state = state_with_results(3)
    ballots = [{"key": str(i), "ranking": list(p)}
               for i, p in enumerate(itertools.permutations(e["id"] for e in state["entrants"]))]
    assert [r["rank"] for r in score(state["entrants"], ballots, method="pl")["rankings"]] == [1, 1, 1]


def test_task_bootstrap_does_not_treat_duplicate_judges_as_new_independent_evidence():
    state = state_with_results(6, 3)
    ballots = list(state["ballots"].values())
    fitted = score(state["entrants"], ballots, method="pl")
    first = perturbation(state["entrants"], ballots, fitted, draws=20, seed=19)
    doubled = ballots + [{**r, "key": r["key"] + "dup", "judge_id": "second"} for r in ballots]
    # Double the likelihood and penalty: fitted targets stay identical. The
    # cluster draw still moves duplicate same-task answers together.
    second_fit = score(state["entrants"], doubled, method="pl", regularization=2)
    second = perturbation(state["entrants"], doubled, second_fit, draws=20, seed=19, regularization=2)
    assert first["clusters"] == second["clusters"] == len(ballots)
    for key in first["entrants"]:
        assert first["entrants"][key]["strength_sd"] == pytest.approx(second["entrants"][key]["strength_sd"], abs=1e-6)
    assert first == perturbation(state["entrants"], ballots, fitted, draws=20, seed=19)
    with pytest.raises(ZermeloError, match="two resampling"):
        perturbation(state["entrants"], ballots, fitted, draws=20, cluster="judge")


@pytest.mark.parametrize("size", [2, 4, 12])
def test_adaptive_connected_reproducible_and_exact_task_budget(size):
    state = state_with_results()
    design = adaptive_design(state, "wave", size, 1, 71, task_count=20)
    assert design == adaptive_design(state, "wave", size, 1, 71, task_count=20)
    assert len(design["tasks"]) == 20
    assert len(design["coverage"]["components"]) == 1
    assert design["selection"]["random_bridge_tasks"] == 2
    assert all(len(t["entrants"]) == len(set(t["entrants"])) == size for t in design["tasks"])
    assert design["selection"]["base_input_hash"] == digest(state)
    assert len([t for t in design["tasks"] if t["selection"] == "neighborhood"]) > 0
    with pytest.raises(ZermeloError, match="at least"):
        adaptive_design(state, "short", 2, 1, task_count=1)


def test_incremental_keeps_snapshots_and_connects_every_new_entrant():
    state = state_with_results()
    old = copy.deepcopy(state["batches"])
    register_entrants(state, [{"id": "newa", "name": "A"}, {"id": "newb", "name": "B"}])
    assert state["batches"] == old
    design = adaptive_design(state, "new", 5, 2, only_new=True, task_count=8)
    new_ids = {"newa", "newb"}
    assert all(set(t["entrants"]) & new_ids for t in design["tasks"])
    pairs = [pair for row in state["ballots"].values() for pair in itertools.combinations(row["ranking"], 2)]
    pairs += [pair for t in design["tasks"] for pair in itertools.combinations(t["entrants"], 2)]
    assert len(components([e["id"] for e in state["entrants"]], pairs)) == 1
    assert observed_graph(state)["unobserved"] == sorted(new_ids)
    with pytest.raises(ZermeloError, match="disconnected"):
        fit_project(state)


def test_calibration_subset_permutations_and_consistent_wrong_model():
    state = state_with_results(20)
    plan = plan_calibration(state, "cal", [4, 8], sample=16, subsets=3, repeats=3, seed=10)
    assert len(plan["sample_ids"]) == 16
    snapshots = {key: len(value["design"]["tasks"]) for key, value in state["batches"].items() if key in plan["batch_ids"]}
    assert snapshots == {"cal-k4": 9, "cal-k8": 9}
    before = fit_project(state)
    for key in plan["batch_ids"]:
        batch = state["batches"][key]
        batch["fielding"] = copy.deepcopy(state["batches"]["first"]["fielding"])
        for t in batch["design"]["tasks"]:
            ballot_key = fielding.ballot_key(key, t["id"], "j", 0)
            state["ballots"][ballot_key] = {"key": ballot_key, "batch_id": key, "task_id": t["id"], "judge_id": "j",
                                           "iteration": 0, "ranking": sorted(t["entrants"], reverse=True),
                                           "source_format": "manual-json", "source_sha256": "fixture"}
    after = fit_project(state)
    assert before["rankings"] == after["rankings"]
    assert after["excluded_calibration_ballots"] == 18
    analysis = analyze_calibration(state, "cal")
    assert analysis["recommended_chunk_size"] == 8
    assert all(r["mean_kendall_disagreement"] == 0 for r in analysis["candidates"])
    truth = [e["id"] for e in state["entrants"]]
    analysis = analyze_calibration(state, "cal", reference=truth)
    assert analysis["recommended_chunk_size"] is None
    assert all(r["mean_reference_error"] == 1 for r in analysis["candidates"])
    del state["ballots"][ballot_key]
    assert analyze_calibration(state, "cal")["recommended_chunk_size"] is None
    state["batches"]["cal-k8"]["fielding"]["model"]["model"] = "different"
    with pytest.raises(ZermeloError, match="identical model"):
        analyze_calibration(state, "cal")


def test_information_ceiling_is_not_a_tolerance_promise():
    info = information_budget(10000, 10, calls=500, cost_per_call=.002, budget=5)
    assert 5400 < info["exact_sort_call_lower_bound"] < 5500
    assert info["exact_sort_bits"] == pytest.approx(118458.143, abs=.01)
    assert info["estimated_cost"] == 1
    assert info["affordable_calls"] == 2500
    assert information_budget(10, 10)["exact_sort_call_lower_bound"] == 1
    for args in [(1, 2), (10, 11)]:
        with pytest.raises(ZermeloError):
            information_budget(*args)
    with pytest.raises(ZermeloError):
        information_budget(10, 5, budget=5)
    assert kendall_distance(["a", "b", "c"], ["b", "a", "c"]) == 1 / 3


def test_stability_requires_new_unchanged_ballots_and_matching_settings():
    state = state_with_results(6)
    previous = fit_project(state)
    with pytest.raises(ZermeloError, match="new ranking ballots"):
        assess_snapshot(state, previous, previous)
    row = next(iter(state["ballots"].values()))
    state["ballots"]["extra"] = {**row, "key": "extra"}
    current = fit_project(state)
    result = assess_snapshot(state, previous, current, tolerance=1)
    assert result["new_ballots"] == 1
    assert result["perturbation_within_tolerance"] is None
    assert not result["review_for_stopping"]
    changed = copy.deepcopy(current)
    changed["settings"]["regularization"] = 2
    with pytest.raises(ZermeloError, match="same entrant IDs and fit settings"):
        assess_snapshot(state, previous, changed)
    changed = copy.deepcopy(current)
    changed["ballot_hashes"][row["key"]] = "conflict"
    with pytest.raises(ZermeloError, match="unchanged subset"):
        assess_snapshot(state, previous, changed)


def test_legacy_database_read_and_new_cli_branding(tmp_path):
    store = Store(tmp_path)
    store.initialize("Quality")
    assert store.path.name == "zermelo.sqlite3"
    store.path.rename(tmp_path / "elo.sqlite3")
    legacy = Store(tmp_path)
    assert legacy.load()["criterion"] == "Quality"
    assert legacy.path.name == "elo.sqlite3"
    result = CliRunner().invoke(main, ["version"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["command"] == "zermelo version"
    assert data["data"]["version"] == "0.2.0"
    (tmp_path / "zermelo.sqlite3").touch()
    with pytest.raises(ZermeloError, match="Both"):
        Store(tmp_path)


def test_cli_calibration_native_roundtrip_and_incremental_next(tmp_path):
    pytest.importorskip("edsl")
    from edsl import Jobs, Result, Results

    store = Store(tmp_path / "native")
    store.initialize("Higher is better")
    with store.update("entrants") as (state, _):
        register_entrants(state, [{"id": f"e{i}", "name": str(i)} for i in range(8)])
    runner = CliRunner()

    def cli(*args):
        result = runner.invoke(main, ["--project", str(store.root), *args])
        assert result.exit_code == 0, result.output
        return json.loads(result.output)["data"]

    plan = cli("calibrate", "plan", "pilot", "--batch-sizes", "2,4", "--sample", "8", "--subsets", "2", "--repeats", "2")
    # Planning requires no EDSL inference and produces no paid run.
    for batch_id in plan["batch_ids"]:
        manifest = cli("batch", "export", batch_id, "--model", "test")
        jobs = Jobs.git.load(manifest["jobs_path"])
        assert "ep run" in manifest["run_command"]
        candidates = [s["candidates"] for s in jobs.scenarios]
        assert len(set(candidates)) == len(candidates)
        assert all("Independent calibration replicate:" in text for text in candidates)
        rows = []
        for scenario in jobs.scenarios:
            order = sorted([scenario[f"option_{i}"] for i in range(jobs.survey.questions[0].num_selections)])
            rows.append(Result(agent=jobs.agents[0], scenario=scenario, model=jobs.models[0], iteration=0,
                               answer={"ranking": order}))
        output = tmp_path / f"{batch_id}.ep"
        Results(survey=jobs.survey, data=rows).git.save(output)
        imported = cli("results", "import", batch_id, str(output))
        assert imported["coverage"]["complete"]
    assert cli("next")["stage"] == "analyze_calibration"
    report = cli("calibrate", "analyze", "pilot")
    assert report["recommended_chunk_size"] == 4
    assert cli("status")["observed_graph"]["ranking_ballots"] == 0
    assert len(cli("status")["observed_graph"]["unobserved"]) == 8
    cli("batch", "plan", "production", "--chunk-size", "4", "--rounds", "1")
    cli("batch", "export", "production", "--model", "test")
    template = cli("results", "template", "production")
    tasks = {t["id"]: t for t in store.load()["batches"]["production"]["design"]["tasks"]}
    for row in template["ballots"]:
        row["ranking"] = sorted(tasks[row["task_id"]]["entrants"])
    manual = tmp_path / "manual.json"
    manual.write_text(json.dumps(template))
    cli("results", "import", "production", str(manual))
    assert cli("rank")["excluded_calibration_ballots"] == 8
    cli("entrants", "add", "fresh", "--name", "New")
    assert cli("next")["stage"] == "plan_unobserved"
    assert cli("batch", "plan", "new", "--only-new", "--rounds", "1")["selection"]["only_new"]
