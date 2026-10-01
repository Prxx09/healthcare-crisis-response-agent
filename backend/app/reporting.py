from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


NAVY = colors.HexColor("#16324A")
TEAL = colors.HexColor("#287766")
PALE = colors.HexColor("#F1F5F7")
MUTED = colors.HexColor("#657786")


def build_timeline(alert: dict[str, Any], actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = [{
        "timestamp": alert["created_at"],
        "event": "alert_created",
        "title": "Alert created for review",
        "detail": f"{alert['alert_level'].title()} signal entered the Incident Commander queue.",
    }]
    if alert.get("approved_at"):
        decision = alert["status"]
        events.append({
            "timestamp": alert["approved_at"],
            "event": f"alert_{decision}",
            "title": f"Alert {decision}",
            "detail": f"Decision recorded by {alert.get('reviewed_by') or 'Incident Commander'}.",
        })
    for action in actions:
        events.append({
            "timestamp": action["created_at"],
            "event": "action_created",
            "title": "Response action created",
            "detail": f"{action['action_text']} - owner: {action['owner_role']}.",
        })
        if action["updated_at"] != action["created_at"]:
            events.append({
                "timestamp": action["updated_at"],
                "event": "action_updated",
                "title": f"Action marked {action['status'].replace('_', ' ')}",
                "detail": f"Assignee: {action.get('assignee_name') or 'unassigned'}. {action.get('completion_note') or ''}".strip(),
            })
    return sorted(events, key=lambda item: item["timestamp"])


def build_situation_report(alert: dict[str, Any], actions: list[dict[str, Any]]) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=22 * mm, bottomMargin=20 * mm,
        title=f"Situation Report - Alert {alert['id']}", author="CrisisWatch",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=NAVY, alignment=TA_LEFT, spaceAfter=5 * mm))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=5 * mm, spaceAfter=2 * mm))
    styles.add(ParagraphStyle(name="BodyMuted", parent=styles["BodyText"], fontSize=8.5, leading=12, textColor=MUTED))
    styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontSize=8, leading=10))

    region = alert["regions"]["name"]
    condition = alert["conditions"]["name"]
    evidence = alert.get("evidence_summary") or {}
    story: list[Any] = [
        Paragraph("Healthcare Crisis Situation Report", styles["ReportTitle"]),
        Paragraph("Synthetic surveillance decision-support record", styles["BodyMuted"]),
        Spacer(1, 4 * mm),
    ]
    metadata = [
        ["Alert", f"#{alert['id']}", "Status", alert["status"].replace("_", " ").title()],
        ["Region", region, "Condition", condition],
        ["Analysis date", str(alert.get("analysis_date") or "-"), "Level", alert["alert_level"].title()],
        ["Rule version", alert["rule_version"], "Reviewed by", alert.get("reviewed_by") or "Pending"],
    ]
    meta_table = Table(metadata, colWidths=[27 * mm, 55 * mm, 28 * mm, 52 * mm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7E0E6")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([meta_table, Paragraph("Evidence summary", styles["Section"])])
    sources = evidence.get("supporting_sources") or []
    story.append(Paragraph(
        f"The surveillance engine identified a {alert['alert_level']} signal with {len(sources)} supporting source(s): {', '.join(sources) or 'none recorded'}. "
        "This report documents prepared evidence and decisions; it does not represent a clinical diagnosis.", styles["BodyText"]
    ))

    signals = evidence.get("signals") or []
    if signals:
        signal_data = [["Source", "Current", "Baseline", "Change", "Z-score"]]
        for signal in signals:
            signal_data.append([
                signal["signal_source"].replace("_", " ").title(), str(signal["current_count"]),
                str(signal["baseline_mean"]), f"{signal['percent_change']}%", str(signal.get("z_score") or "-"),
            ])
        signal_table = Table(signal_data, colWidths=[48 * mm, 27 * mm, 30 * mm, 28 * mm, 27 * mm], repeatRows=1)
        signal_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7E0E6")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]), ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.extend([Spacer(1, 3 * mm), signal_table])

    story.append(Paragraph("Decision record", styles["Section"]))
    story.append(Paragraph(
        f"Status: <b>{alert['status'].replace('_', ' ').title()}</b>. Reviewer: <b>{alert.get('reviewed_by') or 'Pending'}</b>. "
        f"Note: {alert.get('review_note') or 'No review note recorded.'}", styles["BodyText"]
    ))
    story.append(Paragraph("Response actions", styles["Section"]))
    if actions:
        action_data = [["Action", "Owner / assignee", "Timeframe", "Status"]]
        for action in actions:
            action_data.append([
                Paragraph(action["action_text"], styles["Cell"]),
                Paragraph(f"{action['owner_role']}<br/>{action.get('assignee_name') or 'Unassigned'}", styles["Cell"]),
                Paragraph(action["timeframe"], styles["Cell"]),
                action["status"].replace("_", " ").title(),
            ])
        action_table = Table(action_data, colWidths=[72 * mm, 40 * mm, 30 * mm, 25 * mm], repeatRows=1)
        action_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), TEAL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7E0E6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(action_table)
    else:
        story.append(Paragraph("No response actions have been recorded for this alert.", styles["BodyMuted"]))
    story.extend([Spacer(1, 7 * mm), Paragraph("Decision support only - synthetic aggregate data. Human authorization remains required for controlled response actions.", styles["BodyMuted"])])

    def page_frame(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D7E0E6")); canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
        canvas.setFont("Helvetica", 7); canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 9 * mm, "CrisisWatch | Healthcare Crisis Prediction and Response Agent")
        canvas.drawRightString(192 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return buffer.getvalue()
