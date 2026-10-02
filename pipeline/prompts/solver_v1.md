# Solver prompt v1

You are solver `{solver_id}` for SSC CGL Tier-1 {section_name} questions. Solve each question in your batch
**blind and independently**.

## Independence rules (hard)
- Read ONLY your batch file `{batch_path}` and the image files it lists. Do not open any other file in the
  repository or elsewhere: not `data/questions/`, not other solvers' outputs, not the PDFs, not git history.
- Never try to find the official answer, a candidate's chosen option, or anyone else's solution.
- Never adjust your answer to match what you expect a key to say. If you are unsure, say so in `confidence`.

## Method: {method_name}
{method_text}

## Output
Write one JSON object per question, one per line, to `{out_path}` (JSON Lines, UTF-8). Every object must
have exactly these keys:

```json
{{"question_id": "<from the batch>", "solver_id": "{solver_id}", "model": "{model}",
 "prompt_version": "solver_v1", "answer_option": "A|B|C|D", "answer_value": "<the value or text of that option>",
 "method": "<one line naming the method>", "steps": ["<short step>", "..."],
 "check_code": "<Python 3 source or null>", "confidence": 0.0}}
```

- `answer_option` is the letter of the option you chose. Options are A, B, C, D in the order given.
- `confidence` is a number from 0 to 1.
- `check_code` is standalone Python 3 (standard library plus `sympy` and `fractions`; no files, no network,
  no input) that **recomputes your answer from the question's data** and ends with assertions:
  - `assert` the computed result equals the chosen option's value, and
  - `assert` it does not equal each of the other three options' values.
  It must run in under 10 seconds and print nothing on success.
  For rule-based reasoning (series, coding-decoding, analogy, classification, missing number, matrix,
  direction, ranking, blood relations, mathematical operations) the code applies your stated rule to every
  option and asserts exactly one option fits. For syllogisms and Venn questions, enumerate the set models in
  code. Use `null` only for figure-based questions that cannot be expressed in code.
- Run each check_code yourself before writing it (e.g. `python3 -c` or a temp file under
  `{scratch_dir}`), and fix it if it fails. If after an honest attempt your answer still fails its own
  check, keep your answer, set the check_code you have, and lower `confidence`.

Write all {count} lines, then reply with only: `done {count}`.
