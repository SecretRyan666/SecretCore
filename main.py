import os
from datetime import datetime, timedelta
from io import BytesIO

import pandas as pd
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import engine, SessionLocal
from models import Base, User, AnalysisRecord

# =========================
# CONFIG
# =========================
SECRET_KEY = os.getenv("SECRET_KEY", "local_dev_secret_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

app = FastAPI()

Base.metadata.create_all(bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# =========================
# DB SESSION
# =========================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =========================
# PASSWORD
# =========================
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# =========================
# JWT
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
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    return user

# =========================
# ADMIN AUTO CREATE
# =========================
@app.on_event("startup")
def create_admin():
    db = SessionLocal()
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        new_admin = User(
            username="admin",
            password=hash_password("admin123"),
            is_approved=True
        )
        db.add(new_admin)
        db.commit()
    db.close()

# =========================
# SECRET ENGINE
# =========================
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

        results.append({
            "KEY": key,
            "total": total,
            "승": f"{generate_bar(win_p)} {win_p}%",
            "무": f"{generate_bar(draw_p)} {draw_p}%",
            "패": f"{generate_bar(lose_p)} {lose_p}%"
        })

    return results

# =========================
# ROUTES
# =========================
@app.get("/")
def root():
    return {"message": "SecretCore Service Running"}

@app.post("/register")
def register(username: str, password: str, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = User(
        username=username,
        password=hash_password(password),
        is_approved=True  # 승인 자동 true
    )

    db.add(new_user)
    db.commit()

    return {"message": "User registered successfully"}

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

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/analyze")
def analyze_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        filename = file.filename.lower()
        raw = file.file.read()

        if filename.endswith(".csv"):
            try:
                df = pd.read_csv(BytesIO(raw), encoding="utf-8")
            except:
                df = pd.read_csv(BytesIO(raw), encoding="cp949")

        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(BytesIO(raw))

        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type"
            )

        required_columns = [
            "유형",
            "일반구분",
            "핸디구분",
            "정역",
            "홈원정",
            "결과"
        ]

        for col in required_columns:
            if col not in df.columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required column: {col}"
                )

        engine_result = secret_engine(df)

        record = AnalysisRecord(
            filename=file.filename,
            rows=len(df),
            columns=len(df.columns),
            owner=current_user
        )

        db.add(record)
        db.commit()

        return {
            "message": "Secret analysis complete",
            "result_count": len(engine_result),
            "analysis_preview": engine_result[:10]
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/my-analyses")
def my_analyses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    records = db.query(AnalysisRecord).filter(
        AnalysisRecord.user_id == current_user.id
    ).all()

    return [
        {
            "filename": r.filename,
            "rows": r.rows,
            "columns": r.columns,
            "created_at": r.created_at
        }
        for r in records
    ]