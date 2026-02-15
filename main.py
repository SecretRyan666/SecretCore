import os
from datetime import datetime, timedelta
from io import StringIO, BytesIO

import pandas as pd
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import engine, SessionLocal
from models import Base, User, AnalysisRecord

# =========================
# 🔐 CONFIG
# =========================

SECRET_KEY = os.getenv("SECRET_KEY", "local_dev_secret_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

app = FastAPI()
Base.metadata.create_all(bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# =========================
# 🗄 DATABASE
# =========================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =========================
# 🔑 PASSWORD
# =========================

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# =========================
# 🔐 JWT
# =========================

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=15)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
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

# =========================
# 🧠 SECRET ENGINE
# =========================

def create_key(row):
    return f"{row['유형']}|{row['일반구분']}|{row['핸디구분']}|{row['정역']}|{row['홈원정']}"

def generate_bar(percent):
    filled = int(percent / 5)
    return "█" * filled + "-" * (20 - filled)

def secret_engine(df):

    required_columns = [
        "유형", "일반구분", "핸디구분",
        "정역", "홈원정", "결과"
    ]

    for col in required_columns:
        if col not in df.columns:
            raise Exception(f"Missing required column: {col}")

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

        # 🔥 붕괴 위험
        if (
            sample["일반구분"] == "A"
            and sample["정역"] == "역"
            and sample["홈원정"] == "홈"
            and sample["핸디구분"] in ["B", "C"]
        ):
            signal = "⚠ 핸디 붕괴 고위험"

        # 🎯 무 시그널
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

# =========================
# 🌐 ROUTES
# =========================

@app.get("/")
def root():
    return {"message": "SecretCore Service Running"}

# 회원가입
@app.post("/register")
def register(username: str, password: str, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(
        username=username,
        password=hash_password(password),
        is_approved=False,
        is_admin=False
    )

    db.add(user)
    db.commit()

    return {"message": "User registered. Wait for approval."}

# 로그인
@app.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):

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

# 내 정보
@app.get("/users/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return {
        "username": current_user.username,
        "is_admin": current_user.is_admin
    }

# 파일 분석
@app.post("/analyze")
def analyze_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    try:
        filename = file.filename.lower()

        if filename.endswith(".csv"):
            contents = file.file.read().decode("utf-8")
            df = pd.read_csv(StringIO(contents))

        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            contents = file.file.read()
            df = pd.read_excel(BytesIO(contents))

        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

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

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 내 분석 기록
@app.get("/my-analyses")
def get_my_analyses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    records = db.query(AnalysisRecord).filter(
        AnalysisRecord.user_id == current_user.id
    ).all()

    return [
        {
            "filename": r.filename,
            "rows": r.total_rows,
            "columns": r.total_columns,
            "created_at": r.created_at
        }
        for r in records
    ]