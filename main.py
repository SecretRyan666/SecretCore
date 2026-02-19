from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import pandas as pd
import os

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

FAVORITES = []
LEDGER = []

# =====================================================
# 서버 재시작 자동 로드
# =====================================================

def load_data():
    global CURRENT_DF
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE, encoding="utf-8-sig", low_memory=True)

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

    return {
        "EV":{
            "승":round(ev_w,3),
            "무":round(ev_d,3),
            "패":round(ev_l,3)
        },
        "추천":best
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
# 업로드 전용 페이지
# =====================================================

@app.get("/page-upload", response_class=HTMLResponse)
def page_upload():

    if not LOGGED_IN:
        return RedirectResponse("/", status_code=302)

    return """
    <html lang="ko">
    <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Language" content="ko">
    <meta name="google" content="notranslate">
    </head>
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
# Page1 - DarkPro 통합 UI (강화버전)
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():

    if not LOGGED_IN:
        return """
        <html lang="ko">
        <head>
        <meta charset="utf-8">
        <meta http-equiv="Content-Language" content="ko">
        <meta name="google" content="notranslate">
        </head>
        <body style="background:#0f1720;color:white;font-family:Arial;
                     display:flex;justify-content:center;
                     align-items:center;height:100vh;">
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
<meta http-equiv="Content-Language" content="ko">
<meta name="google" content="notranslate">
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
backdrop-filter:blur(12px);
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

.secret{
position:absolute;
top:50%;
left:63%;
transform:translate(-50%,-50%);
background:#22c55e;
color:#0f1720;
font-size:11px;
padding:4px 10px;
border-radius:999px;
font-weight:700;
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
        <div onclick="openFilter()">⚙️</div>
        <div onclick="resetFilter()">🔄</div>
        <div onclick="location.href='/page-upload'">📤</div>
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

let filters = JSON.parse(localStorage.getItem("filters")||"{}");

function resetFilter(){
    filters = {};
    localStorage.setItem("filters","{}");
    load();
}

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

    let query = new URLSearchParams(filters).toString();
    let r = await fetch('/matches?'+query);
    let data = await r.json();

    let html="";

    data.forEach(function(m){

        let secret = Math.random() > 0.8 ? "<div class='secret'>SECRET</div>" : "";

        html += `
        <div class="card">
            ${secret}
            <div class="league">${m[5]}</div>
            <div class="match"><b>${m[6]}</b> vs <b>${m[7]}</b></div>
            <div>승 ${Number(m[8]).toFixed(2)} | 무 ${Number(m[9]).toFixed(2)} | 패 ${Number(m[10]).toFixed(2)}</div>
            <div class="info-btn" onclick="goDetail(${m[1]},${m[3]})">정보</div>
            <div class="star-btn" onclick="toggleFav('${m[6]}','${m[7]}',this)">★</div>
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
# 업로드 처리
# =====================================================

@app.post("/upload-data")
def upload(file: UploadFile = File(...)):
    global CURRENT_DF

    df = pd.read_csv(file.file, encoding="utf-8-sig", low_memory=True)

    if df.shape[1] < 17:
        return {"error":"컬럼 구조 오류"}

    df.iloc[:, COL_WIN_ODDS]  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_DRAW_ODDS] = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_LOSE_ODDS] = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0).round(2)

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
# 경기목록 API (기본: 경기전 + 일반/핸디1)
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

    # 기본조건 고정
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
# 즐겨찾기
# =====================================================

@app.post("/fav-toggle")
def fav_toggle(home:str = Form(...), away:str = Form(...)):
    global FAVORITES

    exist = next((f for f in FAVORITES if f["home"]==home and f["away"]==away), None)

    if exist:
        FAVORITES = [f for f in FAVORITES if not (f["home"]==home and f["away"]==away)]
        return {"status":"removed"}
    else:
        FAVORITES.append({"home":home,"away":away})
        return {"status":"added"}


@app.get("/favorites", response_class=HTMLResponse)
def favorites():

    html = ""

    for f in FAVORITES:
        html += f"""
        <div style='background:#1e293b;margin:10px;padding:15px;border-radius:12px;'>
        {f["home"]} vs {f["away"]}
        </div>
        """

    return f"""
    <html lang="ko">
    <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Language" content="ko">
    <meta name="google" content="notranslate">
    </head>
    <body style='background:#0f1720;color:white;padding:20px;'>
    <h2>즐겨찾기 목록</h2>
    {html}
    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

# =====================================================
# 가계부
# =====================================================

@app.get("/ledger", response_class=HTMLResponse)
def ledger():

    total = sum(item.get("profit",0) for item in LEDGER)

    return f"""
    <html lang="ko">
    <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Language" content="ko">
    <meta name="google" content="notranslate">
    </head>
    <body style='background:#0f1720;color:white;padding:20px;'>
    <h2>가계부</h2>
    총합: {round(total,2)}
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
    <html lang="ko">
    <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Language" content="ko">
    <meta name="google" content="notranslate">
    </head>
    <body style='background:#0f1720;color:white;padding:20px;'>
    <h2>메모장</h2>
    <textarea style='width:100%;height:300px;background:#1e293b;color:white;'></textarea>
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
    <html lang="ko">
    <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Language" content="ko">
    <meta name="google" content="notranslate">
    </head>
    <body style='background:#0f1720;color:white;padding:20px;'>
    <h2>캡처</h2>
    <button onclick="history.back()">← 뒤로</button>
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
        <div style="width:{percent}%;background:{color_map[mode]};
                    height:100%;border-radius:999px;"></div>
    </div>
    """

# =====================================================
# Page2 - 상세
# =====================================================

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
    <html lang="ko">
    <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Language" content="ko">
    <meta name="google" content="notranslate">
    </head>
    <body style="background:#0f1720;color:white;font-family:Arial;padding:20px;">

    <h2>[{league}] {home} vs {away}</h2>
    승 {win_odds:.2f} / 무 {draw_odds:.2f} / 패 {lose_odds:.2f}
    <br><br>
    <b>추천: {ev_data["추천"]}</b>

    <h3>5조건 완전일치</h3>
    승 {base_dist["wp"]}% {bar_html(base_dist["wp"],"win")}
    무 {base_dist["dp"]}% {bar_html(base_dist["dp"],"draw")}
    패 {base_dist["lp"]}% {bar_html(base_dist["lp"],"lose")}

    <h3>리그 통계</h3>
    승 {league_dist["wp"]}% {bar_html(league_dist["wp"],"win")}
    무 {league_dist["dp"]}% {bar_html(league_dist["dp"],"draw")}
    패 {league_dist["lp"]}% {bar_html(league_dist["lp"],"lose")}

    <br>
    <a href="/page3?team={home}&league={league}">홈팀 분석</a><br>
    <a href="/page3?team={away}&league={league}">원정팀 분석</a><br>
    <a href="/page4?win={win_odds}&draw={draw_odds}&lose={lose_odds}">배당 분석</a><br><br>

    <button onclick="history.back()">← 뒤로</button>

    </body>
    </html>
    """

# =====================================================
# Page3
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

    all_dist = distribution(team_df)

    if league:
        league_df = team_df[team_df.iloc[:, COL_LEAGUE]==league]
    else:
        league_df = pd.DataFrame()

    league_dist = distribution(league_df)

    return f"""
    <html lang="ko">
    <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Language" content="ko">
    <meta name="google" content="notranslate">
    </head>
    <body style="background:#0f1720;color:white;padding:20px;">

    <h2>{team} 팀 분석</h2>

    <h3>전체</h3>
    승 {all_dist["wp"]}% {bar_html(all_dist["wp"],"win")}
    무 {all_dist["dp"]}% {bar_html(all_dist["dp"],"draw")}
    패 {all_dist["lp"]}% {bar_html(all_dist["lp"],"lose")}

    <h3>리그</h3>
    승 {league_dist["wp"]}% {bar_html(league_dist["wp"],"win")}
    무 {league_dist["dp"]}% {bar_html(league_dist["dp"],"draw")}
    패 {league_dist["lp"]}% {bar_html(league_dist["lp"],"lose")}

    <button onclick="history.back()">← 뒤로</button>

    </body>
    </html>
    """

# =====================================================
# Page4 - 배당 분석 (완전일치 + 단일조건 확장)
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4(win:float, draw:float, lose:float):

    df = CURRENT_DF
    if df.empty:
        return "<h2>데이터 없음</h2>"

    win  = round(float(win),2)
    draw = round(float(draw),2)
    lose = round(float(lose),2)

    win_series  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS], errors="coerce").fillna(0).round(2)
    draw_series = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0).round(2)
    lose_series = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0).round(2)

    # 완전일치
    exact_df = df[
        (win_series==win) &
        (draw_series==draw) &
        (lose_series==lose)
    ]
    exact_dist = distribution(exact_df)

    # 승 동일
    win_df = df[win_series==win]
    win_dist = distribution(win_df)

    # 무 동일
    draw_df = df[draw_series==draw]
    draw_dist = distribution(draw_df)

    # 패 동일
    lose_df = df[lose_series==lose]
    lose_dist = distribution(lose_df)

    def block(title, dist):
        return f"""
        <div style="margin-bottom:22px;padding:16px;
                    background:#1e293b;border-radius:14px;">
            <h3>{title}</h3>
            총 {dist["총"]}경기<br>
            승 {dist["wp"]}% {bar_html(dist["wp"],"win")}
            무 {dist["dp"]}% {bar_html(dist["dp"],"draw")}
            패 {dist["lp"]}% {bar_html(dist["lp"],"lose")}
        </div>
        """

    return f"""
    <html lang="ko">
    <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Language" content="ko">
    <meta name="google" content="notranslate">
    </head>
    <body style="background:#0f1720;color:white;padding:20px;">

    <h2>배당 분석</h2>
    승 {win:.2f} / 무 {draw:.2f} / 패 {lose:.2f}

    {block("완전일치 통계", exact_dist)}
    {block("승배당 동일 통계", win_dist)}
    {block("무배당 동일 통계", draw_dist)}
    {block("패배당 동일 통계", lose_dist)}

    <button onclick="history.back()">← 뒤로</button>

    </body>
    </html>
    """

# =====================================================
# 로컬 실행
# =====================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)