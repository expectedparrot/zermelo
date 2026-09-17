"""Follow the public guidance contract across setup, recovery, and completion."""

import hashlib
import json
import shlex
from pathlib import Path

import pytest
from click.testing import CliRunner

from zermelo.cli import main
from zermelo.store import Store


def cli(root, *args):
    result = CliRunner().invoke(main, ["--project", str(root), *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def follow(step, **inputs):
    action = step["actions"][0]
    assert set(inputs) == set(action["required_inputs"])
    assert shlex.split(action["command"]) == action["argv"]
    args = [inputs.get(arg[1:-1], arg) if arg.startswith("{") else arg for arg in action["argv"]]
    assert args[0] == "zermelo"
    result = CliRunner().invoke(main, args[1:])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["data"]


def next_step(root):
    envelope = cli(root, "next")
    step = envelope["data"]
    assert envelope["next_steps"] == [a["command"] for a in step["actions"] if a["runnable"]]
    return step


def returned_results(run_action, *, partial=False, inconsistent=False):
    """Simulate the external EP boundary with native test-model artifacts, no inference."""
    edsl = pytest.importorskip("edsl")
    args = run_action["argv"]
    assert args[:2] == ["ep", "run"]
    assert run_action["external"] and run_action["may_spend_credits"]
    jobs_path = Path(args[args.index("--jobs") + 1])
    original = jobs_path.read_bytes()
    jobs = edsl.Jobs.git.load(jobs_path)
    rows = []
    for scenario in jobs.scenarios:
        for agent in jobs.agents:
            for iteration in range(int(args[args.index("--n") + 1])):
                k = jobs.survey.questions[0].num_selections
                order = sorted(scenario[f"option_{i}"] for i in range(k))
                if inconsistent and int(scenario["elo_task_id"].rsplit("t", 1)[1]) % 2 == 0:
                    order.reverse()
                rows.append(edsl.Result(agent=agent, scenario=scenario, model=jobs.models[0], iteration=iteration,
                                        answer={"ranking": order}))
    target = Path(args[args.index("--output") + 1])
    assert not target.exists()
    edsl.Results(survey=jobs.survey, data=rows[:1] if partial else rows).git.save(target)
    assert jobs_path.read_bytes() == original
    return target


def setup_panel(root, tmp_path):
    edsl = pytest.importorskip("edsl")
    step = next_step(root)
    assert step["stage"] == "initialize" and not step["actions"][0]["runnable"]
    follow(step, criterion="Prefer higher values")
    entrants = tmp_path / "entrant inputs.json"
    entrants.write_text(json.dumps([{"id": f"e{i}", "name": f"Value {i}"} for i in range(6)]))
    follow(next_step(root), entrants_path=str(entrants))
    assert next_step(root)["stage"] == "register_rankers"
    agents = tmp_path / "ranker inputs.ep"
    edsl.AgentList([edsl.Agent(name="alice"), edsl.Agent(name="bob")]).git.save(agents)
    follow(next_step(root), agent_list_path=str(agents))


def finish_batch(root):
    step = next_step(root)
    assert step["stage"] == "export"
    assert not step["actions"][0]["may_spend_credits"]
    follow(step, model="test")
    returned_results(next_step(root)["actions"][0])
    follow(next_step(root))


def test_follow_next_from_empty_project_through_recovery_and_saved_ranking(tmp_path):
    root = tmp_path / "project with spaces"
    setup_panel(root, tmp_path)
    follow(next_step(root))
    manifest = follow(next_step(root), model="test")
    assert set(manifest["judges"]) == {"alice", "bob"}
    first = returned_results(next_step(root)["actions"][0], partial=True)
    original = first.read_bytes()
    follow(next_step(root))
    retry = next_step(root)
    assert retry["stage"] == "incomplete_results" and retry["missing"]
    returned_results(retry["actions"][0])
    follow(next_step(root))
    assert first.read_bytes() == original
    ready = next_step(root)
    assert ready["stage"] == "ready_to_rank"
    # Printing a ranking is not a saved deliverable.
    printed = cli(root, "rank")["data"]
    assert next_step(root)["stage"] == "ready_to_rank"
    saved = follow(ready)
    assert saved["input_hash"] == printed["input_hash"]
    assert cli(root, "rank")["data"]["input_hash"] == saved["input_hash"]
    complete = next_step(root)
    assert complete["stage"] == "complete" and not complete["actions"]
    report = Path(complete["artifacts"][0])
    original_report = report.read_bytes()
    state_before = Store(root).load()
    assert next_step(root) == complete
    assert Store(root).load() == state_before  # next is read-only.
    with Store(root).connect() as connection:
        assert connection.execute("SELECT content FROM sources WHERE sha256=?",
                                  (hashlib.sha256(original).hexdigest(),)).fetchone()[0] == original
    moved = tmp_path / "moved project"
    root.rename(moved)
    assert next_step(moved)["stage"] == "complete"
    report = moved / report.name
    report.write_text("changed")
    assert next_step(moved)["stage"] == "ready_to_rank"
    assert next_step(moved)["actions"][0]["argv"][-1] != str(report)
    report.write_bytes(original_report)
    cli(moved, "entrants", "add", "new", "--name", "New value")
    assert next_step(moved)["stage"] == "plan_unobserved"
    follow(next_step(moved))
    finish_batch(moved)
    assert next_step(moved)["stage"] == "ready_to_rank"
    follow(next_step(moved))
    assert next_step(moved)["stage"] == "complete"
    cli(moved, "entrants", "add", "newer", "--name", "Another value")
    # Generated names must not collide on the second incremental wave.
    assert next_step(moved)["actions"][0]["argv"][5] == "newcomers-2"
    follow(next_step(moved))


def test_calibration_advances_to_production_and_csv_completion(tmp_path):
    root = tmp_path / "calibration"
    setup_panel(root, tmp_path)
    cli(root, "calibrate", "plan", "pilot", "--batch-sizes", "2,4", "--sample", "6", "--subsets", "2", "--repeats", "2")
    finish_batch(root)
    finish_batch(root)
    assert next_step(root)["stage"] == "analyze_calibration"
    analysis = follow(next_step(root))
    assert analysis["recommended_chunk_size"] == 4
    assert cli(root, "calibrate", "analyze", "pilot")["data"]["input_hash"] == analysis["input_hash"]
    step = next_step(root)
    assert step["stage"] == "plan"
    assert step["actions"][0]["argv"][-2:] == ["--chunk-size", "4"]
    follow(step)
    finish_batch(root)
    output = root / "ranking.csv"
    cli(root, "rank", "--output", str(output))
    assert next_step(root)["stage"] == "complete"
    output.with_suffix(".metadata.json").unlink()
    assert next_step(root)["stage"] == "ready_to_rank"


def test_export_output_avoids_existing_artifacts_and_next_does_not_execute(tmp_path, monkeypatch):
    root = tmp_path / "study"
    setup_panel(root, tmp_path)
    follow(next_step(root))
    existing = root / "batch-1_results.ep"
    existing.write_bytes(b"preserve existing artifact")
    monkeypatch.setattr("zermelo.fielding.export_batch", lambda *a, **kw: pytest.fail("next must not export"))
    step = next_step(root)
    assert step["stage"] == "export"
    job_path = Path(step["actions"][0]["argv"][-1])
    assert job_path.with_name(job_path.stem.removesuffix("_job") + "_results.ep") != existing
    assert existing.read_bytes() == b"preserve existing artifact"


def test_calibration_without_eligible_size_requires_review(tmp_path):
    root = tmp_path / "inconsistent"
    setup_panel(root, tmp_path)
    cli(root, "calibrate", "plan", "pilot", "--batch-sizes", "2", "--sample", "6", "--subsets", "2", "--repeats", "2")
    follow(next_step(root), model="test")
    returned_results(next_step(root)["actions"][0], inconsistent=True)
    follow(next_step(root))
    report = follow(next_step(root))
    assert report["recommended_chunk_size"] is None
    step = next_step(root)
    assert step["stage"] == "plan" and not step["actions"][0]["runnable"]
    follow(step, chunk_size="2")
    assert next_step(root)["stage"] == "export"


def test_missing_fielding_dependency_has_install_action(tmp_path, monkeypatch):
    root = tmp_path / "no-fielding"
    cli(root, "init", "--criterion", "Quality")
    cli(root, "entrants", "add", "a", "--name", "A")
    cli(root, "entrants", "add", "b", "--name", "B")
    monkeypatch.setattr("zermelo.workflow.importlib.util.find_spec", lambda name: None)
    step = next_step(root)
    assert step["stage"] == "install_fielding"
    assert step["actions"][0]["argv"][-1] == "zermelo[fielding]"
    assert not step["actions"][0]["may_spend_credits"]
