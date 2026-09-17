# Ten ranking experiments for a blog series

This collection contains ten reproducible studies using **1,015 original concept
cards**, six explicitly authored synthetic profiles per study, and real external
EP judgments. Book and movie cards describe **fictional concepts**, not published
works. The catalog crosses concept families with stated variants; it is a
controlled authored collection, not a representative sample of options or people.

| Study | Cards | Demonstration |
|---|---:|---|
| `books` | 100 | Individual versus pooled reader preferences |
| `features` | 80 | Frozen panels and a 30-task adaptive follow-up |
| `library` | 100 | Ranker disagreement and explicit subgroup sensitivity |
| `names` | 200 | Calibration at group sizes 4, 8, and 12 |
| `movies` | 75 | Pooled favorites versus a worst-individual-rank diagnostic |
| `projects` | 60 | Identical cards and profiles, two separately frozen criteria |
| `talks` | 120 | Rank 100 proposals, then connect 20 late arrivals |
| `openings` | 100 | 200 task-cluster conditional-sensitivity draws |
| `museum` | 80 | PL, BT, and Elo fitted to identical accepted ballots |
| `blog` | 100 | Guided workflow, deliberate partial ingestion, then 20 late ideas |

The six profiles are defined in `catalog.py`; none are sampled people. Each
family/variant pair has its own stable ID and description. The opening-paragraph
cards contain original prose; other cards describe concepts. The initial blog
study fields 80 cards before its final 20 arrive.

## Prepare without inference

Install the repository's `fielding`, `dev`, and `docs` extras. Run these commands
from the repository root, using the Python environment where Zermelo is installed:

```bash
python examples/blog_series/prepare.py runs/blog_demo \
  --model gemini-3.1-flash-lite --service google
```

Preparation creates native `agent_list.ep` files, registers the six rankers,
freezes entrant definitions and criteria, plans designs, and exports jobs. It
**never submits model inference**. It requires a fresh directory under `runs/`.
For example, its export corresponds to:

```bash
zermelo --project runs/blog_demo/books/main batch export main \
  --model gemini-3.1-flash-lite --service google \
  --model-parameters runs/blog_demo/books/main/inputs/model-parameters.json \
  --output runs/blog_demo/books/main/main_job.ep
```

The default production design uses groups of five, three rounds, and six profiles.
Temperature is 0.3, the output limit is 2,048 tokens, and seeds are explicit. The
programming-project study initializes a second project for the learning criterion.
The naming study starts with calibration only: six subsets, three shuffled repeats,
and six profiles for each group size, with a prespecified disagreement threshold
of 0.20. If no candidate qualifies, `advance.py` records an explicit exploratory
fallback to the smallest tested size; the report does not call that a successful
calibration.

## Estimate, execute externally, and preserve the results

The recorded run was authorized for $5 per example, including follow-ups and
retries. `budget.json` holds that allocation. Estimates are point estimates, not
price guarantees. The submission helper requires a twofold estimate reserve
within each study's allocation and retains all prior jobs in its running estimate.

```bash
python examples/blog_series/field.py runs/blog_demo --estimate
python examples/blog_series/field.py runs/blog_demo --submit
python examples/blog_series/field.py runs/blog_demo --collect
```

`--submit` is the only operation here that submits inference. It invokes external
`ep run --background` commands with private visibility. Background submissions do
not use `--output`; collection downloads results to the frozen expected path:

```bash
ep jobs cost runs/blog_demo/books/main/main_job.ep
ep run --jobs runs/blog_demo/books/main/main_job.ep \
  --background --task-timeout 900 \
  --remote_inference_results_visibility private
# Use the returned UUID:
ep jobs results JOB_UUID --output runs/blog_demo/books/main/main_results.ep
zermelo --project runs/blog_demo/books/main results import main --skip-invalid
```

Call `--collect` again while jobs are pending. It saves status responses and never
resubmits a job. Submission intent is written before the remote call. If a process
fails between submission and its response, inspect the private records and EP job
list before retrying; do not risk an accidental duplicate submission.

Once results are downloaded:

```bash
python examples/blog_series/advance.py runs/blog_demo
```

This imports original results and exports the feature-specific next waves. It
never runs models. Repeat **estimate → submit → collect → advance** until all
projects have `final.json`. Follow-ups count toward the same example's budget.
For missing assignments, inspect `zermelo --project PROJECT status` and `next`.
Keep every retry file and import it explicitly; conflicting ballots remain errors.

The recorded first wave exposed response-validation failures. A five-assignment
probe validated an explicit integer-permutation response reminder. `retry.py`
exports only missing cells, grouped by ranker to avoid accidental cross-products:

```bash
python examples/blog_series/retry.py runs/blog_demo --wave format-recovery
python examples/blog_series/field.py runs/blog_demo --estimate
python examples/blog_series/field.py runs/blog_demo --submit
python examples/blog_series/field.py runs/blog_demo --collect
python examples/blog_series/advance.py runs/blog_demo
```

Each retry has its own immutable manifest recording the response-format addition,
original job and design, assigned tasks, and frozen model. Successful ballots are
not resubmitted. This helper supports the iteration-zero studies in this collection.
The formatting change could influence responses and is disclosed in the report;
it is not presented as an identical-prompt replication. New exports now include
the explicit instruction from the start.

The blog workflow demonstration deliberately imports half of an already returned
artifact, records incomplete guidance, then imports the original complete file.
It demonstrates deduplication and recovery from partial ingestion, **not a claimed
model failure**. Genuine failed interviews, if any, remain separately recorded.

## Build the blog draft

```bash
python examples/blog_series/report.py runs/blog_demo
```

This creates `reports/blog-post.md`, a local `reports/index.html` preview, ten
profile-disagreement figures, and `analysis.json`. It refuses to replace an
existing report directory. It fits per-profile PL rankings, compares PL/BT/Elo,
checks panel and criterion sensitivity, and reports recorded token costs. Returned
per-result token costs are not a reconciled account bill; private status and
submission logs remain separate from the blog draft.

The plots distinguish **task counts**, **between-ranker disagreement**, and
**conditional sensitivity**. Implied wins from the same ballot are not treated as
independent observations. The bootstrap reweights entire tasks across their
rankers. Neither stability nor synthetic agreement establishes population accuracy.
All jobs, original result bytes, registrations, source definitions, and score
metadata remain under the run directory. Credentials are never copied into it.
