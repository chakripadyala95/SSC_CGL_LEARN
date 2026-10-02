# SSC CGL Tier-1 Quant + Reasoning practice platform

Built in phases from the 2024 SSC CGL Tier-I response sheets in the repo root.

## Phase 1: Intake

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pipeline.intake   # validates sheets, copies accepted ones, writes SOURCES.md and MISSING.md
.venv/bin/python -m pytest
```

Accepted files are copied unmodified to `data/raw/2024/<dd.mm.yyyy>_<HHMM>/`. Re-running changes nothing unless a source file's hash changed.

## Phase 2: Extraction

```bash
.venv/bin/python -m pipeline.extract   # ~3 min; --no-images skips the PNGs (~1 min)
```

Writes one record per Quant and Reasoning question to `data/questions/questions.jsonl`, failed checks to
`data/questions/review_queue.json`, and per-paper counts to `COVERAGE.md`.

- The correct option is read twice, from the green option label in the text layer and from the green tick in
  the rendered page, and the two must agree. It is the sheet's key and stays `UNVERIFIED` until the solvers
  confirm it.
- Page images (200 DPI, candidate fields blanked) and crops go to `data/questions/assets/<paper_id>/`, which is
  not committed (~360 MB) and is rebuilt by the command above. `<Q|R>nn.png` is the review crop and shows the
  answer marker; `<Q|R>nn_stem.png` (stems with figures or typeset math) and `<Q|R>nn_opt<X>.png` (figure
  options) show no marker and are what blind solvers get.
- `topic`/`subtopic` are provisional keyword tags (`topic_source: "rule"`) for coverage only. Stems that are
  images stay untagged; real tagging is Phase 3.

## Phase 2: Answer verification

```bash
.venv/bin/python -m pipeline.solve prepare   --paper 2024-09-09_0900   # blind batches for the solvers
.venv/bin/python -m pipeline.solve aggregate --paper 2024-09-09_0900   # compare solvers with the key
.venv/bin/python -m pipeline.solve report                              # roll up all papers
```

- Every question is solved blind by two solvers with different methods (prompt: `pipeline/prompts/solver_v1.md`).
  Quant: A is code-first (SymPy), B is shortcut-first with check code. Reasoning: A states the rule, B
  eliminates options; figure questions get only the crops and options. Solvers never see the key, a candidate's
  answer, or each other's output. Where A and B split, a third solver (C, "test every option" / "work back from
  the options") breaks the tie.
- Solver outputs are in `data/solver/runs/<paper>/<SECTION>/<solver>.jsonl`; `<solver>.<tag>.jsonl` re-runs
  replace that solver's earlier answer. `data/solver/quarantine/` keeps outputs made on stem crops that showed
  option rows; they are not used.
- The aggregator is plain code. It runs each solver's check code in a separate interpreter with a timeout and
  marks each question `KEY_CONFIRMED_CODE` (Quant, a passing check), `KEY_CONFIRMED_DUAL` (two solvers agree
  with the key), `KEY_DISPUTED` (solvers agree on another option), or one of the review states.
- `data/solver/SUMMARY.md` has the per-paper table; `data/solver/review_queue.json` lists every question that
  is not confirmed, for human review.
- Human review: `python -m pipeline.solve import-review <dir>` reads the review page's exported decision files
  into `data/review/decisions.jsonl` (approve, edit or reject, pinned to the question version it was made on;
  reviewer ids are not kept). `report` then marks those questions `KEY_CONFIRMED_REVIEW` or `REJECTED`, and
  writes `data/solver/final_answers.jsonl`: the sheet's key next to the answer each question publishes with.
  A section mock is published once all 25 of its questions are `KEY_CONFIRMED_*`.

## App: database, API and web

PostgreSQL + FastAPI (`api/`) + Next.js (`web/`). The loader reads what the pipeline writes to `data/`:

| Input | Becomes |
| --- | --- |
| `data/intake_manifest.json` | `papers` (accepted sheets only) |
| `data/questions/questions.jsonl` | `mocks` (a QUANT and a REASONING mock per paper), `questions`, `question_versions`, `question_assets` |
| `data/questions/review_queue.json` | `review_queue` (source `extract`) |
| `data/solver/verifications/*.jsonl` | `answer_verifications`, the version's `key_status`, and `review_queue` (source `solver`) for keys not confirmed |

A question whose stem, options or key changes gets a new version; solver runs attach to the version they solved
(same hash as `pipeline.solve.question_version`). A section mock becomes `PUBLISHED` only when all 25 current
versions are `KEY_CONFIRMED_*`. Marks, negative marking and timers live in the `exam_pattern` table.

```bash
cp .env.example .env
make setup            # Python venv + web dependencies
docker compose up -d db
make load             # migrate, then load data/ (idempotent: a re-run prints "No changes.")
make api              # http://localhost:8000/docs
make web              # http://localhost:3000
make test             # needs the database for tests/test_api.py (skipped when unreachable)
```

`docker compose up -d --build` runs all three. Question crops are served from `data/questions/assets/`, which
`pipeline.extract` regenerates.

API: `/mocks`, `/mocks/{id}/questions` (published mocks only, no key, blind crops only), `/admin/mocks/{id}/questions`
and `/admin/questions/{id}` (key, both extraction reads, solver runs), `/admin/review-queue`, `/exam-pattern`, `/papers`.

## Phase 3a: Taxonomy and formula/method IDs

`data/taxonomy/quant.json` and `reasoning.json` hold the proposed topic tree and the formula/method library IDs
(`<topic-slug>.<slug>`, never changed once published). `python -m pipeline.taxonomy check` validates them and
`python -m pipeline.taxonomy render` writes `TAXONOMY.md`. `data/taxonomy/discovery/` keeps the first labelling
pass that the counts come from; these are draft tags, not the Phase 3c tags.

## Phase 3b: Formula and method library

`data/library/<section>/<topic-slug>.json` has one entry per approved ID: statement, conditions, derivation,
shortcut, a worked example from a real paper question, traps, related IDs, a diagram spec and verification
code. `python -m pipeline.library check` validates entries (approved IDs, `[[f:…]]` tokens, worked-example
answers against `data/solver/final_answers.jsonl`, diagrams with alt text). `verify` runs each entry's code in an
isolated interpreter (SymPy identities, shortcuts on 1,000+ random inputs, boundary tests, reasoning methods on
their worked example) and stores the result on the entry; `manual` entries go to review. `render` writes the
printable cheat sheets to `docs/cheatsheets/`.
