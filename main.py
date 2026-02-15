전체코드로 주고 엑셀파일은 어디다 업로드해?

좋아 라이언 🔥
지금 두 가지를 정확히 정리해줄게.

1️⃣ 엑셀(CSV) 파일 어디에 업로드하냐?
2️⃣ main.py 전체 최종 통합 코드

✅ 먼저: CSV 파일 어디에 업로드하냐?

👉 서버에 미리 올리는 게 아니다.

📌 업로드 위치는 여기다:
Streamlit 웹앱 화면


주소:

https://appcore-aigqydsydpapbxcwwvhy4h.streamlit.app/


로그인 후 화면에:

📁 Upload Excel for Analysis


여기에서 파일 선택하면 된다.

⚠️ 중요한 것

파일 확장자: .csv

파일명: 시크릿데이타.csv

컬럼 구조 고정 (우리가 맞춘 구조)

서버에 따로 업로드할 필요 없다.
웹에서 업로드 → API로 전송 → 서버에서 분석.

🔥 이제 main.py 전체 최종 통합 코드

👉 이 코드로 main.py 전체 교체해.

import os
from datetime import datetime, timedelta
from io import StringIO

import pandas as pd
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import engine, SessionLocal
from models import Base, User, AnalysisRecord

SECRET_KEY = os.getenv("SECRET_KEY", "local_dev_secret_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

app = FastAPI()
Base.metadata.create_all(bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ================= DB =================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ================= PASSWORD =================
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# ================= JWT =================
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=15)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)):

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    return user

# ================= SECRET ENGINE =================

def create_key(row):
    return f"{row['유형']}|{row['일반구분']}|{row['핸디구분']}|{row['정역']}|{row['홈원정']}"

def generate_bar(percent):
    filled = int(percent / 5)
    return "█" * filled + "-" * (20 - filled)

def secret_engine(df):

    df["KEY"] = df.apply(create_key, axis=1)

    results = []
    grouped = df.groupby("KEY")

    for key, group in grouped:

        total = len(group)
        win = (group["결과"] == "승").sum()
        draw = (group["결과"] == "무").sum()
        lose = (group["결과"] == "패").sum()

        win_p = round(win / total * 100, 2)
        draw_p = round(draw / total * 100, 2)
        lose_p = round(lose / total * 100, 2)

        sample = group.iloc[0]
        signal = None

        if (
            sample["일반구분"] == "A"
            and sample["정역"] == "역"
            and sample["홈원정"] == "홈"
            and sample["핸디구분"] in ["B", "C"]
        ):
            signal = "⚠ 핸디 붕괴 고위험"

        if (
            sample["일반구분"] == "A"
            and sample["정역"] == "정"
            and sample["핸디구분"] in ["D", "E-C", "G"]
        ):
            signal = "🎯 핸디무 시그널"

        results.append({
            "KEY": key,
            "total": total,
            "승": f"{generate_bar(win_p)} {win_p}% ({win})",
            "무": f"{generate_bar(draw_p)} {draw_p}% ({draw})",
            "패": f"{generate_bar(lose_p)} {lose_p}% ({lose})",
            "signal": signal
        })

    return results

# ================= ROUTES =================

@app.get("/")
def root():
    return {"message": "SecretCore Service Running"}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(),
          db: Session = Depends(get_db)):

    user = db.query(User).filter(
        User.username == form_data.username
    ).first()

    if not user or not verify_password(
        form_data.password, user.password
    ):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if not user.is_approved:
        raise HTTPException(status_code=403, detail="User not approved")

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/analyze")
def analyze_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    contents = file.file.read().decode("utf-8")
    df = pd.read_csv(StringIO(contents))

    engine_result = secret_engine(df)

    record = AnalysisRecord(
        filename=file.filename,
        total_rows=len(df),
        total_columns=len(df.columns),
        columns=", ".join(df.columns),
        owner=current_user
    )

    db.add(record)
    db.commit()

    return {
        "message": "Secret analysis complete",
        "group_count": len(engine_result),
        "analysis_preview": engine_result[:10]
    }