"""Structured validation of multi-agent workflow JSON outputs and composite evidence scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

AGENT_SOURCES = frozenset({"llm", "fallback"})

MARKET_AGREEMENT_OK = frozenset({"aligned", "mixed", "divergent", "unverified", "partial alignment"})

MARKET_STANCE_OK = frozenset({"bullish", "bearish", "cautious", "constructive"})

MARKET_BIAS_OK = frozenset({"bullish", "bearish", "mixed", "unknown"})


@dataclass
class QCCheck:
    id: str
    pass_: bool
    detail: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "pass": self.pass_, "detail": self.detail, "required": self.required}


@dataclass
class QCReport:
    checks: list[QCCheck] = field(default_factory=list)
    schema_score_0_100: int = 0
    warnings: list[str] = field(default_factory=list)
    failed_required_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "checks": [c.to_dict() for c in self.checks],
            "schema_score_0_100": self.schema_score_0_100,
            "warnings": list(self.warnings),
            "failed_required_count": self.failed_required_count,
        }


def _str_list(x: Any, max_items: int = 50) -> list[str]:
    if x is None:
        return []
    if isinstance(x, str):
        t = x.strip()
        return [t] if t else []
    if isinstance(x, (list, tuple)):
        out: list[str] = []
        for item in x[:max_items]:
            if item is None:
                continue
            if isinstance(item, dict):
                s = str(item.get("text") or item.get("statement") or item).strip()
            else:
                s = str(item).strip()
            if s:
                out.append(s)
        return out
    return [str(x).strip()] if str(x).strip() else []


def _add(report: QCReport, cid: str, ok: bool, detail: str, *, required: bool = True) -> None:
    report.checks.append(QCCheck(id=cid, pass_=ok, detail=detail, required=required))


def _validate_agent1(agent1: dict[str, Any], report: QCReport) -> None:
    if not isinstance(agent1, dict):
        _add(report, "agent1_is_dict", False, "agent1 is not an object")
        return
    summary = agent1.get("cross_section_summary")
    ok = isinstance(summary, str) and len(summary.strip()) >= 8
    _add(report, "agent1_cross_section_summary", ok, "cross_section_summary missing or too short" if not ok else "ok")
    conns = agent1.get("connections")
    if conns is None:
        conns = []
    if not isinstance(conns, list):
        _add(report, "agent1_connections_list", False, "connections must be a list")
        return
    for i, c in enumerate(conns[:12]):
        if not isinstance(c, dict):
            _add(report, f"agent1_connection_{i}", False, "connection entry not an object", required=False)
            continue
        keys = {"theme", "sections", "why_it_matters", "trigger"}
        sub_ok = all(str(c.get(k) or "").strip() for k in keys)
        _add(
            report,
            f"agent1_connection_shape_{i}",
            sub_ok,
            "connection fields empty or incomplete" if not sub_ok else "ok",
            required=False,
        )


def _validate_agent2(agent2: dict[str, Any], report: QCReport) -> None:
    if not isinstance(agent2, dict):
        _add(report, "agent2_is_dict", False, "agent2 is not an object")
        return
    label = str(agent2.get("world_mood_label", "") or "").strip()
    _add(report, "agent2_mood_label", bool(label), "world_mood_label empty" if not label else "ok")
    try:
        score = int(agent2.get("world_mood_score", 0))
    except (TypeError, ValueError):
        score = 0
    score_ok = -100 <= score <= 100
    _add(report, "agent2_mood_score_range", score_ok, f"score {score} out of [-100,100]" if not score_ok else "ok")
    stance = str(agent2.get("market_stance", "") or "").lower().strip()
    stance_ok = stance in MARKET_STANCE_OK
    _add(report, "agent2_market_stance_enum", stance_ok, f"invalid market_stance {stance!r}" if not stance_ok else "ok")
    desc = agent2.get("description")
    desc_ok = isinstance(desc, str) and len(desc.strip()) >= 4
    _add(report, "agent2_description", desc_ok, "description missing or too short" if not desc_ok else "ok")
    reasoning = agent2.get("reasoning")
    if reasoning is None:
        reasoning = []
    if isinstance(reasoning, str):
        reasoning_ok = len(reasoning.strip()) >= 4
    elif isinstance(reasoning, list):
        reasoning_ok = len(_str_list(reasoning)) >= 1
    else:
        reasoning_ok = False
    _add(
        report,
        "agent2_reasoning",
        reasoning_ok,
        "reasoning should be a non-empty list or string" if not reasoning_ok else "ok",
        required=False,
    )


def _as_truth_checks(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, (list, tuple)):
        out = []
        for item in raw:
            if item is None:
                continue
            out.extend(_str_list(item))
        return out
    return _str_list(raw)


def _validate_agent3(agent3: dict[str, Any], provenance: dict[str, str], report: QCReport) -> None:
    if not isinstance(agent3, dict):
        _add(report, "agent3_is_dict", False, "agent3 is not an object")
        return
    agr = str(agent3.get("market_agreement", "") or "").lower().strip()
    ok_enum = agr in MARKET_AGREEMENT_OK
    _add(report, "agent3_market_agreement_enum", ok_enum, f"invalid market_agreement {agr!r}" if not ok_enum else "ok")
    insight = agent3.get("final_insight")
    ins_ok = isinstance(insight, str) and len(insight.strip()) >= 8
    _add(report, "agent3_final_insight", ins_ok, "final_insight missing or too short" if not ins_ok else "ok")
    checks = _as_truth_checks(agent3.get("truth_checks"))
    if provenance.get("agent3") == "llm" and not checks:
        _add(
            report,
            "agent3_truth_checks_llm",
            False,
            "truth_checks empty for LLM-produced agent3",
            required=False,
        )
    elif provenance.get("agent3") == "llm" and checks:
        _add(report, "agent3_truth_checks_llm", True, f"{len(checks)} checks", required=False)


def _coerce_bias_stance(stance: str) -> str:
    s = stance.lower().strip()
    if s in {"constructive", "bullish"}:
        return "risk_on"
    if s in {"bearish"}:
        return "risk_off"
    return "neutral"


def _cross_consistency(
    agent2: dict[str, Any],
    agent3: dict[str, Any],
    market_snapshot: dict[str, Any],
    report: QCReport,
) -> None:
    bias = str((market_snapshot or {}).get("market_bias", "unknown") or "unknown").lower().strip()
    if bias not in MARKET_BIAS_OK:
        report.warnings.append(f"Unexpected market_bias value {bias!r}")
    stance = str((agent2 or {}).get("market_stance", "") or "").lower().strip()
    agreement = str((agent3 or {}).get("market_agreement", "") or "").lower().strip()

    b_bucket = _coerce_bias_stance(bias if bias != "unknown" else "mixed")
    s_bucket = _coerce_bias_stance(stance)
    if bias == "unknown":
        report.warnings.append("Market bias unavailable; cross-check with tape is limited.")
    elif b_bucket != s_bucket and b_bucket != "neutral" and s_bucket != "neutral":
        report.warnings.append(
            f"News stance ({stance}) vs tape bias ({bias}) may be tensioned — review Agent 3 agreement ({agreement})."
        )

    if agreement == "aligned" and bias == "bearish" and s_bucket == "risk_on":
        report.warnings.append("aligned agreement but bearish tape vs constructive/bullish stance — worth a human pass.")
    if agreement == "divergent" and bias != "unknown" and s_bucket == "neutral":
        report.warnings.append("Divergent read with neutral stance: ensure narrative still matches headlines.")


def validate_workflow_outputs(
    agent1: dict[str, Any],
    agent2: dict[str, Any],
    agent3: dict[str, Any],
    market_snapshot: dict[str, Any],
    provenance: dict[str, str],
) -> QCReport:
    report = QCReport()
    prov = {k: str(v) for k, v in (provenance or {}).items()}
    for key in ("agent1", "agent2", "agent3"):
        if key not in prov:
            prov[key] = "unknown"
        elif prov[key] not in AGENT_SOURCES:
            prov[key] = "unknown"

    _validate_agent1(agent1, report)
    _validate_agent2(agent2, report)
    _validate_agent3(agent3, prov, report)
    _cross_consistency(agent2, agent3, market_snapshot or {}, report)

    required_checks = [c for c in report.checks if c.required]
    passed_req = sum(1 for c in required_checks if c.pass_)
    total_req = len(required_checks)
    if total_req == 0:
        report.schema_score_0_100 = 100
    else:
        report.schema_score_0_100 = int(round(100 * passed_req / total_req))
    report.failed_required_count = sum(1 for c in required_checks if not c.pass_)
    return report


def workflow_confidence_heuristic(agent1: dict[str, Any], agent3: dict[str, Any], market: dict[str, Any]) -> int:
    base = 52
    base += min(18, len((agent1 or {}).get("connections", []) or []) * 6)
    if str((agent3 or {}).get("market_agreement", "")).lower().strip() in {"aligned", "partial alignment", "mixed"}:
        base += 10
    if (market or {}).get("instruments"):
        base += 8
    return max(20, min(92, base))


def compute_composite_evidence_score(
    qc_report: QCReport,
    provenance: dict[str, str],
    marquee_qc: dict[str, Any] | None,
    confidence_pct: int | None = None,
) -> int:
    schema = max(0, min(100, int(qc_report.schema_score_0_100)))
    marquee = int(marquee_qc.get("score", 0) or 0) if isinstance(marquee_qc, dict) else 0
    conf = int(confidence_pct) if confidence_pct is not None else 58
    conf = max(20, min(92, conf))
    score = int(round(schema * 0.42 + marquee * 0.33 + conf * 0.25))
    if any(provenance.get(k) == "fallback" for k in ("agent1", "agent2", "agent3")):
        score = min(score, 70)
    return max(0, min(100, score))


def metrics_from_workflow_dict(workflow: dict[str, Any] | None) -> dict[str, Any]:
    if not workflow or not isinstance(workflow, dict):
        return {}
    a1 = workflow.get("agent1") or {}
    a2 = workflow.get("agent2") or {}
    a3 = workflow.get("agent3") or {}
    return {
        "world_mood_score": int(a2.get("world_mood_score", 0) or 0),
        "world_mood_label": str(a2.get("world_mood_label", "") or ""),
        "connections_count": len(a1.get("connections") or []) if isinstance(a1.get("connections"), list) else 0,
        "market_agreement": str(a3.get("market_agreement", "") or ""),
    }


def compare_quick_and_full(quick: dict[str, Any], full: dict[str, Any]) -> dict[str, Any]:
    q = metrics_from_workflow_dict(quick) if quick else {}
    f = metrics_from_workflow_dict(full) if full else {}
    return {
        "quick": q,
        "full": f,
        "deltas": {
            "world_mood_score": int(f.get("world_mood_score", 0)) - int(q.get("world_mood_score", 0)),
            "connections_count": int(f.get("connections_count", 0)) - int(q.get("connections_count", 0)),
            "market_agreement_changed": str(q.get("market_agreement", "")) != str(f.get("market_agreement", "")),
        },
    }