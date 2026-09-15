# From small rankings to one overall ranking

## Design

For each round, sort entrant IDs, shuffle them with the registered random seed,
and walk through that order in groups of `k`. Advance by `k - 1`, so neighboring
groups share an entrant. If the final group is short, wrap to the beginning.
Shuffle display positions within every group.

Every round includes every entrant and has a connected comparison graph.
The number of tasks per round is `ceil((N - 1) / (k - 1))`, using
`k = min(requested chunk size, N)`. Task count therefore grows linearly in the
number of entrants for fixed group size. The planner does not enumerate all
possible entrant pairs. Appearance counts can differ; the design records them.
Different rounds reshuffle the chain. More rounds generally improve comparison
coverage, but the package does not claim that a fixed number guarantees accuracy.

## Implied wins

The ballot `A > B > C` supplies three wins: A over B, A over C, and B over C.
More generally, a strict ranking of `k` options supplies `k(k - 1)/2` wins.
Omitted options, duplicates, ties, and foreign IDs are errors.

With default `entrant` weighting, each win has weight `1/(k - 1)`.
Each entrant appears in exactly `k - 1` comparisons within a ballot, so its
weighted exposure in that ballot is one. Total ballot weight is `k/2`.
This does not equalize total exposure across entrants or judge groups. Agents
with more registered ballots contribute more evidence. Raw win/loss columns
remain unweighted counts, while scores use the selected weighting.

## Plackett–Luce (CLI default)

For a strict ranking `r1 > ... > rk`, the model likelihood is

```text
P(r | S, theta) = product over j=1..k-1 of
                 exp(theta[rj]) / sum(exp(theta[rl]) for l=j..k)
```

Zermelo minimizes the sum of negative log likelihoods of whole ballots plus
`lambda / 2 * sum(theta[i]^2)`. Stable log-sum-exp arithmetic and an analytic
gradient feed L-BFGS. Equal permutations are aggregated and fits are invariant
to import order. Each ballot has unit weight; the pair-weight option affects
BT/Elo only. The positive penalty makes estimates finite but introduces shrinkage.
For groups of two, this is the same likelihood as Bradley–Terry.

PL is a model for rankings over subsets, as described in the
[choix documentation](https://choix.lum.li/en/latest/). It assumes a common
latent strength and Luce's choice structure. LLM context effects, inconsistent
preferences and heterogeneous judges can violate those assumptions. A maximum
likelihood or penalized fit alone does not supply valid uncertainty intervals.
This package does not estimate a judge-specific or mixture PL model.

## Bradley–Terry

Each entrant has a strength parameter `theta[i]`. The probability that entrant
`i` beats `j` is

```text
P(i > j) = logistic(theta[i] - theta[j])
         = 1 / (1 + exp(theta[j] - theta[i]))
```

The implementation minimizes a weighted pairwise negative log likelihood plus
`lambda / 2 * sum(theta[i]^2)`, using L-BFGS with an analytic gradient.
The positive L2 penalty (default `lambda = 1`) keeps estimates finite for
undefeated or always-losing entrants. It also shrinks weakly measured strengths
toward zero. Scores can be sensitive to that choice in small or sparse datasets.

This follows the regularized latent-strength approach studied in
[Chen et al., Spectral Method and Regularized MLE Are Both Optimal for Top-K Ranking](https://arxiv.org/abs/1707.09971).
Here the pairwise outcomes are derived from full group rankings, so the fitted
criterion is a **composite likelihood**, not a likelihood for independent wins.

Strengths are centered and displayed on a familiar Elo scale:

```text
rating[i] = 1500 + 400 / log(10) * theta[i]
```

A 400-point difference corresponds to modeled odds of 10:1. The 1500 origin is
arbitrary. The ratings are estimates for this entrant pool, criterion, and judge
mixture; they are not calibrated against an external rating system.

This model supplies the desired latent overall ordering. A fuller IRT model
could add judge discrimination or preference dimensions, but those parameters
are not estimated here. A generic judge intercept would cancel when comparing
two entrant scores for the same judge.

## Elo

All entrants start at 1500. Ballots are processed in a deterministic order by
batch/task/judge/iteration key. For each implied win, calculate

```text
expected = 1 / (1 + 10^((loser_rating - winner_rating) / 400))
change = K * weight * (1 - expected)
```

Add the change to the winner and subtract it from the loser. Accumulate all
changes using pre-ballot ratings and apply them simultaneously at the end of the
ballot. This removes dependence on arbitrary pair order inside a ranking.
It retains Elo's dependence on ballot order. The package performs one pass,
with default `K = 32`; repeated import does not create repeated passes.

All methods preserve mean rating 1500. Numerically equal scores receive the
same rank, with entrant ID used only to order their display rows.

## Identification and limits

The observed comparison graph must be connected, including every registered
entrant. Otherwise, scores across components are supported only by the penalty,
and the CLI refuses to produce an overall ranking. Missing assignments prevent
ranking unless `--allow-incomplete` is explicit; it does not waive connectivity.

Connectivity is necessary but does not ensure a precise ranking. A graph joined
by only a few comparisons can be fragile. Examine appearance counts and unique
pair coverage, increase rounds, and compare results across seeds and judge panels.

Group context and display position can affect judgments. Wins within a ballot
are dependent, and repeated calls to the same agent/model can also be dependent.
The package does not report confidence intervals that treat those wins as
independent samples. It does not estimate population shares from synthetic
agents, model preference cycles, or infer a universally correct order.

The group-ranking question uses EDSL's native
[QuestionRank](https://docs.expectedparrot.com/en/latest/questions.html), with
fixed-length options and explicit full-ranking validation on import.


## Adaptive selection and incremental entrants

The initial randomized overlapping chain is unchanged. A neighborhood wave
re-fits PL with penalty one to observed production ballots, orders entrants by
strength, and reserves a chain that covers and connects the pool. Additional
windows prioritize centers with weight `1/(1 + I_i)`, where `I_i` sums pairwise
logistic curvature `p_ij(1-p_ij)/(k-1)` over appearances. This diagonal surrogate
ignores covariance and is used only as a scheduling heuristic. It is not a sigma
estimate or proven expected information gain. Random bridge tasks occupy a
requested fraction of the total wave, limited by the remaining task budget.

The mandatory chain provides the connectivity guarantee; a positive random
bridge probability alone would not. `--only-new` connects every unobserved entrant
to well-spaced observed anchors, using the old observed graph for connectivity.
Past entrant snapshots are immutable. Newly added isolated nodes prevent scoring
until bridging results arrive. A disconnected observed core needs a random
coverage wave before a neighborhood fit is possible.

The wave records its input hash, selection method, penalty, task kinds, requested
budget and coverage. No online TrueSkill state is maintained: a full PL re-fit
provides the next wave's ordering. This avoids mixing an online approximation's
scale or dynamics with an unrelated final likelihood model.

## Calibration and information bounds

See the [sorting post](https://www.thariq.io/blog/sorting/) for the small-group
ranking idea. Zermelo's calibration samples nested subsets across sizes, repeats
each subset with randomized display positions, and compares complete rankings
within the same judge. Normalized Kendall distance is the fraction of pair orders
that differ. Subset/judge means, not all dependent pair comparisons, are averaged.

Repeated agreement measures reproducibility, not truth. It cannot identify an
adjacent-transposition error rate, a binary symmetric channel, or a TrueSkill
noise scale without additional assumptions. An optional externally justified
reference ranking supplies a separate error diagnostic. Different candidate
sizes must use identical judges, model settings and iterations. Replicate prompt
markers reduce identical cache reuse but do not establish independent draws.
Calibration ballots are excluded from production estimation and design priorities.

There are `n!` possible total orders. A perfect size-k ranking query has at most
`k!` possible outputs, so an adaptive decision tree of depth M has at most
`(k!)^M` leaves. Consequently an arbitrary exact noiseless sort requires
`M >= ceil(log2(n!)/log2(k!))`. It is a necessary counting bound, not a sufficient
sample size. Approximate rank error additionally depends on the distortion
criterion, item strengths, comparison design and response noise. Summing
`log2(k!)` over repeated answers measures an output capacity ceiling, not the
information actually learned. The binary formula `1-H(epsilon)` is not silently
applied to ranking outputs.

Recommendations screen sizes by a user-chosen disagreement threshold, optionally
also reference error, then compare capacity per supplied dollar (or choose the
largest eligible size without prices). This is a transparent heuristic, not a
claim to have estimated an optimal group size.

## Uncertainty and stopping diagnostics

Optional normalized exponential multiplier weights are drawn per task cluster
(all its judges and iterations together), or per judge (all that judge's ballots
together). Every replicate re-fits the same penalized model. All weights remain
positive, maintaining the observed comparison graph. No pair-level resampling
is used. With few clusters, dependence across clusters, model misspecification or
strong shrinkage, the reported ranges can be misleadingly narrow. Judge and task
clustering answer different sensitivity questions, and neither captures every
source of dependence. Adaptive selection remains conditioned on the observed
wave history, not re-simulated inside these perturbations.

The output reports per-entrant rank quantiles and strength SD, adjacent-pair
reversal frequencies, and the 95th percentile of maximum movement from the fit.
These are **conditional sensitivity diagnostics**, not calibrated posterior
probabilities or coverage guarantees. The sum of adjacent reversal frequencies
is an expected adjacent reversal count under these perturbations; it is not
expected Kendall distance or expected error against an unknown true order.

Snapshot assessment checks for new unchanged ballots, complete production
coverage, matching entrant IDs, model/judge definitions and fit settings. It compares Kendall tau and
maximum movement, then tests both observed movement and perturbation movement
against a fraction of the list length. Its review flag is advisory. It does not
spend credits, run another wave, or certify a true-order tolerance. Stability
across overlapping snapshots is dependent and can occur for a wrong ordering.
