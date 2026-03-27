import streamlit as st

st.set_page_config(page_title="Hema Portal", page_icon="🐍", layout="centered")

st.title("Python portal")
st.write(
    "This sample app is containerized for **Docker**, **Artifact Registry**, "
    "**Cloud Run**, and **Cloud Build** CI/CD."
)
st.success("If you see this in the browser, the container is serving traffic correctly.")

if st.button("Ping"):
    st.balloons()
