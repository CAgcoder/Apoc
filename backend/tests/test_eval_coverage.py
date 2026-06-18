from unittest.mock import patch

from eval import coverage


def test_coverage_is_addressed_over_total():
    design = {"requirements_mapping": [{"requirement": "R1", "how_addressed": "done"}]}
    checklist = ["R1 must exist", "R2 must exist", "R3 must exist"]

    def fake_judge(item, mapping_text, model):
        return item.startswith("R1")

    with patch("eval.coverage._judge_item", side_effect=fake_judge):
        result = coverage.score(design, checklist, model="held-out")

    assert result["addressed"] == 1
    assert result["total"] == 3
    assert result["coverage"] == 1 / 3


def test_empty_checklist_is_zero_not_crash():
    with patch("eval.coverage._judge_item", return_value=True):
        result = coverage.score({"requirements_mapping": []}, [], model="held-out")
    assert result["coverage"] == 0.0
