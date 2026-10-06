"""Phase 3d: shortcut-first solutions.

  python -m pipeline.solutions prepare <paper> <out_dir>   writer batches for a paper (verified answers only)
  python -m pipeline.solutions merge <dir>                 writer outputs (sol_*.jsonl) -> data/solutions/<paper>.jsonl
  python -m pipeline.solutions verify [--paper P]          crispness lint + check code; stores the status
  python -m pipeline.solutions lint [--paper P]            the lint alone (part of `make verify`)
  python -m pipeline.solutions check-file <sol.jsonl>      lint + check code on a writer's file, writes nothing

Writers (pipeline/prompts/solution_v1.md) only see questions whose answer is confirmed, with the verified
answer and a verified solver's steps. Each solution carries check code that recomputes the answer the fastest
way and prints `ANSWER=<letter>`. A solution is VERIFIED_CODE when it passes the lint and its code prints the
verified answer; otherwise it is PENDING, and the app shows the answer with "Solution pending".
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pipeline.library import load_entries, run_code
from pipeline.solve import CONFIRMED, LETTERS, load_questions, question_version
from pipeline.tags import load_tags

ROOT = Path(__file__).resolve().parents[1]
PROMPT_VERSION = "solution_v1"
SOLUTION_KEYS = {"key", "question_version", "answer", "answer_value", "trick", "fastest", "elimination",
                 "elimination_is_fastest", "trap", "diagram", "full", "formula_ids", "check_code", "writer",
                 "prompt_version"}
MAX_STEPS = 4
MAX_WORDS = 60
BANNED = ("let us", "let's", "we know that", "therefore we can say", "hence proved", "it is given that",
          "according to the question")
TOKEN_RE = re.compile(r"\[\[f:([^\]]+)\]\]")
MATH_RE = re.compile(r"\$[^$]*\$")
# A solution diagram is required for these topics and never drawn for pure arithmetic.
DIAGRAM_REQUIRED = {"Geometry", "Mensuration", "Blood Relations", "Syllogism", "Venn", "Dice/Cube"}
DIAGRAM_REQUIRED_SUBTOPICS = {"Heights & distances"}
NO_DIAGRAM = {"Number System", "Simplification", "Percentage", "Profit & Loss", "Average", "SI/CI",
              "Ratio & Proportion", "Mixture & Alligation", "Time & Work"}
# Figure-based reasoning keeps the original crop, with overlays only.
CROP_TOPICS = {"Figure-based", "Counting Figures"}
DIAGRAM_TYPES = {"geometry", "solid", "area-model", "bar-model", "alligation-cross", "number-line", "chart", "venn",
                 "family-tree", "direction-grid", "seating", "dice-net", "fold-steps", "mirror-axis", "table",
                 "crop-overlay"}


def solutions_dir(root: Path) -> Path:
    return root / "data" / "solutions"


def key_of(q: dict) -> str:
    return f"{q['paper_id']}_{q['section'][0]}{q['q_no']:02d}"


def final_rows(root: Path) -> dict[str, dict]:
    path = root / "data" / "solver" / "final_answers.jsonl"
    return {f"{r['paper_id']}_{r['section'][0]}{r['q_no']:02d}": r
            for r in map(json.loads, path.read_text().splitlines())}


def best_steps(root: Path, q: dict, answer: str) -> list[str]:
    """Steps of a valid solver run that reached the verified answer on this version."""
    path = root / "data" / "solver" / "verifications" / f"{q['paper_id']}.jsonl"
    for rec in map(json.loads, path.read_text().splitlines()):
        if (rec["section"], rec["q_no"]) == (q["section"], q["q_no"]):
            runs = [v for v in rec["verifications"] if v.get("valid", True) and v["solver_answer"] == answer
                    and v["question_version"] == question_version(q) and v.get("steps")]
            runs.sort(key=lambda v: (not v.get("check_passed"), -(v.get("confidence") or 0)))
            return runs[0]["steps"] if runs else []
    return []


def prepare(root: Path, paper: str, out_dir: Path, per_batch: int = 10) -> list[Path]:
    """Writer batches: only questions with a confirmed answer, never a rejected one."""
    finals, tags, entries = final_rows(root), load_tags(root), load_entries(root)
    items = []
    for q in load_questions(root, paper):
        k = key_of(q)
        f = finals.get(k)
        if f is None or f["status"] not in CONFIRMED:
            continue
        t = tags[k]
        ids = list(dict.fromkeys(t["formula_ids"] + [i for i, e in entries.items() if e["topic"] == t["topic"]]))
        items.append({
            "key": k, "question_version": question_version(q), "section": q["section"],
            "stem": q["stem_text"], "stem_text_complete": q["stem_text_complete"],
            "options": {o["label"]: o["text"] for o in q["options"]},
            "option_images": {o["label"]: o["image"] for o in q["options"] if o["image"]},
            "crop": q["question_crop"], "stem_image": q["stem_image"],
            "answer": f["final_answer"], "verified_steps": best_steps(root, q, f["final_answer"]),
            "tags": {x: t[x] for x in ("topic", "subtopic", "question_type", "formula_ids", "shortcut_used")},
            "diagram_rule": diagram_rule(t),
            "library": [{"id": i, "name": entries[i]["name"], "statement": entries[i]["statement"],
                         "shortcut": entries[i]["shortcut"]} for i in ids if i in entries],
        })
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for n in range(0, len(items), per_batch):
        p = out_dir / f"in_{paper}_{n // per_batch}.json"
        p.write_text(json.dumps(items[n:n + per_batch], indent=1, ensure_ascii=False) + "\n")
        paths.append(p)
    return paths


def diagram_rule(tag: dict) -> str:
    """crop-overlay (figure questions), required, none (pure arithmetic) or optional."""
    if tag["topic"] in CROP_TOPICS:
        return "crop-overlay"
    if tag["topic"] in DIAGRAM_REQUIRED or tag["subtopic"] in DIAGRAM_REQUIRED_SUBTOPICS:
        return "required"
    return "none" if tag["topic"] in NO_DIAGRAM else "optional"


def words(text: str) -> int:
    """Words outside math and formula tokens."""
    return len(TOKEN_RE.sub(" ", MATH_RE.sub(" ", text)).split())


def shingles(text: str, n: int = 8) -> set[tuple[str, ...]]:
    w = re.findall(r"[a-z0-9]+", MATH_RE.sub(" ", text).lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def lint(sol: dict, q: dict, tag: dict, answer: str, entries: dict[str, dict]) -> list[str]:
    """The crispness lint. Every message is a reason to rewrite the solution."""
    errs = []
    keys = set(sol)
    if keys != SOLUTION_KEYS:
        return [f"fields {sorted(keys ^ SOLUTION_KEYS)} missing or extra"]
    if sol["question_version"] != question_version(q):
        errs.append("written for an older version of the question")
    if sol["answer"] != answer:
        errs.append(f"answer {sol['answer']} is not the verified answer {answer}")
    if not (sol["trick"] or "").strip():
        errs.append("the fastest way has no named trick")
    steps = sol["elimination"] if sol["elimination_is_fastest"] else sol["fastest"]
    if not isinstance(sol["fastest"], list) or not sol["fastest"]:
        errs.append("fastest way has no steps")
    for name, block in (("fastest way", sol["fastest"]), ("elimination", sol["elimination"] or [])):
        if len(block) > MAX_STEPS:
            errs.append(f"{name} has {len(block)} steps (max {MAX_STEPS})")
        if any("\n" in s for s in block):
            errs.append(f"{name} has a step longer than one line")
        if sum(words(s) for s in block) > MAX_WORDS:
            errs.append(f"{name} has {sum(words(s) for s in block)} words outside math (max {MAX_WORDS})")
    if sol["elimination_is_fastest"] and not sol["elimination"]:
        errs.append("elimination marked fastest but empty")
    if not any(TOKEN_RE.search(s) for s in (steps or [])):
        errs.append("the fastest way links no formula or method ([[f:<id>]])")
    text_blocks = (sol["fastest"] + (sol["elimination"] or []) + [sol["trap"]] + sol["full"]
                   + [sol["answer_value"] or ""])
    text = "\n".join(text_blocks)
    for tok in TOKEN_RE.findall(text):
        if tok not in entries:
            errs.append(f"unresolved token [[f:{tok}]]")
    unlinked = TOKEN_RE.sub(" ", text).lower()
    for i, e in entries.items():
        if len(e["name"].split()) >= 2 and e["name"].lower() in unlinked:
            errs.append(f"mentions {e['name']!r} without its token [[f:{i}]]")
    low = text.lower()
    errs += [f"banned phrase {b!r}" for b in BANNED if re.search(rf"\b{re.escape(b)}\b", low)]
    if shingles(q["stem_text"]) & shingles("\n".join(sol["fastest"])):
        errs.append("the fastest way restates the question")
    if not sol["trap"].strip() or "\n" in sol["trap"]:
        errs.append("trap must be one line")
    elif not re.search(r"\(([a-d])\)", sol["trap"]):
        errs.append("trap must name the wrong option it leads to, e.g. (b)")
    if not sol["full"]:
        errs.append("full method is empty")
    d = sol["diagram"]
    rule = diagram_rule(tag)
    if d is None and rule in ("required", "crop-overlay"):
        errs.append(f"{tag['topic']} needs a diagram")
    if d is not None:
        if rule == "none":
            errs.append("no diagram for pure arithmetic")
        if d.get("spec", {}).get("type") not in DIAGRAM_TYPES:
            errs.append(f"unknown diagram type {d.get('spec', {}).get('type')}")
        elif rule == "crop-overlay" and d["spec"]["type"] != "crop-overlay":
            errs.append("figure questions keep the original crop with overlays only")
        if not (d.get("alt_text") or "").strip():
            errs.append("diagram has no alt text")
    if not (sol["check_code"] or "").strip():
        errs.append("no check code")
    return errs


def check(sol: dict, answer: str) -> tuple[bool, str]:
    passed, note, stdout = run_code(sol["check_code"] or "")
    got = re.findall(r"ANSWER=([A-D])", stdout)
    if not passed:
        return False, note
    if got != [answer]:
        return False, f"check code printed {got or 'no ANSWER='}, expected [{answer!r}]"
    return True, ""


def load_solutions(root: Path, paper: str | None = None) -> dict[str, list[dict]]:
    out = {}
    for f in sorted(solutions_dir(root).glob("*.jsonl")):
        if paper is None or f.stem == paper:
            out[f.stem] = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    return out


def merge(root: Path, src: Path) -> dict[str, int]:
    """sol_*.jsonl writer outputs, later files win (a rewrite overrides), grouped per paper."""
    by_key = {}
    for f in sorted(src.glob("sol_*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                s = json.loads(line)
                by_key[s["key"]] = s
    papers: dict[str, list[dict]] = {}
    for k in sorted(by_key):
        papers.setdefault(k.rsplit("_", 1)[0], []).append(by_key[k])
    out = solutions_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    for paper, sols in papers.items():
        old = {s["key"]: s for s in load_solutions(root, paper).get(paper, [])}
        for s in sols:  # keep a stored verification only while the solution is unchanged
            prev = old.get(s["key"])
            if prev and {k: prev.get(k) for k in SOLUTION_KEYS} == {k: s.get(k) for k in SOLUTION_KEYS}:
                s["verification"] = prev.get("verification")
        (out / f"{paper}.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in sols))
    return {p: len(s) for p, s in papers.items()}


def verify(root: Path, paper: str | None = None, run_checks: bool = True) -> dict[str, dict]:
    finals, tags, entries = final_rows(root), load_tags(root), load_entries(root)
    results = {}
    for p, sols in load_solutions(root, paper).items():
        questions = {key_of(q): q for q in load_questions(root, p)}
        for s in sols:
            k = s["key"]
            f = finals[k]
            errs = lint({x: s.get(x) for x in SOLUTION_KEYS if x in s}, questions[k], tags[k], f["final_answer"],
                        entries)
            if f["status"] not in CONFIRMED:
                errs.append(f"answer is {f['status']}, not confirmed")
            ok, note = check(s, f["final_answer"]) if run_checks and not errs else (False, "")
            if run_checks and not errs and not ok:
                errs.append(f"check code: {note}")
            results[k] = {"status": "VERIFIED_CODE" if not errs else "PENDING", "errors": errs,
                          "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            if run_checks:
                s["verification"] = results[k]
        if run_checks:
            (solutions_dir(root) / f"{p}.jsonl").write_text(
                "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in sols))
    return results


def check_file(root: Path, path: Path) -> dict[str, list[str]]:
    finals, tags, entries = final_rows(root), load_tags(root), load_entries(root)
    out = {}
    for s in (json.loads(line) for line in path.read_text().splitlines() if line.strip()):
        k = s.get("key", "?")
        if k not in finals:
            out[k] = ["unknown question key"]
            continue
        q = next(q for q in load_questions(root, k.rsplit("_", 1)[0]) if key_of(q) == k)
        errs = lint(s, q, tags[k], finals[k]["final_answer"], entries)
        if not errs:
            ok, note = check(s, finals[k]["final_answer"])
            errs = [] if ok else [f"check code: {note}"]
        out[k] = errs
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["prepare", "merge", "verify", "lint", "check-file"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--paper")
    ap.add_argument("--repo-root", type=Path, default=ROOT)
    a = ap.parse_args()
    if a.command == "prepare":
        for p in prepare(a.repo_root, a.args[0], Path(a.args[1])):
            print(p)
        return
    if a.command == "merge":
        print(merge(a.repo_root, Path(a.args[0])))
        return
    if a.command == "check-file":
        bad = {k: e for k, e in check_file(a.repo_root, Path(a.args[0])).items() if e}
        for k, e in bad.items():
            print(f"{k}: " + "; ".join(e))
        print(f"{len(bad)} solutions with problems")
        raise SystemExit(1 if bad else 0)
    res = verify(a.repo_root, a.paper, run_checks=a.command == "verify")
    for k, r in sorted(res.items()):
        if r["errors"]:
            print(f"{k}: " + "; ".join(r["errors"]))
    print(dict(Counter(r["status"] for r in res.values())))
    raise SystemExit(1 if a.command == "lint" and any(r["errors"] for r in res.values()) else 0)


if __name__ == "__main__":
    main()
