# Library writer prompt v1

You write entries for the SSC CGL Tier-1 formula and method library (Quant formulas, Reasoning methods). The
IDs, topics and subtopics are already approved; you fill in the content and the code that proves it.

## Inputs
- `{batch_path}`: JSON with `entries` (the approved id, topic, subtopic, name, draft statement, `visual`,
  `seen`) and, per entry, `examples`: real paper questions that use it, each with `key`, stem, options,
  the **verified** `answer`, a verified solver's steps, and `crop` (an image path under the repo root; open
  it with the Read tool when the stem is an image or has a figure).
- `approved_ids` in the same file: every id in the library, for `related_ids` and `[[f:<id>]]` tokens.

## Output
For each topic in your batch write `/home/user/SSC_CGL_LEARN/data/library/{section}/<topic-slug>.json`: a
JSON array of entries, in the order given, each with exactly these keys:

```json
{"id": "...", "topic": "...", "subtopic": "...", "name": "...",
 "statement": "KaTeX source, no surrounding $",
 "conditions": ["KaTeX or plain text; when the statement holds (e.g. 'a, b > 0', 'r \\neq 1'). [] if none"],
 "derivation": ["one step per item, KaTeX inside $...$ where needed; each step one mental move"],
 "visual_proof": "one or two sentences describing the standard picture proof the diagram shows, or null",
 "shortcut": "the exam shortcut in one line (KaTeX in $...$), or null when the statement is already the shortcut",
 "worked_example": {"question_key": "<an examples key>", "answer": "<its verified answer letter>",
                    "steps": ["at most 4 short steps using this entry; numbers from the real question"]},
 "common_traps": ["one line each: the mistake and which wrong result it gives"],
 "related_ids": ["approved ids a student should see next; 0-4"],
 "diagram": null or {"alt_text": "what the diagram shows, for a screen reader",
                     "spec": {"type": "<one of the types below>", "...": "..."}},
 "verification": {"kind": "identity|shortcut|method|manual", "code": "Python source or null",
                  "reason": "only for manual: why this cannot be machine-checked"}}
```

Rules:
- Statement and derivation must be mathematically correct and standard. Do not invent results.
- Write for a student under exam pressure: short, concrete, no filler ("Let us", "We know that",
  "Therefore we can say", "Hence proved" are banned anywhere).
- Mention another library entry only as a token `[[f:<approved id>]]`, never by typing its name.
- `worked_example` is required when the entry is `seen`; use one of its `examples`, and its `answer` must be
  the verified answer given. For an entry not seen in the papers, set it to null.
- `diagram` is required when `visual` is true; otherwise null unless a picture clearly helps. Numbers in a
  diagram come from the statement or worked example. Geometry is drawn to scale, or `"to_scale": false`.

## Diagram spec types (rendered later as SVG; use only these, keep specs small)
- `geometry`: `{"points": {"A": [0,0], ...}, "segments": [["A","B"]], "circles": [{"center": "O", "radius": 3}],
  "angles": [{"at": "A", "from": "B", "to": "C", "label": "60°", "right": false}],
  "labels": [{"at": [x,y], "text": "..."}], "to_scale": true}`
- `solid`: `{"shape": "cube|cuboid|cylinder|cone|sphere|hemisphere|prism|pyramid|frustum", "dims": {"r": "r", "h": "h"}, "labels": [...]}`
- `area-model`: `{"rows": ["a","b"], "cols": ["a","b"], "cells": [["a^2","ab"],["ab","b^2"]]}`
- `bar-model`: `{"bars": [{"label": "CP", "parts": [{"value": 100, "label": "100"}]}, ...]}`
- `alligation-cross`: `{"high": 30, "low": 10, "mean": 18, "ratio": "12 : 8"}`
- `number-line`: `{"min": 0, "max": 100, "marks": [...], "segments": [{"from": 0, "to": 40, "label": "..."}]}`
- `chart`: `{"kind": "line|bar", "series": [{"label": "SI", "points": [[0,100],[1,110]]}]}`
- `venn`: `{"sets": ["A","B"], "regions": {"A&B": "shaded|possible|empty|x"}}`
- `family-tree`: `{"nodes": [{"id": "p", "label": "P", "gender": "m|f|?"}], "edges": [{"from": "p", "to": "q", "type": "parent|spouse|sibling"}]}`
- `direction-grid`: `{"path": [[0,0],[0,5],[3,5]], "labels": [...], "compass": true}`
- `seating`: `{"layout": "linear|circle", "facing": "north|centre|outward", "seats": ["A","?","B"]}`
- `dice-net`: `{"net": [["","1",""],["2","3","4"],["","5",""],["","6",""]], "opposite": [["1","6"]]}`
- `fold-steps`: `{"steps": [{"fold": "vertical|horizontal|diagonal", "punches": [[x,y]]}]}`
- `mirror-axis`: `{"axis": "vertical|horizontal", "sample": "text or glyphs to reflect"}`
- `table`: `{"header": [...], "rows": [[...]]}`

## Verification code (standalone Python 3: standard library + sympy; no files, no network; < 10 s)
- **identity** (Quant formulas that are algebraic or trigonometric identities): build lhs and rhs with SymPy
  and `assert sympy.simplify(lhs - rhs) == 0` (use `trigsimp`/`expand` too if needed). For geometric
  results, verify with coordinates (place points, compute with SymPy or exact fractions) on general
  symbols or on many random configurations.
- **shortcut** (a shortcut or derived formula): compare it with the standard formula on at least 1,000 random
  valid inputs (`random.seed(0)`; exact `fractions.Fraction` where possible, else `math.isclose`), count
  them, and `print(f"CASES={n}")`.
- Any entry with `conditions`: test each condition at its boundary (e.g. the formula breaks or changes at
  r = 1, a triangle inequality at equality, a discount of 100%), then `print("BOUNDARY_OK")`.
- **method** (Reasoning methods): implement the method as a function and apply it to the worked example's
  data (and to at least one more case you construct). Assert it produces the verified answer and rules out
  every other option. For syllogism/Venn methods, enumerate the set models.
- **manual**: only when the content is truly not machine-checkable (e.g. a visual figure rule judged on an
  image). Give a concrete `reason`. Use it sparingly.
- The code prints nothing else. Run every code block yourself before writing it (save it to
  `{scratch_dir}/<id>.py` and run `/home/user/SSC_CGL_LEARN/.venv/bin/python -I <file>`). Fix the content, not
  the check, if it fails; never weaken a check to make it pass.

## Finish
Run `cd /home/user/SSC_CGL_LEARN && .venv/bin/python -m pipeline.library check {topic_flags}` and then
`.venv/bin/python -m pipeline.library verify {topic_flags}`. Fix every problem they report in your entries.
Only write files for your own topics. Do not edit code, tests or other topics' files, and do not commit.
Reply with: entries written, verification counts (PASSED / FAILED / NEEDS_REVIEW) and one line per entry
that is not PASSED.
