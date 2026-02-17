from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jose import jwt
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
import os
import math

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
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("sub")

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != FAKE_USER["username"] or form_data.password != FAKE_USER["password"]:
        raise HTTPException(status_code=401)
    token = create_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

# ================= DATA =================

DATA_FILE = "data_store.csv"
CURRENT_DF = pd.DataFrame()

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_csv(DATA_FILE)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...), user: str = Depends(get_current_user)):
    global CURRENT_DF
    raw = file.file.read()
    df = pd.read_csv(BytesIO(raw), encoding="utf-8")
    df = df.fillna("")
    CURRENT_DF = df
    save_data(df)
    return {"rows": len(df)}

# ================= UTIL =================

def bar(p):
    filled = int(p/5)
    return "█"*filled + "-"*(20-filled)

def dist_calc(df):
    total = len(df)
    if total == 0:
        return {"총":0,"승":"-","무":"-","패":"-","wp":0,"dp":0,"lp":0}

    result_col = df.iloc[:,13]
    win = (result_col=="승").sum()
    draw = (result_col=="무").sum()
    lose = (result_col=="패").sum()

    wp = win/total*100
    dp = draw/total*100
    lp = lose/total*100

    return {
        "총":total,
        "승":f"{bar(wp)} {round(wp,2)}% ({win})",
        "무":f"{bar(dp)} {round(dp,2)}% ({draw})",
        "패":f"{bar(lp)} {round(lp,2)}% ({lose})",
        "wp":wp,"dp":dp,"lp":lp
    }

def run_filter(df, conditions):
    f = df.copy()
    for col_idx, val in conditions.items():
        f = f[f.iloc[:,col_idx]==val]
    return f

def ai_grade(score):
    if score>=85: return "S"
    if score>=70: return "A"
    if score>=55: return "B"
    return "C"

# ================= MATCH LIST (PAGE1) =================

@app.get("/matches")
def matches(user:str=Depends(get_current_user)):
    df = CURRENT_DF
    m = df[df.iloc[:,13]=="경기전"]
    return m.to_dict("records")

# ================= INTEGRATED SCAN (PAGE2,3,4) =================

@app.get("/scan")
def scan(year:int, round_no:str, match_no:int, user:str=Depends(get_current_user)):

    df = CURRENT_DF

    row = df[(df.iloc[:,1]==year)&
             (df.iloc[:,2]==round_no)&
             (df.iloc[:,3]==match_no)]

    if row.empty:
        raise HTTPException(404)

    row = row.iloc[0]

    base_cond = {
        14:row.iloc[14],
        16:row.iloc[16],
        11:row.iloc[11],
        15:row.iloc[15],
        12:row.iloc[12]
    }

    base = run_filter(df, base_cond)
    base_dist = dist_calc(base)

    general_all = run_filter(df,{14:row.iloc[14],16:row.iloc[16],11:row.iloc[11]})
    general_dist = dist_calc(general_all)

    team_home = run_filter(df,{6:row.iloc[6]})
    team_home_dist = dist_calc(team_home)

    team_away = run_filter(df,{7:row.iloc[7]})
    team_away_dist = dist_calc(team_away)

    odds_win = run_filter(df,{8:row.iloc[8]})
    odds_win_dist = dist_calc(odds_win)

    ev = base_dist["wp"]/100 * float(row.iloc[8]) - 1
    grade = ai_grade(max(base_dist["wp"],base_dist["dp"],base_dist["lp"]))

    return {
        "기본조건":base_dist,
        "일반전체":general_dist,
        "홈팀":team_home_dist,
        "원정팀":team_away_dist,
        "배당승":odds_win_dist,
        "EV":round(ev,3),
        "AI":grade
    }

# ================= UI =================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<html>
<body style='background:#111;color:white;font-family:Arial;padding:15px'>
<h2>⚽ SecretCore PRO</h2>
<button onclick='load()'>경기목록</button>
<div id='list'></div>

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
        html+=`<div style='margin-bottom:10px'>
        ${m[5]} | <b>${m[6]}</b> vs <b>${m[7]}</b>
        <button onclick="scan(${m[1]},'${m[2]}',${m[3]})">정보</button>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

async function scan(y,r,m){
    let res=await fetch(`/scan?year=${y}&round_no=${r}&match_no=${m}`,
    {headers:{"Authorization":"Bearer "+token}});
    let d=await res.json();
    alert("AI:"+d.AI+" EV:"+d.EV);
}
</script>
</body>
</html>
"""