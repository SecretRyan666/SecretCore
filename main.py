from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
import pandas as pd
from io import BytesIO
import os

app = FastAPI()

# =====================================================
# 절대참조 컬럼 인덱스 (A~Q 고정)
# =====================================================
COL_NO = 0
COL_YEAR = 1
COL_ROUND = 2
COL_MATCH = 3
COL_SPORT = 4
COL_LEAGUE = 5
COL_HOME = 6
COL_AWAY = 7
COL_WIN_ODDS = 8
COL_DRAW_ODDS = 9
COL_LOSE_ODDS = 10
COL_GENERAL = 11
COL_HANDI = 12
COL_RESULT = 13
COL_TYPE = 14
COL_TURN = 15
COL_HOMEAWAY = 16

DATA_FILE = "data_store.csv"
CURRENT_DF = pd.DataFrame()

# =====================================================
# 유틸
# =====================================================

def bar(p):
    filled = int(p/5)
    return "█"*filled + "-"*(20-filled)

def distribution(df):
    total = len(df)
    if total == 0:
        return {"총":0,"승":"-","무":"-","패":"-","wp":0,"dp":0,"lp":0}

    win = (df.iloc[:,COL_RESULT] == "승").sum()
    draw = (df.iloc[:,COL_RESULT] == "무").sum()
    lose = (df.iloc[:,COL_RESULT] == "패").sum()

    wp = win/total*100
    dp = draw/total*100
    lp = lose/total*100

    return {
        "총": int(total),
        "승": f"{bar(wp)} {round(wp,2)}% ({int(win)})",
        "무": f"{bar(dp)} {round(dp,2)}% ({int(draw)})",
        "패": f"{bar(lp)} {round(lp,2)}% ({int(lose)})",
        "wp": wp, "dp": dp, "lp": lp
    }

def run_filter(df, conditions):
    filtered = df
    for col, val in conditions:
        filtered = filtered[filtered.iloc[:,col] == val]
    return filtered

def ai_grade(score):
    if score >= 90: return "S+"
    if score >= 80: return "S"
    if score >= 70: return "A"
    if score >= 60: return "B"
    if score >= 50: return "C"
    return "D"

# =====================================================
# 업로드
# =====================================================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...)):
    global CURRENT_DF
    raw = file.file.read()
    df = pd.read_csv(BytesIO(raw), low_memory=False)

    df.iloc[:,COL_WIN_ODDS] = pd.to_numeric(df.iloc[:,COL_WIN_ODDS], errors="coerce").fillna(0)
    df.iloc[:,COL_DRAW_ODDS] = pd.to_numeric(df.iloc[:,COL_DRAW_ODDS], errors="coerce").fillna(0)
    df.iloc[:,COL_LOSE_ODDS] = pd.to_numeric(df.iloc[:,COL_LOSE_ODDS], errors="coerce").fillna(0)

    CURRENT_DF = df
    df.to_csv(DATA_FILE,index=False)

    return {"total":len(df)}

# =====================================================
# 페이지1 경기목록
# =====================================================

@app.get("/matches")
def matches():
    df = CURRENT_DF
    m = df[df.iloc[:,COL_RESULT]=="경기전"]
    return JSONResponse(content=m.values.tolist())

# =====================================================
# 페이지2 통합스캔
# =====================================================

@app.get("/page2")
def page2(year:int, match:int):

    df = CURRENT_DF
    row = df[(df.iloc[:,COL_YEAR]==year) &
             (df.iloc[:,COL_MATCH]==match)].iloc[0]

    base = run_filter(df, [
        (COL_TYPE,row.iloc[COL_TYPE]),
        (COL_HOMEAWAY,row.iloc[COL_HOMEAWAY]),
        (COL_GENERAL,row.iloc[COL_GENERAL]),
        (COL_TURN,row.iloc[COL_TURN]),
        (COL_HANDI,row.iloc[COL_HANDI])
    ])

    base_dist = distribution(base)

    general_all = run_filter(df,[
        (COL_TYPE,row.iloc[COL_TYPE]),
        (COL_HOMEAWAY,row.iloc[COL_HOMEAWAY])
    ])

    general_match = run_filter(df,[
        (COL_TYPE,row.iloc[COL_TYPE]),
        (COL_HOMEAWAY,row.iloc[COL_HOMEAWAY]),
        (COL_GENERAL,row.iloc[COL_GENERAL])
    ])

    league_match = run_filter(df,[
        (COL_LEAGUE,row.iloc[COL_LEAGUE])
    ])

    # EV
    ev_w = base_dist["wp"]/100 * row.iloc[COL_WIN_ODDS] - 1
    ev_d = base_dist["dp"]/100 * row.iloc[COL_DRAW_ODDS] - 1
    ev_l = base_dist["lp"]/100 * row.iloc[COL_LOSE_ODDS] - 1

    best = max({"승":ev_w,"무":ev_d,"패":ev_l}, key={"승":ev_w,"무":ev_d,"패":ev_l}.get)
    score = max(base_dist["wp"],base_dist["dp"],base_dist["lp"])
    grade = ai_grade(score)

    return {
        "기본조건":base_dist,
        "일반전체":distribution(general_all),
        "일반매칭":distribution(general_match),
        "리그매칭":distribution(league_match),
        "EV":{"승":round(ev_w,3),"무":round(ev_d,3),"패":round(ev_l,3)},
        "AI":grade,
        "추천":best
    }

# =====================================================
# 페이지3 팀스캔
# =====================================================

@app.get("/page3")
def page3(team:str):

    df = CURRENT_DF
    team_df = df[(df.iloc[:,COL_HOME]==team)|(df.iloc[:,COL_AWAY]==team)]
    return distribution(team_df)

# =====================================================
# 페이지4 배당스캔
# =====================================================

@app.get("/page4")
def page4(win:float, draw:float, lose:float):

    df = CURRENT_DF
    odds_df = df[(df.iloc[:,COL_WIN_ODDS]==win) &
                 (df.iloc[:,COL_DRAW_ODDS]==draw) &
                 (df.iloc[:,COL_LOSE_ODDS]==lose)]

    return distribution(odds_df)

# =====================================================
# UI
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<html>
<head>
<style>
body{background:#111;color:white;font-family:Arial}
.card{background:#1c1c1c;padding:12px;margin:10px;border-radius:8px}
.toggle{color:#00ffcc;cursor:pointer}
.hidden{display:none}
.center{font-weight:bold;color:#00ffcc}
</style>
</head>
<body>

<h2>SecretCore 통합</h2>
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
        <span class="toggle" onclick="p2(${m[1]},${m[3]},${i})">정보</span> |
        <span class="toggle" onclick="p3('${m[6]}')">${m[6]}</span> |
        <span class="toggle" onclick="p3('${m[7]}')">${m[7]}</span> |
        <span class="toggle" onclick="p4(${m[8]},${m[9]},${m[10]})">승무패</span>
        <div id="d${i}" class="hidden"></div>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

async function p2(y,m,i){
    let r=await fetch(`/page2?year=${y}&match=${m}`);
    let d=await r.json();
    let box=document.getElementById("d"+i);
    box.innerHTML=
    "<div class='center'>기본조건</div>"+d.기본조건.승+"<br>"+d.기본조건.무+"<br>"+d.기본조건.패+
    "<br><div class='center'>일반전체</div>"+d.일반전체.승+"<br>"+d.일반전체.무+"<br>"+d.일반전체.패+
    "<br><div class='center'>일반매칭</div>"+d.일반매칭.승+"<br>"+d.일반매칭.무+"<br>"+d.일반매칭.패+
    "<br><div class='center'>리그매칭</div>"+d.리그매칭.승+"<br>"+d.리그매칭.무+"<br>"+d.리그매칭.패+
    "<br><div class='center'>AI:"+d.AI+" 추천:"+d.추천+"</div>";
    box.classList.toggle("hidden");
}

async function p3(t){
    let r=await fetch(`/page3?team=${t}`);
    let d=await r.json();
    alert("팀분포\\n"+d.승+"\\n"+d.무+"\\n"+d.패);
}

async function p4(w,d,l){
    let r=await fetch(`/page4?win=${w}&draw=${d}&lose=${l}`);
    let x=await r.json();
    alert("배당분포\\n"+x.승+"\\n"+x.무+"\\n"+x.패);
}

</script>
</body>
</html>
"""