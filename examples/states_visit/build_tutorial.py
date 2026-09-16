"""Build the package's worked tutorial from the preserved states run."""

import html
import json
import pprint
import re
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

from diagnostic_plots import build_diagnostics
from edsl import Agent, AgentList, Results
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexer import inherit
from pygments.lexers import BashLexer, JsonLexer, PythonLexer
from pygments.token import Name

from zermelo.design import adaptive_design
from zermelo.diagnostics import information_budget, perturbation
from zermelo.scoring import score
from zermelo.store import Store


class TutorialBashLexer(BashLexer):
    """Color the tutorial's external commands and flags as well as shell syntax."""

    tokens = {
        "root": [
            (r"(?<!\S)(?:zermelo|ep|python|mkdir)\b", Name.Function),
            (r"(?<!\S)--?[a-zA-Z][\w-]*", Name.Attribute),
            inherit,
        ],
    }


def main():
    root = Path(sys.argv[1]).resolve()
    output = Path("docs")
    assets = output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    state = Store(root).load()
    batch = state["batches"]["main"]
    design, manifest = batch["design"], batch["fielding"]
    analysis = json.loads((root / "reports/analysis.json").read_text())
    ballots = list(state["ballots"].values())
    for key in analysis["labels"]:
        selected = ballots if key == "pooled" else [row for row in ballots if row["judge_id"] == key]
        analysis["series"][key]["pl"] = score(state["entrants"], selected, method="pl")
    pl = analysis["series"]["pooled"]["pl"]
    uncertainty = perturbation(state["entrants"], ballots, pl, draws=200, seed=20260915)
    diagnostics = build_diagnostics(state, pl, uncertainty, analysis["labels"], assets)
    # Re-export only the synthetic rankers, never the original response payloads.
    with tempfile.TemporaryDirectory() as temp:
        native_agents = AgentList([Agent.from_dict(agent) for agent in manifest["judges"].values()])
        native_path = Path(temp) / "agent_list.ep"
        native_agents.git.save(native_path, message="Six synthetic traveler profiles from the worked example")
        shutil.copyfile(native_path, assets / "agent_list.ep")
    results = Results.git.load(root / "batches/main/results.ep")
    names = {row["id"]: row["name"] for row in state["entrants"]}
    sample = []
    for result in results[:6]:
        data = result.to_dict(add_edsl_version=False)
        judge = data["agent"]["traits"]["elo_judge_id"]
        codes = data["answer"]["ranking"]
        sample.append({"judge_id": judge, "label": analysis["labels"][judge], "codes": codes,
                       "ranking": [data["scenario"][f"option_{code}"] for code in codes],
                       "comment": data["comments_dict"]["ranking_comment"]})
    token_cost, input_tokens, output_tokens = 0.0, 0, 0
    for path in [root / "batches/main/results.ep", root / "retries/retry-02.results.ep",
                 root / "retries/retry-01-format.results.ep"]:
        for result in Results.git.load(path):
            raw = result.to_dict(add_edsl_version=False).get("raw_model_response", {})
            token_cost += raw.get("ranking_cost") or 0
            input_tokens += raw.get("ranking_input_tokens") or 0
            output_tokens += raw.get("ranking_output_tokens") or 0
    # Export only selected synthetic example data. No account details, raw API
    # payloads, private run links, or machine-specific paths enter public docs.
    data = {"schema_version": 1, "names": names, "samples": sample, "groups": design["tasks"][:3],
            "labels": analysis["labels"], "series": analysis["series"],
            "comparison": analysis["comparison"], "model": manifest["model"],
            "design_hash": design["design_hash"], "input_hash": analysis["input_hash"],
            "expected_rankings": 390, "observed_rankings": 390, "implied_wins": 3900,
            "unique_pairs": 518, "possible_pairs": 1225,
            "bt_elo_spearman": analysis["bt_elo_spearman"], "shared_top_10": analysis["shared_top_10"],
            "rounds_4_vs_5_spearman": analysis["rounds_4_vs_5_spearman"],
            "token_cost_sum_usd": token_cost, "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_estimate_usd": 0.2877, "initial_job_reported_cost_usd": 0.1087,
            "first_pass_valid": 388, "format_clarified_ballots": 1, "pl_uncertainty": uncertainty, "diagnostics": diagnostics}
    (assets / "states-example.json").write_text(json.dumps(data, indent=2) + "\n")
    shutil.copyfile(root / "reports/rank-comparison.csv", assets / "state-ranks.csv")
    shutil.copyfile(root / "reports/traveler-ranks.png", assets / "traveler-ranks.png")
    shutil.copyfile(root / "reports/traveler-ranks.svg", assets / "traveler-ranks.svg")

    def esc(value):
        return html.escape(str(value))

    formatter = HtmlFormatter(nowrap=True)

    def syntax(text, language):
        lexer = {"bash": TutorialBashLexer, "json": JsonLexer, "python": PythonLexer}[language](stripnl=False, ensurenl=False)
        return highlight(text, lexer, formatter).removesuffix("\n")

    def command(text, captured=None, label=None, excerpt=False, language="bash"):
        if language == "bash":
            text = re.sub(r'"(runs/states[^"\n]*)"', r'\1', text)
        label = label or ("Bash" if language == "bash" else language.title())
        block = '<div class="command"><div class="command-head"><span>' + esc(label)
        block += '</span><button class="copy" type="button">Copy</button></div><pre><code class="syntax language-' + language + '">' + syntax(text, language) + '</code></pre></div>'
        if captured is not None:
            capture = captured if isinstance(captured, str) else json.dumps(captured, indent=2)
            block += '<details class="capture"><summary>Show command output'
            block += ' <span>(selected fields)</span>' if excerpt else ''
            block += '</summary><pre><code class="syntax language-json">' + syntax(capture, 'json') + '</code></pre></details>'
        return block

    def log(name):
        return json.loads((root / "logs" / name).read_text())

    def table(headers, rows, caption=None):
        return '<div class="table-wrap"><table>' + ('<caption>' + esc(caption) + '</caption>' if caption else '') + \
            '<thead><tr>' + ''.join('<th scope="col">' + esc(cell) + '</th>' for cell in headers) + \
            '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + esc(cell) + '</td>' for cell in row) + '</tr>'
                                           for row in rows) + '</tbody></table></div>'

    figures = {"HIGHLIGHT_CSS": HtmlFormatter(style="monokai").get_style_defs(".command .syntax") + "\n" +
                                HtmlFormatter(style="default").get_style_defs(".capture .syntax")}
    figures["SET_PROJECT"] = command('mkdir -p runs/states\nzermelo project use runs/states')
    figures["PREPARE"] = command('python examples/states_visit/prepare.py "runs/states/inputs"',
                                 {"states": 50, "profiles": 6, "output": "runs/states/inputs", "agent_list": "runs/states/inputs/agent_list.ep"})
    # Preserve spaces exactly: Bash removes each backslash-newline inside quotes.
    criterion_lines = textwrap.wrap(state["criterion"], width=64, drop_whitespace=False,
                                    replace_whitespace=False, break_long_words=False, break_on_hyphens=False)
    criterion = "\\\n".join(re.sub(r'([\\"$`])', r'\\\1', line) for line in criterion_lines)
    figures["INIT"] = command('zermelo init \\\n  --criterion "' + criterion + '"',
                              {"status": "ok", "data": {"project": "runs/states", "criterion": state["criterion"]}}, excerpt=True)
    figures["IMPORT_ENTRANTS"] = command('zermelo entrants import "runs/states/inputs/entrants.csv"', log("entrants.json"))
    figures["ENTRANT_SAMPLE"] = table(["ID", "Name", "Information supplied"],
                                       [[key, names[key], next(e["description"] for e in state["entrants"] if e["id"] == key)]
                                        for key in ["CO", "HI", "IL"]])
    figures["AGENTS"] = table(["Synthetic traveler", "Stated preferences"],
                               [[p["traits"]["profile_name"], p["traits"]["travel_preferences"]]
                                for p in analysis["profiles"]])
    profiles = [{"id": key, "traits": {k: v for k, v in agent["traits"].items() if k != "elo_judge_id"}}
                for key, agent in manifest["judges"].items()]
    figures["RANKERS_SOURCE"] = command(
        'from edsl import Agent, AgentList\n\nprofiles = ' + pprint.pformat(profiles, width=85, sort_dicts=False) +
        '\n\nrankers = AgentList([Agent(name=p["id"], traits=p["traits"]) for p in profiles])\n'
        'rankers.git.save("agent_list.ep")', language="python")
    figures["RANKERS_ADD"] = command('zermelo rankers add "runs/states/inputs/agent_list.ep"\nzermelo rankers list')
    figures["PLAN"] = command('zermelo batch plan main \\\n  --chunk-size 5 --rounds 5 --seed 20260914',
                              {"status": "ok", "data": {"batch_id": "main", "chunk_size": 5, "rounds": 5,
                                 "seed": 20260914, "coverage": {"unique_pairs": 518, "possible_pairs": 1225},
                                 "design_hash": design["design_hash"]}}, excerpt=True)
    group_html = []
    for i, group in enumerate(design["tasks"][:3]):
        shared = set(group["entrants"]) & set(design["tasks"][i-1]["entrants"]) if i else set()
        shared |= set(group["entrants"]) & set(design["tasks"][i+1]["entrants"]) if i < 2 else set()
        chips = ''.join('<span class="state-chip' + (' bridge' if key in shared else '') + '">' + esc(names[key]) + '</span>'
                        for key in group["entrants"])
        group_html.append('<div class="group-row"><strong>Group ' + str(i+1) + '</strong><div>' + chips + '</div></div>')
    figures["GROUPS"] = ''.join(group_html)
    figures["EXPORT"] = command('zermelo batch export main \\\n  --model gemini-3.1-flash-lite --service google \\\n  --output "runs/states/ranking_job.ep" \\\n  --model-parameters "runs/states/inputs/model-parameters.json"',
                                {"status": "ok", "data": {"scenario_count": 65, "agent_count": 6, "question_count": 1,
                                 "model_count": 1, "iterations": 1, "expected_model_calls": 390,
                                 "model": manifest["model"], "jobs_path": "runs/states/ranking_job.ep", "results_path": "runs/states/ranking_results.ep",
                                 "execution": "external via ep run"}}, excerpt=True)
    figures["COST"] = command('ep jobs cost "runs/states/ranking_job.ep"', log("cost-estimate-live.json"))
    figures["RUN"] = command('ep run --jobs runs/states/ranking_job.ep \\\n  --n 1 --task-timeout 900 \\\n  --remote_inference_results_visibility private \\\n  --output runs/states/ranking_results.ep')
    initial = log("import-initial-codes.json")["data"]
    figures["IMPORT_RESULTS"] = command('zermelo results import main \\\n  "runs/states/ranking_results.ep" --skip-invalid',
                                        {"status": "warning", "data": {key: initial[key] for key in
                                         ["added", "duplicates", "native_code_rows_mapped", "rejected", "coverage"]}}, excerpt=True)
    figures["RETRY_EXPORT"] = command('python examples/states_visit/retry_jobs.py "runs/states"',
                                      {"assignments": [{"task_id": "main-t000046", "judge_id": "family", "iteration": 0},
                                                       {"task_id": "main-t000060", "judge_id": "city_culture", "iteration": 0}]}, excerpt=True)
    figures["RETRY_RUN"] = command('ep run --jobs "runs/states/retries/retry-02.jobs.ep" \\\n  --fresh --task-timeout 900 \\\n  --remote_inference_results_visibility private \\\n  --output "runs/states/retries/retry-02.results.ep"',
                                   {"status": "ok", "data": {"meta": {"result_count": 1, "run_status": "complete",
                                    "completed_interview_count": 1, "failed_interview_count": 0}}}, excerpt=True)
    figures["RETRY_IMPORT"] = command('zermelo results import main \\\n  "runs/states/retries/retry-02.results.ep"',
                                      {"status": "warning", "data": {"added": 1, "duplicates": 0,
                                       "coverage": {"expected": 390, "received": 389, "complete": False}}}, excerpt=True)
    figures["FINAL_IMPORT"] = command('zermelo results import main \\\n  "runs/states/retries/retry-01-format.results.ep"',
                                      {"status": "ok", "data": {"added": 1, "duplicates": 0, "native_code_rows_mapped": 1,
                                       "coverage": {"expected": 390, "received": 390, "missing": [], "complete": True}}}, excerpt=True)
    figures["BT_RANK"] = command('zermelo rank --method bt --output "runs/states/rankings-bt.csv"',
                              {"status": "ok", "data": {"method": "bt", "weighting": "entrant", "complete": True,
                               "diagnostics": analysis["series"]["pooled"]["bt"]["diagnostics"],
                               "rankings": analysis["series"]["pooled"]["bt"]["rankings"][:5]}}, excerpt=True)
    figures["RANK"] = command('zermelo rank --method pl --output runs/states/rankings.csv')
    figures["ELO"] = command('zermelo rank --method elo \\\n  --output "runs/states/rankings-elo.json"',
                             {"status": "ok", "data": {"method": "elo", "complete": True,
                              "diagnostics": analysis["series"]["pooled"]["elo"]["diagnostics"]}}, excerpt=True)
    comparison = {row["id"]: row for row in analysis["comparison"]}
    figures["TOP_TEN"] = table(["BT rank", "State", "BT rating", "Elo rank"],
                                [[row["rank"], row["name"], f"{row['rating']:.1f}", comparison[row["id"]]["pooled_elo_rank"]]
                                 for row in analysis["series"]["pooled"]["bt"]["rankings"][:10]])
    figures["PROFILE_TOPS"] = table(["Traveler", "Five most preferred states"],
                                     [[label, ', '.join(row["name"] for row in analysis["series"][key]["pl"]["rankings"][:5])]
                                      for key, label in analysis["labels"].items() if key != "pooled"])
    figures["CODE_INSPECTION"] = command('zermelo batch show main',
                                          {"design": {"tasks": design["tasks"][:1]}}, excerpt=True)
    figures["REGISTER_MORE"] = command('zermelo batch plan followup \\\n  --chunk-size 5 --rounds 5 --seed 20260915')
    figures["PL_REFIT"] = command('zermelo rank --method pl --bootstrap 200 --seed 20260915 '
                                   '--output "runs/states/rankings-pl.json"',
                                   {"method": "pl", "ballots": len(ballots), "cluster": "task", "clusters": uncertainty["clusters"],
                                    "draws": 200, "max_rank_movement_p95": uncertainty["max_rank_movement_p95"],
                                    "expected_adjacent_reversals_under_perturbation":
                                    uncertainty["expected_adjacent_reversals_under_perturbation"]}, excerpt=True)
    figures["PL_TOP"] = table(["PL rank", "State", "Rating", "Task-perturbation rank range (2.5–97.5%)"],
                               [[row["rank"], row["name"], f"{row['rating']:.1f}",
                                 f"{uncertainty['entrants'][row['id']]['rank_p025']:.1f}–"
                                 f"{uncertainty['entrants'][row['id']]['rank_p975']:.1f}"]
                                for row in pl["rankings"][:10]])
    preview = adaptive_design(state, "refinement", 5, 1, 20260915, task_count=30)
    figures["ADAPTIVE_PLAN"] = command('zermelo batch plan refinement --strategy neighborhood '
                                       '--chunk-size 5 --rounds 1 --tasks 30 --bridge-frac .1 --seed 20260915',
                                       {"tasks": 30, "mandatory_coverage_tasks": preview["selection"]["mandatory_tasks"],
                                        "random_bridges": preview["selection"]["random_bridge_tasks"],
                                        "planned_calls_with_six_judges": 180, "executed": False}, excerpt=True)
    figures["ADAPTIVE_GROUPS"] = table(["Task kind", "Example states"],
        [[kind, ', '.join(names[key] for key in next(t for t in preview["tasks"] if t["selection"] == kind)["entrants"])]
         for kind in ["coverage-chain", "random-bridge", "neighborhood"]])
    figures["CALIBRATE_PLAN"] = command('zermelo calibrate plan pilot --sample 40 '
                                        '--batch-sizes 4,8,12,16 --subsets 10 --repeats 3 --seed 42')
    figures["CALIBRATE_EXPORT"] = command('zermelo batch export pilot-k4 '
                                          '--model gemini-3.1-flash-lite --service google '
                                          '--output "runs/states/pilot-k4_job.ep" '
                                          '--model-parameters "runs/states/inputs/model-parameters.json"')
    figures["CALIBRATE_ANALYZE"] = command('zermelo calibrate analyze pilot '
                                           '--max-disagreement .1 --output "runs/states/calibration.json"')
    figures["INFO_BUDGET"] = command('zermelo budget --entrants 10000 --chunk-size 10 --calls 500 '
                                      '--cost-per-call .002 --budget 5',
                                      information_budget(10000, 10, 500, .002, 5), excerpt=True)
    figures["ASSESS"] = command('zermelo assess "runs/states/rankings-pl.json" '
                                 '--tolerance .02 --bootstrap 200 --output "runs/states/assessment.json"')
    figures["INCREMENTAL"] = command('zermelo entrants import more.csv\n'
                                      'zermelo batch plan newcomers --only-new '
                                      '--chunk-size 5 --rounds 1 --seed 44')
    figures["SCORE_COEF"] = f"{400 / __import__('math').log(10):.2f}"
    figures["TOKEN_COST"] = f"{token_cost:.6f}"
    figures["INPUT_TOKENS"] = f"{input_tokens:,}"
    figures["OUTPUT_TOKENS"] = f"{output_tokens:,}"
    figures["DIAGNOSTIC_FACTS"] = table(["Diagnostic", "What this run contains"], [
        ["Comparison coverage", f"{diagnostics['coverage']['unique_pairs']} of {diagnostics['coverage']['possible_pairs']} pairs; "
         f"{diagnostics['coverage']['tasks']} distinct tasks"],
        ["Task perturbations", "200 re-fits of 65 task clusters, keeping the six rankers together"],
        ["Traveler disagreement", "Each profile pair compared on 65 shared tasks"],
        ["Round stability", "Cumulative PL fits through rounds 1 to 5; overlapping evidence"]])
    figures["DATA"] = json.dumps(data).replace("<", "\\u003c")
    template = Path(__file__).with_name("tutorial.template.html").read_text()
    for key, value in figures.items():
        template = template.replace("@@" + key + "@@", value)
    assert "@@" not in template, "Unfilled tutorial placeholder"
    (output / "index.html").write_text(template)
    print(json.dumps({"tutorial": str(output / "index.html"), "source_run": root.name,
                      "ballots": len(state["ballots"]), "token_cost_sum_usd": token_cost}))


if __name__ == "__main__":
    main()
