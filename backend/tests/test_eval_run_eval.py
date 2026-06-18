from pathlib import Path

from eval import run_eval

FIXTURE = Path(__file__).parent / "fixtures" / "eval_run"


def test_evaluate_run_builds_four_way_objective_row():
    # candidate_A has 1 substantive alternative, candidate_B has 0, canonical has 2
    row = run_eval.evaluate_run(FIXTURE, brief_slug="fixture")
    assert row["candidate_A"]["alternatives_count"] == 1
    assert row["candidate_B"]["alternatives_count"] == 0
    assert row["canonical"]["alternatives_count"] == 2
    # opus_solo absent in this fixture
    assert "opus_solo" not in row


def test_render_report_contains_headline_delta(tmp_path):
    rows = {
        "fincore": {
            "canonical": {"alternatives_count": 6},
            "opus_solo": {"alternatives_count": 3},
        }
    }
    out = tmp_path / "report.md"
    run_eval.render_report(rows, out)
    text = out.read_text()
    assert "alternatives_count" in text
    assert "fincore" in text
