from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from jose import JWTError, jwt
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
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
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except:
        raise HTTPException(status_code=401)

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != "admin" or form_data.password != "1234":
        raise HTTPException(status_code=401)
    token = create_access_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

# =========================
# GLOBAL DATA + SAVE
# =========================

DATA_FILE = "data_store.csv"
CURRENT_DF = pd.DataFrame()

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_csv(DATA_FILE)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# =========================
# BAR
# =========================

def bar(p):
    filled = int(p/5)
    return "█"*filled + "-"*(20-filled)

# =========================
# ADVANCED AI SCORE
# =========================

def ai_grade(win, draw, lose, ev_best, handi):
    score = max(win, draw, lose)
    if ev_best > 0: score += 5
    if draw >= 40: score -= 7
    if "붕괴" in handi: score -= 10

    if score > 80: return "S+"
    if score > 70: return "S"
    if score > 60: return "A"
    if score > 50: return "B"
    return "C"

# =========================
# UPLOAD
# =========================

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
    df = df[df["유형"].isin(["일반","핸디1"])]

    CURRENT_DF = df
    save_data(df)

    target = df[df["결과"]=="경기전"]

    return {"total": len(df), "경기전": len(target)}

# =========================
# MATCHES
# =========================

@app.get("/matches")
def matches(user:str=Depends(get_current_user)):
    df = CURRENT_DF
    m = df[df["결과"]=="경기전"]
    return m[["년도","회차","순번","홈팀","원정팀","유형"]].to_dict("records")

# =========================
# ULTIMATE ENGINE
# =========================

@app.get("/ultimate-analysis")
def ultimate(year:int, round_no:str, match_no:int,
             user:str=Depends(get_current_user)):

    df = CURRENT_DF

    t = df[(df["년도"]==year)&
           (df["회차"]==round_no)&
           (df["순번"]==match_no)]

    if t.empty: raise HTTPException(404)

    row = t.iloc[0]

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

    ev_w = win_p/100*row["승"]-1
    ev_d = draw_p/100*row["무"]-1
    ev_l = lose_p/100*row["패"]-1

    ev_dict = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_dict, key=ev_dict.get)

    handi_df = df[df["유형"]=="핸디1"]
    h_total = len(handi_df)
    h_vc = handi_df["결과"].value_counts()
    h_lose = h_vc.get("패",0)
    collapse = h_lose/h_total*100 if h_total else 0
    handi = f"붕괴 {round(collapse,1)}%" if collapse>=55 else "안정"

    grade = ai_grade(win_p,draw_p,lose_p,ev_dict[best],handi)

    return {
        "기본":row.to_dict(),
        "분포":{
            "총":total,
            "승":f"{bar(win_p)} {round(win_p,2)}%",
            "무":f"{bar(draw_p)} {round(draw_p,2)}%",
            "패":f"{bar(lose_p)} {round(lose_p,2)}%"
        },
        "EV":{k:round(v,3) for k,v in ev_dict.items()},
        "AI등급":grade,
        "핸디":handi,
        "추천":best
    }

# =========================
# WEB UI
# =========================

@app.get("/", response_class=HTMLResponse)
def login_page():
    return """
    <html>
    <body style="background:#111;color:white;text-align:center;padding:50px">
    <h2>SecretCore Login</h2>
    <form method="post" action="/web-login">
    <input name="username" placeholder="ID"><br><br>
    <input name="password" type="password" placeholder="PW"><br><br>
    <button type="submit">Login</button>
    </form>
    </body>
    </html>
    """

@app.post("/web-login")
def web_login(username:str=Form(...), password:str=Form(...)):
    if username!="admin" or password!="1234":
        return HTMLResponse("<h3>Login Failed</h3>")
    return RedirectResponse("/dashboard", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return """
    <html>
    <body style="background:#111;color:white;text-align:center;padding:50px">
    <h1>⚽ SecretCore</h1>
    <button onclick="location.href='/matches-page'">경기 목록</button>
    </body>
    </html>
    """

@app.get("/matches-page", response_class=HTMLResponse)
def matches_page():
    df = CURRENT_DF
    m = df[df["결과"]=="경기전"]
    html="<h2>경기전 목록</h2>"
    for _,r in m.iterrows():
        html+=f"<p>{r['년도']} {r['회차']} {r['순번']} {r['홈팀']} vs {r['원정팀']} ({r['유형']})</p>"
    return HTMLResponse(f"<html><body style='background:#111;color:white'>{html}</body></html>")