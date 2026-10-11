"""Phase 2 answer verification: blind solver batches in, verified answer statuses out.

  python -m pipeline.solve prepare  --paper 2024-09-09_0900
      writes data/solver/work/<paper>/<SECTION>/batch.json plus copies of the blind crops. A batch holds only
      what a solver may see: question id, stem text, stem image, and the four options. No key, no marker.
  (solver agents write data/solver/runs/<paper>/<SECTION>/<solver_id>.jsonl, see pipeline/prompts/solver_v1.md)
  python -m pipeline.solve aggregate --paper 2024-09-09_0900
      validates each solver output, runs its check code in a subprocess with a timeout, compares solvers with
      each other and with the sheet's key, and writes data/solver/verifications/<paper>.jsonl and
      data/solver/summary/<paper>.md.
  python -m pipeline.solve report
      rolls every paper up into data/solver/SUMMARY.md and data/solver/review_queue.json (everything not
      confirmed: disputed keys, split solvers, missing answers, extraction flags). Reviewed decisions in
      data/review/decisions.jsonl turn a queued question into KEY_CONFIRMED_REVIEW (approve or edit) or
      REJECTED, and it also writes data/solver/final_answers.jsonl (the answer each question publishes with).
  python -m pipeline.solve import-review <dir>
      reads the review page's exported decision documents (one JSON file each) into data/review/decisions.jsonl.

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
    runs: dict[str, dict[str, dict]] = defaultdict(dict)
    # "<solver>.jsonl" plus re-run files "<solver>.<tag>.jsonl"; a re-run replaces that solver's earlier answer
    for f in sorted((root / "data" / "solver" / "runs" / paper / section).glob("*.jsonl"),
                    key=lambda f: (f.name.count("."), f.name)):
        recs = runs[f.name.split(".")[0]]
        for line in f.read_text().splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                recs[r.get("question_id")] = r
    return {solver: list(recs.values()) for solver, recs in runs.items()}


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


REVIEW_STATUSES = ("KEY_DISPUTED", "SOLVERS_DISAGREE", "UNRESOLVED", "NEEDS_SOLVER", "NO_KEY", "EXTRACTION_REVIEW")
CONFIRMED = ("KEY_CONFIRMED_CODE", "KEY_CONFIRMED_DUAL", "KEY_CONFIRMED_REVIEW")
DECISION_ACTIONS = {"approve", "edit", "reject"}


def load_questions_all(root: Path) -> dict[tuple[str, str], dict]:
    path = root / "data" / "questions" / "questions.jsonl"
    return {(q["paper_id"], solver_id_for(q)): q for q in map(json.loads, path.read_text().splitlines())}


def import_review(root: Path, src: Path) -> list[dict]:
    """Normalise the review page's decision documents into data/review/decisions.jsonl.

    Each decision is pinned to the question_version it was made on, so a later re-extraction of that
    question puts it back in the queue instead of silently reusing the decision. Reviewer ids are not kept.
    """
    questions = load_questions_all(root)
    out = []
    for f in sorted(src.glob("*.json")):
        d = json.loads(f.read_text())
        q = questions.get((d["paper"], d["question_id"]))
        if q is None:
            raise ValueError(f"{f.name}: no question {d['paper']} {d['question_id']}")
        if d["action"] not in DECISION_ACTIONS:
            raise ValueError(f"{f.name}: unknown action {d['action']!r}")
        if d["action"] != "reject" and d.get("answer") not in tuple(LETTERS):
            raise ValueError(f"{f.name}: answer {d.get('answer')!r} not A-D")
        if d["action"] == "approve" and d["answer"] != q["official_answer"]:
            raise ValueError(f"{f.name}: approve must keep the key {q['official_answer']}")
        out.append({"paper_id": d["paper"], "section": q["section"], "q_no": q["q_no"],
                     "question_id": d["question_id"], "question_version": question_version(q),
                     "official_answer": q["official_answer"], "status_before": d.get("status_before"),
                     "action": d["action"], "answer": d.get("answer") if d["action"] != "reject" else None,
                     "note": d.get("note") or "", "decided_at": d.get("decided_at")})
    out.sort(key=lambda r: (r["paper_id"], r["section"], r["q_no"]))
    dst = root / "data" / "review" / "decisions.jsonl"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    return out


def load_decisions(root: Path) -> dict[tuple[str, str], dict]:
    path = root / "data" / "review" / "decisions.jsonl"
    if not path.exists():
        return {}
    return {(d["paper_id"], d["question_id"]): d for d in map(json.loads, path.read_text().splitlines())}


def report(root: Path) -> dict:
    """Roll up every paper's verification file into data/solver/SUMMARY.md, data/solver/review_queue.json and
    data/solver/final_answers.jsonl, applying reviewed decisions to queued questions."""
    questions = load_questions_all(root)
    decisions = load_decisions(root)
    rows = []
    for f in sorted((root / "data" / "solver" / "verifications").glob("*.jsonl")):
        rows += [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    for r in rows:
        r["final_answer"] = r["official_answer"] if r["status"] in CONFIRMED else None
        d = decisions.get((r["paper_id"], r["question_id"]))
        if r["status"] not in REVIEW_STATUSES or d is None:
            continue
        if d["question_version"] != question_version(questions[(r["paper_id"], r["question_id"])]):
            continue  # the question changed after review: it goes back in the queue
        r["review"] = d
        r["status"] = "REJECTED" if d["action"] == "reject" else "KEY_CONFIRMED_REVIEW"
        r["final_answer"] = d["answer"]
    cols = ["parsed", *CONFIRMED, *REVIEW_STATUSES, "REJECTED"]
    per_paper: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in rows:
        per_paper[(r["paper_id"], r["section"])][r["status"]] += 1
        per_paper[(r["paper_id"], r["section"])]["parsed"] += 1
    total = sum(per_paper.values(), Counter())

    def published(c: Counter) -> bool:
        return c["parsed"] == 25 and sum(c[s] for s in CONFIRMED) == 25

    n_published = sum(published(c) for c in per_paper.values())

    def first_two(r: dict) -> tuple[str | None, str | None]:
        # the two primary solvers (A and B); a third solver only runs where these two split
        a = next((v for k, v in r["solver_answers"].items() if k.endswith("-a")), None)
        b = next((v for k, v in r["solver_answers"].items() if k.split("-")[1:2] == ["b"]), None)
        return a, b

    pairs = [first_two(r) for r in rows]
    both = [(a, b, r) for (a, b), r in zip(pairs, rows) if a and b]
    agree = [(a, r) for a, b, r in both if a == b]
    edited = [r for r in rows if r.get("review", {}).get("action") == "edit"]
    lines = ["# Answer verification: all papers", "", "Generated by `python -m pipeline.solve report`.", "",
             f"- Questions: {len(rows)}; confirmed: {sum(total[s] for s in CONFIRMED)} "
             f"({total['KEY_CONFIRMED_CODE']} by check code, {total['KEY_CONFIRMED_DUAL']} by two solvers, "
             f"{total['KEY_CONFIRMED_REVIEW']} by review, of which {len(edited)} with a corrected key); "
             f"rejected: {total['REJECTED']}; to review: {sum(total[s] for s in REVIEW_STATUSES)}",
             f"- Section mocks published (all 25 confirmed): {n_published}/{len(per_paper)}",
             f"- Solvers A and B agreed on {len(agree)}/{len(both)} questions; where they agreed, "
             f"the sheet's key matched {sum(a == r['official_answer'] for a, r in agree)}/{len(agree)}", "",
             "| Paper | Section | " + " | ".join(c.replace("KEY_", "").replace("_", " ").lower() for c in cols)
             + " | published |",
             "|---" * (len(cols) + 3) + "|"]
    for paper, section in sorted(per_paper):
        c = per_paper[(paper, section)]
        lines.append(f"| {paper} | {section} | " + " | ".join(str(c[k]) for k in cols)
                     + f" | {'yes' if published(c) else 'no'} |")
    lines.append("| **total** | | " + " | ".join(f"**{total[c]}**" for c in cols) + f" | **{n_published}** |")
    queue = []
    for r in rows:
        if r["status"] not in REVIEW_STATUSES:
            continue
        q = questions[(r["paper_id"], r["question_id"])]
        queue.append({"paper_id": r["paper_id"], "section": r["section"], "q_no": r["q_no"],
                      "question_id": r["question_id"], "status": r["status"], "official_answer": r["official_answer"],
                      "solver_answers": r["solver_answers"], "extraction_review_reasons": q["review_reasons"],
                      "question_crop": q["question_crop"]})
    reviewed = [r for r in rows if "review" in r]
    lines += ["", "## Decided in review", ""]
    lines += [f"- {r['paper_id']} {r['section']} Q{r['q_no']} ({r['question_id']}): {r['review']['status_before']}, "
              f"key {r['official_answer']}, solvers {r['solver_answers']} -> {r['review']['action']}"
              + (f" {r['final_answer']}" if r["final_answer"] else "") for r in reviewed] or ["- none"]
    lines += ["", "## Review queue", ""]
    lines += [f"- {x['paper_id']} {x['section']} Q{x['q_no']} ({x['question_id']}): {x['status']}; "
              f"key {x['official_answer']}, solvers {x['solver_answers']}" for x in queue] or ["- none"]
    (root / "data" / "solver" / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    (root / "data" / "solver" / "review_queue.json").write_text(json.dumps(queue, indent=1, ensure_ascii=False) + "\n")
    (root / "data" / "solver" / "final_answers.jsonl").write_text("".join(
        json.dumps({"paper_id": r["paper_id"], "section": r["section"], "q_no": r["q_no"],
                    "question_id": r["question_id"], "official_answer": r["official_answer"],
                    "final_answer": r["final_answer"], "status": r["status"]}) + "\n" for r in rows))
    return {"total": total, "queue": queue, "agree": len(agree), "both": len(both), "published": n_published}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["prepare", "aggregate", "report", "import-review"])
    ap.add_argument("src", nargs="?", type=Path, help="import-review: directory of exported decision JSON files")
    ap.add_argument("--paper", help="paper_id, e.g. 2024-09-09_0900 (prepare and aggregate)")
    ap.add_argument("--repo-root", type=Path, default=ROOT)
    args = ap.parse_args()
    if args.command == "report":
        res = report(args.repo_root)
        print(dict(res["total"]), f"A/B agree {res['agree']}/{res['both']}", f"review {len(res['queue'])}",
              f"published {res['published']}")
        return
    if args.command == "import-review":
        if not args.src:
            ap.error("import-review needs the directory of decision files")
        decisions = import_review(args.repo_root, args.src)
        print(Counter(d["action"] for d in decisions))
        return
    if not args.paper:
        ap.error("--paper is required for prepare and aggregate")
    if args.command == "prepare":
        for b in prepare(args.repo_root, args.paper):
            print(b.relative_to(args.repo_root))
    else:
        res = aggregate(args.repo_root, args.paper)
        for sec, c in res["summary"].items():
            print(sec, dict(c))


if __name__ == "__main__":
    main()
