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
# UTIL
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
# ULTIMATE ANALYSIS
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

    ev_w = win_p/100*row["승"]-1
    ev_d = draw_p/100*row["무"]-1
    ev_l = lose_p/100*row["패"]-1

    ev_dict = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_dict, key=ev_dict.get)

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
        "EV":{k:round(v,3) for k,v in ev_dict.items()},
        "AI등급": grade,
        "추천": best
    }

# =====================================================
# TEAM SCAN
# =====================================================

@app.get("/team-scan")
def team_scan(team:str, home_away:str,
              user:str=Depends(get_current_user)):

    df = CURRENT_DF

    team_df = df[
        ((df["홈팀"]==team)&(home_away=="홈")) |
        ((df["원정팀"]==team)&(home_away=="원정"))
    ]

    if team_df.empty:
        raise HTTPException(404)

    result = {}

    for game_type in ["일반","핸디1"]:
        sub = team_df[team_df["유형"]==game_type]
        if sub.empty:
            continue

        total = len(sub)
        vc = sub["결과"].value_counts()

        win = vc.get("승",0)
        draw = vc.get("무",0)
        lose = vc.get("패",0)

        win_p = win/total*100 if total else 0
        draw_p = draw/total*100 if total else 0
        lose_p = lose/total*100 if total else 0

        result[game_type] = {
            "총": total,
            "승": f"{bar(win_p)} {round(win_p,2)}%",
            "무": f"{bar(draw_p)} {round(draw_p,2)}%",
            "패": f"{bar(lose_p)} {round(lose_p,2)}%"
        }

    return result

# =====================================================
# ODDS SCAN
# =====================================================

@app.get("/odds-scan")
def odds_scan(odds:float,
              user:str=Depends(get_current_user)):

    df = CURRENT_DF
    sub = df[abs(df["승"] - odds) < 0.001]

    if sub.empty:
        raise HTTPException(404)

    total = len(sub)
    vc = sub["결과"].value_counts()

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

# =====================================================
# FULL MOBILE WEB APP
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>SecretCore AI</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {background:#0f0f0f;color:white;font-family:Arial;margin:0;padding:20px;}
            h1 {color:#00ffcc;text-align:center;}

            .card {
                background:#1c1c1c;
                padding:15px;
                margin-bottom:15px;
                border-radius:14px;
                box-shadow:0 0 12px rgba(0,255,204,0.3);
            }

            .row {
                display:flex;
                justify-content:space-between;
                align-items:center;
            }

            .left {font-size:12px;color:#aaa;}
            .center {font-size:18px;font-weight:bold;color:#00ffcc;}
            .info-btn {
                background:#00ffcc;
                border:none;
                border-radius:8px;
                padding:6px 10px;
                font-weight:bold;
                color:black;
                cursor:pointer;
            }

            .detail {
                margin-top:10px;
                padding:10px;
                background:#111;
                border-radius:10px;
                display:none;
            }

            .section-title {
                margin-top:10px;
                font-weight:bold;
                color:#00ffcc;
            }

            button {
                padding:10px;
                border:none;
                border-radius:8px;
                background:#00ffcc;
                color:black;
                font-weight:bold;
                margin-bottom:15px;
            }
        </style>
    </head>
    <body>

        <h1>⚽ SecretCore AI</h1>
        <button onclick="loadMatches()">경기 불러오기</button>
        <div id="matches"></div>

        <script>

        let token = localStorage.getItem("token");

        async function autoLogin(){
            let form = new URLSearchParams();
            form.append("username","admin");
            form.append("password","1234");

            let res = await fetch("/login",{
                method:"POST",
                headers:{"Content-Type":"application/x-www-form-urlencoded"},
                body:form
            });

            let data = await res.json();
            token = data.access_token;
            localStorage.setItem("token",token);
        }

        async function loadMatches(){

            if(!token){
                await autoLogin();
            }

            let res = await fetch("/matches",{
                headers:{ "Authorization":"Bearer "+token }
            });

            let data = await res.json();
            let html="";

            data.forEach((m,index)=>{
                html+=`
                <div class="card">
                    <div class="row">
                        <div>
                            <div class="left">${m.유형} | ${m.년도} ${m.회차}</div>
                            <div><b>${m.홈팀}</b> vs <b>${m.원정팀}</b></div>
                        </div>
                        <div class="center" id="recommend_${index}">추천</div>
                        <button class="info-btn" onclick="toggleDetail(${index},${m.년도},'${m.회차}',${m.순번})">정보</button>
                    </div>
                    <div class="detail" id="detail_${index}"></div>
                </div>`;
            });

            document.getElementById("matches").innerHTML=html;
        }

        async function toggleDetail(index,year,round_no,match_no){

            let detail = document.getElementById("detail_"+index);

            if(detail.style.display==="block"){
                detail.style.display="none";
                return;
            }

            let res = await fetch(
                `/ultimate-analysis?year=${year}&round_no=${round_no}&match_no=${match_no}`,
                { headers:{ "Authorization":"Bearer "+token } }
            );

            let data = await res.json();

            document.getElementById("recommend_"+index).innerHTML = "추천: "+data.추천;

            let html = `
                <div class="section-title">기본정보</div>
                AI등급: ${data.AI등급}<br>
                승: ${data.분포.승}<br>
                무: ${data.분포.무}<br>
                패: ${data.분포.패}

                <div class="section-title">팀스캔</div>
                (추가 예정)

                <div class="section-title">배당스캔</div>
                (추가 예정)

                <div class="section-title">시크릿분석</div>
                EV 최고값 추천 → ${data.추천}
            `;

            detail.innerHTML = html;
            detail.style.display="block";
        }

        </script>

    </body>
    </html>
    """