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
# 🔐 SECURITY CONFIG
# =========================

SECRET_KEY = os.getenv("SECRET_KEY", "local_dev_secret_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# =========================
# 🚀 APP INIT
# =========================

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
# 👑 ADMIN AUTO CREATE
# =========================

@app.on_event("startup")
def create_admin():
    db = SessionLocal()
    admin = db.query(User).filter(User.username == "admin").first()

    if not admin:
        admin_user = User(
            username="admin",
            password=hash_password("admin123"),
            is_approved=True,
            is_admin=True
        )
        db.add(admin_user)
        db.commit()

    db.close()

# =========================
# 🌐 ROUTES
# =========================

@app.get("/")
def root():
    return {"message": "SecretCore Service Running"}

# -------------------------
# 회원가입
# -------------------------

@app.post("/register")
def register(username: str, password: str, db: Session = Depends(get_db)):

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = User(
        username=username,
        password=hash_password(password),
        is_approved=False,
        is_admin=False
    )

    db.add(new_user)
    db.commit()

    return {"message": "Registered. Waiting for admin approval."}

# -------------------------
# 로그인
# -------------------------

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

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

# -------------------------
# 내 정보
# -------------------------

@app.get("/users/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return {
        "username": current_user.username,
        "is_admin": current_user.is_admin
    }

# -------------------------
# 비밀번호 변경
# -------------------------

@app.post("/change-password")
def change_password(
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    current_user.password = hash_password(new_password)
    db.commit()
    return {"message": "Password updated successfully"}

# -------------------------
# 승인 대기 목록
# -------------------------

@app.get("/admin/pending")
def get_pending_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    users = db.query(User).filter(User.is_approved == False).all()
    return [{"username": user.username} for user in users]

# -------------------------
# 사용자 승인
# -------------------------

@app.post("/admin/approve/{target_username}")
def approve_user(
    target_username: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    user = db.query(User).filter(
        User.username == target_username
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_approved = True
    db.commit()

    return {"message": f"{target_username} approved successfully"}

# =========================
# 📊 EXCEL ANALYSIS API (DB 저장)
# =========================

@app.post("/analyze")
def analyze_excel(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        contents = file.file.read()
        df = pd.read_excel(BytesIO(contents))

        total_rows = len(df)
        total_columns = len(df.columns)

        new_record = AnalysisRecord(
            filename=file.filename,
            total_rows=total_rows,
            total_columns=total_columns,
            columns=", ".join(df.columns),
            owner=current_user
        )

        db.add(new_record)
        db.commit()

        return {
            "message": "Analysis saved successfully",
            "filename": file.filename,
            "rows": total_rows,
            "columns": total_columns
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# =========================
# 📜 사용자 분석 기록 조회
# =========================

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