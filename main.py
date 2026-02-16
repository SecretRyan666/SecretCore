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
    if form_data.username != FAKE_USER["username"] or \
       form_data.password != FAKE_USER["password"]:
        raise HTTPException(status_code=401)
    token = create_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

# ================= DATA STORAGE =================

DATA_FILE = "data_store.csv"
CURRENT_DF = pd.DataFrame()

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_csv(DATA_FILE)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# ================= UTIL =================

def bar(p):
    filled = int(p/5)
    return "█"*filled + "-"*(20-filled)

def ai_score(win, draw, lose, ev_best):
    score = max(win, draw, lose)
    if ev_best > 0: score += 5
    if draw >= 35: score -= 5
    if max(win,lose) >= 65: score += 5
    return round(score,1)

def ai_grade(score):
    if score >= 85: return "S+"
    if score >= 75: return "S"
    if score >= 65: return "A"
    if score >= 55: return "B"
    return "C"

# ================= UPLOAD =================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...),
                user: str = Depends(get_current_user)):

    global CURRENT_DF
    raw = file.file.read()

    if file.filename.endswith(".csv"):
        df = pd.read_csv(BytesIO(raw))
    else:
        df = pd.read_excel(BytesIO(raw))

    df["결과"] = df["결과"].astype(str).str.strip()
    df = df[df["유형"].isin(["일반","핸디1"])]

    CURRENT_DF = df
    save_data(df)

    return {"total": len(df)}

# ================= MATCH LIST =================

@app.get("/matches")
def matches(user:str=Depends(get_current_user)):
    df = CURRENT_DF
    m = df[df["결과"]=="경기전"]
    return m[["년도","회차","순번","홈팀","원정팀","유형"]].to_dict("records")

# ================= PRO ANALYSIS =================

@app.get("/ultimate-analysis")
def ultimate(year:int, round_no:str, match_no:int,
             user:str=Depends(get_current_user)):

    df = CURRENT_DF
    row = df[(df["년도"]==year)&
             (df["회차"]==round_no)&
             (df["순번"]==match_no)].iloc[0]

    # 1단계
    base1 = df[
        (df["유형"]==row["유형"])&
        (df["일반구분"]==row["일반구분"])&
        (df["핸디구분"]==row["핸디구분"])&
        (df["정역"]==row["정역"])&
        (df["홈원정"]==row["홈원정"])
    ]

    # 2단계
    base2 = df[
        (df["유형"]==row["유형"])&
        (df["일반구분"]==row["일반구분"])&
        (df["정역"]==row["정역"])
    ]

    # 3단계
    base3 = df[(df["유형"]==row["유형"])]

    def calc(base):
        total = len(base)
        vc = base["결과"].value_counts()
        win = vc.get("승",0)
        draw = vc.get("무",0)
        lose = vc.get("패",0)
        win_p = win/total*100 if total else 0
        draw_p = draw/total*100 if total else 0
        lose_p = lose/total*100 if total else 0
        return total, win_p, draw_p, lose_p

    t1,w1,d1,l1 = calc(base1)
    t2,w2,d2,l2 = calc(base2)
    t3,w3,d3,l3 = calc(base3)

    ev_w = w1/100*row["승"]-1
    ev_d = d1/100*row["무"]-1
    ev_l = l1/100*row["패"]-1

    ev_dict = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_dict, key=ev_dict.get)

    score = ai_score(w1,d1,l1,ev_dict[best])
    grade = ai_grade(score)

    # 리그 비교
    league_df = df[df["리그"]==row["리그"]]
    league_total, lw, ld, ll = calc(league_df)

    # 팀스캔
    team_home = df[df["홈팀"]==row["홈팀"]]
    team_total, tw, td, tl = calc(team_home)

    # 배당스캔
    odds_df = df[abs(df["승"] - row["승"])<0.001]
    odds_total, ow, od, ol = calc(odds_df)

    # 시크릿
    secret=""
    if row["일반구분"]=="A" and d1>=30:
        secret="🎯 무 시그널"
    if l1>=55:
        secret="⚠ 핸디 붕괴 위험"

    return {
        "조건": row[["유형","일반구분","핸디구분","정역","홈원정"]].to_dict(),

        "1단계": {"총":t1,"승":bar(w1)+" "+str(round(w1,2))+"%"},
        "2단계": {"총":t2,"승":bar(w2)+" "+str(round(w2,2))+"%"},
        "3단계": {"총":t3,"승":bar(w3)+" "+str(round(w3,2))+"%"},

        "리그비교": {"총":league_total,"승%":round(lw,2)},
        "팀스캔": {"총":team_total,"승%":round(tw,2)},
        "배당스캔": {"총":odds_total,"승%":round(ow,2)},

        "AI점수": score,
        "AI등급": grade,
        "추천": best,
        "시크릿": secret
    }

# ================= PRO UI =================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body{background:#0f0f0f;color:white;font-family:Arial;padding:20px}
    .card{background:#1c1c1c;padding:15px;margin-bottom:15px;border-radius:12px}
    .tab{display:inline-block;margin-right:8px;padding:5px 10px;background:#00ffcc;color:black;border-radius:6px;cursor:pointer}
    .detail{margin-top:10px}
    button{padding:8px 12px;background:#00ffcc;border:none;border-radius:6px}
    </style>
    </head>
    <body>

    <h2>⚽ SecretCore PRO</h2>
    <button onclick="loadMatches()">경기 불러오기</button>
    <div id="matches"></div>

    <script>

    let token = localStorage.getItem("token");

    async function autoLogin(){
        let form = new URLSearchParams();
        form.append("username","admin");
        form.append("password","1234");
        let res = await fetch("/login",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:form});
        let data = await res.json();
        token = data.access_token;
        localStorage.setItem("token",token);
    }

    async function loadMatches(){
        if(!token){ await autoLogin(); }
        let res = await fetch("/matches",{headers:{ "Authorization":"Bearer "+token }});
        let data = await res.json();
        let html="";
        data.forEach((m,i)=>{
            html+=`
            <div class="card">
            <b>${m.홈팀}</b> vs <b>${m.원정팀}</b>
            <button onclick="analyze(${m.년도},'${m.회차}',${m.순번},${i})">정보</button>
            <div id="detail_${i}" class="detail"></div>
            </div>`;
        });
        document.getElementById("matches").innerHTML=html;
    }

    async function analyze(y,r,n,i){
        let res = await fetch(`/ultimate-analysis?year=${y}&round_no=${r}&match_no=${n}`,{headers:{ "Authorization":"Bearer "+token }});
        let d = await res.json();

        document.getElementById("detail_"+i).innerHTML = `
        <div>조건: ${d.조건.유형}/${d.조건.일반구분}/${d.조건.핸디구분}/${d.조건.정역}/${d.조건.홈원정}</div>
        <div>AI등급: ${d.AI등급} (${d.AI점수})</div>
        <div>추천: ${d.추천}</div>
        <div>1단계 승: ${d["1단계"].승}</div>
        <div>2단계 승: ${d["2단계"].승}</div>
        <div>3단계 승: ${d["3단계"].승}</div>
        <div>리그승률: ${d.리그비교["승%"]}%</div>
        <div>팀승률: ${d.팀스캔["승%"]}%</div>
        <div>배당승률: ${d.배당스캔["승%"]}%</div>
        <div>${d.시크릿}</div>
        `;
    }

    </script>
    </body>
    </html>
    """