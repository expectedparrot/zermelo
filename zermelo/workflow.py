"""Read-only workflow guidance and evidence-bound report registrations."""

from __future__ import annotations

import hashlib
import importlib.util
import shlex
from pathlib import Path

from . import fielding
from .diagnostics import observed_graph
from .store import ZermeloError, evidence_hash


def register_report(store, state, kind, data, paths=()):
    artifacts = []
    for path in paths:
        path = Path(path).resolve()
        artifacts.append({"path": str(path.relative_to(store.root)) if path.is_relative_to(store.root) else str(path),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    report = {"kind": kind, "evidence_hash": evidence_hash(state), "data": data, "artifacts": artifacts}
    with store.update("workflow.report") as (current, _):
        reports = current.setdefault("workflow_reports", [])
        if report not in reports:
            reports.append(report)


def current_reports(store, state, kind):
    current_hash = evidence_hash(state)
    for report in reversed(state.get("workflow_reports", [])):
        if report["kind"] != kind or report["evidence_hash"] != current_hash:
            continue
        try:
            intact = all(hashlib.sha256((store.root / item["path"]).read_bytes()).hexdigest() == item["sha256"]
                         for item in report["artifacts"])
        except OSError:
            intact = False
        if intact:
            yield report


def unused_name(base, existing):
    candidate, index = base, 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def unused_output(path, *, job=False):
    candidate, index = path, 2
    def occupied(candidate):
        result = candidate.with_name(candidate.stem.removesuffix("_job") + "_results.ep")
        return (candidate.exists() or candidate.with_suffix(".metadata.json").exists()
                or job and result.exists())

    while occupied(candidate):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        index += 1
    return candidate


def guidance(store):
    prefix = ["zermelo", "--project", str(store.root)] if store.selection_source == "--project" else ["zermelo"]

    def action(args, purpose, *, inputs=None, external=False, inference=False, prerequisites=()):
        argv = args if external else prefix + args
        return {"argv": argv, "command": shlex.join(argv), "purpose": purpose,
                "required_inputs": inputs or {}, "runnable": not inputs,
                "external": external, "may_spend_credits": inference, "prerequisites": list(prerequisites)}

    def step(stage, reason, actions=(), **extra):
        return {"workflow_schema_version": 1, "stage": stage, "project": str(store.root), "reason": reason,
                "actions": list(actions), **extra}

    try:
        state = store.load()
    except ZermeloError as exc:
        if exc.code != "not_initialized":
            raise
        return step("initialize", "Choose the precise ranking criterion, best first.", [action(
            ["init", "--criterion", "{criterion}"], "Initialize the selected project.",
            inputs={"criterion": "The criterion supplied by the user; do not invent it."})])

    if len(state["entrants"]) < 2:
        return step("register_entrants", "Register at least two options with stable IDs and descriptions.", [action(
            ["entrants", "import", "{entrants_path}"], "Import the entrant definitions.",
            inputs={"entrants_path": "Path to a CSV or JSON file containing id, name, and optional description."})])

    pending = [key for key, batch in state["batches"].items() if batch["fielding"] is None]
    if (pending or not state["batches"]) and importlib.util.find_spec("edsl") is None:
        return step("install_fielding", "Native ranker registration and export require the fielding extra.", [action(
            ["python", "-m", "pip", "install", "zermelo[fielding]"], "Install native EP support.", external=True)])
    if (pending or not state["batches"]) and not state.get("ranker_list", {}).get("ids"):
        return step("register_rankers", "Choose and register the intended ranker panel before exporting jobs.", [action(
            ["rankers", "add", "{agent_list_path}"], "Freeze a native AgentList as the registered panel.",
            inputs={"agent_list_path": "Path to the intended native AgentList .ep file; see zermelo guide."})])

    if not state["batches"]:
        return step("plan", "Plan connected comparisons for the registered entrants and rankers.", [action(
            ["batch", "plan", "batch-1", "--chunk-size", "5", "--rounds", "3", "--seed", "0"],
            "Create the initial comparison design; inspect it with batch show before export.")])

    for key, batch in state["batches"].items():
        if batch["fielding"] is None:
            path = unused_output(store.root / f"{key}_job.ep", job=True)
            return step("export", "Choose a model and export the frozen design. Export never runs inference.", [action(
                ["batch", "export", key, "--model", "{model}", "--output", str(path)],
                "Export native jobs and return cost/run/import commands.",
                inputs={"model": "An EDSL model name; add --service or --model-parameters when needed."})])
        coverage = fielding.coverage(state, key)
        if coverage["complete"]:
            continue
        jobs = fielding.artifact_path(store, key, "jobs_path")
        result = fielding.artifact_path(store, key, "results_path")
        imported = {item["source_sha256"] for item in batch["imports"]}
        # Never overwrite returned results. Skip already imported copies by content,
        # so duplicate imports and moved projects cannot trap the workflow.
        index = 1
        original = result
        while result.exists() and hashlib.sha256(result.read_bytes()).hexdigest() in imported:
            result = original.with_name(f"{original.stem}-retry-{index}.ep")
            index += 1
        if result.exists():
            return step("import_results", "Import the returned artifact; invalid rows are reported and conflicts fail.", [action(
                ["results", "import", key, str(result), "--skip-invalid"],
                "Preserve original bytes and import valid assigned rankings.")], missing=coverage["missing"])
        if not jobs.is_file():
            return step("restore_jobs", "The frozen job artifact is missing. Restore it before execution.",
                        [action(["batch", "show", key], "Inspect the manifest and archived artifact paths.")],
                        required_artifact=str(jobs))
        run = ["ep", "run", "--jobs", str(jobs), "--n", str(batch["fielding"]["iterations"]),
               "--remote_inference_results_visibility", "private", "--output", str(result)]
        retry = bool(batch["imports"])
        reason = ("Rerun the frozen batch using EP's cache, saving a new result artifact. This retries the full batch; "
                  "cache misses can rerun successful cells and incur charges. Conflicting ballots are rejected on import."
                  if retry else "Execute the exported job externally after reviewing its cost; then call next again.")
        return step("incomplete_results" if retry else "awaiting_external_results", reason, [
            action(run, "Run the frozen job and save results to a new path.", external=True, inference=True,
                   prerequisites=["Review the full-job cost estimate and ensure inference is authorized."]),
            action(["ep", "jobs", "cost", str(jobs)], "Estimate full-job cost before execution.", external=True),
        ], missing=coverage["missing"], expected_model_calls=batch["fielding"]["expected_model_calls"])

    graph = observed_graph(state)
    if not graph["ranking_ballots"] and state.get("calibrations"):
        key = next(reversed(state["calibrations"]))
        report = next((item for item in current_reports(store, state, "calibration")
                       if item["data"]["calibration_id"] == key), None)
        if report is None:
            return step("analyze_calibration", "Analyze the completed calibration before planning production.", [action(
                ["calibrate", "analyze", key], "Record a candidate-size recommendation.")])
        size = report["data"]["recommended_chunk_size"]
        args = ["batch", "plan", unused_name("production", state["batches"]), "--chunk-size", str(size) if size else "{chunk_size}"]
        return step("plan", "Calibration is analyzed. Plan production; consistency is not an accuracy guarantee.", [action(
            args, "Create a production batch using the calibration recommendation." if size else
            "No candidate met the threshold; review the analysis and explicitly choose a size or run another pilot.",
            inputs=None if size else {"chunk_size": "A reviewed integer size of at least two; no candidate was recommended."})])
    if graph["unobserved"]:
        return step("plan_unobserved", "Connect entrants that have no production observations.", [action(
            ["batch", "plan", unused_name("newcomers", state["batches"]), "--only-new", "--rounds", "1"],
            "Compare new entrants with observed anchors.")])
    if len(graph["components"]) > 1:
        return step("connect_components", "Observed comparisons must connect the whole pool.", [action(
            ["batch", "plan", unused_name("bridges", state["batches"]), "--rounds", "1"],
            "Plan comparisons that connect the components.")])
    report = next(current_reports(store, state, "ranking"), None)
    if report and report["data"]["complete"]:
        return step("complete", "A complete ranking is saved and its artifacts match the current project evidence.",
                    artifacts=[str(store.root / item["path"]) for item in report["artifacts"]],
                    limitation="Completion means the requested workflow is finished, not that the ranking is ground truth.")
    return step("ready_to_rank", "All production assignments are present and connected. Save a ranking with provenance.", [action(
        ["rank", "--output", str(unused_output(store.root / "rankings.json"))], "Fit and save the default Plackett–Luce ranking.")])
