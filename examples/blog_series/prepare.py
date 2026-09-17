"""Prepare ten original concept-ranking studies. Never runs model inference."""

import argparse
import json
import shutil
from pathlib import Path

from catalog import STUDIES, candidates
from common import command, export, jobs
from edsl import Agent, AgentList

from zermelo.store import write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--model', default='gemini-3.1-flash-lite')
    parser.add_argument('--service', default='google')
    args = parser.parse_args()
    root = args.output.resolve()
    if not root.is_relative_to(Path('runs').resolve()):
        parser.error('Generated projects must be inside runs/.')
    root.mkdir(parents=True, exist_ok=False)
    write_new(root / 'budget.json', {'authorized_usd_per_study': 5, 'authorized_total_usd': 50,
                                   'model': args.model, 'service': args.service,
                                   'policy': 'Estimate every job before external submission; follow-ups and retries count toward each study.'})
    shutil.copyfile(Path(__file__).with_name('catalog.py'), root / 'catalog.source.py')
    for key, spec in STUDIES.items():
        directory = root / key
        directory.mkdir()
        entrants = candidates(key)
        initial_count = 100 if key == 'talks' else 80 if key == 'blog' else len(entrants)
        project_names = [f'{key}/main'] + ([f'{key}/learning'] if key == 'projects' else [])
        write_new(directory / 'study.json', {**spec, 'key': key, 'projects': project_names,
                   'entrants': entrants, 'initial_count': initial_count, 'model': args.model, 'service': args.service,
                   'provenance': 'Original authored concept families crossed with explicit variants. Synthetic profiles; no sampled people.'})
        for name in project_names:
            project = root / name
            inputs = project / 'inputs'
            inputs.mkdir(parents=True)
            criterion = spec['alternate_criterion'] if name.endswith('/learning') else spec['criterion']
            write_new(inputs / 'entrants.json', entrants[:initial_count])
            write_new(inputs / 'late-entrants.json', entrants[initial_count:])
            write_new(inputs / 'model-parameters.json', {'temperature': 0.3, 'max_tokens': 2048})
            panel = AgentList([Agent(name=f'judge_{i}', traits={'profile_name': profile['name'],
                'preferences': profile['preferences'], 'role': 'Express this synthetic profile; do not claim to represent real people.'})
                for i, profile in enumerate(spec['profiles'], 1)])
            panel.git.save(inputs / 'agent_list.ep', message='Freeze six authored synthetic profiles')
            command(project, 'next')
            command(project, 'init', '--criterion', criterion)
            command(project, 'next')
            command(project, 'entrants', 'import', inputs / 'entrants.json')
            command(project, 'next')
            command(project, 'rankers', 'add', inputs / 'agent_list.ep')
            command(project, 'next')
            if key == 'names':
                plan = command(project, 'calibrate', 'plan', 'pilot', '--batch-sizes', '4,8,12',
                               '--sample', '40', '--subsets', '6', '--repeats', '3', '--seed', '20260916')
                for batch in plan['batch_ids']:
                    export(project, batch, args.model, args.service)
            else:
                command(project, 'batch', 'plan', 'main', '--chunk-size', '5', '--rounds', '3', '--seed', '20260916')
                command(project, 'next')
                export(project, 'main', args.model, args.service)
            command(project, 'next')
    inventory = jobs(root)
    write_new(root / 'jobs-stage-1.json', inventory)
    print(json.dumps({'root': str(root), 'studies': len(STUDIES), 'jobs': len(inventory),
                      'expected_model_calls': sum(job['expected_model_calls'] for job in inventory),
                      'inference_submitted': False}))


if __name__ == '__main__':
    main()
