"""Phase 2 answer verification: blind solver batches in, verified answer statuses out.

  python -m pipeline.solve prepare  --paper 2024-09-09_0900
      writes data/solver/work/<paper>/<SECTION>/batch.json plus copies of the blind crops. A batch holds only
      what a solver may see: question id, stem text, stem image, and the four options. No key, no marker.
  (solver agents write data/solver/runs/<paper>/<SECTION>/<solver_id>.jsonl, see pipeline/prompts/solver_v1.md)
  python -m pipeline.solve aggregate --paper 2024-09-09_0900
      validates each solver output, runs its check code in a subprocess with a timeout, compares solvers with
      each other and with the sheet's key, and writes data/solver/verifications/<paper>.jsonl and
      data/solver/summary/<paper>.md.

The aggregator is plain code. It never changes a solver's answer and never looks at a solution to fit the key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ("QUANT", "REASONING")
LETTERS = "ABCD"
CHECK_TIMEOUT_S = 10
OUTPUT_KEYS = {"question_id", "solver_id", "model", "prompt_version", "answer_option", "answer_value", "method",
               "steps", "check_code", "confidence"}


def load_questions(root: Path, paper: str) -> list[dict]:
    path = root / "data" / "questions" / "questions.jsonl"
    return [q for q in map(json.loads, path.read_text().splitlines()) if q["paper_id"] == paper]


def question_version(q: dict) -> str:
    """Hash of what a solver sees; a changed stem or option makes earlier solver runs stale."""
    payload = json.dumps([q["ssc_question_id"], q["stem_text"], q["stem_image"],
                          [[o["text"], o["image"]] for o in q["options"]]], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def solver_id_for(q: dict) -> str:
    return q["ssc_question_id"] or f"{q['paper_id']}_{q['section']}_{q['q_no']:02d}"


def prepare(root: Path, paper: str) -> list[Path]:
    batches = []
    for section in SECTIONS:
        work = root / "data" / "solver" / "work" / paper / section
        if work.exists():
            shutil.rmtree(work)
        (work / "images").mkdir(parents=True)
        items = []
        for q in (q for q in load_questions(root, paper) if q["section"] == section):
            def blind(path: str | None) -> str | None:
                if not path:
                    return None
                src = root / path
                dst = work / "images" / f"{solver_id_for(q)}_{Path(path).name.split('_', 1)[-1]}"
                shutil.copyfile(src, dst)
                return str(dst.relative_to(root))
            items.append({
                "question_id": solver_id_for(q),
                "question_version": question_version(q),
                "stem_text": q["stem_text"],
                "stem_text_complete": q["stem_text_complete"],
                "stem_image": blind(q["stem_image"]),
                "options": [{"option": o["label"], "text": o["text"], "image": blind(o["image"])}
                            for o in q["options"]],
            })
        batch = work / "batch.json"
        batch.write_text(json.dumps({"paper": paper, "section": section, "questions": items},
                                    indent=1, ensure_ascii=False) + "\n")
        batches.append(batch)
    return batches


def validate(rec: dict, expected_ids: set[str]) -> list[str]:
    errs = []
    if set(rec) != OUTPUT_KEYS:
        errs.append(f"keys {sorted(set(rec) ^ OUTPUT_KEYS)} missing or extra")
    if rec.get("question_id") not in expected_ids:
        errs.append("unknown question_id")
    if rec.get("answer_option") not in tuple(LETTERS):
        errs.append("answer_option not A-D")
    if not isinstance(rec.get("steps"), list):
        errs.append("steps not a list")
    c = rec.get("confidence")
    if not isinstance(c, (int, float)) or not 0 <= c <= 1:
        errs.append("confidence not in 0..1")
    if rec.get("check_code") is not None and not isinstance(rec.get("check_code"), str):
        errs.append("check_code not a string or null")
    return errs


def run_check(code: str | None) -> tuple[bool | None, str]:
    """Run check code in a fresh interpreter, empty temp dir, stripped environment and a timeout."""
    if not code:
        return None, "no check code"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "check.py"
        path.write_text(code)
        try:
            res = subprocess.run([sys.executable, "-I", str(path)], cwd=tmp, capture_output=True, text=True,
                                 timeout=CHECK_TIMEOUT_S, env={"PATH": os.environ.get("PATH", "")})
        except subprocess.TimeoutExpired:
            return False, "timeout"
    if res.returncode == 0:
        return True, ""
    return False, (res.stderr.strip().splitlines() or ["exit " + str(res.returncode)])[-1][:300]


def read_runs(root: Path, paper: str, section: str) -> dict[str, list[dict]]:
    """solver_id -> records; later lines for the same question replace earlier ones (re-runs)."""
    runs: dict[str, list[dict]] = {}
    for f in sorted((root / "data" / "solver" / "runs" / paper / section).glob("*.jsonl")):
        recs = {}
        for line in f.read_text().splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                recs[r.get("question_id")] = r
        runs[f.stem] = list(recs.values())
    return runs


def decide(key: str | None, section: str, verdicts: list[dict]) -> str:
    valid = [v for v in verdicts if v["valid"]]
    answers = Counter(v["solver_answer"] for v in valid)
    if len(valid) < 2:
        return "NEEDS_SOLVER"
    top, n = answers.most_common(1)[0]
    if n < 2 or (len(answers) > 1 and answers.most_common(2)[1][1] == n):
        return "SOLVERS_DISAGREE" if len(valid) < 3 else "UNRESOLVED"
    if key is None:
        return "NO_KEY"
    if top != key:
        return "KEY_DISPUTED"
    agreeing = [v for v in valid if v["solver_answer"] == top]
    if section == "QUANT" and any(v["check_passed"] for v in agreeing):
        return "KEY_CONFIRMED_CODE"
    return "KEY_CONFIRMED_DUAL"


def aggregate(root: Path, paper: str) -> dict:
    questions = {solver_id_for(q): q for q in load_questions(root, paper)}
    rows, summary = [], defaultdict(Counter)
    for section in SECTIONS:
        ids = {k for k, q in questions.items() if q["section"] == section}
        runs = read_runs(root, paper, section)
        by_q: dict[str, list[dict]] = defaultdict(list)
        for solver, recs in runs.items():
            for r in recs:
                errs = validate(r, ids)
                passed, note = run_check(r.get("check_code")) if not errs else (None, "invalid output")
                qid = r.get("question_id")
                opt = r.get("answer_option")
                q = questions.get(qid)
                by_q[qid].append({
                    "question_id": qid,
                    "question_version": question_version(q) if q else None,
                    "solver_id": solver,
                    "model": r.get("model"),
                    "prompt_version": r.get("prompt_version"),
                    "method": r.get("method"),
                    "solver_answer": opt,
                    "matches_key": q is not None and opt == q["official_answer"],
                    "check_code": r.get("check_code"),
                    "check_passed": passed,
                    "check_note": note,
                    "confidence": r.get("confidence"),
                    "steps": r.get("steps"),
                    "valid": not errs,
                    "errors": errs,
                })
        for qid in sorted(ids, key=lambda k: questions[k]["q_no"]):
            q = questions[qid]
            verdicts = by_q.get(qid, [])
            status = decide(q["official_answer"], section, verdicts)
            if q["status"] == "REVIEW" and status.startswith("KEY_CONFIRMED"):
                status = "EXTRACTION_REVIEW"  # a solver verdict never clears an extraction flag
            rows.append({"paper_id": paper, "section": section, "q_no": q["q_no"], "question_id": qid,
                         "official_answer": q["official_answer"], "status": status,
                         "solver_answers": {v["solver_id"]: v["solver_answer"] for v in verdicts},
                         "verifications": verdicts})
            summary[section][status] += 1
            summary[section]["parsed"] += 1
    out = root / "data" / "solver" / "verifications" / f"{paper}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    md = root / "data" / "solver" / "summary" / f"{paper}.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_summary(paper, rows, summary))
    return {"rows": rows, "summary": summary}


def render_summary(paper: str, rows: list[dict], summary: dict) -> str:
    cols = ["parsed", "KEY_CONFIRMED_CODE", "KEY_CONFIRMED_DUAL", "KEY_DISPUTED", "SOLVERS_DISAGREE",
            "UNRESOLVED", "NEEDS_SOLVER", "NO_KEY", "EXTRACTION_REVIEW"]
    lines = [f"# Answer verification: {paper}", "", "Generated by `python -m pipeline.solve aggregate`.", "",
             "| Section | " + " | ".join(c.replace("KEY_", "").replace("_", " ").lower() for c in cols) + " |",
             "|---" * (len(cols) + 1) + "|"]
    for sec in SECTIONS:
        lines.append(f"| {sec} | " + " | ".join(str(summary[sec][c]) for c in cols) + " |")
    lines += ["", "## Solver agreement", ""]
    for sec in SECTIONS:
        rs = [r for r in rows if r["section"] == sec]
        solvers = sorted({s for r in rs for s in r["solver_answers"]})
        for s in solvers:
            vs = [v for r in rs for v in r["verifications"] if v["solver_id"] == s]
            valid = [v for v in vs if v["valid"]]
            checks = [v for v in valid if v["check_passed"] is not None]
            lines.append(
                f"- {sec} `{s}` ({valid[0]['model'] if valid else '?'}): {len(valid)}/{len(vs)} valid, "
                f"{sum(v['matches_key'] for v in valid)} match the key, "
                f"check code passed {sum(bool(v['check_passed']) for v in checks)}/{len(checks)}")
    flagged = [r for r in rows if not r["status"].startswith("KEY_CONFIRMED")]
    lines += ["", "## Not confirmed", ""]
    lines += [f"- {r['section']} Q{r['q_no']} ({r['question_id']}): {r['status']}; key {r['official_answer']}, "
              f"solvers {r['solver_answers']}" for r in flagged] or ["- none"]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["prepare", "aggregate"])
    ap.add_argument("--paper", required=True, help="paper_id, e.g. 2024-09-09_0900")
    ap.add_argument("--repo-root", type=Path, default=ROOT)
    args = ap.parse_args()
    if args.command == "prepare":
        for b in prepare(args.repo_root, args.paper):
            print(b.relative_to(args.repo_root))
    else:
        res = aggregate(args.repo_root, args.paper)
        for sec, c in res["summary"].items():
            print(sec, dict(c))


if __name__ == "__main__":
    main()
