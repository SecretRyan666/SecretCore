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

    return {"추천":best,"AI":grade}

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
# 페이지1 경기목록 (필터 적용)
# =====================================================

@app.get("/matches")
def matches():
    df = CURRENT_DF
    m = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        (df.iloc[:, COL_TYPE].isin(["일반","핸디1"]))
    ]
    return m.values.tolist()

# =====================================================
# API Page2 통합스캔
# =====================================================

@app.get("/api/page2")
def api_page2(year:int, match:int):

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

    general_all = run_filter(df,{
        COL_TYPE:row.iloc[COL_TYPE],
        COL_HOMEAWAY:row.iloc[COL_HOMEAWAY],
        COL_GENERAL:row.iloc[COL_GENERAL]
    })

    league_all = run_filter(df,{ COL_LEAGUE:row.iloc[COL_LEAGUE] })

    return {
        "기본":base_dist,
        "일반전체":distribution(general_all),
        "리그전체":distribution(league_all),
        "EV":ev_ai(base_dist,row)
    }

# =====================================================
# API Page3 팀스캔
# =====================================================

@app.get("/api/page3")
def api_page3(team:str):
    df = CURRENT_DF
    team_df = df[(df.iloc[:,COL_HOME]==team) | (df.iloc[:,COL_AWAY]==team)]
    return distribution(team_df)

# =====================================================
# API Page4 배당스캔
# =====================================================

@app.get("/api/page4")
def api_page4(win:float, draw:float, lose:float):
    df = CURRENT_DF
    odds_df = df[(df.iloc[:,COL_WIN_ODDS]==win) &
                 (df.iloc[:,COL_DRAW_ODDS]==draw) &
                 (df.iloc[:,COL_LOSE_ODDS]==lose)]
    return distribution(odds_df)

# =====================================================
# 메인 UI
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<html>
<head>
<style>
body{background:#0f1117;color:white;font-family:Arial;padding:20px}
h1{font-size:34px}
.card{background:#1a1d26;padding:25px;margin:20px 0;border-radius:20px}
.info-btn{
background:linear-gradient(135deg,#2ef0c5,#00c6ff);
border:none;color:black;font-weight:bold;
padding:14px 22px;border-radius:14px;cursor:pointer;
}
.bar{
height:18px;border-radius:10px;margin:8px 0;
background:#333;
}
.fill{
height:100%;border-radius:10px;
background:linear-gradient(90deg,#2ef0c5,#00c6ff);
}
</style>
</head>
<body>

<h1>SecretCore PRO</h1>
<button class="info-btn" onclick="load()">경기목록 불러오기</button>
<div id="list"></div>

<script>

async function load(){
    let r=await fetch('/matches');
    let d=await r.json();
    let html="";
    d.forEach((m)=>{
        html+=`
        <div class="card">
            <h2>${m[6]} vs ${m[7]}</h2>
            <div>${m[14]} · ${m[16]} · ${m[11]} · ${m[15]} · ${m[12]}</div>
            <div>배당: 승 ${m[8]} | 무 ${m[9]} | 패 ${m[10]}</div>
            <br>
            <button class="info-btn"
            onclick="location.href='/page2?year=${m[1]}&match=${m[3]}'">
            정보
            </button>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

</script>

</body>
</html>
"""