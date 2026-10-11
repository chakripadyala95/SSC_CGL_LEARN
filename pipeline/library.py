"""Phase 3b: the formula and method library.

  python -m pipeline.library check      validates every entry in data/library/<section>/<topic-slug>.json
  python -m pipeline.library verify     runs each entry's verification code and stores the result on the entry
  python -m pipeline.library render     writes the printable cheat sheets to docs/cheatsheets/<topic-slug>.md

Entries are written by writer agents (pipeline/prompts/library_v1.md) for the IDs approved in data/taxonomy/.
Verification is plain code run in a separate interpreter, empty temp dir and a timeout (as pipeline.solve does):
- identity:   SymPy `simplify(lhs - rhs) == 0` for the entry's statement.
- shortcut:   the shortcut against the standard formula on at least 1,000 random valid inputs.
- method:     a Reasoning method applied to its worked example; it must give the answer and rule out the rest.
- manual:     cannot be machine-checked; the stated reason sends the entry to review.
Code also tests each stated condition at its boundary. Each check prints `CASES=<n>` (shortcut) and
`BOUNDARY_OK` (when the entry has conditions) so the harness can tell a real check from an empty one.
Backlinks (questions that use an entry) are computed from the tags, never stored on the entry.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import os
import subprocess
import sys
import tempfile

from pipeline.solve import CHECK_TIMEOUT_S
from pipeline.taxonomy import SECTIONS
from pipeline.taxonomy import load as load_taxonomy

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"id", "topic", "subtopic", "name", "statement", "conditions", "derivation", "visual_proof", "shortcut",
          "worked_example", "common_traps", "related_ids", "diagram", "verification"}
KINDS = {"identity", "shortcut", "method", "manual"}
# Diagrams are code, rendered client-side as SVG. Each type has a fixed shape the renderer understands.
DIAGRAM_TYPES = {
    "geometry",        # points {name: [x, y]}, segments, circles, angles, labels, to_scale
    "solid",           # shape (cube|cuboid|cylinder|cone|sphere|hemisphere|prism|pyramid|frustum), dims, labels
    "area-model",      # rows/cols of labelled rectangles for algebraic identities
    "bar-model",       # bars [{label, parts: [{value, label}]}]
    "alligation-cross",  # high, low, mean, ratio
    "number-line",     # min, max, marks, segments (relative speed, timelines)
    "chart",           # kind line|bar, series [{label, points}]
    "venn",            # sets, regions, shading/possible
    "family-tree",     # nodes [{id, label, gender}], edges [{from, to, type: parent|spouse|sibling}]
    "direction-grid",  # path [[x, y]], labels, compass
    "seating",         # layout linear|circle, seats
    "dice-net",        # net layout, faces
    "fold-steps",      # steps of a paper fold with punch marks
    "mirror-axis",     # axis vertical|horizontal over an original crop or glyphs
    "table",           # rows/cols for matrix and DI reading methods
}
ID_RE = re.compile(r"^[a-z0-9-]+\.[a-z0-9-]+$")
TOKEN_RE = re.compile(r"\[\[f:([^\]]+)\]\]")


def library_dir(root: Path, section: str) -> Path:
    return root / "data" / "library" / section


def load_entries(root: Path) -> dict[str, dict]:
    entries = {}
    for s in SECTIONS:
        for f in sorted(library_dir(root, s).glob("*.json")):
            for e in json.loads(f.read_text()):
                entries[e["id"]] = {**e, "_section": s, "_file": str(f.relative_to(root))}
    return entries


def final_answers(root: Path) -> dict[str, str]:
    """question key (<paper>_<Q|R><nn>) -> the answer each question publishes with."""
    path = root / "data" / "solver" / "final_answers.jsonl"
    return {f"{r['paper_id']}_{r['section'][0]}{r['q_no']:02d}": r["final_answer"]
            for r in map(json.loads, path.read_text().splitlines())}


def check_entry(e: dict, approved: dict[str, dict], answers: dict[str, str]) -> list[str]:
    errs = []
    fields = {k for k in e if not k.startswith("_")}
    if fields != FIELDS:
        return [f"fields {sorted(fields ^ FIELDS)} missing or extra"]
    a = approved.get(e["id"])
    if a is None:
        return ["id is not in the approved taxonomy"]
    if (e["topic"], e["subtopic"]) != (a["topic"], a["subtopic"]):
        errs.append("topic/subtopic differ from the approved taxonomy")
    if not e["statement"].strip():
        errs.append("empty statement")
    if not isinstance(e["conditions"], list):
        errs.append("conditions not a list")
    if not e["derivation"] or not all(isinstance(s, str) and s.strip() for s in e["derivation"]):
        errs.append("derivation must be a non-empty list of steps")
    if not isinstance(e["common_traps"], list) or not e["common_traps"]:
        errs.append("common_traps must list at least one trap")
    for rid in e["related_ids"]:
        if rid not in approved:
            errs.append(f"related id {rid} is not approved")
    text = json.dumps(e, ensure_ascii=False)
    for tok in TOKEN_RE.findall(text):
        if tok not in approved:
            errs.append(f"unresolved token [[f:{tok}]]")
    we = e["worked_example"]
    if we is not None:
        if set(we) != {"question_key", "answer", "steps"}:
            errs.append("worked_example needs question_key, answer, steps")
        elif we["question_key"] not in answers:
            errs.append(f"worked example {we['question_key']} is not a paper question")
        elif answers[we["question_key"]] != we["answer"]:
            errs.append(f"worked example answer {we['answer']} != verified {answers[we['question_key']]}")
    elif a["seen"]:
        errs.append("entry is used in the papers but has no worked example")
    d = e["diagram"]
    if a["visual"] and d is None:
        errs.append("taxonomy marks this entry visual but it has no diagram")
    if d is not None:
        if d.get("spec", {}).get("type") not in DIAGRAM_TYPES:
            errs.append(f"unknown diagram type {d.get('spec', {}).get('type')}")
        if not (d.get("alt_text") or "").strip():
            errs.append("diagram has no alt text")
    v = e["verification"]
    if v.get("kind") not in KINDS:
        errs.append(f"verification kind {v.get('kind')} unknown")
    elif v["kind"] == "manual":
        if not (v.get("reason") or "").strip():
            errs.append("manual verification needs a reason")
    elif not (v.get("code") or "").strip():
        errs.append("verification code missing")
    return errs


def check(root: Path) -> dict[str, list[str]]:
    approved = {e["id"]: e for s in SECTIONS for e in load_taxonomy(root, s)["entries"]}
    answers = final_answers(root)
    entries = load_entries(root)
    errs = {i: check_entry(e, approved, answers) for i, e in entries.items()}
    for i in approved.keys() - entries.keys():
        errs[i] = ["approved id has no library entry"]
    return {i: e for i, e in errs.items() if e}


def run_code(code: str) -> tuple[bool, str, str]:
    """(passed, note, stdout) for code run in a fresh isolated interpreter with a timeout."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "check.py"
        path.write_text(code + "\n")
        try:
            res = subprocess.run([sys.executable, "-I", str(path)], cwd=tmp, capture_output=True, text=True,
                                 timeout=CHECK_TIMEOUT_S, env={"PATH": os.environ.get("PATH", "")})
        except subprocess.TimeoutExpired:
            return False, "timeout", ""
    if res.returncode == 0:
        return True, "", res.stdout
    return False, (res.stderr.strip().splitlines() or ["exit " + str(res.returncode)])[-1][:300], res.stdout


def verify_entry(e: dict) -> dict:
    v = e["verification"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if v["kind"] == "manual":
        return {"status": "NEEDS_REVIEW", "note": v.get("reason"), "checked_at": now}
    passed, note, stdout = run_code(v["code"])
    cases = [int(m) for m in re.findall(r"CASES=(\d+)", stdout)]
    if passed and v["kind"] == "shortcut" and min(cases, default=0) < 1000:
        passed, note = False, f"shortcut checked on {min(cases, default=0)} inputs, need 1000"
    if passed and e["conditions"] and "BOUNDARY_OK" not in stdout:
        passed, note = False, "conditions not tested at their boundaries (no BOUNDARY_OK)"
    return {"status": "PASSED" if passed else "FAILED", "note": note, "checked_at": now}


def verify(root: Path, only: set[str] | None = None) -> dict[str, dict]:
    results = {}
    for s in SECTIONS:
        for f in sorted(library_dir(root, s).glob("*.json")):
            entries = json.loads(f.read_text())
            todo = [e for e in entries if not only or e["id"] in only]
            for e in todo:
                e["verification"]["result"] = results[e["id"]] = verify_entry(e)
            if todo:  # files are per topic; leave other topics' files alone
                f.write_text(json.dumps(entries, indent=1, ensure_ascii=False) + "\n")
    return results


def render(root: Path) -> list[Path]:
    """One printable page per topic: statement and shortcut only, each line linked to its full entry."""
    entries = load_entries(root)
    out = []
    for s in SECTIONS:
        tax = load_taxonomy(root, s)
        for t in tax["topics"]:
            es = [entries[e["id"]] for e in tax["entries"] if e["topic"] == t["topic"] and e["id"] in entries]
            if not es:
                continue
            lines = [f"# {t['topic']}: cheat sheet", ""]
            for e in es:
                slug = e["id"].split(".", 1)[1]
                lines.append(f"- [{e['name']}](/formulas/{t['slug']}#{slug}): ${e['statement']}$")
                if e["shortcut"]:
                    lines.append(f"  - Shortcut: {e['shortcut']}")
            path = root / "docs" / "cheatsheets" / f"{t['slug']}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines) + "\n")
            out.append(path)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "verify", "render"])
    ap.add_argument("--id", action="append", help="only these ids")
    ap.add_argument("--topic", action="append", help="only ids under these topic slugs")
    ap.add_argument("--repo-root", type=Path, default=ROOT)
    args = ap.parse_args()
    def wanted(i: str) -> bool:
        return (not args.id or i in args.id) and (not args.topic or i.split(".")[0] in args.topic)

    if args.command == "check":
        errs = {i: e for i, e in check(args.repo_root).items() if wanted(i)}
        for i, es in sorted(errs.items()):
            print(f"{i}: " + "; ".join(es))
        print(f"{len(errs)} entries with problems")
        raise SystemExit(1 if errs else 0)
    if args.command == "verify":
        ids = {i for i in load_entries(args.repo_root) if wanted(i)} if (args.id or args.topic) else None
        res = verify(args.repo_root, ids)
        for i, r in sorted(res.items()):
            if r["status"] != "PASSED":
                print(f"{i}: {r['status']} {r['note']}")
        from collections import Counter
        print(dict(Counter(r["status"] for r in res.values())))
        return
    for p in render(args.repo_root):
        print(p.relative_to(args.repo_root))


if __name__ == "__main__":
    main()
