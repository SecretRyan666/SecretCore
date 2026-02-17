from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import pandas as pd
from io import BytesIO

app = FastAPI()

# =====================================================
# 절대참조 컬럼 인덱스 (A~Q)
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

    best = max({"승":ev_w,"무":ev_d,"패":ev_l},
               key=lambda x: {"승":ev_w,"무":ev_d,"패":ev_l}[x])

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

    df.iloc[:, COL_WIN_ODDS]  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_DRAW_ODDS] = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_LOSE_ODDS] = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0).round(2)

    CURRENT_DF = df
    return {"rows":len(df)}


# =====================================================
# 페이지1 - 경기목록 (경기전 + 일반/핸디1만)
# =====================================================

@app.get("/matches")
def matches():
    df = CURRENT_DF
    m = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        ((df.iloc[:, COL_TYPE] == "일반") | (df.iloc[:, COL_TYPE] == "핸디1"))
    ]
    return m.values.tolist()


# =====================================================
# 페이지2 - 통합스캔
# =====================================================

@app.get("/page2")
def page2(year:int, match:int):

    df = CURRENT_DF
    row = df[(df.iloc[:,COL_YEAR]==year) &
             (df.iloc[:,COL_MATCH]==match)].iloc[0]

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
        "리그":row.iloc[COL_LEAGUE],
        "홈":row.iloc[COL_HOME],
        "원정":row.iloc[COL_AWAY],
        "승배당":format(row.iloc[COL_WIN_ODDS],".2f"),
        "무배당":format(row.iloc[COL_DRAW_ODDS],".2f"),
        "패배당":format(row.iloc[COL_LOSE_ODDS],".2f"),
        "기본":base_dist,
        "EV":ev_data
    }


# =====================================================
# UI
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{background:#0f1720;color:white;font-family:Arial;margin:0;padding:20px}
h1{font-size:28px}
.card{
  background:#1e293b;
  padding:20px;
  margin-bottom:20px;
  border-radius:16px;
}
.info-btn{
  float:right;
  background:#22d3ee;
  color:black;
  border:none;
  padding:8px 14px;
  border-radius:10px;
  font-weight:bold;
}
.bar{
  height:14px;
  background:#334155;
  border-radius:10px;
  margin-bottom:10px;
  overflow:hidden;
}
.bar-inner{
  height:100%;
  background:#22c55e;
}
</style>
</head>
<body>

<h1>SecretCore PRO</h1>
<button onclick="load()">경기목록 불러오기</button>
<div id="list"></div>

<script>

async function load(){
    let r=await fetch('/matches');
    let d=await r.json();
    let html="";
    d.forEach((m)=>{
        html+=`
        <div class="card">
            <b>${m[5]}</b><br>
            <b>${m[6]}</b> vs <b>${m[7]}</b>
            <button class="info-btn"
              onclick="location.href='/detail?year=${m[1]}&match=${m[3]}'">
              정보
            </button>
            <br><br>
            ${m[14]} · ${m[16]} · ${m[11]} · ${m[15]} · ${m[12]}<br>
            배당: 승 ${Number(m[8]).toFixed(2)} |
                  무 ${Number(m[9]).toFixed(2)} |
                  패 ${Number(m[10]).toFixed(2)}
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

</script>

</body>
</html>
"""


# =====================================================
# 페이지2 화면
# =====================================================

@app.get("/detail", response_class=HTMLResponse)
def detail(year:int, match:int):

    data = page2(year,match)
    dist = data["기본"]

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}
.card{{background:#1e293b;padding:20px;border-radius:16px}}
.bar{{height:14px;background:#334155;border-radius:10px;margin-bottom:10px}}
.bar-inner{{height:100%;background:#22c55e}}
</style>
</head>
<body>

<button onclick="location.href='/'">← 경기목록</button>

<div class="card">
<b>{data["리그"]}</b><br>
<b>{data["홈"]} vs {data["원정"]}</b><br>
배당: 승 {data["승배당"]} |
      무 {data["무배당"]} |
      패 {data["패배당"]}

<br><br>
총 {dist["총"]}경기<br>

승 {dist["wp"]}% ({dist["승"]})
<div class="bar"><div class="bar-inner" style="width:{dist["wp"]}%"></div></div>

무 {dist["dp"]}% ({dist["무"]})
<div class="bar"><div class="bar-inner" style="width:{dist["dp"]}%"></div></div>

패 {dist["lp"]}% ({dist["패"]})
<div class="bar"><div class="bar-inner" style="width:{dist["lp"]}%"></div></div>

<br>
추천: {data["EV"]["추천"]} | AI: {data["EV"]["AI"]}
</div>

</body>
</html>
"""