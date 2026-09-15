import copy
import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from zermelo import fielding
from zermelo.cli import main
from zermelo.design import make_design
from zermelo.store import Store, ZermeloError, register_entrants


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "project with spaces")
    store.initialize("Prefer higher numeric values")
    with store.update("setup") as (state, _):
        register_entrants(state, [{"id": f"e{i}", "name": f"Value {i}", "description": f"Value: {i}"}
                                 for i in range(6)])
        state["batches"]["pilot"] = {"design": make_design(state, "pilot", 3, 2, 42),
                                      "fielding": None, "imports": []}
    return store


@pytest.fixture
def exported(store):
    pytest.importorskip("edsl")
    with store.update("export") as (state, _):
        fielding.export_batch(store, state, "pilot", "test", iterations=2)
    return store


def bundle(store):
    batch = store.load()["batches"]["pilot"]
    tasks = {task["id"]: task for task in batch["design"]["tasks"]}
    return {"schema_version": 1, "batch_id": "pilot", "design_hash": batch["design"]["design_hash"],
            "ballots": [{"task_id": task, "judge_id": judge, "iteration": iteration,
                         "ranking": sorted(tasks[task]["entrants"], reverse=True)}
                        for task, judge, iteration in fielding.expected_keys(batch)]}


def ingest(store, path):
    with store.update("import") as (state, connection):
        return fielding.import_results(state, connection, "pilot", path)


def invoke(store, *args):
    return CliRunner().invoke(main, ["--project", str(store.root), *args])


def test_ep_jobs_roundtrip_and_template_options(exported):
    from edsl import Jobs
    batch = exported.load()["batches"]["pilot"]
    manifest = batch["fielding"]
    jobs = Jobs.git.load(manifest["jobs_path"])
    assert len(jobs.scenarios) == 6
    assert manifest["expected_model_calls"] == 12
    assert "'" in manifest["run_command"]  # Project path has spaces.
    question = jobs.survey.questions[0]
    assert question.num_selections == 3
    assert question.use_code is True
    for scenario, task in zip(jobs.scenarios, batch["design"]["tasks"]):
        assert question._translate_answer_code_to_answer([0, 1, 2], scenario) == task["entrants"]
    assert hashlib.sha256(Path(manifest["jobs_path"]).read_bytes()).hexdigest() == manifest["jobs_sha256"]
    result = invoke(exported, "batch", "export", "pilot", "--model", "test")
    assert result.exit_code == 2
    assert json.loads(result.output)["errors"][0]["code"] == "already_exported"


def test_import_retry_dedup_conflict_and_raw_preservation(exported, tmp_path):
    data = bundle(exported)
    path = tmp_path / "first.json"
    first = {**data, "ballots": data["ballots"][:3]}
    path.write_text(json.dumps(first))
    initial = ingest(exported, path)
    assert initial["added"] == 3 and not initial["coverage"]["complete"]
    assert ingest(exported, path)["duplicates"] == 3
    with exported.connect() as conn:
        assert conn.execute("SELECT content FROM sources").fetchone()[0] == path.read_bytes()
    retry = tmp_path / "retry.json"
    retry.write_text(json.dumps(data))
    merged = ingest(exported, retry)
    assert merged["added"] == 9 and merged["duplicates"] == 3
    assert merged["coverage"]["complete"]
    assert len(exported.load()["batches"]["pilot"]["imports"]) == 2
    before = exported.load()
    bad = copy.deepcopy(data)
    bad["ballots"][-1]["ranking"].reverse()
    retry.write_text(json.dumps(bad))
    with pytest.raises(ZermeloError, match="different ranking"):
        ingest(exported, retry)
    assert exported.load() == before


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "foreign", "null", "numeric", "judge", "iteration", "task", "hash"])
def test_invalid_bundle_is_atomic(exported, tmp_path, mutation):
    data = bundle(exported)
    ballot = data["ballots"][-1]
    if mutation == "missing":
        ballot["ranking"].pop()
    elif mutation == "duplicate":
        ballot["ranking"][0] = ballot["ranking"][1]
    elif mutation == "foreign":
        ballot["ranking"][0] = "unregistered"
    elif mutation == "null":
        ballot["ranking"] = None
    elif mutation == "numeric":
        ballot["ranking"] = [0, 1, 2]
    elif mutation == "judge":
        ballot["judge_id"] = "unregistered"
    elif mutation == "iteration":
        ballot["iteration"] = True
    elif mutation == "task":
        ballot["task_id"] = "other"
    else:
        data["design_hash"] = "different"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data))
    before = exported.load()
    with pytest.raises(ZermeloError):
        ingest(exported, path)
    assert exported.load() == before
    with exported.connect() as conn:
        assert conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0


def test_cli_coverage_ranking_csv_and_next(exported, tmp_path):
    assert json.loads(invoke(exported, "next").output)["data"]["stage"] == "awaiting_external_results"
    result = invoke(exported, "rank")
    assert result.exit_code == 2
    assert json.loads(result.output)["errors"][0]["code"] == "incomplete_results"
    data = bundle(exported)
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({**data, "ballots": data["ballots"][::2]}))
    result = invoke(exported, "results", "import", "pilot", str(partial))
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "warning"
    assert json.loads(invoke(exported, "next").output)["data"]["stage"] == "incomplete_results"
    result = invoke(exported, "rank", "--allow-incomplete")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["complete"] is False
    complete = tmp_path / "complete.json"
    complete.write_text(json.dumps(data))
    ingest(exported, complete)
    assert json.loads(invoke(exported, "next").output)["data"]["stage"] == "ready_to_rank"
    path = tmp_path / "ranking.csv"
    result = invoke(exported, "rank", "--output", str(path))
    assert result.exit_code == 0, result.output
    assert path.read_text().startswith("rank,id,name,rating,strength,ballots,wins,losses")
    assert path.with_suffix(".metadata.json").exists()
    assert json.loads(result.output)["data"]["source_formats"] == ["manual-json"]
    assert invoke(exported, "rank", "--output", str(path)).exit_code == 2


def test_native_results_import_and_provenance(exported, tmp_path):
    from edsl import Jobs, Results
    from edsl.results import Result
    manifest = exported.load()["batches"]["pilot"]["fielding"]
    jobs = Jobs.git.load(manifest["jobs_path"])
    data = [Result(agent=jobs.agents[0], scenario=scenario, model=jobs.models[0], iteration=iteration,
                   answer={"ranking": sorted([scenario[f"option_{i}"] for i in range(3)], reverse=True)})
            for scenario in jobs.scenarios for iteration in range(2)]
    path = tmp_path / "results.ep"
    Results(survey=jobs.survey, data=data).git.save(path)
    imported = ingest(exported, path)
    assert imported["coverage"]["complete"]
    assert imported["source_format"] == "edsl.Results"
    report = json.loads(invoke(exported, "rank").output)
    assert report["status"] == "warning"
    assert "test-model" in report["warnings"][0]
    assert report["data"]["batch_settings"][0]["model"]["model"] == "test"


def test_remote_native_codes_map_through_frozen_display_order(exported, tmp_path):
    from edsl import Jobs, Results
    from edsl.results import Result
    batch = exported.load()["batches"]["pilot"]
    jobs = Jobs.git.load(batch["fielding"]["jobs_path"])
    result = Result(agent=jobs.agents[0], scenario=jobs.scenarios[0], model=jobs.models[0], iteration=0,
                    answer={"ranking": [2, 0, 1]})
    path = tmp_path / "coded.ep"
    Results(survey=jobs.survey, data=[result]).git.save(path)
    imported = ingest(exported, path)
    assert imported["native_code_rows_mapped"] == 1
    assert imported["added"] == 1
    ballot = next(iter(exported.load()["ballots"].values()))
    assert ballot["ranking"] == [jobs.scenarios[0][f"option_{i}"] for i in [2, 0, 1]]
    with exported.connect() as connection:
        assert connection.execute("SELECT content FROM sources").fetchone()[0] == path.read_bytes()


@pytest.mark.parametrize("ranking", [[1, 2, 3], [0, 0, 1], [True, 0, 2], [0, "1", 2], [0, 1], [0, 1, 3]])
def test_invalid_native_codes_are_not_guessed_or_repaired(exported, tmp_path, ranking):
    from edsl import Jobs, Results
    from edsl.results import Result
    jobs = Jobs.git.load(exported.load()["batches"]["pilot"]["fielding"]["jobs_path"])
    result = Result(agent=jobs.agents[0], scenario=jobs.scenarios[0], model=jobs.models[0], iteration=0,
                    answer={"ranking": ranking})
    path = tmp_path / "invalid-coded.ep"
    Results(survey=jobs.survey, data=[result]).git.save(path)
    with pytest.raises(ZermeloError, match="rank every assigned entrant"):
        ingest(exported, path)


def test_skip_invalid_reports_every_rejection_and_keeps_missing_cells(exported, tmp_path):
    data = bundle(exported)
    data["ballots"][0]["ranking"] = None
    data["ballots"][1]["ranking"] = ["foreign"]
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(data))
    result = invoke(exported, "results", "import", "pilot", str(path), "--skip-invalid")
    assert result.exit_code == 0, result.output
    outcome = json.loads(result.output)
    assert outcome["status"] == "warning"
    assert outcome["data"]["added"] == 10
    assert [row["row"] for row in outcome["data"]["rejected"]] == [0, 1]
    assert len(outcome["data"]["coverage"]["missing"]) == 2
    assert exported.load()["batches"]["pilot"]["imports"][0]["rejected"] == outcome["data"]["rejected"]
    # This flag must never allow a response from an unassigned judge.
    data["ballots"][2]["judge_id"] = "foreign"
    path.write_text(json.dumps(data))
    result = invoke(exported, "results", "import", "pilot", str(path), "--skip-invalid")
    assert result.exit_code == 2
    assert json.loads(result.output)["errors"][0]["code"] == "unexpected_ballot"


def test_native_agentlist_and_additional_batch(exported, tmp_path):
    from edsl import Agent, AgentList, Jobs
    agents = AgentList([Agent(name="first", traits={"perspective": "Speed"}),
                        Agent(name="second", traits={"perspective": "Quality"})])
    path = tmp_path / "agents.ep"
    agents.git.save(path)
    assert invoke(exported, "batch", "plan", "second", "--chunk-size", "2", "--rounds", "1").exit_code == 0
    result = invoke(exported, "batch", "export", "second", "--model", "test", "--agents", str(path))
    assert result.exit_code == 0, result.output
    manifest = json.loads(result.output)["data"]
    assert manifest["agent_count"] == 2
    jobs = Jobs.git.load(manifest["jobs_path"])
    assert [agent.traits["elo_judge_id"] for agent in jobs.agents] == ["first", "second"]
    assert list(exported.load()["batches"]) == ["pilot", "second"]
    assert fielding.coverage(exported.load(), "second")["expected"] == 10


def test_transaction_rolls_back_partial_entrant_registration(tmp_path):
    store = Store(tmp_path)
    store.initialize("Quality")
    with pytest.raises(ZermeloError):
        with store.update("invalid") as (state, _):
            register_entrants(state, [{"id": "a", "name": "A"}, {"id": "a", "name": "Duplicate"}])
    assert store.load()["entrants"] == []


@pytest.mark.parametrize("change", ["model", "agent", "scenario", "hash"])
def test_native_result_rejects_changed_execution(exported, tmp_path, change):
    from edsl import Jobs, Model, Results
    from edsl.results import Result
    manifest = exported.load()["batches"]["pilot"]["fielding"]
    jobs = Jobs.git.load(manifest["jobs_path"])
    model, agent, scenario = jobs.models[0], jobs.agents[0], jobs.scenarios[0]
    if change == "model":
        model = Model("test", temperature=0.99)
    elif change == "agent":
        agent.traits["new_trait"] = "changed"
    elif change == "scenario":
        scenario["candidates"] = "different candidates"
    else:
        scenario["elo_design_hash"] = "different"
    path = tmp_path / "bad.ep"
    result = Result(agent=agent, scenario=scenario, model=model, iteration=0,
                    answer={"ranking": [scenario[f"option_{i}"] for i in range(3)]})
    Results(survey=jobs.survey, data=[result]).git.save(path)
    with pytest.raises(ZermeloError):
        ingest(exported, path)


def test_cli_init_registration_and_errors(tmp_path):
    store = Store(tmp_path / "new")
    assert json.loads(invoke(store, "next").output)["data"]["stage"] == "initialize"
    assert invoke(store, "init", "--criterion", "Best quality").exit_code == 0
    assert json.loads(invoke(store, "next").output)["data"]["stage"] == "register_entrants"
    path = tmp_path / "entrants.csv"
    path.write_text('id,name,description\na,Alpha,"Fast, inexpensive"\nb,Beta,Reliable\n')
    assert invoke(store, "entrants", "import", str(path)).exit_code == 0
    assert json.loads(invoke(store, "next").output)["data"]["stage"] == "plan"
    assert invoke(store, "batch", "plan", "pilot").exit_code == 0
    assert json.loads(invoke(store, "next").output)["data"]["stage"] == "export"
    result = invoke(store, "entrants", "add", "c", "--name", "C")
    assert result.exit_code == 0
    assert len(store.load()["entrants"]) == 3
    assert len(store.load()["batches"]["pilot"]["design"]["entrants"]) == 2
    for args in [("rank", "--method", "invalid"), ("unknown",), ("batch", "plan", "bad", "--rounds", "0")]:
        result = invoke(store, *args)
        assert result.exit_code == 2
        assert json.loads(result.output)["status"] == "error"
    for command in ["guide", "version", "capabilities", "status"]:
        result = invoke(store, command)
        assert result.exit_code == 0
        assert set(json.loads(result.output)) == {"status", "command", "data", "warnings", "errors", "next_steps"}
