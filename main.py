from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import pandas as pd
from io import BytesIO
import os
import json

app = FastAPI()

# =====================================================
# 절대참조 인덱스
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

DATA_FILE = "current_data.csv"

CURRENT_DF = pd.DataFrame()
LOGGED_IN = False

# =====================================================
# 데이터 자동 로드 (서버 재시작 대비)
# =====================================================

def load_data():
    global CURRENT_DF
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE, encoding="utf-8-sig", low_memory=False)

        df.iloc[:, COL_WIN_ODDS]  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS], errors="coerce").fillna(0).round(2)
        df.iloc[:, COL_DRAW_ODDS] = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0).round(2)
        df.iloc[:, COL_LOSE_ODDS] = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0).round(2)

        CURRENT_DF = df

load_data()

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

    ev_map = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_map, key=ev_map.get)

    score = max(dist["wp"],dist["dp"],dist["lp"])
    grade = "S" if score>=60 else "A" if score>=50 else "B"

    return {
        "EV":{"승":round(ev_w,3),"무":round(ev_d,3),"패":round(ev_l,3)},
        "추천":best,
        "AI":grade
    }

# =====================================================
# 로그인
# =====================================================

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    global LOGGED_IN
    if username == "ryan" and password == "963258":
        LOGGED_IN = True
    return RedirectResponse("/", status_code=302)

@app.get("/logout")
def logout():
    global LOGGED_IN
    LOGGED_IN = False
    return RedirectResponse("/", status_code=302)

# =====================================================
# 업로드 (숫자형 변환 후 저장)
# =====================================================

@app.post("/upload-data")
def upload(file: UploadFile = File(...)):
    global CURRENT_DF

    raw = file.file.read()
    df = pd.read_csv(BytesIO(raw), encoding="utf-8-sig", low_memory=False)

    if df.shape[1] < 17:
        return {"error":"컬럼 구조 오류"}

    df.iloc[:, COL_WIN_ODDS]  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_DRAW_ODDS] = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_LOSE_ODDS] = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0).round(2)

    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

    CURRENT_DF = df

    return RedirectResponse("/", status_code=302)

# =====================================================
# 필터 API
# =====================================================

@app.get("/filters")
def filters():

    df = CURRENT_DF

    if df.empty:
        return {
            "type":[],
            "homeaway":[],
            "general":[],
            "dir":[],
            "handi":[]
        }

    return {
        "type": sorted(df.iloc[:, COL_TYPE].dropna().unique().tolist()),
        "homeaway": sorted(df.iloc[:, COL_HOMEAWAY].dropna().unique().tolist()),
        "general": sorted(df.iloc[:, COL_GENERAL].dropna().unique().tolist()),
        "dir": sorted(df.iloc[:, COL_DIR].dropna().unique().tolist()),
        "handi": sorted(df.iloc[:, COL_HANDI].dropna().unique().tolist())
    }


# =====================================================
# Page1 - 경기목록 API
# =====================================================

@app.get("/matches")
def matches(
    filter_type: str = None,
    filter_homeaway: str = None,
    filter_general: str = None,
    filter_dir: str = None,
    filter_handi: str = None
):

    df = CURRENT_DF

    if df.empty:
        return []

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
# Page1 UI (🔥 f-string 제거 + 상태 유지 + 디자인 고정)
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():

    if LOGGED_IN:
        login_area = """
        <form action="/upload-data" method="post" enctype="multipart/form-data" style="display:inline;">
            <input type="file" name="file" required>
            <button type="submit">업로드</button>
        </form>
        <a href="/logout"><button>로그아웃</button></a>
        """
    else:
        login_area = """
        <form action="/login" method="post" style="display:inline;">
            <input name="username" placeholder="ID">
            <input name="password" type="password" placeholder="PW">
            <button type="submit">로그인</button>
        </form>
        """

    return """
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>

body{
    background:#0f1720;
    color:white;
    font-family:Arial;
    padding:20px
}

.header{
    display:flex;
    justify-content:space-between;
    align-items:center;
    margin-bottom:10px
}

.filters{
    display:flex;
    gap:6px;
    margin-top:15px;
    flex-wrap:nowrap;
    overflow-x:auto
}

.filters button,
.filters select{
    height:32px;
    font-size:13px;
    padding:0 10px;
    border-radius:8px;
    background:#1e293b;
    color:white;
    border:1px solid #334155;
    min-width:70px
}

.card{
    background:#1e293b;
    padding:18px;
    border-radius:18px;
    margin-top:16px;
    position:relative
}

.info-btn{
    position:absolute;
    right:12px;
    top:12px;
    height:28px;
    font-size:12px;
    padding:0 10px;
    border-radius:6px
}

</style>
</head>
<body>

<div class="header">
<h2>SecretCore PRO</h2>
<div>""" + login_area + """</div>
</div>

<div class="filters">
<button onclick="resetFilters()">경기목록</button>
<select id="type"></select>
<select id="homeaway"></select>
<select id="general"></select>
<select id="dir"></select>
<select id="handi"></select>
</div>

<div id="list"></div>

<script>

let filters = {};

window.onload = async function(){
    await loadFilters();

    const saved = localStorage.getItem("sc_filters");
    if(saved){
        filters = JSON.parse(saved);
        for(let key in filters){
            const select = document.getElementById(key.replace("filter_",""));
            if(select) select.value = filters[key];
        }
    }

    load();
}

async function loadFilters(){

    let r = await fetch('/filters');
    let data = await r.json();

    const map = {
        type:"유형",
        homeaway:"홈원정",
        general:"일반",
        dir:"정역",
        handi:"핸디"
    };

    for(let key in map){
        let select = document.getElementById(key);
        select.innerHTML = `<option value="">${map[key]}</option>`;

        data[key].forEach(function(val){
            let opt=document.createElement("option");
            opt.value=val;
            opt.text=val;
            select.appendChild(opt);
        });

        select.onchange=function(){
            setFilter("filter_"+key,select.value);
        };
    }
}

function resetFilters(){
    filters={};
    localStorage.removeItem("sc_filters");
    document.querySelectorAll("select").forEach(function(s){
        s.value="";
    });
    load();
}

function setFilter(key,val){
    if(val==="") delete filters[key];
    else filters[key]=val;

    localStorage.setItem("sc_filters", JSON.stringify(filters));
    load();
}

async function load(){
    let query=new URLSearchParams(filters).toString();
    let r=await fetch('/matches?'+query);
    let data=await r.json();

    let html="";

    data.forEach(function(m){

        html+=`
        <div class="card">
        <b>${m[5]}</b><br>
        <b>${m[6]}</b> vs <b>${m[7]}</b>
        <button class="info-btn"
        onclick="location.href='/detail?year=${m[1]}&match=${m[3]}'">정보</button>
        <br>
        ${m[14]} · ${m[16]} · ${m[11]} · ${m[15]} · ${m[12]}
        <br>
        승 ${Number(m[8]).toFixed(2)} |
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
# Page2 - 상세 분석
# =====================================================

def bar_html(percent):
    return f"""
    <div class="bar-wrap">
        <div class="bar-inner" style="width:{percent}%;"></div>
    </div>
    """

@app.get("/detail", response_class=HTMLResponse)
def detail(year:int, match:int):

    df = CURRENT_DF

    if df.empty:
        return "<h2>데이터 없음</h2>"

    row_df = df[
        (df.iloc[:, COL_YEAR]==year) &
        (df.iloc[:, COL_MATCH]==match)
    ]

    if row_df.empty:
        return "<h2>경기 없음</h2>"

    row = row_df.iloc[0]

    league = row.iloc[COL_LEAGUE]
    home   = row.iloc[COL_HOME]
    away   = row.iloc[COL_AWAY]

    win_odds  = float(row.iloc[COL_WIN_ODDS])
    draw_odds = float(row.iloc[COL_DRAW_ODDS])
    lose_odds = float(row.iloc[COL_LOSE_ODDS])

    cond_label = f"{row.iloc[COL_TYPE]} · {row.iloc[COL_HOMEAWAY]} · {row.iloc[COL_GENERAL]} · {row.iloc[COL_DIR]} · {row.iloc[COL_HANDI]}"

    base_cond = {
        COL_TYPE:row.iloc[COL_TYPE],
        COL_HOMEAWAY:row.iloc[COL_HOMEAWAY],
        COL_GENERAL:row.iloc[COL_GENERAL],
        COL_DIR:row.iloc[COL_DIR],
        COL_HANDI:row.iloc[COL_HANDI]
    }

    base_df = run_filter(df, base_cond)
    base_dist = distribution(base_df)

    league_cond = base_cond.copy()
    league_cond[COL_LEAGUE] = league
    league_df = run_filter(df, league_cond)
    league_dist = distribution(league_df)

    ev_data = ev_ai(base_dist,row)

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>

body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}

.card{{
    background:#1e293b;
    padding:18px;
    border-radius:18px;
    margin-top:16px
}}

.flex{{
    display:flex;
    gap:20px;
    flex-wrap:wrap
}}

.col{{
    flex:1;
    min-width:260px
}}

.bar-wrap{{
    width:100%;
    background:#334155;
    border-radius:8px;
    overflow:hidden;
    height:14px;
    margin:6px 0 10px 0
}}

.bar-inner{{
    height:100%;
    background:#22c55e;
    max-width:100%
}}

button{{
    margin-top:10px;
    padding:6px 12px;
    border-radius:6px
}}

</style>
</head>
<body>

<h3>[{league}] {home} vs {away}</h3>
{cond_label} |
승 {win_odds:.2f} /
무 {draw_odds:.2f} /
패 {lose_odds:.2f}

<div class="card">
<h4>5조건 완전일치</h4>
총 {base_dist["총"]}경기<br>
승 {base_dist["wp"]}% ({base_dist["승"]})
{bar_html(base_dist["wp"])}
무 {base_dist["dp"]}% ({base_dist["무"]})
{bar_html(base_dist["dp"])}
패 {base_dist["lp"]}% ({base_dist["패"]})
{bar_html(base_dist["lp"])}
</div>

<div class="card flex">
<div class="col">
<h4>모든리그</h4>
총 {base_dist["총"]}경기<br>
승 {base_dist["wp"]}%{bar_html(base_dist["wp"])}
무 {base_dist["dp"]}%{bar_html(base_dist["dp"])}
패 {base_dist["lp"]}%{bar_html(base_dist["lp"])}
</div>
<div class="col">
<h4>{league}</h4>
총 {league_dist["총"]}경기<br>
승 {league_dist["wp"]}%{bar_html(league_dist["wp"])}
무 {league_dist["dp"]}%{bar_html(league_dist["dp"])}
패 {league_dist["lp"]}%{bar_html(league_dist["lp"])}
</div>
</div>

<div class="card">
<h4>AI 분석</h4>
추천: <b>{ev_data["추천"]}</b><br>
AI 등급: <b>{ev_data["AI"]}</b><br>
EV → 승 {ev_data["EV"]["승"]} /
무 {ev_data["EV"]["무"]} /
패 {ev_data["EV"]["패"]}
</div>

<a href="/page3?team={home}&league={league}"><button>홈팀 분석</button></a>
<a href="/page3?team={away}&league={league}"><button>원정팀 분석</button></a>
<a href="/page4?win={win_odds}&draw={draw_odds}&lose={lose_odds}"><button>배당 분석</button></a>

<br><br>
<a href="/"><button>← 경기목록</button></a>

</body>
</html>
"""

# =====================================================
# Page3 - 팀 분석
# =====================================================

@app.get("/page3", response_class=HTMLResponse)
def page3(team:str, league:str=None):

    df = CURRENT_DF

    if df.empty:
        return "<h2>데이터 없음</h2>"

    team_df = df[
        (df.iloc[:, COL_HOME]==team) |
        (df.iloc[:, COL_AWAY]==team)
    ]

    league_all_dist = distribution(team_df)

    if league:
        league_df = team_df[team_df.iloc[:, COL_LEAGUE]==league]
    else:
        league_df = pd.DataFrame()

    league_dist = distribution(league_df)

    home_game_df = team_df[team_df.iloc[:, COL_HOME]==team]
    away_game_df = team_df[team_df.iloc[:, COL_AWAY]==team]

    home_game_dist = distribution(home_game_df)
    away_game_dist = distribution(away_game_df)

    dir_home_df = df[
        (df.iloc[:, COL_HOME]==team) &
        (df.iloc[:, COL_HOMEAWAY]=="홈")
    ]

    dir_away_df = df[
        (df.iloc[:, COL_HOME]==team) &
        (df.iloc[:, COL_HOMEAWAY]=="원정")
    ]

    dir_home_dist = distribution(dir_home_df)
    dir_away_dist = distribution(dir_away_df)

    def block(title, dist):
        return f"""
        <div class="card">
        <h4>{title}</h4>
        총 {dist["총"]}경기<br>
        승 {dist["wp"]}%{bar_html(dist["wp"])}
        무 {dist["dp"]}%{bar_html(dist["dp"])}
        패 {dist["lp"]}%{bar_html(dist["lp"])}
        </div>
        """

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>

body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}

.card{{
    background:#1e293b;
    padding:18px;
    border-radius:18px;
    margin-top:16px
}}

.flex{{display:flex;gap:20px;flex-wrap:wrap}}
.col{{flex:1;min-width:260px}}

.bar-wrap{{
    width:100%;
    background:#334155;
    border-radius:8px;
    overflow:hidden;
    height:14px;
    margin:6px 0 10px 0
}}

.bar-inner{{
    height:100%;
    background:#22c55e;
    max-width:100%
}}

button{{margin-top:10px;padding:6px 12px;border-radius:6px}}

</style>
</head>
<body>

<h3>{team} 팀 분석</h3>

<div class="flex">
<div class="col">
{block(team+" | 모든리그", league_all_dist)}
</div>
<div class="col">
{block(team+" | "+(league if league else "리그없음"), league_dist)}
</div>
</div>

<div class="flex">
<div class="col">
{block(team+" | 홈경기", home_game_dist)}
</div>
<div class="col">
{block(team+" | 원정경기", away_game_dist)}
</div>
</div>

<div class="flex">
<div class="col">
{block(team+" | 홈방향", dir_home_dist)}
</div>
<div class="col">
{block(team+" | 원정방향", dir_away_dist)}
</div>
</div>

<a href="/"><button>← 경기목록</button></a>

</body>
</html>
"""

# =====================================================
# Page4 - 배당 분석
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4(win:float, draw:float, lose:float):

    df = CURRENT_DF

    if df.empty:
        return "<h2>데이터 없음</h2>"

    win  = round(float(win),2)
    draw = round(float(draw),2)
    lose = round(float(lose),2)

    win_series  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS],  errors="coerce").fillna(0).round(2)
    draw_series = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0).round(2)
    lose_series = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0).round(2)

    exact_df = df[
        (win_series==win) &
        (draw_series==draw) &
        (lose_series==lose)
    ]

    exact_dist = distribution(exact_df)

    win_df  = df[win_series==win]
    draw_df = df[draw_series==draw]
    lose_df = df[lose_series==lose]

    def block(title, dist):
        return f"""
        <div class="card">
        <h4>{title}</h4>
        총 {dist["총"]}경기<br>
        승 {dist["wp"]}%{bar_html(dist["wp"])}
        무 {dist["dp"]}%{bar_html(dist["dp"])}
        패 {dist["lp"]}%{bar_html(dist["lp"])}
        </div>
        """

    def general_loop(df_block):

        if df_block.empty:
            return "<div class='card'>데이터 없음</div>"

        html=""
        generals = sorted(df_block.iloc[:, COL_GENERAL].dropna().unique())

        for g in generals:
            sub = df_block[df_block.iloc[:, COL_GENERAL]==g]
            dist = distribution(sub)

            html += f"""
            <div class="card">
            <h4>일반 = {g}</h4>
            총 {dist["총"]}경기<br>
            승 {dist["wp"]}%{bar_html(dist["wp"])}
            무 {dist["dp"]}%{bar_html(dist["dp"])}
            패 {dist["lp"]}%{bar_html(dist["lp"])}
            </div>
            """

        return html

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>

body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}

.card{{
    background:#1e293b;
    padding:18px;
    border-radius:18px;
    margin-top:16px
}}

.bar-wrap{{
    width:100%;
    background:#334155;
    border-radius:8px;
    overflow:hidden;
    height:14px;
    margin:6px 0 10px 0
}}

.bar-inner{{
    height:100%;
    background:#22c55e;
    max-width:100%
}}

details{{margin-top:16px}}
button{{margin-top:10px;padding:6px 12px;border-radius:6px}}

</style>
</head>
<body>

<h3>배당 분석</h3>

{block(f"{win:.2f} / {draw:.2f} / {lose:.2f}", exact_dist)}

<details>
<summary>승배당 {win:.2f} 일반 분포</summary>
{general_loop(win_df)}
</details>

<details>
<summary>무배당 {draw:.2f} 일반 분포</summary>
{general_loop(draw_df)}
</details>

<details>
<summary>패배당 {lose:.2f} 일반 분포</summary>
{general_loop(lose_df)}
</details>

<br>
<a href="/"><button>← 경기목록</button></a>

</body>
</html>
"""

# =====================================================
# Health Check
# =====================================================

@app.get("/health")
def health():
    return {
        "data_loaded": not CURRENT_DF.empty,
        "rows": len(CURRENT_DF)
    }


# =====================================================
# 로컬 실행용
# =====================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)