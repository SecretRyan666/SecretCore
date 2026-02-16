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

# ================= DATA =================

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

def distribution(df):
    total = len(df)
    vc = df["결과"].value_counts()
    win = vc.get("승",0)
    draw = vc.get("무",0)
    lose = vc.get("패",0)
    win_p = win/total*100 if total else 0
    draw_p = draw/total*100 if total else 0
    lose_p = lose/total*100 if total else 0
    return {
        "총": total,
        "승": f"{bar(win_p)} {round(win_p,2)}%",
        "무": f"{bar(draw_p)} {round(draw_p,2)}%",
        "패": f"{bar(lose_p)} {round(lose_p,2)}%"
    }

# ================= UPLOAD =================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...),
                user: str = Depends(get_current_user)):

    global CURRENT_DF
    raw = file.file.read()
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
    df["승"] = pd.to_numeric(df["승"], errors="coerce")
    df["무"] = pd.to_numeric(df["무"], errors="coerce")
    df["패"] = pd.to_numeric(df["패"], errors="coerce")

    df = df[df["유형"].isin(["일반","핸디1"])]

    CURRENT_DF = df
    save_data(df)

    return {"total_games": len(df)}

# ================= MATCHES =================

@app.get("/matches")
def matches(user:str=Depends(get_current_user)):
    df = CURRENT_DF
    m = df[df["결과"]=="경기전"]
    return m[["년도","회차","순번","홈팀","원정팀","유형"]].to_dict("records")

# ================= ULTIMATE (3단계 포함) =================

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

    # 1단계
    base1 = df[
        (df["유형"]==row["유형"])&
        (df["홈원정"]==row["홈원정"])&
        (df["일반구분"]==row["일반구분"])&
        (df["정역"]==row["정역"])&
        (df["핸디구분"]==row["핸디구분"])
    ]

    # 2단계
    base2 = df[
        (df["유형"]==row["유형"])&
        (df["홈원정"]==row["홈원정"])&
        (df["일반구분"]==row["일반구분"])
    ]

    # 3단계 (리그매칭)
    base3 = base1[base1["리그"]==row["리그"]]

    return {
        "기본정보": row.to_dict(),
        "1단계": distribution(base1),
        "2단계": distribution(base2),
        "3단계(리그매칭)": distribution(base3)
    }

# ================= TEAM SCAN =================

@app.get("/team-scan")
def team_scan(team:str, user:str=Depends(get_current_user)):
    df = CURRENT_DF
    sub = df[(df["홈팀"]==team)|(df["원정팀"]==team)]
    return distribution(sub)

# ================= ODDS SCAN =================

@app.get("/odds-scan")
def odds_scan(odds:float, user:str=Depends(get_current_user)):
    df = CURRENT_DF
    sub = df[abs(df["승"]-odds)<0.001]
    return distribution(sub)

# ================= MOBILE UI =================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>SecretCore PRO</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {background:#0f0f0f;color:white;font-family:Arial;padding:20px;}
            h1 {color:#00ffcc;text-align:center;}
            .card {background:#1c1c1c;padding:15px;margin-bottom:15px;border-radius:14px;}
            .detail {margin-top:10px;padding:10px;background:#111;border-radius:10px;}
            button {padding:6px 10px;border:none;border-radius:8px;background:#00ffcc;color:black;}
        </style>
    </head>
    <body>

    <h1>⚽ SecretCore PRO</h1>
    <button onclick="loadMatches()">경기 불러오기</button>
    <div id="matches"></div>

    <script>
    let token;

    async function login(){
        let form = new URLSearchParams();
        form.append("username","admin");
        form.append("password","1234");
        let res = await fetch("/login",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:form});
        let data = await res.json();
        token = data.access_token;
    }

    async function loadMatches(){
        if(!token){ await login(); }
        let res = await fetch("/matches",{headers:{Authorization:"Bearer "+token}});
        let data = await res.json();
        let html="";
        data.forEach(m=>{
            html+=`
            <div class="card">
            <b>${m.홈팀}</b> vs <b>${m.원정팀}</b>
            <button onclick="detail(${m.년도},'${m.회차}',${m.순번})">i</button>
            <div id="d${m.순번}"></div>
            </div>`;
        });
        document.getElementById("matches").innerHTML=html;
    }

    async function detail(y,r,n){
        let res = await fetch(`/ultimate-analysis?year=${y}&round_no=${r}&match_no=${n}`,{headers:{Authorization:"Bearer "+token}});
        let data = await res.json();
        document.getElementById("d"+n).innerHTML=
        "<div class='detail'>"+
        "<b>1단계</b><br>"+data["1단계"].승+"<br>"+
        "<b>2단계</b><br>"+data["2단계"].승+"<br>"+
        "<b>3단계 리그매칭</b><br>"+data["3단계(리그매칭)"].승+
        "</div>";
    }
    </script>

    </body>
    </html>
    """