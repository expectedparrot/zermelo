import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from zermelo import fielding
from zermelo.cli import main
from zermelo.design import make_design
from zermelo.project import resolve_project
from zermelo.rankers import add_rankers
from zermelo.store import Store, ZermeloError, register_entrants


def test_project_selection_precedence_and_move(tmp_path, monkeypatch):
    monkeypatch.delenv("ZERMELO_PROJECT", raising=False)
    runner = CliRunner()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    result = runner.invoke(main, ["project", "use", "runs/study"])
    assert result.exit_code == 0, result.output
    assert not (workspace / "runs/study").exists()  # Selection does not silently initialize.
    assert runner.invoke(main, ["init", "--criterion", "Quality"]).exit_code == 0
    nested = workspace / "subdir"
    nested.mkdir()
    monkeypatch.chdir(nested)
    assert resolve_project()[0] == workspace / "runs/study"
    selected = json.loads(runner.invoke(main, ["project", "show"]).output)["data"]
    assert selected["source"] == str(workspace / ".zermelo-project")
    monkeypatch.setenv("ZERMELO_PROJECT", str(tmp_path / "environment"))
    assert resolve_project()[0] == tmp_path / "environment"
    assert resolve_project(tmp_path / "explicit")[0] == tmp_path / "explicit"
    monkeypatch.delenv("ZERMELO_PROJECT")
    monkeypatch.chdir(tmp_path)
    moved = tmp_path / "moved"
    workspace.rename(moved)
    monkeypatch.chdir(moved)
    assert resolve_project()[0] == moved / "runs/study"
    assert runner.invoke(main, ["project", "clear"]).exit_code == 0
    monkeypatch.chdir(moved / "runs/study")
    assert resolve_project()[1] == "containing project"


def project_fixture(tmp_path):
    store = Store(tmp_path / "study")
    store.initialize("Quality")
    with store.update("setup") as (state, _):
        register_entrants(state, [{"id": f"e{i}", "name": str(i)} for i in range(4)])
        state["batches"]["main"] = {"design": make_design(state, "main", 4, 1), "fielding": None, "imports": []}
    return store


def test_native_ranker_registration_preserves_sources_and_freezes_exports(tmp_path):
    edsl = pytest.importorskip("edsl")
    store = project_fixture(tmp_path)
    source = tmp_path / "agent_list.ep"
    edsl.AgentList([edsl.Agent(name="alice", traits={"priority": "quality"})]).git.save(source)
    original = source.read_bytes()
    with store.update("rankers") as (state, conn):
        registration = add_rankers(store, state, conn, source)
    assert registration["total"] == 1
    with store.connect() as conn:
        assert conn.execute("SELECT content FROM sources WHERE sha256=?", (hashlib.sha256(original).hexdigest(),)).fetchone()[0] == original
    with store.update("export") as (state, _):
        manifest = fielding.export_batch(store, state, "main", "test", output_path=store.root / "ranking_job.ep")
    assert sorted(manifest["judges"]) == ["alice"]
    assert manifest["ranker_origin"] == "registered AgentList"
    old_snapshot = Path(registration["agent_list"])
    old_bytes = old_snapshot.read_bytes()
    second = tmp_path / "second.ep"
    edsl.AgentList([edsl.Agent(name="bob", traits={"priority": "price"})]).git.save(second)
    with store.update("rankers") as (state, conn):
        added = add_rankers(store, state, conn, second)
    assert added["total"] == 2
    assert old_snapshot.read_bytes() == old_bytes
    assert sorted(store.load()["batches"]["main"]["fielding"]["judges"]) == ["alice"]
    with store.update("rankers") as (state, conn):
        assert add_rankers(store, state, conn, source)["duplicates"] == 1
    bad = tmp_path / "conflict.ep"
    edsl.AgentList([edsl.Agent(name="alice", traits={"priority": "changed"})]).git.save(bad)
    before = store.load()
    with pytest.raises(ZermeloError, match="different definition"):
        with store.update("rankers") as (state, conn):
            add_rankers(store, state, conn, bad)
    assert store.load() == before


def test_custom_job_export_commands_and_implicit_ingest_after_move(tmp_path, monkeypatch):
    edsl = pytest.importorskip("edsl")
    store = project_fixture(tmp_path)
    runner = CliRunner()
    monkeypatch.setenv("ZERMELO_PROJECT", str(store.root))
    job_path = store.root / "ranking_job.ep"
    result = runner.invoke(main, ["batch", "export", "main", "--model", "test", "--output", str(job_path)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    manifest = data["data"]
    assert manifest["results_path"] == str(store.root / "ranking_results.ep")
    assert job_path.read_bytes() == (store.root / "batches/main/jobs.ep").read_bytes()
    assert manifest["cost_command"].endswith("ranking_job.ep")
    assert manifest["import_command"].startswith("zermelo results import main ")
    assert len(data["next_steps"]) == 3
    jobs = edsl.Jobs.git.load(job_path)
    scenario = jobs.scenarios[0]
    results = edsl.Results(survey=jobs.survey, data=[edsl.Result(
        agent=jobs.agents[0], model=jobs.models[0], scenario=scenario, iteration=0,
        answer={"ranking": [scenario[f"option_{i}"] for i in range(4)]})])
    results.git.save(manifest["results_path"])
    moved = tmp_path / "moved study"
    store.root.rename(moved)
    monkeypatch.setenv("ZERMELO_PROJECT", str(moved))
    next_data = json.loads(runner.invoke(main, ["next"]).output)
    assert next_data["data"]["stage"] == "import_results"
    assert next_data["next_steps"][0].startswith("zermelo results import")
    result = runner.invoke(main, ["results", "import", "main"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["coverage"]["complete"]
    assert Store(moved).load()["batches"]["main"]["fielding"] == manifest


def test_export_collision_does_not_change_state_or_existing_file(tmp_path):
    pytest.importorskip("edsl")
    store = project_fixture(tmp_path)
    target = tmp_path / "ranking_job.ep"
    target.write_bytes(b"preserve")
    before = store.load()
    with pytest.raises(ZermeloError, match="overwrite"):
        with store.update("export") as (state, _):
            fielding.export_batch(store, state, "main", "test", output_path=target)
    assert target.read_bytes() == b"preserve"
    assert store.load() == before
    assert not (store.root / "batches/main").exists()


def test_unnamed_native_rankers_receive_stable_ids(tmp_path):
    edsl = pytest.importorskip("edsl")
    source = tmp_path / "agent_list.ep"
    edsl.AgentList([edsl.Agent(traits={"preference": "nature"}),
                    edsl.Agent(traits={"preference": "nature"}),
                    edsl.Agent(name="City traveler", traits={"preference": "cities"})]).git.save(source)
    first = fielding.load_agents(source)
    second = fielding.load_agents(source)
    ids = [agent.traits["elo_judge_id"] for agent in first]
    assert len(set(ids)) == 3
    assert all(key.startswith("ranker-") for key in ids)
    assert ids == [agent.traits["elo_judge_id"] for agent in second]
    assert first[-1].name == "City traveler"
