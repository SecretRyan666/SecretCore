from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import pandas as pd
from io import BytesIO

app = FastAPI()

# =====================================================
# 절대참조 컬럼 인덱스 (A~Q 고정)
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

def run_filter(df, conditions: dict):
    filtered = df
    for col_idx, val in conditions.items():
        if val is None:
            continue
        if isinstance(val, list):
            filtered = filtered[filtered.iloc[:, col_idx].isin(val)]
        else:
            filtered = filtered[filtered.iloc[:, col_idx] == val]
    return filtered


def bar(p):
    filled = int(p / 5)
    return "█" * filled + "-" * (20 - filled)


def distribution(df):
    total = len(df)
    if total == 0:
        return {
            "총":0,"승":0,"무":0,"패":0,
            "wp":0,"dp":0,"lp":0,
            "승막대":"-","무막대":"-","패막대":"-"
        }

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
        "wp":wp,"dp":dp,"lp":lp,
        "승막대":bar(wp),
        "무막대":bar(dp),
        "패막대":bar(lp)
    }


def ev_ai(dist, row):
    win_odds  = float(row.iloc[COL_WIN_ODDS])
    draw_odds = float(row.iloc[COL_DRAW_ODDS])
    lose_odds = float(row.iloc[COL_LOSE_ODDS])

    ev_w = dist["wp"]/100*win_odds - 1
    ev_d = dist["dp"]/100*draw_odds - 1
    ev_l = dist["lp"]/100*lose_odds - 1

    ev_map = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_map, key=ev_map.get)

    score = max(dist["wp"],dist["dp"],dist["lp"])
    grade = "S" if score>=60 else "A" if score>=50 else "B"

    return {
        "EV":{k:round(v,3) for k,v in ev_map.items()},
        "추천":best,
        "AI":grade
    }

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

    base = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        (df.iloc[:, COL_TYPE].isin(["일반","핸디1"]))
    ]

    return base.values.tolist()

# =====================================================
# 페이지2 - 통합스캔
# =====================================================

@app.get("/page2")
def page2(year:int, match:int):

    df = CURRENT_DF
    row = df[
        (df.iloc[:,COL_YEAR]==year) &
        (df.iloc[:,COL_MATCH]==match)
    ].iloc[0]

    base_cond = {
        COL_TYPE:row.iloc[COL_TYPE],
        COL_HOMEAWAY:row.iloc[COL_HOMEAWAY],
        COL_GENERAL:row.iloc[COL_GENERAL],
        COL_DIR:row.iloc[COL_DIR],
        COL_HANDI:row.iloc[COL_HANDI]
    }

    base_df = run_filter(df, base_cond)
    base_dist = distribution(base_df)

    general_all = run_filter(df,{
        COL_GENERAL:row.iloc[COL_GENERAL]
    })

    general_match = run_filter(base_df,{
        COL_GENERAL:row.iloc[COL_GENERAL]
    })

    league_all = run_filter(df,{
        COL_LEAGUE:row.iloc[COL_LEAGUE]
    })

    league_match = run_filter(base_df,{
        COL_LEAGUE:row.iloc[COL_LEAGUE]
    })

    ev_data = ev_ai(base_dist,row)

    return {
        "기본":base_dist,
        "일반전체":distribution(general_all),
        "일반매칭":distribution(general_match),
        "리그전체":distribution(league_all),
        "리그매칭":distribution(league_match),
        "EV":ev_data
    }

# =====================================================
# 페이지3 - 팀스캔
# =====================================================

@app.get("/page3")
def page3(team:str):

    df = CURRENT_DF

    team_df = df[
        (df.iloc[:,COL_HOME]==team) |
        (df.iloc[:,COL_AWAY]==team)
    ]

    return distribution(team_df)

# =====================================================
# 페이지4 - 배당스캔
# =====================================================

@app.get("/page4")
def page4(win:float, draw:float, lose:float):

    df = CURRENT_DF

    odds_df = df[
        (df.iloc[:,COL_WIN_ODDS]==win) &
        (df.iloc[:,COL_DRAW_ODDS]==draw) &
        (df.iloc[:,COL_LOSE_ODDS]==lose)
    ]

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
body{background:#0e1117;color:white;font-family:Arial;margin:0;padding:20px}
.card{background:#161b22;margin-bottom:20px;padding:20px;border-radius:14px}
.toggle{color:#00f5ff;cursor:pointer;font-weight:bold}
.hidden{display:none}
.bar{font-family:monospace}
</style>
</head>
<body>

<h1>SecretCore PRO</h1>
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
        <div style="display:flex;justify-content:space-between">
            <div>
                <b>${m[5]}</b><br>
                <b>${m[6]}</b> vs <b>${m[7]}</b><br>
                ${m[14]}.${m[16]}.${m[11]}.${m[15]}.${m[12]}<br>
                승:${m[8]} 무:${m[9]} 패:${m[10]}
            </div>
            <div>
                <span class="toggle" onclick="p2(${m[1]},${m[3]},${i})">정보</span>
            </div>
        </div>
        <div id="d${i}" class="hidden"></div>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

async function p2(y,m,i){
    let r=await fetch(`/page2?year=${y}&match=${m}`);
    let d=await r.json();
    let box=document.getElementById("d"+i);
    box.innerHTML=`
    <div class="bar">
    <b>기본조건</b><br>
    승 ${d.기본.승막대} ${d.기본.wp}% (${d.기본.승})<br>
    무 ${d.기본.무막대} ${d.기본.dp}% (${d.기본.무})<br>
    패 ${d.기본.패막대} ${d.기본.lp}% (${d.기본.패})<br><br>

    <b>일반전체</b> 승:${d.일반전체.승} 무:${d.일반전체.무} 패:${d.일반전체.패}<br>
    <b>일반매칭</b> 승:${d.일반매칭.승} 무:${d.일반매칭.무} 패:${d.일반매칭.패}<br>
    <b>리그전체</b> 승:${d.리그전체.승} 무:${d.리그전체.무} 패:${d.리그전체.패}<br>
    <b>리그매칭</b> 승:${d.리그매칭.승} 무:${d.리그매칭.무} 패:${d.리그매칭.패}<br><br>

    추천:${d.EV.추천} | AI:${d.EV.AI}
    </div>
    `;
    box.classList.toggle("hidden");
}

</script>

</body>
</html>
"""