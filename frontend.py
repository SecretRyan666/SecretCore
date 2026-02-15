import streamlit as st
import requests

API_URL = "https://secretcore.onrender.com"

st.set_page_config(page_title="SecretCore", page_icon="🔐")
st.title("🔐 SecretCore Web App")

menu = ["Login", "Register"]
choice = st.sidebar.selectbox("Menu", menu)

# ================= REGISTER =================
if choice == "Register":
    st.subheader("Create Account")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Register"):
        response = requests.post(
            f"{API_URL}/register",
            params={"username": username, "password": password},
        )

        if response.status_code == 200:
            st.success("Registered. Wait for admin approval.")
        else:
            st.error(response.json().get("detail"))

# ================= LOGIN =================
if choice == "Login":
    st.subheader("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        response = requests.post(
            f"{API_URL}/login",
            data={"username": username, "password": password},
        )

        if response.status_code == 200:
            st.session_state.token = response.json()["access_token"]
            st.success("Login successful")
        else:
            st.error(response.json().get("detail"))

# ================= AUTHORIZED AREA =================
if "token" in st.session_state:

    headers = {"Authorization": f"Bearer {st.session_state.token}"}

    user_info = requests.get(f"{API_URL}/users/me", headers=headers)

    if user_info.status_code == 200:
        data = user_info.json()

        st.markdown("---")
        st.write("### 👤 User Info")
        st.write("Username:", data["username"])
        st.write("Admin:", data["is_admin"])

        if st.button("Logout"):
            del st.session_state.token
            st.rerun()

        # ================= FILE UPLOAD =================
        st.markdown("---")
        st.subheader("📁 Upload Excel for Analysis")

        uploaded_file = st.file_uploader("Choose Excel file", type=["xlsx"])

        if uploaded_file is not None:
            if st.button("Analyze"):
                files = {"file": uploaded_file.getvalue()}

                response = requests.post(
                    f"{API_URL}/analyze",
                    headers=headers,
                    files={"file": (uploaded_file.name, uploaded_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                )

                if response.status_code == 200:
                    st.success("Analysis completed and saved.")
                    st.json(response.json())
                else:
                    st.error(response.json().get("detail"))

        # ================= MY ANALYSES =================
        st.markdown("---")
        st.subheader("📜 My Analysis History")

        history = requests.get(f"{API_URL}/my-analyses", headers=headers)

        if history.status_code == 200:
            records = history.json()

            if records:
                for record in records:
                    st.write(
                        f"📄 {record['filename']} | Rows: {record['rows']} | "
                        f"Columns: {record['columns']} | Date: {record['created_at']}"
                    )
            else:
                st.write("No analysis history yet.")