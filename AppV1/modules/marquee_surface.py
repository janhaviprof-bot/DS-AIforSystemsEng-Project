"""Flatten multi-agent workflow JSON into one surface string for marquee QC overlap checks."""

from __future__ import annotations


def marquee_surface_text(workflow: dict) -> str:
    wf = workflow or {}
    parts: list[str] = []
    a1 = wf.get("agent1") or {}
    a2 = wf.get("agent2") or {}
    a3 = wf.get("agent3") or {}
    mkt = wf.get("market_snapshot") or {}

    for blob in (
        a1.get("cross_section_summary", ""),
        a1.get("headline", ""),
        a2.get("description", ""),
        a3.get("final_insight", ""),
        mkt.get("summary", ""),
        wf.get("marquee_text", ""),
    ):
        text = str(blob or "").strip()
        if text:
            parts.append(text)

    conns = a1.get("connections") or []
    if isinstance(conns, list):
        for c in conns[:4]:
            if not isinstance(c, dict):
                continue
            frag = " ".join(
                str(c.get(k) or "").strip()
                for k in ("theme", "trigger", "why_it_matters")
                if c.get(k)
            )
            if frag:
                parts.append(frag)

    return " ".join(parts).strip()
