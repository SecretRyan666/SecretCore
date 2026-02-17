from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import pandas as pd
from io import BytesIO

app = FastAPI()

# =====================================================
# A~Q 절대참조 인덱스
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

    return {
        "EV":{"승":round(ev_w,3),"무":round(ev_d,3),"패":round(ev_l,3)},
        "추천":best,
        "AI":grade
    }


def text_bar(p):
    blocks = int(round(p / 5))  # 20칸
    return "█"*blocks + "░"*(20-blocks)


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
# Page1 - 경기목록
# =====================================================

@app.get("/matches")
def matches(filter_type:str=None, filter_homeaway:str=None,
            filter_general:str=None, filter_dir:str=None,
            filter_handi:str=None):

    df = CURRENT_DF

    m = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        ((df.iloc[:, COL_TYPE] == "일반") | (df.iloc[:, COL_TYPE] == "핸디1"))
    ]

    if filter_type:
        m = m[m.iloc[:, COL_TYPE] == filter_type]
    if filter_homeaway:
        m = m[m.iloc[:, COL_HOMEAWAY] == filter_homeaway]
    if filter_general:
        m = m[m.iloc[:, COL_GENERAL] == filter_general]
    if filter_dir:
        m = m[m.iloc[:, COL_DIR] == filter_dir]
    if filter_handi:
        m = m[m.iloc[:, COL_HANDI] == filter_handi]

    return m.values.tolist()

# =====================================================
# Page2 - 통합스캔
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

    # 일반전체
    general_all = run_filter(df,{COL_GENERAL:row.iloc[COL_GENERAL]})
    general_all_dist = distribution(general_all)

    # 리그전체
    league_all = run_filter(df,{COL_LEAGUE:row.iloc[COL_LEAGUE]})
    league_all_dist = distribution(league_all)

    ev_data = ev_ai(base_dist,row)

    return {
        "리그":row.iloc[COL_LEAGUE],
        "홈":row.iloc[COL_HOME],
        "원정":row.iloc[COL_AWAY],
        "유형":row.iloc[COL_TYPE],
        "홈원정":row.iloc[COL_HOMEAWAY],
        "일반":row.iloc[COL_GENERAL],
        "정역":row.iloc[COL_DIR],
        "핸디":row.iloc[COL_HANDI],
        "승배당":format(row.iloc[COL_WIN_ODDS],".2f"),
        "무배당":format(row.iloc[COL_DRAW_ODDS],".2f"),
        "패배당":format(row.iloc[COL_LOSE_ODDS],".2f"),
        "기본":base_dist,
        "일반전체":general_all_dist,
        "리그전체":league_all_dist,
        "EV":ev_data
    }


# =====================================================
# Page3 - 팀스캔
# =====================================================

@app.get("/page3")
def page3(team:str):

    df = CURRENT_DF

    team_df = df[(df.iloc[:,COL_HOME]==team) |
                 (df.iloc[:,COL_AWAY]==team)]

    overall = distribution(team_df)

    home_df = team_df[team_df.iloc[:,COL_HOME]==team]
    away_df = team_df[team_df.iloc[:,COL_AWAY]==team]

    home_dist = distribution(home_df)
    away_dist = distribution(away_df)

    return {
        "팀":team,
        "전체":overall,
        "홈":home_dist,
        "원정":away_dist
    }


# =====================================================
# Page4 - 배당스캔
# =====================================================

@app.get("/page4")
def page4(win:float, draw:float, lose:float):

    df = CURRENT_DF

    odds_df = df[
        (df.iloc[:,COL_WIN_ODDS]==win) &
        (df.iloc[:,COL_DRAW_ODDS]==draw) &
        (df.iloc[:,COL_LOSE_ODDS]==lose)
    ]

    overall = distribution(odds_df)

    return {
        "승":win,
        "무":draw,
        "패":lose,
        "분포":overall
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
body{
  background:#0f1720;
  color:white;
  font-family:Arial;
  margin:0;
  padding:40px;
  font-size:18px
}
h1{margin-bottom:30px}

.card{
  background:rgba(30,41,59,0.8);
  backdrop-filter:blur(8px);
  padding:25px;
  margin-bottom:25px;
  border-radius:20px;
}

button{
  background:#22d3ee;
  color:black;
  border:none;
  padding:8px 14px;
  border-radius:12px;
  font-size:14px;
  font-weight:bold;
  margin-right:6px;
  margin-bottom:10px;
}

.team-btn{
  background:#334155;
  color:white;
}

.badge{
  display:inline-block;
  padding:6px 10px;
  border-radius:12px;
  font-size:14px;
  font-weight:bold;
}

.win{color:#22c55e}
.draw{color:#cbd5e1}
.lose{color:#ef4444}

pre{
  background:#0b1220;
  padding:15px;
  border-radius:14px;
  font-size:15px;
}
</style>
</head>
<body>

<h1>SecretCore PRO</h1>

<div>
<button onclick="load()">경기목록</button>
<button onclick="filterType('일반')">유형 일반</button>
<button onclick="filterType('핸디1')">유형 핸디1</button>
</div>

<div id="list"></div>

<script>

window.onload = load;

async function load(){
    let r=await fetch('/matches');
    let d=await r.json();
    renderList(d);
}

async function filterType(t){
    let r=await fetch('/matches?filter_type='+t);
    let d=await r.json();
    renderList(d);
}

function renderList(d){
    let html="";
    d.forEach((m)=>{
        html+=`
        <div class="card">
            <b>${m[5]}</b><br>
            <b class="team-btn"
               onclick="location.href='/page3?team=${m[6]}'">${m[6]}</b>
             vs
            <b class="team-btn"
               onclick="location.href='/page3?team=${m[7]}'">${m[7]}</b>

            <button style="float:right"
              onclick="location.href='/detail?year=${m[1]}&match=${m[3]}'">
              정보
            </button>

            <br><br>
            ${m[14]} · ${m[16]} · ${m[11]} · ${m[15]} · ${m[12]}<br>
            승 <span class="win"
               onclick="location.href='/page4?win=${m[8]}&draw=${m[9]}&lose=${m[10]}'">
               ${Number(m[8]).toFixed(2)}</span> |
            무 <span class="draw"
               onclick="location.href='/page4?win=${m[8]}&draw=${m[9]}&lose=${m[10]}'">
               ${Number(m[9]).toFixed(2)}</span> |
            패 <span class="lose"
               onclick="location.href='/page4?win=${m[8]}&draw=${m[9]}&lose=${m[10]}'">
               ${Number(m[10]).toFixed(2)}</span>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

</script>

</body>
</html>
"""


# =====================================================
# 상세 페이지
# =====================================================

@app.get("/detail", response_class=HTMLResponse)
def detail(year:int, match:int):

    data = page2(year,match)

    def block(title,dist):
        return f"""
        <h3>{title} 기준 총 {dist["총"]}경기</h3>
        <pre>
승 {text_bar(dist["wp"])} {dist["wp"]}% ({dist["승"]})
무 {text_bar(dist["dp"])} {dist["dp"]}% ({dist["무"]})
패 {text_bar(dist["lp"])} {dist["lp"]}% ({dist["패"]})
        </pre>
        """

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:40px}}
.card{{background:rgba(30,41,59,0.8);padding:30px;border-radius:20px}}
button{{background:#22d3ee;color:black;border:none;
padding:8px 14px;border-radius:12px;font-weight:bold}}
pre{{background:#0b1220;padding:15px;border-radius:14px}}
</style>
</head>
<body>

<button onclick="location.href='/'">← 경기목록</button>

<div class="card">
<b>{data["리그"]}</b><br>
<b>{data["홈"]}</b> vs <b>{data["원정"]}</b><br>
유형 {data["유형"]} · {data["홈원정"]} · {data["일반"]} · {data["정역"]} · {data["핸디"]}<br>
배당: 승 {data["승배당"]} | 무 {data["무배당"]} | 패 {data["패배당"]}

{block("기본조건",data["기본"])}
{block("일반전체",data["일반전체"])}
{block("리그전체",data["리그전체"])}

<br>
추천: {data["EV"]["추천"]} |
AI: {data["EV"]["AI"]}

<br><br>
<button onclick="location.href='/page3?team={data["홈"]}'">홈팀분석</button>
<button onclick="location.href='/page3?team={data["원정"]}'">원정팀분석</button>
<button onclick="location.href='/page4?win={data["승배당"]}&draw={data["무배당"]}&lose={data["패배당"]}'">배당분석</button>

</div>

</body>
</html>
"""