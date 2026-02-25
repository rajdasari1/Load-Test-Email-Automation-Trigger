import os
import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email_html(html_body: str, attachments: list[str] = None):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")

    email_from = os.getenv("EMAIL_FROM", smtp_username or "")
    email_to = [e.strip() for e in os.getenv("EMAIL_TO", "").split(",") if e.strip()]
    email_cc = [e.strip() for e in os.getenv("EMAIL_CC", "").split(",") if e.strip()]
    subject = os.getenv("EMAIL_SUBJECT", "Member Portal Load Test Summary")

    if not (smtp_server and smtp_username and smtp_password and email_to):
        raise RuntimeError("SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_TO are required.")

    msg = MIMEMultipart("mixed")
    msg["From"] = email_from
    msg["To"] = ", ".join(email_to)
    if email_cc:
        msg["Cc"] = ", ".join(email_cc)
    msg["Subject"] = subject

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("Please view this email in an HTML-capable client.", "plain"))
    alt.attach(MIMEText(html_body, "html"))
    msg.attach(alt)

    # Optional attachments
    attachments = attachments or []
    for path in attachments:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        # Infer mime subtype as octet-stream for generic files
        from email.mime.base import MIMEBase
        from email import encoders
        part = MIMEBase("application", "octet-stream")
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls(context=context)
        server.login(smtp_username, smtp_password)
        server.sendmail(email_from, email_to + email_cc, msg.as_string())

    print(f"Email sent to {email_to} (cc: {email_cc}).")
