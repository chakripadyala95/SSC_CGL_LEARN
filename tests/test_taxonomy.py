import copy

from pipeline.taxonomy import ROOT, SECTIONS, check, check_tags, load

LIB = {"topics": [{"topic": "Percentage", "slug": "percentage", "question_count": 1,
                   "subtopics": [{"name": "Successive change", "question_types": [], "question_count": 1}]}],
       "entries": [{"id": "percentage.successive-change", "topic": "Percentage", "subtopic": "Successive change",
                    "name": "Successive change", "statement": "(1+a)(1+b)-1", "visual": True, "seen": True,
                    "question_count": 1}]}


def test_valid_library_passes():
    assert check(LIB) == []


def test_id_prefix_must_be_topic_slug():
    lib = copy.deepcopy(LIB)
    lib["entries"][0]["id"] = "pct.successive-change"
    assert any("prefix" in e for e in check(lib))


def test_duplicate_ids_fail():
    lib = copy.deepcopy(LIB)
    lib["entries"].append(dict(lib["entries"][0]))
    assert any("duplicate id" in e for e in check(lib))


def test_committed_taxonomy_and_draft_tags_are_consistent():
    for s in SECTIONS:
        lib = load(ROOT, s)
        assert check(lib) + check_tags(ROOT, s, lib) == []
