from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import pandas as pd
from io import BytesIO

app = FastAPI()

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
# 안정화
# =====================================================

def check_df():
    if CURRENT_DF.empty:
        return False
    if CURRENT_DF.shape[1] < 17:
        return False
    return True

# =====================================================
# PRO 루프엔진
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
# 고유값 루프엔진
# =====================================================

def loop_distribution(df, col_idx):
    result = {}
    unique_vals = df.iloc[:, col_idx].dropna().unique()

    for val in unique_vals:
        subset = df[df.iloc[:, col_idx] == val]
        result[str(val)] = distribution(subset)

    return result


# =====================================================
# 매칭구조
# =====================================================

def general_matching(df, base_df, general_val):
    # 일반전체
    general_all = run_filter(df, {COL_GENERAL: general_val})
    # 일반매칭 (기본조건 안에서 동일 일반값)
    general_match = run_filter(base_df, {COL_GENERAL: general_val})
    return distribution(general_all), distribution(general_match)


def league_matching(df, base_df, league_val):
    # 리그전체
    league_all = run_filter(df, {COL_LEAGUE: league_val})
    # 리그매칭
    league_match = run_filter(base_df, {COL_LEAGUE: league_val})
    return distribution(league_all), distribution(league_match)


# =====================================================
# AI 강화
# =====================================================

def enhanced_ai(base_dist, general_match_dist, league_match_dist, row):

    win_odds  = float(row.iloc[COL_WIN_ODDS])
    draw_odds = float(row.iloc[COL_DRAW_ODDS])
    lose_odds = float(row.iloc[COL_LOSE_ODDS])

    ev_w = base_dist["wp"]/100*win_odds - 1
    ev_d = base_dist["dp"]/100*draw_odds - 1
    ev_l = base_dist["lp"]/100*lose_odds - 1

    best = max({"승":ev_w,"무":ev_d,"패":ev_l},
               key=lambda x: {"승":ev_w,"무":ev_d,"패":ev_l}[x])

    base_score = max(base_dist["wp"],base_dist["dp"],base_dist["lp"])
    general_score = max(general_match_dist["wp"],general_match_dist["dp"],general_match_dist["lp"])
    league_score = max(league_match_dist["wp"],league_match_dist["dp"],league_match_dist["lp"])

    avg_score = (base_score + general_score + league_score) / 3

    if avg_score >= 65:
        grade = "S"
    elif avg_score >= 55:
        grade = "A"
    elif avg_score >= 45:
        grade = "B"
    else:
        grade = "C"

    return {
        "EV":{"승":round(ev_w,3),"무":round(ev_d,3),"패":round(ev_l,3)},
        "추천":best,
        "AI":grade
    }


# =====================================================
# 20칸 고정막대
# =====================================================

def text_bar(p):
    blocks = int(round(p / 5))
    return "█"*blocks + "░"*(20-blocks)

# =====================================================
# 업로드
# =====================================================

@app.post("/upload-data")
def upload(file: UploadFile = File(...)):
    global CURRENT_DF

    raw = file.file.read()
    df = pd.read_csv(BytesIO(raw), encoding="utf-8-sig", low_memory=False)

    if df.shape[1] < 17:
        return {"error":"컬럼 구조 오류"}

    df.iloc[:, COL_WIN_ODDS]  = pd.to_numeric(df.iloc[:, COL_WIN_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_DRAW_ODDS] = pd.to_numeric(df.iloc[:, COL_DRAW_ODDS], errors="coerce").fillna(0).round(2)
    df.iloc[:, COL_LOSE_ODDS] = pd.to_numeric(df.iloc[:, COL_LOSE_ODDS], errors="coerce").fillna(0).round(2)

    CURRENT_DF = df
    return {"rows":len(df)}


# =====================================================
# Page1 - 고유값 루프 필터 API
# =====================================================

@app.get("/filters")
def get_filters():

    if not check_df():
        return {}

    df = CURRENT_DF

    return {
        "유형": df.iloc[:, COL_TYPE].dropna().unique().tolist(),
        "홈원정": df.iloc[:, COL_HOMEAWAY].dropna().unique().tolist(),
        "일반": df.iloc[:, COL_GENERAL].dropna().unique().tolist(),
        "정역": df.iloc[:, COL_DIR].dropna().unique().tolist(),
        "핸디": df.iloc[:, COL_HANDI].dropna().unique().tolist()
    }


# =====================================================
# Page1 - 경기목록
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

    # 1차 공통필터
    m = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        ((df.iloc[:, COL_TYPE] == "일반") |
         (df.iloc[:, COL_TYPE] == "핸디1"))
    ]

    # 선택 필터 누적 적용
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
# Page1 - UI (자동 루프 필터)
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{background:#0f1720;color:white;font-family:Arial;padding:25px}
.card{background:rgba(30,41,59,0.9);padding:18px;border-radius:18px;margin-bottom:18px}
h2{margin-bottom:15px}
.filter-group{margin-bottom:10px}
.filter-btn{
    background:#1e293b;
    color:white;
    border:1px solid #334155;
    padding:4px 8px;
    border-radius:8px;
    font-size:12px;
    margin:2px;
    cursor:pointer;
}
.filter-btn.active{
    background:#22d3ee;
    color:black;
}
.reset-btn{
    background:#ef4444;
    color:white;
    border:none;
    padding:6px 10px;
    border-radius:10px;
    font-size:12px;
    cursor:pointer;
}
.team{cursor:pointer;font-weight:bold}
.win{color:#22c55e;cursor:pointer}
.draw{color:#cbd5e1;cursor:pointer}
.lose{color:#ef4444;cursor:pointer}
.info-btn{
    float:right;
    background:#22d3ee;
    color:black;
    border:none;
    padding:4px 8px;
    border-radius:8px;
    font-size:12px;
    cursor:pointer;
}
</style>
</head>
<body>

<h2>SecretCore PRO</h2>

<div id="filters"></div>
<button class="reset-btn" onclick="resetFilters()">경기목록</button>

<hr style="border-color:#334155;margin:15px 0">

<div id="list"></div>

<script>

let filters = {};

window.onload = async function(){
    await loadFilters();
    await loadMatches();
};

async function loadFilters(){
    let r = await fetch('/filters');
    let data = await r.json();

    let html = "";

    for(let group in data){
        html += `<div class="filter-group"><b>${group}</b><br>`;
        data[group].forEach(val=>{
            html += `<button class="filter-btn"
                      onclick="toggleFilter('${group}','${val}',this)">
                      ${val}</button>`;
        });
        html += `</div>`;
    }

    document.getElementById("filters").innerHTML = html;
}

function toggleFilter(group,val,btn){
    let keyMap = {
        "유형":"filter_type",
        "홈원정":"filter_homeaway",
        "일반":"filter_general",
        "정역":"filter_dir",
        "핸디":"filter_handi"
    };

    let key = keyMap[group];

    if(filters[key] === val){
        delete filters[key];
        btn.classList.remove("active");
    }else{
        filters[key] = val;
        btn.classList.add("active");
    }

    loadMatches();
}

function resetFilters(){
    filters = {};
    document.querySelectorAll(".filter-btn").forEach(b=>b.classList.remove("active"));
    loadMatches();
}

async function loadMatches(){
    let query = new URLSearchParams(filters).toString();
    let r = await fetch('/matches?'+query);
    let data = await r.json();

    let html = "";

    data.forEach(m=>{
        html += `
        <div class="card">
            <b>${m[5]}</b><br>
            <span class="team"
              onclick="location.href='/page3?team=${m[6]}'">${m[6]}</span>
            vs
            <span class="team"
              onclick="location.href='/page3?team=${m[7]}'">${m[7]}</span>

            <button class="info-btn"
              onclick="location.href='/detail?year=${m[1]}&match=${m[3]}'">
              정보
            </button>

            <br><br>
            ${m[14]} · ${m[16]} · ${m[11]} · ${m[15]} · ${m[12]}<br>
            승 <span class="win"
              onclick="location.href='/page4?win=${m[8]}&draw=${m[9]}&lose=${m[10]}'">
              ${Number(m[8]).toFixed(2)}</span> |
            무 <span class="draw"
              onclick="location.href='/page4?win=${m[8]}&draw=${m[9]}&lose=${m[10]}'">
              ${Number(m[9]).toFixed(2)}</span> |
            패 <span class="lose"
              onclick="location.href='/page4?win=${m[8]}&draw=${m[9]}&lose=${m[10]}'">
              ${Number(m[10]).toFixed(2)}</span>
        </div>`;
    });

    document.getElementById("list").innerHTML = html;
}

</script>

</body>
</html>
"""

# =====================================================
# Page2 - 통합스캔 (PRO 완전체)
# =====================================================

@app.get("/detail", response_class=HTMLResponse)
def detail(year:int, match:int):

    if not check_df():
        return "<h2>데이터 없음</h2>"

    df = CURRENT_DF

    rows = df[
        (df.iloc[:,COL_YEAR]==year) &
        (df.iloc[:,COL_MATCH]==match)
    ]

    if rows.empty:
        return "<h2>경기 없음</h2>"

    row = rows.iloc[0]

    # -------------------------------------------------
    # 기본조건
    # -------------------------------------------------

    base_cond = {
        COL_TYPE:row.iloc[COL_TYPE],
        COL_HOMEAWAY:row.iloc[COL_HOMEAWAY],
        COL_GENERAL:row.iloc[COL_GENERAL],
        COL_DIR:row.iloc[COL_DIR],
        COL_HANDI:row.iloc[COL_HANDI]
    }

    base_df = run_filter(df, base_cond)
    base_dist = distribution(base_df)

    cond_label = f'{row.iloc[COL_TYPE]} · {row.iloc[COL_HOMEAWAY]} · {row.iloc[COL_GENERAL]} · {row.iloc[COL_DIR]} · {row.iloc[COL_HANDI]}'

    # -------------------------------------------------
    # 일반 루프
    # -------------------------------------------------

    general_loop = loop_distribution(df, COL_GENERAL)

    general_all_dist, general_match_dist = general_matching(
        df,
        base_df,
        row.iloc[COL_GENERAL]
    )

    # -------------------------------------------------
    # 리그 루프
    # -------------------------------------------------

    league_loop = loop_distribution(df, COL_LEAGUE)

    league_all_dist, league_match_dist = league_matching(
        df,
        base_df,
        row.iloc[COL_LEAGUE]
    )

    # -------------------------------------------------
    # AI 강화
    # -------------------------------------------------

    ai_data = enhanced_ai(base_dist, general_match_dist, league_match_dist, row)

    # -------------------------------------------------
    # 화면 출력
    # -------------------------------------------------

    def block(title, dist):
        return f"""
        <h3>[{title}] 총 {dist["총"]}경기</h3>
        <pre>
승 {text_bar(dist["wp"])} {dist["wp"]}% ({dist["승"]})
무 {text_bar(dist["dp"])} {dist["dp"]}% ({dist["무"]})
패 {text_bar(dist["lp"])} {dist["lp"]}% ({dist["패"]})
        </pre>
        """

    def loop_block(title, loop_data):
        html = f"<h3>{title}</h3>"
        for key, dist in loop_data.items():
            html += f"""
            <b>{key}</b> ({dist["총"]})
            <pre>
승 {text_bar(dist["wp"])} {dist["wp"]}%
무 {text_bar(dist["dp"])} {dist["dp"]}%
패 {text_bar(dist["lp"])} {dist["lp"]}%
            </pre>
            """
        return html

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:25px}}
.card{{background:rgba(30,41,59,0.9);padding:20px;border-radius:20px;margin-bottom:20px}}
pre{{background:#0b1220;padding:12px;border-radius:14px;
white-space:pre-wrap;font-family:monospace;overflow:hidden}}
.flex{{display:flex;gap:8px;margin-top:15px}}
.flex button{{flex:1;background:#22d3ee;color:black;
border:none;padding:6px 8px;border-radius:10px;font-size:12px}}
</style>
</head>
<body>

<button onclick="history.back()">← 뒤로</button>

<div class="card">
<h2>[{cond_label}]</h2>

{block("기본조건", base_dist)}

{block("일반전체", general_all_dist)}
{block("일반매칭", general_match_dist)}

{block("리그전체", league_all_dist)}
{block("리그매칭", league_match_dist)}

<h3>EV & AI</h3>
<b>추천:</b> {ai_data["추천"]}<br>
<b>AI등급:</b> {ai_data["AI"]}

</div>

<div class="card">
{loop_block("일반 고유값 루프", general_loop)}
</div>

<div class="card">
{loop_block("리그 고유값 루프", league_loop)}
</div>

<div class="flex">
<button onclick="location.href='/page3?team={row.iloc[COL_HOME]}'">홈팀분석</button>
<button onclick="location.href='/page3?team={row.iloc[COL_AWAY]}'">원정팀분석</button>
<button onclick="location.href='/page4?win={row.iloc[COL_WIN_ODDS]:.2f}&draw={row.iloc[COL_DRAW_ODDS]:.2f}&lose={row.iloc[COL_LOSE_ODDS]:.2f}'">배당분석</button>
</div>

</body>
</html>
"""

# =====================================================
# Page3 - 팀스캔 (PRO 확장)
# =====================================================

@app.get("/page3", response_class=HTMLResponse)
def page3(team:str):

    if not check_df():
        return "<h2>데이터 없음</h2>"

    df = CURRENT_DF

    team_df = df[
        (df.iloc[:,COL_HOME]==team) |
        (df.iloc[:,COL_AWAY]==team)
    ]

    overall = distribution(team_df)

    home_df = team_df[team_df.iloc[:,COL_HOME]==team]
    away_df = team_df[team_df.iloc[:,COL_AWAY]==team]

    home_dist = distribution(home_df)
    away_dist = distribution(away_df)

    # 일반 등급 루프
    general_loop = loop_distribution(team_df, COL_GENERAL)

    # 핸디 등급 루프
    handi_loop = loop_distribution(team_df, COL_HANDI)

    def block(title, dist):
        return f"""
        <h3>[{title}] 총 {dist["총"]}경기</h3>
        <pre>
승 {text_bar(dist["wp"])} {dist["wp"]}% ({dist["승"]})
무 {text_bar(dist["dp"])} {dist["dp"]}% ({dist["무"]})
패 {text_bar(dist["lp"])} {dist["lp"]}% ({dist["패"]})
        </pre>
        """

    def loop_block(title, loop_data):
        html = f"<h3>{title}</h3>"
        for key, dist in loop_data.items():
            html += f"""
            <b>{key}</b> ({dist["총"]})
            <pre>
승 {text_bar(dist["wp"])} {dist["wp"]}%
무 {text_bar(dist["dp"])} {dist["dp"]}%
패 {text_bar(dist["lp"])} {dist["lp"]}%
            </pre>
            """
        return html

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:25px}}
.card{{background:rgba(30,41,59,0.9);padding:20px;border-radius:20px;margin-bottom:20px}}
pre{{background:#0b1220;padding:12px;border-radius:14px;
white-space:pre-wrap;font-family:monospace;overflow:hidden}}
</style>
</head>
<body>

<button onclick="history.back()">← 뒤로</button>

<div class="card">
<h2>{team} 팀 분석</h2>

{block("전체", overall)}
{block("홈", home_dist)}
{block("원정", away_dist)}

</div>

<div class="card">
{loop_block("일반 등급 루프", general_loop)}
</div>

<div class="card">
{loop_block("핸디 등급 루프", handi_loop)}
</div>

</body>
</html>
"""

# =====================================================
# Page4 - 배당스캔 (PRO 확장)
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4(win:float, draw:float, lose:float):

    if not check_df():
        return "<h2>데이터 없음</h2>"

    df = CURRENT_DF

    # 동일 배당 필터 (float 오차 보정)
    odds_df = df[
        (df.iloc[:,COL_WIN_ODDS].round(2)==round(win,2)) &
        (df.iloc[:,COL_DRAW_ODDS].round(2)==round(draw,2)) &
        (df.iloc[:,COL_LOSE_ODDS].round(2)==round(lose,2))
    ]

    same_dist = distribution(odds_df)

    # 전체 대비 비교
    total_dist = distribution(df)

    # 배당 루프 (승배당 기준 고유값)
    odds_loop = loop_distribution(df, COL_WIN_ODDS)

    def block(title, dist):
        return f"""
        <h3>[{title}] 총 {dist["총"]}경기</h3>
        <pre>
승 {text_bar(dist["wp"])} {dist["wp"]}% ({dist["승"]})
무 {text_bar(dist["dp"])} {dist["dp"]}% ({dist["무"]})
패 {text_bar(dist["lp"])} {dist["lp"]}% ({dist["패"]})
        </pre>
        """

    def loop_block(title, loop_data):
        html = f"<h3>{title}</h3>"
        for key, dist in loop_data.items():
            html += f"""
            <b>{key}</b> ({dist["총"]})
            <pre>
승 {text_bar(dist["wp"])} {dist["wp"]}%
무 {text_bar(dist["dp"])} {dist["dp"]}%
패 {text_bar(dist["lp"])} {dist["lp"]}%
            </pre>
            """
        return html

    return f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{background:#0f1720;color:white;font-family:Arial;padding:25px}}
.card{{background:rgba(30,41,59,0.9);padding:20px;border-radius:20px;margin-bottom:20px}}
pre{{background:#0b1220;padding:12px;border-radius:14px;
white-space:pre-wrap;font-family:monospace;overflow:hidden}}
</style>
</head>
<body>

<button onclick="history.back()">← 뒤로</button>

<div class="card">
<h2>[배당 {win:.2f} / {draw:.2f} / {lose:.2f}]</h2>

{block("동일배당", same_dist)}
{block("전체대비", total_dist)}

</div>

<div class="card">
{loop_block("승배당 고유값 루프", odds_loop)}
</div>

</body>
</html>
"""