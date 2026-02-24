from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi import Response
import pandas as pd
import os
import json
import time
import traceback
import logging

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
BACKUP_FILE = "backup_snapshot.csv"
FAVORITES_FILE = "favorites.json"

# =====================================================
# 글로벌 상태
# =====================================================

CURRENT_DF = pd.DataFrame()
LOGGED_IN = False
FAVORITES = []

DIST_CACHE = {}
SECRET_CACHE = {}
ODDS_DIST_CACHE = {}

LEAGUE_COUNT = {}
LEAGUE_WEIGHT = {}
FIVE_COND_DIST = {}

MIN_CONFIDENCE = 0.32

logging.basicConfig(level=logging.INFO)

# =====================================================
# 배당 분포 사전 캐시 생성
# =====================================================

def build_odds_cache(df):
    global ODDS_DIST_CACHE
    ODDS_DIST_CACHE.clear()

    if df.empty:
        return

    grouped = df.groupby(
        [df.columns[COL_WIN_ODDS],
         df.columns[COL_DRAW_ODDS],
         df.columns[COL_LOSE_ODDS],
         df.columns[COL_RESULT]]
    ).size().unstack(fill_value=0)

    for key, row in grouped.iterrows():
        total = row.sum()

        ODDS_DIST_CACHE[key] = {
            "총": int(total),
            "승": int(row.get("승", 0)),
            "무": int(row.get("무", 0)),
            "패": int(row.get("패", 0)),
            "wp": round(row.get("승", 0)/total*100,2) if total else 0,
            "dp": round(row.get("무", 0)/total*100,2) if total else 0,
            "lp": round(row.get("패", 0)/total*100,2) if total else 0
        }

# =====================================================
# 데이터 로드
# =====================================================

def load_data():
    global CURRENT_DF

    if not os.path.exists(DATA_FILE):
        CURRENT_DF = pd.DataFrame()
        return

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
    build_odds_cache(CURRENT_DF)

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
# 필터 처리
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
# 분포 계산 (캐시 적용)
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
# 5조건 사전 집계 캐시 생성
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
# 리그 가중치 생성
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
# Secret Score (캐싱 적용)
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


def secret_score_cached(row, df):

    key = (
        row.iloc[COL_TYPE],
        row.iloc[COL_HOMEAWAY],
        row.iloc[COL_GENERAL],
        row.iloc[COL_DIR],
        row.iloc[COL_HANDI],
        row.iloc[COL_WIN_ODDS],
        row.iloc[COL_DRAW_ODDS],
        row.iloc[COL_LOSE_ODDS]
    )

    if key in SECRET_CACHE:
        return SECRET_CACHE[key]

    result = secret_score_fast(row, df)
    SECRET_CACHE[key] = result

    return result

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
        "총": 0,
        "wp": 0, "dp": 0, "lp": 0
    })

    sample = p5.get("총", 0)

    if sample < 20:
        w5 = 0.4
    elif sample < 50:
        w5 = 0.5
    elif sample < 150:
        w5 = 0.65
    else:
        w5 = 0.75

    w_exact = 1 - w5

    odds_key = (
        row.iloc[COL_WIN_ODDS],
        row.iloc[COL_DRAW_ODDS],
        row.iloc[COL_LOSE_ODDS]
    )

    exact_dist = ODDS_DIST_CACHE.get(odds_key, {
        "총": 0,
        "wp": 0, "dp": 0, "lp": 0
    })

    sp_w = w5 * p5.get("wp", 0) + w_exact * exact_dist.get("wp", 0)
    sp_d = w5 * p5.get("dp", 0) + w_exact * exact_dist.get("dp", 0)
    sp_l = w5 * p5.get("lp", 0) + w_exact * exact_dist.get("lp", 0)

    sp_map = {
        "승": round(sp_w, 2),
        "무": round(sp_d, 2),
        "패": round(sp_l, 2)
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
# safe_ev_tuple
# =====================================================

def safe_ev_tuple(dist, row):

    try:
        win_odds  = float(row[COL_WIN_ODDS])
        draw_odds = float(row[COL_DRAW_ODDS])
        lose_odds = float(row[COL_LOSE_ODDS])
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
# secret_score_fast_tuple
# =====================================================

def secret_score_fast_tuple(row):

    key = (
        row[COL_TYPE],
        row[COL_HOMEAWAY],
        row[COL_GENERAL],
        row[COL_DIR],
        row[COL_HANDI]
    )

    dist = FIVE_COND_DIST.get(key, {
        "총":0,"승":0,"무":0,"패":0,
        "wp":0,"dp":0,"lp":0
    })

    if dist["총"] < 10:
        return {"score":0,"sample":dist["총"],"추천":"없음"}

    ev_data = safe_ev_tuple(dist, row)
    best_ev = max(ev_data["EV"].values())

    return {
        "score":round(best_ev,4),
        "sample":dist["총"],
        "추천":ev_data["추천"]
    }

# =====================================================
# secret_pick_brain
# =====================================================

def secret_pick_brain_tuple(row):

    key = (
        row[COL_TYPE],
        row[COL_HOMEAWAY],
        row[COL_GENERAL],
        row[COL_DIR],
        row[COL_HANDI]
    )

    p5 = FIVE_COND_DIST.get(key, {
        "총": 0,
        "wp": 0, "dp": 0, "lp": 0
    })

    sample = p5.get("총", 0)

    if sample < 20:
        w5 = 0.4
    elif sample < 50:
        w5 = 0.5
    elif sample < 150:
        w5 = 0.65
    else:
        w5 = 0.75

    w_exact = 1 - w5

    odds_key = (
        row[COL_WIN_ODDS],
        row[COL_DRAW_ODDS],
        row[COL_LOSE_ODDS]
    )

    exact_dist = ODDS_DIST_CACHE.get(odds_key, {
        "총": 0,
        "wp": 0, "dp": 0, "lp": 0
    })

    sp_w = w5 * p5.get("wp", 0) + w_exact * exact_dist.get("wp", 0)
    sp_d = w5 * p5.get("dp", 0) + w_exact * exact_dist.get("dp", 0)
    sp_l = w5 * p5.get("lp", 0) + w_exact * exact_dist.get("lp", 0)

    sp_map = {
        "승": round(sp_w, 2),
        "무": round(sp_d, 2),
        "패": round(sp_l, 2)
    }

    best = max(sp_map, key=sp_map.get)

    league = row[COL_LEAGUE]
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


@app.get("/auth-status")
def auth_status():
    return {"logged_in": LOGGED_IN}

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
    build_odds_cache(CURRENT_DF)

    return RedirectResponse("/", status_code=302)

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
    return {"self_check": self_check()}

# =====================================================
# 필터 값 추출 API
# =====================================================

@app.get("/filters")
def filters():

    if CURRENT_DF.empty:
        return {}

    df = CURRENT_DF[CURRENT_DF.iloc[:, COL_RESULT] == "경기전"]

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

    if CURRENT_DF.empty:
        return []

    base_df = CURRENT_DF[
        (CURRENT_DF.iloc[:, COL_RESULT] == "경기전") &
        (
            (CURRENT_DF.iloc[:, COL_TYPE] == "일반") |
            (CURRENT_DF.iloc[:, COL_TYPE] == "핸디1")
        )
    ]

    base_df = apply_filters(base_df, type, homeaway, general, dir, handi)

    result = []

    for row in base_df.itertuples(index=False):

        data = list(row)

        # tuple → pandas row 형태로 접근 제거
        sec = secret_score_fast_tuple(row)
        brain = secret_pick_brain_tuple(row)

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
.secret-badge{
position:absolute;right:18px;top:50%;
transform:translateY(-50%);
background:#22c55e;color:#0f1720;
padding:8px 12px;border-radius:14px;
font-size:12px;font-weight:bold;
box-shadow:0 4px 10px rgba(0,0,0,0.4);
}
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

async function load(){

    let params = new URLSearchParams(window.location.search);
    let r = await fetch('/matches?' + params.toString());
    let data = await r.json();

    // 🔥 여기서 conditionBar 처리
    if(data.length>0){
        let first=data[0].row;
        document.getElementById("conditionBar").innerText =
        first[1] + "년 · " + first[2];
    } else {
        document.getElementById("conditionBar").innerText="경기 없음";
    }

    let html="";
    let query = window.location.search;

    data.forEach(function(m){

        let row=m.row;
        let badge="";

        if(m.secret){
            badge=`<div class="secret-badge">
            시크릿픽 ${m.pick}
            </div>`;
        }

        html+=`<div class="card">
        ${badge}
        <div><b>${row[6]}</b> vs <b>${row[7]}</b></div>
        <div>승 ${row[8]} | 무 ${row[9]} | 패 ${row[10]}</div>
        <div>${row[14]} · ${row[16]} · ${row[11]} · ${row[15]} · ${row[12]}</div>
        <div class="info-btn">
        <a href="/detail?no=${row[0]}${query}" style="color:#38bdf8;">정보</a>
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

    if CURRENT_DF.empty:
        return "<h2>데이터 없음</h2>"

    row_df = CURRENT_DF[CURRENT_DF.iloc[:, COL_NO] == str(no)]
    if row_df.empty:
        return "<h2>경기 없음</h2>"

    row = row_df.iloc[0]

    home   = row.iloc[COL_HOME]
    away   = row.iloc[COL_AWAY]
    league = row.iloc[COL_LEAGUE]

    five_cond_text = (
        f"{row.iloc[COL_TYPE]} · "
        f"{row.iloc[COL_HOMEAWAY]} · "
        f"{row.iloc[COL_GENERAL]} · "
        f"{row.iloc[COL_DIR]} · "
        f"{row.iloc[COL_HANDI]}"
    )

    league_cond_text = (
        f"{row.iloc[COL_LEAGUE]} · "
        f"{row.iloc[COL_TYPE]} · "
        f"{row.iloc[COL_HOMEAWAY]} · "
        f"{row.iloc[COL_GENERAL]} · "
        f"{row.iloc[COL_DIR]} · "
        f"{row.iloc[COL_HANDI]}"
    )

    filtered_df = apply_filters(CURRENT_DF, type, homeaway, general, dir, handi)

    # 카드1 - 5조건 완전일치
    base_cond = build_5cond(row)
    base_df = run_filter(filtered_df, base_cond)
    base_dist = distribution(base_df)

    # 카드1 - 동일 리그 + 5조건
    league_cond = build_league_cond(row)
    league_df = run_filter(filtered_df, league_cond)
    league_dist = distribution(league_df)

    # -----------------------------
    # 카드2 - 리그 포함 + 5조건
    # -----------------------------
    league_keyword = str(row.iloc[COL_LEAGUE])

    league_all_df = filtered_df[
        filtered_df.iloc[:, COL_LEAGUE].str.contains(
            league_keyword, na=False
        )
    ]

    league_all_cond = build_5cond(row)
    league_all_df = run_filter(league_all_df, league_all_cond)
    league_all_dist = distribution(league_all_df)

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

<div style="display:flex;gap:20px;flex-wrap:wrap;">

<div style="flex:1;background:#1e293b;padding:16px;border-radius:16px;min-width:280px;">
<h3>5조건 완전일치</h3>
<div style="font-size:12px;opacity:0.7;margin-bottom:10px;">
{five_cond_text}
</div>
총 {base_dist["총"]}경기
<div>승 {base_dist["wp"]}% ({base_dist["승"]}경기)</div>
{bar_html(base_dist["wp"],"win")}
<div>무 {base_dist["dp"]}% ({base_dist["무"]}경기)</div>
{bar_html(base_dist["dp"],"draw")}
<div>패 {base_dist["lp"]}% ({base_dist["패"]}경기)</div>
{bar_html(base_dist["lp"],"lose")}
</div>

<div style="flex:1;background:#1e293b;padding:16px;border-radius:16px;min-width:280px;">
<h3>동일리그 5조건</h3>
<div style="font-size:12px;opacity:0.7;margin-bottom:10px;">
{league_cond_text}
</div>
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

<button onclick="toggleBox('card2')" 
style="margin-bottom:10px;">
📊 카드2 보기/숨기기
</button>

<div id="card2" 
style="background:#1e293b;
padding:16px;border-radius:16px;
min-width:280px;display:none;">

<h3>리그포함 5조건 분포</h3>

<div style="font-size:12px;opacity:0.7;margin-bottom:10px;">
리그 포함: {league_keyword}
</div>

총 {league_all_dist["총"]}경기

<div>승 {league_all_dist["wp"]}% ({league_all_dist["승"]}경기)</div>
{bar_html(league_all_dist["wp"],"win")}

<div>무 {league_all_dist["dp"]}% ({league_all_dist["무"]}경기)</div>
{bar_html(league_all_dist["dp"],"draw")}

<div>패 {league_all_dist["lp"]}% ({league_all_dist["패"]}경기)</div>
{bar_html(league_all_dist["lp"],"lose")}

</div>

<br><br>

<script>
function toggleBox(id){{
    var el = document.getElementById(id);
    if(el.style.display==="none"){{
        el.style.display="block";
    }}else{{
        el.style.display="none";
    }}
}}
</script>

<br><br>
<button onclick="history.back()">← 뒤로</button>
</body>
</html>
"""

# =====================================================
# Page3 - 팀 분석
# =====================================================

@app.get("/page3", response_class=HTMLResponse)
def page3_view(no: str = None, away: int = 0):

    if not no:
        return "<h2>잘못된 접근</h2>"

    if CURRENT_DF.empty:
        return "<h2>데이터 없음</h2>"

    row_df = CURRENT_DF[CURRENT_DF.iloc[:, COL_NO] == str(no)]
    if row_df.empty:
        return "<h2>경기 없음</h2>"

    row = row_df.iloc[0]

    team_name = row.iloc[COL_AWAY] if away else row.iloc[COL_HOME]
    league = row.iloc[COL_LEAGUE]

    # 전체 경기 (홈+원정)
    team_all_df = CURRENT_DF[
        (
            (CURRENT_DF.iloc[:, COL_HOME] == team_name) |
            (CURRENT_DF.iloc[:, COL_AWAY] == team_name)
        ) &
        (CURRENT_DF.iloc[:, COL_RESULT] != "경기전")
    ]

    # 홈/원정 분리
    if away:
        team_side_df = CURRENT_DF[
            (CURRENT_DF.iloc[:, COL_AWAY] == team_name) &
            (CURRENT_DF.iloc[:, COL_RESULT] != "경기전")
        ]
        side_label = "원정 경기"
    else:
        team_side_df = CURRENT_DF[
            (CURRENT_DF.iloc[:, COL_HOME] == team_name) &
            (CURRENT_DF.iloc[:, COL_RESULT] != "경기전")
        ]
        side_label = "홈 경기"

    dist_all = distribution(team_all_df)
    dist_side = distribution(team_side_df)

    html = f"""
<html>
<body style="background:#0f1720;color:white;
font-family:Arial;padding:30px;">

<h2>📈 팀 분석 - {team_name}</h2>
<div style="opacity:0.7;font-size:12px;margin-bottom:20px;">
리그: {league}
</div>

<div style="display:flex;gap:20px;flex-wrap:wrap;">

<div style="flex:1;background:#1e293b;padding:20px;border-radius:18px;min-width:280px;">

<h3>전체 분포 ({dist_all["총"]}경기)</h3>

<div style="font-size:12px;opacity:0.7;margin-bottom:12px;">
조건: 팀={team_name} · 홈+원정 전체 · 완료경기
</div>

<div>승 {dist_all["wp"]}% ({dist_all["승"]}경기)</div>
{bar_html(dist_all["wp"],"win")}
<div>무 {dist_all["dp"]}% ({dist_all["무"]}경기)</div>
{bar_html(dist_all["dp"],"draw")}
<div>패 {dist_all["lp"]}% ({dist_all["패"]}경기)</div>
{bar_html(dist_all["lp"],"lose")}

</div>

<div style="flex:1;background:#1e293b;padding:20px;border-radius:18px;min-width:280px;">

<h3>{side_label} 분포 ({dist_side["총"]}경기)</h3>

<div style="font-size:12px;opacity:0.7;margin-bottom:12px;">
조건: 팀={team_name} · {side_label} · 완료경기
</div>

<div>승 {dist_side["wp"]}% ({dist_side["승"]}경기)</div>
{bar_html(dist_side["wp"],"win")}
<div>무 {dist_side["dp"]}% ({dist_side["무"]}경기)</div>
{bar_html(dist_side["dp"],"draw")}
<div>패 {dist_side["lp"]}% ({dist_side["패"]}경기)</div>
{bar_html(dist_side["lp"],"lose")}

</div>

</div>

<br><br>
<button onclick="history.back()">← 뒤로</button>

</body>
</html>
"""
    return html

# =====================================================
# Page4 - 배당 분석
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4_view(no: str = None):

    if not no:
        return "<h2>잘못된 접근</h2>"

    if CURRENT_DF.empty:
        return "<h2>데이터 없음</h2>"

    row_df = CURRENT_DF[CURRENT_DF.iloc[:, COL_NO] == str(no)]
    if row_df.empty:
        return "<h2>경기 없음</h2>"

    row = row_df.iloc[0]

    home = row.iloc[COL_HOME]
    away = row.iloc[COL_AWAY]
    league = row.iloc[COL_LEAGUE]

    try:
        win_odds  = float(row.iloc[COL_WIN_ODDS])
        draw_odds = float(row.iloc[COL_DRAW_ODDS])
        lose_odds = float(row.iloc[COL_LOSE_ODDS])
    except:
        return "<h2>배당 데이터 오류</h2>"

    odds_df = CURRENT_DF[
        (CURRENT_DF.iloc[:, COL_WIN_ODDS]  == row.iloc[COL_WIN_ODDS]) &
        (CURRENT_DF.iloc[:, COL_DRAW_ODDS] == row.iloc[COL_DRAW_ODDS]) &
        (CURRENT_DF.iloc[:, COL_LOSE_ODDS] == row.iloc[COL_LOSE_ODDS])
    ]

    odds_df = odds_df[odds_df.iloc[:, COL_RESULT] != "경기전"]

    dist = distribution(odds_df)
    ev_data = safe_ev(dist, row)

    implied_total = (1/win_odds) + (1/draw_odds) + (1/lose_odds)
    margin = round((implied_total - 1) * 100, 2)

    html = f"""
<html>
<body style="background:#0f1720;color:white;
font-family:Arial;padding:30px;">

<h2>💰 배당 분석</h2>
<h3>[{league}] {home} vs {away}</h3>

<button onclick="toggleBox('box1')">📊 분포 보기/숨기기</button>
<div id="box1" style="background:#1e293b;
padding:20px;border-radius:18px;margin-top:12px;">

<h3>배당 분포 ({dist["총"]}경기)</h3>

<div>승 {dist["wp"]}% ({dist["승"]}경기)</div>
{bar_html(dist["wp"],"win")}

<div>무 {dist["dp"]}% ({dist["무"]}경기)</div>
{bar_html(dist["dp"],"draw")}

<div>패 {dist["lp"]}% ({dist["패"]}경기)</div>
{bar_html(dist["lp"],"lose")}

</div>

<br>

<button onclick="toggleBox('box2')">📈 EV 보기/숨기기</button>
<div id="box2" style="background:#1e293b;
padding:20px;border-radius:18px;margin-top:12px;">

<h3>EV 분석</h3>
추천: <b>{ev_data["추천"]}</b><br>
승 EV: {ev_data["EV"]["승"]}<br>
무 EV: {ev_data["EV"]["무"]}<br>
패 EV: {ev_data["EV"]["패"]}

<br><br>
시장 마진: {margin}%

</div>

<br><br>
<button onclick="history.back()">← 뒤로</button>

<script>
function toggleBox(id) {{
    var el = document.getElementById(id);
    if(el.style.display==="none") {{
        el.style.display="block";
    }} else {{
        el.style.display="none";
    }}
}}
</script>

</body>
</html>
"""
    return html

# =====================================================
# 고신뢰도 시크릿픽 전용 API
# =====================================================

@app.get("/high-confidence")
def high_confidence(min_conf: float = MIN_CONFIDENCE):

    if CURRENT_DF.empty:
        return []

    result = []

    base_df = CURRENT_DF[CURRENT_DF.iloc[:, COL_RESULT] == "경기전"]

    for _, row in base_df.iterrows():

        brain = secret_pick_brain(row, CURRENT_DF)

        if brain["confidence"] >= min_conf:

            result.append({
                "no": row.iloc[COL_NO],
                "home": row.iloc[COL_HOME],
                "away": row.iloc[COL_AWAY],
                "추천": brain["추천"],
                "confidence": brain["confidence"],
                "sample": brain["sample"]
            })

    return result

# =====================================================
# EV 기준 상위 경기 추출 API
# =====================================================

@app.get("/top-ev")
def top_ev(limit: int = 20):

    if CURRENT_DF.empty:
        return []

    candidates = []

    base_df = CURRENT_DF[CURRENT_DF.iloc[:, COL_RESULT] == "경기전"]

    for _, row in base_df.iterrows():

        key = (
            row.iloc[COL_TYPE],
            row.iloc[COL_HOMEAWAY],
            row.iloc[COL_GENERAL],
            row.iloc[COL_DIR],
            row.iloc[COL_HANDI]
        )

        dist = FIVE_COND_DIST.get(key)

        if not dist or dist["총"] < 10:
            continue

        ev_data = safe_ev(dist, row)
        best_ev = max(ev_data["EV"].values())

        candidates.append({
            "no": row.iloc[COL_NO],
            "home": row.iloc[COL_HOME],
            "away": row.iloc[COL_AWAY],
            "추천": ev_data["추천"],
            "EV": round(best_ev, 4),
            "sample": dist["총"]
        })

    return sorted(candidates, key=lambda x: x["EV"], reverse=True)[:limit]

# =====================================================
# 고EV + 고신뢰도 복합 필터 API
# =====================================================

@app.get("/elite-picks")
def elite_picks(min_ev: float = 0.05,
                min_conf: float = 0.45):

    if CURRENT_DF.empty:
        return []

    result = []

    base_df = CURRENT_DF[CURRENT_DF.iloc[:, COL_RESULT] == "경기전"]

    for _, row in base_df.iterrows():

        key = (
            row.iloc[COL_TYPE],
            row.iloc[COL_HOMEAWAY],
            row.iloc[COL_GENERAL],
            row.iloc[COL_DIR],
            row.iloc[COL_HANDI]
        )

        dist = FIVE_COND_DIST.get(key)

        if not dist or dist["총"] < 20:
            continue

        ev_data = safe_ev(dist, row)
        best_ev = max(ev_data["EV"].values())

        brain = secret_pick_brain(row, CURRENT_DF)

        if best_ev >= min_ev and brain["confidence"] >= min_conf:

            result.append({
                "no": row.iloc[COL_NO],
                "home": row.iloc[COL_HOME],
                "away": row.iloc[COL_AWAY],
                "EV": round(best_ev, 4),
                "confidence": brain["confidence"],
                "추천": brain["추천"]
            })

    return sorted(result, key=lambda x: (x["confidence"], x["EV"]), reverse=True)

# =====================================================
# 전략 성능 시뮬레이션 API (누적 EV 기반)
# =====================================================

@app.get("/strategy-sim")
def strategy_sim(min_sample: int = 20):

    if CURRENT_DF.empty:
        return {"status": "no data"}

    total_profit = 0
    bet_count = 0

    completed = CURRENT_DF[CURRENT_DF.iloc[:, COL_RESULT] != "경기전"]

    for _, row in completed.iterrows():

        key = (
            row.iloc[COL_TYPE],
            row.iloc[COL_HOMEAWAY],
            row.iloc[COL_GENERAL],
            row.iloc[COL_DIR],
            row.iloc[COL_HANDI]
        )

        dist = FIVE_COND_DIST.get(key)

        if not dist or dist["총"] < min_sample:
            continue

        ev_data = safe_ev(dist, row)
        pick = ev_data["추천"]
        actual = row.iloc[COL_RESULT]

        odds_map = {
            "승": float(row.iloc[COL_WIN_ODDS]),
            "무": float(row.iloc[COL_DRAW_ODDS]),
            "패": float(row.iloc[COL_LOSE_ODDS])
        }

        if pick == actual:
            total_profit += odds_map[pick] - 1
        else:
            total_profit -= 1

        bet_count += 1

    roi = round((total_profit / bet_count), 4) if bet_count > 0 else 0

    return {
        "bets": bet_count,
        "total_profit": round(total_profit, 4),
        "ROI": roi
    }

# =====================================================
# 리스크 등급 분류 API
# =====================================================

@app.get("/risk-grade")
def risk_grade(no: str):

    if CURRENT_DF.empty:
        return {"status": "no data"}

    row_df = CURRENT_DF[CURRENT_DF.iloc[:, COL_NO] == str(no)]
    if row_df.empty:
        return {"status": "match not found"}

    row = row_df.iloc[0]
    brain = secret_pick_brain(row, CURRENT_DF)

    conf = brain["confidence"]

    if conf >= 0.65:
        grade = "A"
    elif conf >= 0.50:
        grade = "B"
    elif conf >= 0.40:
        grade = "C"
    else:
        grade = "D"

    return {
        "home": row.iloc[COL_HOME],
        "away": row.iloc[COL_AWAY],
        "confidence": conf,
        "risk_grade": grade
    }

# =====================================================
# 회차별 ROI 추적 API
# =====================================================

@app.get("/round-roi")
def round_roi():

    if CURRENT_DF.empty:
        return {"status": "no data"}

    completed = CURRENT_DF[CURRENT_DF.iloc[:, COL_RESULT] != "경기전"]

    grouped = completed.groupby(completed.iloc[:, COL_ROUND])

    report = []

    for rnd, group in grouped:

        profit = 0
        bets = 0

        for _, row in group.iterrows():

            key = (
                row.iloc[COL_TYPE],
                row.iloc[COL_HOMEAWAY],
                row.iloc[COL_GENERAL],
                row.iloc[COL_DIR],
                row.iloc[COL_HANDI]
            )

            dist = FIVE_COND_DIST.get(key)

            if not dist or dist["총"] < 20:
                continue

            ev_data = safe_ev(dist, row)
            pick = ev_data["추천"]
            actual = row.iloc[COL_RESULT]

            odds_map = {
                "승": float(row.iloc[COL_WIN_ODDS]),
                "무": float(row.iloc[COL_DRAW_ODDS]),
                "패": float(row.iloc[COL_LOSE_ODDS])
            }

            if pick == actual:
                profit += odds_map[pick] - 1
            else:
                profit -= 1

            bets += 1

        roi = round((profit / bets), 4) if bets > 0 else 0

        report.append({
            "round": rnd,
            "bets": bets,
            "ROI": roi
        })

    return sorted(report, key=lambda x: x["round"])

# =====================================================
# Strategy 1 View
# =====================================================

@app.get("/strategy1-view", response_class=HTMLResponse)
def strategy1_view():

    return """
    <html>
    <body style="background:#0f1720;color:white;padding:30px;font-family:Arial;">
    <h2>🧠 전략 1 분석 (High Confidence)</h2>
    <div id="content"></div>

    <script>
    fetch("/high-confidence")
    .then(res=>res.json())
    .then(data=>{
        let html="";
        data.forEach(m=>{
            html += `<div style="margin-bottom:12px;">
            ${m.home} vs ${m.away} → ${m.추천} (${m.confidence})
            </div>`;
        });
        document.getElementById("content").innerHTML=html;
    });
    </script>

    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

# =====================================================
# Strategy 2 View
# =====================================================

@app.get("/strategy2-view", response_class=HTMLResponse)
def strategy2_view():

    return """
    <html>
    <body style="background:#0f1720;color:white;padding:30px;font-family:Arial;">
    <h2>🎯 전략 2 (Top EV)</h2>
    <div id="content"></div>

    <script>
    fetch("/top-ev")
    .then(res=>res.json())
    .then(data=>{
        let html="";
        data.forEach(m=>{
            html += `<div style="margin-bottom:12px;">
            ${m.home} vs ${m.away} → ${m.추천} (EV ${m.EV})
            </div>`;
        });
        document.getElementById("content").innerHTML=html;
    });
    </script>

    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

# =====================================================
# History View
# =====================================================

@app.get("/history", response_class=HTMLResponse)
def history_view():

    return """
    <html>
    <body style="background:#0f1720;color:white;padding:30px;font-family:Arial;">
    <h2>📊 회차별 ROI</h2>
    <div id="content"></div>

    <script>
    fetch("/round-roi")
    .then(res=>res.json())
    .then(data=>{
        let html="";
        data.forEach(r=>{
            html += `<div>
            ${r.round}회차 → ROI ${r.ROI} (${r.bets}경기)
            </div>`;
        });
        document.getElementById("content").innerHTML=html;
    });
    </script>

    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

# =====================================================
# Evaluate View
# =====================================================

@app.get("/evaluate", response_class=HTMLResponse)
def evaluate_view():

    return """
    <html>
    <body style="background:#0f1720;color:white;padding:30px;font-family:Arial;">
    <h2>🧪 전략 시뮬레이션</h2>
    <div id="content"></div>

    <script>
    fetch("/strategy-sim")
    .then(res=>res.json())
    .then(data=>{
        document.getElementById("content").innerHTML =
        `베팅수: ${data.bets}<br>
         총수익: ${data.total_profit}<br>
         ROI: ${data.ROI}`;
    });
    </script>

    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

# =====================================================
# 시스템 상태 리포트
# =====================================================

@app.get("/system-report")
def system_report():

    return {
        "rows": len(CURRENT_DF),
        "five_cond_cache": len(FIVE_COND_DIST),
        "league_count": len(LEAGUE_COUNT),
        "league_weight": len(LEAGUE_WEIGHT),
        "favorites": len(FAVORITES),
        "dist_cache": len(DIST_CACHE),
        "secret_cache": len(SECRET_CACHE)
    }

# =====================================================
# 데이터 정합성 점검
# =====================================================

@app.get("/data-validate")
def data_validate():

    if CURRENT_DF.empty:
        return {"status": "no data"}

    issues = []

    if CURRENT_DF.shape[1] != EXPECTED_COLS:
        issues.append("컬럼 수 불일치")

    if CURRENT_DF.iloc[:, COL_RESULT].isnull().sum() > 0:
        issues.append("결과 컬럼 null 존재")

    if CURRENT_DF.iloc[:, COL_TYPE].isnull().sum() > 0:
        issues.append("유형 컬럼 null 존재")

    return {
        "rows": len(CURRENT_DF),
        "issues": issues if issues else "정상"
    }

# =====================================================
# 캐시 강제 초기화
# =====================================================

@app.get("/cache-clear")
def cache_clear():

    DIST_CACHE.clear()
    SECRET_CACHE.clear()
    FIVE_COND_DIST.clear()
    LEAGUE_COUNT.clear()
    LEAGUE_WEIGHT.clear()

    if not CURRENT_DF.empty:
        build_five_cond_cache(CURRENT_DF)
        build_league_weight(CURRENT_DF)

    return {
        "status": "cache rebuilt",
        "five_cond_cache": len(FIVE_COND_DIST),
        "league_weight": len(LEAGUE_WEIGHT)
    }

# =====================================================
# 요청 처리 시간 측정 미들웨어
# =====================================================

@app.middleware("http")
async def process_time_middleware(request, call_next):
    start_time = time.time()
    response: Response = await call_next(request)
    process_time = round((time.time() - start_time) * 1000, 2)
    response.headers["X-Process-Time-ms"] = str(process_time)
    return response

# =====================================================
# 글로벌 예외 핸들러
# =====================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"[ERROR] {request.url} -> {str(exc)}")
    traceback.print_exc()

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc)
        }
    )

# =====================================================
# 서버 시작 / 종료 로그
# =====================================================

@app.on_event("startup")
def startup_log():
    print("=====================================")
    print(" SecretCore PRO Server Started")
    print(f" Data Loaded: {not CURRENT_DF.empty}")
    print(f" Rows: {len(CURRENT_DF)}")
    print(f" FiveCond Cache: {len(FIVE_COND_DIST)}")
    print(f" League Weight: {len(LEAGUE_WEIGHT)}")
    print("=====================================")


@app.on_event("shutdown")
def shutdown_log():
    print("=====================================")
    print(" SecretCore PRO Server Shutdown")
    print("=====================================")