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
STRATEGY_HISTORY_FILE = "strategy_history.json"
# 최소 신뢰도 컷
MIN_CONFIDENCE = 0.32

# 리그 가중치 캐시
LEAGUE_COUNT = {}
LEAGUE_WEIGHT = {}

# =====================================================
# 5조건 사전 분포 캐시 (속도 개선)
# =====================================================
FIVE_COND_DIST = {}

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

        # ✅ 데이터 로드 후 캐시 재빌드
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

    if len(df) == 0:
        key = ("empty", 0)
    else:
        key = (len(df), df.iloc[0, COL_NO])

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
# 5조건 사전 집계 생성
# =====================================================
def build_five_cond_cache(df):
    global FIVE_COND_DIST
    FIVE_COND_DIST.clear()

    if df.empty:
        return

    # 5조건 그룹핑
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

    if not FIVE_COND_DIST:
        build_five_cond_cache(df)
        build_league_weight(df)

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
# SecretPick Brain (SP 단독 실험용)
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

    # ===== 동적 가중치 =====
    if sample < 20:
        w5 = 0.4
    elif sample < 50:
        w5 = 0.5
    elif sample < 150:
        w5 = 0.65
    else:
        w5 = 0.75

    w_exact = 1 - w5

    # ===== 배당 완전일치 =====
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

    # ===== 리그 가중치 적용 =====
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
# dtype=str 유지
# 컬럼 검증
# DIST_CACHE + SECRET_CACHE 초기화
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

    # 캐시 지연 생성 (lazy build)
    FIVE_COND_DIST.clear()
    LEAGUE_COUNT.clear()
    LEAGUE_WEIGHT.clear()

    return RedirectResponse("/", status_code=302)


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
# 필터 값 추출 API (Page1 모달용)
# 동적 데이터 기반
# =====================================================

@app.get("/filters")
def filters():

    df = CURRENT_DF

    if df.empty:
        return {}

    # 🔥 경기전만 기준으로 필터 목록 생성
    df = df[df.iloc[:, COL_RESULT] == "경기전"]

    return {
        "type": sorted(df.iloc[:, COL_TYPE].dropna().unique().tolist()),
        "homeaway": sorted(df.iloc[:, COL_HOMEAWAY].dropna().unique().tolist()),
        "general": sorted(df.iloc[:, COL_GENERAL].dropna().unique().tolist()),
        "dir": sorted(df.iloc[:, COL_DIR].dropna().unique().tolist()),
        "handi": sorted(df.iloc[:, COL_HANDI].dropna().unique().tolist())
    }

# =====================================================
# Page1 - 메인 (PRO UI + 다중필터 + 조건표시줄)
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
.star-btn{position:absolute;right:14px;top:40px;font-size:18px;color:#6b7280;}
.star-active{color:#facc15;}

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

.checkbox-group{
margin-bottom:12px;
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

<!-- 필터 모달 -->
<div class="modal" id="filterModal">
  <div class="modal-content">
    <h3>필터</h3>
    <div id="filterArea"></div>
    <button onclick="applyFilters()">적용</button>
    <button onclick="closeModal()">닫기</button>
  </div>
</div>

<script>

function resetFilters(){
    window.location.href="/";
}

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
            params.set(el.name,
                params.get(el.name)+","+el.value);
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

    let text = "";

    if(data.length > 0){
        let first = data[0].row;
        let year = first[1];
        let round = first[2];
        text = year + "년 · " + round + "회차";
    } else {
        text = "경기 없음";
    }

    document.getElementById("conditionBar").innerText = text;
}

async function toggleFav(home,away,el){
    let res = await fetch("/fav-toggle",{
        method:"POST",
        headers:{"Content-Type":"application/x-www-form-urlencoded"},
        body:`home=${home}&away=${away}`
    });
    let data = await res.json();
    if(data.status=="added") el.classList.add("star-active");
    else el.classList.remove("star-active");
}

async function load(){

    updateConditionBar();

    let params = new URLSearchParams(window.location.search);
    let r = await fetch('/matches?' + params.toString());
    let data = await r.json();

    let html="";

    data.forEach(function(m){

        let row = m.row;

        let badge = "";

if(m.secret){

    badge = `
    <div style="
        position:absolute;
        right:18px;
        top:50%;
        transform:translateY(-50%);
        background:#22c55e;
        color:#0f1720;
        padding:8px 12px;
        border-radius:14px;
        font-size:12px;
        font-weight:bold;
        box-shadow:0 4px 10px rgba(0,0,0,0.4);
    ">
        시크릿픽 ${m.pick}
    </div>
    `;
}

        html+=`
        <div class="card">
        ${badge}
        <div><b>${row[6]}</b> vs <b>${row[7]}</b></div>
        <div>승 ${row[8]} | 무 ${row[9]} | 패 ${row[10]}</div>
        <div>${row[14]} · ${row[16]} · ${row[11]} · ${row[15]} · ${row[12]}</div>
        <div class="info-btn">
            <a href="/detail?no=${row[0]}" style="color:#38bdf8;">정보</a>
        </div>
        <div class="star-btn"
        onclick="toggleFav('${row[6]}','${row[7]}',this)">★</div>
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
# 경기목록 API (다중필터 + SECRET 최적화)
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

    base_df = apply_filters(
        base_df, type, homeaway, general, dir, handi
    )

    result = []

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
        "pick": sec["추천"] if is_secret else ""
    })

    return result

# =====================================================
# 즐겨찾기 토글
# =====================================================

@app.post("/fav-toggle")
def fav_toggle(home: str = Form(...), away: str = Form(...)):

    global FAVORITES

    key = f"{home}__{away}"

    if key in FAVORITES:
        FAVORITES.remove(key)
        return {"status": "removed"}
    else:
        FAVORITES.append(key)
        return {"status": "added"}

# =====================================================
# Ledger
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

# =====================================================
# Memo
# =====================================================

@app.get("/memo", response_class=HTMLResponse)
def memo_page():
    return """
    <html><body style='background:#0f1720;color:white;padding:30px;'>
    <h2>📝 Memo</h2>
    <p>준비중입니다.</p>
    <button onclick="history.back()">← 뒤로</button>
    </body></html>
    """

# =====================================================
# Capture
# =====================================================

@app.get("/capture", response_class=HTMLResponse)
def capture_page():
    return """
    <html><body style='background:#0f1720;color:white;padding:30px;'>
    <h2>📸 Capture</h2>
    <p>준비중입니다.</p>
    <button onclick="history.back()">← 뒤로</button>
    </body></html>
    """

# =====================================================
# Favorites
# =====================================================

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
# Page2 - 상세 분석 (필터 기반 분포 + 시크릿픽)
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

    # =========================
    # 필터 적용
    # =========================

    filtered_df = apply_filters(
        df, type, homeaway, general, dir, handi
    )

    # 5조건 완전일치 → 필터 기반
    base_cond = build_5cond(row)
    base_df = run_filter(filtered_df, base_cond)
    base_dist = distribution(base_df)

    # 동일리그 5조건 → 필터 기반
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

    <div>승 {base_dist["wp"]}% ({base_dist["승"]}경기)</div>
{bar_html(base_dist["wp"],"win")}

<div>무 {base_dist["dp"]}% ({base_dist["무"]}경기)</div>
{bar_html(base_dist["dp"],"draw")}

<div>패 {base_dist["lp"]}% ({base_dist["패"]}경기)</div>
{bar_html(base_dist["lp"],"lose")}

    <!-- 동일리그 -->
    <div style="flex:1;background:#1e293b;
                padding:16px;border-radius:16px;">

    <h3>동일리그 5조건</h3>
    총 {league_dist["총"]}경기

    <div>승 {league_dist["wp"]}% ({league_dist["승"]}경기)</div>
{bar_html(league_dist["wp"],"win")}

<div>무 {league_dist["dp"]}% ({league_dist["무"]}경기)</div>
{bar_html(league_dist["dp"],"draw")}

<div>패 {league_dist["lp"]}% ({league_dist["패"]}경기)</div>
{bar_html(league_dist["lp"],"lose")}

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
# Page3 - 팀 분석 (홈/원정 분리 + 필터 기반 + 막대그래프)
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

<div>승 {all_dist["wp"]}% ({all_dist["승"]}경기)</div>
{bar_html(all_dist["wp"],"win")}

<div>무 {all_dist["dp"]}% ({all_dist["무"]}경기)</div>
{bar_html(all_dist["dp"],"draw")}

<div>패 {all_dist["lp"]}% ({all_dist["패"]}경기)</div>
{bar_html(all_dist["lp"],"lose")}
    </details>

    <br>

    <details>
    <summary><b>홈 vs 원정 비교</b></summary>

    <div style="display:flex;gap:12px;">

    <div style="flex:1;background:#1e293b;padding:12px;border-radius:12px;">
<b>홈</b><br>
총 {home_dist["총"]}경기

<div>승 {home_dist["wp"]}% ({home_dist["승"]}경기)</div>
{bar_html(home_dist["wp"],"win")}

<div>무 {home_dist["dp"]}% ({home_dist["무"]}경기)</div>
{bar_html(home_dist["dp"],"draw")}

<div>패 {home_dist["lp"]}% ({home_dist["패"]}경기)</div>
{bar_html(home_dist["lp"],"lose")}
</div>

    <div style="flex:1;background:#1e293b;padding:12px;border-radius:12px;">
<b>원정</b><br>
총 {away_dist["총"]}경기

<div>승 {away_dist["wp"]}% ({away_dist["승"]}경기)</div>
{bar_html(away_dist["wp"],"win")}

<div>무 {away_dist["dp"]}% ({away_dist["무"]}경기)</div>
{bar_html(away_dist["dp"],"draw")}

<div>패 {away_dist["lp"]}% ({away_dist["패"]}경기)</div>
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
# Page4 - 배당 분석 (필터 기반 + 3열 EV + 접기 + 막대그래프)
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

<div>승 {exact_dist["wp"]}% ({exact_dist["승"]}경기)</div>
{bar_html(exact_dist["wp"],"win")}

<div>무 {exact_dist["dp"]}% ({exact_dist["무"]}경기)</div>
{bar_html(exact_dist["dp"],"draw")}

<div>패 {exact_dist["lp"]}% ({exact_dist["패"]}경기)</div>
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

<div>승 {win_dist["wp"]}% ({win_dist["승"]}경기)</div>
{bar_html(win_dist["wp"],"win")}

<div>무 {win_dist["dp"]}% ({win_dist["무"]}경기)</div>
{bar_html(win_dist["dp"],"draw")}

<div>패 {win_dist["lp"]}% ({win_dist["패"]}경기)</div>
{bar_html(win_dist["lp"],"lose")}
    </details>

    <br>

    <details>
    <summary><b>무 동일 통계</b></summary>
    총 {draw_dist["총"]}경기

<div>승 {draw_dist["wp"]}% ({draw_dist["승"]}경기)</div>
{bar_html(draw_dist["wp"],"win")}

<div>무 {draw_dist["dp"]}% ({draw_dist["무"]}경기)</div>
{bar_html(draw_dist["dp"],"draw")}

<div>패 {draw_dist["lp"]}% ({draw_dist["패"]}경기)</div>
{bar_html(draw_dist["lp"],"lose")}
    </details>

    <br>

    <details>
    <summary><b>패 동일 통계</b></summary>
    총 {lose_dist["총"]}경기

<div>승 {lose_dist["wp"]}% ({lose_dist["승"]}경기)</div>
{bar_html(lose_dist["wp"],"win")}

<div>무 {lose_dist["dp"]}% ({lose_dist["무"]}경기)</div>
{bar_html(lose_dist["dp"],"draw")}

<div>패 {lose_dist["lp"]}% ({lose_dist["패"]}경기)</div>
{bar_html(lose_dist["lp"],"lose")}
    </details>

    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

# =====================================================
# Strategy1 - 3x3x3x3 = 81조합
# =====================================================

@app.get("/strategy1")
def strategy1():

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

    candidates = []

    for _, row in base_df.iterrows():

        brain = secret_pick_brain(row, df)

        candidates.append({
            "no": row.iloc[COL_NO],
            "home": row.iloc[COL_HOME],
            "away": row.iloc[COL_AWAY],
            "league": row.iloc[COL_LEAGUE],
            "pick": brain["추천"],
            "confidence": brain["confidence"],
            "odds": float(row.iloc[COL_WIN_ODDS])
                    if brain["추천"] == "승"
                    else float(row.iloc[COL_DRAW_ODDS])
                    if brain["추천"] == "무"
                    else float(row.iloc[COL_LOSE_ODDS])
        })

    candidates.sort(key=lambda x: x["confidence"], reverse=True)

    # confidence 컷 적용
    candidates = [c for c in candidates if 
    c["confidence"] >= MIN_CONFIDENCE]

    if len(candidates) < 12:
        return {"error":"경기 수 부족"}

    # 리그 중복 방지 포트 구성
    def build_port(pool, size, used_leagues):
        port = []
        for c in pool:
            if len(port) == size:
                break
            if c["league"] not in used_leagues:
                port.append(c)
                used_leagues.add(c["league"])
        return port

    used = set()

    port1 = build_port(candidates, 3, used)
    port2 = build_port([c for c in candidates if c not in port1], 3, used)
    port3 = build_port([c for c in candidates if c not in port1+port2], 3, used)
    port4 = build_port([c for c in candidates if c not in port1+port2+port3], 3, used)

    combos = []

    for a in port1:
        for b in port2:
            for c in port3:
                for d in port4:
                    combos.append({
                        "matches":[a,b,c,d],
                        "combo_odds": round(
                            a["odds"] *
                            b["odds"] *
                            c["odds"] *
                            d["odds"], 2
                        )
                    })

    return {
        "port1": port1,
        "port2": port2,
        "port3": port3,
        "port4": port4,
        "total_combos": len(combos)
    }

# =====================================================
# Strategy2 - 10x10 = 100조합
# =====================================================

@app.get("/strategy2")
def strategy2():

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

    candidates = []

    for _, row in base_df.iterrows():

        brain = secret_pick_brain(row, df)

        candidates.append({
            "no": row.iloc[COL_NO],
            "home": row.iloc[COL_HOME],
            "away": row.iloc[COL_AWAY],
            "pick": brain["추천"],
            "confidence": brain["confidence"],
            "odds": float(row.iloc[COL_WIN_ODDS])
                    if brain["추천"] == "승"
                    else float(row.iloc[COL_DRAW_ODDS])
                    if brain["추천"] == "무"
                    else float(row.iloc[COL_LOSE_ODDS])
        })

    # confidence 기준 정렬
    candidates.sort(key=lambda x: x["confidence"], reverse=True)

    # confidence 컷 적용
    candidates = [c for c in candidates if 
    c["confidence"] >= MIN_CONFIDENCE]

    if len(candidates) < 20:
        return {"error":"경기 수 부족"}

    port1 = candidates[0:10]
    port2 = candidates[10:20]

    combos = []

    for a in port1:
        for b in port2:
            combos.append({
                "match1": a,
                "match2": b,
                "combo_odds": round(
                    a["odds"] * b["odds"], 2
                )
            })

    return {
        "port1": port1,
        "port2": port2,
        "total_combos": len(combos)
    }

# =====================================================
# 전략 결과 평가 + ROI 계산
# =====================================================

import json

def evaluate_strategy1():

    df = CURRENT_DF
    if df.empty:
        return None

    strategy = strategy1()
    if "error" in strategy:
        return None

    ports = [
        strategy["port1"],
        strategy["port2"],
        strategy["port3"],
        strategy["port4"]
    ]

    hit_counts = []

    for port in ports:
        hits = 0
        for item in port:
            row = df[df.iloc[:, COL_NO] == item["no"]]
            if not row.empty:
                result = row.iloc[0][COL_RESULT]
                if result == item["pick"]:
                    hits += 1
        hit_counts.append(hits)

    a,b,c,d = hit_counts
    success_combos = a*b*c*d

    total_invest = 81 * 1000
    total_profit = 0

    if success_combos > 0:
        for p1 in ports[0]:
            for p2 in ports[1]:
                for p3 in ports[2]:
                    for p4 in ports[3]:
                        rows = [
                            df[df.iloc[:, COL_NO]==p1["no"]],
                            df[df.iloc[:, COL_NO]==p2["no"]],
                            df[df.iloc[:, COL_NO]==p3["no"]],
                            df[df.iloc[:, COL_NO]==p4["no"]],
                        ]
                        if all(not r.empty and r.iloc[0][COL_RESULT]==pick["pick"]
                               for r,pick in zip(rows,[p1,p2,p3,p4])):
                            total_profit += (
                                p1["odds"] *
                                p2["odds"] *
                                p3["odds"] *
                                p4["odds"] * 1000
                            )

    net = total_profit - total_invest
    roi = round(net/total_invest*100,1)

    return {
        "strategy":"strategy1",
        "hits":hit_counts,
        "success_combos":success_combos,
        "total_invest":total_invest,
        "total_profit":round(total_profit,0),
        "net":round(net,0),
        "roi":roi
    }

def evaluate_strategy2():

    df = CURRENT_DF
    if df.empty:
        return None

    strategy = strategy2()
    if "error" in strategy:
        return None

    port1 = strategy["port1"]
    port2 = strategy["port2"]

    hit1 = []
    hit2 = []

    for item in port1:
        row = df[df.iloc[:, COL_NO] == item["no"]]
        if not row.empty and row.iloc[0][COL_RESULT]==item["pick"]:
            hit1.append(item)

    for item in port2:
        row = df[df.iloc[:, COL_NO] == item["no"]]
        if not row.empty and row.iloc[0][COL_RESULT]==item["pick"]:
            hit2.append(item)

    success_combos = len(hit1) * len(hit2)

    total_invest = 100 * 1000
    total_profit = 0

    for a in hit1:
        for b in hit2:
            total_profit += a["odds"] * b["odds"] * 1000

    net = total_profit - total_invest
    roi = round(net/total_invest*100,1)

    return {
        "strategy":"strategy2",
        "hit1":len(hit1),
        "hit2":len(hit2),
        "success_combos":success_combos,
        "total_invest":total_invest,
        "total_profit":round(total_profit,0),
        "net":round(net,0),
        "roi":roi
    }

@app.get("/evaluate")
def evaluate():

    s1 = evaluate_strategy1()
    s2 = evaluate_strategy2()

    record = {
        "strategy1": s1,
        "strategy2": s2
    }

    if os.path.exists(STRATEGY_HISTORY_FILE):
        with open(STRATEGY_HISTORY_FILE,"r") as f:
            history = json.load(f)
    else:
        history = []

    history.append(record)

    with open(STRATEGY_HISTORY_FILE,"w") as f:
        json.dump(history,f,indent=2)

    return record

# =====================================================
# 전략1 UI 페이지
# =====================================================

@app.get("/strategy1-view", response_class=HTMLResponse)
def strategy1_view():

    if not LOGGED_IN:
        return RedirectResponse("/", status_code=302)

    data = strategy1()

    if "error" in data:
        return "<h2>경기 수 부족</h2>"

    html = "<h2>🧠 전략1</h2>"

    for i, port in enumerate(
        [data["port1"], data["port2"], data["port3"], data["port4"]],
        start=1
    ):
        html += f"<h3>Port{i}</h3>"
        for m in port:
            html += f"""
            <div>
            {m["home"]} vs {m["away"]} |
            <b>{m["pick"]}</b> |
            배당 {m["odds"]}
            </div>
            """

    html += f"<br>총 조합수: {data['total_combos']}"

    # ===== 평균/최소/최대 배당 계산 =====
    combo_odds = []

    for a in data["port1"]:
        for b in data["port2"]:
            for c in data["port3"]:
                for d in data["port4"]:
                    combo_odds.append(
                        a["odds"] *
                        b["odds"] *
                        c["odds"] *
                        d["odds"]
                    )

    avg_odds = round(sum(combo_odds)/len(combo_odds),2)
    min_odds = round(min(combo_odds),2)
    max_odds = round(max(combo_odds),2)
    avg_return = round(avg_odds * 1000,0)

    html += f"""
    <br>
    평균 조합 배당: {avg_odds}<br>
    최소 조합 배당: {min_odds}<br>
    최대 조합 배당: {max_odds}<br>
    1000원 기준 평균 수익: {avg_return}원
    """

    return f"""
    <html>
    <body style="background:#0f1720;color:white;padding:20px;">
    {html}
    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

# =====================================================
# 전략2 UI 페이지
# =====================================================

@app.get("/strategy2-view", response_class=HTMLResponse)
def strategy2_view():

    if not LOGGED_IN:
        return RedirectResponse("/", status_code=302)

    data = strategy2()

    if "error" in data:
        return "<h2>경기 수 부족</h2>"

    html = "<h2>🎯 전략2 (10x10 = 100조합)</h2>"

    for i, port in enumerate(
        [data["port1"], data["port2"]],
        start=1
    ):
        html += f"<h3>Port{i}</h3>"
        for m in port:
            html += f"""
            <div>
            {m["home"]} vs {m["away"]} |
            <b>{m["pick"]}</b> |
            배당 {m["odds"]}
            </div>
            """

    html += f"<br>총 조합수: {data['total_combos']}"

    # ===== 평균/최소/최대 배당 계산 =====
    combo_odds = []

    for a in data["port1"]:
        for b in data["port2"]:
            combo_odds.append(
                a["odds"] *
                b["odds"]
            )

    avg_odds = round(sum(combo_odds)/len(combo_odds),2)
    min_odds = round(min(combo_odds),2)
    max_odds = round(max(combo_odds),2)
    avg_return = round(avg_odds * 1000,0)

    html += f"""
    <br>
    평균 조합 배당: {avg_odds}<br>
    최소 조합 배당: {min_odds}<br>
    최대 조합 배당: {max_odds}<br>
    1000원 기준 평균 수익: {avg_return}원
    """

    return f"""
    <html>
    <body style="background:#0f1720;color:white;padding:20px;">
    {html}
    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

@app.get("/history", response_class=HTMLResponse)
def history_page():

    if not LOGGED_IN:
        return RedirectResponse("/", status_code=302)

    if not os.path.exists(STRATEGY_HISTORY_FILE):
        return "<h2>기록 없음</h2>"

    with open(STRATEGY_HISTORY_FILE,"r") as f:
        history = json.load(f)

    total_net_s1 = 0
    total_net_s2 = 0

    rows = ""

    for i, record in enumerate(history, start=1):

        s1 = record.get("strategy1")
        s2 = record.get("strategy2")

        if s1:
            total_net_s1 += s1["net"]
        if s2:
            total_net_s2 += s2["net"]

        rows += f"""
        <tr>
            <td>{i}</td>
            <td>{s1["roi"] if s1 else "-"}</td>
            <td>{s2["roi"] if s2 else "-"}</td>
        </tr>
        """

    return f"""
    <html>
    <body style='background:#0f1720;color:white;padding:30px;font-family:Arial;'>

    <h2>📊 전략 히스토리</h2>

    <table border="1" cellpadding="8" style="border-collapse:collapse;">
        <tr>
            <th>회차</th>
            <th>Strategy1 ROI</th>
            <th>Strategy2 ROI</th>
        </tr>
        {rows}
    </table>

    <br><br>

    <h3>누적 결과</h3>
    Strategy1 누적 손익: {round(total_net_s1,0)} 원<br>
    Strategy2 누적 손익: {round(total_net_s2,0)} 원<br>

    <br>
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