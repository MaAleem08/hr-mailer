import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

def send_campaign_emails(campaign_id, sender_email, password, subject_template, body_template, df, attachment_path=None):
    try:
        server = smtplib.SMTP('://gmail.com', 587)
        server.starttls()
        server.login(sender_email, password)
    except Exception as e:
        raise Exception(f'Failed to connect to Gmail: {e}')

    for index, row in df.iterrows():
        email = row.get('HR EMAIL', row.get('Email'))
        if not email: continue
        subject = subject_template
        body = body_template
        for col in df.columns:
            placeholder = f'{{{{{col}}}}}'
            if placeholder in subject: subject = subject.replace(placeholder, str(row[col]))
            if placeholder in body: body = body.replace(placeholder, str(row[col]))
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        try:
            server.sendmail(sender_email, email, msg.as_string())
        except Exception:
            pass
    server.quit()
