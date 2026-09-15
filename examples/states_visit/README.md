# Live example: 50 states and six travelers

The package's complete worked tutorial is `docs/index.html`. It is generated from
`tutorial.template.html` and the preserved live data by `build_tutorial.py`.
The run-specific dashboard described below is a separate analysis artifact.

This example compares all 50 U.S. states using six synthetic traveler profiles:
outdoors, cities and culture, beaches, food and music, history, and family travel.
The state cards are illustrative summaries, not exhaustive travel research.

The completed local run is preserved under `runs/states_visit_20260914/`.
Open `reports/index.html` for the interactive results, or `reports/summary.md`
for a written summary. The report lets you choose a traveler and scoring method.

## Design and observed outcome

- Five states per ranking, five shuffled rounds, 65 tasks per traveler.
- 390 complete rankings and 3,900 implied wins, covering 518 distinct state pairs.
- Gemini 3.1 Flash-Lite through EP's Google service, with private results.
- 388 valid rankings in the first run. Two assignments required retries; one
  required an explicit response-format reminder after repeated validation errors.
- Native results contained zero-based option indices. The importer decodes these
  through the frozen display order and preserves the original result bytes.

The pooled Bradley–Terry top five were California, North Carolina, New York,
South Carolina, and Georgia. Profile-specific results differ substantially.
Bradley–Terry and Elo shared nine of their top ten states and had rank correlation
0.985. These results describe the selected model-generated personas, not actual
travelers or population preferences.

## Reproduce the workflow

1. Select the project once with `zermelo project use runs/NEW_RUN`.
2. Run `python examples/states_visit/prepare.py runs/NEW_RUN/inputs`. This writes
   the state cards and six hand-authored traveler profiles as a native
   `inputs/agent_list.ep`, plus model parameters and design notes.
3. Run `zermelo init --criterion TEXT`, using `inputs/design-notes.json`.
   Import entrants with `zermelo entrants import runs/NEW_RUN/inputs/entrants.csv`
   and register the rankers with `zermelo rankers add runs/NEW_RUN/inputs/agent_list.ep`.
4. Plan `zermelo batch plan main --chunk-size 5 --rounds 5 --seed 20260914`, then
   export with `zermelo batch export main --model gemini-3.1-flash-lite --service google
   --model-parameters runs/NEW_RUN/inputs/model-parameters.json
   --output runs/NEW_RUN/ranking_job.ep` (as one command).
5. Use the returned cost and run commands, or run
   `ep jobs cost runs/NEW_RUN/ranking_job.ep` and
   `ep run --jobs runs/NEW_RUN/ranking_job.ep --remote_inference_results_visibility private
   --output runs/NEW_RUN/ranking_results.ep`. For background jobs, download to
   this expected results path afterward.
6. Run `zermelo results import main --skip-invalid`, then inspect `status` and
   `next`. `retry_jobs.py PROJECT` exports jobs for missing assignments; run the
   returned EP commands externally and import each explicit retry filename.
7. Run `zermelo rank --method bt --output runs/NEW_RUN/rankings.csv` to reproduce
   the original method. Compare with `--method pl` or `--method elo` in new files.
8. With the `docs` extra installed, `python examples/states_visit/report.py runs/NEW_RUN`
   creates the separate run report. The package tutorial's diagnostic figures are
   rebuilt using `build_tutorial.py` against the preserved original run.

The report script expects the same example layout and a saved EP cost estimate at
`logs/cost-estimate-live.json`. Preserve all source jobs, results, retry notes,
registrations, and CLI logs. Reuse new project directories rather than overwriting
this completed run. Model execution always remains an external EP command.


## Zermelo 0.2 re-analysis

The package and CLI were renamed from `elo` to `zermelo` after the live run.
The original database and artifacts retain their names. Current CLI ranks default
to Plackett–Luce; the reproduction commands above explicitly request the historical
BT analysis. A local re-fit of the same 390 live ballots puts California, North
Carolina, Georgia, New York and South Carolina first under PL. No new inference
was needed. The worked tutorial includes all three methods, task-cluster
sensitivity ranges, and previews of calibration and adaptive follow-up commands.
These previews have not been fielded on the live states project.
