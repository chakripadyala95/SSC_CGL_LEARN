"""Phase 3c: question tags, tag QA, near-duplicates and the coverage report.

  python -m pipeline.tags merge <dir>        tagger outputs (tags_<section>_<n>.jsonl) -> data/tags/questions.jsonl
  python -m pipeline.tags sample             picks the 10% QA sample per topic -> data/tags/qa_sample.json
  python -m pipeline.tags agreement <dir>    compares a blind second tagger on the sample -> data/tags/qa.json
  python -m pipeline.tags dedupe             embeds every question and marks near-duplicates across papers
  python -m pipeline.tags coverage           writes COVERAGE_TAGS.md (the Phase 3c gate)

Tags are proposed by an LLM tagger (pipeline/prompts/tagger_v1.md). A blind second tagger re-tags a 10% sample
of every topic; a topic below 95% agreement is retagged. Two taggers agree on a question when they give the same
topic and subtopic and the second tagger's ids include the first tagger's primary id.
Near-duplicates use a local open-source embedding model (fastembed, BAAI/bge-small-en-v1.5); a question whose
text is near-identical to a question in an earlier shift, with the same subtopic, gets `duplicate_of` so
analytics count the pattern once.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from pipeline.taxonomy import SECTIONS
from pipeline.taxonomy import load as load_taxonomy

ROOT = Path(__file__).resolve().parents[1]
TAG_KEYS = {"key", "topic", "subtopic", "question_type", "formula_ids", "shortcut_used", "difficulty",
            "expected_time_sec", "has_visual", "tagger", "prompt_version"}
SAMPLE_RATE = 0.10
MIN_SAMPLE = 3
AGREEMENT_BAR = 0.95
DUP_THRESHOLD = 0.95
EMBED_MODEL = "BAAI/bge-small-en-v1.5"


def tags_path(root: Path) -> Path:
    return root / "data" / "tags" / "questions.jsonl"


def question_key(q: dict) -> str:
    return f"{q['paper_id']}_{q['section'][0]}{q['q_no']:02d}"


def load_questions(root: Path) -> dict[str, dict]:
    path = root / "data" / "questions" / "questions.jsonl"
    return {question_key(q): q for q in map(json.loads, path.read_text().splitlines())
            if q["section"] in ("QUANT", "REASONING")}


def approved(root: Path) -> tuple[set[tuple[str, str]], set[str]]:
    subs, ids = set(), set()
    for s in SECTIONS:
        tax = load_taxonomy(root, s)
        subs |= {(t["topic"], x["name"]) for t in tax["topics"] for x in t["subtopics"]}
        ids |= {e["id"] for e in tax["entries"]}
    return subs, ids


def validate(tag: dict, subs: set, ids: set) -> list[str]:
    errs = []
    if set(tag) - {"duplicate_of", "duplicate_score"} != TAG_KEYS:
        errs.append(f"keys {sorted((set(tag) - {'duplicate_of', 'duplicate_score'}) ^ TAG_KEYS)}")
        return errs
    if (tag["topic"], tag["subtopic"]) not in subs:
        errs.append(f"unknown subtopic {tag['topic']} / {tag['subtopic']}")
    if not tag["formula_ids"]:
        errs.append("no formula or method id")
    errs += [f"unknown id {i}" for i in tag["formula_ids"] if i not in ids]
    if tag["difficulty"] not in (1, 2, 3, 4, 5):
        errs.append("difficulty not 1-5")
    if not isinstance(tag["expected_time_sec"], int) or not 5 <= tag["expected_time_sec"] <= 600:
        errs.append("expected_time_sec not 5-600")
    return errs


def read_runs(src: Path, pattern: str = "tags_*.jsonl") -> dict[str, dict]:
    tags = {}
    for f in sorted(src.glob(pattern)):
        for line in f.read_text().splitlines():
            if line.strip():
                t = json.loads(line)
                tags[t["key"]] = t
    return tags


def merge(root: Path, src: Path) -> dict:
    questions = load_questions(root)
    subs, ids = approved(root)
    tags = read_runs(src)
    problems = {k: validate(t, subs, ids) for k, t in tags.items()}
    problems = {k: e for k, e in problems.items() if e}
    problems.update({k: ["not tagged"] for k in questions.keys() - tags.keys()})
    good = [tags[k] for k in sorted(questions) if k in tags and k not in problems]
    out = tags_path(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    old = {t["key"]: t for t in map(json.loads, out.read_text().splitlines())} if out.exists() else {}
    for t in good:  # keep duplicate marks from an earlier dedupe run
        for k in ("duplicate_of", "duplicate_score"):
            if k in old.get(t["key"], {}):
                t[k] = old[t["key"]][k]
    out.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in good))
    return {"tagged": len(good), "problems": problems}


def load_tags(root: Path) -> dict[str, dict]:
    return {t["key"]: t for t in map(json.loads, tags_path(root).read_text().splitlines())}


def sample(root: Path, seed: int = 0) -> dict[str, list[str]]:
    by_topic = defaultdict(list)
    for k, t in sorted(load_tags(root).items()):
        by_topic[t["topic"]].append(k)
    rng = random.Random(seed)
    picked = {topic: sorted(rng.sample(keys, min(len(keys), max(MIN_SAMPLE, round(len(keys) * SAMPLE_RATE)))))
              for topic, keys in sorted(by_topic.items())}
    path = root / "data" / "tags" / "qa_sample.json"
    path.write_text(json.dumps(picked, indent=1) + "\n")
    return picked


def agrees(a: dict, b: dict) -> bool:
    return (a["topic"], a["subtopic"]) == (b["topic"], b["subtopic"]) and a["formula_ids"][0] in b["formula_ids"]


def agreement(root: Path, src: Path) -> dict:
    tags = load_tags(root)
    picked = json.loads((root / "data" / "tags" / "qa_sample.json").read_text())
    second = read_runs(src, "qa_*.jsonl")
    per_topic = {}
    for topic, keys in picked.items():
        rows = [{"key": k, "agree": agrees(tags[k], second[k]),
                 "first": {f: tags[k][f] for f in ("topic", "subtopic", "formula_ids")},
                 "second": {f: second[k][f] for f in ("topic", "subtopic", "formula_ids")}}
                for k in keys if k in second]
        n = sum(r["agree"] for r in rows)
        per_topic[topic] = {"sampled": len(keys), "checked": len(rows), "agree": n,
                            "rate": round(n / len(rows), 3) if rows else None,
                            "passes": bool(rows) and len(rows) == len(keys) and n / len(rows) >= AGREEMENT_BAR,
                            "disagreements": [r for r in rows if not r["agree"]]}
    (root / "data" / "tags" / "qa.json").write_text(json.dumps(per_topic, indent=1, ensure_ascii=False) + "\n")
    return per_topic


def question_text(q: dict) -> str:
    opts = " | ".join(o["text"] or "" for o in q["options"])
    return f"{q['stem_text']} || {opts}".strip()


def dedupe(root: Path, threshold: float = DUP_THRESHOLD) -> list[dict]:
    import numpy as np
    from fastembed import TextEmbedding

    questions = load_questions(root)
    tags = load_tags(root)
    keys = [k for k in sorted(tags) if questions[k]["stem_text_complete"] and len(questions[k]["stem_text"]) >= 40]
    vecs = np.array(list(TextEmbedding(EMBED_MODEL).embed([question_text(questions[k]) for k in keys])))
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    sims = vecs @ vecs.T
    pairs = []
    for i, k in enumerate(keys):  # keys sort by paper, so j < i is an earlier (or the same) shift
        best = None
        for j in range(i):
            other = keys[j]
            if other.rsplit("_", 1)[0] == k.rsplit("_", 1)[0] or other[-3] != k[-3]:
                continue  # same shift, or other section
            if sims[i, j] >= threshold and tags[other]["subtopic"] == tags[k]["subtopic"]:
                if best is None or sims[i, j] > sims[i, best]:
                    best = j
        if best is not None:
            root_key = tags[keys[best]].get("duplicate_of") or keys[best]
            tags[k]["duplicate_of"], tags[k]["duplicate_score"] = root_key, round(float(sims[i, best]), 4)
            pairs.append({"key": k, "duplicate_of": root_key, "score": tags[k]["duplicate_score"]})
        else:
            tags[k].pop("duplicate_of", None)
            tags[k].pop("duplicate_score", None)
    tags_path(root).write_text("".join(json.dumps(tags[k], ensure_ascii=False) + "\n" for k in sorted(tags)))
    return pairs


def coverage(root: Path) -> str:
    questions = load_questions(root)
    tags = load_tags(root)
    qa_path = root / "data" / "tags" / "qa.json"
    qa = json.loads(qa_path.read_text()) if qa_path.exists() else {}
    lines = ["# Tagging coverage", "", "Generated by `python -m pipeline.tags coverage`.", ""]
    untagged = sorted(questions.keys() - tags.keys())
    no_formula = sorted(k for k, t in tags.items() if not t["formula_ids"])
    dups = [t for t in tags.values() if t.get("duplicate_of")]
    used = Counter(i for t in tags.values() for i in t["formula_ids"])
    primary = Counter(t["formula_ids"][0] for t in tags.values())
    lines += [f"- Questions: {len(questions)}; tagged: {len(tags)}; untagged: {len(untagged)}",
              f"- Questions with no formula or method link: **{len(no_formula) + len(untagged)}** (must be 0)",
              f"- Near-duplicates of a question in an earlier shift: {len(dups)}",
              f"- Tag QA: {sum(v['passes'] for v in qa.values())}/{len(qa)} topics at or above "
              f"{AGREEMENT_BAR:.0%} agreement on their 10% blind sample" if qa else "- Tag QA: not run yet", ""]
    for s in SECTIONS:
        tax = load_taxonomy(root, s)
        sec = s.upper()
        sec_tags = [t for k, t in tags.items() if questions[k]["section"] == sec]
        papers = sorted({questions[t["key"]]["paper_id"] for t in sec_tags})
        lines += [f"## {s.title()}", "",
                  "| Topic | Questions | Per shift | Unique patterns | QA agreement | Subtopics (questions) |",
                  "|---|---|---|---|---|---|"]
        for t in tax["topics"]:
            ts = [x for x in sec_tags if x["topic"] == t["topic"]]
            subs = Counter(x["subtopic"] for x in ts)
            q = qa.get(t["topic"])
            qa_cell = f"{q['agree']}/{q['checked']}" if q else "-"
            lines.append(f"| {t['topic']} | {len(ts)} | {len(ts) / len(papers):.1f} | "
                         f"{sum(not x.get('duplicate_of') for x in ts)} | {qa_cell} | "
                         + "; ".join(f"{n} ({c})" for n, c in subs.most_common()) + " |")
        unseen = [e for e in tax["entries"] if used[e["id"]] == 0]
        lines += ["", f"Library entries not yet seen in papers ({len(unseen)}):", ""]
        lines += [f"- `{e['id']}` {e['name']}" for e in unseen] or ["- none"]
        top = [(i, n) for i, n in primary.most_common() if i.split(".")[0] in {x["slug"] for x in tax["topics"]}]
        lines += ["", "Most used as the primary formula or method:", ""]
        lines += [f"- `{i}`: {n}" for i, n in top[:10]]
        lines.append("")
    if dups:
        lines += ["## Near-duplicates", ""]
        lines += [f"- {t['key']} repeats {t['duplicate_of']} (similarity {t['duplicate_score']})"
                  for t in sorted(dups, key=lambda t: t["key"])]
    text = "\n".join(lines) + "\n"
    (root / "COVERAGE_TAGS.md").write_text(text)
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["merge", "sample", "agreement", "dedupe", "coverage"])
    ap.add_argument("src", nargs="?", type=Path)
    ap.add_argument("--repo-root", type=Path, default=ROOT)
    args = ap.parse_args()
    root = args.repo_root
    if args.command in ("merge", "agreement") and not args.src:
        ap.error(f"{args.command} needs the directory of tagger outputs")
    if args.command == "merge":
        res = merge(root, args.src)
        for k, e in sorted(res["problems"].items()):
            print(f"{k}: {'; '.join(e)}")
        print(f"tagged {res['tagged']}, problems {len(res['problems'])}")
    elif args.command == "sample":
        picked = sample(root)
        print(f"{sum(map(len, picked.values()))} questions across {len(picked)} topics")
    elif args.command == "agreement":
        for topic, v in agreement(root, args.src).items():
            print(f"{topic}: {v['agree']}/{v['checked']} {'ok' if v['passes'] else 'RETAG'}")
    elif args.command == "dedupe":
        print(f"{len(dedupe(root))} near-duplicates")
    else:
        coverage(root)


if __name__ == "__main__":
    main()
