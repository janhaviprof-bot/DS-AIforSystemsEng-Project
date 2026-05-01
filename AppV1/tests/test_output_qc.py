"""Unit tests for multi-agent output validation and evidence helpers."""

from __future__ import annotations

import os
import sys

_APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from agents.output_qc import (  # noqa: E402
    compare_quick_and_full,
    compute_composite_evidence_score,
    metrics_from_workflow_dict,
    validate_workflow_outputs,
)


def _minimal_valid_bundle():
    agent1 = {
        "cross_section_summary": "Enough text in cross section summary here.",
        "connections": [
            {
                "theme": "macro",
                "sections": ["business", "world"],
                "why_it_matters": "shared catalyst",
                "trigger": "policy",
            }
        ],
    }
    agent2 = {
        "world_mood_label": "Mixed",
        "world_mood_score": 10,
        "market_stance": "cautious",
        "description": "Mood looks cautious overall in this window.",
        "reasoning": ["Headline mix skews careful.", "Volatility in the tape."],
    }
    agent3 = {
        "market_agreement": "mixed",
        "final_insight": "News and markets are only partly aligned right now.",
        "truth_checks": ["Check A", "Check B"],
    }
    market_snapshot = {"market_bias": "mixed", "instruments": [{"symbol": "^GSPC"}]}
    provenance = {"agent1": "llm", "agent2": "llm", "agent3": "llm"}
    return agent1, agent2, agent3, market_snapshot, provenance


def test_validate_all_required_pass():
    a1, a2, a3, m, p = _minimal_valid_bundle()
    r = validate_workflow_outputs(a1, a2, a3, m, p)
    assert r.failed_required_count == 0
    assert r.schema_score_0_100 == 100


def test_validate_world_mood_score_range():
    a1, a2, a3, m, p = _minimal_valid_bundle()
    a2["world_mood_score"] = 150
    r = validate_workflow_outputs(a1, a2, a3, m, p)
    assert r.failed_required_count >= 1
    assert any(c.id == "agent2_mood_score_range" and not c.pass_ for c in r.checks)


def test_validate_invalid_market_agreement():
    a1, a2, a3, m, p = _minimal_valid_bundle()
    a3["market_agreement"] = "INVALID"
    r = validate_workflow_outputs(a1, a2, a3, m, p)
    assert any(c.id == "agent3_market_agreement_enum" and not c.pass_ for c in r.checks)


def test_truth_checks_expected_for_llm_agent3():
    a1, a2, a3, m, p = _minimal_valid_bundle()
    a3["truth_checks"] = []
    r = validate_workflow_outputs(a1, a2, a3, m, p)
    assert any(
        c.id == "agent3_truth_checks_llm" and not c.pass_ and not c.required for c in r.checks
    )


def test_composite_capped_when_fallback():
    a1, a2, a3, m, p = _minimal_valid_bundle()
    r = validate_workflow_outputs(a1, a2, a3, m, p)
    high = compute_composite_evidence_score(
        r,
        {"agent1": "llm", "agent2": "llm", "agent3": "llm"},
        {"score": 95},
        90,
    )
    capped = compute_composite_evidence_score(
        r,
        {"agent1": "fallback", "agent2": "llm", "agent3": "llm"},
        {"score": 95},
        90,
    )
    assert capped <= 70
    assert high >= capped


def test_compare_quick_and_full_deltas():
    quick = {
        "agent1": {"connections": []},
        "agent2": {"world_mood_score": 2},
        "agent3": {"market_agreement": "mixed"},
    }
    full = {
        "agent1": {"connections": [{"theme": "t", "sections": [], "why_it_matters": "w", "trigger": "x"}]},
        "agent2": {"world_mood_score": 15},
        "agent3": {"market_agreement": "aligned"},
    }
    c = compare_quick_and_full(quick, full)
    assert c["deltas"]["world_mood_score"] == 13
    assert c["deltas"]["connections_count"] == 1
    assert c["deltas"]["market_agreement_changed"] is True


def test_metrics_from_workflow_dict():
    wf = {
        "agent1": {"connections": [1, 2]},
        "agent2": {"world_mood_score": -5, "world_mood_label": "Cautious"},
        "agent3": {"market_agreement": "divergent"},
    }
    m = metrics_from_workflow_dict(wf)
    assert m["world_mood_score"] == -5
    assert m["connections_count"] == 2
    assert m["market_agreement"] == "divergent"
