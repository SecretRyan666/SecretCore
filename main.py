from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import pandas as pd
import os
import json

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
STRATEGY_HISTORY_FILE = "strategy_history.json"

MIN_CONFIDENCE = 0.32

LEAGUE_COUNT = {}
LEAGUE_WEIGHT = {}

FIVE_COND_DIST = {}

# =====================================================
# 데이터 로드
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

        build_five_cond_cache(CURRENT_DF)
        build_league_weight(CURRENT_DF)

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
# 필터
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

def filter_text(type, homeaway, general, dir, handi):

    parts = []
    if type: parts.append(f"유형={type}")
    if homeaway: parts.append(f"홈/원정={homeaway}")
    if general: parts.append(f"일반={general}")
    if dir: parts.append(f"정역={dir}")
    if handi: parts.append(f"핸디={handi}")

    return " · ".join(parts) if parts else "기본조건"

def run_filter(df, conditions: dict):
    filtered = df
    for col_idx, val in conditions.items():
        if val is None:
            continue
        filtered = filtered[filtered.iloc[:, col_idx] == val]
    return filtered

# =====================================================
# 분포
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
# 5조건 캐시
# =====================================================

def build_five_cond_cache(df):
    global FIVE_COND_DIST
    FIVE_COND_DIST.clear()

    if df.empty:
        return

    group_cols = [
        COL_TYPE,
        COL_HOMEAWAY,
        COL_GENERAL,
        COL_DIR,
        COL_HANDI
    ]

    grouped = df.groupby(
        df.columns[group_cols].tolist() + [df.columns[COL_RESULT]]
    ).size().unstack(fill_value=0)

    for key, row in grouped.iterrows():

        total = row.sum()

        FIVE_COND_DIST[key] = {
            "총": int(total),
            "승": int(row.get("승", 0)),
            "무": int(row.get("무", 0)),
            "패": int(row.get("패", 0)),
        }

        if total > 0:
            FIVE_COND_DIST[key]["wp"] = round(row.get("승", 0)/total*100,2)
            FIVE_COND_DIST[key]["dp"] = round(row.get("무", 0)/total*100,2)
            FIVE_COND_DIST[key]["lp"] = round(row.get("패", 0)/total*100,2)
        else:
            FIVE_COND_DIST[key]["wp"] = 0
            FIVE_COND_DIST[key]["dp"] = 0
            FIVE_COND_DIST[key]["lp"] = 0

# =====================================================
# 리그 가중치
# =====================================================

def build_league_weight(df):

    global LEAGUE_COUNT, LEAGUE_WEIGHT

    LEAGUE_COUNT.clear()
    LEAGUE_WEIGHT.clear()

    if df.empty:
        return

    league_counts = df.iloc[:, COL_LEAGUE].value_counts()

    for league, count in league_counts.items():

        LEAGUE_COUNT[league] = int(count)

        if count >= 800:
            LEAGUE_WEIGHT[league] = 1.05
        elif count >= 300:
            LEAGUE_WEIGHT[league] = 1.00
        else:
            LEAGUE_WEIGHT[league] = 0.90

# =====================================================
# EV 계산
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
# SECRET
# =====================================================

def secret_score_fast(row, df):

    key = (
        row.iloc[COL_TYPE],
        row.iloc[COL_HOMEAWAY],
        row.iloc[COL_GENERAL],
        row.iloc[COL_DIR],
        row.iloc[COL_HANDI]
    )

    dist = FIVE_COND_DIST.get(key, {
        "총":0,"승":0,"무":0,"패":0,
        "wp":0,"dp":0,"lp":0
    })

    if dist["총"] < 10:
        return {"score":0,"sample":dist["총"],"추천":"없음"}

    ev_data = safe_ev(dist, row)
    best_ev = max(ev_data["EV"].values())

    return {
        "score":round(best_ev,4),
        "sample":dist["총"],
        "추천":ev_data["추천"]
    }

# =====================================================
# SecretPick Brain
# =====================================================

def secret_pick_brain(row, df):

    key = (
        row.iloc[COL_TYPE],
        row.iloc[COL_HOMEAWAY],
        row.iloc[COL_GENERAL],
        row.iloc[COL_DIR],
        row.iloc[COL_HANDI]
    )

    p5 = FIVE_COND_DIST.get(key, {
        "총":0,
        "wp":0,"dp":0,"lp":0
    })

    sample = p5.get("총",0)

    if sample < 20:
        w5 = 0.4
    elif sample < 50:
        w5 = 0.5
    elif sample < 150:
        w5 = 0.65
    else:
        w5 = 0.75

    w_exact = 1 - w5

    exact_df = df[
        (df.iloc[:, COL_WIN_ODDS]  == row.iloc[COL_WIN_ODDS]) &
        (df.iloc[:, COL_DRAW_ODDS] == row.iloc[COL_DRAW_ODDS]) &
        (df.iloc[:, COL_LOSE_ODDS] == row.iloc[COL_LOSE_ODDS])
    ]

    exact_dist = distribution(exact_df)

    sp_w = w5*p5.get("wp",0) + w_exact*exact_dist.get("wp",0)
    sp_d = w5*p5.get("dp",0) + w_exact*exact_dist.get("dp",0)
    sp_l = w5*p5.get("lp",0) + w_exact*exact_dist.get("lp",0)

    sp_map = {
        "승": round(sp_w,2),
        "무": round(sp_d,2),
        "패": round(sp_l,2)
    }

    best = max(sp_map, key=sp_map.get)

    league = row.iloc[COL_LEAGUE]
    league_weight = LEAGUE_WEIGHT.get(league, 1.0)

    adjusted_conf = round((sp_map[best] / 100) * league_weight, 3)

    return {
        "추천": best,
        "확률": sp_map,
        "confidence": adjusted_conf,
        "sample": sample,
        "weight_5cond": w5,
        "league_weight": league_weight
    }


# =====================================================
# Health Check
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


@app.get("/health")
def health():
    return {
        "self_check": self_check()
    }


# =====================================================
# 필터 값 추출 API
# =====================================================

@app.get("/filters")
def filters():

    df = CURRENT_DF

    if df.empty:
        return {}

    df = df[df.iloc[:, COL_RESULT] == "경기전"]

    return {
        "type": sorted(df.iloc[:, COL_TYPE].dropna().unique().tolist()),
        "homeaway": sorted(df.iloc[:, COL_HOMEAWAY].dropna().unique().tolist()),
        "general": sorted(df.iloc[:, COL_GENERAL].dropna().unique().tolist()),
        "dir": sorted(df.iloc[:, COL_DIR].dropna().unique().tolist()),
        "handi": sorted(df.iloc[:, COL_HANDI].dropna().unique().tolist())
    }


# =====================================================
# 경기목록 API
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

    base_df = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        (
            (df.iloc[:, COL_TYPE] == "일반") |
            (df.iloc[:, COL_TYPE] == "핸디1")
        )
    ]

    base_df = apply_filters(base_df, type, homeaway, general, dir, handi)

    result = []

    for _, row in base_df.iterrows():

        data = row.values.tolist()
        sec = secret_score_fast(row, df)
        brain = secret_pick_brain(row, df)

        is_secret = bool(
            sec["score"] > 0.05 and
            sec["sample"] >= 20 and
            sec["추천"] != "없음"
        )

        result.append({
            "row": list(map(str, data)),
            "secret": is_secret,
            "pick": sec["추천"] if is_secret else "",
            "sp_pick": brain["추천"],
            "confidence": brain["confidence"]
        })

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

    DIST_CACHE.clear()
    SECRET_CACHE.clear()

    build_five_cond_cache(CURRENT_DF)
    build_league_weight(CURRENT_DF)

    return RedirectResponse("/", status_code=302)


# =====================================================
# Page1 - 메인 UI
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
}
.info-btn{position:absolute;right:14px;top:12px;font-size:12px;}
.bottom-nav{
position:fixed;bottom:0;width:100%;
background:#111827;display:flex;
justify-content:space-around;padding:12px 0;font-size:20px;
}
.modal{
display:none;position:fixed;top:0;left:0;width:100%;height:100%;
background:rgba(0,0,0,0.6);justify-content:center;align-items:center;
}
.modal-content{
background:#1e293b;padding:20px;border-radius:16px;
width:340px;max-height:80vh;overflow:auto;
}
.checkbox-group{margin-bottom:12px;}
</style>
</head>

<body>

<div class="header">
<div class="logo">SecretCore PRO</div>
<div class="top-icons">
<div onclick="resetFilters()">🔄</div>
<div onclick="openModal()">🔍</div>
<div onclick="location.href='/page-upload'">📤</div>
<div onclick="location.href='/logout'">👤</div>
</div>
</div>

<div id="conditionBar"
style="padding:8px 16px;font-size:12px;
opacity:0.8;border-bottom:1px solid #1e293b;">
기본조건
</div>

<div id="list" style="padding-bottom:100px;"></div>

<div class="bottom-nav">
<a href="/strategy1-view">🧠</a>
<a href="/strategy2-view">🎯</a>
<a href="/history">📊</a>
<a href="/evaluate">🧪</a>
</div>

<div class="modal" id="filterModal">
<div class="modal-content">
<h3>필터</h3>
<div id="filterArea"></div>
<button onclick="applyFilters()">적용</button>
<button onclick="closeModal()">닫기</button>
</div>
</div>

<script>

function resetFilters(){ window.location.href="/"; }

function openModal(){
document.getElementById("filterModal").style.display="flex";
loadFilters();
}

function closeModal(){
document.getElementById("filterModal").style.display="none";
}

async function loadFilters(){
let res = await fetch("/filters");
let data = await res.json();
let html="";
for(let key in data){
html += "<div class='checkbox-group'><b>"+key+"</b><br>";
data[key].forEach(v=>{
html += `<label>
<input type="checkbox" name="${key}" value="${v}"> ${v}
</label><br>`;
});
html += "</div>";
}
document.getElementById("filterArea").innerHTML = html;
}

function applyFilters(){
let params = new URLSearchParams();
document.querySelectorAll("#filterArea input:checked")
.forEach(el=>{
if(params.has(el.name)){
params.set(el.name, params.get(el.name)+","+el.value);
}else{
params.set(el.name, el.value);
}
});
window.location.href = "/?" + params.toString();
}

async function updateConditionBar(){
let params = new URLSearchParams(window.location.search);
let r = await fetch('/matches?' + params.toString());
let data = await r.json();
let text="";
if(data.length>0){
let first=data[0].row;
text = first[1]+"년 · "+first[2]+"회차";
}else{
text="경기 없음";
}
document.getElementById("conditionBar").innerText=text;
}

async function load(){
updateConditionBar();
let params = new URLSearchParams(window.location.search);
let r = await fetch('/matches?' + params.toString());
let data = await r.json();
let html="";
data.forEach(function(m){
let row=m.row;
let badge="";
if(m.secret){
badge=`<div style="position:absolute;right:18px;top:50%;
transform:translateY(-50%);
background:#22c55e;color:#0f1720;
padding:8px 12px;border-radius:14px;
font-size:12px;font-weight:bold;
box-shadow:0 4px 10px rgba(0,0,0,0.4);">
시크릿픽 ${m.pick}
</div>`;
}
html+=`<div class="card">
${badge}
<div><b>${row[6]}</b> vs <b>${row[7]}</b></div>
<div>승 ${row[8]} | 무 ${row[9]} | 패 ${row[10]}</div>
<div>${row[14]} · ${row[16]} · ${row[11]} · ${row[15]} · ${row[12]}</div>
<div class="info-btn">
<a href="/detail?no=${row[0]}" style="color:#38bdf8;">정보</a>
</div>
</div>`;
});
document.getElementById("list").innerHTML=html;
}

load();
</script>

</body>
</html>
"""

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

    filtered_df = apply_filters(df, type, homeaway, general, dir, handi)

    base_cond = build_5cond(row)
    base_df = run_filter(filtered_df, base_cond)
    base_dist = distribution(base_df)

    league_cond = build_league_cond(row)
    league_df = run_filter(filtered_df, league_cond)
    league_dist = distribution(league_df)

    secret_data = safe_ev(base_dist, row)

    condition_str = filter_text(type, homeaway, general, dir, handi)

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

<div style="flex:1;background:#1e293b;padding:16px;border-radius:16px;">
<h3>5조건 완전일치</h3>
총 {base_dist["총"]}경기
<div>승 {base_dist["wp"]}% ({base_dist["승"]}경기)</div>
{bar_html(base_dist["wp"],"win")}
<div>무 {base_dist["dp"]}% ({base_dist["무"]}경기)</div>
{bar_html(base_dist["dp"],"draw")}
<div>패 {base_dist["lp"]}% ({base_dist["패"]}경기)</div>
{bar_html(base_dist["lp"],"lose")}
</div>

<div style="flex:1;background:#1e293b;padding:16px;border-radius:16px;">
<h3>동일리그 5조건</h3>
총 {league_dist["총"]}경기
<div>승 {league_dist["wp"]}% ({league_dist["승"]}경기)</div>
{bar_html(league_dist["wp"],"win")}
<div>무 {league_dist["dp"]}% ({league_dist["무"]}경기)</div>
{bar_html(league_dist["dp"],"draw")}
<div>패 {league_dist["lp"]}% ({league_dist["패"]}경기)</div>
{bar_html(league_dist["lp"],"lose")}
</div>

</div>

<br><br>

<div style="background:#1e293b;padding:16px;border-radius:16px;">
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
# 기타 페이지 (Stub)
# =====================================================

@app.get("/ledger", response_class=HTMLResponse)
def ledger_page():
    return """
<html><body style='background:#0f1720;color:white;padding:30px;'>
<h2>📊 Ledger</h2>
<p>준비중입니다.</p>
<button onclick="history.back()">← 뒤로</button>
</body></html>
"""


@app.get("/memo", response_class=HTMLResponse)
def memo_page():
    return """
<html><body style='background:#0f1720;color:white;padding:30px;'>
<h2>📝 Memo</h2>
<p>준비중입니다.</p>
<button onclick="history.back()">← 뒤로</button>
</body></html>
"""


@app.get("/capture", response_class=HTMLResponse)
def capture_page():
    return """
<html><body style='background:#0f1720;color:white;padding:30px;'>
<h2>📸 Capture</h2>
<p>준비중입니다.</p>
<button onclick="history.back()">← 뒤로</button>
</body></html>
"""


@app.get("/favorites", response_class=HTMLResponse)
def favorites_page():

    global FAVORITES

    items = "<br>".join(FAVORITES) if FAVORITES else "없음"

    return f"""
<html><body style='background:#0f1720;color:white;padding:30px;'>
<h2>⭐ Favorites</h2>
<p>{items}</p>
<button onclick="history.back()">← 뒤로</button>
</body></html>
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