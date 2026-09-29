# SSC CGL Tier-1 Quant + Reasoning practice platform

Built in phases from the 2024 SSC CGL Tier-I response sheets in the repo root.

## Phase 1: Intake

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pipeline.intake   # validates sheets, copies accepted ones, writes SOURCES.md and MISSING.md
.venv/bin/python -m pytest
```

Accepted files are copied unmodified to `data/raw/2024/<dd.mm.yyyy>_<HHMM>/`. Re-running changes nothing unless a source file's hash changed.
