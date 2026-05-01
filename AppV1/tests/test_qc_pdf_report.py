"""Smoke tests for QC PDF export."""

from __future__ import annotations

import os

from reporting.qc_pdf_report import build_report_markdown, generate_qc_report_pdf


def test_generate_pdf_reportlab_magic():
    os.environ["MARQUEE_QC_PDF_ENGINE"] = "reportlab"
    state = {
        "status": "ready",
        "workflow": {"generated_at": "2026-05-01T12:00:00Z"},
        "marquee_qc": None,
    }
    out = generate_qc_report_pdf(state, last_refresh=None)
    assert out.startswith(b"%PDF")


def test_build_markdown_includes_headers():
    md = build_report_markdown(
        {"status": "idle", "workflow": {}},
        report_generated_iso="2026-05-01T00:00:00Z",
        last_refresh_iso=None,
    )
    assert "Marquee QC report" in md
    assert "Provenance" in md
