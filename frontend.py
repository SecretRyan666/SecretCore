import streamlit as st
import requests

API_URL = "https://secretcore.onrender.com"

st.set_page_config(page_title="SecretCore", page_icon="🔐")
st.title("🔐 SecretCore Web App")

# =========================
# SESSION INIT
# =========================
if "token" not in st.session_state:
    st.session_state.token = None

# =========================
# SIDEBAR MENU
# =========================
menu = ["Login", "Register"]
choice = st.sidebar.selectbox("Menu", menu)

# =========================
# REGISTER
# =========================
if choice == "Register":

    st.subheader("Create Account")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Register"):

        response = requests.post(
            f"{API_URL}/register",
            params={"username": username, "password": password},
        )

        st.write("Status:", response.status_code)
        st.write("Response:", response.text)

        if response.status_code == 200:
            st.success("Registered. Admin approval required.")
        else:
            st.error("Registration failed")

# =========================
# LOGIN
# =========================
if choice == "Login":

    st.subheader("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):

        response = requests.post(
            f"{API_URL}/login",
            data={"username": username, "password": password},
        )

        st.write("Status:", response.status_code)
        st.write("Response:", response.text)

        if response.status_code == 200:
            st.session_state.token = response.json()["access_token"]
            st.success("Login successful")
        else:
            st.error("Login failed")

# =========================
# AUTHORIZED AREA
# =========================
if st.session_state.token:

    headers = {"Authorization": f"Bearer {st.session_state.token}"}

    st.markdown("---")
    st.subheader("📁 Upload CSV or Excel")

    uploaded_file = st.file_uploader(
        "Choose file",
        type=["csv", "xlsx", "xls"]
    )

    if uploaded_file is not None:

        if st.button("Analyze"):

            st.write("Analyze button clicked")

            response = requests.post(
                f"{API_URL}/analyze",
                headers=headers,
                files={
                    "file": (
                        uploaded_file.name,
                        uploaded_file,
                        uploaded_file.type
                    )
                }
            )

            st.write("Status Code:", response.status_code)
            st.write("Raw Response:", response.text)

            if response.status_code == 200:
                st.success("Analysis completed")
                st.json(response.json())
            else:
                st.error("Analysis failed")

    # =========================
    # HISTORY
    # =========================
    st.markdown("---")
    st.subheader("📜 My Analysis History")

    history = requests.get(
        f"{API_URL}/my-analyses",
        headers=headers
    )

    st.write("History Status:", history.status_code)

    if history.status_code == 200:
        records = history.json()
        if records:
            for r in records:
                st.write(
                    f"{r['filename']} | "
                    f"Rows: {r['rows']} | "
                    f"Columns: {r['columns']} | "
                    f"Date: {r['created_at']}"
                )
        else:
            st.write("No history yet.")
    else:
        st.error("History load failed")

# =========================
# LOGOUT
# =========================
if st.session_state.token:
    if st.sidebar.button("Logout"):
        st.session_state.token = None
        st.success("Logged out")