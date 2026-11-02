import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from config import config

logger = logging.getLogger("pc_agent.email")

def send_smtp_email(to_email: str, subject: str, body_text: str) -> bool:
    """
    Sends an email using standard smtplib with STARTTLS.
    100% Free: Works with Gmail App Password or any free SMTP provider.
    If SMTP credentials are not configured or fail, logs the email content to stdout
    so local testing always works without blocking the user!
    """
    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        logger.info(
            "ℹ️ [SMTP MOCK / LOCAL DEV] SMTP credentials not set in .env. Email logged to console:\n"
            "--------------------------------------------------\n"
            "TO: %s\nSUBJECT: %s\nBODY:\n%s\n"
            "--------------------------------------------------",
            to_email, subject, body_text
        )
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{config.SMTP_FROM_NAME} <{config.SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10)
        server.ehlo()
        if config.SMTP_PORT == 587:
            server.starttls()
            server.ehlo()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.sendmail(config.SMTP_FROM_EMAIL, [to_email], msg.as_string())
        server.quit()
        logger.info("✅ SMTP email successfully delivered to %s", to_email)
        return True
    except Exception as e:
        logger.error("❌ Failed to send SMTP email to %s: %s", to_email, str(e))
        return False
