# Working on Zermelo

- Use `zermelo guide`, `zermelo --help`, and `zermelo next` for the workflow.
  Select a project with `zermelo project use DIR` or `ZERMELO_PROJECT`.
- Keep model execution in external `ep run` commands. Exporting jobs must never
  submit inference or spend credits.
- Preserve entrant snapshots, designs, `.ep` jobs, original result bytes, source
  registrations, and score metadata. Do not silently replace conflicting ballots.
- Keep generated projects in `runs/`. Do not commit credentials or private runs.
- Use `pytest -q` and `ruff check zermelo tests` after code changes. Native integration
  tests require the fielding extra and use EDSL's test model, without paid calls.
- Keep README commands and CLI guide/next guidance aligned with behavior.
- Keep `docs/index.html` as the worked methodological tutorial. Rebuild it with
  `python examples/states_visit/build_tutorial.py runs/states_visit_20260914` after
  changing its template or captured example data; preserve live source artifacts.
- Statistical changes need meaningful recovery or invariant tests. Do not treat
  wins implied by the same ballot as independent observations for uncertainty.

- Prefer native AgentList .ep files registered with `rankers add`; retain source
  bytes and immutable snapshots. Exports must preserve their frozen ranker panel.
- Show explicit shallow job paths with `batch export --output` in examples.
  Keep returned cost/run/import commands and optional-path ingestion aligned.
- Tutorial code blocks use build-time syntax highlighting; diagnostic figures
  must distinguish task counts, ranker disagreement, and conditional sensitivity.
