# =====================================================
# SecretCore PRO - FULL VERSION
# 루프엔진 확장 + 일반/리그 매칭 + EV/AI + 추천로직 수정
# Python 3.11 안정화 기준
# =====================================================

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import pandas as pd
import os
import hashlib
import math

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
# 기본 필터 (경기전 + 일반/핸디1)
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
# AI 등급 계산
# =====================================================

def calc_ai_grade(ev):

    if ev >= 0.15:
        return "S"
    elif ev >= 0.08:
        return "A"
    elif ev >= 0.03:
        return "B"
    elif ev >= 0:
        return "C"
    else:
        return "D"

# =====================================================
# 추천 로직 (수정 적용)
# 1순위: 완전일치 최다값
# 2순위: 표본 30 이상 EV 비교
# 3순위: EV 차이 0.03 미만 무 우선
# =====================================================

def recommend(dist, odd_win, odd_draw, odd_lose):

    total = dist["total"]

    if total == 0:
        return "추천불가", 0, "D"

    p_win = dist["승"] / total
    p_draw = dist["무"] / total
    p_lose = dist["패"] / total

    max_count = max(dist["승"], dist["무"], dist["패"])

    if max_count == dist["승"]:
        first = "승"
    elif max_count == dist["무"]:
        first = "무"
    else:
        first = "패"

    ev_win = calc_ev(p_win, odd_win)
    ev_draw = calc_ev(p_draw, odd_draw)
    ev_lose = calc_ev(p_lose, odd_lose)

    evs = {"승":ev_win,"무":ev_draw,"패":ev_lose}

    if total >= 30:
        sorted_ev = sorted(evs.items(), key=lambda x: x[1], reverse=True)

        if abs(sorted_ev[0][1] - sorted_ev[1][1]) < 0.03:
            chosen = "무"
        else:
            chosen = sorted_ev[0][0]
    else:
        chosen = first

    ev_value = evs[chosen]
    grade = calc_ai_grade(ev_value)

    return chosen, round(ev_value,4), grade

# =====================================================
# Health Check
# =====================================================

@app.get("/health")
def health():
    return {"status":"ok"}

# =====================================================
# 관리자 로그인
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
# 데이터 업로드 (영구 저장 구조)
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
    if not CURRENT_DF.empty:
        for col in [COL_ODD_WIN, COL_ODD_DRAW, COL_ODD_LOSE]:
            CURRENT_DF.iloc[:, col] = pd.to_numeric(
                CURRENT_DF.iloc[:, col],
                errors="coerce"
            ).fillna(0)

    return RedirectResponse("/", status_code=302)


# =====================================================
# 필터 고유값 자동 생성 (루프엔진 기반)
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
# 경기 목록 API (Page1 연동)
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
# Page1 - 메인 화면 (안정화 버전)
# f-string 제거 + 문자열 연결 방식
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
# Page2 - 통합 분석 FULL
# 5조건 완전일치
# 일반전체 / 일반매칭
# 리그전체 / 리그매칭
# EV / AI / 추천 포함
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

    # =====================================================
    # 5조건 완전일치
    # =====================================================

    full_match = df[
        (df.iloc[:, COL_TYPE] == row.iloc[COL_TYPE]) &
        (df.iloc[:, COL_HOMEAWAY] == row.iloc[COL_HOMEAWAY]) &
        (df.iloc[:, COL_GENERAL] == row.iloc[COL_GENERAL]) &
        (df.iloc[:, COL_DIR] == row.iloc[COL_DIR]) &
        (df.iloc[:, COL_HANDI] == row.iloc[COL_HANDI])
    ]

    dist_full = distribution(full_match)

    # =====================================================
    # 일반전체 / 일반매칭
    # =====================================================

    general_all = df[df.iloc[:, COL_GENERAL] == row.iloc[COL_GENERAL]]
    dist_general_all = distribution(general_all)

    general_match = full_match[
        full_match.iloc[:, COL_GENERAL] == row.iloc[COL_GENERAL]
    ]
    dist_general_match = distribution(general_match)

    # =====================================================
    # 리그전체 / 리그매칭
    # =====================================================

    league_all = df[df.iloc[:, COL_LEAGUE] == row.iloc[COL_LEAGUE]]
    dist_league_all = distribution(league_all)

    league_match = full_match[
        full_match.iloc[:, COL_LEAGUE] == row.iloc[COL_LEAGUE]
    ]
    dist_league_match = distribution(league_match)

    # =====================================================
    # 추천 계산 (완전일치 기준)
    # =====================================================

    odd_win = float(row.iloc[COL_ODD_WIN])
    odd_draw = float(row.iloc[COL_ODD_DRAW])
    odd_lose = float(row.iloc[COL_ODD_LOSE])

    rec, ev_value, grade = recommend(
        dist_full,
        odd_win,
        odd_draw,
        odd_lose
    )

    # =====================================================
    # HTML 출력
    # =====================================================

    def block(title, dist):
        return """
        <div class='box'>
        <h3>""" + title + """</h3>
        표본: """ + str(dist["total"]) + """<br>
        승 """ + str(dist["승"]) + """ /
        무 """ + str(dist["무"]) + """ /
        패 """ + str(dist["패"]) + """
        </div>
        """

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

    <h2>통합 분석 - FULL</h2>

    """ + block("5조건 완전일치", dist_full) + """
    """ + block("일반전체", dist_general_all) + """
    """ + block("일반매칭", dist_general_match) + """
    """ + block("리그전체", dist_league_all) + """
    """ + block("리그매칭", dist_league_match) + """

    <div class='box'>
    <h3>추천 결과</h3>
    추천: """ + rec + """<br>
    EV: """ + str(ev_value) + """<br>
    AI 등급: """ + grade + """
    </div>

    <br>
    <a href="/"><button>← 돌아가기</button></a>

    </body>
    </html>
    """

# =====================================================
# Page3 - 팀스캔 FULL
# 1단: 리그 비교
# 2단: 경기 위치
# 3단: 방향 기준
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

    if team_all.empty:
        return HTMLResponse("<h3>팀 경기 없음</h3>")

    # =====================================================
    # 1단: 리그 비교
    # =====================================================

    dist_all = distribution(team_all)

    if league:
        team_league = team_all[
            team_all.iloc[:, COL_LEAGUE] == league
        ]
    else:
        team_league = team_all

    dist_league = distribution(team_league)

    # =====================================================
    # 2단: 경기 위치
    # =====================================================

    home_games = team_all[
        team_all.iloc[:, COL_HOME] == team
    ]

    away_games = team_all[
        team_all.iloc[:, COL_AWAY] == team
    ]

    dist_home = distribution(home_games)
    dist_away = distribution(away_games)

    # =====================================================
    # 3단: 방향 기준 (홈기준/원정기준)
    # =====================================================

    direction_home = df[
        df.iloc[:, COL_HOME] == team
    ]

    direction_away = df[
        df.iloc[:, COL_AWAY] == team
    ]

    dist_dir_home = distribution(direction_home)
    dist_dir_away = distribution(direction_away)

    # =====================================================
    # 출력 블록 함수
    # =====================================================

    def block(title, dist):
        return """
        <div class='box'>
        <h3>""" + title + """</h3>
        표본: """ + str(dist["total"]) + """<br>
        승 """ + str(dist["승"]) + """ /
        무 """ + str(dist["무"]) + """ /
        패 """ + str(dist["패"]) + """
        </div>
        """

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

    """ + block("리그 전체", dist_all) + """
    """ + block("현재 리그", dist_league) + """
    """ + block("홈 경기", dist_home) + """
    """ + block("원정 경기", dist_away) + """
    """ + block("방향 기준 - 홈", dist_dir_home) + """
    """ + block("방향 기준 - 원정", dist_dir_away) + """

    <br>
    <a href="/"><button>← 돌아가기</button></a>

    </body>
    </html>
    """

# =====================================================
# Page4 - 배당스캔 FULL
# 완전일치 + 전체루프 + 매칭 분리 구조
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

    # =====================================================
    # 동일 배당 전체 분포
    # =====================================================

    all_same = df[
        round(df.iloc[:, col], 2) == round(float(odd), 2)
    ]

    dist_all = distribution(all_same)

    # =====================================================
    # 기본 필터 적용 매칭 분포
    # =====================================================

    base = base_filter(df)

    match_same = base[
        round(base.iloc[:, col], 2) == round(float(odd), 2)
    ]

    dist_match = distribution(match_same)

    # =====================================================
    # 출력 블록
    # =====================================================

    def block(title, dist):
        return """
        <div class='box'>
        <h3>""" + title + """</h3>
        표본: """ + str(dist["total"]) + """<br>
        승 """ + str(dist["승"]) + """ /
        무 """ + str(dist["무"]) + """ /
        패 """ + str(dist["패"]) + """
        </div>
        """

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

    <h2>배당스캔 - """ + result + """ """ + str(round(odd,2)) + """</h2>

    """ + block("전체 동일배당", dist_all) + """
    """ + block("기본필터 매칭배당", dist_match) + """

    <br>
    <a href="/"><button>← 돌아가기</button></a>

    </body>
    </html>
    """