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

# =====================================================
# 🔥 코드테스트 기반 전역 추가
# =====================================================

FAVORITES = []
LEDGER = []

# =====================================================
# 서버 재시작 자동 로드
# =====================================================

def load_data():
    global CURRENT_DF
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(
            DATA_FILE,
            encoding="utf-8-sig",
            low_memory=True
        )

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


# =====================================================
# 🔥 AI 등급 삭제 반영 (코드테스트 근거)
# =====================================================

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
# 업로드
# =====================================================

@app.post("/upload-data")
def upload(file: UploadFile = File(...)):
    global CURRENT_DF

    df = pd.read_csv(
        file.file,
        encoding="utf-8-sig",
        low_memory=True
    )

    if df.shape[1] < 17:
        return {"error":"컬럼 구조 오류"}

    df.iloc[:, COL_WIN_ODDS]  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_DRAW_ODDS] = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_LOSE_ODDS] = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0).round(2)

    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
    CURRENT_DF = df

    return RedirectResponse("/", status_code=302)

# =====================================================
# Page1 UI
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():

    if LOGGED_IN:
        login_area = """
        <form id="uploadForm" action="/upload-data" method="post" enctype="multipart/form-data" style="display:inline-flex;gap:6px;align-items:center;">
            <input type="file" name="file" required style="font-size:12px;">
            <button type="submit">📤</button>
        </form>
        <a href="/logout"><button>👤</button></a>
        """
    else:
        login_area = """
        <form action="/login" method="post" style="display:inline-flex;gap:6px;">
            <input name="username" placeholder="ID" style="width:70px;">
            <input name="password" type="password" placeholder="PW" style="width:70px;">
            <button type="submit">👤</button>
        </form>
        """

    return """
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="background:#0f1720;color:white;font-family:Arial;margin:0;">

<div style="display:flex;justify-content:space-between;align-items:center;padding:15px;background:#111827;">
    <div style="font-weight:700;">SecretCore PRO</div>
    <div>""" + login_area + """</div>
</div>

<div id="list" style="padding:15px;padding-bottom:90px;"></div>

<div style="position:fixed;bottom:0;width:100%;background:#111827;display:flex;justify-content:space-around;padding:12px 0;">
    <a href="/ledger" style="color:white;text-decoration:none;">🏠</a>
    <a href="/memo" style="color:white;text-decoration:none;">🌍</a>
    <a href="/capture" style="color:white;text-decoration:none;">📸</a>
    <a href="/favorites" style="color:white;text-decoration:none;">📰</a>
</div>

<script>
async function load(){
    let r = await fetch('/matches');
    let data = await r.json();
    let html="";

    data.forEach(function(m){
        html +=
        "<div style='background:#1e293b;margin-bottom:12px;padding:15px;border-radius:14px;'>"+
        "<div style='font-weight:600;color:#38bdf8;'>"+m[5]+"</div>"+
        "<div><b>"+m[6]+"</b> vs <b>"+m[7]+"</b></div>"+
        "<div>승 "+Number(m[8]).toFixed(2)+" | 무 "+Number(m[9]).toFixed(2)+" | 패 "+Number(m[10]).toFixed(2)+"</div>"+
        "</div>";
    });

    document.getElementById("list").innerHTML = html;
}
load();
</script>

</body>
</html>
"""

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
# 경기목록 API
# =====================================================

@app.get("/matches")
def matches(
    filter_type: str = None,
    filter_homeaway: str = None,
    filter_general: str = None,
    filter_dir: str = None,
    filter_handi: str = None
):

    df = CURRENT_DF

    if df.empty:
        return []

    # 기본조건: 경기전 + 일반/핸디1
    base_df = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        (
            (df.iloc[:, COL_TYPE] == "일반") |
            (df.iloc[:, COL_TYPE] == "핸디1")
        )
    ]

    conditions = {}

    if filter_type:
        conditions[COL_TYPE] = filter_type
    if filter_homeaway:
        conditions[COL_HOMEAWAY] = filter_homeaway
    if filter_general:
        conditions[COL_GENERAL] = filter_general
    if filter_dir:
        conditions[COL_DIR] = filter_dir
    if filter_handi:
        conditions[COL_HANDI] = filter_handi

    filtered = run_filter(base_df, conditions)

    return filtered.values.tolist()


# =====================================================
# PRO 막대그래프 (3색)
# =====================================================

def bar_html(percent, mode="win"):

    color_map = {
        "win":"linear-gradient(90deg,#22c55e,#16a34a)",
        "draw":"linear-gradient(90deg,#94a3b8,#64748b)",
        "lose":"linear-gradient(90deg,#ef4444,#dc2626)"
    }

    return f"""
    <div class="bar-wrap">
        <div class="bar-inner" style="width:{percent}%;background:{color_map[mode]};"></div>
    </div>
    """


# =====================================================
# Page2 - 상세 대시보드 (AI 등급 삭제 반영)
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

    cond_label = f"{row.iloc[COL_TYPE]} · {row.iloc[COL_HOMEAWAY]} · {row.iloc[COL_GENERAL]} · {row.iloc[COL_DIR]} · {row.iloc[COL_HANDI]}"

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
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>

body{{
background:linear-gradient(135deg,#0f1720,#1e293b);
color:white;
font-family:Arial;
padding:20px;
}}

.summary-card{{
background:linear-gradient(135deg,#1e293b,#0f1720);
padding:20px;
border-radius:22px;
box-shadow:0 10px 40px rgba(0,0,0,0.5);
margin-bottom:20px;
}}

.card{{
background:rgba(30,41,59,0.9);
padding:20px;
border-radius:20px;
margin-bottom:18px;
box-shadow:0 8px 30px rgba(0,0,0,0.4);
}}

.flex{{
display:flex;
gap:20px;
flex-wrap:wrap;
}}

.col{{
flex:1;
min-width:260px;
}}

.bar-wrap{{
width:100%;
background:rgba(255,255,255,0.08);
border-radius:999px;
overflow:hidden;
height:16px;
margin:8px 0 14px 0;
}}

.bar-inner{{
height:100%;
border-radius:999px;
transition:width 0.4s ease;
}}

button{{
margin-top:12px;
padding:6px 12px;
border-radius:8px;
}}

</style>
</head>
<body>

<div class="summary-card">
<h3>[{league}] {home} vs {away}</h3>
{cond_label}<br>
승 {win_odds:.2f} / 무 {draw_odds:.2f} / 패 {lose_odds:.2f}
<br><br>
<b>추천: {ev_data["추천"]}</b>
</div>

<div class="card">
<h4>5조건 완전일치</h4>
총 {base_dist["총"]}경기<br>
승 {base_dist["wp"]}%{bar_html(base_dist["wp"],"win")}
무 {base_dist["dp"]}%{bar_html(base_dist["dp"],"draw")}
패 {base_dist["lp"]}%{bar_html(base_dist["lp"],"lose")}
</div>

<div class="flex">
<div class="col">
<div class="card">
<h4>모든리그</h4>
총 {base_dist["총"]}경기<br>
승 {base_dist["wp"]}%{bar_html(base_dist["wp"],"win")}
무 {base_dist["dp"]}%{bar_html(base_dist["dp"],"draw")}
패 {base_dist["lp"]}%{bar_html(base_dist["lp"],"lose")}
</div>
</div>

<div class="col">
<div class="card">
<h4>{league}</h4>
총 {league_dist["총"]}경기<br>
승 {league_dist["wp"]}%{bar_html(league_dist["wp"],"win")}
무 {league_dist["dp"]}%{bar_html(league_dist["dp"],"draw")}
패 {league_dist["lp"]}%{bar_html(league_dist["lp"],"lose")}
</div>
</div>
</div>

<a href="/page3?team={home}&league={league}"><button>홈팀 분석</button></a>
<a href="/page3?team={away}&league={league}"><button>원정팀 분석</button></a>
<a href="/page4?win={win_odds}&draw={draw_odds}&lose={lose_odds}"><button>배당 분석</button></a>

<br><br>
<a href="/"><button>← 경기목록</button></a>

</body>
</html>
"""

# =====================================================
# Page3 - 팀 분석 (AI등급 없음)
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

    home_df = team_df[team_df.iloc[:, COL_HOME]==team]
    away_df = team_df[team_df.iloc[:, COL_AWAY]==team]

    home_dist = distribution(home_df)
    away_dist = distribution(away_df)

    def block(title, dist):
        return f"""
        <div class="card">
        <h4>{title}</h4>
        총 {dist["총"]}경기<br>
        승 {dist["wp"]}%{bar_html(dist["wp"],"win")}
        무 {dist["dp"]}%{bar_html(dist["dp"],"draw")}
        패 {dist["lp"]}%{bar_html(dist["lp"],"lose")}
        </div>
        """

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>

body{{
background:linear-gradient(135deg,#0f1720,#1e293b);
color:white;
font-family:Arial;
padding:20px;
}}

.card{{
background:rgba(30,41,59,0.9);
padding:20px;
border-radius:20px;
margin-bottom:18px;
}}

.flex{{
display:flex;
gap:20px;
flex-wrap:wrap;
}}

.col{{
flex:1;
min-width:260px;
}}

.bar-wrap{{
width:100%;
background:rgba(255,255,255,0.08);
border-radius:999px;
overflow:hidden;
height:16px;
margin:8px 0 14px 0;
}}

.bar-inner{{
height:100%;
border-radius:999px;
}}

button{{margin-top:12px;padding:6px 12px;border-radius:8px}}

</style>
</head>
<body>

<h3>{team} 팀 분석</h3>

<div class="flex">
<div class="col">
{block(team+" | 모든리그", all_dist)}
</div>
<div class="col">
{block(team+" | "+(league if league else "리그없음"), league_dist)}
</div>
</div>

<div class="flex">
<div class="col">
{block(team+" | 홈경기", home_dist)}
</div>
<div class="col">
{block(team+" | 원정경기", away_dist)}
</div>
</div>

<button onclick="history.back()">← 뒤로</button>

</body>
</html>
"""


# =====================================================
# Page4 - 배당 분석
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4(win:float, draw:float, lose:float):

    df = CURRENT_DF

    if df.empty:
        return "<h2>데이터 없음</h2>"

    win  = round(float(win),2)
    draw = round(float(draw),2)
    lose = round(float(lose),2)

    win_series  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS],  errors="coerce").fillna(0).round(2)
    draw_series = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0).round(2)
    lose_series = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0).round(2)

    exact_df = df[
        (win_series==win) &
        (draw_series==draw) &
        (lose_series==lose)
    ]
    exact_dist = distribution(exact_df)

    return f"""
<html>
<body style="background:#0f1720;color:white;padding:20px;font-family:Arial;">

<h3>배당 분석</h3>
승 {win:.2f} / 무 {draw:.2f} / 패 {lose:.2f}

<div>
총 {exact_dist["총"]}경기<br>
승 {exact_dist["wp"]}%<br>
무 {exact_dist["dp"]}%<br>
패 {exact_dist["lp"]}%
</div>

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
    <html>
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
    <html>
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
    <html>
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
    <html>
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
# 로컬 실행용
# =====================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)