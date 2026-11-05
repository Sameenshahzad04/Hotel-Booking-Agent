
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import config

logger = logging.getLogger("pc_agent.email")

def send_smtp_email(to_email: str, subject: str, body_text: str) -> bool:
    """
    Sends an email using standard smtplib with STARTTLS.
    Falls back to a console log mock if SMTP credentials are missing.
    """
    if not getattr(config, "SMTP_USER", None) or not getattr(config, "SMTP_PASSWORD", None):
        logger.info(
            "ℹ️ [SMTP MOCK / LOCAL DEV] SMTP credentials not set in config. Email logged to console:\n"
            "--------------------------------------------------\n"
            "TO: %s\nSUBJECT: %s\nBODY:\n%s\n"
            "--------------------------------------------------",
            to_email, subject, body_text
        )
        return True

    try:
        msg = MIMEMultipart("alternative")
        from_email = getattr(config, "SMTP_FROM_EMAIL", config.SMTP_USER)
        from_name = getattr(config, "SMTP_FROM_NAME", "Pearl Continental Hotel Lahore")
        
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        host = getattr(config, "SMTP_HOST", "smtp.gmail.com")
        port = getattr(config, "SMTP_PORT", 587)

        server = smtplib.SMTP(host, port, timeout=10)
        server.ehlo()
        if port == 587:
            server.starttls()
            server.ehlo()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()
        
        logger.info("✅ SMTP email successfully delivered to %s", to_email)
        return True
    except Exception as e:
        logger.error("❌ Failed to send SMTP email to %s: %s", to_email, str(e))
        return False
