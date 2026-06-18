from pathlib import Path

from eval import designs

FIXTURE = Path(__file__).parent / "fixtures" / "eval_run"


def test_load_contestants_reads_three_from_disk():
    out = designs.load_contestants(FIXTURE)
    assert out["candidate_A"]["title"] == "A"
    assert out["candidate_B"]["title"] == "B"
    assert out["canonical"]["title"] == "C"
    # opus_solo not yet generated -> absent, not crashing
    assert "opus_solo" not in out


def test_load_contestants_includes_opus_solo_when_present(tmp_path):
    (tmp_path / "candidate_A.json").write_text('{"title": "A"}')
    (tmp_path / "candidate_B.json").write_text('{"title": "B"}')
    (tmp_path / "canonical.json").write_text('{"title": "C"}')
    (tmp_path / "opus_solo.json").write_text('{"title": "O"}')
    out = designs.load_contestants(tmp_path)
    assert out["opus_solo"]["title"] == "O"


def test_missing_required_file_raises(tmp_path):
    (tmp_path / "candidate_A.json").write_text('{"title": "A"}')
    try:
        designs.load_contestants(tmp_path)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass
