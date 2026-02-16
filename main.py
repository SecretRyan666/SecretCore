from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from datetime import datetime, timedelta
import pandas as pd
import os
from io import BytesIO

# =========================
# APP INIT
# =========================

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# AUTH
# =========================

SECRET_KEY = "secretcorekey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 600

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

fake_user = {"username": "admin", "password": "1234"}

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401)
        return username
    except JWTError:
        raise HTTPException(status_code=401)

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != fake_user["username"] or form_data.password != fake_user["password"]:
        raise HTTPException(status_code=401)
    token = create_access_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

# =========================
# GLOBAL DATA (영구저장)
# =========================

DATA_FILE = "stored_data.xlsx"
CURRENT_DF = pd.DataFrame()

def load_saved_data():
    global CURRENT_DF
    if os.path.exists(DATA_FILE):
        CURRENT_DF = pd.read_excel(DATA_FILE)
        CURRENT_DF["결과"] = CURRENT_DF["결과"].astype(str).str.strip()

load_saved_data()

# =========================
# UTIL
# =========================

def generate_bar(percent):
    filled = int(percent / 5)
    return "█" * filled + "-" * (20 - filled)

def advanced_ai_score(win_pct, draw_pct, lose_pct, ev_best, handi_status):
    score = max(win_pct, draw_pct, lose_pct)
    if ev_best > 0: score += 5
    if draw_pct >= 40: score -= 7
    if "붕괴" in handi_status: score -= 10

    if score > 80: return "S+"
    if score > 70: return "S"
    if score > 60: return "A"
    if score > 50: return "B"
    return "C"

# =========================
# UPLOAD (영구저장 포함)
# =========================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...), user: str = Depends(get_current_user)):
    global CURRENT_DF

    raw = file.file.read()
    df = pd.read_excel(BytesIO(raw))

    df["결과"] = df["결과"].astype(str).str.strip()
    df = df[df["유형"].isin(["일반", "핸디1"])]

    df.to_excel(DATA_FILE, index=False)
    CURRENT_DF = df

    target_games = df[df["결과"] == "경기전"]

    return {
        "total_games": int(len(df)),
        "target_games": int(len(target_games))
    }

# =========================
# MATCH LIST
# =========================

@app.get("/matches")
def get_matches(user: str = Depends(get_current_user)):
    df = CURRENT_DF
    matches = df[df["결과"] == "경기전"]
    return matches[["년도","회차","순번","홈팀","원정팀","유형"]].to_dict("records")

# =========================
# ULTIMATE ANALYSIS
# =========================

@app.get("/ultimate-analysis")
def ultimate_analysis(year:int, round_no:str, match_no:int,
                      user:str=Depends(get_current_user)):

    df = CURRENT_DF

    target = df[(df["년도"]==year)&
                (df["회차"]==round_no)&
                (df["순번"]==match_no)]

    if target.empty:
        raise HTTPException(status_code=404)

    row = target.iloc[0]

    base = df[(df["유형"]==row["유형"])&
              (df["일반구분"]==row["일반구분"])&
              (df["핸디구분"]==row["핸디구분"])&
              (df["정역"]==row["정역"])&
              (df["홈원정"]==row["홈원정"])]

    total = len(base)
    counts = base["결과"].value_counts()

    win = counts.get("승",0)
    draw = counts.get("무",0)
    lose = counts.get("패",0)

    win_pct = win/total*100 if total else 0
    draw_pct = draw/total*100 if total else 0
    lose_pct = lose/total*100 if total else 0

    ev_win = win_pct/100 * row["승"] - 1
    ev_draw = draw_pct/100 * row["무"] - 1
    ev_lose = lose_pct/100 * row["패"] - 1

    ev_dict = {"승":ev_win,"무":ev_draw,"패":ev_lose}
    best_pick = max(ev_dict, key=ev_dict.get)

    handi_df = df[df["유형"]=="핸디1"]
    collapse_rate = 0
    if not handi_df.empty:
        total_h = len(handi_df)
        lose_h = handi_df["결과"].value_counts().get("패",0)
        collapse_rate = lose_h/total_h*100 if total_h else 0

    handi_status = "안정"
    if collapse_rate >= 55:
        handi_status = f"붕괴위험 {round(collapse_rate,1)}%"

    ai_grade = advanced_ai_score(
        win_pct, draw_pct, lose_pct,
        ev_dict[best_pick], handi_status
    )

    return {
        "기본정보": row.to_dict(),
        "분포": {
            "총경기": total,
            "승": f"{generate_bar(win_pct)} {round(win_pct,2)}% ({win})",
            "무": f"{generate_bar(draw_pct)} {round(draw_pct,2)}% ({draw})",
            "패": f"{generate_bar(lose_pct)} {round(lose_pct,2)}% ({lose})"
        },
        "EV": {
            "승": round(ev_win,3),
            "무": round(ev_draw,3),
            "패": round(ev_lose,3)
        },
        "AI등급": ai_grade,
        "핸디상태": handi_status,
        "최종추천": best_pick
    }

# =========================
# WEB APP UI
# =========================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
    <title>SecretCore FULL ENGINE</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body { background:#111; color:white; text-align:center; font-family:Arial; padding:40px;}
    h1 {color:#00ffcc;}
    button {
        padding:15px;
        margin:10px;
        width:200px;
        font-size:16px;
        border-radius:10px;
        border:none;
        background:#00ffcc;
        color:black;
    }
    </style>
    </head>
    <body>
    <h1>⚽ SecretCore FULL ENGINE</h1>
    <p>AI Sports Betting Engine</p>
    <button onclick="location.href='/docs'">API 테스트</button>
    </body>
    </html>
    """