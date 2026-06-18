from unittest.mock import patch

from eval import judge


def test_pairwise_both_orders_a_consistent_win():
    # judge always prefers whichever design has title "FUSED"
    def fake_call(system, user, model):
        return "first" if user.index("FUSED") < user.index("OTHER") else "second"

    with patch("eval.judge._ask", side_effect=fake_call):
        verdict = judge.pairwise(
            {"title": "FUSED"}, {"title": "OTHER"}, model="held-out",
            a_name="canonical", b_name="opus_solo"
        )
    assert verdict["winner"] == "canonical"
    assert verdict["consistent"] is True


def test_pairwise_flip_is_tie():
    # judge always says "first" regardless of content -> position bias -> tie
    with patch("eval.judge._ask", return_value="first"):
        verdict = judge.pairwise(
            {"title": "FUSED"}, {"title": "OTHER"}, model="held-out",
            a_name="canonical", b_name="opus_solo"
        )
    assert verdict["winner"] == "tie"
    assert verdict["consistent"] is False


def test_prompt_does_not_leak_contestant_names():
    captured = {}

    def fake_call(system, user, model):
        captured["user"] = user
        return "first"

    with patch("eval.judge._ask", side_effect=fake_call):
        judge.pairwise(
            {"title": "X"}, {"title": "Y"}, model="m",
            a_name="canonical", b_name="opus_solo"
        )
    assert "canonical" not in captured["user"]
    assert "opus_solo" not in captured["user"]
