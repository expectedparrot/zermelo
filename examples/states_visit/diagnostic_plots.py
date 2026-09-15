"""Publication-friendly diagnostics from the preserved live states ballots."""

from collections import Counter, defaultdict
from itertools import combinations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from zermelo.calibration import kendall_distance
from zermelo.scoring import score


def build_diagnostics(state, fit, uncertainty, labels, output):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.labelcolor": "#203329", "text.color": "#203329", "svg.hashsalt": "zermelo"})
    ballots = list(state["ballots"].values())
    ids = [row["id"] for row in fit["rankings"]]
    names = {row["id"]: row["name"] for row in fit["rankings"]}
    index = {key: i for i, key in enumerate(ids)}
    paths = {}

    def save(fig, name):
        for suffix in ["png", "svg"]:
            path = output / f"{name}.{suffix}"
            fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="#fafaf6",
                        metadata={"Date": None} if suffix == "svg" else None)
        paths[name] = {"png": f"assets/{name}.png", "svg": f"assets/{name}.svg"}
        plt.close(fig)

    # Count distinct task contexts, not six implied independent copies per task.
    tasks = {(row["batch_id"], row["task_id"]): row["ranking"] for row in ballots}
    matrix = np.zeros((len(ids), len(ids)), dtype=int)
    for ranking in tasks.values():
        for left, right in combinations(ranking, 2):
            i, j = index[left], index[right]
            matrix[i, j] += 1
            matrix[j, i] += 1
    fig, ax = plt.subplots(figsize=(9, 8), layout="constrained")
    color = plt.get_cmap("YlGnBu").copy()
    color.set_bad("#f0f0e9")
    values = np.ma.masked_where(matrix == 0, matrix)
    chart = ax.imshow(values, cmap=color, vmin=1, vmax=max(2, matrix.max()))
    ax.set_xticks(range(len(ids)), ids, fontsize=7, rotation=90)
    ax.set_yticks(range(len(ids)), ids, fontsize=7)
    ax.set_xlabel("State · ordered by pooled Plackett–Luce rank")
    ax.set_title("Which states were actually compared?", loc="left", pad=20, fontsize=16)
    fig.colorbar(chart, ax=ax, shrink=.65, label="Distinct five-state tasks shared by the pair")
    save(fig, "comparison-coverage")

    top = fit["rankings"][:20]
    fig, ax = plt.subplots(figsize=(9, 8), layout="constrained")
    for y, row in enumerate(top):
        span = uncertainty["entrants"][row["id"]]
        ax.plot([span["rank_p025"], span["rank_p975"]], [y, y], color="#9fb9a7", lw=5, solid_capstyle="round")
        ax.scatter(row["rank"], y, color="#245b42", s=35, zorder=3)
    ax.set_yticks(range(len(top)), [row["name"] for row in top])
    ax.invert_yaxis()
    ax.set_xlim(.5, max(uncertainty["entrants"][r["id"]]["rank_p975"] for r in top) + 1)
    ax.set_xlabel("Rank · dot = pooled fit; segment = 2.5–97.5% of task perturbations")
    ax.grid(axis="x", alpha=.18)
    ax.set_title("How sensitive are the leading ranks?", loc="left", pad=20, fontsize=16)
    save(fig, "rank-sensitivity")

    judges = [key for key in labels if key != "pooled"]
    shared = defaultdict(dict)
    for row in ballots:
        shared[row["batch_id"], row["task_id"], row["iteration"]][row["judge_id"]] = row["ranking"]
    distances, counts = Counter(), Counter()
    for answers in shared.values():
        for left, right in combinations(sorted(answers), 2):
            distances[left, right] += kendall_distance(answers[left], answers[right])
            counts[left, right] += 1
    disagreement = np.full((len(judges), len(judges)), np.nan)
    for i, left in enumerate(judges):
        for j, right in enumerate(judges):
            pair = tuple(sorted([left, right]))
            if i != j and counts[pair]:
                disagreement[i, j] = distances[pair] / counts[pair]
    short = [labels[key].replace(" traveler", "").replace(" planner", "") for key in judges]
    fig, ax = plt.subplots(figsize=(9, 7), layout="constrained")
    cmap = plt.get_cmap("YlOrRd").copy()
    cmap.set_bad("#f0f0e9")
    chart = ax.imshow(np.ma.masked_invalid(disagreement), cmap=cmap, vmin=0, vmax=1)
    for i in range(len(judges)):
        for j in range(len(judges)):
            value = disagreement[i, j]
            text = "—" if np.isnan(value) else f"{value:.0%}"
            ax.text(j, i, text, ha="center", va="center", fontsize=12,
                    color="white" if value > .65 else "#203329")
    ax.set_xticks(range(len(judges)), short, rotation=35, ha="right")
    ax.set_yticks(range(len(judges)), short)
    ax.set_title("Which travelers disagree?", loc="left", pad=20, fontsize=16)
    fig.colorbar(chart, ax=ax, shrink=.7, label="Mean fraction of pair orders reversed on shared tasks")
    save(fig, "ranker-disagreement")

    main = state["batches"]["main"]["design"]
    task_round = {t["id"]: t["round"] for t in main["tasks"]}
    previous, changes = None, []
    for round_id in sorted(set(task_round.values())):
        selected = [row for row in ballots if row["batch_id"] == "main" and task_round[row["task_id"]] <= round_id]
        snapshot = score(state["entrants"], selected, method="pl")
        current = {row["id"]: row["rank"] for row in snapshot["rankings"]}
        if previous:
            movement = [abs(current[key] - previous[key]) for key in ids]
            overlap = len({key for key in ids if current[key] <= 10} & {key for key in ids if previous[key] <= 10})
            changes.append({"through_round": round_id, "max_movement": max(movement),
                            "median_movement": float(np.median(movement)), "top10_overlap": overlap})
        previous = current
    fig, (ax, right) = plt.subplots(1, 2, figsize=(10, 4.5), layout="constrained")
    x = [row["through_round"] for row in changes]
    ax.plot(x, [row["max_movement"] for row in changes], "o-", color="#ad682e", label="Largest movement")
    ax.plot(x, [row["median_movement"] for row in changes], "o-", color="#245b42", label="Median movement")
    ax.set_ylabel("Absolute change in rank")
    ax.set_title("Movement from the preceding fit", loc="left")
    ax.legend(frameon=False, fontsize=9)
    right.bar(x, [row["top10_overlap"] for row in changes], color="#548365", width=.55)
    right.set_ylim(0, 11)
    right.set_ylabel("States shared with the preceding top ten")
    right.set_title("Does the top ten change?", loc="left")
    for axis in (ax, right):
        axis.set_xticks(x)
        axis.set_xlabel("Include rankings through round")
        axis.grid(axis="y", alpha=.18)
        axis.set_axisbelow(True)
    save(fig, "round-stability")
    return {"paths": paths, "coverage": {"tasks": len(tasks), "unique_pairs": int(np.count_nonzero(matrix) // 2),
                                         "possible_pairs": len(ids) * (len(ids) - 1) // 2},
            "ranker_disagreement": [{"left": left, "right": right, "shared_tasks": count,
                                     "mean_kendall_distance": distances[left, right] / count}
                                    for (left, right), count in sorted(counts.items())],
            "round_stability": changes,
            "limitations": ["Task perturbations are conditional sensitivity ranges, not confidence guarantees.",
                            "Between-profile disagreement is a difference of preferences, not repeat error.",
                            "Cumulative fits reuse earlier ballots; stability does not establish accuracy."],
            "state_names": names}
