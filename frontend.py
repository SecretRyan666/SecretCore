import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

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
            st.success("Logged out")
            st.rerun()

        st.markdown("---")
        st.subheader("🔑 Change Password")
        new_pw = st.text_input("New Password", type="password")

        if st.button("Update Password"):
            response = requests.post(
                f"{API_URL}/change-password",
                headers=headers,
                params={"new_password": new_pw},
            )
            if response.status_code == 200:
                st.success("Password updated")
            else:
                st.error("Error updating password")

        if data["is_admin"]:
            st.markdown("---")
            st.markdown("### 👑 Admin Panel")

            pending = requests.get(f"{API_URL}/admin/pending", headers=headers)

            if pending.status_code == 200:
                users = pending.json()

                if users:
                    for user in users:
                        col1, col2 = st.columns([3,1])
                        col1.write(user["username"])
                        if col2.button("✅ Approve", key=user["username"]):
                            requests.post(
                                f"{API_URL}/admin/approve/{user['username']}",
                                headers=headers,
                            )
                            st.success(f"{user['username']} approved")
                            st.rerun()
                else:
                    st.write("No pending users.")