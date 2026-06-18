from eval import metrics


def _design(**over):
    base = {
        "title": "X", "executive_summary": "s", "context": "c",
        "requirements_mapping": [{"requirement": "R1", "how_addressed": "a"}],
        "components": [{"name": "n"}], "data_flows": ["f"], "tech_stack": ["t"],
        "nfrs": ["n"],
        "decisions": [
            {"id": "AD-01", "decision": "use X", "rationale": "r",
             "alternatives": "Soft delete (risks ghost vouchers).", "risk": "rk"},
            {"id": "AD-02", "decision": "use Y", "rationale": "r",
             "alternatives": "", "risk": "rk"},
            {"id": "AD-03", "decision": "use Z", "rationale": "r",
             "alternatives": "N/A", "risk": "rk"},
        ],
        "risks": [
            {"title": "deadlocks", "severity": "high", "mitigation": "lock ordering"},
            {"title": "bloat", "severity": "low", "mitigation": ""},
        ],
        "cost_estimate": "e", "open_questions": ["q"],
    }
    base.update(over)
    return base


def test_alternatives_density_counts_only_substantive():
    # AD-01 substantive; AD-02 empty; AD-03 "N/A" is boilerplate -> 1 of 3
    m = metrics.alternatives_density(_design())
    assert m["count"] == 1
    assert m["ratio"] == 1 / 3


def test_risk_specificity_requires_named_risk_and_mitigation():
    # 2 risks, only 1 has a mitigation -> 1
    assert metrics.risk_specificity(_design()) == 1


def test_structural_completeness_passes_when_all_sections_present():
    assert metrics.structural_completeness(_design()) is True


def test_structural_completeness_fails_on_empty_section():
    assert metrics.structural_completeness(_design(risks=[])) is False


def test_all_metrics_bundles_objective_scores():
    out = metrics.objective_scores(_design())
    assert out["alternatives_count"] == 1
    assert out["risk_specificity"] == 1
    assert out["structural_complete"] is True
