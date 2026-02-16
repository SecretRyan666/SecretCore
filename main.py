from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jose import jwt, JWTError
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= AUTH =================

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

# ================= DATA STORAGE =================

DATA_FILE = "data_store.xlsx"
CURRENT_DF = pd.DataFrame()

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_excel(DATA_FILE)

def save_data(df):
    df.to_excel(DATA_FILE, index=False)

# ================= UTIL =================

def bar(p):
    filled = int(p/5)
    return "█"*filled + "-"*(20-filled)

def dist(df):
    total = len(df)
    vc = df["결과"].value_counts()
    win = vc.get("승",0)
    draw = vc.get("무",0)
    lose = vc.get("패",0)
    wp = win/total*100 if total else 0
    dp = draw/total*100 if total else 0
    lp = lose/total*100 if total else 0
    return {
        "총": total,
        "승": f"{bar(wp)} {round(wp,2)}% ({win})",
        "무": f"{bar(dp)} {round(dp,2)}% ({draw})",
        "패": f"{bar(lp)} {round(lp,2)}% ({lose})",
        "wp": wp, "dp": dp, "lp": lp
    }

def ai_grade(score):
    if score >= 90: return "S+"
    if score >= 80: return "S"
    if score >= 70: return "A"
    if score >= 60: return "B"
    if score >= 50: return "C"
    return "D"

# ================= UPLOAD =================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...),
                user: str = Depends(get_current_user)):

    global CURRENT_DF

    raw = file.file.read()

    try:
        df = pd.read_excel(BytesIO(raw), sheet_name="원본")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"엑셀 로드 실패: {str(e)}")

    # ✅ 컬럼 공백 제거
    df.columns = df.columns.str.strip()

    required = [
        "년도","회차","순번","리그",
        "홈팀","원정팀","유형",
        "일반구분","핸디구분","정역","홈원정",
        "결과","승","무","패"
    ]

    for col in required:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Missing column: {col}")

    df["결과"] = df["결과"].astype(str).str.strip()

    # ✅ 안전 숫자 변환
    df["승"] = pd.to_numeric(df["승"], errors="coerce").fillna(0)
    df["무"] = pd.to_numeric(df["무"], errors="coerce").fillna(0)
    df["패"] = pd.to_numeric(df["패"], errors="coerce").fillna(0)

    df = df[df["유형"].isin(["일반","핸디1"])]

    CURRENT_DF = df
    save_data(df)

    target = df[df["결과"] == "경기전"]

    return {
        "total_games": int(len(df)),
        "target_games": int(len(target))
    }

# ================= MATCH LIST =================

@app.get("/matches")
def matches(user:str=Depends(get_current_user)):
    df = CURRENT_DF
    m = df[df["결과"]=="경기전"].copy()
    m = m.sort_values(["리그","일반구분"])
    return m.to_dict("records")

# ================= 통합스캔 =================

@app.get("/integrated-scan")
def scan(year:int, round_no:str, match_no:int,
         user:str=Depends(get_current_user)):

    df = CURRENT_DF

    row = df[(df["년도"]==year)&
             (df["회차"]==round_no)&
             (df["순번"]==match_no)].iloc[0]

    # 기본조건키
    base = df[
        (df["유형"]==row["유형"])&
        (df["홈원정"]==row["홈원정"])&
        (df["일반구분"]==row["일반구분"])&
        (df["정역"]==row["정역"])&
        (df["핸디구분"]==row["핸디구분"])
    ]

    base_dist = dist(base)

    # 일반전체
    general_all = df[
        (df["유형"]==row["유형"])&
        (df["홈원정"]==row["홈원정"])&
        (df["일반구분"]==row["일반구분"])
    ]

    general_dist = dist(general_all)

    # 리그전체
    league_all = df[df["리그"]==row["리그"]]
    league_dist = dist(league_all)

    # EV 계산
    ev_w = base_dist["wp"]/100*row["승"]-1
    ev_d = base_dist["dp"]/100*row["무"]-1
    ev_l = base_dist["lp"]/100*row["패"]-1

    ev_dict = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_dict,key=ev_dict.get)

    score = max(base_dist["wp"],base_dist["dp"],base_dist["lp"])
    if ev_dict[best]>0: score+=5
    if base_dist["dp"]>=35: score-=5
    if base_dist["총"]<30: score-=5

    grade = ai_grade(score)

    secret=""
    if row["일반구분"]=="A" and base_dist["dp"]>=30:
        secret="🎯 무 시그널"
    if row["핸디구분"] in ["B","C"] and base_dist["lp"]>=50:
        secret="⚠ 핸디 붕괴"

    return {
        "조건":{
            "유형":row["유형"],
            "홈원정":row["홈원정"],
            "일반":row["일반구분"],
            "정역":row["정역"],
            "핸디":row["핸디구분"]
        },
        "기본조건분포":base_dist,
        "일반전체":general_dist,
        "리그전체":league_dist,
        "EV":{k:round(v,3) for k,v in ev_dict.items()},
        "AI등급":grade,
        "추천":best,
        "시크릿":secret
    }

# ================= UI =================

@app.get("/",response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body{background:#111;color:white;font-family:Arial;padding:15px;}
    .card{background:#1c1c1c;padding:12px;margin-bottom:12px;border-radius:10px;}
    .row{display:flex;justify-content:space-between;}
    .btn{background:#00ffcc;color:black;border:none;padding:6px 8px;border-radius:6px;}
    </style>
    </head>
    <body>
    <h2>⚽ SecretCore PRO</h2>
    <button onclick="load()">경기불러오기</button>
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
            <div class="card">
            <div class="row">
            <div>
            ${m.리그} | <b>${m.홈팀}</b> vs <b>${m.원정팀}</b><br>
            ${m.유형}.${m.홈원정}.${m.일반구분}.${m.정역}.${m.핸디구분}
            </div>
            <button class="btn" onclick="scan(${m.년도},'${m.회차}',${m.순번})">정보</button>
            </div>
            </div>`;
        });
        document.getElementById("list").innerHTML=html;
    }
    async function scan(y,r,m){
        let res=await fetch(`/integrated-scan?year=${y}&round_no=${r}&match_no=${m}`,
        {headers:{"Authorization":"Bearer "+token}});
        let d=await res.json();
        alert("추천:"+d.추천+" | AI:"+d.AI등급);
    }
    </script>
    </body>
    </html>
    """