from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import pandas as pd
import os

app = FastAPI()

# =====================================================
# 절대참조 인덱스 (고정 구조)
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
# 캐시
# =====================================================

DIST_CACHE = {}
SECRET_CACHE = {}

# =====================================================
# 데이터 로드 (dtype=str 고정)
# =====================================================

def load_data():
    global CURRENT_DF

    if os.path.exists(DATA_FILE):

        df = pd.read_csv(
            DATA_FILE,
            encoding="utf-8-sig",
            dtype=str,
            low_memory=False
        )

        if df.shape[1] != EXPECTED_COLS:
            CURRENT_DF = pd.DataFrame()
            return

        CURRENT_DF = df

load_data()

# =====================================================
# 조건 빌더
# =====================================================

def build_5cond(row):
    return {
        COL_TYPE:      row.iloc[COL_TYPE],
        COL_HOMEAWAY:  row.iloc[COL_HOMEAWAY],
        COL_GENERAL:   row.iloc[COL_GENERAL],
        COL_DIR:       row.iloc[COL_DIR],
        COL_HANDI:     row.iloc[COL_HANDI]
    }

def build_league_cond(row):
    cond = build_5cond(row)
    cond[COL_LEAGUE] = row.iloc[COL_LEAGUE]
    return cond

# =====================================================
# 필터 적용 함수 (다중선택 AND)
# =====================================================

def apply_filters(df, type, homeaway, general, dir, handi):

    if type:
        df = df[df.iloc[:, COL_TYPE].isin(type.split(","))]

    if homeaway:
        df = df[df.iloc[:, COL_HOMEAWAY].isin(homeaway.split(","))]

    if general:
        df = df[df.iloc[:, COL_GENERAL].isin(general.split(","))]

    if dir:
        df = df[df.iloc[:, COL_DIR].isin(dir.split(","))]

    if handi:
        df = df[df.iloc[:, COL_HANDI].isin(handi.split(","))]

    return df

# =====================================================
# 조건 텍스트 생성
# =====================================================

def filter_text(type, homeaway, general, dir, handi):

    parts = []

    if type: parts.append(f"유형={type}")
    if homeaway: parts.append(f"홈/원정={homeaway}")
    if general: parts.append(f"일반={general}")
    if dir: parts.append(f"정역={dir}")
    if handi: parts.append(f"핸디={handi}")

    return " · ".join(parts) if parts else "기본조건"

# =====================================================
# run_filter
# =====================================================

def run_filter(df, conditions: dict):
    filtered = df
    for col_idx, val in conditions.items():
        if val is None:
            continue
        filtered = filtered[filtered.iloc[:, col_idx] == val]
    return filtered

# =====================================================
# 분포 (DIST_CACHE 적용)
# =====================================================

def distribution(df):

    key = tuple(df.index)

    if key in DIST_CACHE:
        return DIST_CACHE[key]

    total = len(df)

    if total == 0:
        result = {"총":0,"승":0,"무":0,"패":0,"wp":0,"dp":0,"lp":0}
        DIST_CACHE[key] = result
        return result

    result_col = df.iloc[:, COL_RESULT]

    win  = (result_col == "승").sum()
    draw = (result_col == "무").sum()
    lose = (result_col == "패").sum()

    wp = round(win/total*100,2)
    dp = round(draw/total*100,2)
    lp = round(lose/total*100,2)

    result = {
        "총":int(total),
        "승":int(win),
        "무":int(draw),
        "패":int(lose),
        "wp":wp,
        "dp":dp,
        "lp":lp
    }

    DIST_CACHE[key] = result
    return result


# =====================================================
# 안전 EV
# =====================================================

def safe_ev(dist, row):

    try:
        win_odds  = float(row.iloc[COL_WIN_ODDS])
        draw_odds = float(row.iloc[COL_DRAW_ODDS])
        lose_odds = float(row.iloc[COL_LOSE_ODDS])
    except:
        return {"EV": {"승":0,"무":0,"패":0}, "추천":"없음"}

    ev_w = dist["wp"]/100 * win_odds  - 1
    ev_d = dist["dp"]/100 * draw_odds - 1
    ev_l = dist["lp"]/100 * lose_odds - 1

    ev_map = {"승":ev_w, "무":ev_d, "패":ev_l}
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
# SECRET 점수 (조합 캐싱 적용)
# =====================================================

def secret_score_fast(row, df):

    cond = build_5cond(row)
    cond_key = tuple(cond.values())

    if cond_key in SECRET_CACHE:
        return SECRET_CACHE[cond_key]

    sub_df = run_filter(df, cond)
    dist = distribution(sub_df)

    if dist["총"] < 10:
        result = {"score":0,"sample":dist["총"],"추천":"없음"}
        SECRET_CACHE[cond_key] = result
        return result

    ev_data = safe_ev(dist, row)
    best_ev = max(ev_data["EV"].values())

    result = {
        "score":round(best_ev,4),
        "sample":dist["총"],
        "추천":ev_data["추천"]
    }

    SECRET_CACHE[cond_key] = result
    return result


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
# 업로드 처리
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

    if df.shape[1] != EXPECTED_COLS:
        return {
            "error": f"컬럼 불일치: {df.shape[1]} / 기대값 {EXPECTED_COLS}"
        }

    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

    CURRENT_DF = df

    # 캐시 초기화
    DIST_CACHE.clear()
    SECRET_CACHE.clear()

    return RedirectResponse("/", status_code=302)

# =====================================================
# 업로드 페이지
# =====================================================

@app.get("/page-upload", response_class=HTMLResponse)
def page_upload():

    if not LOGGED_IN:
        return RedirectResponse("/", status_code=302)

    return """
    <html>
    <body style='background:#0f1720;color:white;padding:30px;font-family:Arial;'>
    <h2>📤 업로드</h2>
    <form action="/upload-data" method="post" enctype="multipart/form-data">
        <input type="file" name="file" required><br><br>
        <button type="submit">업로드 실행</button>
    </form>
    <br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

# =====================================================
# self_check
# =====================================================

def self_check():

    report = {}

    report["data_loaded"] = not CURRENT_DF.empty
    report["rows"] = len(CURRENT_DF)

    report["column_count_ok"] = (
        CURRENT_DF.shape[1] == EXPECTED_COLS
        if not CURRENT_DF.empty else False
    )

    try:
        _ = CURRENT_DF.iloc[:, COL_NO]
        _ = CURRENT_DF.iloc[:, COL_TYPE]
        report["index_access_ok"] = True
    except:
        report["index_access_ok"] = False

    report["dist_cache_size"] = len(DIST_CACHE)
    report["secret_cache_size"] = len(SECRET_CACHE)

    report["expected_cols"] = EXPECTED_COLS

    return report


# =====================================================
# Health Check
# =====================================================

@app.get("/health")
def health():
    return {
        "self_check": self_check()
    }


# =====================================================
# 필터 값 추출 API (경기전 기준 적용)
# =====================================================

@app.get("/filters")
def filters():

    df = CURRENT_DF

    if df.empty:
        return {}

    # 🔥 경기전만 기준
    df = df[
        df.iloc[:, COL_RESULT] == "경기전"
    ]

    return {
        "type": sorted(df.iloc[:, COL_TYPE].dropna().unique().tolist()),
        "homeaway": sorted(df.iloc[:, COL_HOMEAWAY].dropna().unique().tolist()),
        "general": sorted(df.iloc[:, COL_GENERAL].dropna().unique().tolist()),
        "dir": sorted(df.iloc[:, COL_DIR].dropna().unique().tolist()),
        "handi": sorted(df.iloc[:, COL_HANDI].dropna().unique().tolist())
    }

# =====================================================
# Page1 - 메인
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():

    if not LOGGED_IN:
        return """
        <html>
        <body style="background:#0f1720;color:white;
        display:flex;justify-content:center;
        align-items:center;height:100vh;">
        <form action="/login" method="post">
        <h2>Login</h2>
        <input name="username"><br><br>
        <input name="password" type="password"><br><br>
        <button type="submit">로그인</button>
        </form>
        </body>
        </html>
        """

    return """
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{background:#0f1720;color:white;font-family:Arial;margin:0;}

.header{
display:flex;justify-content:space-between;align-items:center;
padding:14px 18px;background:#111827;position:sticky;top:0;z-index:50;
}

.logo{font-weight:700;font-size:18px;color:#38bdf8;}
.top-icons{display:flex;gap:18px;font-size:18px;cursor:pointer;}

.card{
background:#1e293b;margin:14px;padding:18px;
border-radius:18px;position:relative;
box-shadow:0 4px 12px rgba(0,0,0,0.3);
overflow:hidden;
}

.secret-overlay{
position:absolute;
top:50%;
left:50%;
transform:translate(-50%,-50%);
font-size:22px;
font-weight:bold;
color:#22c55e;
opacity:0.18;
pointer-events:none;
}

.info-btn{position:absolute;right:14px;top:12px;font-size:12px;}
.star-btn{position:absolute;right:14px;top:40px;font-size:18px;color:#6b7280;}

.bottom-nav{
position:fixed;bottom:0;width:100%;
background:#111827;display:flex;
justify-content:space-around;padding:12px 0;font-size:20px;
}
</style>
</head>
<body>

<div class="header">
    <div class="logo">SecretCore PRO</div>
    <div class="top-icons">
        <div onclick="location.href='/'">🔄</div>
        <div onclick="openModal()">🔍</div>
        <div onclick="location.href='/page-upload'">📤</div>
        <div onclick="location.href='/logout'">👤</div>
    </div>
</div>

<div id="conditionBar"
style="padding:8px 16px;font-size:14px;
border-bottom:1px solid #1e293b;">
로딩중...
</div>

<div id="list" style="padding-bottom:100px;"></div>

<div class="bottom-nav">
    <a href="/ledger">🏠</a>
    <a href="/memo">📝</a>
    <a href="/capture">📸</a>
    <a href="/favorites">⭐</a>
</div>

<script>

async function load(){

    let params = new URLSearchParams(window.location.search);
    let r = await fetch('/matches?' + params.toString());
    let json = await r.json();

    let data = json.data;
    let meta = json.meta;

    if(meta.years.length>0 && meta.rounds.length>0){
        document.getElementById("conditionBar").innerText =
            meta.years[0] + "년 " + meta.rounds[0] + "회";
    } else {
        document.getElementById("conditionBar").innerText = "경기 없음";
    }

    let html="";

    data.forEach(function(m){

        let row = m.row;
        let overlay = "";

        if(m.secret){
            overlay = `<div class="secret-overlay">
                        시크릿픽 ${m.secret_pick}
                       </div>`;
        }

        html+=`
        <div class="card">
        ${overlay}
        <div><b>${row[6]}</b> vs <b>${row[7]}</b></div>
        <div>승 ${row[8]} | 무 ${row[9]} | 패 ${row[10]}</div>
        <div>${row[14]} · ${row[16]} · ${row[11]} · ${row[15]} · ${row[12]}</div>
        <div class="info-btn">
            <a href="/detail?no=${row[0]}" style="color:#38bdf8;">정보</a>
        </div>
        </div>`;
    });

    document.getElementById("list").innerHTML = html;
}

load();
</script>
</body>
</html>
"""


# =====================================================
# 경기목록 API (meta + secret_pick 반환)
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
        return {"meta":{"years":[],"rounds":[]},"data":[]}

    base_df = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        (
            (df.iloc[:, COL_TYPE] == "일반") |
            (df.iloc[:, COL_TYPE] == "핸디1")
        )
    ]

    base_df = apply_filters(
        base_df, type, homeaway, general, dir, handi
    )

    result = []

    for _, row in base_df.iterrows():

        data = row.values.tolist()
        sec = secret_score_fast(row, df)

        is_secret = bool(
            sec["score"] > 0.05 and
            sec["sample"] >= 20 and
            sec["추천"] != "없음"
        )

        result.append({
            "row": list(map(str, data)),
            "secret": is_secret,
            "secret_pick": sec["추천"] if is_secret else ""
        })

    years = base_df.iloc[:, COL_YEAR].unique().tolist()
    rounds = base_df.iloc[:, COL_ROUND].unique().tolist()

    return {
        "meta": {
            "years": years,
            "rounds": rounds
        },
        "data": result
    }

# =====================================================
# PRO 막대그래프
# =====================================================

def bar_html(percent, mode="win"):

    color_map = {
        "win":"linear-gradient(90deg,#22c55e,#16a34a)",
        "draw":"linear-gradient(90deg,#94a3b8,#64748b)",
        "lose":"linear-gradient(90deg,#ef4444,#dc2626)"
    }

    return f"""
    <div style="width:100%;background:rgba(255,255,255,0.08);
                border-radius:999px;height:14px;margin:6px 0;">
        <div style="width:{percent}%;
                    background:{color_map[mode]};
                    height:100%;
                    border-radius:999px;"></div>
    </div>
    """


# =====================================================
# Page2 - 상세 분석
# =====================================================

@app.get("/detail", response_class=HTMLResponse)
def detail(
    no: str = None,
    type: str = None,
    homeaway: str = None,
    general: str = None,
    dir: str = None,
    handi: str = None
):

    if not no:
        return "<h2>잘못된 접근</h2>"

    df = CURRENT_DF
    if df.empty:
        return "<h2>데이터 없음</h2>"

    row_df = df[df.iloc[:, COL_NO] == str(no)]
    if row_df.empty:
        return "<h2>경기 없음</h2>"

    row = row_df.iloc[0]

    home   = row.iloc[COL_HOME]
    away   = row.iloc[COL_AWAY]
    league = row.iloc[COL_LEAGUE]

    # 필터 적용
    filtered_df = apply_filters(
        df, type, homeaway, general, dir, handi
    )

    # 5조건 완전일치
    base_cond = build_5cond(row)
    base_df = run_filter(filtered_df, base_cond)
    base_dist = distribution(base_df)

    # 동일리그 5조건
    league_cond = build_league_cond(row)
    league_df = run_filter(filtered_df, league_cond)
    league_dist = distribution(league_df)

    # 시크릿픽
    secret_data = safe_ev(base_dist, row)

    condition_str = filter_text(
        type, homeaway, general, dir, handi
    )

    return f"""
    <html>
    <body style="background:#0f1720;color:white;
                 font-family:Arial;padding:20px;">

    <h2>[{league}] {home} vs {away}</h2>

    <div style="opacity:0.7;font-size:12px;margin-bottom:15px;">
    현재 필터: {condition_str}
    </div>

    승 {row.iloc[COL_WIN_ODDS]} /
    무 {row.iloc[COL_DRAW_ODDS]} /
    패 {row.iloc[COL_LOSE_ODDS]}

    <br><br>

    <div style="display:flex;gap:20px;">

    <!-- 5조건 -->
    <div style="flex:1;background:#1e293b;
                padding:16px;border-radius:16px;">

    <h3>5조건 완전일치</h3>
    총 {base_dist["총"]}경기

    <div>승 {base_dist["wp"]}%</div>
    {bar_html(base_dist["wp"],"win")}

    <div>무 {base_dist["dp"]}%</div>
    {bar_html(base_dist["dp"],"draw")}

    <div>패 {base_dist["lp"]}%</div>
    {bar_html(base_dist["lp"],"lose")}
    </div>

    <!-- 동일리그 -->
    <div style="flex:1;background:#1e293b;
                padding:16px;border-radius:16px;">

    <h3>동일리그 5조건</h3>
    총 {league_dist["총"]}경기

    <div>승 {league_dist["wp"]}%</div>
    {bar_html(league_dist["wp"],"win")}

    <div>무 {league_dist["dp"]}%</div>
    {bar_html(league_dist["dp"],"draw")}

    <div>패 {league_dist["lp"]}%</div>
    {bar_html(league_dist["lp"],"lose")}
    </div>

    </div>

    <br><br>

    <div style="background:#1e293b;
                padding:16px;border-radius:16px;">
    <h3>시크릿픽</h3>
    추천: <b>{secret_data["추천"]}</b><br>
    승 EV: {secret_data["EV"]["승"]}<br>
    무 EV: {secret_data["EV"]["무"]}<br>
    패 EV: {secret_data["EV"]["패"]}
    </div>

    <br><br>

    <a href="/page3?no={no}">홈팀 분석</a><br>
    <a href="/page3?no={no}&away=1">원정팀 분석</a><br>
    <a href="/page4?no={no}">배당 분석</a>

    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

# =====================================================
# Page3 - 팀 분석
# =====================================================

@app.get("/page3", response_class=HTMLResponse)
def page3(
    no: str = None,
    away: str = None,
    type: str = None,
    homeaway: str = None,
    general: str = None,
    dir: str = None,
    handi: str = None
):

    if not no:
        return "<h2>잘못된 접근</h2>"

    df = CURRENT_DF
    if df.empty:
        return "<h2>데이터 없음</h2>"

    row_df = df[df.iloc[:, COL_NO] == str(no)]
    if row_df.empty:
        return "<h2>경기 없음</h2>"

    row = row_df.iloc[0]

    team = row.iloc[COL_AWAY] if away else row.iloc[COL_HOME]
    team_type = "원정팀 분석" if away else "홈팀 분석"

    filtered_df = apply_filters(
        df, type, homeaway, general, dir, handi
    )

    team_df = filtered_df[
        (filtered_df.iloc[:, COL_HOME] == team) |
        (filtered_df.iloc[:, COL_AWAY] == team)
    ]

    home_df = filtered_df[filtered_df.iloc[:, COL_HOME] == team]
    away_df = filtered_df[filtered_df.iloc[:, COL_AWAY] == team]

    all_dist = distribution(team_df)
    home_dist = distribution(home_df)
    away_dist = distribution(away_df)

    condition_str = filter_text(type, homeaway, general, dir, handi)

    return f"""
    <html>
    <body style="background:#0f1720;color:white;
                 font-family:Arial;padding:20px;">

    <h2>{team} {team_type}</h2>

    <div style="opacity:0.7;font-size:12px;margin-bottom:15px;">
    현재 필터: {condition_str}
    </div>

    <details open>
    <summary><b>전체 통계</b></summary>
    총 {all_dist["총"]}경기
    {bar_html(all_dist["wp"],"win")}
    {bar_html(all_dist["dp"],"draw")}
    {bar_html(all_dist["lp"],"lose")}
    </details>

    <br>

    <details>
    <summary><b>홈 vs 원정 비교</b></summary>

    <div style="display:flex;gap:12px;">

    <div style="flex:1;background:#1e293b;padding:12px;border-radius:12px;">
    <b>홈</b><br>
    총 {home_dist["총"]}경기
    {bar_html(home_dist["wp"],"win")}
    {bar_html(home_dist["dp"],"draw")}
    {bar_html(home_dist["lp"],"lose")}
    </div>

    <div style="flex:1;background:#1e293b;padding:12px;border-radius:12px;">
    <b>원정</b><br>
    총 {away_dist["총"]}경기
    {bar_html(away_dist["wp"],"win")}
    {bar_html(away_dist["dp"],"draw")}
    {bar_html(away_dist["lp"],"lose")}
    </div>

    </div>

    </details>

    <br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """


# =====================================================
# Page4 - 배당 분석
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4(
    no: str = None,
    type: str = None,
    homeaway: str = None,
    general: str = None,
    dir: str = None,
    handi: str = None
):

    if not no:
        return "<h2>잘못된 접근</h2>"

    df = CURRENT_DF
    if df.empty:
        return "<h2>데이터 없음</h2>"

    row_df = df[df.iloc[:, COL_NO] == str(no)]
    if row_df.empty:
        return "<h2>경기 없음</h2>"

    row = row_df.iloc[0]

    filtered_df = apply_filters(
        df, type, homeaway, general, dir, handi
    )

    win_str  = row.iloc[COL_WIN_ODDS]
    draw_str = row.iloc[COL_DRAW_ODDS]
    lose_str = row.iloc[COL_LOSE_ODDS]

    exact_df = filtered_df[
        (filtered_df.iloc[:, COL_WIN_ODDS]  == win_str) &
        (filtered_df.iloc[:, COL_DRAW_ODDS] == draw_str) &
        (filtered_df.iloc[:, COL_LOSE_ODDS] == lose_str)
    ]

    win_df  = filtered_df[filtered_df.iloc[:, COL_WIN_ODDS] == win_str]
    draw_df = filtered_df[filtered_df.iloc[:, COL_DRAW_ODDS] == draw_str]
    lose_df = filtered_df[filtered_df.iloc[:, COL_LOSE_ODDS] == lose_str]

    exact_dist = distribution(exact_df)
    win_dist   = distribution(win_df)
    draw_dist  = distribution(draw_df)
    lose_dist  = distribution(lose_df)

    win_ev  = safe_ev(win_dist,  row)
    draw_ev = safe_ev(draw_dist, row)
    lose_ev = safe_ev(lose_dist, row)

    condition_str = filter_text(type, homeaway, general, dir, handi)

    return f"""
    <html>
    <body style="background:#0f1720;color:white;
                 font-family:Arial;padding:20px;">

    <h2>배당 분석</h2>

    <div style="opacity:0.7;font-size:12px;margin-bottom:15px;">
    현재 필터: {condition_str}
    </div>

    승 {win_str} / 무 {draw_str} / 패 {lose_str}

    <br><br>

    <h3>완전일치</h3>
    총 {exact_dist["총"]}경기
    {bar_html(exact_dist["wp"],"win")}
    {bar_html(exact_dist["dp"],"draw")}
    {bar_html(exact_dist["lp"],"lose")}

    <br><br>

    <div style="display:flex;gap:12px;">

    <div style="flex:1;background:#1e293b;padding:12px;border-radius:12px;">
    <b>승 EV</b><br>
    추천: {win_ev["추천"]}<br>
    {win_ev["EV"]["승"]}
    </div>

    <div style="flex:1;background:#1e293b;padding:12px;border-radius:12px;">
    <b>무 EV</b><br>
    추천: {draw_ev["추천"]}<br>
    {draw_ev["EV"]["무"]}
    </div>

    <div style="flex:1;background:#1e293b;padding:12px;border-radius:12px;">
    <b>패 EV</b><br>
    추천: {lose_ev["추천"]}<br>
    {lose_ev["EV"]["패"]}
    </div>

    </div>

    <br><br>

    <details>
    <summary><b>승 동일 통계</b></summary>
    총 {win_dist["총"]}경기
    {bar_html(win_dist["wp"],"win")}
    {bar_html(win_dist["dp"],"draw")}
    {bar_html(win_dist["lp"],"lose")}
    </details>

    <br>

    <details>
    <summary><b>무 동일 통계</b></summary>
    총 {draw_dist["총"]}경기
    {bar_html(draw_dist["wp"],"win")}
    {bar_html(draw_dist["dp"],"draw")}
    {bar_html(draw_dist["lp"],"lose")}
    </details>

    <br>

    <details>
    <summary><b>패 동일 통계</b></summary>
    총 {lose_dist["총"]}경기
    {bar_html(lose_dist["wp"],"win")}
    {bar_html(lose_dist["dp"],"draw")}
    {bar_html(lose_dist["lp"],"lose")}
    </details>

    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """


# =====================================================
# 실행부
# =====================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )