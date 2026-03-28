import streamlit as st

st.set_page_config(page_title="GCP Web Portal", page_icon="🚀", layout="centered")

st.title("Live from GitHub → Cloud Build → Cloud Run")
st.write(
    "This sample app is containerized for **Docker**, **Artifact Registry**, "
    "**Cloud Run**, and **Cloud Build** CI/CD."
)
st.success("If this banner and the new title appear after a git push, CI/CD is working.")

if st.button("Ping"):
    st.balloons()
