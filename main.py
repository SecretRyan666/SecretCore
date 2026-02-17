from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import pandas as pd
from io import BytesIO

app = FastAPI()

# =====================================================
# 절대참조 인덱스 (A~Q 고정)
# =====================================================

COL_NO        = 0
COL_YEAR      = 1
COL_ROUND     = 2
COL_MATCH     = 3
COL_SPORT     = 4
COL_LEAGUE    = 5
COL_HOME      = 6
COL_AWAY      = 7
COL_WIN_ODDS  = 8
COL_DRAW_ODDS = 9
COL_LOSE_ODDS = 10
COL_GENERAL   = 11
COL_HANDI     = 12
COL_RESULT    = 13
COL_TYPE      = 14
COL_DIR       = 15
COL_HOMEAWAY  = 16

CURRENT_DF = pd.DataFrame()

# =====================================================
# 루프엔진
# =====================================================

def run_filter(df, conditions):
    filtered = df
    for col_idx, val in conditions.items():
        filtered = filtered[filtered.iloc[:, col_idx] == val]
    return filtered


def distribution(df):
    total = len(df)
    if total == 0:
        return {"총":0,"승":0,"무":0,"패":0,"wp":0,"dp":0,"lp":0}

    result_col = df.iloc[:, COL_RESULT]

    win  = (result_col == "승").sum()
    draw = (result_col == "무").sum()
    lose = (result_col == "패").sum()

    wp = round(win/total*100,2)
    dp = round(draw/total*100,2)
    lp = round(lose/total*100,2)

    return {
        "총":int(total),
        "승":int(win),
        "무":int(draw),
        "패":int(lose),
        "wp":wp,"dp":dp,"lp":lp
    }


def ev_ai(dist, row):
    win_odds  = float(row.iloc[COL_WIN_ODDS])
    draw_odds = float(row.iloc[COL_DRAW_ODDS])
    lose_odds = float(row.iloc[COL_LOSE_ODDS])

    ev_w = dist["wp"]/100*win_odds - 1
    ev_d = dist["dp"]/100*draw_odds - 1
    ev_l = dist["lp"]/100*lose_odds - 1

    best = max({"승":ev_w,"무":ev_d,"패":ev_l}, key=lambda x: {"승":ev_w,"무":ev_d,"패":ev_l}[x])
    score = max(dist["wp"],dist["dp"],dist["lp"])
    grade = "S" if score>=60 else "A" if score>=50 else "B"

    return {"EV":{"승":round(ev_w,3),"무":round(ev_d,3),"패":round(ev_l,3)},
            "추천":best,"AI":grade}

# =====================================================
# 업로드
# =====================================================

@app.post("/upload-data")
def upload(file: UploadFile = File(...)):
    global CURRENT_DF
    raw = file.file.read()
    df = pd.read_csv(BytesIO(raw), low_memory=False)

    df.iloc[:, COL_WIN_ODDS]  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS], errors="coerce").fillna(0)
    df.iloc[:, COL_DRAW_ODDS] = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0)
    df.iloc[:, COL_LOSE_ODDS] = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0)

    CURRENT_DF = df
    return {"rows":len(df)}

# =====================================================
# 페이지1 - 경기목록
# =====================================================

@app.get("/matches")
def matches():
    df = CURRENT_DF
    m = df[df.iloc[:, COL_RESULT] == "경기전"]
    return m.values.tolist()

# =====================================================
# 페이지2 - 경기 상세
# =====================================================

@app.get("/page2")
def page2(year:int, match:int):

    df = CURRENT_DF
    row = df[(df.iloc[:,COL_YEAR]==year) & (df.iloc[:,COL_MATCH]==match)].iloc[0]

    base_cond = {
        COL_TYPE:row.iloc[COL_TYPE],
        COL_HOMEAWAY:row.iloc[COL_HOMEAWAY],
        COL_GENERAL:row.iloc[COL_GENERAL],
        COL_DIR:row.iloc[COL_DIR],
        COL_HANDI:row.iloc[COL_HANDI]
    }

    base_df = run_filter(df, base_cond)
    base_dist = distribution(base_df)

    ev_data = ev_ai(base_dist,row)

    return {
        "기본":base_dist,
        "EV":ev_data
    }

# =====================================================
# 페이지3 - 팀스캔
# =====================================================

@app.get("/page3")
def page3(team:str):
    df = CURRENT_DF
    team_df = df[(df.iloc[:,COL_HOME]==team) | (df.iloc[:,COL_AWAY]==team)]
    return distribution(team_df)

# =====================================================
# 페이지4 - 배당스캔
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
.card{background:#1c1c1c;margin:10px;padding:12px;border-radius:8px}
.row{display:flex;justify-content:space-between;align-items:center}
.btn{background:#00ffcc;color:black;padding:5px 8px;border-radius:6px;cursor:pointer}
.section{margin-top:10px;padding:8px;background:#222;border-radius:6px}
.hidden{display:none}
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
    d.forEach((m)=>{
        html+=`
        <div class="card">
            <div class="row">
                <div>
                <b>${m[6]}</b> vs <b>${m[7]}</b><br>
                ${m[14]}.${m[16]}.${m[11]}.${m[15]}.${m[12]}
                </div>
                <div class="btn" onclick="goPage2(${m[1]},${m[3]})">정보</div>
            </div>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

async function goPage2(y,m){
    let r=await fetch(`/page2?year=${y}&match=${m}`);
    let d=await r.json();

    document.body.innerHTML=`
    <h2>경기 상세</h2>
    <div class="section">
        <b>기본분포</b><br>
        승:${d.기본.승} 무:${d.기본.무} 패:${d.기본.패}<br>
        추천:${d.EV.추천} AI:${d.EV.AI}
    </div>

    <div class="section">
        <b onclick="toggle('team')">팀 분석 ▼</b>
        <div id="team" class="hidden">
            <input id="teamName" placeholder="팀명 입력">
            <button onclick="loadTeam()">조회</button>
            <div id="teamResult"></div>
        </div>
    </div>

    <div class="section">
        <b onclick="toggle('odds')">배당 분석 ▼</b>
        <div id="odds" class="hidden">
            승:<input id="w">
            무:<input id="d">
            패:<input id="l">
            <button onclick="loadOdds()">조회</button>
            <div id="oddsResult"></div>
        </div>
    </div>

    <button onclick="location.reload()">← 목록</button>
    `;
}

function toggle(id){
    document.getElementById(id).classList.toggle("hidden");
}

async function loadTeam(){
    let t=document.getElementById("teamName").value;
    let r=await fetch(`/page3?team=${t}`);
    let d=await r.json();
    document.getElementById("teamResult").innerHTML=
        "승:"+d.승+" 무:"+d.무+" 패:"+d.패;
}

async function loadOdds(){
    let w=document.getElementById("w").value;
    let d=document.getElementById("d").value;
    let l=document.getElementById("l").value;
    let r=await fetch(`/page4?win=${w}&draw=${d}&lose=${l}`);
    let x=await r.json();
    document.getElementById("oddsResult").innerHTML=
        "승:"+x.승+" 무:"+x.무+" 패:"+x.패;
}

</script>
</body>
</html>
"""