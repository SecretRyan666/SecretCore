# =====================================================
# SecretCore PRO - 최신 통합코드
# 루프엔진 + UI + 추천로직 수정 + 영구저장 + 안정화 포함
# Python 3.14 배포 안정화 반영
# =====================================================

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import pandas as pd
import os
import hashlib

app = FastAPI()

# =====================================================
# 전역 설정
# =====================================================

DATA_FILE = "current_data.csv"
CURRENT_DF = pd.DataFrame()
LOGGED_IN = False

# =====================================================
# 컬럼 절대참조 (A~Q 고정)
# =====================================================

COL_NO = 0
COL_YEAR = 1
COL_ROUND = 2
COL_MATCH = 3
COL_DATE = 4
COL_LEAGUE = 5
COL_HOME = 6
COL_AWAY = 7
COL_ODD_WIN = 8
COL_ODD_DRAW = 9
COL_ODD_LOSE = 10
COL_GENERAL = 11
COL_HANDI = 12
COL_RESULT = 13
COL_TYPE = 14
COL_DIR = 15
COL_HOMEAWAY = 16

# =====================================================
# 서버 시작 시 데이터 자동 로드
# =====================================================

if os.path.exists(DATA_FILE):
    try:
        CURRENT_DF = pd.read_csv(DATA_FILE, encoding="utf-8-sig")
    except:
        CURRENT_DF = pd.DataFrame()

# =====================================================
# 공통 필터 (경기전 + 일반/핸디1)
# =====================================================

def base_filter(df):
    if df.empty:
        return df
    return df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        (df.iloc[:, COL_TYPE].isin(["일반", "핸디1"]))
    ]

# =====================================================
# 분포 계산
# =====================================================

def distribution(df):

    total = len(df)
    if total == 0:
        return {"승":0,"무":0,"패":0,"total":0}

    win = (df.iloc[:, COL_RESULT] == "승").sum()
    draw = (df.iloc[:, COL_RESULT] == "무").sum()
    lose = (df.iloc[:, COL_RESULT] == "패").sum()

    return {
        "승": int(win),
        "무": int(draw),
        "패": int(lose),
        "total": int(total)
    }

# =====================================================
# EV 계산
# =====================================================

def calc_ev(prob, odd):
    return (prob * odd) - 1

# =====================================================
# 추천 로직 (수정 반영)
# 1순위 완전일치 최다값
# 2순위 표본 30 이상 시 EV 비교
# 3순위 EV 차이 0.03 미만 시 무 우선
# =====================================================

def recommend(dist, odd_win, odd_draw, odd_lose):

    total = dist["total"]
    if total == 0:
        return "추천불가"

    p_win = dist["승"] / total
    p_draw = dist["무"] / total
    p_lose = dist["패"] / total

    # 1순위 - 최다값
    max_count = max(dist["승"], dist["무"], dist["패"])
    if max_count == dist["승"]:
        first = "승"
    elif max_count == dist["무"]:
        first = "무"
    else:
        first = "패"

    # 2순위 - EV 비교 (표본 30 이상)
    if total >= 30:
        ev_win = calc_ev(p_win, odd_win)
        ev_draw = calc_ev(p_draw, odd_draw)
        ev_lose = calc_ev(p_lose, odd_lose)

        evs = {"승":ev_win,"무":ev_draw,"패":ev_lose}
        sorted_ev = sorted(evs.items(), key=lambda x: x[1], reverse=True)

        # 3순위 - EV 차이 0.03 미만 시 무 우선
        if abs(sorted_ev[0][1] - sorted_ev[1][1]) < 0.03:
            return "무"

        return sorted_ev[0][0]

    return first

# =====================================================
# health check
# =====================================================

@app.get("/health")
def health():
    return {"status":"ok"}

# =====================================================
# 로그인 / 로그아웃
# =====================================================

ADMIN_ID = "admin"
ADMIN_PW_HASH = hashlib.sha256("1234".encode()).hexdigest()

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    global LOGGED_IN
    hashed = hashlib.sha256(password.encode()).hexdigest()

    if username == ADMIN_ID and hashed == ADMIN_PW_HASH:
        LOGGED_IN = True

    return RedirectResponse("/", status_code=302)


@app.get("/logout")
def logout():
    global LOGGED_IN
    LOGGED_IN = False
    return RedirectResponse("/", status_code=302)


# =====================================================
# 데이터 업로드 (영구 저장)
# =====================================================

@app.post("/upload-data")
async def upload_data(file: UploadFile = File(...)):
    global CURRENT_DF

    if not LOGGED_IN:
        return RedirectResponse("/", status_code=302)

    contents = await file.read()

    with open(DATA_FILE, "wb") as f:
        f.write(contents)

    try:
        CURRENT_DF = pd.read_csv(DATA_FILE, encoding="utf-8-sig")
    except:
        CURRENT_DF = pd.DataFrame()

    # 배당 숫자형 변환
    for col in [COL_ODD_WIN, COL_ODD_DRAW, COL_ODD_LOSE]:
        if not CURRENT_DF.empty:
            CURRENT_DF.iloc[:, col] = pd.to_numeric(
                CURRENT_DF.iloc[:, col],
                errors="coerce"
            ).fillna(0)

    return RedirectResponse("/", status_code=302)


# =====================================================
# 필터 고유값 자동 생성
# =====================================================

@app.get("/filters")
def filters():

    df = base_filter(CURRENT_DF)

    if df.empty:
        return {}

    return {
        "type": sorted(df.iloc[:, COL_TYPE].dropna().unique().tolist()),
        "homeaway": sorted(df.iloc[:, COL_HOMEAWAY].dropna().unique().tolist()),
        "general": sorted(df.iloc[:, COL_GENERAL].dropna().unique().tolist()),
        "dir": sorted(df.iloc[:, COL_DIR].dropna().unique().tolist()),
        "handi": sorted(df.iloc[:, COL_HANDI].dropna().unique().tolist())
    }


# =====================================================
# 경기 목록 API
# =====================================================

@app.get("/matches")
def matches(
    filter_type: str = "",
    filter_homeaway: str = "",
    filter_general: str = "",
    filter_dir: str = "",
    filter_handi: str = ""
):

    df = base_filter(CURRENT_DF)

    if filter_type:
        df = df[df.iloc[:, COL_TYPE] == filter_type]

    if filter_homeaway:
        df = df[df.iloc[:, COL_HOMEAWAY] == filter_homeaway]

    if filter_general:
        df = df[df.iloc[:, COL_GENERAL] == filter_general]

    if filter_dir:
        df = df[df.iloc[:, COL_DIR] == filter_dir]

    if filter_handi:
        df = df[df.iloc[:, COL_HANDI] == filter_handi]

    if df.empty:
        return []

    return df.values.tolist()

# =====================================================
# Page1 UI (f-string 제거 안정화 버전)
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():

    login_area = ""
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
body{background:#0f1720;color:white;font-family:Arial;padding:20px}
.header{display:flex;justify-content:space-between;align-items:center}
.filters{display:flex;gap:10px;margin-top:15px;flex-wrap:wrap}
select,button{padding:5px}
.card{background:#1e293b;padding:15px;border-radius:15px;margin-top:15px}
.info-btn{float:right;margin-left:10px}
</style>
</head>
<body>

<div class="header">
    <h2>SecretCore PRO</h2>
    <div>""" + login_area + """</div>
</div>

<div class="filters">
    <button onclick="resetFilters()">경기목록</button>
    <select id="type" onchange="setFilter('filter_type',this.value)">
        <option value="">유형</option>
    </select>
    <select id="homeaway" onchange="setFilter('filter_homeaway',this.value)">
        <option value="">홈원정</option>
    </select>
    <select id="general" onchange="setFilter('filter_general',this.value)">
        <option value="">일반</option>
    </select>
    <select id="dir" onchange="setFilter('filter_dir',this.value)">
        <option value="">정역</option>
    </select>
    <select id="handi" onchange="setFilter('filter_handi',this.value)">
        <option value="">핸디</option>
    </select>
</div>

<div id="list"></div>

<script>

let filters = {};

window.onload = async function() {
    await loadFilters();
    load();
}

async function loadFilters(){
    let r = await fetch('/filters');
    let data = await r.json();

    for (let key in data){
        let select = document.getElementById(key);
        if(!select) continue;
        data[key].forEach(val=>{
            let opt = document.createElement("option");
            opt.value = val;
            opt.text = val;
            select.appendChild(opt);
        });
    }
}

function resetFilters(){
    filters = {};
    document.querySelectorAll("select").forEach(s=>s.value="");
    load();
}

function setFilter(key,val){
    if(val==="") delete filters[key];
    else filters[key]=val;
    load();
}

async function load(){
    let query = new URLSearchParams(filters).toString();
    let r = await fetch('/matches?'+query);
    let data = await r.json();
    let html="";
    data.forEach(m=>{
        html+=`
        <div class="card">
            <b>${m[5]}</b><br>
            <b>${m[6]}</b> vs <b>${m[7]}</b>
            <button class="info-btn" onclick="location.href='/detail?year=${m[1]}&match=${m[3]}'">정보</button>
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
# Page2 - 통합 분석
# 5조건 완전일치 분포 + 추천 적용
# =====================================================

@app.get("/detail", response_class=HTMLResponse)
def detail(year: int, match: int):

    df = CURRENT_DF

    if df.empty:
        return HTMLResponse("<h3>데이터 없음</h3>")

    target = df[
        (df.iloc[:, COL_YEAR] == year) &
        (df.iloc[:, COL_MATCH] == match)
    ]

    if target.empty:
        return HTMLResponse("<h3>경기 찾을 수 없음</h3>")

    row = target.iloc[0]

    # 5조건 완전일치 필터
    filtered = df[
        (df.iloc[:, COL_TYPE] == row.iloc[COL_TYPE]) &
        (df.iloc[:, COL_HOMEAWAY] == row.iloc[COL_HOMEAWAY]) &
        (df.iloc[:, COL_GENERAL] == row.iloc[COL_GENERAL]) &
        (df.iloc[:, COL_DIR] == row.iloc[COL_DIR]) &
        (df.iloc[:, COL_HANDI] == row.iloc[COL_HANDI])
    ]

    dist = distribution(filtered)

    odd_win = float(row.iloc[COL_ODD_WIN])
    odd_draw = float(row.iloc[COL_ODD_DRAW])
    odd_lose = float(row.iloc[COL_ODD_LOSE])

    rec = recommend(dist, odd_win, odd_draw, odd_lose)

    total = dist["total"]

    if total > 0:
        p_win = round(dist["승"] / total * 100, 2)
        p_draw = round(dist["무"] / total * 100, 2)
        p_lose = round(dist["패"] / total * 100, 2)
    else:
        p_win = p_draw = p_lose = 0

    return """
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body{background:#0f1720;color:white;font-family:Arial;padding:20px}
    .box{background:#1e293b;padding:20px;border-radius:15px;margin-top:20px}
    </style>
    </head>
    <body>

    <h2>통합 분석</h2>

    <div class="box">
        <b>리그:</b> """ + str(row.iloc[COL_LEAGUE]) + """<br>
        <b>홈:</b> """ + str(row.iloc[COL_HOME]) + """<br>
        <b>원정:</b> """ + str(row.iloc[COL_AWAY]) + """<br>
        <hr>
        <b>5조건 표본수:</b> """ + str(total) + """<br><br>

        승: """ + str(dist["승"]) + """ (" + str(p_win) + """%)<br>
        무: """ + str(dist["무"]) + """ (" + str(p_draw) + """%)<br>
        패: """ + str(dist["패"]) + """ (" + str(p_lose) + """%)<br>

        <hr>
        <h3>추천: """ + rec + """</h3>
    </div>

    <br>
    <a href="/"><button>← 돌아가기</button></a>

    </body>
    </html>
    """

# =====================================================
# Page3 - 팀스캔
# 리그비교 → 경기위치 → 방향기준 구조
# =====================================================

@app.get("/team", response_class=HTMLResponse)
def team(team: str, league: str = ""):

    df = CURRENT_DF

    if df.empty:
        return HTMLResponse("<h3>데이터 없음</h3>")

    # 팀 전체 경기
    team_all = df[
        (df.iloc[:, COL_HOME] == team) |
        (df.iloc[:, COL_AWAY] == team)
    ]

    # 현재 리그 기준
    if league:
        team_league = team_all[team_all.iloc[:, COL_LEAGUE] == league]
    else:
        team_league = team_all

    # 홈 경기
    home_games = team_all[team_all.iloc[:, COL_HOME] == team]

    # 원정 경기
    away_games = team_all[team_all.iloc[:, COL_AWAY] == team]

    dist_all = distribution(team_all)
    dist_league = distribution(team_league)
    dist_home = distribution(home_games)
    dist_away = distribution(away_games)

    return """
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body{background:#0f1720;color:white;font-family:Arial;padding:20px}
    .box{background:#1e293b;padding:20px;border-radius:15px;margin-top:20px}
    </style>
    </head>
    <body>

    <h2>팀스캔 - """ + team + """</h2>

    <div class="box">
        <h3>리그 비교</h3>
        전체: """ + str(dist_all["total"]) + """ 경기<br>
        승 """ + str(dist_all["승"]) + """ / 무 """ + str(dist_all["무"]) + """ / 패 """ + str(dist_all["패"]) + """<br><br>

        현재리그: """ + str(dist_league["total"]) + """ 경기<br>
        승 """ + str(dist_league["승"]) + """ / 무 """ + str(dist_league["무"]) + """ / 패 """ + str(dist_league["패"]) + """
    </div>

    <div class="box">
        <h3>경기 위치</h3>
        홈경기: """ + str(dist_home["total"]) + """ 경기<br>
        승 """ + str(dist_home["승"]) + """ / 무 """ + str(dist_home["무"]) + """ / 패 """ + str(dist_home["패"]) + """<br><br>

        원정경기: """ + str(dist_away["total"]) + """ 경기<br>
        승 """ + str(dist_away["승"]) + """ / 무 """ + str(dist_away["무"]) + """ / 패 """ + str(dist_away["패"]) + """
    </div>

    <br>
    <a href="/"><button>← 돌아가기</button></a>

    </body>
    </html>
    """

# =====================================================
# Page4 - 배당스캔
# 승/무/패 단일배당 기준 분포 확인
# =====================================================

@app.get("/odds", response_class=HTMLResponse)
def odds(result: str, odd: float):

    df = CURRENT_DF

    if df.empty:
        return HTMLResponse("<h3>데이터 없음</h3>")

    if result == "승":
        col = COL_ODD_WIN
    elif result == "무":
        col = COL_ODD_DRAW
    else:
        col = COL_ODD_LOSE

    # 동일 배당 필터 (소수점 2자리 기준)
    filtered = df[
        round(df.iloc[:, col], 2) == round(float(odd), 2)
    ]

    dist = distribution(filtered)

    total = dist["total"]

    if total > 0:
        p_win = round(dist["승"] / total * 100, 2)
        p_draw = round(dist["무"] / total * 100, 2)
        p_lose = round(dist["패"] / total * 100, 2)
    else:
        p_win = p_draw = p_lose = 0

    return """
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body{background:#0f1720;color:white;font-family:Arial;padding:20px}
    .box{background:#1e293b;padding:20px;border-radius:15px;margin-top:20px}
    </style>
    </head>
    <body>

    <h2>배당 스캔 - """ + result + """ """ + str(round(odd,2)) + """</h2>

    <div class="box">
        표본수: """ + str(total) + """<br><br>

        승: """ + str(dist["승"]) + """ (" + str(p_win) + """%)<br>
        무: """ + str(dist["무"]) + """ (" + str(p_draw) + """%)<br>
        패: """ + str(dist["패"]) + """ (" + str(p_lose) + """%)<br>
    </div>

    <br>
    <a href="/"><button>← 돌아가기</button></a>

    </body>
    </html>
    """