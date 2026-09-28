import streamlit as st
import streamlit.components.v1 as components
import subprocess
time = __import__('time')

@st.cache_resource
def start_flask():
    proc = subprocess.Popen(["python", "app.py"])
    time.sleep(2)
    return proc

start_flask()
st.title("Bulk HR Email Sender ??")
components.iframe("http://127.0.0.1:5000", height=800, scrolling=True)
