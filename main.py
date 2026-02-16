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
        "승": f"{bar(win_p)} {round(win_p,2)}% ({win})",
        "무": f"{bar(draw_p)} {round(draw_p,2)}% ({draw})",
        "패": f"{bar(lose_p)} {round(lose_p,2)}% ({lose})",
        "win_p": win_p,
        "draw_p": draw_p,
        "lose_p": lose_p
    }

def ai_grade(score):
    if score > 80: return "S+"
    if score > 70: return "S"
    if score > 60: return "A"
    if score > 50: return "B"
    return "C"

# ================= UPLOAD =================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...),
                user: str = Depends(get_current_user)):

    global CURRENT_DF
    raw = file.file.read()
    df = pd.read_excel(BytesIO(raw))

    df["결과"] = df["결과"].astype(str).str.strip()
    df["승"] = pd.to_numeric(df["승"], errors="coerce")
    df["무"] = pd.to_numeric(df["무"], errors="coerce")
    df["패"] = pd.to_numeric(df["패"], errors="coerce")

    df = df[df["유형"].isin(["일반","핸디1"])]

    CURRENT_DF = df
    save_data(df)

    return {"total_games": len(df)}

# ================= MATCH LIST =================

@app.get("/matches")
def matches(user:str=Depends(get_current_user)):
    df = CURRENT_DF
    m = df[df["결과"]=="경기전"]
    return m[[
        "년도","회차","순번",
        "홈팀","원정팀",
        "유형","홈원정","일반구분","정역","핸디구분",
        "승","무","패"
    ]].to_dict("records")

# ================= 통합스캔 =================

@app.get("/integrated-scan")
def integrated_scan(year:int, round_no:str, match_no:int,
                    user:str=Depends(get_current_user)):

    df = CURRENT_DF
    target = df[(df["년도"]==year)&
                (df["회차"]==round_no)&
                (df["순번"]==match_no)]

    if target.empty:
        raise HTTPException(404)

    row = target.iloc[0]

    # 기본조건키
    base_key = df[
        (df["유형"]==row["유형"])&
        (df["홈원정"]==row["홈원정"])&
        (df["일반구분"]==row["일반구분"])&
        (df["정역"]==row["정역"])&
        (df["핸디구분"]==row["핸디구분"])
    ]

    base_dist = distribution(base_key)

    # 일반 전체
    normal_all = df[
        (df["유형"]==row["유형"])&
        (df["홈원정"]==row["홈원정"])&
        (df["일반구분"]==row["일반구분"])
    ]

    normal_all_dist = distribution(normal_all)

    # 일반 매칭 (동일 일반구분)
    normal_match = df[df["일반구분"]==row["일반구분"]]
    normal_match_dist = distribution(normal_match)

    # EV 계산
    win_p = base_dist["win_p"]
    draw_p = base_dist["draw_p"]
    lose_p = base_dist["lose_p"]

    ev_w = win_p/100 * row["승"] - 1
    ev_d = draw_p/100 * row["무"] - 1
    ev_l = lose_p/100 * row["패"] - 1

    ev_dict = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_dict, key=ev_dict.get)

    score = max(win_p, draw_p, lose_p)
    grade = ai_grade(score)

    return {
        "기본정보": row.to_dict(),
        "기본조건키분포": base_dist,
        "일반전체분포": normal_all_dist,
        "일반매칭분포": normal_match_dist,
        "EV": {k:round(v,3) for k,v in ev_dict.items()},
        "AI등급": grade,
        "추천": best
    }

# ================= UI =================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {background:#111;color:white;font-family:Arial;padding:20px;}
            .card {background:#1c1c1c;padding:15px;margin-bottom:10px;border-radius:10px;}
            .row {display:flex;justify-content:space-between;align-items:center;}
            .info-btn {background:#00ffcc;border:none;padding:6px 10px;border-radius:6px;font-weight:bold;}
            .detail {margin-top:10px;padding:10px;background:#000;border-radius:8px;display:none;}
        </style>
    </head>
    <body>
    <h2>⚽ SecretCore 통합스캔</h2>
    <button onclick="loadMatches()">경기 불러오기</button>
    <div id="list"></div>

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
            <div class="row">
                <div>
                    <b>${m.홈팀}</b> vs <b>${m.원정팀}</b><br>
                    ${m.유형}.${m.홈원정}.${m.일반구분}.${m.정역}.${m.핸디구분}
                </div>
                <button class="info-btn" onclick="scan(${i},${m.년도},'${m.회차}',${m.순번})">정보</button>
            </div>
            <div class="detail" id="d_${i}"></div>
        </div>`;
    });
    document.getElementById("list").innerHTML = html;
}

async function scan(i,y,r,n){
    let detail = document.getElementById("d_"+i);
    if(detail.style.display==="block"){detail.style.display="none";return;}
    let res = await fetch(`/integrated-scan?year=${y}&round_no=${r}&match_no=${n}`,{headers:{ "Authorization":"Bearer "+token }});
    let data = await res.json();
    detail.innerHTML = `
        <b>기본조건키</b><br>
        승 ${data.기본조건키분포.승}<br>
        무 ${data.기본조건키분포.무}<br>
        패 ${data.기본조건키분포.패}<br><br>
        <b>일반전체</b><br>
        승 ${data.일반전체분포.승}<br>
        무 ${data.일반전체분포.무}<br>
        패 ${data.일반전체분포.패}<br><br>
        <b>일반매칭</b><br>
        승 ${data.일반매칭분포.승}<br>
        무 ${data.일반매칭분포.무}<br>
        패 ${data.일반매칭분포.패}<br><br>
        <b>추천:</b> ${data.추천} / ${data.AI등급}
    `;
    detail.style.display="block";
}

</script>
</body>
</html>
"""