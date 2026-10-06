from pipeline.tags import agrees, validate

SUBS = {("Percentage", "Successive change")}
IDS = {"percentage.successive-change", "percentage.basic"}
TAG = {"key": "p_Q01", "topic": "Percentage", "subtopic": "Successive change", "question_type": "x",
       "formula_ids": ["percentage.successive-change"], "shortcut_used": "multiplying factors", "difficulty": 2,
       "expected_time_sec": 30, "has_visual": False, "tagger": "tagger-a", "prompt_version": "tagger_v1"}


def test_valid_tag():
    assert validate(TAG, SUBS, IDS) == []


def test_tag_needs_a_known_formula():
    assert validate({**TAG, "formula_ids": []}, SUBS, IDS) == ["no formula or method id"]
    assert validate({**TAG, "formula_ids": ["percentage.nope"]}, SUBS, IDS) == ["unknown id percentage.nope"]


def test_agreement_needs_same_subtopic_and_primary_id():
    assert agrees(TAG, {**TAG, "formula_ids": ["percentage.basic", "percentage.successive-change"]})
    assert not agrees(TAG, {**TAG, "formula_ids": ["percentage.basic"]})
    assert not agrees(TAG, {**TAG, "subtopic": "Other"})
