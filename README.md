# Zermelo

<p align="center">
  <a href="https://github.com/expectedparrot/zermelo"><img src="docs/assets/zermelo-artwork.jpg" width="640" alt="Zermelo artwork: two parrots playing chess inside expectation brackets"></a>
</p>

Rank a large pool of options by asking agents to rank small, overlapping groups.
Zermelo fits whole group rankings with **Plackett–Luce**, or combines their implied
pairwise wins using **Bradley–Terry** scores or **Elo ratings**. Repeated-subset
calibration and connected adaptive waves help decide what to ask next.

For 20 entrants, groups of five, and three rounds, the default design produces
**15 tasks per judge**, each containing five options. Overlap connects the groups
into one comparison network. No judge needs to rank all 20 at once.

The package registers entrants, prepares native Expected Parrot jobs, imports
results, and produces JSON or CSV rankings. Execution is a separate `ep run` step.

**Worked tutorial:** open `docs/index.html` from this checkout. It explains the
complete method using a live 50-state example, with captured commands, an
interactive ballot-to-wins explanation, score interpretation, and actual results.

## Install

From this directory:

```bash
uv pip install -e '.[fielding,dev,docs]'
```

Or use `python -m pip install -e '.[fielding,dev,docs]'`. The distribution is named
`zermelo`; its Python module and command are `zermelo`. Omit `fielding` if you only need
planning and the Python scoring API. Native job export/import requires EDSL.

```bash
zermelo version
zermelo capabilities
zermelo guide
```

## Quick start

The included entrants are 20 fictional e-commerce product improvements. Choose a
specific criterion; all batches within the project use it.

```bash
zermelo project use runs/shop
zermelo init --criterion 'Rank improvements by expected benefit to your shopping experience, best first.'
zermelo entrants import examples/entrants.csv
zermelo batch plan first --chunk-size 5 --rounds 3 --seed 42
zermelo batch show first
```

Export with your EDSL model name in place of `MODEL`. The supplied agent profiles
are illustrative synthetic perspectives.

```bash
zermelo rankers add examples/agent_list.ep
zermelo rankers list
zermelo batch export first --model MODEL --output runs/shop/ranking_job.ep
```

Export returns the exact `ep run` command, paths, model settings, and expected call
count: **45 calls** for three judges in this example. Review the design and run
that command when ready to execute model inference. EDSL owns authentication.

```bash
ep jobs cost runs/shop/ranking_job.ep
ep run --jobs runs/shop/ranking_job.ep --remote_inference_results_visibility private --output runs/shop/ranking_results.ep
zermelo results import first
zermelo rank --output runs/shop/rankings.csv
zermelo rank --method elo --output runs/shop/elo-rankings.json
```

`rankings.csv` contains rank, entrant ID/name, rating, latent strength, ballot
count, wins, and losses. `rankings.metadata.json` records method settings, coverage,
input hash, and limitations. CLI commands emit one JSON envelope; `--help` is text.

### Set the project once

`zermelo project use runs/shop` saves a `.zermelo-project` marker in the current
directory. Commands in that directory and its descendants use the selected
project. The marker stores a relative path, so moving the workspace preserves
in-workspace selections. Selection can precede `init`.

```bash
zermelo project show
# Alternative for just this shell:
export ZERMELO_PROJECT="$PWD/runs/shop"
```

Precedence is: an explicit `--project DIR`, then `ZERMELO_PROJECT`, then the
nearest saved selection or containing initialized project, then the current
directory. `project show` explains the effective choice; `project clear` removes
only the marker in the current directory. An exported environment variable
continues to apply until you unset it.

### Supply native rankers

The included `examples/agent_list.ep` contains three hand-authored synthetic
shopping perspectives. The states script similarly creates six authored travel
profiles. These are supplied persona definitions, not people sampled from a
population or agents discovered by the package. Create your own list with EDSL:

```python
from edsl import Agent, AgentList

rankers = AgentList([
    Agent(name="value", traits={"priority": "Prefer value for money."}),
    Agent(name="quality", traits={"priority": "Prefer quality and reliability."}),
])
rankers.git.save("agent_list.ep")
```

```bash
zermelo rankers add agent_list.ep
```

Registration keeps the original bytes, source hash, and a versioned native
`AgentList` snapshot under the project. Adding identical agents deduplicates;
a changed definition under an existing name fails. Use a new name to add a new
perspective. Export freezes whichever registered panel is current at that point.

### Choose the job and results paths

`batch export --output runs/shop/ranking_job.ep` creates a native job at that
exact path and keeps a verified archival copy. By default, results are expected
beside it at `ranking_results.ep`; `--results-output PATH` can override this.
Export returns `jobs_path`, `results_path`, and ready-to-use `cost_command`,
`run_command`, and `import_command`. No inference runs during export.

`results import BATCH` reads the saved results destination. Supply a filename
when importing a retry or a file downloaded elsewhere. Existing output files
are never overwritten. Without `--output`, the original internal batch path
remains available for compatibility. In-project paths resolve after moving a
project; paths explicitly exported outside it remain external.

### A no-cost execution smoke test

Use a separate project and replace the export/run steps with:

```bash
zermelo project use runs/smoke
zermelo init --criterion 'Smoke test only: exercise the ranking workflow.'
zermelo entrants import examples/entrants.csv
zermelo batch plan first --chunk-size 5 --rounds 3 --seed 42
zermelo batch export first --model test --model-parameters examples/test-model.json --output runs/smoke/ranking_job.ep
ep run --jobs runs/smoke/ranking_job.ep --local --output runs/smoke/ranking_results.ep
zermelo results import first
zermelo rank
```

The test model ranks options in their displayed order. Those outputs verify the
software path; **they are not evidence about the entrants**. The canned answer has
five indices and therefore requires five-option groups.

## More comparisons and recovery

For a larger live example, see [50 states and six traveler profiles](examples/states_visit/README.md).

```bash
zermelo project use runs/shop
zermelo status
zermelo next
zermelo batch plan second --chunk-size 5 --rounds 3 --seed 43
```

Export and field the second batch in the same way. `rank` pools all project
ballots. Different batches may use different agents or models; this changes the
mixture of judgments being estimated. The criterion and existing entrant definitions
are immutable. You can append entrants; earlier batch snapshots stay unchanged.

Missing assignments appear in `status`. Re-running the original jobs can use
EDSL's cache for successful calls; save retry results under a new filename and
import them separately. Identical ballots are counted once. Conflicting answers
for the same batch/task/judge/iteration are rejected; use a new batch or declared
iterations to collect additional independent judgments.

An import rejects invalid rankings by default, atomically. To retain usable rows
from a partially failed result file, add `results import ... --skip-invalid`.
Every rejected row is reported and the original result bytes are preserved.
Mismatched assignments, judge definitions, and model settings always fail.

Native EP results may contain entrant IDs or zero-based option indices. The
importer maps exact full integer permutations through the frozen task's option
order and reports `native_code_rows_mapped`. Original result bytes are preserved.
Manual JSON ballots always require entrant IDs; indices are not accepted there.

`rank` requires every production batch to be exported and complete. Calibration
batches are analyzed separately and never enter production scores. Use
`--allow-incomplete` for an explicitly provisional ranking; disconnected observed
comparisons still fail. The package accepts strict full rankings only, without
ties or partial top-k answers.

## Inputs and methods

- Entrants: JSON array or CSV with `id`, `name`, and optional `description`.
  IDs start with a letter and use up to 80 letters, digits, hyphens, or underscores.
- Rankers: `rankers add agent_list.ep` registers a native EDSL `AgentList` with
  unique valid agent names (or legacy `elo_judge_id` traits). Unnamed agents and
  descriptive names containing spaces receive deterministic IDs automatically. Subsequent exports
  use this panel automatically. `rankers list` displays definitions and sources.
  Existing batch panels never change when more rankers are added. With neither
  registered rankers nor an explicit file, export uses one neutral judge.
  `batch export --rankers other.ep` overrides the panel for one batch; the old
  `--agents` option and JSON inputs remain available for compatibility.
- Model parameters: `--model-parameters settings.json` freezes generation settings
  such as `temperature` and `max_tokens` into the jobs. `--service` can select an
  inference service explicitly. `--iterations` declares repeats per assignment.
- Manual ballots: `results template BATCH --output ballots.json` supplies missing
  task/judge/iteration cells. Fill each `ranking` with entrant IDs, best first, and
  import it. Manual sources remain labeled separately from native EP results.

**Plackett–Luce is the CLI default.** It fits the probability of each full ranking
as successive selections from the remaining alternatives. It uses one likelihood
contribution per ballot and a positive L2 penalty. This is a modeling assumption,
not a claim that LLM judgments follow this distribution exactly.

`--method bt` fits pairwise Bradley–Terry composite likelihood. Its default
weighting gives each implied win weight `1 / (group size - 1)`; `--weighting pair`
uses unit pair weights. These weights do not change the whole-ranking PL fit.
`--method elo` provides the original sequential comparator. All methods center
ratings at 1500. For compatibility, the Python `score()` API retains its `bt`
default; pass `method="pl"` explicitly.

## Calibrate on your options

Choose sizes that fit the sampled pool (these defaults require at least 16 entrants):

```bash
zermelo calibrate plan pilot --sample 20 --batch-sizes 4,8,12,16 --subsets 10 --repeats 3 --seed 42
zermelo batch export pilot-k4 --model MODEL --output runs/shop/pilot-k4_job.ep
```

Export **each** `pilot-k4`, `pilot-k8`, `pilot-k12`, and `pilot-k16` batch using
identical model parameters, agents and iterations. Run each returned `ep run`
command, then import its results with `results import BATCH PATH`. This design
uses 30 tasks per size per judge: 360 calls for four sizes and three judges.
Planning and exporting make no inference calls.

```bash
zermelo calibrate analyze pilot --max-disagreement .1 --output runs/shop/calibration.json
```

Repeated subsets keep their membership and shuffle their display order. Analysis
measures mean normalized Kendall disagreement **within each judge**, then averages
subset/judge groups. It never mistakes disagreement between different traveler
profiles for repeat noise. An explicit replicate marker varies the rendered prompt
to avoid identical cache entries; statistical independence is still an assumption.

Without costs, the recommendation is the largest completed candidate size passing
your disagreement threshold. Optional `--costs costs.json` supplies estimated
USD/call by size, e.g. `{"4":0.001,"8":0.002,"12":0.003,"16":0.004}`. Eligible sizes
are then compared using `log2(k!)/cost`, an alphabet-capacity heuristic. It is **not
measured useful information or proven optimality**. `--reference truth.json` adds
error against an externally justified JSON ordering of all snapshot IDs. The same
threshold applies to reference error. Incomplete candidates prevent a recommendation.
A consistently wrong model can have zero disagreement.

## Plan adaptive waves and incremental entrants

After a completed production wave:

```bash
zermelo rank --bootstrap 200 --output runs/shop/wave-1.json
zermelo batch plan wave-2 --strategy neighborhood --chunk-size 5 --rounds 1 --tasks 20 --bridge-frac .1 --seed 43
```

The planner re-fits PL to current production ballots. It first reserves a chain
covering every entrant, then allocates the remaining tasks to random bridges and
nearby ranks. Low comparison information increases a neighborhood's sampling
priority. That priority is a scheduling proxy, not a posterior variance. `--tasks`
is an exact task budget **including** the reserved coverage; insufficient budgets
fail. For 20 entrants and groups of five, five tasks are mandatory; this example
adds two random bridges and thirteen targeted neighborhoods. Multiply by judges
and iterations to obtain the expected model call count. Extra tasks are optional;
without `--tasks`, adaptive planning adds `ceil(mandatory_tasks * bridge_frac)` tasks.
The requested bridge fraction is capped by space left after mandatory coverage.

Export, run and import `wave-2`, then compare snapshots:

```bash
zermelo assess runs/shop/wave-1.json --tolerance .02 --bootstrap 200 --output runs/shop/assessment.json
```

`assess` requires new ballots, unchanged previous ballots, complete production
coverage, and the same entrants, model/judge definitions and fit settings. It reports Kendall stability,
maximum movement, and the 95th percentile of maximum rank movement under cluster
perturbations. A `.02` tolerance means 2% of the list's length **relative to the
previous fit and perturbations**, not error against truth. The review flag asks
you to consider stopping; repeated stable snapshots can still be wrong.

`rank --bootstrap 200` assigns normalized exponential weights to whole task
clusters and re-fits the model. All judges and iterations for a task move together.
`--cluster judge` instead perturbs the judge mixture. Rank ranges, strength SDs and
adjacent reversal frequencies live in JSON or the CSV metadata sidecar. These are
conditional sensitivity diagnostics, not calibrated posterior probabilities or
confidence intervals. Positive weights preserve the observed graph. Neither
clustering captures every dependence of adaptive model judgments.

To append entrants without changing historical designs:

```bash
zermelo entrants import more.csv
zermelo batch plan newcomers --only-new --chunk-size 5 --rounds 1 --seed 44
```

Every new task includes an unobserved entrant. Mandatory tasks connect each newcomer
to anchors spread across the existing ranking. The combined observed/planned graph
must connect the pool; scoring still refuses isolated entrants until results arrive.

## Information and dollar budgets

```bash
zermelo budget --entrants 10000 --chunk-size 10 --calls 500 --cost-per-call .002 --budget 5
```

An arbitrary noiseless exact sort needs at least `log2(n!)/log2(k!)` calls, rounded
up: about 5,400 for 10,000 options and groups of ten. Five hundred calls have at most
about 10,896 bits of transcript capacity, versus about 118,458 bits for the total
order. Neither quantity says how much information was actually learned. Noise,
redundant comparisons and preferences that lack a single true order matter.
The command deliberately does not convert this lower bound into a promised rank
error or stopping rule. Cost estimates are user-supplied and exclude retries;
`--budget` does not enforce an EP spending cap.

The package uses a full PL re-fit between waves rather than adding a separate
TrueSkill approximation and an unidentifiable noise calibration. It does not infer
TrueSkill beta from self-consistency. See [the method notes](docs/method.md).

## Rename compatibility

The distribution, import package and executable are now `zermelo` (0.2.0).
Reinstall the editable package to get the command. Existing `elo.sqlite3` projects
are read in place, preserving all designs, result bytes and registrations. New
projects use `zermelo.sqlite3`; ambiguous directories containing both names fail.
The EP interchange fields retain the historical `elo_*` identifiers so original
jobs and results still match. The statistical method is still named `elo`.
The checkout directory does not need to be renamed. No `elo` import/CLI alias is
installed by the new distribution.

## Local artifacts

```text
project/
  zermelo.sqlite3               # Entrants, plans, ballots, registrations, original result bytes
  rankers/HASH/agent_list.ep # Immutable native ranker snapshot
  ranking_job.ep            # Chosen export path, ready for ep jobs cost / ep run
  ranking_results.ep        # Expected results path
  batches/first/
    design.json             # Frozen criterion, entrant snapshot, seed, assignments, coverage
    manifest.json           # Agents/model, hashes, expected calls, external run command
    jobs.ep                 # Native, save/load-verified EDSL Jobs
    results.ep              # Created externally by ep run
  rankings.csv
  rankings.metadata.json
```

Artifacts are not overwritten. Preserve the database and batch directories
together. Generated projects belong under `runs/`, which is gitignored.

## Development

```bash
pytest -q
ruff check zermelo tests
```

The tests cover connected designs, statistical recovery from simulated outcomes,
native `.ep` round trips, strict import validation, transactional failure,
deduplication, missing coverage, and CLI envelopes. No paid model calls are needed.

To rebuild the tutorial from the preserved states run:

```bash
python examples/states_visit/build_tutorial.py runs/states_visit_20260914
```


The worked index includes Bash syntax highlighting and four diagnostic plots:
pair coverage, task-cluster rank sensitivity, between-ranker disagreement, and
rank movement as rounds accumulate. PNG/SVG downloads accompany each plot.
The `docs` extra supplies Pygments and Matplotlib for rebuilding them.
