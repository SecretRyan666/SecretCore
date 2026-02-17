from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import pandas as pd
from io import BytesIO
import os
import math

app = FastAPI()

# =====================================================
# 절대참조 인덱스 (A~Q)
# =====================================================

COL_NO = 0
COL_YEAR = 1
COL_ROUND = 2
COL_MATCH = 3
COL_SPORT = 4
COL_LEAGUE = 5
COL_HOME = 6
COL_AWAY = 7
COL_WIN = 8
COL_DRAW = 9
COL_LOSE = 10
COL_GENERAL = 11
COL_HANDI = 12
COL_RESULT = 13
COL_TYPE = 14
COL_JEONG = 15
COL_HOMEAWAY = 16

DATA_FILE = "data_store.csv"
CURRENT_DF = pd.DataFrame()

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_csv(DATA_FILE, low_memory=False)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# =====================================================
# 루프엔진
# =====================================================

def loop_distribution(df):
    total = len(df)
    if total == 0:
        return {"총":0,"승":0,"무":0,"패":0,"wp":0,"dp":0,"lp":0}

    win = len(df[df.iloc[:,COL_RESULT] == "승"])
    draw = len(df[df.iloc[:,COL_RESULT] == "무"])
    lose = len(df[df.iloc[:,COL_RESULT] == "패"])

    wp = round(win/total*100,2)
    dp = round(draw/total*100,2)
    lp = round(lose/total*100,2)

    return {
        "총": total,
        "승": win,
        "무": draw,
        "패": lose,
        "wp": wp,
        "dp": dp,
        "lp": lp
    }

def filter_base(df,row):
    return df[
        (df.iloc[:,COL_TYPE] == row[COL_TYPE]) &
        (df.iloc[:,COL_HOMEAWAY] == row[COL_HOMEAWAY]) &
        (df.iloc[:,COL_GENERAL] == row[COL_GENERAL]) &
        (df.iloc[:,COL_JEONG] == row[COL_JEONG]) &
        (df.iloc[:,COL_HANDI] == row[COL_HANDI])
    ]

# =====================================================
# 업로드
# =====================================================

@app.post("/upload-data")
def upload(file: UploadFile = File(...)):
    global CURRENT_DF
    raw = file.file.read()
    df = pd.read_csv(BytesIO(raw), low_memory=False)

    # 숫자 변환
    df.iloc[:,COL_WIN] = pd.to_numeric(df.iloc[:,COL_WIN], errors="coerce").fillna(0)
    df.iloc[:,COL_DRAW] = pd.to_numeric(df.iloc[:,COL_DRAW], errors="coerce").fillna(0)
    df.iloc[:,COL_LOSE] = pd.to_numeric(df.iloc[:,COL_LOSE], errors="coerce").fillna(0)

    CURRENT_DF = df
    save_data(df)

    return {"rows": len(df)}

# =====================================================
# 페이지1 – 경기목록
# =====================================================

@app.get("/matches")
def matches():
    df = CURRENT_DF
    m = df[df.iloc[:,COL_RESULT] == "경기전"]
    return m.values.tolist()

# =====================================================
# 페이지2 – 기본정보
# =====================================================

@app.get("/page2")
def page2(year:int, match:int):
    df = CURRENT_DF
    row = df[(df.iloc[:,COL_YEAR]==year) &
             (df.iloc[:,COL_MATCH]==match)].iloc[0]

    base = filter_base(df,row)
    return loop_distribution(base)

# =====================================================
# 페이지3 – 팀스캔
# =====================================================

@app.get("/page3")
def page3(team:str):
    df = CURRENT_DF
    tdf = df[(df.iloc[:,COL_HOME]==team) |
             (df.iloc[:,COL_AWAY]==team)]
    return loop_distribution(tdf)

# =====================================================
# 페이지4 – 배당스캔
# =====================================================

@app.get("/page4")
def page4(win:float, draw:float, lose:float):
    df = CURRENT_DF
    odf = df[(df.iloc[:,COL_WIN]==win) &
             (df.iloc[:,COL_DRAW]==draw) &
             (df.iloc[:,COL_LOSE]==lose)]
    return loop_distribution(odf)

# =====================================================
# UI
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{background:#0f1117;color:#fff;font-family:Arial;padding:15px}
.card{background:#1c1f26;padding:14px;margin-bottom:12px;border-radius:12px}
.btn{color:#00ffc3;cursor:pointer;margin-right:10px}
.hidden{display:none}
.bar{height:8px;background:#00ffc3;margin:4px 0;border-radius:4px}
</style>
</head>
<body>

<h2>SecretCore PRO</h2>
<button onclick="load()">경기목록</button>
<div id="list"></div>

<script>

async function load(){
    let r=await fetch('/matches');
    let d=await r.json();
    let html="";
    d.forEach((m,i)=>{
        html+=`
        <div class="card">
        <b>${m[6]}</b> vs <b>${m[7]}</b><br>
        ${m[14]}.${m[16]}.${m[11]}.${m[15]}.${m[12]}<br>
        <span class="btn" onclick="p2(${m[1]},${m[3]},${i})">정보</span>
        <span class="btn" onclick="p3('${m[6]}')">${m[6]}</span>
        <span class="btn" onclick="p3('${m[7]}')">${m[7]}</span>
        <span class="btn" onclick="p4(${m[8]},${m[9]},${m[10]})">승무패</span>
        <div id="d${i}" class="hidden"></div>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

function drawBox(d){
    return `
    총:${d.총}<br>
    승:${d.승} (${d.wp}%)<div class="bar" style="width:${d.wp}%"></div>
    무:${d.무} (${d.dp}%)<div class="bar" style="width:${d.dp}%"></div>
    패:${d.패} (${d.lp}%)<div class="bar" style="width:${d.lp}%"></div>
    `;
}

async function p2(y,m,i){
    let r=await fetch(`/page2?year=${y}&match=${m}`);
    let d=await r.json();
    let box=document.getElementById("d"+i);
    box.innerHTML=drawBox(d);
    box.classList.toggle("hidden");
}

async function p3(t){
    let r=await fetch(`/page3?team=${t}`);
    let d=await r.json();
    alert("팀분포\\n"+JSON.stringify(d));
}

async function p4(w,d,l){
    let r=await fetch(`/page4?win=${w}&draw=${d}&lose=${l}`);
    let x=await r.json();
    alert("배당분포\\n"+JSON.stringify(x));
}

</script>

</body>
</html>
"""