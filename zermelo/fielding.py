"""Native EDSL Jobs/Results exchange; never invokes model inference."""

from __future__ import annotations

import contextlib
import hashlib
import json
import shlex
import sys
import tempfile
from pathlib import Path

from . import __version__
from .store import ZermeloError, digest, identifier, read_json, write_new


def edsl_imports():
    try:
        import edsl
    except ImportError as exc:
        raise ZermeloError("missing_dependency", "Install native EP support with: pip install 'zermelo[fielding]'") from exc
    return edsl


def model_spec(data):
    return {key: data.get(key) for key in ("model", "inference_service", "parameters")}


def load_agents(path=None):
    edsl = edsl_imports()
    if path is None:
        return edsl.AgentList([edsl.Agent(name="judge", traits={"elo_judge_id": "judge"})])
    if path.suffix.lower() == ".ep":
        agents = edsl.AgentList.git.load(path)
        agents = edsl.AgentList([edsl.Agent.from_dict(agent.to_dict()) for agent in agents])
    else:
        rows = read_json(path)
        if not isinstance(rows, list) or not rows:
            raise ZermeloError("invalid_agents", "Agents JSON must be a nonempty list of {id, traits} objects")
        agents = []
        for row in rows:
            if not isinstance(row, dict) or set(row) - {"id", "traits"} or not isinstance(row.get("traits", {}), dict):
                raise ZermeloError("invalid_agents", "Each agent must have id and optional traits")
            judge_id = identifier(row.get("id"))
            traits = dict(row.get("traits", {}))
            traits["elo_judge_id"] = judge_id
            agents.append(edsl.Agent(name=judge_id, traits=traits))
        agents = edsl.AgentList(agents)
    seen = set()
    anonymous_counts = {}
    for agent in agents:
        explicit = agent.traits.get("elo_judge_id")
        if explicit:
            judge_id = identifier(explicit)
        else:
            try:
                judge_id = identifier(agent.name)
            except ZermeloError:
                # Ordinary EDSL lists often have no agent names. Derive a stable
                # ID from the full definition; retain repeated identical entries.
                fingerprint = digest(agent.to_dict(add_edsl_version=False))[:16]
                anonymous_counts[fingerprint] = anonymous_counts.get(fingerprint, 0) + 1
                judge_id = f"ranker-{fingerprint}-{anonymous_counts[fingerprint]:03d}"
        if judge_id in seen:
            raise ZermeloError("duplicate_judge", f"Duplicate judge ID: {judge_id}")
        seen.add(judge_id)
        agent.traits["elo_judge_id"] = judge_id
    if not agents:
        raise ZermeloError("invalid_agents", "At least one agent is required")
    return agents


def build_jobs(design, agents, model):
    edsl = edsl_imports()
    entrants = {row["id"]: row for row in design["entrants"]}
    scenarios = []
    for task in design["tasks"]:
        # Put arbitrary entrant text in scenario values, so Jinja does not interpret
        # braces inside entrant descriptions as additional template expressions.
        scenario = {"elo_batch_id": design["batch_id"], "elo_design_hash": design["design_hash"],
                    "elo_task_id": task["id"], **build_scenario_check(design, task, entrants)}
        scenarios.append(edsl.Scenario(scenario))
    question = edsl.QuestionRank(
        question_name="ranking",
        question_text="Rank these candidates from BEST to WORST according to this criterion:\n"
                      "{{ criterion }}\n\n{{ candidates }}\n\n"
                      "Use only the supplied candidate information and your judgment. "
                      "Rank every candidate exactly once. No ties or omissions.",
        question_options=["{{ option_" + str(i) + " }}" for i in range(design["chunk_size"])],
        num_selections=design["chunk_size"], use_code=True,
    )
    return edsl.Survey([question]).by(edsl.ScenarioList(scenarios)).by(agents).by(model)


def export_batch(store, state, batch_id, model_name, *, service=None, parameters=None, agents_path=None, iterations=1,
                 output_path=None, results_output=None):
    batch = get_batch(state, batch_id)
    if batch["fielding"] is not None:
        raise ZermeloError("already_exported", "This batch already has frozen jobs; create another batch for a new run")
    if type(iterations) is not int or iterations < 1:
        raise ZermeloError("invalid_iterations", "Iterations must be a positive integer")
    parameters = {} if parameters is None else parameters
    if not isinstance(parameters, dict) or set(parameters) & {"model", "service_name", "api_key", "api_token"}:
        raise ZermeloError("invalid_parameters", "Model parameters must be a JSON object of generation settings")
    from .rankers import registered_path

    ranker_registration = None
    if agents_path is None:
        agents_path = registered_path(store, state)
        ranker_registration = state.get("ranker_list")
    output = store.root / "batches" / batch_id
    canonical_jobs = output / "jobs.ep"
    jobs_path = Path(output_path).resolve() if output_path else canonical_jobs
    if jobs_path.suffix.lower() != ".ep":
        raise ZermeloError("invalid_output", "Job output must end in .ep")
    if jobs_path != canonical_jobs and jobs_path.is_relative_to(output):
        raise ZermeloError("invalid_output", "Choose a job path outside the batch archive or its canonical jobs.ep")
    result_stem = jobs_path.stem.removesuffix("_job") + "_results"
    results_path = (Path(results_output).resolve() if results_output else
                    jobs_path.with_name(result_stem + ".ep") if output_path else output / "results.ep")
    if results_path.suffix.lower() != ".ep" or results_path == jobs_path or results_path == canonical_jobs:
        raise ZermeloError("invalid_output", "Choose a distinct .ep results path")
    if results_path.is_relative_to(output) and results_path != output / "results.ep":
        raise ZermeloError("invalid_output", "Results inside the batch archive must be named results.ep")
    if output.exists() or jobs_path.exists() or results_path.exists():
        raise ZermeloError("already_exists", "Refusing to overwrite a batch, exported job, or expected results file")
    import_prefix = (["zermelo"] if getattr(store, "selection_source", "--project") != "--project"
                     else ["zermelo", "--project", str(store.root)])
    edsl = edsl_imports()
    with contextlib.redirect_stdout(sys.stderr):
        agents = load_agents(agents_path)
        model = edsl.Model(model_name, **({"service_name": service} if service else {}), **parameters)
        jobs = build_jobs(batch["design"], agents, model)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".building-", dir=output.parent) as temp:
            staging = Path(temp)
            path = staging / "jobs.ep"
            jobs.git.save(path, message=f"Build Zermelo batch {batch_id}")
            loaded = edsl.Jobs.git.load(path)
            if digest(loaded.to_dict()) != digest(jobs.to_dict()):
                raise ZermeloError("artifact_verification_failed", "Jobs did not survive a native EP save/load round trip")
            command = shlex.join(["ep", "run", "--jobs", str(jobs_path), "--n", str(iterations),
                                  "--remote_inference_results_visibility", "private", "--output", str(results_path)])
            specification = model_spec(model.to_dict())
            manifest = {"schema_version": 1, "package_version": __version__, "batch_id": batch_id,
                        "design_hash": batch["design"]["design_hash"], "model": specification,
                        "judges": {agent.traits["elo_judge_id"]: agent.to_dict(add_edsl_version=False)
                                   for agent in agents},
                        "iterations": iterations, "scenario_count": len(jobs.scenarios), "agent_count": len(agents),
                        "question_count": 1, "model_count": 1,
                        "expected_model_calls": len(jobs.scenarios) * len(agents) * iterations,
                        "jobs_path": str(jobs_path), "results_path": str(results_path), "run_command": command,
                        "execution": "external via ep run", "inference": "remote by default",
                        "ranker_list": ranker_registration,
                        "ranker_origin": "registered AgentList" if ranker_registration else
                                         "explicit agent file" if agents_path else "default neutral judge",
                        "cost_command": shlex.join(["ep", "jobs", "cost", str(jobs_path)]),
                        "import_command": shlex.join(import_prefix + ["results", "import", batch_id, str(results_path)]),
                        "canonical_jobs_path": str(canonical_jobs),
                        "project_relative_paths": {key: str(value.relative_to(store.root))
                            for key, value in {"jobs_path": jobs_path, "results_path": results_path}.items()
                            if value.is_relative_to(store.root)},
                        "estimated_cost": None, "jobs_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            write_new(staging / "design.json", batch["design"])
            write_new(staging / "manifest.json", manifest)
            external_created = False
            try:
                if jobs_path != canonical_jobs:
                    jobs_path.parent.mkdir(parents=True, exist_ok=True)
                    with jobs_path.open("xb") as handle:
                        external_created = True
                        handle.write(path.read_bytes())
                staging.rename(output)
            except BaseException:
                if external_created:
                    jobs_path.unlink()
                raise
    batch["fielding"] = manifest
    return manifest


def get_batch(state, batch_id):
    try:
        return state["batches"][batch_id]
    except KeyError as exc:
        raise ZermeloError("unknown_batch", f"Unknown batch: {batch_id}") from exc


def expected_keys(batch):
    manifest = batch["fielding"]
    if manifest is None:
        return []
    return [(task["id"], judge, iteration) for task in batch["design"]["tasks"]
            for judge in sorted(manifest["judges"]) for iteration in range(manifest["iterations"])]


def ballot_key(batch_id, task_id, judge_id, iteration):
    return f"{batch_id}/{task_id}/{judge_id}/{iteration:08d}"


def coverage(state, batch_id):
    batch = get_batch(state, batch_id)
    expected = expected_keys(batch)
    missing = [{"task_id": task, "judge_id": judge, "iteration": iteration}
               for task, judge, iteration in expected
               if ballot_key(batch_id, task, judge, iteration) not in state["ballots"]]
    return {"batch_id": batch_id, "exported": batch["fielding"] is not None, "expected": len(expected),
            "received": len(expected) - len(missing), "missing": missing,
            "complete": bool(expected) and not missing}


def normalize_native(path, batch):
    edsl = edsl_imports()
    manifest = batch["fielding"]
    try:
        with contextlib.redirect_stdout(sys.stderr):
            results = edsl.Results.git.load(path)
    except Exception as exc:
        raise ZermeloError("invalid_artifact", f"Cannot read native EP Results: {path}") from exc
    rows = []
    mapped_code_rows = 0
    tasks = {task["id"]: task for task in batch["design"]["tasks"]}
    entrants = {e["id"]: e for e in batch["design"]["entrants"]}
    for index, result in enumerate(results):
        data = result.to_dict(add_edsl_version=False)
        scenario = data.get("scenario", {})
        judge = data.get("agent", {}).get("traits", {}).get("elo_judge_id")
        task_id = scenario.get("elo_task_id")
        if (scenario.get("elo_design_hash") != batch["design"]["design_hash"]
                or scenario.get("elo_batch_id") != batch["design"]["batch_id"] or task_id not in tasks):
            raise ZermeloError("response_mismatch", f"Row {index} belongs to another design or task")
        if judge not in manifest["judges"]:
            raise ZermeloError("response_mismatch", f"Row {index} has an unregistered judge")
        agent = data["agent"]
        registered = manifest["judges"][judge]
        # Some EDSL versions add bookkeeping fields. Compare the substantive agent definition.
        for key in ("traits", "name", "instruction"):
            if agent.get(key) != registered.get(key):
                raise ZermeloError("response_mismatch", f"Row {index} changed the registered agent's {key}")
        if model_spec(data.get("model", {})) != manifest["model"]:
            raise ZermeloError("response_mismatch", f"Row {index} does not match the frozen model settings")
        expected_scenario = build_scenario_check(batch["design"], tasks[task_id], entrants)
        if any(scenario.get(key) != value for key, value in expected_scenario.items()):
            raise ZermeloError("response_mismatch", f"Row {index} changed the assigned candidate information")
        ranking = data.get("answer", {}).get("ranking")
        assigned = tasks[task_id]["entrants"]
        # Local EDSL may translate codes before serialization; the remote runner
        # can retain QuestionRank's zero-based codes. Decode only an exact full
        # permutation against the already-validated frozen option order.
        if (isinstance(ranking, list) and len(ranking) == len(assigned)
                and all(type(value) is int for value in ranking)
                and set(ranking) == set(range(len(assigned)))):
            ranking = [assigned[value] for value in ranking]
            mapped_code_rows += 1
        rows.append({"task_id": task_id, "judge_id": judge, "iteration": data.get("iteration", 0),
                     "ranking": ranking})
    return rows, mapped_code_rows


def build_scenario_check(design, task, entrants):
    result = {"criterion": design["criterion"], "candidates": "\n\n".join(
        f"ID: {key}\nName: {entrants[key]['name']}\nDescription: {entrants[key]['description']}"
        for key in task["entrants"])}
    if design.get("purpose") == "calibration":
        result["candidates"] += f"\n\nIndependent calibration replicate: {task['id']} (ignore this identifier when ranking)."
    result.update({f"option_{i}": key for i, key in enumerate(task["entrants"])})
    return result


def import_results(state, connection, batch_id, path, *, skip_invalid=False):
    batch = get_batch(state, batch_id)
    if batch["fielding"] is None:
        raise ZermeloError("not_exported", "Export the batch to freeze its judges and execution settings first")
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    mapped_code_rows = 0
    if path.suffix == ".ep":
        rows, mapped_code_rows = normalize_native(path, batch)
        source_format = "edsl.Results"
    else:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ZermeloError("unsupported_schema", "Expected a version 1 ballot bundle")
        if data.get("batch_id") != batch_id or data.get("design_hash") != batch["design"]["design_hash"]:
            raise ZermeloError("response_mismatch", "Ballot bundle does not match this batch and design hash")
        rows = data.get("ballots")
        source_format = "manual-json"
    if not isinstance(rows, list) or not rows:
        raise ZermeloError("invalid_results", "Result bundle must contain at least one ballot")
    tasks = {task["id"]: task for task in batch["design"]["tasks"]}
    pending = {}
    duplicates = 0
    rejected = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"task_id", "judge_id", "iteration", "ranking"}:
            raise ZermeloError("invalid_ballot", "Ballots require exactly task_id, judge_id, iteration, ranking")
        task_id, judge, iteration = row["task_id"], row["judge_id"], row["iteration"]
        if (not isinstance(task_id, str) or task_id not in tasks or not isinstance(judge, str)
                or judge not in batch["fielding"]["judges"] or type(iteration) is not int
                or not 0 <= iteration < batch["fielding"]["iterations"]):
            raise ZermeloError("unexpected_ballot", "Ballot task, judge, or iteration was not assigned")
        ranking = row["ranking"]
        if (not isinstance(ranking, list) or not all(isinstance(key, str) for key in ranking)
                or len(ranking) != len(tasks[task_id]["entrants"])
                or len(set(ranking)) != len(ranking) or set(ranking) != set(tasks[task_id]["entrants"])):
            message = f"{task_id}: rank every assigned entrant exactly once, best first"
            if not skip_invalid:
                raise ZermeloError("invalid_ranking", message)
            rejected.append({"row": row_index, "task_id": task_id, "judge_id": judge, "iteration": iteration,
                             "code": "invalid_ranking", "message": message, "ranking": ranking})
            continue
        key = ballot_key(batch_id, task_id, judge, iteration)
        previous = pending.get(key) or state["ballots"].get(key)
        if previous:
            if previous["ranking"] != ranking:
                raise ZermeloError("conflicting_result", f"A different ranking already exists for {key}")
            duplicates += 1
            continue
        pending[key] = {**row, "key": key, "batch_id": batch_id,
                        "source_sha256": source_hash, "source_format": source_format}
    if not pending and not duplicates:
        raise ZermeloError("no_valid_results", f"No usable rankings; rejected {len(rejected)} rows")
    # All rows validate before any write; the caller owns the SQLite transaction.
    state["ballots"].update(pending)
    connection.execute("INSERT OR IGNORE INTO sources VALUES (?, ?, ?)", (source_hash, path.name, raw))
    registration = {"source_sha256": source_hash, "source_format": source_format,
                    "source_path": str(path.resolve()), "added": len(pending), "duplicates": duplicates,
                    "skip_invalid": skip_invalid, "rejected": rejected,
                    "native_code_rows_mapped": mapped_code_rows}
    if not any(item["source_sha256"] == source_hash for item in batch["imports"]):
        batch["imports"].append(registration)
    return {**registration, "coverage": coverage(state, batch_id)}


def artifact_path(store, batch_id, kind):
    """Resolve new relative paths and legacy in-project artifacts after a move."""
    manifest = get_batch(store.load(), batch_id)["fielding"]
    if manifest is None:
        raise ZermeloError("not_exported", "Export this batch before locating its artifacts")
    relative = manifest.get("project_relative_paths", {}).get(kind)
    if relative:
        return store.root / relative
    original = Path(manifest[kind])
    if original.exists():
        return original
    conventional = store.root / "batches" / batch_id / ("jobs.ep" if kind == "jobs_path" else "results.ep")
    return conventional if conventional.exists() else original
