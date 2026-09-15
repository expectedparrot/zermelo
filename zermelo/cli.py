"""Noninteractive CLI with a single JSON envelope per command."""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import shlex
import sqlite3
import tempfile
from pathlib import Path

import click

from . import __version__, fielding
from .calibration import analyze_calibration, plan_calibration
from .design import adaptive_design, make_design
from .diagnostics import assess_snapshot, information_budget, observed_graph, perturbation, ranking_ballots
from .project import MARKER, resolve_project
from .rankers import add_rankers, registered_path
from .scoring import score
from .store import Store, ZermeloError, digest, read_json, register_entrants, write_new


def emit(data=None, *, errors=None, warnings=None, next_steps=None, command=None):
    context = click.get_current_context(silent=True)
    warnings = warnings or []
    click.echo(json.dumps({"status": "error" if errors else "warning" if warnings else "ok",
                           "command": command or (context.command_path if context else "zermelo"),
                           "data": data or {}, "warnings": warnings, "errors": errors or [],
                           "next_steps": next_steps or []}, indent=2, allow_nan=False))


class JSONGroup(click.Group):
    def main(self, *args, **kwargs):
        standalone = kwargs.pop("standalone_mode", True)
        try:
            return super().main(*args, standalone_mode=False, **kwargs)
        except Exception as exc:
            code = "operation_failed"
            if isinstance(exc, ZermeloError):
                code = exc.code
            elif isinstance(exc, (click.ClickException, ValueError, TypeError)):
                code = "invalid_input"
            if isinstance(exc, (OSError, sqlite3.Error)):
                code = "io_error"
            emit(errors=[{"code": code, "message": str(exc)}], command="zermelo")
            if standalone:
                raise SystemExit(2) from exc
            raise click.exceptions.Exit(2) from exc


@click.group(cls=JSONGroup)
@click.option("--project", type=click.Path(path_type=Path, file_okay=False),
              help="Override ZERMELO_PROJECT, a project-use selection, or a containing project.")
@click.pass_context
def main(ctx, project):
    """Rank many entrants using small agent judgments. Model execution uses ep run."""
    ctx.info_name = "zermelo"
    if ctx.invoked_subcommand == "project":
        root, source = Path.cwd(), "current directory"
    else:
        root, source = resolve_project(project)
    ctx.obj = Store(root)
    ctx.obj.selection_source = source


@main.group()
def project():
    """Select a project once for this workspace, or inspect the effective selection."""


@project.command("use")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
def project_use(directory):
    """Remember DIR for this directory and its descendants; init can follow."""
    root = directory.expanduser().resolve()
    marker = Path.cwd() / MARKER
    data = {"project": os.path.relpath(root, marker.parent)}
    with tempfile.NamedTemporaryFile(mode="w", dir=marker.parent, prefix=".zermelo-project-", delete=False) as handle:
        json.dump(data, handle)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        temporary.replace(marker)
    finally:
        temporary.unlink(missing_ok=True)
    effective, source = resolve_project()
    warnings = [] if effective == root else [f"ZERMELO_PROJECT overrides this selection with {effective}."]
    emit({"selected_project": str(root), "marker": str(marker), "effective_project": str(effective), "source": source},
         warnings=warnings, next_steps=["zermelo next"])


@project.command("show")
@click.pass_context
def project_show(ctx):
    """Show which project commands will use, and where that choice comes from."""
    root, source = resolve_project(ctx.find_root().params.get("project"))
    emit({"project": str(root), "source": source})


@project.command("clear")
def project_clear():
    """Remove this directory's saved selection. Environment variables remain in effect."""
    marker = Path.cwd() / MARKER
    existed = marker.exists()
    marker.unlink(missing_ok=True)
    root, source = resolve_project()
    emit({"removed": existed, "project": str(root), "source": source})


@main.group()
def rankers():
    """Register EDSL AgentLists once and use them for subsequent batch exports."""


@rankers.command("add")
@click.argument("path", type=click.Path(exists=True, path_type=Path, dir_okay=False))
@click.pass_obj
def rankers_add(store, path):
    """Append rankers from a native agent_list.ep; preserve definitions and source bytes."""
    with store.update("rankers.add") as (state, connection):
        data = add_rankers(store, state, connection, path)
    emit(data)


@rankers.command("list")
@click.pass_obj
def rankers_list(store):
    """Inspect the registered AgentList, definitions, and provenance."""
    state = store.load()
    path = registered_path(store, state)
    agents = fielding.load_agents(path) if path else []
    emit({"count": len(agents), "agent_list": str(path) if path else None,
          "rankers": [a.to_dict(add_edsl_version=False) for a in agents],
          "sources": state.get("ranker_sources", [])})


@main.command()
def version():
    """Show the package version."""
    emit({"version": __version__})


@main.command()
def capabilities():
    """Inspect installed features without contacting services."""
    emit({"methods": ["pl", "bt", "elo"], "calibration": True, "adaptive_batches": True,
          "incremental_entrants": True, "uncertainty": "cluster multiplier bootstrap", "entrant_formats": ["csv", "json"],
          "result_formats": ["edsl.Results.ep", "manual-json"],
          "native_ep_available": importlib.util.find_spec("edsl") is not None,
          "execution": "external via ep run", "strict_full_rankings": True})


@main.command()
def guide():
    """Explain the complete workflow and statistical conventions."""
    emit({"workflow": [
        "project use DIR: select a project once for this workspace. Alternatively export ZERMELO_PROJECT=DIR.",
        "init --criterion TEXT: create the selected project with a fixed criterion.",
        "rankers add agent_list.ep: register a native EDSL AgentList once; rankers list shows definitions and sources.",
        "entrants import PATH or entrants add ID --name TEXT: register immutable entrant definitions.",
        "Optional calibrate plan pilot --batch-sizes 4,8,12,16 --sample 40 --subsets 10 --repeats 3: "
        "save repeated shuffled subsets; choose sizes that fit your pool.",
        "batch export ID --model MODEL --output ranking_job.ep: use registered rankers, freeze the model, "
        "and return exact cost/run/import commands. "
        "Use identical fielding settings for all calibration sizes.",
        "Run the returned ep run command externally; it may incur model charges. Export never submits inference.",
        "results import ID [PATH]: ingest the expected results path or an explicit file; validate .ep Results or labeled manual JSON and preserve original bytes. "
        "--skip-invalid explicitly records rejected rankings; conflicting cells always fail.",
        "calibrate analyze pilot [--costs costs.json] [--reference truth.json]: screen candidate sizes; "
        "calibration ballots never enter production rankings.",
        "budget --chunk-size 5 --calls 100 [--cost-per-call .002 --budget 5]: inspect an exact-sort lower bound "
        "and user-estimated costs. This does not promise a rank tolerance or enforce spending.",
        "batch plan first --chunk-size 5 --rounds 3: create connected production tasks, then export/run/import.",
        "rank --method pl --bootstrap 200 --output snapshot.json: fit whole rankings and optional cluster sensitivity.",
        "batch plan followup --strategy neighborhood --rounds 1 --tasks 30 --bridge-frac .1: "
        "reserve connected coverage, then target uncertain neighborhoods and random bridges. Export/run/import again.",
        "assess snapshot.json --tolerance .02: compare after new complete ballots; reports movement and sensitivity, not truth error.",
        "entrants import more.csv; batch plan newcomers --only-new --rounds 1: connect unobserved entrants to rated anchors.",
        "status and next: inspect missing cells and suggested next steps. rank requires complete production batches by default.",
    ], "project_option": "Precedence: --project DIR, ZERMELO_PROJECT, nearest project-use marker or containing project, cwd.",
          "methods": {"pl": "Default CLI: L2-regularized Plackett-Luce likelihood of each whole strict ranking; order invariant.",
                      "bt": "L2-regularized Bradley-Terry pairwise composite likelihood; order invariant.",
                      "elo": "One canonical-order pass with simultaneous within-ballot Elo updates; order sensitive."},
          "weighting": "PL gives each ballot unit weight. BT/Elo default pair weight 1/(k-1); --weighting pair uses one.",
          "uncertainty": "--bootstrap resamples with positive cluster weights. Default task clusters keep all judges/repeats "
                         "together. --cluster judge changes the sensitivity question. Neither provides calibrated accuracy guarantees.",
          "compatibility": "Reads legacy elo.sqlite3 in place. Historical EP metadata keeps elo_* wire identifiers.",
          "limitations": "Strict permutations only. Pooled agent/model preferences, no judge effects. Calibration consistency "
                          "is not accuracy; entropy capacity is not information learned. Disconnected observed graphs fail."})


@main.command()
@click.option("--criterion", required=True, help="The precise criterion, with best first.")
@click.pass_obj
def init(store, criterion):
    """Initialize a local ranking project."""
    store.initialize(criterion)
    emit({"project": str(store.root), "criterion": criterion})


@main.group()
def entrants():
    """Register entrants, including additions after earlier batches."""


@entrants.command("add")
@click.argument("entrant_id")
@click.option("--name", required=True)
@click.option("--description", default="", help="Information the judge needs about this candidate.")
@click.pass_obj
def entrant_add(store, entrant_id, name, description):
    """Register one entrant with a stable ID."""
    with store.update("entrants.add") as (state, _):
        result = register_entrants(state, [{"id": entrant_id, "name": name, "description": description}])
    emit(result)


@entrants.command("import")
@click.argument("path", type=click.Path(exists=True, path_type=Path, dir_okay=False))
@click.pass_obj
def entrant_import(store, path):
    """Register entrants from a JSON array or CSV with id,name,description columns."""
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    else:
        rows = read_json(path)
    with store.update("entrants.import") as (state, _):
        result = register_entrants(state, rows)
    emit(result)


@entrants.command("list")
@click.pass_obj
def entrant_list(store):
    """List registered entrant definitions."""
    state = store.load()
    emit({"entrants": state["entrants"], "definitions_immutable": True, "additions_allowed": True})


@main.group()
def batch():
    """Plan connected tasks and export native EP Jobs."""


@batch.command("plan")
@click.argument("batch_id")
@click.option("--chunk-size", type=click.IntRange(min=2), default=5, show_default=True)
@click.option("--rounds", type=click.IntRange(min=1), default=3, show_default=True)
@click.option("--seed", type=int, default=0, show_default=True)
@click.option("--strategy", type=click.Choice(["random", "neighborhood"]), default="random", show_default=True)
@click.option("--bridge-frac", type=click.FloatRange(0, 1), default=.1, show_default=True)
@click.option("--tasks", type=click.IntRange(min=1), help="Total tasks, including mandatory coverage; insufficient budgets fail.")
@click.option("--only-new", is_flag=True, help="Compare unobserved entrants with anchors from the existing ranking.")
@click.pass_obj
def batch_plan(store, batch_id, chunk_size, rounds, seed, strategy, bridge_frac, tasks, only_new):
    """Create a reproducible wave with an immutable entrant snapshot."""
    with store.update("batch.plan") as (state, _):
        if strategy == "random" and tasks is None and not only_new:
            design = make_design(state, batch_id, chunk_size, rounds, seed)
        else:
            design = adaptive_design(state, batch_id, chunk_size, rounds, seed, strategy=strategy,
                                     bridge_fraction=bridge_frac, task_count=tasks, only_new=only_new)
        state["batches"][batch_id] = {"design": design, "fielding": None, "imports": []}
    emit(design)


@batch.command("show")
@click.argument("batch_id")
@click.pass_obj
def batch_show(store, batch_id):
    """Inspect a preserved design, manifest, and registrations."""
    emit(fielding.get_batch(store.load(), batch_id))


@batch.command("export")
@click.argument("batch_id")
@click.option("--model", "model_name", required=True, help="EDSL model name; use test for offline validation.")
@click.option("--service", help="Explicit EDSL inference service.")
@click.option("--model-parameters", type=click.Path(exists=True, path_type=Path, dir_okay=False),
              help="JSON generation settings, e.g. temperature and max_tokens.")
@click.option("--rankers", "--agents", "agents_path", type=click.Path(exists=True, path_type=Path, dir_okay=False),
              help="Override registered rankers with an AgentList .ep. --agents/JSON remain compatible with older workflows.")
@click.option("--iterations", type=click.IntRange(min=1), default=1, show_default=True)
@click.option("--output", "output_path", type=click.Path(path_type=Path, dir_okay=False),
              help="Export a native job to this .ep path, e.g. runs/states/ranking_job.ep.")
@click.option("--results-output", type=click.Path(path_type=Path, dir_okay=False),
              help="Expected results .ep path; defaults beside a custom job as NAME_results.ep.")
@click.pass_obj
def batch_export(store, batch_id, model_name, service, model_parameters, agents_path, iterations, output_path, results_output):
    """Write and verify jobs.ep and its manifest; return the external run command."""
    parameters = read_json(model_parameters) if model_parameters else None
    with store.update("batch.export") as (state, _):
        manifest = fielding.export_batch(store, state, batch_id, model_name, service=service, parameters=parameters,
                                        agents_path=agents_path, iterations=iterations,
                                        output_path=output_path, results_output=results_output)
    emit(manifest, next_steps=[manifest["cost_command"], manifest["run_command"], manifest["import_command"]])


@main.group()
def results():
    """Register external results and prepare manual response templates."""


@results.command("template")
@click.argument("batch_id")
@click.option("--output", type=click.Path(path_type=Path, dir_okay=False))
@click.pass_obj
def results_template(store, batch_id, output):
    """Return missing cells with empty rankings for explicit manual completion."""
    state = store.load()
    batch_data = fielding.get_batch(state, batch_id)
    if batch_data["fielding"] is None:
        raise ZermeloError("not_exported", "Export the batch first")
    data = {"schema_version": 1, "batch_id": batch_id, "design_hash": batch_data["design"]["design_hash"],
            "ballots": [{**row, "ranking": []} for row in fielding.coverage(state, batch_id)["missing"]]}
    if output:
        write_new(output, data)
    emit(data)


@results.command("import")
@click.argument("batch_id")
@click.argument("path", required=False, type=click.Path(exists=True, path_type=Path, dir_okay=False))
@click.option("--skip-invalid", is_flag=True, help="Explicitly omit invalid rankings, recording every rejected row.")
@click.pass_obj
def results_import(store, batch_id, path, skip_invalid):
    """Validate all rows, preserve the original bytes, and merge without double counting."""
    path = path or fielding.artifact_path(store, batch_id, "results_path")
    with store.update("results.import") as (state, connection):
        result = fielding.import_results(state, connection, batch_id, path, skip_invalid=skip_invalid)
    warnings = [] if result["coverage"]["complete"] else ["Batch is incomplete; inspect coverage.missing."]
    if result["rejected"]:
        warnings.append(f"Explicitly skipped {len(result['rejected'])} invalid rankings; see rejected for details.")
    emit(result, warnings=warnings)


@main.command()
@click.pass_obj
def status(store):
    """Inspect entrant counts and missing assignments for every batch."""
    state = store.load()
    emit({"entrants": len(state["entrants"]), "ballots": len(state["ballots"]),
          "rankers": len(state.get("ranker_list", {}).get("ids", [])),
          "batches": [fielding.coverage(state, key) for key in state["batches"]],
          "observed_graph": observed_graph(state), "calibrations": list(state.get("calibrations", {}))})


@main.command("next")
@click.pass_obj
def next_command(store):
    """Suggest the next command from persisted project state."""
    prefix = (["zermelo", "--project", str(store.root)] if store.selection_source == "--project" else ["zermelo"])
    action = prefix + ["guide"]
    try:
        state = store.load()
    except ZermeloError as exc:
        if exc.code != "not_initialized":
            raise
        emit({"stage": "initialize", "requirement": "Choose a criterion and initialize the project."},
             next_steps=[shlex.join(action)])
        return
    if len(state["entrants"]) < 2:
        stage = "register_entrants"
        action = prefix + ["entrants", "add", "--help"]
    elif not state["batches"]:
        stage = "plan"
        action = prefix + ["batch", "plan", "batch-1"]
    else:
        stage = "ready_to_rank"
        action = prefix + ["rank"]
        for key, batch_data in state["batches"].items():
            if batch_data["fielding"] is None:
                stage = "export"
                action = prefix + ["batch", "export", key, "--help"]
                break
            if not fielding.coverage(state, key)["complete"]:
                path = fielding.artifact_path(store, key, "results_path")
                stage = "import_results" if path.exists() else "awaiting_external_results"
                if path.exists() and not batch_data["imports"]:
                    action = prefix + ["results", "import", key, str(path)]
                elif batch_data["imports"]:
                    stage = "incomplete_results"
                    action = prefix + ["status"]
                else:
                    action = shlex.split(batch_data["fielding"]["run_command"])
                break
    if stage == "ready_to_rank":
        graph = observed_graph(state)
        if not graph["ranking_ballots"] and state.get("calibrations"):
            stage = "analyze_calibration"
            action = prefix + ["calibrate", "analyze", next(reversed(state["calibrations"]))]
        elif graph["unobserved"]:
            stage = "plan_unobserved"
            action = prefix + ["batch", "plan", "newcomers", "--only-new", "--rounds", "1"]
        elif len(graph["components"]) > 1:
            stage = "connect_components"
            action = prefix + ["batch", "plan", "bridges", "--rounds", "1"]
    emit({"stage": stage, "project": str(store.root)}, next_steps=[shlex.join(action)])


@main.command()
@click.option("--method", type=click.Choice(["pl", "bt", "elo"]), default="pl", show_default=True)
@click.option("--regularization", type=float, default=1.0, show_default=True, help="Positive L2 penalty for PL/BT strengths.")
@click.option("--k-factor", type=float, default=32.0, show_default=True, help="Elo update size.")
@click.option("--weighting", type=click.Choice(["entrant", "pair"]), default="entrant", show_default=True)
@click.option("--allow-incomplete", is_flag=True, help="Report a provisional ranking with missing assignments.")
@click.option("--output", type=click.Path(path_type=Path, dir_okay=False), help="New .json or .csv output path.")
@click.option("--bootstrap", type=click.IntRange(min=20), help="Cluster perturbation draws (e.g. 200), for PL/BT.")
@click.option("--cluster", type=click.Choice(["task", "judge"]), default="task", show_default=True)
@click.option("--seed", type=int, default=0, show_default=True)
@click.pass_obj
def rank(store, method, regularization, k_factor, weighting, allow_incomplete, output, bootstrap, cluster, seed):
    """Fit overall rankings from registered ballots; require complete coverage by default."""
    data = fit_project(store.load(), method=method, regularization=regularization, k_factor=k_factor,
                       weighting=weighting, allow_incomplete=allow_incomplete,
                       bootstrap=bootstrap, cluster=cluster, seed=seed)
    warnings = data["warnings"]
    if output:
        if output.suffix.lower() == ".csv":
            metadata_path = output.with_suffix(".metadata.json")
            if output.exists() or metadata_path.exists():
                raise ZermeloError("already_exists", "Refusing to overwrite a ranking or its metadata")
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=["rank", "id", "name", "rating", "strength", "ballots", "wins", "losses"])
            writer.writeheader()
            writer.writerows(data["rankings"])
            write_new(output, buffer.getvalue(), raw=True)
            write_new(metadata_path, {key: value for key, value in data.items() if key != "rankings"})
        elif output.suffix.lower() == ".json":
            write_new(output, data)
        else:
            raise ZermeloError("invalid_output", "Ranking output must end in .json or .csv")
    emit(data, warnings=warnings)


def fit_project(state, *, method="pl", regularization=1.0, k_factor=32.0, weighting="entrant",
                allow_incomplete=False, bootstrap=None, cluster="task", seed=0):
    batches = {key: value for key, value in state["batches"].items()
               if value["design"].get("purpose", "ranking") == "ranking"}
    coverage = [fielding.coverage(state, key) for key in batches]
    incomplete = [row["batch_id"] for row in coverage if not row["complete"]]
    if incomplete and not allow_incomplete:
        raise ZermeloError("incomplete_results", f"Incomplete batches: {', '.join(incomplete)}. "
                          "Inspect status or use --allow-incomplete")
    ballots = ranking_ballots(state)
    data = score(state["entrants"], ballots, method=method, regularization=regularization,
                 k_factor=k_factor, weighting=weighting)
    data.update({"criterion": state["criterion"], "complete": not incomplete, "package_version": __version__,
                 "coverage": coverage, "input_hash": digest(state),
                 "settings": {"method": method, "regularization": regularization, "k_factor": k_factor,
                              "weighting": data["weighting"]},
                 "ballot_hashes": {row["key"]: digest(row) for row in ballots},
                 "batch_settings": [{"batch_id": key, "design_hash": value["design"]["design_hash"],
                                     "model": value["fielding"]["model"] if value["fielding"] else None,
                                     "panel_hash": digest({k: value["fielding"][k] for k in ("model", "judges")})
                                     if value["fielding"] else None,
                                     "judge_ids": sorted(value["fielding"]["judges"]) if value["fielding"] else []}
                                    for key, value in batches.items()],
                 "source_formats": sorted({row["source_format"] for row in ballots}),
                 "excluded_calibration_ballots": len(state["ballots"]) - len(ballots)})
    warnings = [f"Provisional ranking: incomplete batches {', '.join(incomplete)}"] if incomplete else []
    if any(row["source_format"] == "edsl.Results"
           and state["batches"][row["batch_id"]]["fielding"]["model"]["inference_service"] == "test"
           for row in ballots):
        warnings.append("Includes test-model results: software fixtures, not evidence about entrant preferences.")
    if bootstrap:
        data["uncertainty"] = perturbation(state["entrants"], ballots, data, draws=bootstrap, cluster=cluster,
                                           seed=seed, regularization=regularization, weighting=weighting)
    data["warnings"] = warnings
    return data


@main.group()
def calibrate():
    """Plan and analyze repeated subsets. Export and run their batches separately."""


@calibrate.command("plan")
@click.argument("calibration_id")
@click.option("--batch-sizes", default="4,8,12,16", show_default=True)
@click.option("--sample", type=click.IntRange(min=2), default=40, show_default=True)
@click.option("--subsets", type=click.IntRange(min=2), default=10, show_default=True)
@click.option("--repeats", type=click.IntRange(min=2), default=3, show_default=True)
@click.option("--seed", type=int, default=0, show_default=True)
@click.pass_obj
def calibrate_plan(store, calibration_id, batch_sizes, sample, subsets, repeats, seed):
    """Save comparable candidate-size designs without model execution."""
    sizes = [int(part.strip()) for part in batch_sizes.split(",")]
    with store.update("calibrate.plan") as (state, _):
        result = plan_calibration(state, calibration_id, sizes, sample=sample, subsets=subsets,
                                  repeats=repeats, seed=seed)
    emit(result, next_steps=[shlex.join(["zermelo", "--project", str(store.root), "batch", "export", key, "--help"])
                            for key in result["batch_ids"]])


@calibrate.command("analyze")
@click.argument("calibration_id")
@click.option("--max-disagreement", type=click.FloatRange(0, 1), default=.1, show_default=True)
@click.option("--costs", type=click.Path(exists=True, path_type=Path, dir_okay=False),
              help='JSON estimated dollars per call by size, e.g. {"4": 0.001, "8": 0.002}.')
@click.option("--reference", type=click.Path(exists=True, path_type=Path, dir_okay=False),
              help="JSON array of every snapshot entrant ID in a justified known order.")
@click.option("--output", type=click.Path(path_type=Path, dir_okay=False))
@click.pass_obj
def calibrate_analyze(store, calibration_id, max_disagreement, costs, reference, output):
    """Measure within-judge disagreement and recommend among completed candidate sizes."""
    data = analyze_calibration(store.load(), calibration_id, max_disagreement=max_disagreement,
                               costs=read_json(costs) if costs else None,
                               reference=read_json(reference) if reference else None)
    if output:
        write_new(output, data)
    emit(data)


@main.command("budget")
@click.option("--entrants", "entrant_count", type=click.IntRange(min=2), help="Defaults to this project's entrant count.")
@click.option("--chunk-size", type=click.IntRange(min=2), default=5, show_default=True)
@click.option("--calls", type=click.IntRange(min=0), default=0, show_default=True, help="Includes all judges and repeats.")
@click.option("--cost-per-call", type=click.FloatRange(min=0), help="User-supplied dollar estimate, not automatic pricing.")
@click.option("--budget", "dollar_budget", type=click.FloatRange(min=0), help="Dollar planning budget, not an enforced cap.")
@click.pass_obj
def budget_command(store, entrant_count, chunk_size, calls, cost_per_call, dollar_budget):
    """Show a noiseless exact-sort lower bound and a transparent cost estimate."""
    n = entrant_count if entrant_count is not None else len(store.load()["entrants"])
    emit(information_budget(n, chunk_size, calls, cost_per_call, dollar_budget))


@main.command("assess")
@click.argument("previous", type=click.Path(exists=True, path_type=Path, dir_okay=False))
@click.option("--tolerance", type=click.FloatRange(0, 1), default=.02, show_default=True,
              help="Maximum movement as a fraction of the list, not error relative to truth.")
@click.option("--bootstrap", type=click.IntRange(min=20), default=200, show_default=True)
@click.option("--cluster", type=click.Choice(["task", "judge"]), default="task", show_default=True)
@click.option("--seed", type=int, default=0, show_default=True)
@click.option("--output", type=click.Path(path_type=Path, dir_okay=False))
@click.pass_obj
def assess(store, previous, tolerance, bootstrap, cluster, seed, output):
    """Compare a previous rank JSON snapshot with a fit after new complete ballots."""
    prior = read_json(previous)
    if "data" in prior and "rankings" not in prior:
        prior = prior["data"]
    settings = dict(prior.get("settings", {}))
    if not settings or settings.get("method") not in {"pl", "bt"}:
        raise ZermeloError("incompatible_snapshot", "Use a zermelo rank --method pl|bt JSON snapshot")
    if settings.get("weighting") == "whole-ballot":
        settings["weighting"] = "entrant"
    state = store.load()
    current = fit_project(state, **settings)
    assess_snapshot(state, prior, current, tolerance)  # Validate before expensive perturbation fits.
    current["uncertainty"] = perturbation(state["entrants"], ranking_ballots(state), current, draws=bootstrap,
                                           cluster=cluster, seed=seed, regularization=settings["regularization"],
                                           weighting=settings["weighting"])
    data = assess_snapshot(state, prior, current, tolerance)
    data["current_snapshot"] = current
    if output:
        write_new(output, data)
    emit(data)
