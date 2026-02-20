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
# 루프엔진 조건 빌더
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
# SECRET 점수
# =====================================================

def secret_score(row, df):

    cond = build_5cond(row)
    sub_df = run_filter(df, cond)
    dist = distribution(sub_df)

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
# 업로드 처리 (dtype=str 유지 + 컬럼검증 + 캐시초기화)
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
        return {"error": f"컬럼 불일치: {df.shape[1]} / 기대값 {EXPECTED_COLS}"}

    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

    CURRENT_DF = df
    DIST_CACHE.clear()

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
    report["expected_cols"] = EXPECTED_COLS

    return report

# =====================================================
# Health Check
# =====================================================

@app.get("/health")
def health():
    return {"self_check": self_check()}

# =====================================================
# Page1 - 메인 (PRO UI + COL_NO 단일키)
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
background:#111827;
position:sticky;
top:0;
z-index:50;
}

.logo{
font-weight:700;
font-size:18px;
color:#38bdf8;
}

.top-icons{
display:flex;
gap:18px;
font-size:18px;
}

.card{
background:#1e293b;
margin:14px;
padding:18px;
border-radius:18px;
position:relative;
box-shadow:0 4px 12px rgba(0,0,0,0.3);
}

.info-btn{
position:absolute;
right:14px;
top:12px;
font-size:12px;
cursor:pointer;
}

.star-btn{
position:absolute;
right:14px;
top:40px;
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
        <div onclick="location.reload()">🔄</div>
        <div>🔍</div>
        <div onclick="location.href='/page-upload'">📤</div>
        <div onclick="location.href='/logout'">👤</div>
    </div>
</div>

<div id="conditionBar" style="
padding:8px 16px;
font-size:12px;
opacity:0.8;
border-bottom:1px solid #1e293b;">
기본조건: 경기전 · 일반/핸디1
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

async function load(){

    let r = await fetch('/matches');
    let data = await r.json();

    let html="";

    data.forEach(function(m){

        let row = m.row;
        let badge = m.secret ?
        "<div style='color:#22c55e;font-weight:bold;margin-bottom:6px;'>SECRET</div>" : "";

        html+=`
        <div class="card">
        ${badge}
        <div><b>${row[6]}</b> vs <b>${row[7]}</b></div>
        <div>승 ${row[8]} | 무 ${row[9]} | 패 ${row[10]}</div>
        <div>${row[14]} · ${row[16]} · ${row[11]} · ${row[15]} · ${row[12]}</div>
        <div class="info-btn">
            <a href="/detail?no=${row[0]}" style="color:#38bdf8;">정보</a>
        </div>
        <div class="star-btn" onclick="toggleFav('${row[6]}','${row[7]}',this)">★</div>
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
# 경기목록 API (기본조건 + SECRET)
# =====================================================

@app.get("/matches")
def matches():

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

    result = []

    for _, row in base_df.iterrows():

        data = row.values.tolist()
        sec = secret_score(row, df)

        is_secret = bool(
            sec["score"] > 0.05 and
            sec["sample"] >= 20 and
            sec["추천"] != "없음"
        )

        result.append({
            "row": list(map(str, data)),
            "secret": is_secret
        })

    return result

# =====================================================
# Page2 - 상세 분석 (COL_NO 단일 조회)
# =====================================================

@app.get("/detail", response_class=HTMLResponse)
def detail(no: str = None):

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

    # 5조건 완전일치
    base_cond = build_5cond(row)
    base_df = run_filter(df, base_cond)
    base_dist = distribution(base_df)

    # 동일리그 5조건
    league_cond = build_league_cond(row)
    league_df = run_filter(df, league_cond)
    league_dist = distribution(league_df)

    ev_data = safe_ev(base_dist, row)

    return f"""
    <html>
    <body style="background:#0f1720;color:white;font-family:Arial;padding:20px;">

    <h2>[{league}] {home} vs {away}</h2>

    승 {row.iloc[COL_WIN_ODDS]} /
    무 {row.iloc[COL_DRAW_ODDS]} /
    패 {row.iloc[COL_LOSE_ODDS]}

    <br><br>

    <h3>5조건 완전일치</h3>
    총 {base_dist["총"]}경기<br>
    승 {base_dist["wp"]}%<br>
    무 {base_dist["dp"]}%<br>
    패 {base_dist["lp"]}%<br>

    <br>

    <h3>동일리그 5조건</h3>
    총 {league_dist["총"]}경기<br>
    승 {league_dist["wp"]}%<br>
    무 {league_dist["dp"]}%<br>
    패 {league_dist["lp"]}%<br>

    <br>

    <h3>EV 분석</h3>
    추천: {ev_data["추천"]}<br>
    승 EV: {ev_data["EV"]["승"]}<br>
    무 EV: {ev_data["EV"]["무"]}<br>
    패 EV: {ev_data["EV"]["패"]}<br>

    <br>
    <a href="/page3?no={row.iloc[COL_NO]}">팀 분석</a><br>
    <a href="/page4?no={row.iloc[COL_NO]}">배당 분석</a>

    <br><br>
    <button onclick="history.back()">← 뒤로</button>

    </body>
    </html>
    """


# =====================================================
# Page3 - 팀 분석 (COL_NO 기반)
# =====================================================

@app.get("/page3", response_class=HTMLResponse)
def page3(no: str = None):

    if not no:
        return "<h2>잘못된 접근</h2>"

    df = CURRENT_DF
    if df.empty:
        return "<h2>데이터 없음</h2>"

    row_df = df[df.iloc[:, COL_NO] == str(no)]

    if row_df.empty:
        return "<h2>경기 없음</h2>"

    row = row_df.iloc[0]

    team   = row.iloc[COL_HOME]
    league = row.iloc[COL_LEAGUE]

    team_df = df[
        (df.iloc[:, COL_HOME] == team) |
        (df.iloc[:, COL_AWAY] == team)
    ]

    all_dist = distribution(team_df)

    league_df = team_df[
        team_df.iloc[:, COL_LEAGUE] == league
    ]
    league_dist = distribution(league_df)

    return f"""
    <html>
    <body style="background:#0f1720;color:white;padding:20px;">

    <h2>{team} 팀 분석</h2>

    <h3>전체</h3>
    총 {all_dist["총"]}경기<br>
    승 {all_dist["wp"]}%<br>
    무 {all_dist["dp"]}%<br>
    패 {all_dist["lp"]}%<br>

    <br>

    <h3>리그</h3>
    총 {league_dist["총"]}경기<br>
    승 {league_dist["wp"]}%<br>
    무 {league_dist["dp"]}%<br>
    패 {league_dist["lp"]}%<br>

    <br>
    <button onclick="history.back()">← 뒤로</button>

    </body>
    </html>
    """


# =====================================================
# Page4 - 배당 분석 (COL_NO 기반)
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4(no: str = None):

    if not no:
        return "<h2>잘못된 접근</h2>"

    df = CURRENT_DF
    if df.empty:
        return "<h2>데이터 없음</h2>"

    row_df = df[df.iloc[:, COL_NO] == str(no)]

    if row_df.empty:
        return "<h2>경기 없음</h2>"

    row = row_df.iloc[0]

    win_str  = row.iloc[COL_WIN_ODDS]
    draw_str = row.iloc[COL_DRAW_ODDS]
    lose_str = row.iloc[COL_LOSE_ODDS]

    exact_df = df[
        (df.iloc[:, COL_WIN_ODDS]  == win_str) &
        (df.iloc[:, COL_DRAW_ODDS] == draw_str) &
        (df.iloc[:, COL_LOSE_ODDS] == lose_str)
    ]

    exact_dist = distribution(exact_df)

    return f"""
    <html>
    <body style="background:#0f1720;color:white;padding:20px;">

    <h2>배당 분석</h2>
    승 {win_str} / 무 {draw_str} / 패 {lose_str}

    <br><br>

    <h3>완전일치</h3>
    총 {exact_dist["총"]}경기<br>
    승 {exact_dist["wp"]}%<br>
    무 {exact_dist["dp"]}%<br>
    패 {exact_dist["lp"]}%<br>

    <br>
    <button onclick="history.back()">← 뒤로</button>

    </body>
    </html>
    """

# =====================================================
# 즐겨찾기
# =====================================================

@app.post("/fav-toggle")
def fav_toggle(home:str = Form(...), away:str = Form(...)):
    global FAVORITES

    exist = next(
        (f for f in FAVORITES
         if f["home"] == home and f["away"] == away),
        None
    )

    if exist:
        FAVORITES = [
            f for f in FAVORITES
            if not (f["home"] == home and f["away"] == away)
        ]
        return {"status": "removed"}
    else:
        FAVORITES.append({
            "home": home,
            "away": away
        })
        return {"status": "added"}


@app.get("/favorites", response_class=HTMLResponse)
def favorites():

    html = ""

    for f in FAVORITES:
        html += f"""
        <div style='background:#1e293b;
                    margin:10px;
                    padding:15px;
                    border-radius:12px;'>
        {f["home"]} vs {f["away"]}
        </div>
        """

    return f"""
    <html>
    <body style='background:#0f1720;color:white;padding:20px;'>
    <h2>즐겨찾기 목록</h2>
    {html}
    <br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """


# =====================================================
# 가계부
# =====================================================

@app.get("/ledger", response_class=HTMLResponse)
def ledger():

    total = sum(item.get("profit", 0) for item in LEDGER)

    return f"""
    <html>
    <body style='background:#0f1720;color:white;padding:20px;'>
    <h2>가계부</h2>
    총합: {round(total, 2)}
    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """


# =====================================================
# 메모장
# =====================================================

@app.get("/memo", response_class=HTMLResponse)
def memo():
    return """
    <html>
    <body style='background:#0f1720;color:white;padding:20px;'>
    <h2>메모장</h2>
    <textarea style='width:100%;
                     height:300px;
                     background:#1e293b;
                     color:white;'>
    </textarea>
    <br><br>
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """


# =====================================================
# 캡처
# =====================================================

@app.get("/capture", response_class=HTMLResponse)
def capture():
    return """
    <html>
    <body style='background:#0f1720;color:white;padding:20px;'>
    <h2>캡처</h2>
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