"""Shared local helpers. Model execution is exclusively an external ep run."""

import json
from pathlib import Path

from click.testing import CliRunner

from zermelo.store import Store, write_new


def command(project, *args):
    from zermelo.cli import main

    result = CliRunner().invoke(main, ["--project", str(project), *map(str, args)])
    try:
        envelope = json.loads(result.output)
    except ValueError as exc:
        raise RuntimeError(f"Non-JSON CLI output for {args}: {result.output}") from exc
    logs = Path(project) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    index = len(list(logs.glob('*.json'))) + 1
    write_new(logs / f"{index:03d}-{'-'.join(str(x) for x in args[:2]).replace('/', '_')}.json", envelope)
    if result.exit_code:
        raise RuntimeError(envelope["errors"])
    return envelope["data"]


def export(project, batch, model, service):
    return command(project, "batch", "export", batch, "--model", model, "--service", service,
                   "--model-parameters", Path(project) / "inputs/model-parameters.json",
                   "--output", Path(project) / f"{batch}_job.ep")


def jobs(root):
    """Inventory frozen jobs without touching their bytes or submitting inference."""
    result = []
    for path in sorted(Path(root).glob('*/study.json')):
        study = json.loads(path.read_text())
        for project in study["projects"]:
            directory = Path(root) / project
            state = Store(directory).load()
            for batch, data in state["batches"].items():
                if data["fielding"]:
                    result.append({"study": study["key"], "project": str(directory), "batch": batch,
                                   **data["fielding"]})
    return result
