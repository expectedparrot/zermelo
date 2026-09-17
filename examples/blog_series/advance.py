"""Import returned artifacts and export justified follow-ups. Never executes models."""

import argparse
import json
from pathlib import Path

from common import command, export, jobs
from edsl import Results

from zermelo import fielding
from zermelo.store import Store, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    retry_index = root / 'retry-jobs.json'
    retries = json.loads(retry_index.read_text()) if retry_index.exists() else []
    for entry in jobs(root) + retries:
        project = Path(entry['project'])
        batch = entry.get('import_batch', entry['batch'])
        store = Store(project)
        state = store.load()
        if fielding.coverage(state, batch)['complete']:
            continue
        source = Path(entry['results_path'])
        if not source.exists():
            continue
        # A deliberate partial import demonstrates recovery without fabricating a
        # model failure or rerunning already available successful interviews.
        if project.parent.name == 'blog' and batch == 'main' and not state['batches']['main']['imports']:
            partial = project / 'demonstration-partial.ep'
            if not partial.exists():
                results = Results.git.load(source)
                half = Results(survey=results.survey, data=list(results)[:len(results) // 2])
                half.git.save(partial, message='Deliberately withheld half for ingestion demonstration; not an inference failure')
            command(project, 'results', 'import', 'main', partial, '--skip-invalid')
            command(project, 'next')
        command(project, 'results', 'import', batch, source, '--skip-invalid')
    blocked = []
    for path in sorted(root.glob('*/study.json')):
        spec = json.loads(path.read_text())
        for name in spec['projects']:
            project = root / name
            state = Store(project).load()
            if any(not fielding.coverage(state, key)['complete'] for key in state['batches']):
                blocked.append(name)
                continue
            key = spec['key']
            if key == 'names' and 'main' not in state['batches']:
                report = command(project, 'calibrate', 'analyze', 'pilot', '--max-disagreement', '.2',
                                 '--output', project / 'calibration.json') if not (project / 'calibration.json').exists() else json.loads((project / 'calibration.json').read_text())
                size = report['recommended_chunk_size']
                if size is None:
                    # This is an explicit recorded choice, not a passing calibration result.
                    size = 4
                    write_new(project / 'calibration-decision.json', {'selected_size': size,
                        'reason': 'No candidate passed the prespecified .20 disagreement threshold. Use the smallest tested size as an exploratory fallback; do not claim calibration success.'})
                command(project, 'batch', 'plan', 'main', '--chunk-size', size, '--rounds', '3', '--seed', '20260917')
                export(project, 'main', spec['model'], spec['service'])
                continue
            if not (project / 'baseline.json').exists():
                command(project, 'rank', '--output', project / 'baseline.json')
            if key == 'features' and 'refinement' not in state['batches']:
                command(project, 'batch', 'plan', 'refinement', '--strategy', 'neighborhood', '--chunk-size', '5',
                        '--rounds', '1', '--tasks', '30', '--bridge-frac', '.1', '--seed', '20260917')
                export(project, 'refinement', spec['model'], spec['service'])
            elif key in ('talks', 'blog') and 'newcomers' not in state['batches']:
                command(project, 'entrants', 'import', project / 'inputs/late-entrants.json')
                command(project, 'next')
                command(project, 'batch', 'plan', 'newcomers', '--only-new', '--chunk-size', '5', '--rounds', '1', '--seed', '20260917')
                export(project, 'newcomers', spec['model'], spec['service'])
            elif not (project / 'final.json').exists():
                extra = ['--bootstrap', '200', '--cluster', 'task', '--seed', '20260916'] if key == 'openings' else []
                command(project, 'rank', '--output', project / 'final.json', *extra)
                command(project, 'next')
    inventory = jobs(root)
    stage = len(list(root.glob('jobs-stage-*.json'))) + 1
    write_new(root / f'jobs-stage-{stage}.json', inventory)
    print(json.dumps({'root': str(root), 'jobs': len(inventory), 'waiting_projects': blocked, 'inference_submitted': False}))


if __name__ == '__main__':
    main()
