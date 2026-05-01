"""
qc_report_generator.py
=======================
Generate a crisp, professional QC report PDF for LLM output evaluation.

Usage:
    python qc_report_generator.py                  # uses built-in demo data
    python qc_report_generator.py state.json       # pass your agent_state JSON file

Output: qc_report_<timestamp>.pdf
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)


def qc_report_filename() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"qc_report_{ts}.pdf"


def build_report_markdown(
    agent_state: dict[str, Any],
    *,
    report_generated_iso: str,
    last_refresh_iso: str | None,
) -> str:
    """Compatibility helper kept for tests and debugging."""
    wf = agent_state.get("workflow") or {}
    lines = [
        "# Marquee QC report",
        "",
        f"- Report generated: {report_generated_iso}",
        f"- Workflow generated_at: {wf.get('generated_at', '(not recorded)')}",
        f"- Last refresh: {last_refresh_iso or '(unknown)'}",
        "",
        "## Provenance",
        "",
        str((wf.get("provenance") or {})),
    ]
    return "\n".join(lines)

# ── Palette ──────────────────────────────────────────────────────────────────
INK        = colors.HexColor("#0f172a")   # near-black text
MUTED      = colors.HexColor("#64748b")   # secondary text
RULE       = colors.HexColor("#e2e8f0")   # dividers
ACCENT     = colors.HexColor("#2563eb")   # blue accent
GOOD       = colors.HexColor("#16a34a")   # green ≥80
WARN       = colors.HexColor("#d97706")   # amber 50–79
BAD        = colors.HexColor("#dc2626")   # red <50
CELL_HEAD  = colors.HexColor("#f1f5f9")   # table header bg
CELL_EVEN  = colors.HexColor("#ffffff")
CELL_ODD   = colors.HexColor("#f8fafc")

W, H = LETTER

# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_color(score: float, max_score: float = 100) -> colors.Color:
    pct = score / max_score * 100
    if pct >= 80:
        return GOOD
    if pct >= 50:
        return WARN
    return BAD


def _label_for(score: float, max_score: float = 100) -> str:
    pct = score / max_score * 100
    if pct >= 90: return "Excellent"
    if pct >= 80: return "Good"
    if pct >= 65: return "Moderate"
    if pct >= 50: return "Fair"
    return "Poor"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Custom Flowables ──────────────────────────────────────────────────────────

class ScoreBadge(Flowable):
    """Large circular score badge with label beneath."""
    def __init__(self, score: float, max_score: float = 100, label: str = "", title: str = ""):
        super().__init__()
        self.score = score
        self.max_score = max_score
        self.label = label
        self.title = title
        self.size = 72
        self.width = self.size + 20
        self.height = self.size + 28

    def draw(self):
        c = self.canv
        cx = self.size / 2 + 10
        cy = self.size / 2 + 20
        r = self.size / 2

        # Background circle
        c.setFillColor(CELL_HEAD)
        c.setStrokeColor(RULE)
        c.setLineWidth(1)
        c.circle(cx, cy, r, fill=1, stroke=1)

        # Arc for score
        col = _score_color(self.score, self.max_score)
        pct = self.score / self.max_score
        c.setStrokeColor(col)
        c.setLineWidth(5)
        c.setLineCap(1)
        start_angle = 90
        sweep = 360 * pct
        if sweep > 0:
            c.arc(cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5, start_angle, -sweep)

        # Score number
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 18)
        txt = f"{int(self.score)}"
        tw = c.stringWidth(txt, "Helvetica-Bold", 18)
        c.drawString(cx - tw / 2, cy - 6, txt)
        c.setFont("Helvetica", 7)
        denom = f"/ {int(self.max_score)}"
        dw = c.stringWidth(denom, "Helvetica", 7)
        c.setFillColor(MUTED)
        c.drawString(cx - dw / 2, cy - 15, denom)

        # Label below badge
        if self.label:
            c.setFillColor(col)
            c.setFont("Helvetica-Bold", 8)
            lw = c.stringWidth(self.label, "Helvetica-Bold", 8)
            c.drawString(cx - lw / 2, 10, self.label)

        # Title above badge
        if self.title:
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 7.5)
            tw2 = c.stringWidth(self.title, "Helvetica", 7.5)
            c.drawString(cx - tw2 / 2, cy + r + 6, self.title)


class MiniBar(Flowable):
    """Horizontal bar for a 1–5 pillar score."""
    def __init__(self, label: str, score: int, max_score: int = 5, width: float = 4.5 * inch):
        super().__init__()
        self.label = label
        self.score = score
        self.max_score = max_score
        self._width = width
        self.height = 18
        self.width = width

    def draw(self):
        c = self.canv
        bar_left = 2.5 * inch
        bar_w = self._width - bar_left - 0.4 * inch
        bar_h = 8
        y_bar = 5

        # Label
        c.setFont("Helvetica", 8.5)
        c.setFillColor(INK)
        c.drawString(0, y_bar + 1, self.label)

        # Background track
        c.setFillColor(RULE)
        c.roundRect(bar_left, y_bar, bar_w, bar_h, 3, fill=1, stroke=0)

        # Filled portion
        filled = bar_w * (self.score / self.max_score)
        col = _score_color(self.score, self.max_score)
        c.setFillColor(col)
        c.roundRect(bar_left, y_bar, filled, bar_h, 3, fill=1, stroke=0)

        # Score text
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(INK)
        c.drawRightString(self._width, y_bar + 1, f"{self.score}/{self.max_score}")


class SectionDots(Flowable):
    """Row of colored dots (one per section) with score labels."""
    def __init__(self, sections: dict[str, int], width: float = 5 * inch):
        super().__init__()
        self.sections = sections
        self._width = width
        self.height = 60
        self.width = width

    def draw(self):
        c = self.canv
        items = list(self.sections.items())
        if not items:
            return
        step = self._width / len(items)
        for i, (name, score) in enumerate(items):
            cx = step * i + step / 2
            cy = 32
            r = 18
            col = _score_color(score)
            c.setFillColor(col)
            c.setStrokeColor(colors.white)
            c.setLineWidth(1.5)
            c.circle(cx, cy, r, fill=1, stroke=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 9)
            stxt = str(score)
            sw = c.stringWidth(stxt, "Helvetica-Bold", 9)
            c.drawString(cx - sw / 2, cy - 3, stxt)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 7.5)
            nw = c.stringWidth(name.capitalize(), "Helvetica", 7.5)
            c.drawString(cx - nw / 2, 10, name.capitalize())


# ── Styles ────────────────────────────────────────────────────────────────────

def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1":      ParagraphStyle("H1",      fontName="Helvetica-Bold",  textColor=INK,   fontSize=20, leading=24, spaceAfter=4),
        "h2":      ParagraphStyle("H2",      fontName="Helvetica-Bold",  textColor=ACCENT, fontSize=11, leading=14, spaceBefore=14, spaceAfter=6),
        "kv_key":  ParagraphStyle("KVKey",   fontName="Helvetica",       textColor=MUTED, fontSize=8),
        "kv_val":  ParagraphStyle("KVVal",   fontName="Helvetica-Bold",  textColor=INK,   fontSize=8.5),
        "body":    ParagraphStyle("Body",    fontName="Helvetica",       textColor=INK,   fontSize=8.5, leading=12),
        "caption": ParagraphStyle("Caption", fontName="Helvetica",       textColor=MUTED, fontSize=7.5),
        "footer":  ParagraphStyle("Footer",  fontName="Helvetica",       textColor=MUTED, fontSize=7),
    }


# ── KV Table helper ───────────────────────────────────────────────────────────

def _kv_table(rows: list[tuple[str, str]], st: dict) -> Table:
    data = [[Paragraph(k, st["kv_key"]), Paragraph(str(v), st["kv_val"])] for k, v in rows]
    t = Table(data, colWidths=[1.5 * inch, 5.2 * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
    ]))
    return t


# ── Page decorations ──────────────────────────────────────────────────────────

def _on_page(canv: rl_canvas.Canvas, doc, title: str, ts: str):
    canv.saveState()
    # Top rule
    canv.setStrokeColor(ACCENT)
    canv.setLineWidth(2.5)
    canv.line(0.75 * inch, H - 0.45 * inch, W - 0.75 * inch, H - 0.45 * inch)
    # Header text
    canv.setFont("Helvetica-Bold", 8)
    canv.setFillColor(ACCENT)
    canv.drawString(0.75 * inch, H - 0.60 * inch, title)
    canv.setFont("Helvetica", 7.5)
    canv.setFillColor(MUTED)
    canv.drawRightString(W - 0.75 * inch, H - 0.60 * inch, ts)
    # Footer
    canv.setStrokeColor(RULE)
    canv.setLineWidth(0.5)
    canv.line(0.75 * inch, 0.45 * inch, W - 0.75 * inch, 0.45 * inch)
    canv.setFont("Helvetica", 7)
    canv.setFillColor(MUTED)
    canv.drawString(0.75 * inch, 0.30 * inch, "CONFIDENTIAL — Internal QC use only")
    canv.drawRightString(W - 0.75 * inch, 0.30 * inch, f"Page {doc.page}")
    canv.restoreState()


# ── Main builder ──────────────────────────────────────────────────────────────

def build_qc_pdf(agent_state: dict[str, Any]) -> bytes:
    wf   = agent_state.get("workflow") or {}
    qc   = agent_state.get("marquee_qc") or {}
    qcr  = agent_state.get("qc_report") or {}
    cq   = agent_state.get("compare_quick_full") or {}
    comp = agent_state.get("composite_evidence_score")
    prov = wf.get("provenance") or {}
    status = str(agent_state.get("status", "unknown"))
    ts   = _now_iso()
    gen_at = wf.get("generated_at", "(not recorded)")
    lr   = agent_state.get("last_refresh", "(unknown)")

    metrics_raw = qc.get("metrics") or {}
    headline_score = float(qc.get("score") or 0)
    schema_score = float(qcr.get("schema_score_0_100") or 0)
    composite = float(comp) if comp is not None else None

    METRIC_LABELS = [
        ("semantic",     "Semantic alignment"),
        ("sentiment",    "Sentiment coherence"),
        ("grounding",    "Entity grounding"),
        ("consistency",  "Internal consistency"),
        ("specificity",  "Specificity"),
    ]

    bio = BytesIO()
    doc = SimpleDocTemplate(
        bio,
        pagesize=LETTER,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.70 * inch,
    )

    st = _styles()
    flow = []

    # ── Title block ───────────────────────────────────────────────────────────
    flow.append(Paragraph("LLM Output Quality Report", st["h1"]))
    flow.append(Paragraph("Marquee QC &amp; Provenance · Signal Studio", st["caption"]))
    flow.append(Spacer(1, 4))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=8))

    # ── Run metadata (compact KV) ─────────────────────────────────────────────
    flow.append(_kv_table([
        ("Report generated", ts),
        ("Workflow timestamp", gen_at),
        ("Feed last refresh", lr),
        ("Pipeline status", status.upper()),
    ], st))
    flow.append(Spacer(1, 10))

    # ── Score summary row ─────────────────────────────────────────────────────
    flow.append(Paragraph("Score Summary", st["h2"]))
    badges = []
    if composite is not None:
        badges.append(ScoreBadge(composite, 100, _label_for(composite), "Composite"))
    badges.append(ScoreBadge(headline_score, 100, _label_for(headline_score), "Headline QC"))
    badges.append(ScoreBadge(schema_score, 100, _label_for(schema_score), "Schema QC"))

    badge_row_data = [[b for b in badges]]
    badge_col_w = (W - 1.5 * inch) / max(len(badges), 1)
    badge_table = Table(badge_row_data, colWidths=[badge_col_w] * len(badges), rowHeights=[100])
    badge_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafbfd")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    flow.append(badge_table)
    flow.append(Spacer(1, 12))

    # ── Metric pillars ────────────────────────────────────────────────────────
    flow.append(Paragraph("Headline QC — Metric Pillars (1–5 scale)", st["h2"]))
    for key, label in METRIC_LABELS:
        val = int(metrics_raw.get(key, 0) or 0)
        flow.append(MiniBar(label, val, 5, width=W - 1.5 * inch))
        flow.append(Spacer(1, 2))
    flow.append(Spacer(1, 10))

    # ── Per-section scores ────────────────────────────────────────────────────
    sections_raw = qc.get("sections") or {}
    section_scores: dict[str, int] = {}
    ORDER = ["business", "arts", "technology", "world", "politics"]
    for sid in ORDER:
        row = sections_raw.get(sid)
        if isinstance(row, dict):
            section_scores[sid] = int(row.get("score", 0) or 0)

    if section_scores:
        flow.append(Paragraph("Per-Section Composite Scores", st["h2"]))
        flow.append(SectionDots(section_scores, width=W - 1.5 * inch))
        # Also render a clean table
        tbl_data = [
            [Paragraph("Section", st["kv_key"]),
             Paragraph("Score", st["kv_key"]),
             Paragraph("Rating", st["kv_key"])]
        ]
        for sid, score in section_scores.items():
            tbl_data.append([
                Paragraph(sid.capitalize(), st["body"]),
                Paragraph(f"{score} / 100", st["kv_val"]),
                Paragraph(_label_for(score), st["body"]),
            ])
        sec_tbl = Table(tbl_data, colWidths=[2 * inch, 1.5 * inch, 2 * inch])
        sec_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), CELL_HEAD),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, RULE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [CELL_EVEN, CELL_ODD]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ]))
        flow.append(Spacer(1, 4))
        flow.append(sec_tbl)
        flow.append(Spacer(1, 12))

    # ── Schema QC detail ──────────────────────────────────────────────────────
    flow.append(Paragraph("Schema QC (Deterministic Validators)", st["h2"]))
    if qcr:
        schema_rows = [
            ("Schema score", f"{qcr.get('schema_score_0_100')} / 100"),
            ("Failed required checks", str(qcr.get("failed_required_count", 0))),
            ("Warnings", str(len(qcr.get("warnings") or []))),
        ]
        flow.append(_kv_table(schema_rows, st))
        if qcr.get("warnings"):
            flow.append(Spacer(1, 4))
            warn_data = [[Paragraph("Warning", st["kv_key"])]]
            for w in qcr["warnings"]:
                warn_data.append([Paragraph(str(w), st["body"])])
            warn_tbl = Table(warn_data, colWidths=[W - 1.5 * inch])
            warn_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fef9c3")),
                ("GRID", (0, 0), (-1, -1), 0.3, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            flow.append(warn_tbl)
    else:
        flow.append(Paragraph("Schema QC available after full pipeline run.", st["body"]))
    flow.append(Spacer(1, 12))

    # ── Agent provenance ──────────────────────────────────────────────────────
    if prov:
        flow.append(Paragraph("Agent Provenance", st["h2"]))
        prov_data = [[Paragraph("Agent", st["kv_key"]), Paragraph("Mode", st["kv_key"])]]
        for agent, mode in sorted(prov.items()):
            col = GOOD if str(mode) == "llm" else WARN
            prov_data.append([
                Paragraph(agent, st["body"]),
                Paragraph(str(mode).upper(), ParagraphStyle("M", textColor=col, fontSize=8.5, fontName="Helvetica-Bold")),
            ])
        prov_tbl = Table(prov_data, colWidths=[2 * inch, 2 * inch])
        prov_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), CELL_HEAD),
            ("GRID", (0, 0), (-1, -1), 0.3, RULE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [CELL_EVEN, CELL_ODD]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ]))
        flow.append(prov_tbl)
        flow.append(Spacer(1, 12))

    # ── Quick → full deltas ───────────────────────────────────────────────────
    if isinstance(cq, dict) and cq.get("deltas"):
        flow.append(Paragraph("Quick Snapshot → Full Run Deltas", st["h2"]))
        quick = cq.get("quick") or {}
        full  = cq.get("full")  or {}
        deltas = cq.get("deltas") or {}
        delta_data = [[
            Paragraph("Field", st["kv_key"]),
            Paragraph("Quick", st["kv_key"]),
            Paragraph("Full", st["kv_key"]),
            Paragraph("Δ", st["kv_key"]),
        ]]
        all_keys = sorted(set(list(quick.keys()) + list(full.keys())))
        for k in all_keys:
            qv = quick.get(k, "—")
            fv = full.get(k, "—")
            dv = deltas.get(k, "")
            delta_data.append([
                Paragraph(k, st["body"]),
                Paragraph(str(qv), st["body"]),
                Paragraph(str(fv), st["body"]),
                Paragraph(str(dv) if dv != "" else "—", st["body"]),
            ])
        delta_tbl = Table(delta_data, colWidths=[2 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch])
        delta_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), CELL_HEAD),
            ("GRID", (0, 0), (-1, -1), 0.3, RULE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [CELL_EVEN, CELL_ODD]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ]))
        flow.append(delta_tbl)
        flow.append(Spacer(1, 12))

    # ── Metric definitions (collapsed, small) ─────────────────────────────────
    flow.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=6))
    flow.append(Paragraph("Metric Definitions", st["h2"]))
    defs = [
        ("Semantic alignment",   "Token overlap between rendered output surface and aggregated section packets (briefs, headlines). Bands 1–5."),
        ("Sentiment coherence",  "Aggregated article sentiment vs. world mood score. Larger gaps reduce the score."),
        ("Entity grounding",     "Capitalized phrases in output vs. combined source corpus frequency."),
        ("Internal consistency", "Market agreement wording × lexical overlap between cross-section summary and final insight."),
        ("Specificity",          "Penalizes vague canned phrases; rewards named entities and informative tokens."),
    ]
    def_data = [[Paragraph("Pillar", st["kv_key"]), Paragraph("Definition", st["kv_key"])]]
    for name, defn in defs:
        def_data.append([Paragraph(name, st["body"]), Paragraph(defn, st["body"])])
    def_tbl = Table(def_data, colWidths=[1.6 * inch, W - 1.5 * inch - 1.6 * inch])
    def_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CELL_HEAD),
        ("GRID", (0, 0), (-1, -1), 0.3, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [CELL_EVEN, CELL_ODD]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    flow.append(def_tbl)
    flow.append(Spacer(1, 10))
    flow.append(Paragraph(
        "Scoring: headline composite = round(Σ pillar scores / 25 × 100). "
        "Per-section scores restrict source corpus to that section's packet.",
        st["caption"]
    ))

    # ── Build ─────────────────────────────────────────────────────────────────
    page_title = "LLM Output QC Report · News for People in Hurry"
    doc.build(
        flow,
        onFirstPage=lambda c, d: _on_page(c, d, page_title, ts),
        onLaterPages=lambda c, d: _on_page(c, d, page_title, ts),
    )
    return bio.getvalue()


def generate_qc_report_pdf(
    agent_state: dict[str, Any],
    *,
    last_refresh: datetime | None = None,
) -> bytes:
    """App-facing wrapper that uses the exact sample generator layout."""
    st = dict(agent_state or {})
    if last_refresh is not None:
        if last_refresh.tzinfo is None:
            st["last_refresh"] = last_refresh.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            st["last_refresh"] = last_refresh.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif "last_refresh" not in st:
        st["last_refresh"] = "(unknown)"
    return build_qc_pdf(st)


# ── Demo data (mirrors the uploaded PDF) ──────────────────────────────────────

DEMO_STATE: dict[str, Any] = {
    "status": "ready",
    "last_refresh": "2026-05-01T00:47:57Z",
    "composite_evidence_score": 84,
    "workflow": {
        "generated_at": "2026-05-01T04:48:17.193234Z",
        "provenance": {"agent1": "llm", "agent2": "llm", "agent3": "llm"},
    },
    "marquee_qc": {
        "score": 72,
        "label": "Moderate",
        "metrics": {
            "semantic":     4,
            "sentiment":    5,
            "grounding":    2,
            "consistency":  2,
            "specificity":  5,
        },
        "sections": {
            "business":   {"score": 60},
            "arts":       {"score": 60},
            "technology": {"score": 64},
            "world":      {"score": 64},
            "politics":   {"score": 60},
        },
    },
    "qc_report": {
        "schema_score_0_100": 100,
        "failed_required_count": 0,
        "warnings": ["world_mood_score defaulted to 0 in quick snapshot"],
    },
    "compare_quick_full": {
        "quick":  {"world_mood_score": 0,   "world_mood_label": "Mixed",    "connections_count": 0, "market_agreement": "mixed"},
        "full":   {"world_mood_score": -10, "world_mood_label": "Cautious", "connections_count": 2, "market_agreement": "divergent"},
        "deltas": {"world_mood_score": -10, "connections_count": 2, "market_agreement_changed": True},
    },
}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as fh:
            state = json.load(fh)
    else:
        state = DEMO_STATE
        print("No JSON file supplied — using built-in demo state.")

    pdf_bytes = build_qc_pdf(state)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = f"qc_report_{ts}.pdf"
    with open(out, "wb") as fh:
        fh.write(pdf_bytes)
    print(f"✓ Written: {out}  ({len(pdf_bytes):,} bytes)")