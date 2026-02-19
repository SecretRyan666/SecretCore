from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import pandas as pd
import os

app = FastAPI()

# =====================================================
# 절대참조 인덱스 (고정)
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

EXPECTED_COLS = 17

DATA_FILE = "current_data.csv"

CURRENT_DF = pd.DataFrame()
LOGGED_IN = False
FAVORITES = []
LEDGER = []

# =====================================================
# 데이터 로드 (안정화 강화)
# =====================================================

def validate_structure(df):
    if df.shape[1] < EXPECTED_COLS:
        raise ValueError("컬럼 구조 오류: 17개 미만")

def load_data():
    global CURRENT_DF

    if os.path.exists(DATA_FILE):
        df = pd.read_csv(
            DATA_FILE,
            encoding="utf-8-sig",
            dtype=str,          # 🔥 문자열 유지
            low_memory=False
        )

        validate_structure(df)

        # 🔥 배당은 문자열 그대로 유지 (완전일치 오차 0 보장)
        CURRENT_DF = df

load_data()

# =====================================================
# 루프엔진
# =====================================================

def run_filter(df, conditions: dict):
    if df.empty:
        return df

    filtered = df
    for col_idx, val in conditions.items():
        if val is None or val == "":
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

    wp = round((win/total)*100,2) if total else 0
    dp = round((draw/total)*100,2) if total else 0
    lp = round((lose/total)*100,2) if total else 0

    return {
        "총":int(total),
        "승":int(win),
        "무":int(draw),
        "패":int(lose),
        "wp":wp,
        "dp":dp,
        "lp":lp
    }


def ev_ai(dist, row):
    try:
        win_odds  = float(row.iloc[COL_WIN_ODDS])
        draw_odds = float(row.iloc[COL_DRAW_ODDS])
        lose_odds = float(row.iloc[COL_LOSE_ODDS])
    except:
        return {
            "EV":{"승":0,"무":0,"패":0},
            "추천":"없음"
        }

    ev_w = dist["wp"]/100 * win_odds  - 1
    ev_d = dist["dp"]/100 * draw_odds - 1
    ev_l = dist["lp"]/100 * lose_odds - 1

    ev_map = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_map, key=ev_map.get)

    return {
        "EV":{
            "승":round(ev_w,3),
            "무":round(ev_d,3),
            "패":round(ev_l,3)
        },
        "추천":best
    }

# =====================================================
# 헬스체크
# =====================================================

@app.get("/health")
def health():
    return {
        "data_loaded": not CURRENT_DF.empty,
        "rows": len(CURRENT_DF)
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
# 업로드 처리 (문자열 유지 구조)
# =====================================================

@app.post("/upload-data")
def upload(file: UploadFile = File(...)):
    global CURRENT_DF

    df = pd.read_csv(
        file.file,
        encoding="utf-8-sig",
        dtype=str,
        low_memory=False
    )

    validate_structure(df)

    # 🔥 배당은 문자열 그대로 저장
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
    CURRENT_DF = df

    return RedirectResponse("/", status_code=302)


# =====================================================
# 필터 고유값 API
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
# 경기목록 API (Page1 전용 고정조건 적용)
# 기본조건: 경기전 + 유형 일반/핸디1
# =====================================================

@app.get("/matches")
def matches(
    type: str = None,
    homeaway: str = None,
    general: str = None,
    dir: str = None,
    handi: str = None
):

    df = CURRENT_DF

    if df.empty:
        return []

    # 🔒 Page1 고정조건
    base_df = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        (
            (df.iloc[:, COL_TYPE] == "일반") |
            (df.iloc[:, COL_TYPE] == "핸디1")
        )
    ]

    conditions = {}

    if type:
        conditions[COL_TYPE] = type
    if homeaway:
        conditions[COL_HOMEAWAY] = homeaway
    if general:
        conditions[COL_GENERAL] = general
    if dir:
        conditions[COL_DIR] = dir
    if handi:
        conditions[COL_HANDI] = handi

    filtered = run_filter(base_df, conditions)

    return filtered.values.tolist()

# =====================================================
# Page1 - DarkPro 원본 복구 + 증분 병합
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():

    if not LOGGED_IN:
        return """
        <html lang="ko">
        <head>
        <meta charset="utf-8">
        </head>
        <body style="background:#0f1720;color:white;
                     display:flex;justify-content:center;
                     align-items:center;height:100vh;font-family:Arial;">
        <form action="/login" method="post">
            <h2>Login</h2>
            <input name="username" placeholder="ID"><br><br>
            <input name="password" type="password" placeholder="PW"><br><br>
            <button type="submit">로그인</button>
        </form>
        </body>
        </html>
        """

    return """
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<style>

body{
background:#0f1720;
color:white;
font-family:Arial;
margin:0;
}

.header{
display:flex;
justify-content:space-between;
align-items:center;
padding:14px 18px;
background:rgba(17,24,39,0.95);
position:sticky;
top:0;
z-index:50;
}

.logo{
font-weight:700;
font-size:18px;
background:linear-gradient(90deg,#22d3ee,#38bdf8);
-webkit-background-clip:text;
color:transparent;
}

.top-icons{
display:flex;
gap:18px;
font-size:18px;
}

.top-icons div{
cursor:pointer;
padding:6px;
border-radius:8px;
}

.top-icons div:hover{
background:rgba(255,255,255,0.08);
}

.condition-bar{
padding:8px 16px;
font-size:12px;
opacity:0.75;
border-bottom:1px solid rgba(255,255,255,0.05);
}

.card{
background:linear-gradient(145deg,#1e293b,#111827);
margin:14px;
padding:18px;
border-radius:18px;
position:relative;
box-shadow:0 10px 30px rgba(0,0,0,0.4);
}

.league{
color:#38bdf8;
font-weight:600;
font-size:13px;
}

.match{
margin-top:4px;
margin-bottom:6px;
}

.condition{
font-size:12px;
opacity:0.7;
margin-bottom:6px;
}

.info-btn{
position:absolute;
right:14px;
top:50%;
transform:translateY(-120%);
font-size:12px;
cursor:pointer;
}

.star-btn{
position:absolute;
right:14px;
top:50%;
transform:translateY(20%);
font-size:18px;
cursor:pointer;
color:#6b7280;
}

.star-active{
color:#facc15;
}

.bottom-nav{
position:fixed;
bottom:0;
width:100%;
background:#111827;
display:flex;
justify-content:space-around;
padding:12px 0;
font-size:20px;
}

</style>
</head>

<body>

<div class="header">
    <div class="logo">SecretCore PRO</div>
    <div class="top-icons">
        <div onclick="location.href='/page-upload'">📤</div>
        <div onclick="resetFilter()">🔄</div>
        <div onclick="location.href='/favorites'">⭐</div>
        <div onclick="location.href='/logout'">👤</div>
    </div>
</div>

<div class="condition-bar" id="conditionBar">
경기전 · 일반/핸디1
</div>

<div id="list" style="padding-bottom:100px;"></div>

<div class="bottom-nav">
    <a href="/ledger">🏠</a>
    <a href="/memo">📝</a>
    <a href="/capture">📸</a>
    <a href="/favorites">⭐</a>
</div>

<script>

async function toggleFav(home,away,el){
    let res = await fetch("/fav-toggle",{
        method:"POST",
        headers:{"Content-Type":"application/x-www-form-urlencoded"},
        body:`home=${home}&away=${away}`
    });

    let data = await res.json();

    if(data.status=="added"){
        el.classList.add("star-active");
    }else{
        el.classList.remove("star-active");
    }
}

function goDetail(year,match){
    location.href="/detail?year="+year+"&match="+match;
}

async function load(){

    let r = await fetch('/matches');
    let data = await r.json();

    let html="";

    data.forEach(function(m){

        html += `
        <div class="card">
            <div class="league">${m[5]}</div>
            <div class="match"><b>${m[6]}</b> vs <b>${m[7]}</b></div>

            <div class="condition">
            ${m[14]} · ${m[16]} · ${m[11]} · ${m[15]} · ${m[12]}
            </div>

            <div>
            승 ${Number(m[8]).toFixed(2)} |
            무 ${Number(m[9]).toFixed(2)} |
            패 ${Number(m[10]).toFixed(2)}
            </div>

            <div class="info-btn"
                 onclick="goDetail(${m[1]},${m[3]})">정보</div>

            <div class="star-btn"
                 onclick="toggleFav('${m[6]}','${m[7]}',this)">★</div>

        </div>
        `;
    });

    document.getElementById("list").innerHTML = html;
}

load();

</script>

</body>
</html>
"""

# =====================================================
# Page2 - 상세 분석 (좌우 비교 + EV 하단 포함)
# =====================================================

def bar_html(percent):
    return f"""
    <div style="
        width:100%;
        background:#334155;
        border-radius:8px;
        overflow:hidden;
        height:14px;
        margin:6px 0 10px 0">
        <div style="
            height:100%;
            width:{percent}%;
            background:#22c55e;">
        </div>
    </div>
    """


@app.get("/detail", response_class=HTMLResponse)
def detail(year:int, match:int):

    df = CURRENT_DF
    if df.empty:
        return "<h2>데이터 없음</h2>"

    row_df = df[
        (df.iloc[:, COL_YEAR] == str(year)) &
        (df.iloc[:, COL_MATCH] == str(match))
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

    # 🔒 5조건
    base_cond = {
        COL_TYPE: row.iloc[COL_TYPE],
        COL_HOMEAWAY: row.iloc[COL_HOMEAWAY],
        COL_GENERAL: row.iloc[COL_GENERAL],
        COL_DIR: row.iloc[COL_DIR],
        COL_HANDI: row.iloc[COL_HANDI]
    }

    base_df = run_filter(df, base_cond)
    base_dist = distribution(base_df)

    # 동일리그
    league_cond = base_cond.copy()
    league_cond[COL_LEAGUE] = league

    league_df = run_filter(df, league_cond)
    league_dist = distribution(league_df)

    ev_data = ev_ai(base_dist, row)

    cond_label = f"{row.iloc[COL_TYPE]} · {row.iloc[COL_HOMEAWAY]} · {row.iloc[COL_GENERAL]} · {row.iloc[COL_DIR]} · {row.iloc[COL_HANDI]}"

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}
.card{{background:#1e293b;padding:18px;border-radius:16px;margin-top:18px}}
.flex{{display:flex;gap:20px;flex-wrap:wrap}}
.col{{flex:1;min-width:260px}}
button{{margin-top:10px;padding:6px 12px;border-radius:6px}}
</style>
</head>
<body>

<h3>[{league}] {home} vs {away}</h3>
{cond_label}<br>
승 {win_odds:.2f} /
무 {draw_odds:.2f} /
패 {lose_odds:.2f}

<div class="card">
<h4>조건 분포 비교</h4>

<div class="flex">
<div class="col">
<b>전체 5조건</b><br>
총 {base_dist["총"]}경기<br>
승 {base_dist["wp"]}% ({base_dist["승"]})
{bar_html(base_dist["wp"])}
무 {base_dist["dp"]}% ({base_dist["무"]})
{bar_html(base_dist["dp"])}
패 {base_dist["lp"]}% ({base_dist["패"]})
{bar_html(base_dist["lp"])}
</div>

<div class="col">
<b>{league} 동일조건</b><br>
총 {league_dist["총"]}경기<br>
승 {league_dist["wp"]}% ({league_dist["승"]})
{bar_html(league_dist["wp"])}
무 {league_dist["dp"]}% ({league_dist["무"]})
{bar_html(league_dist["dp"])}
패 {league_dist["lp"]}% ({league_dist["패"]})
{bar_html(league_dist["lp"])}
</div>
</div>

<hr style="margin:18px 0;border-color:#334155">

<b>EV 분석</b><br>
추천: <b>{ev_data["추천"]}</b><br>
EV → 승 {ev_data["EV"]["승"]} /
무 {ev_data["EV"]["무"]} /
패 {ev_data["EV"]["패"]}

</div>

<br>

<a href="/page3?team={home}&league={league}">
<button>홈팀 분석</button>
</a>

<a href="/page3?team={away}&league={league}">
<button>원정팀 분석</button>
</a>

<a href="/page4?win={win_odds:.2f}&draw={draw_odds:.2f}&lose={lose_odds:.2f}">
<button>배당 분석</button>
</a>

<br><br>
<a href="/"><button>← 경기목록</button></a>

</body>
</html>
"""

# =====================================================
# Page3 - 팀 분석 (상단 고정 + 하단 접기)
# =====================================================

@app.get("/page3", response_class=HTMLResponse)
def page3(team:str, league:str=None):

    df = CURRENT_DF
    if df.empty:
        return "<h2>데이터 없음</h2>"

    # 🔒 팀 전체 경기
    team_df = df[
        (df.iloc[:, COL_HOME] == team) |
        (df.iloc[:, COL_AWAY] == team)
    ]

    if team_df.empty:
        return "<h2>팀 데이터 없음</h2>"

    # 🔒 상단 고정 조건: 유형 + 팀 + 홈원정 + 일반
    base_cond = {
        COL_TYPE: team_df.iloc[0][COL_TYPE],
        COL_HOMEAWAY: team_df.iloc[0][COL_HOMEAWAY],
        COL_GENERAL: team_df.iloc[0][COL_GENERAL]
    }

    top_df = run_filter(team_df, base_cond)
    top_dist = distribution(top_df)

    # EV 계산용 기준 row
    row = team_df.iloc[0]
    ev_data = ev_ai(top_dist, row)

    # 🔒 하단: 유형 + 팀 + 홈원정 (일반 제거)
    bottom_cond = {
        COL_TYPE: team_df.iloc[0][COL_TYPE],
        COL_HOMEAWAY: team_df.iloc[0][COL_HOMEAWAY]
    }

    bottom_df = run_filter(team_df, bottom_cond)

    # 일반값별 세로 나열
    generals = sorted(bottom_df.iloc[:, COL_GENERAL].dropna().unique())

    def block(title, dist):
        return f"""
        <div style="margin-bottom:10px">
        총 {dist["총"]}경기<br>
        승 {dist["wp"]}%<br>
        무 {dist["dp"]}%<br>
        패 {dist["lp"]}%
        </div>
        """

    general_html = ""
    for g in generals:
        sub = bottom_df[bottom_df.iloc[:, COL_GENERAL] == g]
        dist = distribution(sub)

        general_html += f"""
        <details style="margin-top:8px">
            <summary>일반 = {g}</summary>
            {block("", dist)}
        </details>
        """

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}
.card{{background:#1e293b;padding:18px;border-radius:16px;margin-top:18px}}
.fixed{{position:sticky;top:0;background:#0f1720;padding-bottom:10px}}
</style>
</head>
<body>

<h3>{team} 팀 분석</h3>

<div class="card fixed">
<h4>상단 고정 분포 (유형+팀+홈원정+일반)</h4>

총 {top_dist["총"]}경기<br>
승 {top_dist["wp"]}%<br>
무 {top_dist["dp"]}%<br>
패 {top_dist["lp"]}%<br><br>

<b>EV 분석</b><br>
추천: {ev_data["추천"]}<br>
EV → 승 {ev_data["EV"]["승"]} /
무 {ev_data["EV"]["무"]} /
패 {ev_data["EV"]["패"]}

</div>

<div class="card">
<h4>일반값별 분포 (유형+팀+홈원정)</h4>
{general_html}
</div>

<br>
<a href="/"><button>← 경기목록</button></a>

</body>
</html>
"""

# =====================================================
# Page4 - 배당 분석 (완전일치 + 3열 비교 + 접기)
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4(win:str, draw:str, lose:str):

    df = CURRENT_DF
    if df.empty:
        return "<h2>데이터 없음</h2>"

    # 🔒 문자열 완전일치 (오차 0)
    win_str  = win
    draw_str = draw
    lose_str = lose

    # =====================================================
    # 1️⃣ 완전일치 (승/무/패 모두 동일)
    # =====================================================

    exact_df = df[
        (df.iloc[:, COL_WIN_ODDS]  == win_str) &
        (df.iloc[:, COL_DRAW_ODDS] == draw_str) &
        (df.iloc[:, COL_LOSE_ODDS] == lose_str)
    ]

    exact_dist = distribution(exact_df)

    # EV 계산 기준 row (없으면 0 처리)
    if not exact_df.empty:
        row = exact_df.iloc[0]
        ev_exact = ev_ai(exact_dist, row)
    else:
        ev_exact = {"추천":"없음","EV":{"승":0,"무":0,"패":0}}

    # =====================================================
    # 2️⃣ 승 / 무 / 패 단일 동일
    # =====================================================

    win_df  = df[df.iloc[:, COL_WIN_ODDS]  == win_str]
    draw_df = df[df.iloc[:, COL_DRAW_ODDS] == draw_str]
    lose_df = df[df.iloc[:, COL_LOSE_ODDS] == lose_str]

    win_dist  = distribution(win_df)
    draw_dist = distribution(draw_df)
    lose_dist = distribution(lose_df)

    def block(title, dist):
        return f"""
        <div style="margin-bottom:10px">
        총 {dist["총"]}경기<br>
        승 {dist["wp"]}% ({dist["승"]})<br>
        무 {dist["dp"]}% ({dist["무"]})<br>
        패 {dist["lp"]}% ({dist["패"]})
        </div>
        """

    # 일반값별 세로 나열
    def general_loop(df_block):

        if df_block.empty:
            return "<div>데이터 없음</div>"

        html = ""
        generals = sorted(df_block.iloc[:, COL_GENERAL].dropna().unique())

        for g in generals:
            sub = df_block[df_block.iloc[:, COL_GENERAL] == g]
            dist = distribution(sub)

            html += f"""
            <details style="margin-top:6px">
                <summary>일반 = {g}</summary>
                {block("", dist)}
            </details>
            """

        return html

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}
.card{{background:#1e293b;padding:18px;border-radius:16px;margin-top:18px}}
.flex{{display:flex;gap:20px;flex-wrap:wrap}}
.col{{flex:1;min-width:240px}}
hr{{border-color:#334155}}
</style>
</head>
<body>

<h3>배당 분석</h3>
승 {win_str} / 무 {draw_str} / 패 {lose_str}

<!-- 카드1 : 완전일치 + EV -->
<div class="card">
<h4>완전일치 통계</h4>
{block("", exact_dist)}

<hr>

<b>EV 분석</b><br>
추천: {ev_exact["추천"]}<br>
EV → 승 {ev_exact["EV"]["승"]} /
무 {ev_exact["EV"]["무"]} /
패 {ev_exact["EV"]["패"]}
</div>

<!-- 카드2 : 3열 비교 -->
<div class="card">
<h4>단일 배당 비교</h4>

<div class="flex">

<div class="col">
<b>승배당 동일</b>
{block("", win_dist)}
{general_loop(win_df)}
</div>

<div class="col">
<b>무배당 동일</b>
{block("", draw_dist)}
{general_loop(draw_df)}
</div>

<div class="col">
<b>패배당 동일</b>
{block("", lose_dist)}
{general_loop(lose_df)}
</div>

</div>
</div>

<br>
<a href="/"><button>← 경기목록</button></a>

</body>
</html>
"""