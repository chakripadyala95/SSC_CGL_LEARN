"""Phase 1 intake: validate the 2024 SSC CGL Tier-I response sheets and copy accepted files.

Usage: python -m pipeline.intake [--repo-root PATH]

Writes data/raw/2024/<dd.mm.yyyy>_<HHMM>/<original filename>, data/intake_manifest.json,
SOURCES.md and MISSING.md. Re-running changes nothing unless a source file's hash changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pymupdf

SHEET_GLOB = "SSC-CGL-Tier-1-Question-Paper-English_*.pdf"
SIMILAR_GLOB = "SSC-CGL-T-I-Similar-Paper-*.pdf"
HEADER = "Combined Graduate Level Examination 2024 Tier I"
SECTIONS = {
    "General Intelligence and Reasoning": "REASONING",
    "General Awareness": "GA",
    "Quantitative Aptitude": "QUANT",
    "English Comprehension": "ENGLISH",
}
# Agreed with the user: SSC Question IDs in these sheets run 11-13 digits, so accept 10-13.
QID_RE = re.compile(r"Question ID\s*:\s*(\d+)")
QID_DIGITS = range(10, 14)
# Question ID boxes end at x ~= 470-525pt. A box pushed further right by an overflowing stem is clipped at the
# page frame, truncating its IDs; such questions go to review instead of failing the file.
CLIPPED_X1 = 540
FILENAME_RE = re.compile(
    r"English_(\d{2})\.(\d{2})\.(\d{4})_(\d{1,2})\.(\d{2})-(AM|PM)-\d{1,2}\.\d{2}-(?:AM|PM)"
)
HEADER_TIME_RE = re.compile(r"Exam Time\s*(\d{1,2}):(\d{2})\s*(AM|PM)")
HEADER_DATE_RE = re.compile(r"Exam Date\s*(\d{2})/(\d{2})/(\d{4})")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def to_hhmm(hour: str, minute: str, meridiem: str) -> str:
    h = int(hour) % 12 + (12 if meridiem == "PM" else 0)
    return f"{h:02d}{minute}"


def parse_filename(name: str) -> tuple[str, str] | None:
    """Return (dd.mm.yyyy, HHMM) from a response-sheet filename."""
    m = FILENAME_RE.search(name)
    if not m:
        return None
    dd, mm, yyyy, hour, minute, meridiem = m.groups()
    return f"{dd}.{mm}.{yyyy}", to_hhmm(hour, minute, meridiem)


def original_first(path: Path) -> tuple[str, bool, str]:
    """Sort key placing "name.pdf" before its browser copies "name (1).pdf", "name (2).pdf"."""
    base = re.sub(r" \(\d+\)(?=\.pdf$)", "", path.name)
    return base, base != path.name, path.name


def is_green(color: int) -> bool:
    r, g = color >> 16, (color >> 8) & 255
    return g > r + 40


@dataclass
class SheetScan:
    header: bool = False
    header_date: str | None = None
    header_hhmm: str | None = None
    pages: int = 0
    ad_pages: list[int] = field(default_factory=list)
    annotations: int = 0
    producer: str = ""
    qids: list[str] = field(default_factory=list)
    clipped_qids: list[str] = field(default_factory=list)
    option_ids: int = 0
    statuses: int = 0
    chosen: int = 0
    # per section: questions (green answer options), Question IDs, Q.n labels
    sections: dict[str, dict[str, int]] = field(default_factory=dict)


def scan(path: Path) -> SheetScan:
    """Read the text layer in layout order and count the response-sheet fields per section."""
    s = SheetScan()
    doc = pymupdf.open(path)
    s.pages = doc.page_count
    s.producer = doc.metadata.get("producer") or ""
    events: list[tuple[int, float, float, str, str]] = []
    full_text = []
    for pno, page in enumerate(doc):
        s.annotations += len(list(page.annots()))
        text = page.get_text().replace("\xa0", " ")
        full_text.append(text)
        if len(text.strip()) < 20:
            s.ad_pages.append(pno + 1)
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line["spans"]
                line_text = "".join(sp["text"] for sp in spans).replace("\xa0", " ").strip()
                x0, y0 = line["bbox"][0], line["bbox"][1]
                if line_text.startswith("Section :"):
                    events.append((pno, y0, x0, "section", line_text.split(":", 1)[1].strip()))
                elif re.match(r"Q\.\d+", line_text):
                    events.append((pno, y0, x0, "label", line_text))
                elif m := QID_RE.search(line_text):
                    kind = "clipped" if line["bbox"][2] > CLIPPED_X1 else "qid"
                    events.append((pno, y0, x0, kind, m.group(1)))
                for sp in spans:
                    if re.match(r"^\s*[1-4]\.", sp["text"]) and is_green(sp["color"]):
                        events.append((pno, sp["bbox"][1], sp["bbox"][0], "answer", sp["text"]))
    text = "\n".join(full_text)
    s.header = HEADER in text
    if m := HEADER_DATE_RE.search(text):
        s.header_date = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    if m := HEADER_TIME_RE.search(text):
        s.header_hhmm = to_hhmm(*m.groups())
    s.option_ids = len(re.findall(r"Option [1-4] ID\s*:\s*\d+", text))
    s.statuses = len(re.findall(r"Status\s*:", text))
    s.chosen = len(re.findall(r"Chosen Option\s*:", text))

    current = None
    for _, _, _, kind, value in sorted(events):
        if kind == "section":
            current = SECTIONS.get(value, value)
            s.sections.setdefault(current, {"questions": 0, "qids": 0, "labels": 0})
            continue
        if kind == "qid":
            s.qids.append(value)
        if kind == "clipped":
            s.clipped_qids.append(value)
            continue
        if current is None:
            continue
        key = {"answer": "questions", "qid": "qids", "label": "labels"}[kind]
        s.sections[current][key] += 1
    return s


def overflow_count(s: SheetScan) -> int:
    """Questions whose Question ID box is missing or clipped because a math-typeset stem overflows the page."""
    return sum(max(0, v["questions"] - v["qids"]) for v in s.sections.values())


def unlabeled_count(s: SheetScan) -> int:
    """Questions whose `Q.n` label has no readable text (stem typeset as math); they need crops."""
    return sum(max(0, v["questions"] - v["labels"]) for v in s.sections.values())


def validate(s: SheetScan, file_date: str, file_hhmm: str) -> list[str]:
    """Return rejection reasons; empty means accepted."""
    reasons = []
    if not s.header:
        reasons.append("SSC header missing")
    if (s.header_date, s.header_hhmm) != (file_date, file_hhmm):
        reasons.append(f"header {s.header_date} {s.header_hhmm} != filename {file_date} {file_hhmm}")
    bad = [q for q in s.qids if len(q) not in QID_DIGITS]
    if bad:
        reasons.append(f"Question IDs outside 10-13 digits: {bad}")
    if len(s.qids) + overflow_count(s) != 100:
        reasons.append(f"{len(s.qids)} Question IDs + {overflow_count(s)} overflowed != 100")
    if s.option_ids < 4 * len(s.qids):
        reasons.append(f"{s.option_ids} Option IDs for {len(s.qids)} questions")
    expected = len(s.qids) + len(s.clipped_qids)
    if s.statuses != expected or s.chosen != expected:
        reasons.append(f"Status/Chosen Option counts {s.statuses}/{s.chosen} != {expected}")
    if sorted(s.sections) != sorted(SECTIONS.values()):
        reasons.append(f"sections found: {sorted(s.sections)}")
    for sec in ("QUANT", "REASONING"):
        n = s.sections.get(sec, {}).get("questions", 0)
        if n != 25:
            reasons.append(f"{sec} has {n} questions")
    if s.annotations:
        reasons.append(f"{s.annotations} PDF annotations added")
    return reasons


def notes(s: SheetScan) -> str:
    parts = [
        f"Adda247 re-publication ({s.producer.strip()}); branding header/watermark and "
        f"ad page(s) {', '.join(map(str, s.ad_pages)) or 'none'} accepted as known noise"
    ]
    if n := overflow_count(s):
        where = [
            f"{sec} {v['questions'] - v['qids']}"
            for sec, v in s.sections.items()
            if v["questions"] > v["qids"]
        ]
        parts.append(
            f"{n} question(s) overflow the page with Question ID box cut off ({', '.join(where)}); "
            "to review queue in Phase 2"
        )
    if s.clipped_qids:
        parts.append(f"clipped Question ID(s) {', '.join(s.clipped_qids)} (truncated at page edge)")
    if n := unlabeled_count(s):
        parts.append(f"{n} Quant stem(s) with no readable text layer (math typeset); crop-only")
    return "; ".join(parts)


def run(root: Path) -> dict:
    raw_dir = root / "data" / "raw" / "2024"
    records, duplicates, by_hash = [], [], {}
    # Prefer the original name over browser copies like "name (1).pdf" when deduplicating.
    for path in sorted(root.glob(SHEET_GLOB), key=original_first):
        digest = sha256(path)
        if digest in by_hash:
            duplicates.append({"filename": path.name, "sha256": digest, "same_as": by_hash[digest]})
            continue
        by_hash[digest] = path.name
        parsed = parse_filename(path.name)
        if not parsed:
            records.append({"filename": path.name, "sha256": digest, "accepted": False,
                            "reasons": ["filename not in expected pattern"]})
            continue
        date, hhmm = parsed
        s = scan(path)
        reasons = validate(s, date, hhmm)
        rec = {
            "date": date, "time_slot": hhmm, "filename": path.name, "sha256": digest,
            "key_status": "unknown", "accepted": not reasons, "reasons": reasons,
            "notes": notes(s), "overflow_questions": overflow_count(s),
            "unlabeled_questions": unlabeled_count(s), "clipped_qids": s.clipped_qids,
            "sections": s.sections, "stored_path": None,
        }
        if not reasons:
            dest = raw_dir / f"{date}_{hhmm}" / path.name
            if not dest.exists() or sha256(dest) != digest:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
            rec["stored_path"] = str(dest.relative_to(root))
        records.append(rec)
    records.sort(key=lambda r: (r.get("date", "")[6:], r.get("date", "")[3:5], r.get("date", "")[:2],
                                r.get("time_slot", "")))
    excluded = [p.name for p in sorted(root.glob(SIMILAR_GLOB))]
    manifest = {"sources": records, "duplicates": duplicates, "excluded": excluded}
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "intake_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (root / "SOURCES.md").write_text(render_sources(records))
    (root / "MISSING.md").write_text(render_missing(records, duplicates, excluded))
    return manifest


def render_sources(records: list[dict]) -> str:
    accepted = sum(r["accepted"] for r in records)
    lines = [
        "# Sources",
        "",
        "Generated by `python -m pipeline.intake`. Do not edit by hand.",
        "",
        f"{accepted} of {len(records)} unique 2024 response sheets accepted. "
        "Answer keys are `unknown` (tentative vs final is not stated) until verified in Phase 2.",
        "",
        "Accepted with agreed relaxations: Adda247 branding (logo header, watermark, ad page) is known noise; "
        "Question IDs of 10-13 digits are valid; questions whose Question ID box is cut off by an "
        "overflowing math stem are counted from their answer marker and go to the review queue.",
        "",
        "| Date | Slot | Original filename | Stored path | SHA-256 | Key | Status | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        status = "accepted" if r["accepted"] else "rejected: " + "; ".join(r["reasons"])
        lines.append(
            f"| {r.get('date', '')} | {r.get('time_slot', '')} | `{r['filename']}` | "
            f"`{r['stored_path'] or '-'}` | `{r['sha256']}` | {r.get('key_status', 'unknown')} | "
            f"{status} | {r.get('notes', '')} |"
        )
    return "\n".join(lines) + "\n"


def render_missing(records: list[dict], duplicates: list[dict], excluded: list[str]) -> str:
    lines = ["# Missing, duplicate and excluded files", "",
             "Generated by `python -m pipeline.intake`. For information only.", "",
             "## Duplicates (byte-identical, skipped)", ""]
    lines += [f"- `{d['filename']}` is identical to `{d['same_as']}` (SHA-256 `{d['sha256'][:16]}…`)"
              for d in duplicates] or ["- none"]
    lines += ["", "## Excluded: 2025 \"Similar Paper\" reconstructions", "",
              "Authored in MS Word with no Question IDs; excluded by the spec.", ""]
    lines += [f"- `{name}`" for name in excluded] or ["- none"]
    lines += ["", "## Rejected", ""]
    rejected = [r for r in records if not r["accepted"]]
    lines += [f"- `{r['filename']}`: {'; '.join(r['reasons'])}" for r in rejected] or ["- none"]
    overflow = [r for r in records if r.get("overflow_questions")]
    lines += ["", "## Questions to review (accepted files)", "",
              "Math-typeset stems that run off the page, cutting off the Question ID box. "
              "This is why some sheets show 99 Question IDs or `Ans` labels for 100 questions: "
              "every sheet has exactly 100 green correct-option markers.", ""]
    lines += [f"- {r['date']} {r['time_slot']}: {r['overflow_questions']}" for r in overflow] or ["- none"]
    unlabeled = [r for r in records if r.get("unlabeled_questions")]
    total = sum(r["unlabeled_questions"] for r in unlabeled)
    lines += ["", "## Stems without a text layer (accepted files)", "",
              f"{total} Quant questions across {len(unlabeled)} sheets have their stem and `Q.n` label typeset as "
              "math with no extractable text. Their answer markers are intact; Phase 2 stores them as crops.", ""]
    lines += [f"- {r['date']} {r['time_slot']}: {r['unlabeled_questions']}" for r in unlabeled] or ["- none"]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    root = ap.parse_args().repo_root
    m = run(root)
    ok = sum(r["accepted"] for r in m["sources"])
    print(f"accepted {ok}/{len(m['sources'])}, duplicates {len(m['duplicates'])}, excluded {len(m['excluded'])}")


if __name__ == "__main__":
    main()
