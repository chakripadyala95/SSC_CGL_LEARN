"""Phase 2 extraction: pull the Quant and Reasoning questions out of the accepted response sheets.

Usage: python -m pipeline.extract [--repo-root PATH] [--no-images]

Reads data/intake_manifest.json and writes:
  data/questions/questions.jsonl   one record per Quant/Reasoning question (1,500 for 30 sheets)
  data/questions/review_queue.json questions that failed a check, with reasons
  data/questions/assets/<paper_id>/  page PNGs (200 DPI) and crops, regenerated from the raw PDFs
  COVERAGE.md                      per paper and section counts

The correct option is read two independent ways and the two must agree:
  1. text layer: the option label ("1.", "2.", ...) is printed in green, the wrong ones in red;
  2. rendered page: the marker icon left of each option is a green tick or a red cross.
Answers are the sheet's key, not trusted: every record starts as key_status UNVERIFIED.
Candidate fields (Status, Chosen Option, header) are never read into the dataset and are blanked
on page images.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from pipeline.topics import tag

SECTIONS = {
    "General Intelligence and Reasoning": "REASONING",
    "General Awareness": "GA",
    "Quantitative Aptitude": "QUANT",
    "English Comprehension": "ENGLISH",
}
KEEP = ("REASONING", "QUANT")
LETTERS = "ABCD"
DPI = 200
TEXT_GREY = 0x252525
OPTION_RE = re.compile(r"^\s*([1-4])\.(?:\s|$)")
LABEL_RE = re.compile(r"^Q\.\s*(\d+)\s*")
QID_RE = re.compile(r"Question ID\s*:\s*(\d+)")
OPTID_RE = re.compile(r"Option\s*([1-4])\s*ID\s*:\s*(\d+)")
# Question ID boxes normally end by x ~= 525pt; further right means the box was clipped by the page frame.
CLIPPED_X1 = 540
PAGE_MARGIN_Y = 60  # Adda247 logos sit above this line on every page


def color_kind(color: int) -> str:
    r, g, b = color >> 16, (color >> 8) & 255, color & 255
    if g > r + 40 and g > b:
        return "green"
    if r > g + 80 and r > b + 80:
        return "red"
    return "other"


@dataclass
class Item:
    """A text line or an image, positioned in document order."""
    page: int
    bbox: tuple[float, float, float, float]
    text: str = ""
    kind: str = "line"  # line | image
    spans: list[dict] = field(default_factory=list)

    @property
    def key(self) -> tuple[int, float, float]:
        return self.page, self.bbox[1], self.bbox[0]


@dataclass
class Option:
    n: int
    span_bbox: tuple[float, float, float, float]
    line: Item
    text_color: str
    marker: Item | None = None
    images: list[Item] = field(default_factory=list)


def read_items(doc: pymupdf.Document) -> list[Item]:
    items: list[Item] = []
    for pno, page in enumerate(doc):
        if len(page.get_text().strip()) < 20:  # Adda247 ad page, a single full-page image
            continue
        for block in page.get_text("dict")["blocks"]:
            bbox = tuple(block["bbox"])
            if bbox[3] < PAGE_MARGIN_Y:
                continue
            if block["type"] == 1:
                items.append(Item(pno, bbox, kind="image"))
                continue
            for line in block["lines"]:
                text = "".join(s["text"] for s in line["spans"]).replace("\xa0", " ")
                if text.strip():
                    items.append(Item(pno, tuple(line["bbox"]), text.strip(), spans=line["spans"]))
    items.sort(key=lambda it: it.key)
    return items


def v_overlap(a, b) -> float:
    return min(a[3], b[3]) - max(a[1], b[1])


@dataclass
class RawQuestion:
    section: str
    seq: int  # 1-based position within the section
    stem: list[Item]
    options: list[Option]
    meta: list[Item]  # Question ID / Option ID lines


def segment(items: list[Item]) -> tuple[list[RawQuestion], list[str]]:
    """Split the document into questions, anchored on each run of option labels 1-4."""
    problems: list[str] = []
    questions: list[RawQuestion] = []
    section = None
    seq: Counter = Counter()
    pending: list[Item] = []  # items since the previous question's options
    current: RawQuestion | None = None
    i = 0
    while i < len(items):
        it = items[i]
        if it.kind == "line" and it.text.startswith("Section :"):
            name = it.text.split(":", 1)[1].strip()
            section = SECTIONS.get(name)
            if section is None:
                problems.append(f"unknown section {name!r}")
            if current is not None:
                current.meta.extend(pending)
            current, pending = None, []
            i += 1
            continue
        opt = None
        if it.kind == "line" and it.bbox[0] < 300:
            for sp in it.spans:
                m = OPTION_RE.match(sp["text"])
                if m and color_kind(sp["color"]) in ("green", "red"):
                    opt = Option(int(m.group(1)), tuple(sp["bbox"]), it, color_kind(sp["color"]))
                    break
        if opt is not None:
            if opt.n == 1:
                # stem = everything since the previous question's metadata ended
                prev_meta_end = 0
                for k, p in enumerate(pending):
                    if p.kind == "line" and ("Chosen Option" in p.text or "Marked For Review" in p.text
                                             or p.text.startswith("Status")):
                        prev_meta_end = k + 1
                if current is not None:
                    current.meta.extend(pending[:prev_meta_end])
                stem = pending[prev_meta_end:]
                seq[section] += 1
                current = RawQuestion(section, seq[section], stem, [opt], [])
                questions.append(current)
            elif current is not None and current.options and current.options[-1].n == opt.n - 1:
                # anything between options (images) belongs to the options
                _attach_between(current, pending)
                current.options.append(opt)
            else:
                problems.append(f"option {opt.n} out of order on page {it.page + 1}")
            pending = []
            i += 1
            continue
        pending.append(it)
        i += 1
    if current is not None:
        current.meta.extend(pending)
    for q in questions:
        _assign_option_images(q)
    return questions, problems


def _attach_between(q: RawQuestion, pending: list[Item]) -> None:
    q.options[-1].images.extend(p for p in pending if p.kind == "image")


def _assign_option_images(q: RawQuestion) -> None:
    """Find each option's marker icon; move figure images that sit in an option's row onto that option."""
    # images that came after option 4 (before the ID block) belong to the options too
    trailing = [m for m in q.meta if m.kind == "image"]
    q.meta = [m for m in q.meta if m.kind != "image"]
    # images in the stem list that sit level with or below option 1 belong to options
    first = q.options[0]
    keep_stem = []
    for s in q.stem:
        level = s.page == first.line.page and s.bbox[3] > first.span_bbox[1] + 1
        if level and s.kind == "image":
            trailing.append(s)
        elif level and s.bbox[1] >= first.span_bbox[1] - 1:
            continue  # "Ans" label glyphs beside the options; keeps the blind stem crop free of options
        else:
            keep_stem.append(s)
    q.stem = keep_stem
    pool = trailing + [img for o in q.options for img in o.images]
    for o in q.options:
        o.images = []
    for img in pool:
        best, best_d = None, None
        for o in q.options:
            if o.line.page != img.page:
                continue
            sx0, sy0, sx1, sy1 = o.span_bbox
            ix0, iy0, ix1, iy1 = img.bbox
            is_marker = ix1 <= sx0 + 2 and ix0 >= sx0 - 25 and v_overlap(img.bbox, o.span_bbox) > 2 \
                and (ix1 - ix0) < 20
            if is_marker:
                best, best_d = o, -1.0
                break
            d = abs((iy0 + iy1) / 2 - (sy0 + sy1) / 2)
            if ix0 >= sx0 and (best_d is None or d < best_d):
                best, best_d = o, d
        if best is None:
            continue
        if best_d == -1.0:
            best.marker = img
        else:
            best.images.append(img)


def marker_kind(pix: pymupdf.Pixmap, bbox, scale: float) -> str:
    """Classify a marker icon from rendered pixels: green tick, red cross, or unknown."""
    x0, y0, x1, y1 = (int(round(v * scale)) for v in bbox)
    green = red = 0
    n = pix.n
    samples = pix.samples_mv
    for y in range(max(y0, 0), min(y1, pix.height)):
        row = y * pix.stride
        for x in range(max(x0, 0), min(x1, pix.width)):
            r, g, b = samples[row + x * n: row + x * n + 3]
            # tick: olive/green (g >= r, little blue); cross: dark red. The pink Adda247 watermark
            # (~248,196,200) that overlaps some icons matches neither.
            if g - b > 40 and g >= r - 10 and g < 220:
                green += 1
            elif r - g > 60 and r - b > 60 and g < 170:
                red += 1
    if green > 3 and green > 2 * red:
        return "tick"
    if red > 3 and red > 2 * green:
        return "cross"
    return "unknown"


def union(bboxes):
    xs0, ys0, xs1, ys1 = zip(*bboxes)
    return min(xs0), min(ys0), max(xs1), max(ys1)


def region_by_page(items: list[Item], pad: float = 2.0) -> list[tuple[int, tuple]]:
    by_page: dict[int, list] = defaultdict(list)
    for it in items:
        by_page[it.page].append(it.bbox)
    out = []
    for p in sorted(by_page):
        x0, y0, x1, y1 = union(by_page[p])
        out.append((p, (x0 - pad, y0 - pad, x1 + pad, y1 + pad)))
    return out


def render_regions(doc: pymupdf.Document, regions: list[tuple[int, tuple]], path: Path,
                   blank: list[tuple[int, tuple]] = ()) -> None:
    """Render one or more page regions stacked vertically into a PNG."""
    rects = [pymupdf.Rect(r) & doc[p].rect for p, r in regions]
    width = max(r.width for r in rects)
    height = sum(r.height for r in rects) + 6 * (len(rects) - 1)
    out = pymupdf.open()
    page = out.new_page(width=width, height=height)
    y = 0.0
    for (p, _), r in zip(regions, rects):
        page.show_pdf_page(pymupdf.Rect(0, y, r.width, y + r.height), doc, p, clip=r)
        for bp, bb in blank:
            if bp == p:
                br = pymupdf.Rect(bb) & r
                if not br.is_empty:
                    page.draw_rect(br - (r.x0, r.y0 - y, r.x0, r.y0 - y), color=None, fill=(1, 1, 1))
        y += r.height + 6
    path.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=DPI).save(path)


def clean_stem_text(stem: list[Item], col_x: float) -> tuple[str, int | None]:
    """Stem text without the "Q.n"/"Ans" labels. col_x is where the content column starts."""
    label = None
    lines = []
    for s in stem:
        if s.kind != "line":
            continue
        t = s.text
        if t == "Ans":
            continue
        if m := LABEL_RE.match(t):
            label = int(m.group(1))
            t = t[m.end():]
        # math-typeset stems print the "Q.n" and "Ans" labels one glyph per line down the left margin
        if s.bbox[2] <= col_x + 1 and len(t) <= 3:
            continue
        if t:
            lines.append(t)
    text = "\n".join(lines).strip()
    # a stem that is only punctuation around typeset math has no usable text layer
    if not re.search(r"[A-Za-z0-9\u0900-\u097F]", text):
        text = ""
    return text, label


def option_text(o: Option) -> str:
    t = o.line.text
    m = OPTION_RE.match(t)
    return t[m.end():].strip() if m else t.strip()


def extract_paper(root: Path, src: dict, images: bool) -> tuple[list[dict], list[str]]:
    path = root / src["stored_path"]
    d, mth, y = src["date"].split(".")
    paper_id = f"{y}-{mth}-{d}_{src['time_slot']}"
    doc = pymupdf.open(path)
    items = read_items(doc)
    raw, problems = segment(items)
    asset_dir = root / "data" / "questions" / "assets" / paper_id
    rel = lambda p: str(p.relative_to(root))  # noqa: E731

    # candidate-specific text to blank on page images
    blanks: list[tuple[int, tuple]] = []
    for it in items:
        if it.kind == "line" and (it.text.startswith(("Status", "Chosen Option", "Marked For Review"))
                                  or it.text in ("Answered", "Not Answered")):
            blanks.append((it.page, (it.bbox[0] - 2, it.bbox[1] - 1, 650, it.bbox[3] + 1)))
    blanks.append((0, (0, PAGE_MARGIN_Y, 650, 200)))  # header: roll number, name, venue

    pages_needed = sorted({it.page for q in raw if q.section in KEEP
                           for it in q.stem + [o.line for o in q.options]})
    pix_cache: dict[int, pymupdf.Pixmap] = {}
    scale = DPI / 72
    for p in pages_needed:
        pix_cache[p] = doc[p].get_pixmap(dpi=DPI)
        if images:
            out = asset_dir / "pages" / f"p{p + 1:02d}.png"
            render_regions(doc, [(p, tuple(doc[p].rect))], out,
                           blank=[b for b in blanks if b[0] == p])

    records = []
    for q in raw:
        if q.section not in KEEP:
            continue
        reasons: list[str] = []
        col_x = min((o.marker.bbox[0] for o in q.options if o.marker), default=q.options[0].span_bbox[0] - 15)
        stem_text, label = clean_stem_text(q.stem, col_x)
        if label is not None and label != q.seq:
            reasons.append(f"label Q.{label} does not match position {q.seq}")
        stem_imgs = [s for s in q.stem if s.kind == "image"]
        qid_line = next((m for m in q.meta if QID_RE.search(m.text)), None)
        ssc_qid = QID_RE.search(qid_line.text).group(1) if qid_line else None
        if qid_line is None:
            reasons.append("Question ID not found")
        elif qid_line.bbox[2] > CLIPPED_X1 or not 10 <= len(ssc_qid) <= 13:
            reasons.append("Question ID box clipped by an overflowing stem")
        option_ids = {}
        for m in q.meta:
            if mm := OPTID_RE.search(m.text):
                option_ids[LETTERS[int(mm.group(1)) - 1]] = mm.group(2)

        if len(q.options) != 4:
            reasons.append(f"{len(q.options)} options, expected 4")
        text_marks = [o for o in q.options if o.text_color == "green"]
        img_marks = []
        for o in q.options:
            if o.marker is None:
                o_kind = "missing"
            else:
                o_kind = marker_kind(pix_cache[o.marker.page], o.marker.bbox, scale)
            if o_kind == "tick":
                img_marks.append(o)
            elif o_kind not in ("cross",):
                reasons.append(f"option {o.n} marker icon {o_kind}")
        ans_text = LETTERS[text_marks[0].n - 1] if len(text_marks) == 1 else None
        ans_img = LETTERS[img_marks[0].n - 1] if len(img_marks) == 1 else None
        if len(text_marks) != 1:
            reasons.append(f"{len(text_marks)} green answer labels in the text layer")
        if len(img_marks) != 1:
            reasons.append(f"{len(img_marks)} tick markers in the page image")
        if ans_text and ans_img and ans_text != ans_img:
            reasons.append(f"text layer says {ans_text}, page image says {ans_img}")
        official = ans_text if ans_text and ans_text == ans_img else None

        no_text_layer = not stem_text
        if no_text_layer and not stem_imgs:
            reasons.append("empty stem with no image")

        stem_regions = region_by_page(q.stem) if q.stem else []
        opt_items = [o.line for o in q.options] + [img for o in q.options for img in o.images] \
            + [o.marker for o in q.options if o.marker]
        full_regions = region_by_page(q.stem + opt_items)
        # left label column ("Q.1", "Ans") is outside the crop's content; keep the stem's own width
        sec = "Q" if q.section == "QUANT" else "R"
        base = f"{sec}{q.seq:02d}"
        crop = asset_dir / f"{base}.png"
        stem_img_path = asset_dir / f"{base}_stem.png" if (stem_imgs or no_text_layer) and stem_regions else None
        options = []
        for o in q.options:
            opt = {"label": LETTERS[o.n - 1], "text": option_text(o), "image": None}
            if o.images:
                ip = asset_dir / f"{base}_opt{LETTERS[o.n - 1]}.png"
                opt["image"] = rel(ip)
                if images:
                    render_regions(doc, region_by_page(o.images, pad=1.0), ip)
            if not opt["text"] and not opt["image"]:
                reasons.append(f"option {opt['label']} has no text or image")
            options.append(opt)
        if images:
            render_regions(doc, full_regions, crop)
            if stem_img_path:
                render_regions(doc, stem_regions, stem_img_path)

        rec = {
            "paper_id": paper_id,
            "mock_id": f"{paper_id}_{q.section}",
            "q_no": q.seq,
            "section": q.section,
            "ssc_question_id": ssc_qid,
            "option_ids": option_ids,
            "stem_text": stem_text,
            "stem_text_complete": bool(stem_text) and not stem_imgs,
            "stem_image": rel(stem_img_path) if stem_img_path else None,
            "options": options,
            "official_answer": official,
            "answer_text_layer": ans_text,
            "answer_page_image": ans_img,
            "key_status": "UNVERIFIED",
            "source_file": src["stored_path"],
            "source_page": full_regions[0][0] + 1 if full_regions else None,
            "source_bbox": [{"page": p + 1, "bbox": [round(v, 1) for v in bb]} for p, bb in full_regions],
            "question_crop": rel(crop),
            "has_visual": bool(stem_imgs) or any(o["image"] for o in options),
            "status": "REVIEW" if reasons else "EXTRACTED",
            "review_reasons": reasons,
        }
        rec.update(tag(rec))
        records.append(rec)
    return records, problems


def cross_checks(records: list[dict]) -> None:
    """Section counts, duplicate (paper, q_no), and the same SSC question keyed differently across shifts."""
    counts = Counter((r["paper_id"], r["section"]) for r in records)
    for r in records:
        n = counts[(r["paper_id"], r["section"])]
        if n != 25:
            flag(r, f"section has {n} questions, expected 25")
    seen = Counter((r["paper_id"], r["section"], r["q_no"]) for r in records)
    for r in records:
        if seen[(r["paper_id"], r["section"], r["q_no"])] > 1:
            flag(r, "duplicate (paper, section, q_no)")
    by_qid: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r["ssc_question_id"] and not any("clipped" in x for x in r["review_reasons"]):
            by_qid[r["ssc_question_id"]].append(r)
    for qid, rs in by_qid.items():
        answers = {r["official_answer"] for r in rs}
        if len(rs) > 1:
            for r in rs:
                r["also_in"] = sorted(f"{o['paper_id']}#{o['section']}{o['q_no']}" for o in rs if o is not r)
        if len(answers) > 1:
            for r in rs:
                flag(r, f"SSC question {qid} keyed differently across shifts")


def flag(r: dict, reason: str) -> None:
    if reason not in r["review_reasons"]:
        r["review_reasons"].append(reason)
    r["status"] = "REVIEW"


def run(root: Path, images: bool = True) -> dict:
    manifest = json.loads((root / "data" / "intake_manifest.json").read_text())
    records: list[dict] = []
    problems: dict[str, list[str]] = {}
    for src in manifest["sources"]:
        if not src["accepted"]:
            continue
        recs, probs = extract_paper(root, src, images)
        records.extend(recs)
        if probs:
            problems[src["filename"]] = probs
    cross_checks(records)
    records.sort(key=lambda r: (r["paper_id"], r["section"] != "QUANT", r["q_no"]))
    out = root / "data" / "questions"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "questions.jsonl").open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    queue = [{"paper_id": r["paper_id"], "section": r["section"], "q_no": r["q_no"],
              "ssc_question_id": r["ssc_question_id"], "reasons": r["review_reasons"],
              "question_crop": r["question_crop"]} for r in records if r["status"] == "REVIEW"]
    (out / "review_queue.json").write_text(json.dumps(queue, indent=1, ensure_ascii=False) + "\n")
    (root / "COVERAGE.md").write_text(render_coverage(records, problems))
    return {"records": records, "problems": problems, "queue": queue}


def render_coverage(records: list[dict], problems: dict[str, list[str]]) -> str:
    from pipeline.topics import QUANT_TOPICS, REASONING_TOPICS

    total = len(records)
    review = sum(r["status"] == "REVIEW" for r in records)
    lines = [
        "# Question bank coverage",
        "",
        "Generated by `python -m pipeline.extract`. Do not edit by hand.",
        "",
        f"{total} questions extracted ({sum(r['section'] == 'QUANT' for r in records)} Quant, "
        f"{sum(r['section'] == 'REASONING' for r in records)} Reasoning) from "
        f"{len({r['paper_id'] for r in records})} papers. {total - review} passed every extraction check; "
        f"{review} are in the review queue (`data/questions/review_queue.json`).",
        "",
        "Every answer is the sheet's own key, read two ways (green label in the text layer, green tick in the "
        "rendered page). All answers stay `UNVERIFIED` until the Phase 2 solvers confirm them. "
        "Topic tags are provisional keyword rules for coverage only; the real tagging is Phase 3.",
        "",
        "## Per paper and section",
        "",
        "| Paper | Section | Parsed | Clean | Review | Answer agreed | Stem as image | Has figure | Topic tagged |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        groups[(r["paper_id"], r["section"])].append(r)
    for (pid, sec), rs in sorted(groups.items()):
        lines.append(
            f"| {pid} | {sec} | {len(rs)} | {sum(r['status'] == 'EXTRACTED' for r in rs)} | "
            f"{sum(r['status'] == 'REVIEW' for r in rs)} | {sum(r['official_answer'] is not None for r in rs)} | "
            f"{sum(r['stem_image'] is not None for r in rs)} | {sum(r['has_visual'] for r in rs)} | "
            f"{sum(r['topic'] is not None for r in rs)} |"
        )
    reasons = Counter()
    for r in records:
        for x in r["review_reasons"]:
            reasons[re.sub(r"\d+", "N", x) if "SSC question" in x else x] += 1
    lines += ["", "## Review reasons", ""]
    lines += [f"- {n} × {x}" for x, n in reasons.most_common()] or ["- none"]
    lines += ["", "## Review queue", ""]
    lines += [f"- {r['paper_id']} {r['section']} Q{r['q_no']}: {'; '.join(r['review_reasons'])}"
              for r in records if r["status"] == "REVIEW"] or ["- none"]
    for sec, names in (("QUANT", QUANT_TOPICS), ("REASONING", REASONING_TOPICS)):
        rs = [r for r in records if r["section"] == sec]
        c = Counter(r["topic"] or "Untagged" for r in rs)
        lines += ["", f"## Provisional topics: {sec.title()} ({len(rs)} questions)", "",
                  "| Topic | Questions | Per shift |", "|---|---|---|"]
        shifts = len({r["paper_id"] for r in rs}) or 1
        for name in list(names) + ["Untagged"]:
            if c[name]:
                lines.append(f"| {name} | {c[name]} | {c[name] / shifts:.1f} |")
    repeats = sum(1 for r in records if r.get("also_in"))
    lines += ["", "## Repeated questions", "",
              f"{repeats} records share their SSC Question ID with a question in another shift."]
    if problems:
        lines += ["", "## Parser notes", ""]
        lines += [f"- `{f}`: {'; '.join(p)}" for f, p in problems.items()]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--no-images", action="store_true", help="skip writing page images and crops")
    args = ap.parse_args()
    res = run(args.repo_root, images=not args.no_images)
    recs = res["records"]
    print(f"extracted {len(recs)} questions, {len(res['queue'])} in review, parser notes {len(res['problems'])}")


if __name__ == "__main__":
    main()
