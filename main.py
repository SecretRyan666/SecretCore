from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import pandas as pd
from io import BytesIO
import os

app = FastAPI()

# =====================================================
# 고정 파일 경로 (영구 저장)
# =====================================================

DATA_FILE = "current_data.csv"

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
# 서버 시작 시 자동 로드
# =====================================================

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_csv(DATA_FILE, encoding="utf-8-sig", low_memory=False)

# =====================================================
# 안정화
# =====================================================

def check_df():
    if CURRENT_DF.empty:
        return False
    if CURRENT_DF.shape[1] < 17:
        return False
    return True

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

def text_bar(p):
    blocks = int(round(p / 5))
    return "█"*blocks + "░"*(20-blocks)

# =====================================================
# 간단 관리자 로그인 (세션 방식 단순화)
# =====================================================

ADMIN_ID = "ryan"
ADMIN_PW = "963258"   # 실제 운영 시 환경변수 + 해시로 교체 권장

LOGGED_IN = False


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    global LOGGED_IN
    if username == ADMIN_ID and password == ADMIN_PW:
        LOGGED_IN = True
    return RedirectResponse("/", status_code=302)


@app.get("/logout")
def logout():
    global LOGGED_IN
    LOGGED_IN = False
    return RedirectResponse("/", status_code=302)


# =====================================================
# 업로드 (디스크 저장 + 덮어쓰기)
# =====================================================

@app.post("/upload-data")
def upload(file: UploadFile = File(...)):
    global CURRENT_DF

    raw = file.file.read()
    df = pd.read_csv(BytesIO(raw), encoding="utf-8-sig", low_memory=False)

    if df.shape[1] < 17:
        return {"error":"컬럼 구조 오류"}

    # 🔥 먼저 숫자형 변환
    df.iloc[:, COL_WIN_ODDS]  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_DRAW_ODDS] = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_LOSE_ODDS] = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0).round(2)

    # 🔥 그 다음 디스크 저장
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

    CURRENT_DF = df

    return RedirectResponse("/", status_code=302)

# =====================================================
# Page1 - 경기목록 API
# =====================================================

@app.get("/matches")
def matches(filter_type:str=None,
            filter_homeaway:str=None,
            filter_general:str=None,
            filter_dir:str=None,
            filter_handi:str=None):

    if not check_df():
        return []

    df = CURRENT_DF

    m = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        ((df.iloc[:, COL_TYPE] == "일반") |
         (df.iloc[:, COL_TYPE] == "핸디1"))
    ]

    conditions = {
        COL_TYPE: filter_type,
        COL_HOMEAWAY: filter_homeaway,
        COL_GENERAL: filter_general,
        COL_DIR: filter_dir,
        COL_HANDI: filter_handi
    }

    m = run_filter(m, conditions)

    return m.values.tolist()


# =====================================================
# Page1 - UI
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():

    login_area = ""

    if LOGGED_IN:
        login_area = """
        <form action="/upload-data" method="post" enctype="multipart/form-data" style="display:inline;">
            <input type="file" name="file" required>
            <button type="submit">파일 업로드</button>
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

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}
.header{{display:flex;justify-content:space-between;align-items:center}}
.filters{{display:flex;gap:10px;margin-top:15px;flex-wrap:wrap}}
select,button{{padding:5px}}
.card{{background:#1e293b;padding:15px;border-radius:15px;margin-top:15px}}
</style>
</head>
<body>

<div class="header">
    <h2>SecretCore PRO</h2>
    <div>{login_area}</div>
</div>

<div class="filters">
    <button onclick="resetFilters()">경기목록</button>
    <select onchange="setFilter('filter_type',this.value)">
        <option value="">유형</option>
    </select>
    <select onchange="setFilter('filter_homeaway',this.value)">
        <option value="">홈원정</option>
    </select>
    <select onchange="setFilter('filter_general',this.value)">
        <option value="">일반</option>
    </select>
    <select onchange="setFilter('filter_dir',this.value)">
        <option value="">정역</option>
    </select>
    <select onchange="setFilter('filter_handi',this.value)">
        <option value="">핸디</option>
    </select>
</div>

<div id="list"></div>

<script>
let filters = {{}};

window.onload = load;

function resetFilters(){{
    filters = {{}};
    load();
}}

function setFilter(key,val){{
    if(val==="") delete filters[key];
    else filters[key]=val;
    load();
}}

async function load(){{
    let query = new URLSearchParams(filters).toString();
    let r = await fetch('/matches?'+query);
    let data = await r.json();
    let html="";
    data.forEach(m=>{{
        html+=`
        <div class="card">
            <b>${{m[5]}}</b><br>
            <b>${{m[6]}}</b> vs <b>${{m[7]}}</b>
            <button onclick="location.href='/detail?year=${{m[1]}}&match=${{m[3]}}'">정보</button>
            <br>
            ${{m[14]}} · ${{m[16]}} · ${{m[11]}} · ${{m[15]}} · ${{m[12]}}
            <br>
            승 ${{Number(m[8]).toFixed(2)}} |
            무 ${{Number(m[9]).toFixed(2)}} |
            패 ${{Number(m[10]).toFixed(2)}}
        </div>`;
    }});
    document.getElementById("list").innerHTML=html;
}}
</script>

</body>
</html>
"""

# =====================================================
# Page2 - 통합 분석
# =====================================================

@app.get("/detail", response_class=HTMLResponse)
def detail(year:int, match:int):

    if not check_df():
        return "<h2>데이터 없음</h2>"

    df = CURRENT_DF

    rows = df[
        (df.iloc[:, COL_YEAR]==year) &
        (df.iloc[:, COL_MATCH]==match)
    ]

    if rows.empty:
        return "<h2>경기 없음</h2>"

    row = rows.iloc[0]

    league = row.iloc[COL_LEAGUE]
    home = row.iloc[COL_HOME]
    away = row.iloc[COL_AWAY]

    cond_label = f"{row.iloc[COL_TYPE]} · {row.iloc[COL_HOMEAWAY]} · {row.iloc[COL_GENERAL]} · {row.iloc[COL_DIR]} · {row.iloc[COL_HANDI]}"
    odds_label = f"{row.iloc[COL_WIN_ODDS]:.2f} / {row.iloc[COL_DRAW_ODDS]:.2f} / {row.iloc[COL_LOSE_ODDS]:.2f}"

    # 5조건 완전일치
    base_cond = {
        COL_TYPE:row.iloc[COL_TYPE],
        COL_HOMEAWAY:row.iloc[COL_HOMEAWAY],
        COL_GENERAL:row.iloc[COL_GENERAL],
        COL_DIR:row.iloc[COL_DIR],
        COL_HANDI:row.iloc[COL_HANDI]
    }

    base_df = run_filter(df, base_cond)
    base_dist = distribution(base_df)

    # 리그 제외 (5조건 유지)
    league_all_dist = base_dist

    # 5조건 + 현재리그
    league_cond = base_cond.copy()
    league_cond[COL_LEAGUE] = league
    league_df = run_filter(df, league_cond)
    league_dist = distribution(league_df)

    def block(label, dist):
        return f"""
        <h3>[{label}]</h3>
        총 {dist["총"]}경기<br>
        승 {text_bar(dist["wp"])} {dist["wp"]}% ({dist["승"]})<br>
        무 {text_bar(dist["dp"])} {dist["dp"]}% ({dist["무"]})<br>
        패 {text_bar(dist["lp"])} {dist["lp"]}% ({dist["패"]})
        """

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}
.card{{background:#1e293b;padding:15px;border-radius:15px;margin-top:15px}}
.flex{{display:flex;gap:20px;flex-wrap:wrap}}
.col{{flex:1;min-width:250px}}
</style>
</head>
<body>

<h3>[{league}] {home} vs {away}</h3>
{cond_label} | {odds_label}

<div class="card">
{block(cond_label, base_dist)}
</div>

<div class="card flex">
<div class="col">
{block(cond_label + " | 모든리그", league_all_dist)}
</div>
<div class="col">
{block(cond_label + " | " + league, league_dist)}
</div>
</div>

<br>
<a href="/page3?team={home}"><button>홈팀 분석</button></a>
<a href="/page3?team={away}"><button>원정팀 분석</button></a>
<a href="/page4?win={row.iloc[COL_WIN_ODDS]}&draw={row.iloc[COL_DRAW_ODDS]}&lose={row.iloc[COL_LOSE_ODDS]}"><button>배당 분석</button></a>

</body>
</html>
"""

# =====================================================
# Page3 - 팀 분석
# =====================================================

@app.get("/page3", response_class=HTMLResponse)
def page3(team:str):

    if not check_df():
        return "<h2>데이터 없음</h2>"

    df = CURRENT_DF

    # 팀 전체
    team_df = df[
        (df.iloc[:, COL_HOME] == team) |
        (df.iloc[:, COL_AWAY] == team)
    ]

    # 1️⃣ 리그 비교
    league_all_dist = distribution(team_df)

    # 현재 리그 추정 (가장 최근 경기 리그 기준)
    current_league = None
    if len(team_df) > 0:
        current_league = team_df.iloc[0][COL_LEAGUE]

    league_df = team_df[team_df.iloc[:, COL_LEAGUE] == current_league] if current_league else pd.DataFrame()
    league_dist = distribution(league_df)

    # 2️⃣ 경기 위치 분리
    home_df = team_df[team_df.iloc[:, COL_HOME] == team]
    away_df = team_df[team_df.iloc[:, COL_AWAY] == team]

    home_dist = distribution(home_df)
    away_dist = distribution(away_df)

    # 3️⃣ 방향 기준 비교 (홈팀 기준 홈/원정 방향)
    dir_home_df = df[
        (df.iloc[:, COL_HOME] == team) &
        (df.iloc[:, COL_HOMEAWAY] == "홈")
    ]

    dir_away_df = df[
        (df.iloc[:, COL_HOME] == team) &
        (df.iloc[:, COL_HOMEAWAY] == "원정")
    ]

    dir_home_dist = distribution(dir_home_df)
    dir_away_dist = distribution(dir_away_df)

    def block(label, dist):
        return f"""
        <h3>[{label}]</h3>
        총 {dist["총"]}경기<br>
        승 {text_bar(dist["wp"])} {dist["wp"]}% ({dist["승"]})<br>
        무 {text_bar(dist["dp"])} {dist["dp"]}% ({dist["무"]})<br>
        패 {text_bar(dist["lp"])} {dist["lp"]}% ({dist["패"]})
        """

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}
.card{{background:#1e293b;padding:15px;border-radius:15px;margin-top:15px}}
.flex{{display:flex;gap:20px;flex-wrap:wrap}}
.col{{flex:1;min-width:250px}}
</style>
</head>
<body>

<h2>{team} 팀 분석</h2>

<div class="card flex">
<div class="col">
{block(team + " | 모든리그", league_all_dist)}
</div>
<div class="col">
{block(team + " | " + (current_league if current_league else "리그없음"), league_dist)}
</div>
</div>

<div class="card flex">
<div class="col">
{block(team + " | 홈경기", home_dist)}
</div>
<div class="col">
{block(team + " | 원정경기", away_dist)}
</div>
</div>

<div class="card flex">
<div class="col">
{block(team + " | 홈방향", dir_home_dist)}
</div>
<div class="col">
{block(team + " | 원정방향", dir_away_dist)}
</div>
</div>

<br>
<a href="/"><button>← 경기목록</button></a>

</body>
</html>
"""

# =====================================================
# Page4 - 배당 분석
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4(win:float, draw:float, lose:float):

    if not check_df():
        return "<h2>데이터 없음</h2>"

    df = CURRENT_DF

    # 1️⃣ 승무패 완전 동일 일치
    exact_df = df[
        (df.iloc[:, COL_WIN_ODDS].round(2) == round(win,2)) &
        (df.iloc[:, COL_DRAW_ODDS].round(2) == round(draw,2)) &
        (df.iloc[:, COL_LOSE_ODDS].round(2) == round(lose,2))
    ]

    exact_dist = distribution(exact_df)

    # 2️⃣ 승배당 완전 일치
    win_df = df[df.iloc[:, COL_WIN_ODDS].round(2) == round(win,2)]

    # 3️⃣ 무배당 완전 일치
    draw_df = df[df.iloc[:, COL_DRAW_ODDS].round(2) == round(draw,2)]

    # 4️⃣ 패배당 완전 일치
    lose_df = df[df.iloc[:, COL_LOSE_ODDS].round(2) == round(lose,2)]

    def block(label, dist):
        return f"""
        <h3>[{label}]</h3>
        총 {dist["총"]}경기<br>
        승 {text_bar(dist["wp"])} {dist["wp"]}% ({dist["승"]})<br>
        무 {text_bar(dist["dp"])} {dist["dp"]}% ({dist["무"]})<br>
        패 {text_bar(dist["lp"])} {dist["lp"]}% ({dist["패"]})
        """

    # 일반 루프 출력 함수
    def general_loop(df_block):
        html = ""
        generals = df_block.iloc[:, COL_GENERAL].dropna().unique()
        for g in generals:
            sub = df_block[df_block.iloc[:, COL_GENERAL] == g]
            dist = distribution(sub)
            html += f"""
            <div style='margin-top:10px;'>
            <b>[일반={g}]</b><br>
            총 {dist["총"]}경기<br>
            승 {text_bar(dist["wp"])} {dist["wp"]}%<br>
            무 {text_bar(dist["dp"])} {dist["dp"]}%<br>
            패 {text_bar(dist["lp"])} {dist["lp"]}%<br>
            </div>
            """
        return html

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:20px}}
.card{{background:#1e293b;padding:15px;border-radius:15px;margin-top:15px}}
details{{margin-top:10px}}
</style>
</head>
<body>

<h2>배당 분석</h2>

<div class="card">
{block(f"{win:.2f} / {draw:.2f} / {lose:.2f}", exact_dist)}
</div>

<div class="card">
<details>
<summary>승배당 {win:.2f} 일반 분포</summary>
{general_loop(win_df)}
</details>
</div>

<div class="card">
<details>
<summary>무배당 {draw:.2f} 일반 분포</summary>
{general_loop(draw_df)}
</details>
</div>

<div class="card">
<details>
<summary>패배당 {lose:.2f} 일반 분포</summary>
{general_loop(lose_df)}
</details>
</div>

<br>
<a href="/"><button>← 경기목록</button></a>

</body>
</html>
"""

# =====================================================
# 실행 가이드
# =====================================================

"""
서버 실행:

uvicorn main:app --host 0.0.0.0 --port 8000

또는 배포 환경에서는

uvicorn main:app --host 0.0.0.0 --port $PORT

"""

# =====================================================
# 추가 안정화
# =====================================================

@app.get("/health")
def health():
    return {
        "data_loaded": not CURRENT_DF.empty,
        "rows": len(CURRENT_DF)
    }