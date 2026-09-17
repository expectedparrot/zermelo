"""Export only missing assignments with a documented response-format clarification."""

import argparse
import json
import shlex
from collections import defaultdict
from pathlib import Path

from common import jobs
from edsl import AgentList, Jobs, QuestionRank, ScenarioList, Survey

from zermelo.fielding import coverage
from zermelo.store import Store, digest, identifier, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--wave', required=True)
    parser.add_argument('--study')
    parser.add_argument('--judge')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    identifier(args.wave)
    root = args.root.resolve()
    index = root / 'retry-jobs.json'
    records = json.loads(index.read_text()) if index.exists() else []
    additions = []
    for entry in jobs(root):
        if args.study and entry['study'] != args.study:
            continue
        state = Store(Path(entry['project'])).load()
        missing = coverage(state, entry['batch'])['missing']
        if args.judge:
            missing = [row for row in missing if row['judge_id'] == args.judge]
        if args.limit:
            missing = missing[:args.limit]
        if not missing:
            continue
        original = Jobs.git.load(entry['jobs_path'])
        k = original.survey.questions[0].num_selections
        clarification = (f'\n\nResponse format: return ONLY one JSON array containing exactly these {k} integer option indices, '
                         f'in your preferred order: {list(range(k))}. Include every index exactly once. '
                         'Do not return entrant IDs or names. Do not omit an option. Do not add prose outside the array.')
        question = QuestionRank.from_dict(original.survey.questions[0].to_dict())
        question.question_text += clarification
        survey = Survey([question])
        grouped = defaultdict(list)
        for cell in missing:
            if cell['iteration'] != 0:
                raise ValueError('This example only exports iteration-zero studies.')
            grouped[cell['judge_id']].append(cell['task_id'])
        for judge, tasks in grouped.items():
            name = f"{entry['batch']}-{args.wave}-{judge}"
            path = Path(entry['project']) / f'{name}_job.ep'
            result_path = path.with_name(f'{name}_results.ep')
            if path.exists() or result_path.exists():
                raise FileExistsError(path)
            scenarios = ScenarioList([s for s in original.scenarios if s['elo_task_id'] in tasks])
            agents = AgentList([a for a in original.agents if a.traits['elo_judge_id'] == judge])
            native = survey.by(scenarios).by(agents).by(original.models[0])
            native.git.save(path, message='Only missing assignments; explicit integer-permutation response clarification')
            assert digest(Jobs.git.load(path).to_dict()) == digest(native.to_dict())
            row = {'study': entry['study'], 'project': entry['project'], 'batch': name, 'import_batch': entry['batch'],
                   'jobs_path': str(path), 'results_path': str(result_path), 'expected_model_calls': len(tasks),
                   'response_format_clarification': clarification, 'task_ids': tasks, 'judge_id': judge,
                   'original_jobs_path': entry['jobs_path'], 'original_design_hash': entry['design_hash'],
                   'model': entry['model'], 'run_command': shlex.join(['ep', 'run', '--jobs', str(path), '--fresh',
                       '--remote_inference_results_visibility', 'private', '--output', str(result_path)])}
            write_new(path.with_suffix('.manifest.json'), row)
            additions.append(row)
    if additions:
        history = root / f'retry-jobs-{args.wave}.json'
        write_new(history, additions)
        if index.exists():
            previous = root / f'retry-index-before-{args.wave}.json'
            write_new(previous, records)
        index.write_text(json.dumps(records + additions, indent=2) + '\n')
    print(json.dumps({'new_jobs': len(additions), 'missing_assignments': sum(row['expected_model_calls'] for row in additions),
                      'inference_submitted': False}))


if __name__ == '__main__':
    main()
