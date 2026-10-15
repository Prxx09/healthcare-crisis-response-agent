from __future__ import annotations

import asyncio
import html
import logging
import re
import smtplib
from datetime import date, datetime, time, timezone
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .alert_service import generate_eligible_alerts
from .config import Settings
from .supabase_client import SupabaseRepository


logger = logging.getLogger(__name__)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
LEVEL_RANK = {"investigate": 1, "escalate": 2}
SOURCE_LABELS = {
    "lab_positives": "Lab positives",
    "pharmacy_demand": "Pharmacy demand",
    "visits": "Visits",
}


def normalize_emails(values: list[str]) -> list[str]:
    emails: list[str] = []
    for value in values:
        email = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError(f"Invalid email address: {value}")
        if email not in emails:
            emails.append(email)
    return emails


def resolve_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown timezone: {name}") from error


def next_scheduled_at(config: dict[str, Any], now: datetime | None = None) -> datetime | None:
    if not config.get("enabled"):
        return None
    zone = resolve_timezone(config["timezone"])
    local_now = (now or datetime.now(timezone.utc)).astimezone(zone)
    scheduled_time = time.fromisoformat(str(config["schedule_time"]))
    candidate = datetime.combine(local_now.date(), scheduled_time, zone)
    if candidate <= local_now:
        candidate = datetime.combine(local_now.date().fromordinal(local_now.date().toordinal() + 1), scheduled_time, zone)
    return candidate


def _build_email(alerts: list[dict[str, Any]], analysis_date: date, settings: Settings) -> tuple[str, str, str]:
    highest_level = max((alert["alert_level"] for alert in alerts), key=lambda level: LEVEL_RANK[level])
    subject = f"[{highest_level.upper()}] CrisisWatch threshold alert - {analysis_date.isoformat()}"
    formatted_date = analysis_date.strftime("%d %b %Y")
    ordered_alerts = sorted(
        alerts,
        key=lambda alert: (
            -LEVEL_RANK[alert["alert_level"]],
            alert["hospitals"]["name"],
            alert["conditions"]["name"],
        ),
    )
    alert_cards = []
    text_rows = []
    for alert in ordered_alerts:
        evidence = alert.get("evidence_summary", {})
        source_keys = evidence.get("supporting_sources", [])
        sources = ", ".join(SOURCE_LABELS.get(source, source.replace("_", " ").title()) for source in source_keys) or "Not recorded"
        hospital = alert["hospitals"]["name"]
        condition = alert["conditions"]["name"]
        level = alert["alert_level"]
        level_color = "#a43f2c" if level == "escalate" else "#a45119"
        level_background = "#fdebea" if level == "escalate" else "#fff0e5"
        signal_rows = []
        for signal in evidence.get("signals", []):
            source = SOURCE_LABELS.get(signal.get("signal_source", ""), str(signal.get("signal_source", "Signal")).replace("_", " ").title())
            change = float(signal.get("percent_change", 0))
            change_text = f"{change:+.1f}% vs baseline"
            signal_rows.append(
                '<tr>'
                f'<td style="padding:10px 0;border-top:1px solid #e8eef2;font-size:13px;color:#526779;">{html.escape(source)}</td>'
                f'<td align="right" style="padding:10px 0;border-top:1px solid #e8eef2;font-size:13px;"><strong style="color:#17324a;">{html.escape(str(signal.get("current_count", "—")))}</strong><span style="display:block;margin-top:2px;color:#718396;font-size:11px;">{html.escape(change_text)}</span></td>'
                '</tr>'
            )
        if not signal_rows:
            signal_rows.append(
                f'<tr><td colspan="2" style="padding:10px 0;border-top:1px solid #e8eef2;font-size:13px;color:#526779;">Supporting sources: {html.escape(sources)}</td></tr>'
            )
        alert_cards.append(
            f"""
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 14px;background:#ffffff;border:1px solid #dfe7ec;border-radius:9px;">
              <tr><td style="padding:20px 22px 12px;">
                <span style="display:inline-block;padding:5px 9px;border-radius:13px;background:{level_background};color:{level_color};font-size:10px;font-weight:bold;letter-spacing:.6px;">{html.escape(level.upper())}</span>
                <h2 style="margin:12px 0 5px;font-size:18px;line-height:25px;color:#17324a;">{html.escape(condition)}</h2>
                <p style="margin:0;color:#65798b;font-size:13px;line-height:19px;">{html.escape(hospital)} &middot; Alert #{alert['id']}</p>
              </td></tr>
              <tr><td style="padding:0 22px 16px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr><td style="padding:8px 0;color:#718396;font-size:10px;font-weight:bold;letter-spacing:.6px;text-transform:uppercase;">Supporting signal</td><td align="right" style="padding:8px 0;color:#718396;font-size:10px;font-weight:bold;letter-spacing:.6px;text-transform:uppercase;">Activity</td></tr>
                  {''.join(signal_rows)}
                </table>
              </td></tr>
            </table>"""
        )
        text_rows.append(f"- {level.title()}: {condition} in {hospital}; supporting sources: {sources}")
    hospitals_affected = len({alert["hospitals"]["name"] for alert in alerts})
    conditions_affected = len({alert["conditions"]["name"] for alert in alerts})
    review_url = _page_url(settings, "/alert-review")
    safe_url = html.escape(review_url, quote=True)
    text_body = (
        "CRISISWATCH CONSOLIDATED THRESHOLD REPORT\n\n"
        f"CrisisWatch detected {len(alerts)} corroborated threshold alert(s) across all configured hospitals and conditions for {formatted_date}.\n\n"
        + "\n".join(text_rows)
        + f"\n\nReview the alerts: {review_url}\n\nHuman review is required before response actions are issued."
    )
    html_body = f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f2f6f8;font-family:Arial,Helvetica,sans-serif;color:#17324a;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f2f6f8;">
      <tr><td align="center" style="padding:32px 16px;">
        <table role="presentation" width="680" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:680px;background:#ffffff;border:1px solid #dce6ec;border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(20,43,65,.08);">
          <tr><td style="height:6px;background:#175c8f;font-size:0;line-height:0;">&nbsp;</td></tr>
          <tr><td style="padding:30px 34px 22px;">
            <span style="display:inline-block;padding:6px 10px;border-radius:14px;background:#e8f1f7;color:#175c8f;font-size:11px;font-weight:bold;letter-spacing:.7px;">CONSOLIDATED SURVEILLANCE REPORT</span>
            <h1 style="margin:16px 0 10px;font-size:27px;line-height:35px;color:#16324a;">CrisisWatch threshold alert</h1>
            <p style="margin:0;font-size:15px;line-height:23px;color:#526779;">Corroborated signals detected across the complete surveillance scope for <strong style="color:#16324a;">{html.escape(formatted_date)}</strong>. This report includes all configured hospitals and conditions and is independent of dashboard filters.</p>
          </td></tr>
          <tr><td style="padding:0 34px 24px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f6f9fb;border:1px solid #e0e8ed;border-radius:8px;">
              <tr>
                <td width="33.33%" align="center" style="padding:17px 8px;border-right:1px solid #e0e8ed;"><div style="font-size:24px;font-weight:bold;color:#17324a;">{len(alerts)}</div><div style="margin-top:4px;font-size:10px;color:#718396;text-transform:uppercase;letter-spacing:.5px;">Threshold alerts</div></td>
                <td width="33.33%" align="center" style="padding:17px 8px;border-right:1px solid #e0e8ed;"><div style="font-size:24px;font-weight:bold;color:#17324a;">{hospitals_affected}</div><div style="margin-top:4px;font-size:10px;color:#718396;text-transform:uppercase;letter-spacing:.5px;">Hospitals affected</div></td>
                <td width="33.33%" align="center" style="padding:17px 8px;"><div style="font-size:24px;font-weight:bold;color:#17324a;">{conditions_affected}</div><div style="margin-top:4px;font-size:10px;color:#718396;text-transform:uppercase;letter-spacing:.5px;">Conditions affected</div></td>
              </tr>
            </table>
          </td></tr>
          <tr><td style="padding:0 34px 12px;"><div style="font-size:11px;font-weight:bold;letter-spacing:.7px;color:#63798b;text-transform:uppercase;">Alert details</div></td></tr>
          <tr><td style="padding:0 34px 14px;background:#f8fafb;">{''.join(alert_cards)}</td></tr>
          <tr><td align="center" style="padding:12px 34px 30px;background:#f8fafb;">
            <a href="{safe_url}" style="display:inline-block;background:#175c8f;color:#ffffff;text-decoration:none;font-size:15px;font-weight:bold;padding:13px 22px;border-radius:7px;">Open alert review</a>
          </td></tr>
          <tr><td style="padding:18px 34px;background:#f3f6f8;border-top:1px solid #e3eaee;text-align:center;color:#7a8997;font-size:11px;line-height:17px;">Scope: all configured hospitals and conditions.<br>Decision support only. Human review is required before response actions are issued.</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
    return subject, text_body, html_body


def _build_no_alert_email(analysis_date: date, settings: Settings) -> tuple[str, str, str]:
    formatted_date = analysis_date.strftime("%d %b %Y")
    safe_date = html.escape(formatted_date)
    dashboard_url = _page_url(settings, "/command-dashboard")
    safe_url = html.escape(dashboard_url, quote=True)
    subject = f"[CLEAR] CrisisWatch daily threshold status - {analysis_date.isoformat()}"
    text_body = (
        "CRISISWATCH DAILY STATUS\n\n"
        f"No monitored signals crossed the configured review threshold for {formatted_date}.\n\n"
        "Status: No threshold crossings detected\n"
        "Action required: No response action is required\n"
        "Monitoring: Surveillance continues on the configured schedule\n\n"
        f"Open the surveillance dashboard: {dashboard_url}\n\n"
        "This is an automated operational status notification from CrisisWatch."
    )
    html_body = f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f2f6f8;font-family:Arial,Helvetica,sans-serif;color:#17324a;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f2f6f8;">
      <tr><td align="center" style="padding:32px 16px;">
        <table role="presentation" width="640" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:640px;background:#ffffff;border:1px solid #dce6ec;border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(20,43,65,.08);">
          <tr><td style="height:6px;background:#287766;font-size:0;line-height:0;">&nbsp;</td></tr>
          <tr><td style="padding:30px 34px 20px;">
            <span style="display:inline-block;padding:6px 10px;border-radius:14px;background:#e7f5f1;color:#246f61;font-size:11px;font-weight:bold;letter-spacing:.7px;">DAILY STATUS</span>
            <h1 style="margin:16px 0 10px;font-size:26px;line-height:34px;color:#16324a;">No threshold crossings detected</h1>
            <p style="margin:0;font-size:15px;line-height:23px;color:#526779;">CrisisWatch completed its scheduled review for <strong style="color:#16324a;">{safe_date}</strong>. Across all configured hospitals and conditions, no monitored signals crossed the configured review threshold.</p>
          </td></tr>
          <tr><td style="padding:0 34px 22px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f1f8f5;border:1px solid #cfe5dc;border-radius:8px;">
              <tr>
                <td width="54" align="center" valign="top" style="padding:20px 0 20px 18px;">
                  <span style="display:inline-block;width:34px;height:34px;line-height:34px;border-radius:17px;background:#287766;color:#ffffff;font-size:20px;font-weight:bold;text-align:center;">&#10003;</span>
                </td>
                <td style="padding:20px 20px 20px 14px;">
                  <div style="font-size:16px;font-weight:bold;line-height:23px;color:#1e6759;">No response action is required</div>
                  <div style="margin-top:4px;font-size:13px;line-height:20px;color:#58756d;">Routine surveillance remains active and will continue on the configured schedule.</div>
                </td>
              </tr>
            </table>
          </td></tr>
          <tr><td style="padding:0 34px 26px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e1e8ed;border-radius:8px;">
              <tr>
                <td width="50%" style="padding:15px 18px;border-right:1px solid #e8eef2;"><div style="font-size:11px;color:#748699;text-transform:uppercase;margin-bottom:5px;">Review date</div><div style="font-size:14px;font-weight:bold;">{safe_date}</div></td>
                <td width="50%" style="padding:15px 18px;"><div style="font-size:11px;color:#748699;text-transform:uppercase;margin-bottom:5px;">Status</div><div style="font-size:14px;font-weight:bold;color:#287766;">Clear</div></td>
              </tr>
            </table>
          </td></tr>
          <tr><td align="center" style="padding:0 34px 30px;">
            <a href="{safe_url}" style="display:inline-block;background:#175c8f;color:#ffffff;text-decoration:none;font-size:15px;font-weight:bold;padding:13px 22px;border-radius:7px;">Open surveillance dashboard</a>
          </td></tr>
          <tr><td style="padding:18px 34px;background:#f7f9fb;border-top:1px solid #e5ebef;text-align:center;color:#7a8997;font-size:11px;line-height:17px;">Scope: all configured hospitals and conditions.<br>Automated operational status from CrisisWatch. Human oversight remains required.</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
    return subject, text_body, html_body


def _send_smtp(
    settings: Settings,
    recipients: list[str],
    cc: list[str],
    subject: str,
    text_body: str,
    html_body: str,
) -> None:
    if not settings.smtp_configured:
        raise RuntimeError("SMTP is not configured on the API server")
    message = EmailMessage()
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email or ""))
    message["To"] = ", ".join(recipients)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    sender_domain = (settings.smtp_from_email or "").rsplit("@", 1)[-1]
    message["Message-ID"] = make_msgid(domain=sender_domain or None)
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as client:
        client.ehlo()
        if settings.smtp_use_tls:
            client.starttls()
            client.ehlo()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        refused = client.send_message(
            message,
            from_addr=settings.smtp_from_email,
            to_addrs=[*recipients, *cc],
        )
        if refused:
            rejected = ", ".join(sorted(refused))
            raise RuntimeError(f"SMTP rejected recipient(s): {rejected}")
        logger.info(
            "SMTP accepted message %s for %d recipient(s)",
            message["Message-ID"],
            len(recipients) + len(cc),
        )


def _format_due_at(value: str | None, timezone_name: str) -> str:
    if not value:
        return "Ongoing"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(resolve_timezone(timezone_name)).strftime("%d %b %Y, %I:%M %p %Z")
    except (ValueError, TypeError):
        return value


def _page_url(settings: Settings, path: str) -> str:
    return f"{settings.public_app_url.rstrip('/')}/{path.lstrip('/')}"


async def send_incident_review_notifications(
    repository: SupabaseRepository,
    settings: Settings,
    alerts: list[dict[str, Any]],
) -> dict[str, int]:
    config = await repository.get_email_alert_config()
    recipient = str(config.get("incident_master_email") or "").strip().lower()
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    for alert in alerts:
        evidence = alert.get("evidence_summary") or {}
        condition = str(evidence.get("condition") or "Unknown condition")
        hospital = str(evidence.get("hospital") or "Unknown hospital")
        level = str(alert.get("alert_level") or evidence.get("level") or "investigate")
        analysis_date = str(alert.get("analysis_date") or evidence.get("analysis_date") or "Not recorded")
        subject = f"CrisisWatch review required: {condition} in {hospital}"
        record = {
            "alert_id": alert["id"],
            "recipient": recipient or None,
            "subject": subject,
        }
        if not recipient:
            record.update({"status": "skipped", "error_message": "No Incident Commander email is configured"})
            await repository.create_incident_review_notification(record)
            counts["skipped"] += 1
            continue
        try:
            recipient = normalize_emails([recipient])[0]
            review_url = _page_url(settings, "/alert-review")
            sources = [
                SOURCE_LABELS.get(source, str(source).replace("_", " ").title())
                for source in evidence.get("supporting_sources", [])
            ]
            source_text = ", ".join(sources) or "Not recorded"
            signal_rows = []
            for signal in evidence.get("signals", []):
                source = SOURCE_LABELS.get(
                    signal.get("signal_source", ""),
                    str(signal.get("signal_source", "Signal")).replace("_", " ").title(),
                )
                change = float(signal.get("percent_change", 0))
                signal_rows.append(
                    '<tr>'
                    f'<td style="padding:10px 0;border-top:1px solid #e8eef2;font-size:13px;color:#526779;">{html.escape(source)}</td>'
                    f'<td align="right" style="padding:10px 0;border-top:1px solid #e8eef2;font-size:13px;"><strong style="color:#17324a;">{html.escape(str(signal.get("current_count", "—")))}</strong><span style="display:block;margin-top:2px;color:#718396;font-size:11px;">{change:+.1f}% vs baseline</span></td>'
                    '</tr>'
                )
            if not signal_rows:
                signal_rows.append(
                    f'<tr><td colspan="2" style="padding:10px 0;border-top:1px solid #e8eef2;font-size:13px;color:#526779;">{html.escape(source_text)}</td></tr>'
                )
            safe_condition = html.escape(condition)
            safe_hospital = html.escape(hospital)
            safe_level = html.escape(level.title())
            safe_analysis_date = html.escape(analysis_date)
            safe_review_url = html.escape(review_url, quote=True)
            text_body = (
                "CRISISWATCH ALERT REVIEW REQUIRED\n\n"
                "A corroborated surveillance signal has been submitted for Incident Commander review.\n\n"
                f"Condition: {condition}\nHospital: {hospital}\nLevel: {level.title()}\n"
                f"Analysis date: {analysis_date}\nSupporting sources: {source_text}\nAlert: #{alert['id']}\n\n"
                f"Open alert review: {review_url}\n\n"
                "No response task is issued until an Incident Commander records a decision."
            )
            html_body = f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f2f6f8;font-family:Arial,Helvetica,sans-serif;color:#17324a;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f2f6f8;">
      <tr><td align="center" style="padding:32px 16px;">
        <table role="presentation" width="640" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:640px;background:#ffffff;border:1px solid #dce6ec;border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(20,43,65,.08);">
          <tr><td style="height:6px;background:#d67632;font-size:0;line-height:0;">&nbsp;</td></tr>
          <tr><td style="padding:30px 34px 20px;">
            <span style="display:inline-block;padding:6px 10px;border-radius:14px;background:#fff0e5;color:#a45119;font-size:11px;font-weight:bold;letter-spacing:.7px;">REVIEW REQUIRED</span>
            <h1 style="margin:16px 0 10px;font-size:26px;line-height:34px;color:#16324a;">New surveillance alert awaiting review</h1>
            <p style="margin:0;font-size:15px;line-height:23px;color:#526779;">A corroborated signal has been submitted for Incident Commander review. No response task has been issued.</p>
          </td></tr>
          <tr><td style="padding:0 34px 20px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#fff8f2;border-left:4px solid #d67632;border-radius:8px;">
              <tr><td style="padding:18px 20px;">
                <div style="font-size:11px;font-weight:bold;letter-spacing:.7px;color:#7d6b5d;margin-bottom:7px;">{safe_level.upper()} &middot; ALERT #{alert['id']}</div>
                <div style="font-size:19px;font-weight:bold;line-height:26px;color:#16324a;">{safe_condition}</div>
                <div style="margin-top:4px;font-size:14px;color:#65798b;">{safe_hospital}</div>
              </td></tr>
            </table>
          </td></tr>
          <tr><td style="padding:0 34px 20px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e1e8ed;border-radius:8px;">
              <tr>
                <td width="50%" style="padding:15px 18px;border-right:1px solid #e8eef2;"><div style="font-size:11px;color:#748699;text-transform:uppercase;margin-bottom:5px;">Analysis date</div><div style="font-size:14px;font-weight:bold;">{safe_analysis_date}</div></td>
                <td width="50%" style="padding:15px 18px;"><div style="font-size:11px;color:#748699;text-transform:uppercase;margin-bottom:5px;">Supporting sources</div><div style="font-size:14px;font-weight:bold;">{len(sources)}</div></td>
              </tr>
            </table>
          </td></tr>
          <tr><td style="padding:0 34px 24px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
              <tr><td style="padding:8px 0;color:#718396;font-size:10px;font-weight:bold;letter-spacing:.6px;text-transform:uppercase;">Supporting signal</td><td align="right" style="padding:8px 0;color:#718396;font-size:10px;font-weight:bold;letter-spacing:.6px;text-transform:uppercase;">Activity</td></tr>
              {''.join(signal_rows)}
            </table>
          </td></tr>
          <tr><td align="center" style="padding:0 34px 30px;">
            <a href="{safe_review_url}" style="display:inline-block;background:#175c8f;color:#ffffff;text-decoration:none;font-size:15px;font-weight:bold;padding:13px 22px;border-radius:7px;">Open alert review</a>
          </td></tr>
          <tr><td style="padding:18px 34px;background:#f7f9fb;border-top:1px solid #e5ebef;text-align:center;color:#7a8997;font-size:11px;line-height:17px;">Decision support only.<br>An Incident Commander must approve or dismiss this alert.</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
            await asyncio.to_thread(_send_smtp, settings, [recipient], [], subject, text_body, html_body)
            record.update({"recipient": recipient, "status": "success", "error_message": None})
            counts["sent"] += 1
        except Exception as error:
            logger.exception("Incident review notification failed for alert %s", alert["id"])
            record.update({"status": "failed", "error_message": str(error)[:500]})
            counts["failed"] += 1
        await repository.create_incident_review_notification(record)
    return counts


async def run_email_alert(
    repository: SupabaseRepository,
    settings: Settings,
    trigger_mode: str,
    analysis_date: date | None = None,
    schedule_date: date | None = None,
) -> dict[str, Any]:
    config = await repository.get_email_alert_config()
    recipients = normalize_emails(config.get("recipients") or [])
    cc = normalize_emails(config.get("cc") or [])
    if not recipients:
        raise ValueError("Add at least one recipient before sending email alerts")
    if analysis_date is None:
        latest = await repository.get_latest_observation_date()
        if not latest:
            raise ValueError("No surveillance observations are available")
        analysis_date = date.fromisoformat(latest)

    # Email reports always evaluate the complete surveillance scope. Dashboard
    # hospital and condition filters are intentionally not accepted here.
    await generate_eligible_alerts(
        repository,
        analysis_date,
        hospital_code=None,
        condition_code=None,
    )
    alerts = await repository.get_alerts_for_date(analysis_date.isoformat())
    minimum_rank = LEVEL_RANK[config["minimum_level"]]
    alerts = [alert for alert in alerts if LEVEL_RANK[alert["alert_level"]] >= minimum_rank]
    delivery = {
        "trigger_mode": trigger_mode,
        "analysis_date": analysis_date.isoformat(),
        "schedule_date": schedule_date.isoformat() if schedule_date else None,
        "recipients": recipients,
        "cc": cc,
        "alert_ids": [alert["id"] for alert in alerts],
    }
    if alerts:
        subject, text_body, html_body = _build_email(alerts, analysis_date, settings)
    else:
        subject, text_body, html_body = _build_no_alert_email(analysis_date, settings)
    delivery["subject"] = subject
    try:
        await asyncio.to_thread(_send_smtp, settings, recipients, cc, subject, text_body, html_body)
        delivery.update({"status": "success", "error_message": None})
    except Exception as error:
        logger.exception("Email alert delivery failed")
        delivery.update({"status": "failed", "error_message": str(error)[:500]})
    saved = await repository.create_email_alert_delivery(delivery)
    if delivery["status"] == "failed":
        raise RuntimeError(delivery["error_message"])
    return {"status": "success", "alerts_sent": len(alerts), "delivery": saved}


async def send_task_owner_notifications(
    repository: SupabaseRepository,
    settings: Settings,
    alert: dict[str, Any],
    actions: list[dict[str, Any]],
) -> dict[str, int]:
    config = await repository.get_email_alert_config()
    configured = config.get("owner_emails") or {}
    owner_emails = {str(role).casefold(): str(email) for role, email in configured.items()}
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    for action in actions:
        owner_role = action["owner_role"]
        recipient = owner_emails.get(owner_role.casefold(), "").strip().lower()
        subject = f"CrisisWatch task assigned: {action['action_text']}"
        record = {
            "alert_id": alert["id"],
            "action_id": action["id"],
            "owner_role": owner_role,
            "recipient": recipient or None,
            "subject": subject,
        }
        if not recipient:
            record.update({"status": "skipped", "error_message": "No owner email is configured"})
            await repository.create_task_owner_notification(record)
            counts["skipped"] += 1
            continue
        try:
            recipient = normalize_emails([recipient])[0]
            hospital = alert["hospitals"]["name"]
            condition = alert["conditions"]["name"]
            due = _format_due_at(action.get("due_at"), config.get("timezone") or "UTC")
            text_body = (
                "NEW CRISISWATCH RESPONSE TASK\n\n"
                f"A response task has been assigned to {owner_role} following Incident Commander approval.\n\n"
                f"TASK\n{action['action_text']}\n\n"
                f"Condition: {condition}\nHospital: {hospital}\nOwner: {owner_role}\n"
                f"Timeframe: {action['timeframe']}\nDue: {due}\nAlert: #{alert['id']}\n\n"
                f"Open the action tracker: {_page_url(settings, '/action-tracker')}\n\n"
                "This is an operational notification from CrisisWatch."
            )
            safe_owner = html.escape(owner_role)
            safe_task = html.escape(action["action_text"])
            safe_condition = html.escape(condition)
            safe_hospital = html.escape(hospital)
            safe_timeframe = html.escape(action["timeframe"])
            safe_due = html.escape(due)
            safe_url = html.escape(_page_url(settings, "/action-tracker"), quote=True)
            html_body = f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f2f6f8;font-family:Arial,Helvetica,sans-serif;color:#17324a;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f2f6f8;">
      <tr><td align="center" style="padding:32px 16px;">
        <table role="presentation" width="640" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:640px;background:#ffffff;border:1px solid #dce6ec;border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(20,43,65,.08);">
          <tr><td style="height:6px;background:#287766;font-size:0;line-height:0;">&nbsp;</td></tr>
          <tr><td style="padding:30px 34px 20px;">
            <span style="display:inline-block;padding:6px 10px;border-radius:14px;background:#e7f5f1;color:#246f61;font-size:11px;font-weight:bold;letter-spacing:.7px;">NEW RESPONSE TASK</span>
            <h1 style="margin:16px 0 10px;font-size:26px;line-height:34px;color:#16324a;">CrisisWatch task assignment</h1>
            <p style="margin:0;font-size:15px;line-height:23px;color:#526779;">A response task has been assigned to <strong style="color:#16324a;">{safe_owner}</strong> following Incident Commander approval.</p>
          </td></tr>
          <tr><td style="padding:0 34px 20px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f3f8fa;border-left:4px solid #287766;border-radius:8px;">
              <tr><td style="padding:18px 20px;">
                <div style="font-size:11px;font-weight:bold;letter-spacing:.7px;color:#63798b;margin-bottom:7px;">TASK</div>
                <div style="font-size:18px;font-weight:bold;line-height:26px;color:#16324a;">{safe_task}</div>
              </td></tr>
            </table>
          </td></tr>
          <tr><td style="padding:0 34px 26px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e1e8ed;border-radius:8px;">
              <tr>
                <td width="50%" style="padding:15px 18px;border-bottom:1px solid #e8eef2;border-right:1px solid #e8eef2;"><div style="font-size:11px;color:#748699;text-transform:uppercase;margin-bottom:5px;">Condition</div><div style="font-size:14px;font-weight:bold;">{safe_condition}</div></td>
                <td width="50%" style="padding:15px 18px;border-bottom:1px solid #e8eef2;"><div style="font-size:11px;color:#748699;text-transform:uppercase;margin-bottom:5px;">Hospital</div><div style="font-size:14px;font-weight:bold;">{safe_hospital}</div></td>
              </tr>
              <tr>
                <td width="50%" style="padding:15px 18px;border-bottom:1px solid #e8eef2;border-right:1px solid #e8eef2;"><div style="font-size:11px;color:#748699;text-transform:uppercase;margin-bottom:5px;">Owner</div><div style="font-size:14px;font-weight:bold;">{safe_owner}</div></td>
                <td width="50%" style="padding:15px 18px;border-bottom:1px solid #e8eef2;"><div style="font-size:11px;color:#748699;text-transform:uppercase;margin-bottom:5px;">Alert</div><div style="font-size:14px;font-weight:bold;">#{alert['id']}</div></td>
              </tr>
              <tr>
                <td width="50%" style="padding:15px 18px;border-right:1px solid #e8eef2;"><div style="font-size:11px;color:#748699;text-transform:uppercase;margin-bottom:5px;">Timeframe</div><div style="font-size:14px;font-weight:bold;">{safe_timeframe}</div></td>
                <td width="50%" style="padding:15px 18px;"><div style="font-size:11px;color:#748699;text-transform:uppercase;margin-bottom:5px;">Due</div><div style="font-size:14px;font-weight:bold;">{safe_due}</div></td>
              </tr>
            </table>
          </td></tr>
          <tr><td align="center" style="padding:0 34px 30px;">
            <a href="{safe_url}" style="display:inline-block;background:#175c8f;color:#ffffff;text-decoration:none;font-size:15px;font-weight:bold;padding:13px 22px;border-radius:7px;">Open action tracker</a>
          </td></tr>
          <tr><td style="padding:18px 34px;background:#f7f9fb;border-top:1px solid #e5ebef;text-align:center;color:#7a8997;font-size:11px;line-height:17px;">This is an operational notification from CrisisWatch.<br>Human oversight remains required for response decisions.</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
            await asyncio.to_thread(_send_smtp, settings, [recipient], [], subject, text_body, html_body)
            record.update({"recipient": recipient, "status": "success", "error_message": None})
            counts["sent"] += 1
        except Exception as error:
            logger.exception("Task owner notification failed for action %s", action["id"])
            record.update({"status": "failed", "error_message": str(error)[:500]})
            counts["failed"] += 1
        await repository.create_task_owner_notification(record)
    return counts


class EmailAlertScheduler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self._run_if_due()
            except Exception:
                logger.exception("Scheduled email alert check failed")
            await asyncio.sleep(max(10, self.settings.email_scheduler_poll_seconds))

    async def _run_if_due(self) -> None:
        repository = SupabaseRepository()
        config = await repository.get_email_alert_config()
        if not config.get("enabled"):
            return
        zone = resolve_timezone(config["timezone"])
        local_now = datetime.now(timezone.utc).astimezone(zone)
        scheduled_time = time.fromisoformat(str(config["schedule_time"]))
        if local_now.time().replace(tzinfo=None) < scheduled_time:
            return
        if await repository.get_scheduled_email_delivery(local_now.date().isoformat()):
            return
        await run_email_alert(repository, self.settings, "scheduled", schedule_date=local_now.date())
