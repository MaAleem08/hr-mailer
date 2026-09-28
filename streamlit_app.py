import streamlit as st
import pandas as pd
import os
from mailer import send_campaign_emails

st.set_page_config(page_title='Bulk HR Email Sender', layout='centered')
st.title('Bulk HR Email Sender ??')
st.markdown('### Streamlined outreach without middlemen or spam')

uploaded_file = st.file_uploader('1. Upload Contact List (CSV or Excel)', type=['csv', 'xlsx'])
if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'): df = pd.read_csv(uploaded_file)
        else: df = pd.read_excel(uploaded_file)
        st.success(f'Loaded {len(df)} contacts!')
    except Exception as e: st.error(f'Error reading file: {e}')

resume_file = st.file_uploader('2. Upload Your Resume (PDF)', type=['pdf'])
if resume_file: st.success(f'? Resume loaded: {resume_file.name}')

sender = st.text_input('Your Gmail Address', placeholder='example@gmail.com')
password = st.text_input('Gmail App Password', type='password', placeholder='16-character token')
subject = st.text_input('Email Subject Line')
body = st.text_area('Email Body Template (Use {{first_name}} placeholders)')

if st.button('START SENDING'):
    if not (uploaded_file and sender and password and subject and body):
        st.warning('Please complete all form fields and upload your contact file first.')
    else:
        st.info('Starting email dispatch loop...')
        try:
            send_campaign_emails(1, sender, password, subject, body, df, resume_file)
            st.success('?? Campaign finished successfully! All emails sent.')
        except Exception as e: st.error(f'Execution halted: {e}')
