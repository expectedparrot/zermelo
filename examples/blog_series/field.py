"""Estimate, submit, or collect through external EP commands; retain private logs.

Submission is explicit (--submit). Each study has a $5 estimate budget. Estimates
are not guaranteed prices; use a twofold reserve before authorizing a submission.
"""

import argparse
import json
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from common import jobs

from zermelo.store import write_new


def ep(args, destination):
    completed = subprocess.run(['ep', *args], capture_output=True, text=True, timeout=240)
    try:
        data = json.loads(completed.stdout)
    except ValueError:
        write_new(destination.with_suffix('.stderr.txt'), completed.stderr + '\n' + completed.stdout)
        raise RuntimeError(f'EP did not return JSON; inspect {destination.parent}')
    write_new(destination, data)
    if completed.returncode or data.get('status') == 'error':
        raise RuntimeError(f'EP failed; inspect {destination}')
    return data


def find_value(data, names):
    if isinstance(data, dict):
        for key in names:
            if key in data and data[key] is not None:
                return data[key]
        for value in data.values():
            found = find_value(value, names)
            if found is not None:
                return found
    return None


def label(job):
    return f"{job['study']}-{Path(job['project']).name}-{job['batch']}"


def inventory(root):
    return jobs(root) + (json.loads((root / 'retry-jobs.json').read_text()) if (root / 'retry-jobs.json').exists() else [])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--estimate', action='store_true')
    mode.add_argument('--submit', action='store_true')
    mode.add_argument('--collect', action='store_true')
    mode.add_argument('--errors', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    records = root / 'fielding'
    records.mkdir(exist_ok=True)
    entries = inventory(root)
    if args.estimate:
        def estimate(job):
            path = records / f'{label(job)}-estimate.json'
            if not path.exists():
                ep(['jobs', 'cost', job['jobs_path']], path)
            data = json.loads(path.read_text())
            return job['study'], float(data['data']['usd'])
        with ThreadPoolExecutor(max_workers=4) as pool:
            amounts = list(pool.map(estimate, entries))
        totals = {}
        for key, usd in amounts:
            totals[key] = totals.get(key, 0) + usd
        print(json.dumps({'point_estimates_usd': totals, 'total_usd': sum(totals.values()), 'jobs': len(entries)}))
    elif args.submit:
        totals = {}
        for job in entries:
            estimate = records / f'{label(job)}-estimate.json'
            if not estimate.exists():
                raise RuntimeError('Estimate all jobs first.')
            usd = float(json.loads(estimate.read_text())['data']['usd'])
            totals[job['study']] = totals.get(job['study'], 0) + usd
        budget = json.loads((root / 'budget.json').read_text())
        if any(2 * amount > budget['authorized_usd_per_study'] for amount in totals.values()):
            raise RuntimeError('Twofold estimate reserve exceeds a study budget; reduce the next wave before submitting.')
        submitted = []
        for job in entries:
            output = records / f'{label(job)}-submission.json'
            if output.exists():
                if json.loads(output.read_text()).get('status') == 'error':
                    raise RuntimeError(f'Previous submission failed; inspect {output} before retrying.')
                continue
            intent = records / f'{label(job)}-submission-intent.json'
            if intent.exists():
                raise RuntimeError(f'Unresolved submission intent {intent}; inspect EP jobs before any retry.')
            args_run = shlex.split(job['run_command'])[1:]
            output_index = args_run.index('--output')
            del args_run[output_index:output_index + 2]
            args_run += ['--background', '--task-timeout', '900']
            write_new(intent, {'argv': ['ep', *args_run], 'estimated_usd': json.loads((records / f'{label(job)}-estimate.json').read_text())['data']['usd']})
            response = ep(args_run, output)
            job_id = find_value(response, ['job_uuid', 'job_id', 'remote_job_uuid'])
            if not job_id:
                raise RuntimeError(f'Could not identify remote job; inspect {output}')
            submitted.append(label(job))
            print(json.dumps({'submitted': label(job), 'expected_calls': job['expected_model_calls']}), flush=True)
        print(json.dumps({'new_submissions': len(submitted), 'point_estimates_usd': totals}))
    elif args.errors:
        for job in entries:
            path = records / f'{label(job)}-errors.json'
            submission = records / f'{label(job)}-submission.json'
            if path.exists() or not submission.exists():
                continue
            job_id = find_value(json.loads(submission.read_text()), ['job_uuid', 'job_id', 'remote_job_uuid'])
            ep(['jobs', 'errors', str(job_id), '--format', 'json'], path)
        print(json.dumps({'error_reports_saved': len(list(records.glob('*-errors.json')))}))
    else:
        def collect(job):
            destination = Path(job['results_path'])
            if destination.exists():
                return label(job), 'downloaded'
            submission = records / f'{label(job)}-submission.json'
            if not submission.exists():
                return label(job), 'not submitted'
            job_id = find_value(json.loads(submission.read_text()), ['job_uuid', 'job_id', 'remote_job_uuid'])
            index = len(list(records.glob(f'{label(job)}-status-*.json'))) + 1
            path = records / f'{label(job)}-status-{index:03d}.json'
            response = ep(['jobs', 'status', str(job_id)], path)
            status = find_value(response.get('data', {}), ['job_status', 'status'])
            if status in ('completed', 'complete', 'partially_completed', 'partial_failed', 'failed', 'cancelled'):
                if not response.get('data', {}).get('results_uuid'):
                    return label(job), 'awaiting result artifact'
                ep(['jobs', 'results', str(job_id), '--output', str(destination)], records / f'{label(job)}-download-{index:03d}.json')
                return label(job), 'downloaded'
            return label(job), status
        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = dict(pool.map(collect, entries))
        print(json.dumps({'jobs': statuses}))


if __name__ == '__main__':
    main()
