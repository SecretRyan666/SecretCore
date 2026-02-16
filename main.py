from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt, JWTError
from datetime import datetime, timedelta
import pandas as pd
import os

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
    if form_data.username != "admin" or form_data.password != "1234":
        raise HTTPException(status_code=401)
    token = create_access_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

# =========================
# GLOBAL DATA LOAD (영구 저장)
# =========================

DATA_FILE = "stored_data.xlsx"

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_excel(DATA_FILE)
else:
    CURRENT_DF = pd.DataFrame()

# =========================
# UTIL
# =========================

def generate_bar(percent):
    filled = int(percent / 5)
    return "█" * filled + "-" * (20 - filled)

def distribution_block(df):
    total = len(df)
    counts = df["결과"].value_counts()

    win = counts.get("승",0)
    draw = counts.get("무",0)
    lose = counts.get("패",0)

    win_pct = win/total*100 if total else 0
    draw_pct = draw/total*100 if total else 0
    lose_pct = lose/total*100 if total else 0

    return {
        "총경기": total,
        "승": f"{generate_bar(win_pct)} {round(win_pct,2)}% ({win})",
        "무": f"{generate_bar(draw_pct)} {round(draw_pct,2)}% ({draw})",
        "패": f"{generate_bar(lose_pct)} {round(lose_pct,2)}% ({lose})",
        "승%": win_pct,
        "무%": draw_pct,
        "패%": lose_pct
    }

def advanced_ai_score(win_pct, draw_pct, lose_pct, ev_best, collapse_rate):
    score = max(win_pct, draw_pct, lose_pct)
    if ev_best > 0:
        score += 5
    if draw_pct >= 40:
        score -= 7
    if collapse_rate >= 55:
        score -= 10

    if score > 80: return "S+"
    if score > 70: return "S"
    if score > 60: return "A"
    if score > 50: return "B"
    return "C"

# =========================
# UPLOAD (영구 저장)
# =========================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...),
                user: str = Depends(get_current_user)):

    global CURRENT_DF

    df = pd.read_excel(file.file)

    df["결과"] = df["결과"].astype(str).str.strip()
    df = df[df["유형"].isin(["일반","핸디1"])]

    CURRENT_DF = df
    df.to_excel(DATA_FILE, index=False)

    target_games = df[df["결과"]=="경기전"]

    return {
        "total_games": int(len(df)),
        "target_games": int(len(target_games))
    }

# =========================
# MATCH LIST
# =========================

@app.get("/matches")
def matches(user: str = Depends(get_current_user)):
    df = CURRENT_DF
    games = df[df["결과"]=="경기전"]
    return games[["년도","회차","순번","홈팀","원정팀","유형"]].to_dict("records")

# =========================
# ULTIMATE FULL ANALYSIS
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

    # 동일조건
    base = df[(df["유형"]==row["유형"])&
              (df["일반구분"]==row["일반구분"])&
              (df["핸디구분"]==row["핸디구분"])&
              (df["정역"]==row["정역"])&
              (df["홈원정"]==row["홈원정"])]

    dist = distribution_block(base)

    # EV
    ev_win = dist["승%"]/100 * row["승"] - 1
    ev_draw = dist["무%"]/100 * row["무"] - 1
    ev_lose = dist["패%"]/100 * row["패"] - 1

    ev_dict = {"승":ev_win,"무":ev_draw,"패":ev_lose}
    best_pick = max(ev_dict, key=ev_dict.get)

    # 핸디 붕괴 동일조건
    handi_df = df[(df["유형"]=="핸디1")&
                  (df["일반구분"]==row["일반구분"])&
                  (df["정역"]==row["정역"])&
                  (df["홈원정"]==row["홈원정"])]

    collapse_rate = 0
    if not handi_df.empty:
        h_counts = handi_df["결과"].value_counts()
        total_h = len(handi_df)
        lose_h = h_counts.get("패",0)
        collapse_rate = lose_h/total_h*100 if total_h else 0

    ai_grade = advanced_ai_score(
        dist["승%"], dist["무%"], dist["패%"],
        ev_dict[best_pick],
        collapse_rate
    )

    return {
        "기본정보": row.to_dict(),
        "동일조건분포": {
            "총경기": dist["총경기"],
            "승": dist["승"],
            "무": dist["무"],
            "패": dist["패"]
        },
        "EV": {
            "승": round(ev_win,3),
            "무": round(ev_draw,3),
            "패": round(ev_lose,3)
        },
        "핸디붕괴율": round(collapse_rate,1),
        "AI등급": ai_grade,
        "최종추천": best_pick
    }

# =========================
# TEAM SCAN FULL
# =========================

@app.get("/team-scan")
def team_scan(team:str, home_away:str,
              user:str=Depends(get_current_user)):

    df = CURRENT_DF

    team_df = df[((df["홈팀"]==team)&(home_away=="홈"))|
                 ((df["원정팀"]==team)&(home_away=="원정"))]

    result = {}

    for game_type in ["일반","핸디1"]:
        sub = team_df[team_df["유형"]==game_type]
        if not sub.empty:
            result[game_type] = distribution_block(sub)

    return result

# =========================
# ODDS SCAN FULL
# =========================

@app.get("/odds-scan")
def odds_scan(odds:float,
              user:str=Depends(get_current_user)):

    df = CURRENT_DF
    sub = df[abs(df["승"]-odds)<0.001]

    if sub.empty:
        raise HTTPException(status_code=404)

    return distribution_block(sub)

# =========================
# WEB UI
# =========================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>SecretCore</title>
        <meta name='viewport' content='width=device-width, initial-scale=1'>
        <style>
            body { background:#111; color:white; text-align:center; padding:40px;}
            button { padding:15px; margin:10px; border-radius:10px;}
        </style>
    </head>
    <body>
        <h1>⚽ SecretCore FULL ENGINE</h1>
        <button onclick="location.href='/docs'">API 테스트</button>
    </body>
    </html>
    """