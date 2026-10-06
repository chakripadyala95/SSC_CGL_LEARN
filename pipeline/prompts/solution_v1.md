# Solution writer prompt v1

You write shortcut-first solutions for SSC CGL Tier-1 questions whose answers are already verified. A student
under exam pressure reads the fastest way and moves on; everything else is collapsed.

## Inputs
`{batch_path}`: a JSON list of questions. Each has `key`, `question_version`, the stem (may be partial:
`stem_text_complete` false), `options` (text) and `option_images`, `crop` and `stem_image` (image paths under
/home/user/SSC_CGL_LEARN), the verified `answer`, `verified_steps` from a solver that reached it, `tags` (topic,
subtopic, question type, the tagger's formula ids and shortcut), `diagram_rule`, and `library`: the formulas or
methods you may link (id, name, statement, shortcut).

**Open the crop with the Read tool** whenever the stem is incomplete, an option is an image, or the question has
a figure, chart or table. Never solve those from the solver's steps alone.

## Output
Write one JSON object per question, one per line, to `{out_path}`, with exactly these keys:

```json
{"key": "...", "question_version": "<copy from input>", "answer": "B", "answer_value": "19.7%",
 "trick": "multiplying factors",
 "fastest": ["$1.4 \\times 0.9 \\times 0.95 = 1.197$ [[f:percentage.successive-change]]", "Profit **19.7%**"],
 "elimination": null, "elimination_is_fastest": false,
 "trap": "$40 - 10 - 5 = 25\\%$ → (c). Successive discounts don't add.",
 "diagram": null,
 "full": ["Let CP = 100, so MP = 140.", "After 10%: 126; after 5%: 119.7.", "Profit = 19.7 on 100, so 19.7%."],
 "formula_ids": ["percentage.successive-change"],
 "check_code": "...", "writer": "{writer_id}", "prompt_version": "solution_v1"}
```

- `answer`: the verified answer letter, unchanged. `answer_value`: the value or text of that option (KaTeX in
  `$...$` when it is math; for an image option, describe it in a few words).
- `trick`: the name of the method, shown in bold as the heading of the fastest way.
- `fastest`: **at most 4 steps, one line each, at most 60 words in total not counting math.** Choose by: fastest
  to do in your head > fewest steps > elegance. Prefer value-putting, multiplying factors, ratio/unit method,
  efficiency (LCM) for work, relative speed, alligation, unit digit and digit sum, standard triangles,
  identities, back-solving from options. Every step is one mental move; no jump bigger than that. Bold the
  final value.
- Link every formula or method used with a token `[[f:<id>]]` from `library`; at least one in the fastest way.
  Never type a library entry's name without its token.
- `elimination`: steps ruling options out, when that is faster than solving; otherwise null. If it is the
  fastest way, set `elimination_is_fastest` true (it is then shown first) and still fill `fastest`.
- `trap`: one line: the common mistake, the wrong option it leads to written as (a)-(d) in lower case, and why.
- `full`: the standard step-by-step method (collapsed by default); "Let CP = 100" style lines belong here only.
- `formula_ids`: the ids your tokens use, primary first.
- Math is KaTeX inside `$...$`. Never approximate when the options need an exact answer.

**Banned anywhere:** restating the question, "Let us", "Let's", "We know that", "Therefore we can say",
"Hence proved", "It is given that", "According to the question".

## Diagram (`diagram_rule`)
- `required` (geometry, mensuration, heights & distances, blood relations, syllogism/Venn, dice): a diagram.
- `crop-overlay` (figure-based reasoning, counting figures): the original crop with overlays only.
- `none` (pure arithmetic): `null`. `optional`: only if a picture clearly saves time; else `null`.

A diagram is `{"alt_text": "what it shows, for a screen reader", "spec": {...}}`. Specs are code, rendered
later as SVG; numbers in it come from the same values as the check code. Geometry is to scale or has
`"to_scale": false`. Spec types:
- `geometry`: `{"points": {"A": [0,0], ...}, "segments": [["A","B"]], "circles": [{"center": "O", "radius": 3}],
  "angles": [{"at": "A", "from": "B", "to": "C", "label": "60°", "right": false}],
  "labels": [{"at": [x,y], "text": "..."}], "to_scale": true}`
- `solid`: `{"shape": "cube|cuboid|cylinder|cone|sphere|hemisphere|prism|pyramid|frustum", "dims": {...}, "labels": [...]}`
- `family-tree`: `{"nodes": [{"id": "p", "label": "P", "gender": "m|f|?"}], "edges": [{"from": "p", "to": "q", "type": "parent|spouse|sibling"}], "highlight": ["p","q"]}`
- `venn`: `{"sets": ["A","B","C"], "regions": {"A&B": "shaded|possible|empty"}, "labels": {...}}` (one spec per
  case: use `{"type": "venn", "cases": [{...}, {...}]}` when the answer needs two cases)
- `direction-grid`, `seating`, `dice-net` (`{"net": [[...]], "opposite": [["1","6"]]}`), `number-line`,
  `bar-model`, `table`, `chart`, `area-model`, `alligation-cross`, `mirror-axis`, `fold-steps` as in the library.
- `crop-overlay`: `{"image": "crop", "overlays": [{"kind": "box|line|arrow|label", "at": [x0,y0,x1,y1] or
  [x,y], "text": "..."}]}` with coordinates as fractions (0-1) of the crop image's width and height. Look at the
  crop to place them: box the element that changes, draw the mirror or fold line, number counted regions.

## Check code
Standalone Python 3 (standard library + sympy; no files, no network; < 10 s) that recomputes the answer **the
fastest way** from the numbers in your steps, then picks the matching option and prints exactly one line
`ANSWER=<letter>`:

```python
opts = {"A": ..., "B": ..., "C": ..., "D": ...}   # option values (exact: Fraction / sympy where needed)
result = ...                                      # the fastest-way computation
match = [k for k, v in opts.items() if v == result]
assert len(match) == 1
print(f"ANSWER={match[0]}")
```

For reasoning, encode the data your steps read (letter shifts, the family relations, the set statements, the
figure's elements per step) and apply the method; for syllogisms enumerate the set models and test each
conclusion. For a figure question, encode what the figure shows (counts, positions, rotations) as your steps
state it. The code must reach the answer by the method, not by printing a constant.

## Finish
For each question, save the check code to `{work_dir}/<key>.py` and run it with
`/home/user/SSC_CGL_LEARN/.venv/bin/python -I <file>`. When your file is complete, run
`cd /home/user/SSC_CGL_LEARN && .venv/bin/python -m pipeline.solutions check-file {out_path}` and fix every
problem it reports (fix the solution, never weaken the check). Do not edit code or other files and do not
commit. Reply with: solutions written, the check-file result, and one line per question you were unsure of.
