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
# DATA (CSV 전용)
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

def distribution(df):
    total = len(df)

    if total == 0:
        return {
            "총": 0,
            "승": "-",
            "무": "-",
            "패": "-",
            "wp": 0,
            "dp": 0,
            "lp": 0
        }

    vc = df["결과"].value_counts()

    win = int(vc.get("승",0))
    draw = int(vc.get("무",0))
    lose = int(vc.get("패",0))

    wp = (win/total*100) if total else 0
    dp = (draw/total*100) if total else 0
    lp = (lose/total*100) if total else 0

    return {
        "총": int(total),
        "승": f"{bar(wp)} {round(wp,2)}% ({win})",
        "무": f"{bar(dp)} {round(dp,2)}% ({draw})",
        "패": f"{bar(lp)} {round(lp,2)}% ({lose})",
        "wp": float(wp),
        "dp": float(dp),
        "lp": float(lp)
    }

# =====================================================
# UPLOAD
# =====================================================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...),
                user: str = Depends(get_current_user)):

    global CURRENT_DF

    raw = file.file.read()

    # CSV 로드
    df = pd.read_csv(BytesIO(raw), encoding="utf-8")

    # 컬럼 공백 제거
    df.columns = df.columns.str.strip()

    required = [
        "년도","회차","순번","리그","홈팀","원정팀",
        "유형","일반구분","핸디구분","정역","홈원정",
        "결과","승","무","패"
    ]

    for col in required:
        if col not in df.columns:
            raise HTTPException(400, f"Missing column: {col}")

    # 결과값 정리
    df["결과"] = df["결과"].astype(str).str.strip()
    df = df[df["결과"].isin(["승","무","패","경기전"])]

    # 배당 숫자 변환 + NaN 제거
    df["승"] = pd.to_numeric(df["승"], errors="coerce").fillna(0)
    df["무"] = pd.to_numeric(df["무"], errors="coerce").fillna(0)
    df["패"] = pd.to_numeric(df["패"], errors="coerce").fillna(0)

    # 유형 필터
    df = df[df["유형"].isin(["일반","핸디1"])]

    CURRENT_DF = df
    save_data(df)

    target = df[df["결과"]=="경기전"]

    return {
        "total_games": int(len(df)),
        "target_games": int(len(target))
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
# 통합스캔 (2페이지)
# =====================================================

@app.get("/integrated-scan")
def integrated_scan(year:int, round_no:str, match_no:int,
                    user:str=Depends(get_current_user)):

    df = CURRENT_DF

    row = df[(df["년도"]==year)&
             (df["회차"]==round_no)&
             (df["순번"]==match_no)]

    if row.empty:
        raise HTTPException(404)

    row = row.iloc[0]

    base_conditions = {
        "유형":row["유형"],
        "홈원정":row["홈원정"],
        "일반구분":row["일반구분"],
        "정역":row["정역"],
        "핸디구분":row["핸디구분"]
    }

    base = run_filter(df, base_conditions)
    base_dist = distribution(base)

    general_conditions = {
        "유형":row["유형"],
        "홈원정":row["홈원정"],
        "일반구분":row["일반구분"]
    }

    general_all = run_filter(df, general_conditions)
    general_dist = distribution(general_all)

    league_conditions = {"리그":row["리그"]}
    league_all = run_filter(df, league_conditions)
    league_dist = distribution(league_all)

    return {
        "조건":base_conditions,
        "기본조건분포":base_dist,
        "일반동일값":general_dist,
        "리그전체":league_dist
    }

# =====================================================
# UI
# =====================================================

@app.get("/", response_class=HTMLResponse)
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
.detail{display:none;background:#222;padding:10px;margin-top:10px;border-radius:8px;}
</style>
</head>
<body>

<h2>⚽ SecretCore 통합설계</h2>
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
    data.forEach((m,i)=>{
        html+=`
        <div class="card">
            <div class="row">
                <div>
                ${m.리그} | <b>${m.홈팀}</b> vs <b>${m.원정팀}</b><br>
                ${m.유형}.${m.홈원정}.${m.일반구분}.${m.정역}.${m.핸디구분}
                </div>
                <button class="btn" onclick="scan(${m.년도},'${m.회차}',${m.순번},${i})">정보</button>
            </div>
            <div class="detail" id="detail_${i}"></div>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

async function scan(y,r,m,i){
    let res=await fetch(`/integrated-scan?year=${y}&round_no=${r}&match_no=${m}`,
    {headers:{"Authorization":"Bearer "+token}});
    let d=await res.json();
    let box=document.getElementById("detail_"+i);
    box.innerHTML=`
    <b>기본조건</b><br>
    승:${d.기본조건분포.승}<br>
    무:${d.기본조건분포.무}<br>
    패:${d.기본조건분포.패}<br><br>
    <b>일반 동일값</b><br>
    승:${d.일반동일값.승}<br>
    무:${d.일반동일값.무}<br>
    패:${d.일반동일값.패}<br><br>
    <b>리그 전체</b><br>
    승:${d.리그전체.승}<br>
    무:${d.리그전체.무}<br>
    패:${d.리그전체.패}
    `;
    box.style.display="block";
}
</script>

</body>
</html>
"""