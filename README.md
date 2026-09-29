# SSC CGL Tier-1 Quant + Reasoning practice platform

Built in phases from the 2024 SSC CGL Tier-I response sheets in the repo root.

## Phase 1: Intake

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pipeline.intake   # validates sheets, copies accepted ones, writes SOURCES.md and MISSING.md
.venv/bin/python -m pytest
```

Accepted files are copied unmodified to `data/raw/2024/<dd.mm.yyyy>_<HHMM>/`. Re-running changes nothing unless a source file's hash changed.

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
