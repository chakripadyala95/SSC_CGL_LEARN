# Tagger prompt v1

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
 "expected_time_sec": 45, "has_visual": false, "tagger": "{tagger_id}", "prompt_version": "tagger_v1"}
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

Tag independently from the meaning of the question. Write the file with a short Python script if convenient,
then check it has one line per question, valid JSON, approved topics/subtopics/ids. Reply with only: lines
written and any questions you could not tag confidently (key and one-line reason).
