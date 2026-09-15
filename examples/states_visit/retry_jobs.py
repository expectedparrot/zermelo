"""Export one native Jobs artifact per missing assignment; execution stays external."""

import json
import shlex
import sys
from pathlib import Path

from edsl import AgentList, Jobs, ScenarioList

from zermelo.fielding import artifact_path, coverage
from zermelo.store import Store, digest


def main():
    root = Path(sys.argv[1]).resolve()
    state = Store(root).load()
    batch = state["batches"]["main"]
    original = Jobs.git.load(artifact_path(Store(root), "main", "jobs_path"))
    missing = coverage(state, "main")["missing"]
    output = root / "retries"
    output.mkdir(exist_ok=False)
    assignments = []
    for index, cell in enumerate(missing, 1):
        if cell["iteration"] != 0:
            raise ValueError("This example declares one iteration; unexpected repeat")
        scenario = next(row for row in original.scenarios if row["elo_task_id"] == cell["task_id"])
        agent = next(row for row in original.agents if row.traits["elo_judge_id"] == cell["judge_id"])
        jobs = original.survey.by(ScenarioList([scenario])).by(AgentList([agent])).by(original.models[0])
        path = output / f"retry-{index:02d}.jobs.ep"
        jobs.git.save(path, message="Retry one missing state-ranking assignment without changing its identity")
        assert digest(Jobs.git.load(path).to_dict()) == digest(jobs.to_dict())
        result_path = output / f"retry-{index:02d}.results.ep"
        command = ["ep", "run", "--jobs", str(path), "--fresh", "--task-timeout", "900",
                   "--remote_inference_results_visibility", "private", "--output", str(result_path)]
        assignments.append({**cell, "jobs": str(path), "results": str(result_path),
                            "command": shlex.join(command)})
    data = {"schema_version": 1, "original_design_hash": batch["design"]["design_hash"],
            "input_hash": digest(state), "assignments": assignments}
    (output / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
