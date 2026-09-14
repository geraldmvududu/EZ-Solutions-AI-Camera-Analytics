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
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.event import Event
from app.models.face_recognition_event import FaceRecognitionEvent
from app.schemas.analytics import AnalyticsSummary, NamedCount


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


def face_appearances_to_csv(appearances: list[FaceRecognitionEvent]) -> str:
    """A person's real appearance history (section 6/23) — one row per actual
    recognition attempt against them, including which recording (if any) captured it,
    so the CSV itself is enough to locate the evidence, not just a text log."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Event ID", "Camera ID", "Status", "Confidence", "Timestamp", "Recording ID", "Snapshot ID", "Reviewed", "Review Decision"])
    for a in appearances:
        writer.writerow([
            str(a.id), str(a.camera_id), a.recognition_status.value, f"{a.confidence_score:.2f}",
            a.event_timestamp.isoformat(), str(a.recording_id) if a.recording_id else "",
            str(a.snapshot_id) if a.snapshot_id else "", a.reviewed, a.review_decision,
        ])
    return buffer.getvalue()


def build_security_report_pdf(
    summary: AnalyticsSummary,
    tenant_name: str,
    face_recognition_by_status: list[NamedCount] | None = None,
    top_recognized_people: list[NamedCount] | None = None,
    video_intelligence_incidents: list[NamedCount] | None = None,
) -> bytes:
    """The face-recognition params are optional and independent of everything else
    here: the caller (app/api/routes/reports.py) only passes them when the requesting
    user actually has view_biometric_events, so a viewer without that permission gets
    a complete report minus that section rather than a 403 on the whole PDF. None
    skips a section entirely; an empty list still renders it with a real "No data for
    this period." message, same as every other section here.
    video_intelligence_incidents has no such gate — Incidents are already visible to
    anyone who can view this report."""
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

    if face_recognition_by_status is not None:
        section("Face Recognition Activity", [[c.label, str(c.count)] for c in face_recognition_by_status], ["Status", "Count"])
    if top_recognized_people is not None:
        section("Top Recognized People", [[c.label, str(c.count)] for c in top_recognized_people], ["Person", "Appearances"])
    if video_intelligence_incidents is not None:
        section(
            "AI Video Intelligence Incidents",
            [[c.label.replace("_", " "), str(c.count)] for c in video_intelligence_incidents],
            ["Category", "Count"],
        )

    doc.build(story)
    return buffer.getvalue()


def build_event_detail_pdf(event: Event, camera_name: str, snapshot_image_bytes: bytes | None = None) -> bytes:
    """A single event's full detail as a standalone PDF (section: per-event export) —
    the same fields the Events page's detail modal already shows (type/severity/
    category/review status/description/raw metadata/snapshot image), not a second,
    differently-worded summary of it. No prose "explanation" here — that's presentation-
    layer text (frontend's explainEvent.ts); this is the underlying real data it's
    built from.

    snapshot_image_bytes is the caller's job to fetch (app/api/routes/reports.py reads
    it from local disk or, for a cloud-uploaded snapshot, via
    object_storage.download_object — see that route for why a presigned-redirect,
    the pattern every other snapshot-serving endpoint uses, doesn't work here: there's
    no browser on this end to follow it). None (no snapshot on the event, or the file/
    object couldn't be read) renders a plain "not available" line instead of silently
    omitting the section."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("EZ Solutions AI Camera Analytics — Event Report", styles["Title"]))
    story.append(Paragraph(event.event_type.value.replace("_", " ").title(), styles["Normal"]))
    story.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC", styles["Normal"]))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Event Snapshot", styles["Heading2"]))
    if snapshot_image_bytes:
        # ImageReader just to measure the real dimensions for aspect-ratio scaling —
        # the Image flowable itself needs its OWN, unconsumed file-like object (it
        # checks hasattr(x, "read"), which ImageReader doesn't satisfy, so passing the
        # same reader here raises a TypeError deep in reportlab's own __init__).
        img_width, img_height = ImageReader(io.BytesIO(snapshot_image_bytes)).getSize()
        max_width, max_height = 4.5 * inch, 3.375 * inch
        scale = min(max_width / img_width, max_height / img_height, 1.0)
        story.append(RLImage(io.BytesIO(snapshot_image_bytes), width=img_width * scale, height=img_height * scale))
    else:
        story.append(Paragraph("No snapshot image is available for this event.", styles["Normal"]))
    story.append(Spacer(1, 16))

    def table(rows: list[list[str]]) -> None:
        t = Table(rows, hAlign="LEFT", colWidths=[1.6 * inch, 4.4 * inch])
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F4F6F5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 16))

    table([
        ["Event ID", str(event.id)],
        ["Camera", camera_name],
        ["Type", event.event_type.value],
        ["Category", event.event_category.value],
        ["Severity", event.severity.value],
        ["Occurred At", event.occurred_at.strftime("%Y-%m-%d %H:%M:%S UTC")],
        ["Review Status", event.status.value],
        ["Reviewed At", event.reviewed_at.strftime("%Y-%m-%d %H:%M:%S UTC") if event.reviewed_at else "—"],
    ])

    if event.description:
        story.append(Paragraph("Description", styles["Heading2"]))
        story.append(Paragraph(event.description, styles["Normal"]))
        story.append(Spacer(1, 16))

    if event.notes:
        story.append(Paragraph("Investigation Notes", styles["Heading2"]))
        story.append(Paragraph(event.notes, styles["Normal"]))
        story.append(Spacer(1, 16))

    metadata_rows = [[k, str(v)] for k, v in (event.event_metadata or {}).items() if v is not None]
    story.append(Paragraph("Detection Data", styles["Heading2"]))
    if metadata_rows:
        table(metadata_rows)
    else:
        story.append(Paragraph("No additional detection data for this event.", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
