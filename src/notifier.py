"""Email notifier — sends HTML job reports via SMTP."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Optional

from src.config import SmtpConfig

logger = logging.getLogger(__name__)


def send_email_report(
    smtp_config: SmtpConfig,
    html_content: str,
    match_count: int,
    report_filepath: Optional[str] = None,
) -> bool:
    """
    Send an HTML job report via email.

    Args:
        smtp_config: SMTP server configuration.
        html_content: The HTML report content.
        match_count: Number of matching jobs (used in subject).
        report_filepath: Optional path to attach the report file.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not smtp_config.server or not smtp_config.to_address:
        logger.info("[notifier] SMTP not configured. Skipping email.")
        return False

    try:
        # Build email
        msg = MIMEMultipart("alternative")
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        if match_count > 0:
            msg["Subject"] = f"🔥 {match_count} New Job Match{'es' if match_count != 1 else ''} — {now}"
        else:
            msg["Subject"] = f"📋 Job Search Report — No New Matches — {now}"

        msg["From"] = smtp_config.from_address or smtp_config.username
        msg["To"] = smtp_config.to_address

        # Plain text fallback
        text_part = MIMEText(
            f"Your job search found {match_count} new matches.\n"
            f"Open the HTML version to see the full report.",
            "plain",
        )
        msg.attach(text_part)

        # HTML body
        html_part = MIMEText(html_content, "html")
        msg.attach(html_part)

        # Optional attachment
        if report_filepath:
            try:
                with open(report_filepath, "rb") as f:
                    attachment = MIMEBase("application", "octet-stream")
                    attachment.set_payload(f.read())
                    encoders.encode_base64(attachment)
                    attachment.add_header(
                        "Content-Disposition",
                        f"attachment; filename=job_report_{now.replace(' ', '_').replace(':', '')}.html",
                    )
                    msg.attach(attachment)
            except Exception as e:
                logger.warning(f"[notifier] Failed to attach report file: {e}")

        # Send
        logger.info(f"[notifier] Sending email to {smtp_config.to_address}")

        if smtp_config.use_tls:
            server = smtplib.SMTP(smtp_config.server, smtp_config.port)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP(smtp_config.server, smtp_config.port)

        if smtp_config.username and smtp_config.password:
            server.login(smtp_config.username, smtp_config.password)

        server.sendmail(
            msg["From"],
            [smtp_config.to_address],
            msg.as_string(),
        )
        server.quit()

        logger.info("[notifier] Email sent successfully!")
        return True

    except Exception as e:
        logger.error(f"[notifier] Failed to send email: {e}", exc_info=True)
        return False
