"""Provisional topic tags from keyword rules.

These are for coverage counts only. The spec's real tagging (taxonomy approval, LLM-proposed tags with a
10% sample check) is Phase 3; every tag here carries topic_source "rule" so it can be replaced wholesale.
Questions whose stem is an image, or that match no rule, stay untagged rather than guessed.
"""

from __future__ import annotations

import re

QUANT_TOPICS = [
    "Number System", "Simplification", "Percentage", "Ratio & Proportion", "Average", "Profit & Loss",
    "SI/CI", "Time & Work", "Time-Speed-Distance", "Mixture & Alligation", "Algebra", "Geometry",
    "Mensuration", "Trigonometry", "Data Interpretation", "Statistics",
]
REASONING_TOPICS = [
    "Analogy", "Classification", "Series", "Coding-Decoding", "Blood Relations", "Direction",
    "Ranking/Order", "Syllogism", "Venn", "Puzzles/Seating", "Mathematical Operations", "Missing Number",
    "Matrix", "Figure-based", "Dice/Cube", "Alphabet/Word order", "Counting Figures",
]

# (topic, subtopic, pattern). First match wins, so specific rules come before broad ones.
QUANT_RULES = [
    ("Data Interpretation", None, r"\b(table|bar[- ]graph|pie[- ]chart|line[- ]graph|histogram|given graph|following graph|chart|income of (five|four|six) )"),
    ("Statistics", None, r"\b(median|mode|standard deviation|variance)\b"),
    ("Trigonometry", "Heights & Distances", r"angle of (elevation|depression)"),
    ("Trigonometry", None, r"\b(sin|cos|tan|cot|sec|cosec)\b|θ|(?-i:\b(sin|cos|tan|cot|sec|cosec)\s*[θαβA-Z0-9])"),
    ("SI/CI", None, r"\b(simple interest|compound interest|compounded|per annum|rate of interest|interest)\b"),
    ("Profit & Loss", "Discount", r"\b(discount|marked price|list price)\b"),
    ("Profit & Loss", None, r"\b(profit|loss|cost price|selling price|gain)\b"),
    ("Mixture & Alligation", None, r"\b(mixture|alligation|solution contains|milk and water|concentration)\b"),
    ("Time-Speed-Distance", None, r"\b(km/h|km/hr|m/s|speed|train|boat|stream|upstream|downstream|distance)\b"),
    ("Time & Work", None, r"\b(pipes?|tap|cistern|tank|complete (a|the) (work|job)|days to (complete|finish)|work)\b"),
    ("Average", None, r"\baverage\b"),
    ("Ratio & Proportion", None, r"\b(ratio|proportion|partnership|share[sd]? (in|the)|divided among)\b|\d+\s*:\s*\d+"),
    ("Percentage", None, r"%|\bper ?cent"),
    ("Ratio & Proportion", "Proportionals & variation", r"mean proportional|fourth proportional|third proportional|varies (directly|inversely)"),
    ("Mensuration", None, r"\b(area|volume|perimeter|surface|cylinder|cone|sphere|hemisphere|cube|cuboid|cuboidal|cubical|prism|pyramid|radius|diameter|rectangle|square)\b"),
    ("Geometry", None, r"\b(triangle|circle|chord|tangent|angle|quadrilateral|polygon|parallelogram|rhombus|trapezium|centroid|incentre|circumcentre|orthocentre|cyclic|arc|perpendicular|bisector|concentric|circles?|straight lines?|points on a plane)\b|∆|△|Δ|∠"),
    ("Algebra", "Ages", r"years ago|as old as|\bages?\b|years (from now|later|hence)"),
    ("Algebra", "Linear equations", r"infinite(ly many)? solutions?|no solution|system of (linear )?equations|coincident lines|satisfy the equations|solution of the following equations|equations .{0,60}parallel|coins|notes of denomination|marbles|chairs"),
    ("Number System", None, r"\b(composite|fractions? is the (largest|smallest)|consecutive|divisible|remainder|factors?|prime|lcm|hcf|l\.c\.m|h\.c\.f|digit|unit place|number of zeros|smallest number|largest number|greatest number)\b"),
    ("Algebra", None, r"\b(x\s*[+\-=]|value of x|if x|polynomial|equation|expression)\b|x2|x³|x\^|\bx\s*\+\s*1/x"),
    ("Simplification", None, r"\b(simplif\w*|value of|evaluate)\b"),
]
REASONING_RULES = [
    ("Syllogism", None, r"\bstatements?\b.*\bconclusions?\b"),
    ("Venn", None, r"venn|diagram (that )?best represents|represents the relationship|numbers in different sections|four different shapes"),
    ("Dice/Cube", None, r"\bdice\b|\bdie\b|\bcube\b"),
    ("Figure-based", "Mirror/Water image", r"mirror image|water image|mirror is placed"),
    ("Figure-based", "Paper folding", r"paper is folded|folded and punched|sheet of paper|paper folding|transparent sheet"),
    ("Figure-based", "Embedded figure", r"embedded|hidden in|figure \(x\) is embedded"),
    ("Counting Figures", None, r"how many triangles|how many squares|number of triangles|number of squares|how many rectangles"),
    ("Figure-based", "Pattern completion", r"complete the (figure|pattern)|figure series|next figure|given figure|following figure"),
    ("Blood Relations", None, r"\b(father|mother|brother|sister|son|daughter|husband|wife|uncle|aunt|grandfather|grandmother|nephew|niece|cousin)\b"),
    ("Direction", None, r"\b(north|south|east|west)\b|turns? (left|right)"),
    ("Coding-Decoding", None, r"code language|is coded as|is written as|coded"),
    ("Mathematical Operations", None, r"interchanged|interchanges of numbers|mathematical signs|signs? (and|to be) interchanged|\+.*−.*×|'\+'|‘\+’"),
    ("Series", None, r"\bseries\b|next term|come next|sequence"),
    ("Missing Number", None, r"missing number|replace the question mark|in place of the question mark|come in place of '?'|in the place of ‘\?’"),
    ("Ranking/Order", None, r"\b(rank|position from|from the (left|right) end|tallest|shortest|heaviest|lightest|in a row)\b"),
    ("Puzzles/Seating", None, r"\b(sitting|seated|circular table|around a|facing the centre|floors?|building|puzzle)\b"),
    ("Classification", None, r"except one|odd (number )?pair|odd one|does not belong|do not belong"),
    ("Analogy", None, r"संबंधित|two sets of numbers|number-?pairs|related to|same relationship|same way as|analog|share the same relationship|is to\b"),
    ("Alphabet/Word order", None, r"dictionary|alphabetical order|english alphabetical|meaningful (english )?word|logical (and meaningful )?order"),
    ("Classification", None, r"odd one|does not belong|do not belong|alike in some manner|same pattern.*group|three of the following"),
    ("Matrix", None, r"\bmatrix\b|\brow\b.*\bcolumn\b"),
]


def _match(rules, text):
    for topic, sub, pat in rules:
        if re.search(pat, text, re.IGNORECASE):
            return topic, sub
    return None, None


def tag(rec: dict) -> dict:
    text = " ".join((rec["stem_text"] + " " + " ".join(o["text"] for o in rec["options"])).split())
    topic = sub = None
    if rec["stem_text"]:
        rules = QUANT_RULES if rec["section"] == "QUANT" else REASONING_RULES
        if rec["section"] == "QUANT" and rec.get("stem_image"):
            # part of the stem is typeset math we cannot read; the generic fallback would be a guess
            rules = [r for r in rules if r[0] != "Simplification"]
        topic, sub = _match(rules, text)
    if topic is None and rec["section"] == "REASONING" and rec["has_visual"] and not rec["stem_text"].strip():
        topic, sub = "Figure-based", None
    return {"topic": topic, "subtopic": sub, "topic_source": "rule" if topic else None}
