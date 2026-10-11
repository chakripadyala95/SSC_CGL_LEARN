# Tagger prompt v3

v2 added decision rules after the v1 sample check found taggers splitting on overlapping subtopics and on
generic vs specific primary ids. v3 adds rules 5-8 after the v2 check: the remaining splits were a subtopic that
did not match the primary id, and the primary id in data interpretation, savings chains and two-item deals.

You tag SSC CGL Tier-1 {section_name} questions against an approved taxonomy and formula/method library.

## Inputs
- `{reference_path}`: the approved `topics` (with subtopics and example question types) and library `entries`
  (`id`, `subtopic` as "Topic / Subtopic", name, statement, shortcut). Use only these topics, subtopics and ids.
- `{batch_path}`: the questions. Each has `key`, the stem (may be partial: `stem_text_complete` false), options,
  the verified `answer`, a verified solver's method and steps, and `crop` (a path under
  /home/user/SSC_CGL_LEARN). **Open the crop with the Read tool whenever the stem is incomplete, an option is an
  image, or the question has a figure**; do not tag from the solver's steps alone in those cases.

## Output
Write one JSON object per question, one per line, to `{out_path}`, with exactly these keys:

```json
{"key": "...", "topic": "...", "subtopic": "...", "question_type": "...",
 "formula_ids": ["primary id first", "..."], "shortcut_used": "...", "difficulty": 3,
 "expected_time_sec": 45, "has_visual": false, "tagger": "{tagger_id}", "prompt_version": "tagger_v3"}
```

- `topic` and `subtopic`: exactly as written in the reference.
- `question_type`: a short name for the pattern, in the same style as the reference's question types (reuse one
  when it fits, e.g. "successive discount on marked price").
- `formula_ids`: 1-3 approved ids the fastest correct solution needs, the primary (most decisive) first. Every
  question gets at least one. An id may come from another topic when that is what the solution uses.
- `shortcut_used`: the quickest method a well-prepared candidate uses, in at most 8 words
  (e.g. "multiplying factors", "value-putting", "option back-solve", "unit digit").
- `difficulty`: 1 (one-step recall) to 5 (multi-step, easy to go wrong), for an SSC CGL candidate.
- `expected_time_sec`: realistic time for a well-prepared candidate using that shortcut (typically 20-90).
- `has_visual`: true if the question itself contains a figure, chart, table or image options.

## Decision rules (apply in order)
1. **Open the crop** for every question with a figure, chart, table, image option or incomplete stem. Never
   tag those from the solver's steps alone.
2. **Topic and subtopic follow what is asked**, not the arithmetic used on the way:
   - A price after discounts or a marked price is Profit & Loss / Discount (even if it is "just percentages");
     a chain of percentage changes on a non-price quantity is Percentage.
   - Data read off a table, bar graph, line graph or pie chart is Data Interpretation, under the chart type.
   - Trigonometry: "find θ" or "solve for x" is Trig equations; "simplify / evaluate an expression" is Identities.
   - Geometry: put the question under the figure it is about (triangle, circle, quadrilateral), not under the
     theorem; a question asking for an area or perimeter of a plane figure is Mensuration.
3. **Primary id = the most specific entry that names the decisive step.** Generic entries are primary only
   when nothing more specific applies: figure.element-tracking, data-interpretation.read-and-total,
   average.arithmetic-mean, trigonometry.pythagorean-identities, percentage.percent-of-quantity,
   profit-loss.profit-percent. List a generic entry second when it is also used.
   - Figure series: name the actual rule (rotation-step, position-permutation, element-count-change ...).
   - Dice: cyclic-order when the answer comes from reading the clockwise order around a common face;
     common-face-opposite when it comes from the face shared by two views; adjacency-elimination when the
     answer comes from ruling out faces seen next to it.
   - Remainders: remainder-cyclicity for powers; remainder-theorem for polynomial remainders.
4. Ties: prefer the subtopic whose question types (in the reference) best match the wording.
5. **The subtopic is the primary id's subtopic** whenever the primary id belongs to the question's own topic
   (e.g. primary trigonometry.reciprocal-sum-two -> Identities; primary trigonometry.complementary-angles ->
   Complementary angles), even if a question type listed under another subtopic sounds closer. Data
   Interpretation is the exception: its subtopic is always the chart type (Table, Pie chart, Bar graph).
6. **Data Interpretation primary id** is the data-interpretation entry for what is computed from the chart:
   percentage-from-chart (a percent or percent change), ratio-from-chart (a ratio), average-from-chart (an
   average), pie-percent-value / pie-central-angle (pie shares), derived-quantity (a quantity not shown on the
   chart must be worked out first, e.g. numbers of men from a total and a ratio), read-and-total only for a
   plain sum or difference. Ids from other topics (ratio-to-parts, reverse-percentage ...) go second.
7. **Percentage**: a chain of spending shares of an income ending in savings (rent, then a share of the rest,
   ..., saves X) is Income, expenditure & savings with percentage.income-expenditure-savings primary.
8. **Profit & Loss**: gain or loss over two transactions (sell one item, use the money for another; two items
   with different gain %) is Profit & loss basics with profit-loss.overall-gain primary. successive-discount is
   only for discounts applied one after another on a marked price.

Tag independently from the meaning of the question. Write the file with a short Python script if convenient,
then check it has one line per question, valid JSON, approved topics/subtopics/ids. Reply with only: lines
written and any questions you could not tag confidently (key and one-line reason).
