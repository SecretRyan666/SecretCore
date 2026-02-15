좋아 라이언 👍
지금 상황 정확히 정리해보자.

👉 Streamlit 주소에서 테스트 중
👉 CSV는 업로드 자체가 안 됨
👉 Excel은 업로드는 되는데 “찾지를 못한다”는 에러

이건 프론트엔드(frontend.py)가 아직 CSV/XLSX 둘 다 지원하도록 수정되지 않았을 가능성이 거의 100%다.

지금 백엔드는 둘 다 지원하는데
프론트가 아직 type=["xlsx"]로만 제한돼 있을 가능성이 크다.

🔥 1️⃣ frontend.py 전체 교체 (CSV + Excel 지원)

Streamlit 쪽 frontend.py를 아래 코드로 통째로 교체해.

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

# ================= AUTHORIZED =================
if "token" in st.session_state:

    headers = {"Authorization": f"Bearer {st.session_state.token}"}

    st.markdown("---")
    st.subheader("📁 Upload CSV or Excel")

    uploaded_file = st.file_uploader(
        "Choose file",
        type=["csv", "xlsx", "xls"]
    )

    if uploaded_file is not None:
        if st.button("Analyze"):
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

            if response.status_code == 200:
                st.success("Analysis completed")
                st.json(response.json())
            else:
                st.error(response.text)

    st.markdown("---")
    st.subheader("📜 My Analysis History")

    history = requests.get(
        f"{API_URL}/my-analyses",
        headers=headers
    )

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