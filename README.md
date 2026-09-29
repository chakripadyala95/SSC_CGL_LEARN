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
