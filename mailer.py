import os
import requests
import base64

def send_campaign_emails(campaign_id, sender_email, password, subject_template, body_template, df, resume_file=None):
    # The application form will now take the Resend API Key inside the 'password' box
    api_key = password
    url = 'https://resend.com'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    attachments = []
    if resume_file is not None:
        resume_file.seek(0)
        encoded_content = base64.b64encode(resume_file.read()).decode('utf-8')
        attachments.append({
            'content': encoded_content,
            'filename': resume_file.name
        })

    for index, row in df.iterrows():
        email = row.get('HR EMAIL', row.get('Email'))
        if not email: continue
        subject = subject_template
        body = body_template
        for col in df.columns:
            placeholder = f'{{{{{col}}}}}'
            if placeholder in subject: subject = subject.replace(placeholder, str(row[col]))
            if placeholder in body: body = body.replace(placeholder, str(row[col]))
        
        payload = {
            'from': 'HR Mailer <onboarding@resend.dev>',
            'to': [email],
            'subject': subject,
            'text': body
        }
        if attachments: payload['attachments'] = attachments
        
        try:
            res = requests.post(url, json=payload, headers=headers)
            if res.status_code >= 400:
                raise Exception(f'API error: {res.text}')
        except Exception as e:
            raise Exception(f'Network failed: {str(e)}')
