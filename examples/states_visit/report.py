"""Render a local report from registered live state-ranking results."""

import csv
import html
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from zermelo.fielding import coverage  # noqa: E402
from zermelo.scoring import score  # noqa: E402
from zermelo.store import Store, digest  # noqa: E402


def save_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    root = Path(sys.argv[1]).resolve()
    state = Store(root).load()
    assert all(coverage(state, key)["complete"] for key in state["batches"]), "Incomplete live results"
    output = root / "reports"
    output.mkdir(exist_ok=True)
    if (output / "index.html").exists():
        raise SystemExit("Report already exists; preserve it before rebuilding")
    ballots = list(state["ballots"].values())
    assert {ballot["source_format"] for ballot in ballots} == {"edsl.Results"}
    batch = state["batches"]["main"]
    manifest = batch["fielding"]
    entrants = state["entrants"]
    profiles = [{"id": key, "traits": agent["traits"]} for key, agent in manifest["judges"].items()]
    labels = {profile["id"]: profile["traits"]["profile_name"] for profile in profiles}
    series = {}
    all_labels = {"pooled": "All six travelers", **labels}
    for key in all_labels:
        selected = ballots if key == "pooled" else [row for row in ballots if row["judge_id"] == key]
        series[key] = {method: score(entrants, selected, method=method) for method in ["bt", "elo"]}
        for method in series[key]:
            save_csv(output / f"{key}-{method}.csv", series[key][method]["rankings"])
    pooled = series["pooled"]["bt"]
    ids = [row["id"] for row in pooled["rankings"]]
    pooled_rank = {row["id"]: row["rank"] for row in pooled["rankings"]}
    elo_rank = {row["id"]: row["rank"] for row in series["pooled"]["elo"]["rankings"]}
    agreement = float(spearmanr([pooled_rank[key] for key in ids], [elo_rank[key] for key in ids]).statistic)
    bt_top = {row["id"] for row in pooled["rankings"][:10]}
    elo_top = {row["id"] for row in series["pooled"]["elo"]["rankings"][:10]}
    task_round = {task["id"]: task["round"] for task in batch["design"]["tasks"]}
    early = score(entrants, [row for row in ballots if task_round[row["task_id"]] <= 4])
    early_rank = {row["id"]: row["rank"] for row in early["rankings"]}
    stability = float(spearmanr([pooled_rank[key] for key in ids], [early_rank[key] for key in ids]).statistic)
    profile_ranks = {key: {row["id"]: row["rank"] for row in series[key]["bt"]["rankings"]} for key in labels}
    comparison_rows = [{"state": row["name"], "id": row["id"], "pooled_bt_rank": row["rank"],
                        "pooled_elo_rank": elo_rank[row["id"]],
                        **{key: profile_ranks[key][row["id"]] for key in labels}} for row in pooled["rankings"]]
    save_csv(output / "rank-comparison.csv", comparison_rows)
    estimate = json.loads((root / "logs/cost-estimate-live.json").read_text())["data"]["usd"]
    data = {"schema_version": 1, "source": "Live EP inference, not test-model fixtures", "input_hash": digest(state),
            "model": manifest["model"], "labels": all_labels, "series": series,
            "expected_ballots": manifest["expected_model_calls"], "observed_ballots": len(ballots),
            "implied_wins": pooled["diagnostics"]["implied_wins"],
            "unique_pairs": pooled["diagnostics"]["unique_pairs"], "possible_pairs": 1225,
            "cost_estimate_usd": estimate, "bt_elo_spearman": agreement, "shared_top_10": len(bt_top & elo_top),
            "rounds_4_vs_5_spearman": stability, "comparison": comparison_rows,
            "criterion": state["criterion"], "profiles": profiles,
            "registrations": batch["imports"]}
    billing_path = root / "logs/billing.json"
    if billing_path.exists():
        data["billing"] = json.loads(billing_path.read_text())
    clarification_path = root / "retries/format-clarification.json"
    if clarification_path.exists():
        data["format_clarification"] = json.loads(clarification_path.read_text())
    (output / "analysis.json").write_text(json.dumps(data, indent=2) + "\n")

    matrix = np.array([[profile_ranks[key][entrant] for key in labels] for entrant in ids])
    fig, ax = plt.subplots(figsize=(10, 16))
    im = ax.imshow(matrix, cmap="viridis_r", vmin=1, vmax=50, aspect="auto")
    ax.set_xticks(range(6), ["Outdoors", "City &\nculture", "Beach &\nrelaxation", "Food &\nmusic", "History", "Family"])
    ax.xaxis.tick_top()
    ax.tick_params(axis="both", length=0)
    ax.set_yticks(range(50), [f"{row['rank']:2d}  {row['name']}" for row in pooled["rankings"]], fontsize=8)
    for i in range(50):
        for j in range(6):
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center", fontsize=7,
                    color="white" if matrix[i, j] > 27 else "#172b35")
    ax.set_title("50 states, six synthetic travelers\nRows ordered by pooled Bradley–Terry rank", pad=43, loc="left")
    fig.colorbar(im, ax=ax, shrink=0.35, label="Rank within traveler profile (1 = most preferred)")
    fig.text(0.02, 0.012, "Live model-generated judgments; not a survey of real travelers. Each profile ranked five states at a time.", fontsize=8)
    fig.tight_layout(rect=(0, 0.025, 1, 1))
    fig.savefig(output / "traveler-ranks.png", dpi=160)
    fig.savefig(output / "traveler-ranks.svg")
    plt.close(fig)

    tops = {key: [row["name"] for row in series[key]["bt"]["rankings"][:5]] for key in all_labels}
    lines = ["# Where would six travelers like to go?", "", "## Live run", "",
             "- 50 U.S. states, six synthetic traveler profiles, five rounds, five states per task.",
             f"- {len(ballots)}/{manifest['expected_model_calls']} valid live rankings; {data['implied_wins']:,} implied wins.",
             f"- Model: {manifest['model']['model']} through {manifest['model']['inference_service']}.",
             f"- {data['unique_pairs']}/{data['possible_pairs']} unique state pairs observed per traveler; connected coverage.",
             f"- EP's pre-run estimate: ${estimate:.4f}.",
             "- Initial import: 388 valid ballots; failed assignments were retried separately and merged without double counting.",
             *([f"- Total reported EP job charges: ${data['billing']['total_usd']:.4f} across "
                f"{len(data['billing']['jobs'])} submissions."] if "billing" in data else []), "", "## Pooled top 10", "",
             "| Rank | State | BT rating | Elo rank |", "|---:|---|---:|---:|"]
    for row in pooled["rankings"][:10]:
        lines.append(f"| {row['rank']} | {row['name']} | {row['rating']:.1f} | {elo_rank[row['id']]} |")
    lines += ["", "## Each traveler's top five", "", "| Traveler | Top five states |", "|---|---|"]
    lines += [f"| {labels[key]} | {', '.join(tops[key])} |" for key in labels]
    lines += ["", "## Sensitivity checks", "",
              f"- Bradley–Terry versus Elo rank correlation: {agreement:.3f}; {len(bt_top & elo_top)}/10 shared top-ten states.",
              f"- Four rounds versus five rounds, pooled BT rank correlation: {stability:.3f}.",
              "- These are descriptive sensitivity checks, not confidence intervals or independent replications.", "",
              "## Interpretation", "",
              "These results show how one language model orders short, hand-authored state cards under six selected "
              "traveler profiles. The pooled ranking gives each profile the same number of ballots. "
              "It does not measure what actual Americans or a representative traveler population prefer. "
              "Cards are abbreviated and may influence the results; distance from home and seasonal disadvantages were set aside.",
              "", "A rating of 1500 is the arbitrary center of the scale. Differences express fitted pairwise preference "
              "strength, not tourism quality, star ratings, or absolute desirability. Elo is sensitive to ballot order. "
              "Wins implied by one ballot are dependent, so no independent-pair confidence intervals are reported.", "",
              "One repeatedly invalid ballot required a documented response-format reminder, with the same "
              "states, traveler, criterion, and model settings. Original and retry artifacts are preserved.", "",
              "See [the interactive report](index.html), [all rankings](rank-comparison.csv), "
              "[traveler heatmap](traveler-ranks.png), and [analysis data](analysis.json).", ""]
    (output / "summary.md").write_text("\n".join(lines))

    payload = json.dumps(data).replace("<", "\\u003c")
    cards = "".join(f"<article class='card'><h3>{html.escape(labels[key])}</h3><ol>"
                    + "".join(f"<li>{html.escape(name)}</li>" for name in tops[key]) + "</ol></article>" for key in labels)
    page = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>50 states · Six travelers</title><style>
:root{color-scheme:light;--ink:#19323b;--muted:#536971;--teal:#086d75;--paper:#f4f6f2}*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:40px 24px}
header{background:#12353e;color:white;padding:45px 32px;border-radius:20px}h1{font-size:clamp(32px,5vw,58px);line-height:1.1;letter-spacing:-1.5px;margin:12px 0}
.eyebrow{font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#91d6cb}header p{max-width:790px;color:#d7e5e5}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}
.metric,.card,.panel{background:white;border:1px solid #dce4df;border-radius:12px;padding:22px}.metric b{font-size:30px;display:block;line-height:1.2}.metric span{font-size:13px;color:var(--muted)}
h2{font-size:27px;margin:40px 0 12px}h3{font-size:17px;margin:0 0 12px}.sub{color:var(--muted);max-width:850px}.profiles{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.card ol{padding-left:22px;margin:0}
.controls{display:flex;gap:18px;flex-wrap:wrap;align-items:end;margin-bottom:20px}label{font-size:13px;display:block}select,input{display:block;font:inherit;padding:9px;border:1px solid #a8bcb4;border-radius:6px;background:white;color:var(--ink)}
.barrow{display:grid;grid-template-columns:160px 1fr 65px;gap:12px;align-items:center;margin:8px 0;font-size:14px}.track{background:#edf2ef;height:15px;border-radius:3px}.fill{height:100%;background:var(--teal);border-radius:3px}.barrow b{text-align:right;font-variant-numeric:tabular-nums}
.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th{text-align:left;border-bottom:2px solid #b4c6bd;white-space:nowrap}td,th{padding:10px 12px}td{border-bottom:1px solid #e6ece8}td.num{text-align:right;font-variant-numeric:tabular-nums}
.note{padding:18px 22px;border-left:4px solid #c79243;background:#fff8e9;margin-top:20px}a{color:var(--teal)}details{margin:20px 0}summary{cursor:pointer;font-weight:600}.foot{font-size:13px;color:var(--muted)}
@media(max-width:720px){main{padding:15px}.metrics{grid-template-columns:repeat(2,1fr)}.profiles{grid-template-columns:1fr}.barrow{grid-template-columns:120px 1fr 55px;font-size:12px}header{padding:28px 22px}}
</style><main><header><div class="eyebrow">Zermelo · Live Expected Parrot demonstration</div><h1>50 states.<br>Six ways to travel.</h1><p>Six synthetic travelers ranked small groups of states. Overlapping groups connect their choices into a ranking of all 50 states, without asking anyone to order the entire list at once.</p></header>
<section class="metrics"><div class="metric"><b>50</b><span>U.S. states</span></div><div class="metric"><b id="ballot-count"></b><span>valid live ranking tasks</span></div><div class="metric"><b id="win-count"></b><span>implied pairwise wins</span></div><div class="metric"><b id="pair-count"></b><span>of 1,225 distinct state pairs</span></div></section>
<div class="note"><strong>A demonstration of model preferences.</strong> These are selected synthetic personas using one model, not survey responses from real travelers. The state cards are short, illustrative summaries.</div>
<h2>Explore the rankings</h2><p class="sub">Switch traveler profiles to see what changes. Bradley–Terry fits all comparisons together; Elo updates ratings in a fixed order. Each view contains all 50 states.</p>
<section class="panel"><div class="controls"><div><label for="traveler">Traveler</label><select id="traveler"></select></div><div><label for="method">Scoring method</label><select id="method"><option value="bt">Bradley–Terry</option><option value="elo">Elo</option></select></div><div><label for="search">Find a state</label><input id="search" type="search" placeholder="State name"></div></div><div id="bars"></div><p class="foot">Top ten in the selected view. Bars show relative rating position among these 50 states; 1500 is an arbitrary midpoint.</p><div class="scroll"><table><thead><tr><th>Rank</th><th>State</th><th>Rating</th><th>Ballots</th><th>Wins</th><th>Losses</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<h2>Six distinct perspectives</h2><p class="sub">Top five states for each profile, using Bradley–Terry.</p><section class="profiles">__CARDS__</section>
<h2>How robust is the ordering?</h2><section class="panel"><p id="sensitivity"></p><p class="foot">These are descriptive sensitivity checks, not confidence intervals. Rankings can change with traveler profiles, state descriptions, model, and comparison design.</p></section>
<h2>How this was run</h2><section class="panel"><ol><li>Registered 50 state cards and six traveler profiles.</li><li>Generated five shuffled rounds of overlapping five-state groups: 65 tasks per traveler.</li><li>Ran 390 live interviews through EP with private results.</li><li>Validated and imported every complete ranking against its assigned states, traveler, model, and iteration.</li><li>Converted each five-state ranking into ten implied wins, weighted 1/4 each, and fit the overall and traveler-specific rankings.</li></ol><p id="model"></p><details><summary>Trip assumptions and interpretation</summary><p id="criterion"></p><p>Each state was treated as a first visit, in a favorable season, with distance from home set aside. The pooled result gives each profile the same number of ballots. Repeated judgments and implied wins within a ballot are dependent. No population or independent-pair uncertainty claims are made.</p></details></section>
<p class="foot">Artifacts: <a href="summary.md">written summary</a> · <a href="rank-comparison.csv">all ranks by profile</a> · <a href="traveler-ranks.png">rank heatmap</a> · <a href="analysis.json">analysis data</a>. Raw results, jobs, input cards, and registrations are preserved in the project directory.</p></main>
<script id="dataset" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.getElementById('dataset').textContent), traveler=document.getElementById('traveler'), method=document.getElementById('method'), search=document.getElementById('search');
Object.entries(data.labels).forEach(([key,label])=>traveler.add(new Option(label,key)));
document.getElementById('ballot-count').textContent=data.observed_ballots;
document.getElementById('win-count').textContent=data.implied_wins.toLocaleString();document.getElementById('pair-count').textContent=data.unique_pairs;
document.getElementById('sensitivity').textContent=`Bradley–Terry and Elo share ${data.shared_top_10} of their top ten states, with rank correlation ${data.bt_elo_spearman.toFixed(3)}. Comparing the first four rounds with all five gives a Bradley–Terry rank correlation of ${data.rounds_4_vs_5_spearman.toFixed(3)}.`;
document.getElementById('model').textContent=`Model: ${data.model.model} via ${data.model.inference_service}. EP's pre-run estimate: $${data.cost_estimate_usd.toFixed(4)}.${data.billing ? ' Total reported job charges: $'+data.billing.total_usd.toFixed(4)+'.' : ''} All ${data.expected_ballots} expected rankings are present after separately registered retries. One repeatedly invalid ballot required a documented response-format reminder with the same traveler, states, criterion, and model settings.`;
document.getElementById('criterion').textContent=data.criterion;
function render(){const rows=data.series[traveler.value][method.value].rankings, min=Math.min(...rows.map(r=>r.rating)), max=Math.max(...rows.map(r=>r.rating)); const bars=document.getElementById('bars');bars.replaceChildren();rows.slice(0,10).forEach(r=>{const row=document.createElement('div');row.className='barrow';const name=document.createElement('span');name.textContent=r.name;const track=document.createElement('div');track.className='track';const fill=document.createElement('div');fill.className='fill';fill.style.width=`${100*(r.rating-min)/(max-min||1)}%`;track.append(fill);const val=document.createElement('b');val.textContent=r.rating.toFixed(1);row.append(name,track,val);bars.append(row)});const body=document.getElementById('rows');body.replaceChildren();rows.filter(r=>r.name.toLowerCase().includes(search.value.toLowerCase())).forEach(r=>{const tr=document.createElement('tr');[r.rank,r.name,r.rating.toFixed(1),r.ballots,r.wins,r.losses].forEach((v,i)=>{const td=document.createElement('td');td.textContent=v;if(i>1)td.className='num';tr.append(td)});body.append(tr)})}
traveler.addEventListener('change',render);method.addEventListener('change',render);search.addEventListener('input',render);render();
</script></html>'''
    (output / "index.html").write_text(page.replace("__CARDS__", cards).replace("__DATA__", payload))
    print(json.dumps({"report": str(output / "index.html"), "tops": tops,
                      "bt_elo_spearman": agreement, "shared_top_10": len(bt_top & elo_top),
                      "rounds_4_vs_5_spearman": stability}, indent=2))


if __name__ == "__main__":
    main()
