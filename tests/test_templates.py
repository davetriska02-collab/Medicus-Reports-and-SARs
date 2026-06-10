"""Built-in report template integrity."""
from sar.report_templates import _builtin_templates

EXPECTED_IDS = {
    "tpl_insurance", "tpl_uc_fitness", "tpl_military", "tpl_safeguarding",
    "tpl_pip", "tpl_dvla", "tpl_firearms", "tpl_adoption", "tpl_occhealth",
    "tpl_travel", "tpl_capacity", "tpl_group2_driver", "tpl_housing",
}


def test_expected_templates_present():
    ids = {t["id"] for t in _builtin_templates()}
    assert EXPECTED_IDS <= ids


def test_template_structure():
    templates = _builtin_templates()
    ids = [t["id"] for t in templates]
    assert len(ids) == len(set(ids)), "duplicate template ids"
    for t in templates:
        assert t["name"] and t["category"] and t["is_builtin"]
        assert t["questions"], f"{t['id']} has no questions"
        qids = [q["id"] for q in t["questions"]]
        assert len(qids) == len(set(qids)), f"duplicate question ids in {t['id']}"
        for q in t["questions"]:
            assert q["text"].strip()
            assert q.get("keywords") or q.get("section_hints"), \
                f"{t['id']}/{q['id']} has no evidence-extraction hints"
            assert q.get("question_type") in ("yes_no", "free_text", "multiple_choice")
            if q["question_type"] == "multiple_choice":
                assert q.get("options")
