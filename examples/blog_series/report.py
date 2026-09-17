"""Build a source-linked blog draft and figures from completed live results."""

import argparse
import hashlib
import json
import os
import textwrap
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/private/tmp/zermelo-blog-matplotlib')
import markdown as markdown_renderer
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from common import jobs
from edsl import Results
from field import label
from scipy.stats import spearmanr

from zermelo.scoring import score
from zermelo.store import Store, evidence_hash, write_new


def ranks(result):
    return {row['id']: row['rank'] for row in result['rankings']}


def compare(left, right):
    a, b = ranks(left), ranks(right)
    keys = sorted(set(a) & set(b))
    return {'spearman': float(spearmanr([a[k] for k in keys], [b[k] for k in keys]).statistic),
            'shared_top_10': len(set(list(a)[:10]) & set(list(b)[:10]))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = root / 'reports'
    output.mkdir(exist_ok=False)
    figures = output / 'figures'
    figures.mkdir()
    details = {}
    initial_valid = initial_requested = 0
    for source in (root / 'fielding').glob('*-status-001.json'):
        if 'format-' in source.name or any(word in source.name for word in ('newcomers', 'refinement')):
            continue
        if source.name == 'names-main-main-status-001.json':
            continue
        record = json.loads(source.read_text()).get('data', {})
        counts = (record.get('latest_job_run_details') or {}).get('interview_details') or {}
        initial_valid += counts.get('completed_interviews', 0)
        initial_requested += counts.get('total_interviews', 0)
    sections = []
    inventory = jobs(root)
    retry_path = root / 'retry-jobs.json'
    if retry_path.exists():
        inventory += json.loads(retry_path.read_text())
    prices = {}
    reported_charges = {}
    for entry in inventory:
        result_path = Path(entry['results_path'])
        if not result_path.exists():
            continue
        total = 0
        for result in Results.git.load(result_path):
            raw = result.to_dict(add_edsl_version=False).get('raw_model_response', {})
            total += raw.get('ranking_cost') or 0
        prices[entry['study']] = prices.get(entry['study'], 0) + total
        statuses = sorted((root / 'fielding').glob(f'{label(entry)}-status-*.json'))
        if statuses:
            status = json.loads(statuses[-1].read_text())
            charge = (status.get('data', {}).get('latest_job_run_details') or {}).get('cost_usd')
            if charge is not None:
                reported_charges[entry['study']] = reported_charges.get(entry['study'], 0) + charge
    for path in sorted(root.glob('*/study.json')):
        spec = json.loads(path.read_text())
        key = spec['key']
        project = root / spec['projects'][0]
        final = json.loads((project / 'final.json').read_text())
        state = Store(project).load()
        ballots = [row for row in state['ballots'].values() if state['batches'][row['batch_id']]['design'].get('purpose', 'ranking') == 'ranking']
        entrants = state['entrants']
        profile_labels = {f'judge_{i}': p['name'] for i, p in enumerate(spec['profiles'], 1)}
        individual = {judge: score(entrants, [row for row in ballots if row['judge_id'] == judge], method='pl') for judge in profile_labels}
        methods = {'pl': final, **{method: score(entrants, ballots, method=method) for method in ('bt', 'elo')}}
        individual_ranks = {judge: ranks(fit) for judge, fit in individual.items()}
        disagreements = sorted([{'id': row['id'], 'name': row['name'],
            'min_rank': min(values[row['id']] for values in individual_ranks.values()),
            'max_rank': max(values[row['id']] for values in individual_ranks.values())} for row in entrants],
            key=lambda row: row['max_rank'] - row['min_rank'], reverse=True)
        clarified_hashes = {hashlib.sha256(Path(entry['results_path']).read_bytes()).hexdigest() for entry in inventory
                            if entry['project'] == str(project) and 'response_format_clarification' in entry
                            and Path(entry['results_path']).exists()}
        clarified_count = sum(row['source_sha256'] in clarified_hashes for row in ballots)
        summary = {'format_clarified_production_ballots': clarified_count, 'criterion': state['criterion'], 'evidence_hash': evidence_hash(state),
            'entrants': len(entrants), 'production_ballots': len(ballots), 'task_count': len({(r['batch_id'], r['task_id']) for r in ballots}),
            'profile_labels': profile_labels, 'individual': individual, 'methods': methods,
            'disagreements': disagreements, 'method_comparison': {m: compare(final, fit) for m, fit in methods.items() if m != 'pl'},
            'observed_token_cost_usd': prices.get(key, 0), 'ep_reported_job_charges_usd': reported_charges.get(key)}
        top = final['rankings'][:10]
        fig, ax = plt.subplots(figsize=(10, 6))
        matrix = np.array([[individual_ranks[judge][row['id']] for judge in profile_labels] for row in top])
        picture = ax.imshow(matrix, cmap='viridis_r', vmin=1, vmax=len(entrants), aspect='auto')
        ax.set_xticks(range(6), [textwrap.fill(name, 15) for name in profile_labels.values()], fontsize=8)
        ax.set_yticks(range(10), [textwrap.fill(row['name'], 38) for row in top], fontsize=8)
        for i in range(10):
            for j in range(6):
                ax.text(j, i, str(matrix[i, j]), ha='center', va='center', fontsize=8,
                        color='black' if matrix[i, j] < len(entrants) / 2 else 'white')
        ax.set_title(f"{spec['title']}\nPooled top ten; cells show each synthetic ranker's rank", fontsize=11)
        fig.colorbar(picture, ax=ax, label='Individual rank (1 is best)')
        fig.tight_layout()
        fig.savefig(figures / f'{key}-rankers.png', dpi=160)
        plt.close(fig)
        paragraphs = [f"## {spec['title']}", '', spec['question'], '', f"**Feature:** {spec['feature']}.", '',
            f"We compared {len(entrants)} concept cards using six authored profiles. The production data contain "
            f"{len(ballots)} complete group rankings across {summary['task_count']} comparison tasks. "
            "A task can be answered by several rankers; those answers are not extra independently designed tasks.", '',
            '**The pooled top five:**', '']
        paragraphs += [f"{i}. {row['name']}" for i, row in enumerate(top[:5], 1)]
        most = disagreements[0]
        if clarified_count:
            paragraphs += ['', f'{clarified_count} accepted production ballots came from missing-assignment retries with an explicit integer-permutation format reminder. Original jobs and failed responses are preserved. The reminder changes response instructions and could influence responses; these are not identical-prompt repetitions.', '']
        paragraphs += ['', f"The largest between-profile rank spread belongs to **{most['name']}**: "
                       f"rank {most['min_rank']} for its most favorable profile and {most['max_rank']} for its least favorable. "
                       "This is disagreement among specified preferences, not an uncertainty interval.", '',
                       f"![Individual profile rankings of the pooled top ten](figures/{key}-rankers.png)", '']
        if key == 'library':
            subsets = {'practical': ['judge_1', 'judge_3', 'judge_4'], 'cultural': ['judge_2', 'judge_5', 'judge_6']}
            fits = {name: score(entrants, [r for r in ballots if r['judge_id'] in judges], method='pl') for name, judges in subsets.items()}
            summary['panel_sensitivity'] = fits
            paragraphs += [f"Reusing the same ballots, the maker/career/family subgroup puts **{fits['practical']['rankings'][0]['name']}** first; "
                           f"the reader/community/curiosity subgroup puts **{fits['cultural']['rankings'][0]['name']}** first. "
                           "These are explicit subgroup fits, not fresh observations or a survey of actual residents.", '']
        if key == 'names':
            calibration = json.loads((project / 'calibration.json').read_text())
            summary['calibration'] = calibration
            paragraphs += ['We first tested group sizes 4, 8, and 12 on six shared subsets, with three shuffled repeats per size and six rankers. '
                           'The prespecified eligibility threshold was mean within-ranker Kendall disagreement ≤ 0.20.', '',
                           '| Group size | Mean disagreement | Eligible |', '|---|---:|---|']
            paragraphs += [f"| {row['chunk_size']} | {row['mean_kendall_disagreement']:.3f} | {row['eligible']} |" for row in calibration['candidates']]
            paragraphs += ['', f"The calibration recommendation was **{calibration['recommended_chunk_size']}**. "
                           "A consistent judge can still be consistently unhelpful; this screens repeatability, not truth.", '']
            if (project / 'calibration-decision.json').exists():
                paragraphs += [json.loads((project / 'calibration-decision.json').read_text())['reason'], '']
        if key == 'projects':
            alternative = json.loads((root / spec['projects'][1] / 'final.json').read_text())
            summary['alternate_criterion'] = {'criterion': alternative['criterion'], 'comparison': compare(final, alternative), 'fit': alternative}
            paragraphs += [f"With a separately initialized project asking about learning fundamentals, the winner becomes "
                           f"**{alternative['rankings'][0]['name']}**. The two criteria share "
                           f"{summary['alternate_criterion']['comparison']['shared_top_10']} of their top ten, with Spearman "
                           f"correlation {summary['alternate_criterion']['comparison']['spearman']:.3f}. "
                           "The candidate cards and profiles are held fixed; the criterion changes explicitly.", '']
        if key in ('features', 'talks', 'blog'):
            baseline = json.loads((project / 'baseline.json').read_text())
            summary['baseline_comparison'] = compare(baseline, final)
            if key == 'features':
                paragraphs += [f"After the initial ranking we added 30 adaptive tasks per ranker, preserving the panel and earlier ballots. "
                               f"The baseline and final top tens share {summary['baseline_comparison']['shared_top_10']} entries. "
                               "Adaptive scheduling is a way to allocate comparisons; this single run does not establish superiority over a random follow-up.", '']
            else:
                old_ids = set(ranks(baseline))
                newcomers = [row for row in final['rankings'] if row['id'] not in old_ids]
                summary['newcomers'] = newcomers
                paragraphs += [f"We began with {len(old_ids)} cards, preserved their original batch, then added {len(newcomers)} late entrants. "
                               f"The highest-ranked newcomer is **{newcomers[0]['name']}**, at final rank {newcomers[0]['rank']}. "
                               "The follow-up connects new candidates to observed anchors.", '']
            if key == 'blog':
                paragraphs += ['For the workflow demonstration we deliberately imported only half of an already returned artifact, '
                               'recorded the resulting incomplete state, then imported the complete original. This is a controlled '
                               'ingestion demonstration, not a claimed model failure. Exact duplicates were counted once; '
                               'the original response bytes remain preserved.', '']
        if key == 'museum':
            paragraphs += ['| Method | Winner | Top-ten overlap with PL | Spearman with PL |', '|---|---|---:|---:|']
            for method, fit in methods.items():
                comparison = compare(final, fit)
                paragraphs += [f"| {method.upper()} | {fit['rankings'][0]['name']} | {comparison['shared_top_10']} | {comparison['spearman']:.3f} |"]
            paragraphs += ['', 'All methods use the same accepted ballots. Elo uses the package’s canonical ballot order; '
                           'this comparison is not a validation against known correct ranks.', '']
        if key == 'openings':
            summary['conditional_sensitivity'] = final.get('uncertainty')
            intervals = final['uncertainty']['entrants']
            fig, ax = plt.subplots(figsize=(10, 6))
            for i, row in enumerate(top):
                interval = intervals[row['id']]
                ax.plot([interval['rank_p025'], interval['rank_p975']], [i, i], color='#448366', linewidth=3)
                ax.scatter([row['rank']], [i], color='#172e22', zorder=3)
            ax.set_yticks(range(len(top)), [textwrap.fill(row['name'], 38) for row in top], fontsize=8)
            ax.invert_yaxis()
            ax.set_xlabel('Rank (1 is best); dots are pooled ranks, bars are conditional 2.5–97.5% ranges')
            ax.set_title('Opening paragraphs: task-cluster sensitivity\n200 draws; this is not between-reader disagreement')
            fig.tight_layout()
            fig.savefig(figures / 'openings-sensitivity.png', dpi=160)
            plt.close(fig)
            paragraphs += ['![Task-cluster conditional rank sensitivity](figures/openings-sensitivity.png)', '']
            paragraphs += ['The saved ranking includes 200 task-cluster multiplier-bootstrap draws. Each draw reweights '
                           'whole tasks, keeping rankers answering the same task together. This measures sensitivity '
                           'conditional on these cards, profiles, and observations; it is not a confidence interval for population taste. '
                           'The complete per-item diagnostic is in `analysis.json`.', '']
        if key == 'books':
            winner = top[0]['id']
            number_first = sum(values[winner] == 1 for values in individual_ranks.values())
            paragraphs += [f"The pooled winner is also the individual winner for **{number_first} of six** profiles. "
                           "Pooling estimates a compromise under equal profile representation; it need not reproduce any one reader’s order.", '']
        if key == 'movies':
            least_bad = min(entrants, key=lambda row: max(values[row['id']] for values in individual_ranks.values()))
            worst_rank = max(values[least_bad['id']] for values in individual_ranks.values())
            summary['minimax_individual_rank'] = {'id': least_bad['id'], 'worst_rank': worst_rank}
            paragraphs += [f"A different group-choice rule—minimizing the worst individual rank—selects **{least_bad['name']}**, "
                           f"whose least favorable profile rank is {worst_rank}. This post-hoc diagnostic uses ordinal ranks; "
                           "it does not measure interpersonal utility or establish a fair voting rule.", '']
        paragraphs += [f"Recorded per-result token charges for this example: **${prices.get(key, 0):.3f}**. "
                       "This sums returned token-cost fields, including follow-up jobs; it is not a reconciled account bill.", '',
                       f"[Frozen study definition](../{key}/study.json) · [Final ranking](../{spec['projects'][0]}/final.json)"]
        sections.append('\n'.join(paragraphs))
        details[key] = summary
    intro = ["# Ten ranking experiments, five options at a time", '',
        'What happens when six readers disagree about the next book, a product team has eighty possible improvements, '
        'or twenty conference proposals arrive after the first ranking is finished? We ran ten small studies to explore '
        'those questions with Zermelo, keeping the criteria, authored profiles, candidate cards, jobs, and returned ballots.', '',
        '**These are live model judgments of original fictional concept cards.** The people are synthetic profiles, '
        'the books and films are unproduced concepts, and the results describe these inputs rather than public opinion. '
        'Cards are constructed from explicitly listed concept families and variants. Repeated structure is deliberate '
        'and affects the comparison; it is not an independent sample of all possible options.', '',
        f'The first wave completed **{initial_valid:,} of {initial_requested:,} requested interviews**; the rest encountered response-validation failures. A five-assignment probe showed that an explicit '
        'instruction to return each zero-based option index exactly once could recover missing answers. We preserved '
        'successful ballots and original artifacts, then retried only missing assignments with that documented format '
        'clarification. New follow-up exports used the explicit instruction from the start. This instrument change is '
        'part of the study history and a limitation of any calibration or preference comparisons.', '',
        'All studies used Gemini 3.1 Flash Lite through EP, temperature 0.3, with six equally represented profiles. '
        'Initial production designs use three overlapping rounds and a fixed seed. Most questions rank five options; '
        'the naming study chooses its production group size after calibration. Rankings use regularized '
        'Plackett–Luce unless an alternative method is explicitly shown.', '',
        'A group ranking is one observation. Its implied pairwise wins are dependent. The figures below show '
        'differences among rankers; the opening-paragraph study separately examines conditional sensitivity by reweighting whole tasks.', '',
        f"The authorized ceiling was $5 per example. Returned token-cost fields total **${sum(prices.values()):.3f}** across the series; "
        f"EP's job-status charge fields separately sum to **${sum(reported_charges.values()):.3f}**. "
        'Cost-estimate and remote execution records are retained separately in the private run directory. '
        'No example should be treated as a population estimate or a demonstration of a universally correct ranking.', '',
        '## Read or reproduce the studies', '',
        'The reusable scripts and all authored concept families are in `examples/blog_series/`. '
        'Preparation exports native jobs without running inference. Execution uses external `ep run` commands; '
        'imports validate assignments and preserve original result bytes. `zermelo next` guides each project toward a saved ranking.', '']
    markdown = '\n'.join(intro) + '\n\n' + '\n\n'.join(sections) + '\n'
    write_new(output / 'blog-post.md', markdown, raw=True)
    write_new(output / 'analysis.json', details)
    # Render the same draft as semantic HTML, with local figures and source links.
    content = markdown_renderer.markdown(markdown, extensions=['tables', 'fenced_code'])
    document = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Ten Zermelo experiments</title><style>'
                'body{max-width:1000px;margin:50px auto;padding:0 24px;font:17px/1.7 system-ui;color:#22372b;background:#fafaf6}'
                'h1{font:48px/1.1 Georgia}h2{margin-top:70px;padding-top:25px;border-top:1px solid #cbd9cc}'
                'img{display:block;max-width:100%;margin:24px 0}a{color:#276348}'
                'table{border-collapse:collapse;width:100%;font-size:15px}td,th{text-align:left;padding:10px;border-bottom:1px solid #ccd7ce}'
                'th{background:#e6eee5}code{background:#e6eee5;padding:2px 4px;border-radius:3px}'
                '@media(max-width:650px){body{font-size:15px}h1{font-size:36px}table{font-size:12px}}'
                '</style></head><body><article>' + content + '</article></body></html>')
    write_new(output / 'index.html', document, raw=True)
    print(json.dumps({'draft': str(output / 'blog-post.md'), 'preview': str(output / 'index.html'), 'recorded_token_cost_usd': prices, 'ep_reported_job_charges_usd': reported_charges}))


if __name__ == '__main__':
    main()
