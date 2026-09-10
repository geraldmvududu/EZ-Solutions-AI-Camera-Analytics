"""Real report generation (section 35) — CSV export streams actual rows from the
database; the PDF report is built with reportlab from the same real aggregate queries
used by the analytics dashboard (app/services/analytics_service.py). No sample/
placeholder content."""

import csv
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.event import Event
from app.schemas.analytics import AnalyticsSummary


def events_to_csv(events: list[Event]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Event ID", "Camera ID", "Type", "Severity", "Description", "Occurred At", "Demo"])
    for e in events:
        writer.writerow([str(e.id), str(e.camera_id), e.event_type.value, e.severity.value, e.description, e.occurred_at.isoformat(), e.is_demo])
    return buffer.getvalue()


def alerts_to_csv(alerts: list[Alert]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Alert ID", "Camera ID", "Type", "Severity", "Status", "Notes", "Created At", "Acknowledged At", "Resolved At"])
    for a in alerts:
        writer.writerow([
            str(a.id), str(a.camera_id), a.alert_type, a.severity.value, a.status.value, a.notes,
            a.created_at.isoformat(),
            a.acknowledged_at.isoformat() if a.acknowledged_at else "",
            a.resolved_at.isoformat() if a.resolved_at else "",
        ])
    return buffer.getvalue()


def build_security_report_pdf(summary: AnalyticsSummary, tenant_name: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("EZ Solutions AI Camera Analytics — Security Report", styles["Title"]))
    story.append(Paragraph(tenant_name, styles["Normal"]))
    story.append(Paragraph(
        f"Period: {summary.range_start.strftime('%Y-%m-%d %H:%M')} — {summary.range_end.strftime('%Y-%m-%d %H:%M')} UTC",
        styles["Normal"],
    ))
    story.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC", styles["Normal"]))
    story.append(Spacer(1, 16))

    def section(title: str, rows: list[list[str]], headers: list[str]) -> None:
        story.append(Paragraph(title, styles["Heading2"]))
        if not rows:
            story.append(Paragraph("No data for this period.", styles["Normal"]))
            story.append(Spacer(1, 12))
            return
        table_data = [headers] + rows
        table = Table(table_data, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2A41")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F5")]),
        ]))
        story.append(table)
        story.append(Spacer(1, 16))

    section("Summary", [
        ["Total Events", str(summary.total_events)],
        ["Total Alerts", str(summary.total_alerts)],
        ["Total Detections", str(summary.total_detections)],
        ["Storage Used", f"{summary.storage_used_bytes / 1024**3:.1f} GB / {summary.storage_total_bytes / 1024**3:.1f} GB"],
    ], ["Metric", "Value"])

    section("Events by Camera", [[c.label, str(c.count)] for c in summary.events_by_camera], ["Camera", "Events"])
    section("Alerts by Severity", [[c.label, str(c.count)] for c in summary.alerts_by_severity], ["Severity", "Count"])
    section("Detections by Object Type", [[c.label, str(c.count)] for c in summary.detections_by_object_type], ["Object Type", "Count"])
    section("Camera Status", [[c.label, str(c.count)] for c in summary.camera_status_summary], ["Status", "Cameras"])

    doc.build(story)
    return buffer.getvalue()
