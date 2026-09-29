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
