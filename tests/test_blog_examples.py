"""Check authored experiment definitions and the spending gate without inference."""

import importlib
import json
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples/blog_series'


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLES))
    return importlib.import_module('catalog')


def test_blog_catalog_has_distinct_frozen_cards_and_complete_panels(catalog):
    expected = {'books': 100, 'features': 80, 'library': 100, 'names': 200, 'movies': 75,
                'projects': 60, 'talks': 120, 'openings': 100, 'museum': 80, 'blog': 100}
    assert set(catalog.STUDIES) == set(expected)
    for key, count in expected.items():
        rows = catalog.candidates(key)
        assert len(rows) == len({row['id'] for row in rows}) == len({row['name'] for row in rows}) == count
        assert len({row['description'] for row in rows}) == count
        assert all(set(row) == {'id', 'name', 'description'} for row in rows)
        spec = catalog.STUDIES[key]
        assert len(spec['profiles']) == len({p['name'] for p in spec['profiles']}) == 6
        assert 'FIRST' in spec['criterion']
    assert catalog.STUDIES['projects']['criterion'] != catalog.STUDIES['projects']['alternate_criterion']


def test_series_submission_budget_gate_precedes_every_external_run(tmp_path, monkeypatch, catalog):
    field = importlib.import_module('field')
    (tmp_path / 'fielding').mkdir()
    (tmp_path / 'budget.json').write_text(json.dumps({'authorized_usd_per_study': 5}))
    entries = [{'study': 'books', 'project': str(tmp_path / 'books/main'), 'batch': 'main'},
               {'study': 'books', 'project': str(tmp_path / 'books/main'), 'batch': 'followup'}]
    for entry in entries:
        (tmp_path / 'fielding' / f"{field.label(entry)}-estimate.json").write_text(json.dumps({'data': {'usd': 1.5}}))
    monkeypatch.setattr(field, 'inventory', lambda root: entries)
    monkeypatch.setattr(field, 'ep', lambda *a, **kw: pytest.fail('Must not submit over budget'))
    monkeypatch.setattr('sys.argv', ['field.py', str(tmp_path), '--submit'])
    with pytest.raises(RuntimeError, match='reserve exceeds'):
        field.main()


def test_retry_exports_only_missing_cells_and_preserves_frozen_inputs(tmp_path, monkeypatch, catalog):
    edsl = pytest.importorskip('edsl')
    retry = importlib.import_module('retry')
    from zermelo import fielding
    from zermelo.design import make_design
    from zermelo.store import Store, digest, register_entrants

    store = Store(tmp_path / 'project')
    store.initialize('Prefer higher values')
    with store.update('prepare') as (state, _):
        register_entrants(state, [{'id': f'e{i}', 'name': str(i)} for i in range(6)])
        state['batches']['main'] = {'design': make_design(state, 'main', 5, 1), 'fielding': None, 'imports': []}
    source = tmp_path / 'agents.ep'
    edsl.AgentList([edsl.Agent(name='one'), edsl.Agent(name='two')]).git.save(source)
    with store.update('export') as (state, _):
        manifest = fielding.export_batch(store, state, 'main', 'test', agents_path=source,
                                        output_path=store.root / 'main_job.ep')
    state = store.load()
    task = state['batches']['main']['design']['tasks'][0]
    manual = tmp_path / 'partial.json'
    manual.write_text(json.dumps({'schema_version': 1, 'batch_id': 'main', 'design_hash': manifest['design_hash'],
                                 'ballots': [{'task_id': task['id'], 'judge_id': 'one', 'iteration': 0,
                                              'ranking': task['entrants']}]}))
    with store.update('import') as (state, connection):
        fielding.import_results(state, connection, 'main', manual)
    before = store.load()
    original_bytes = Path(manifest['jobs_path']).read_bytes()
    monkeypatch.setattr(retry, 'jobs', lambda root: [{'study': 'books', 'project': str(store.root),
                                                   'batch': 'main', **manifest}])
    monkeypatch.setattr('sys.argv', ['retry.py', str(tmp_path), '--wave', 'format-fix'])
    retry.main()
    seen = set()
    for entry in json.loads((tmp_path / 'retry-jobs.json').read_text()):
        job = edsl.Jobs.git.load(entry['jobs_path'])
        assert len(job.agents) == 1
        judge = job.agents[0].traits['elo_judge_id']
        seen.update((scenario['elo_task_id'], judge, 0) for scenario in job.scenarios)
        assert 'return ONLY one JSON array' in job.survey.questions[0].question_text
        assert digest(job.to_dict()) == digest(edsl.Jobs.git.load(entry['jobs_path']).to_dict())
    expected = {(r['task_id'], r['judge_id'], r['iteration']) for r in fielding.coverage(before, 'main')['missing']}
    assert seen == expected
    assert Path(manifest['jobs_path']).read_bytes() == original_bytes
    assert store.load() == before
