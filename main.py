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
        filtered = filtered[filtered.iloc[:, col_idx] == val]
    return filtered


def distribution(df):
    total = len(df)
    if total == 0:
        return {"총":0,"승":0,"무":0,"패":0,"wp":0,"dp":0,"lp":0}

    r = df.iloc[:, COL_RESULT]
    win  = (r == "승").sum()
    draw = (r == "무").sum()
    lose = (r == "패").sum()

    wp = round(win/total*100,2)
    dp = round(draw/total*100,2)
    lp = round(lose/total*100,2)

    return {
        "총":int(total),
        "승":int(win),"무":int(draw),"패":int(lose),
        "wp":wp,"dp":dp,"lp":lp
    }


def ev_ai(dist, row):
    w = float(row.iloc[COL_WIN_ODDS])
    d = float(row.iloc[COL_DRAW_ODDS])
    l = float(row.iloc[COL_LOSE_ODDS])

    ev_w = dist["wp"]/100*w - 1
    ev_d = dist["dp"]/100*d - 1
    ev_l = dist["lp"]/100*l - 1

    ev_map = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_map, key=ev_map.get)

    score = max(dist["wp"],dist["dp"],dist["lp"])
    grade = "S" if score>=60 else "A" if score>=50 else "B"

    return {"EV":ev_map,"추천":best,"AI":grade}

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
# 페이지1 - 경기목록 (확대 디자인)
# =====================================================

@app.get("/matches")
def matches():
    df = CURRENT_DF
    m = df[
        (df.iloc[:,COL_RESULT]=="경기전") &
        ((df.iloc[:,COL_TYPE]=="일반") | (df.iloc[:,COL_TYPE]=="핸디1"))
    ]
    return m.values.tolist()

# =====================================================
# 페이지2 - 통합스캔
# =====================================================

@app.get("/page2")
def page2(year:int, match:int):
    df = CURRENT_DF
    row = df[(df.iloc[:,COL_YEAR]==year)&(df.iloc[:,COL_MATCH]==match)].iloc[0]

    base = run_filter(df,{
        COL_TYPE:row.iloc[COL_TYPE],
        COL_HOMEAWAY:row.iloc[COL_HOMEAWAY],
        COL_GENERAL:row.iloc[COL_GENERAL],
        COL_DIR:row.iloc[COL_DIR],
        COL_HANDI:row.iloc[COL_HANDI]
    })

    base_dist = distribution(base)
    ev = ev_ai(base_dist,row)

    return {"기본":base_dist,"EV":ev}

# =====================================================
# 페이지3 - 팀스캔
# =====================================================

@app.get("/page3")
def page3(team:str):
    df = CURRENT_DF
    team_df = df[(df.iloc[:,COL_HOME]==team)|(df.iloc[:,COL_AWAY]==team)]
    return distribution(team_df)

# =====================================================
# 페이지4 - 배당스캔
# =====================================================

@app.get("/page4")
def page4(win:float, draw:float, lose:float):
    df = CURRENT_DF
    odds_df = df[
        (df.iloc[:,COL_WIN_ODDS]==win)&
        (df.iloc[:,COL_DRAW_ODDS]==draw)&
        (df.iloc[:,COL_LOSE_ODDS]==lose)
    ]
    return distribution(odds_df)

# =====================================================
# UI (확대 확정 디자인)
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{background:#111;color:white;font-family:Arial;margin:0;padding:0}
.container{max-width:1100px;margin:auto;padding:20px}
.card{
    background:#1c1c1c;
    margin:20px 0;
    padding:30px;
    border-radius:18px;
    font-size:22px;
}
.row{
    display:flex;
    justify-content:space-between;
    align-items:center;
}
.info-btn{
    background:#00ffcc;
    color:black;
    border:none;
    padding:14px 24px;
    font-size:20px;
    border-radius:10px;
    cursor:pointer;
}
.hidden{display:none}
.section-title{
    font-size:26px;
    font-weight:bold;
    margin-bottom:10px;
}
</style>
</head>
<body>
<div class="container">
<h1>SecretCore PRO</h1>
<button class="info-btn" onclick="load()">경기목록 불러오기</button>
<div id="list"></div>
</div>

<script>

async function load(){
    let r=await fetch('/matches');
    let d=await r.json();
    let html="";
    d.forEach((m,i)=>{
        html+=`
        <div class="card">
            <div class="row">
                <div>
                    <div class="section-title">
                        ${m[6]} vs ${m[7]}
                    </div>
                    ${m[14]} · ${m[16]} · ${m[11]} · ${m[15]} · ${m[12]}
                </div>
                <button class="info-btn" onclick="openDetail(${m[1]},${m[3]})">
                    정보
                </button>
            </div>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

function openDetail(y,m){
    window.location.href=`/detail.html?year=${y}&match=${m}`;
}

</script>
</body>
</html>
"""