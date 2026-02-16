from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from jose import jwt, JWTError
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
import os

# =====================================================
# APP INIT
# =====================================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# AUTH SYSTEM
# =====================================================

SECRET_KEY = "secretcorekey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 600

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

FAKE_USER = {"username": "admin", "password": "1234"}

def create_token(data: dict):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401)

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != FAKE_USER["username"] or \
       form_data.password != FAKE_USER["password"]:
        raise HTTPException(status_code=401)
    token = create_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

# =====================================================
# DATA STORAGE (영구 저장)
# =====================================================

DATA_FILE = "data_store.csv"
CURRENT_DF = pd.DataFrame()

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_csv(DATA_FILE)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# =====================================================
# UTILITY
# =====================================================

def bar(p):
    filled = int(p/5)
    return "█"*filled + "-"*(20-filled)

def ai_grade(score):
    if score > 80: return "S+"
    if score > 70: return "S"
    if score > 60: return "A"
    if score > 50: return "B"
    return "C"

# =====================================================
# UPLOAD ENGINE
# =====================================================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...),
                user: str = Depends(get_current_user)):

    global CURRENT_DF

    raw = file.file.read()

    if file.filename.endswith(".csv"):
        df = pd.read_csv(BytesIO(raw))
    else:
        df = pd.read_excel(BytesIO(raw))

    required = [
        "년도","회차","순번","리그",
        "홈팀","원정팀","유형",
        "일반구분","핸디구분","정역","홈원정",
        "결과","승","무","패"
    ]

    for col in required:
        if col not in df.columns:
            raise HTTPException(400, f"Missing {col}")

    df["결과"] = df["결과"].astype(str).str.strip()

    # 일반 + 핸디1만 유지
    df = df[df["유형"].isin(["일반","핸디1"])]

    CURRENT_DF = df
    save_data(df)

    target = df[df["결과"]=="경기전"]

    return {
        "total_games": len(df),
        "target_games": len(target)
    }

# =====================================================
# MATCH LIST
# =====================================================

@app.get("/matches")
def matches(user:str=Depends(get_current_user)):
    df = CURRENT_DF
    m = df[df["결과"]=="경기전"]
    return m[["년도","회차","순번","홈팀","원정팀","유형"]].to_dict("records")

# =====================================================
# ULTIMATE ANALYSIS (엔진 자리)
# =====================================================

@app.get("/ultimate-analysis")
def ultimate(year:int, round_no:str, match_no:int,
             user:str=Depends(get_current_user)):

    df = CURRENT_DF

    target = df[(df["년도"]==year)&
                (df["회차"]==round_no)&
                (df["순번"]==match_no)]

    if target.empty:
        raise HTTPException(404)

    row = target.iloc[0]

    base = df[
        (df["유형"]==row["유형"])&
        (df["일반구분"]==row["일반구분"])&
        (df["핸디구분"]==row["핸디구분"])&
        (df["정역"]==row["정역"])&
        (df["홈원정"]==row["홈원정"])
    ]

    total = len(base)
    vc = base["결과"].value_counts()

    win = vc.get("승",0)
    draw = vc.get("무",0)
    lose = vc.get("패",0)

    win_p = win/total*100 if total else 0
    draw_p = draw/total*100 if total else 0
    lose_p = lose/total*100 if total else 0

    score = max(win_p, draw_p, lose_p)
    grade = ai_grade(score)

    return {
        "기본정보": row.to_dict(),
        "분포":{
            "총": total,
            "승": f"{bar(win_p)} {round(win_p,2)}%",
            "무": f"{bar(draw_p)} {round(draw_p,2)}%",
            "패": f"{bar(lose_p)} {round(lose_p,2)}%"
        },
        "AI등급": grade
    }

# =====================================================
# TEAM SCAN (자리 확보)
# =====================================================

@app.get("/team-scan")
def team_scan(team:str, home_away:str,
              user:str=Depends(get_current_user)):

    df = CURRENT_DF

    team_df = df[
        ((df["홈팀"]==team)&(home_away=="홈")) |
        ((df["원정팀"]==team)&(home_away=="원정"))
    ]

    return {"message":"Team scan engine placeholder"}

# =====================================================
# ODDS SCAN (자리 확보)
# =====================================================

@app.get("/odds-scan")
def odds_scan(odds:float,
              user:str=Depends(get_current_user)):
    return {"message":"Odds scan engine placeholder"}

# =====================================================
# MOBILE WEB UI
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>SecretCore</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {background:#111;color:white;text-align:center;padding:40px;}
            h1 {color:#00ffcc;}
            button {
                padding:15px;
                width:200px;
                margin:10px;
                border-radius:10px;
                border:none;
                background:#00ffcc;
                color:black;
                font-weight:bold;
            }
        </style>
    </head>
    <body>
        <h1>⚽ SecretCore</h1>
        <button onclick="location.href='/docs'">API 테스트</button>
    </body>
    </html>
    """