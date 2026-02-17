from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jose import jwt, JWTError
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
import os

# =====================================================
# APP
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
# AUTH
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
    if form_data.username != FAKE_USER["username"] or form_data.password != FAKE_USER["password"]:
        raise HTTPException(status_code=401)
    token = create_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

# =====================================================
# DATA
# =====================================================

DATA_FILE = "data_store.csv"
CURRENT_DF = pd.DataFrame()

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_csv(DATA_FILE)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# =====================================================
# UTIL
# =====================================================

def bar(p):
    filled = int(p / 5)
    return "█" * filled + "-" * (20 - filled)

def distribution(df):
    total = len(df)
    if total == 0:
        return {"총":0,"승":"-","무":"-","패":"-","wp":0,"dp":0,"lp":0}

    vc = df["결과"].value_counts()
    win = vc.get("승",0)
    draw = vc.get("무",0)
    lose = vc.get("패",0)

    wp = win/total*100
    dp = draw/total*100
    lp = lose/total*100

    return {
        "총": total,
        "승": f"{bar(wp)} {round(wp,2)}% ({win})",
        "무": f"{bar(dp)} {round(dp,2)}% ({draw})",
        "패": f"{bar(lp)} {round(lp,2)}% ({lose})",
        "wp": wp,
        "dp": dp,
        "lp": lp
    }

def ai_grade(score):
    if score >= 85: return "S+"
    if score >= 75: return "S"
    if score >= 65: return "A"
    if score >= 55: return "B"
    if score >= 45: return "C"
    return "D"

# =====================================================
# UPLOAD (CSV ONLY)
# =====================================================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...),
                user: str = Depends(get_current_user)):

    global CURRENT_DF

    raw = file.file.read()
    df = pd.read_csv(BytesIO(raw), encoding="utf-8")
    df.columns = df.columns.str.strip()

    required = ["년도","회차","순번","리그","홈팀","원정팀",
                "유형","일반구분","핸디구분","정역","홈원정",
                "결과","승","무","패"]

    for col in required:
        if col not in df.columns:
            raise HTTPException(400, f"Missing column: {col}")

    df["결과"] = df["결과"].astype(str).str.strip()
    df["승"] = pd.to_numeric(df["승"], errors="coerce")
    df["무"] = pd.to_numeric(df["무"], errors="coerce")
    df["패"] = pd.to_numeric(df["패"], errors="coerce")

    CURRENT_DF = df
    save_data(df)

    return {
        "total_games": len(df),
        "target_games": len(df[df["결과"]=="경기전"])
    }

# =====================================================
# MATCH LIST (1페이지)
# =====================================================

@app.get("/matches")
def matches(user:str=Depends(get_current_user)):
    df = CURRENT_DF
    m = df[df["결과"]=="경기전"].copy()
    m = m.sort_values(["리그","일반구분"])
    return m.to_dict("records")

# =====================================================
# 통합스캔 단일엔진
# =====================================================

@app.get("/scan")
def scan(year:int, round_no:str, match_no:int,
         user:str=Depends(get_current_user)):

    df = CURRENT_DF

    row = df[(df["년도"]==year)&
             (df["회차"]==round_no)&
             (df["순번"]==match_no)]

    if row.empty:
        raise HTTPException(404)

    row = row.iloc[0]

    # 기본조건
    base = df[
        (df["유형"]==row["유형"]) &
        (df["홈원정"]==row["홈원정"]) &
        (df["일반구분"]==row["일반구분"]) &
        (df["정역"]==row["정역"]) &
        (df["핸디구분"]==row["핸디구분"])
    ]

    base_dist = distribution(base)

    # 일반 전체
    general_all = df[
        (df["유형"]==row["유형"]) &
        (df["홈원정"]==row["홈원정"]) &
        (df["일반구분"]==row["일반구분"])
    ]

    general_dist = distribution(general_all)

    # 리그 전체
    league_all = df[df["리그"]==row["리그"]]
    league_dist = distribution(league_all)

    # 팀
    home_team = distribution(df[df["홈팀"]==row["홈팀"]])
    away_team = distribution(df[df["원정팀"]==row["원정팀"]])

    # 배당
    odds_win = distribution(df[df["승"]==row["승"]])
    odds_draw = distribution(df[df["무"]==row["무"]])
    odds_lose = distribution(df[df["패"]==row["패"]])

    # EV
    ev_w = base_dist["wp"]/100*row["승"]-1
    ev_d = base_dist["dp"]/100*row["무"]-1
    ev_l = base_dist["lp"]/100*row["패"]-1

    ev_dict = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_dict,key=ev_dict.get)

    score = max(base_dist["wp"],base_dist["dp"],base_dist["lp"])
    if ev_dict[best] > 0: score += 5
    if base_dist["총"] < 30: score -= 5

    grade = ai_grade(score)

    return {
        "기본조건":base_dist,
        "일반전체":general_dist,
        "리그전체":league_dist,
        "홈팀":home_team,
        "원정팀":away_team,
        "배당승":odds_win,
        "배당무":odds_draw,
        "배당패":odds_lose,
        "추천":best,
        "AI등급":grade
    }

# =====================================================
# UI (통합스캔UI)
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <body style="background:#111;color:white;font-family:Arial;padding:15px">
    <h2>⚽ SecretCore PRO</h2>
    <button onclick="load()">경기목록</button>
    <div id="list"></div>

    <script>
    let token;

    async function login(){
        let f=new URLSearchParams();
        f.append("username","admin");
        f.append("password","1234");
        let r=await fetch("/login",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:f});
        let d=await r.json();
        token=d.access_token;
    }

    async function load(){
        if(!token) await login();
        let r=await fetch("/matches",{headers:{"Authorization":"Bearer "+token}});
        let data=await r.json();
        let html="";
        data.forEach(m=>{
            html+=`
            <div style="margin-bottom:10px">
            ${m.리그} | <b>${m.홈팀}</b> vs <b>${m.원정팀}</b>
            <button onclick="scan(${m.년도},'${m.회차}',${m.순번})">정보</button>
            </div>`;
        });
        document.getElementById("list").innerHTML=html;
    }

    async function scan(y,r,m){
        let res=await fetch(`/scan?year=${y}&round_no=${r}&match_no=${m}`,
        {headers:{"Authorization":"Bearer "+token}});
        let d=await res.json();
        alert("추천:"+d.추천+" | AI:"+d.AI등급);
    }
    </script>
    </body>
    </html>
    """