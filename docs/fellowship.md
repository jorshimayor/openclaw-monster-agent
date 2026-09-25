# Flow Research fellowship

48 weeks, 20 hours a week, Cohort 1 · 2026. Distilled from the fellowship
guide, the programme overview and the Applied AI Engineering team charter into
something that files commitments, chases you for them, and leaves a record.

## The one value that has to be right

`start_date` in [`backend/config/fellowship.json`](../backend/config/fellowship.json)
— the Monday of week 1. Every due date, every reminder and the whole timeline
derive from it. It reads **2026-09-21** — the Monday of the week the cohort
started. Change that one line if it moves; nothing else needs touching.

A mid-week start still counts as week 1, and the week does not advance until
the following Monday — twenty hours is not a Monday job, so the week's work
stays on the board for all seven days.

## Why it is not a rotation

Everything else in the study system cycles: what lands today is the date modulo
a cycle length. The fellowship has a beginning, an end, a week 17 that depends
on a decision made at week 17, and a week 31 that makes no sense before week
30. So it resolves from a start date instead, in
[`backend/src/agents/fellowship.py`](../backend/src/agents/fellowship.py), and
the rotation grew one small hook (`plan: "fellowship"`) to call it. Before week
1 and after week 48 the theme goes quiet rather than filing against a programme
that is not running.

## What lands each day

The `flow-fellowship` theme is first in the daily list and due at **18:00** —
the evening block, because the mornings are already spoken for by web3 and
twenty hours a week needs a protected slot rather than whatever is left over.

**Chased every day**, because twenty hours a week does not happen by
remembering on Monday:

- the anchor reading, to read **and reproduce**
- the week's lab
- a one-paragraph thought log

**Filed once and due Sunday 20:00**, because chasing a weekly thing daily is
noise:

- one chapter of the running book
- the phase deliverable, when the week ends a phase
- anything in `assignments` for that week
- the weekly what-shipped/what-broke update
- **CLOSE THE WEEK** — the artifact gate

The distinction is in the filing key. A task with one is filed once for the
week; a task without one re-files every day. A chapter filed daily would be
seven commitments for one chapter.

## The artifact gate

Nothing about a week is finished until something exists that someone else
could open: the notebook, a published article, or a link. The gate is due
Sunday 20:00 and is an ordinary commitment, which means
[`artifact.py`](../backend/src/core/artifact.py) already governs it — an
acknowledgement does not close it, only a link, a file, or 40+ characters of
real text.

## Books alongside the plan

`books` in the config runs one chapter a week. The chapter number is derived
from the week, so nothing has to be ticked off for the count to stay right,
and a book runs out rather than looping.

Currently running: **AI Engineering**, Chip Huyen (O'Reilly), from week 1.
The chapter titles in the config were written from memory — correct any that
are wrong, they only have to be recognisable enough to know where you are.

## The command line

```bash
python3 -m fellowship status        # where you are on the 48 weeks
python3 -m fellowship lab           # generate this week's Jupyter notebook
python3 -m fellowship note "..."    # log a thought against this week
python3 -m fellowship assign "Eval harness brief" --kind project --due 2026-11-02
```

`assign` writes into `assignments` in the config, so work handed to you
mid-programme is filed and chased exactly like planned work instead of living
in a document nobody opens. Kinds: `assignment`, `book`, `project`, `reading`,
`deadline`.

## The notebooks

`python3 -m fellowship lab` writes `fellowship/labs/wNN-topic.ipynb` with the
same five sections every week, so the record is comparable at week 40 to what
it was at week 4:

1. **The paper** — with Keshav's three passes spelled out, because starting at
   the top and reading to the bottom is the thing that does not work.
2. **Reproduction** — and a prompt to write down what would falsify the claim
   *before* running anything.
3. **Lab** — the week's brief.
4. **Thoughts** — what surprised you, what you did not believe, what you would
   test next, and where it connects to the team's research directions.
5. **Article seed** — the angle while it is fresh, not a draft.

An existing notebook is never overwritten without `--force`. That is where the
week's thinking lives.

Read ahead with `--week N` at any time, including before week 1:

```bash
python3 -m fellowship lab --week 1
python3 -m fellowship lab --week 17 --path A   # weeks 17-21 split by track
```

## Publishing

The programme grades a weekly reading-and-reproduction habit and ends at week
47 with a write-up that joins the team's research record. The article seed in
each notebook is the input to that; run drafts through `/write` against
[`docs/writing-standard.md`](writing-standard.md) before publishing.

Weeks 15-16 and 47-48 are the two capstones. Weeks 21, 26, 40 and 46 each
produce something publishable in its own right — a stage write-up, a defended
proposal, a pivot decision, a postmortem.

## The week 17 decision

Weeks 17-21 split into Path A (Agentic Systems & Evaluation) and Path B
(Search & Retrieval Systems). `path` is `null` until you choose. While it is
null those weeks file **the decision itself** as the task rather than silently
picking a track, because week 17 is exactly where the choice is supposed to be
made deliberately, informed by the exposure systems built in weeks 9-14.

Set `"path": "A"` or `"B"` in the config when you decide.

## What this does not do

- **It does not know your cohort's actual dates.** `start_date` is a guess at
  the coming Monday until you say otherwise.
- **It does not track hours.** Twenty a week is the expectation; nothing here
  measures whether you hit it.
- **It does not hold the assignments you have not told it about.** The 48-week
  plan is the skeleton. What gets marked arrives during the programme, and
  reaches the system only through `fellowship assign`.
- **Reading links are not all verified.** Where an arXiv id was not certain the
  link is an arXiv search for the title, rather than a guessed id that 404s.
  Four entries are search links: Holistic Agent Leaderboard, From Surveillance
  to Signalling, Permission-Aware RAG, and the week 18 Path A repeat.
