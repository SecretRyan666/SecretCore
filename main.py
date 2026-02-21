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

EXPECTED_COLS = 17
DATA_FILE = "current_data.csv"

CURRENT_DF = pd.DataFrame()
LOGGED_IN = False
FAVORITES = []
LEDGER = []

DIST_CACHE = {}
SECRET_CACHE = {}

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

load_data()

# =====================================================
# 로그인 / 로그아웃
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
        return {"error": "컬럼 불일치"}

    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

    CURRENT_DF = df
    DIST_CACHE.clear()
    SECRET_CACHE.clear()

    return RedirectResponse("/", status_code=302)

# =====================================================
# 필터 유틸
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

# =====================================================
# filters API (경기전 기준 고정)
# =====================================================

@app.get("/filters")
def filters():

    df = CURRENT_DF
    if df.empty:
        return {}

    df = df[
        (df.iloc[:, COL_RESULT] == "경기전") &
        (
            (df.iloc[:, COL_TYPE] == "일반") |
            (df.iloc[:, COL_TYPE] == "핸디1")
        )
    ]

    return {
        "type": sorted(df.iloc[:, COL_TYPE].dropna().unique().tolist()),
        "homeaway": sorted(df.iloc[:, COL_HOMEAWAY].dropna().unique().tolist()),
        "general": sorted(df.iloc[:, COL_GENERAL].dropna().unique().tolist()),
        "dir": sorted(df.iloc[:, COL_DIR].dropna().unique().tolist()),
        "handi": sorted(df.iloc[:, COL_HANDI].dropna().unique().tolist())
    }


# =====================================================
# Page1
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
.star-btn{position:absolute;right:14px;bottom:12px;font-size:18px;color:#6b7280;}
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
</div>

<div id="list" style="padding-bottom:100px;"></div>

<div class="bottom-nav">
    <a href="/ledger">🏠</a>
    <a href="/memo">📝</a>
    <a href="/capture">📸</a>
    <a href="/favorites">⭐</a>
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

async function load(){

    let params = new URLSearchParams(window.location.search);
    let r = await fetch('/matches?' + params.toString());
    let data = await r.json();

    let html="";
    let headerText="";

    if(data.length>0){
        let first=data[0].row;
        headerText = first[1]+"년 "+first[2]+"회차";
    }else{
        headerText="경기 없음";
    }

    params.forEach((v,k)=>{
        headerText += " · "+k+"="+v;
    });

    document.getElementById("conditionBar").innerText=headerText;

    data.forEach(function(m){

        let row=m.row;

        let badge=m.secret?
        `<div style="
        position:absolute;
        top:50%;
        right:16px;
        transform:translateY(-50%);
        background:#16a34a;
        padding:6px 10px;
        border-radius:12px;
        font-size:12px;
        font-weight:bold;">
        시크릿픽 ${m.pick}
        </div>`:"";

        html+=`
        <div class="card">
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
# matches API
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

    result=[]

    for _, row in base_df.iterrows():

        sec = secret_score_fast(row, df)

        is_secret = bool(
            sec["score"]>0.05 and
            sec["sample"]>=20 and
            sec["추천"]!="없음"
        )

        result.append({
            "row": list(map(str,row.values.tolist())),
            "secret": is_secret,
            "pick": sec["추천"] if is_secret else ""
        })

    return result

# =====================================================
# 분포 / EV / SECRET 로직
# =====================================================

def build_5cond(row):
    return {
        COL_TYPE: row.iloc[COL_TYPE],
        COL_HOMEAWAY: row.iloc[COL_HOMEAWAY],
        COL_GENERAL: row.iloc[COL_GENERAL],
        COL_DIR: row.iloc[COL_DIR],
        COL_HANDI: row.iloc[COL_HANDI]
    }

def build_league_cond(row):
    cond = build_5cond(row)
    cond[COL_LEAGUE] = row.iloc[COL_LEAGUE]
    return cond

def run_filter(df, conditions: dict):
    filtered = df
    for col_idx, val in conditions.items():
        filtered = filtered[filtered.iloc[:, col_idx] == val]
    return filtered

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
    win = (result_col=="승").sum()
    draw = (result_col=="무").sum()
    lose = (result_col=="패").sum()

    wp = round(win/total*100,2)
    dp = round(draw/total*100,2)
    lp = round(lose/total*100,2)

    result={
        "총":int(total),
        "승":int(win),
        "무":int(draw),
        "패":int(lose),
        "wp":wp,"dp":dp,"lp":lp
    }

    DIST_CACHE[key]=result
    return result

def safe_ev(dist,row):
    try:
        w=float(row.iloc[COL_WIN_ODDS])
        d=float(row.iloc[COL_DRAW_ODDS])
        l=float(row.iloc[COL_LOSE_ODDS])
    except:
        return {"EV":{"승":0,"무":0,"패":0},"추천":"없음"}

    ev_w=dist["wp"]/100*w-1
    ev_d=dist["dp"]/100*d-1
    ev_l=dist["lp"]/100*l-1

    ev_map={"승":ev_w,"무":ev_d,"패":ev_l}
    best=max(ev_map,key=ev_map.get)

    return {
        "EV":{
            "승":round(ev_w,3),
            "무":round(ev_d,3),
            "패":round(ev_l,3)
        },
        "추천":best
    }

def secret_score_fast(row,df):
    cond=build_5cond(row)
    key=tuple(cond.values())

    if key in SECRET_CACHE:
        return SECRET_CACHE[key]

    sub_df=run_filter(df,cond)
    dist=distribution(sub_df)

    if dist["총"]<10:
        result={"score":0,"sample":dist["총"],"추천":"없음"}
        SECRET_CACHE[key]=result
        return result

    ev_data=safe_ev(dist,row)
    best_ev=max(ev_data["EV"].values())

    result={
        "score":round(best_ev,4),
        "sample":dist["총"],
        "추천":ev_data["추천"]
    }

    SECRET_CACHE[key]=result
    return result

def bar_html(percent,count,mode="win"):
    color={
        "win":"#22c55e",
        "draw":"#64748b",
        "lose":"#ef4444"
    }
    return f"""
    <div style="margin:6px 0;">
        <div style="font-size:12px;opacity:0.8;">
            {percent}% ({count}경기)
        </div>
        <div style="width:100%;background:#1f2937;
                    border-radius:999px;height:12px;">
            <div style="width:{percent}%;
                        background:{color[mode]};
                        height:100%;
                        border-radius:999px;"></div>
        </div>
    </div>
    """

# =====================================================
# Page2
# =====================================================

@app.get("/detail", response_class=HTMLResponse)
def detail(no:str=None,type:str=None,homeaway:str=None,
           general:str=None,dir:str=None,handi:str=None):

    df=CURRENT_DF
    if df.empty:
        return "<h2>데이터 없음</h2>"

    row=df[df.iloc[:,COL_NO]==str(no)].iloc[0]

    filtered=apply_filters(df,type,homeaway,general,dir,handi)

    base_df=run_filter(filtered,build_5cond(row))
    league_df=run_filter(filtered,build_league_cond(row))

    base_dist=distribution(base_df)
    league_dist=distribution(league_df)

    secret=safe_ev(base_dist,row)
    cond_str=filter_text(type,homeaway,general,dir,handi)

    return f"""
    <h2>{row.iloc[COL_HOME]} vs {row.iloc[COL_AWAY]}</h2>
    <div>적용조건: {cond_str}</div>
    <h3>5조건</h3>
    {bar_html(base_dist["wp"],base_dist["승"])}
    {bar_html(base_dist["dp"],base_dist["무"],"draw")}
    {bar_html(base_dist["lp"],base_dist["패"],"lose")}
    <h3>동일리그</h3>
    {bar_html(league_dist["wp"],league_dist["승"])}
    {bar_html(league_dist["dp"],league_dist["무"],"draw")}
    {bar_html(league_dist["lp"],league_dist["패"],"lose")}
    <h3>시크릿픽: {secret["추천"]}</h3>
    """

# =====================================================
# Page3
# =====================================================

@app.get("/page3", response_class=HTMLResponse)
def page3(no:str=None,away:str=None,
          type:str=None,homeaway:str=None,
          general:str=None,dir:str=None,handi:str=None):

    df=CURRENT_DF
    row=df[df.iloc[:,COL_NO]==str(no)].iloc[0]

    team=row.iloc[COL_AWAY] if away else row.iloc[COL_HOME]
    filtered=apply_filters(df,type,homeaway,general,dir,handi)

    team_df=filtered[
        (filtered.iloc[:,COL_HOME]==team)|
        (filtered.iloc[:,COL_AWAY]==team)
    ]

    dist=distribution(team_df)
    cond_str=filter_text(type,homeaway,general,dir,handi)

    return f"""
    <h2>{team} 분석</h2>
    <div>적용조건: {cond_str}</div>
    {bar_html(dist["wp"],dist["승"])}
    {bar_html(dist["dp"],dist["무"],"draw")}
    {bar_html(dist["lp"],dist["패"],"lose")}
    """

# =====================================================
# Page4
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4(no:str=None,
          type:str=None,homeaway:str=None,
          general:str=None,dir:str=None,handi:str=None):

    df=CURRENT_DF
    row=df[df.iloc[:,COL_NO]==str(no)].iloc[0]

    filtered=apply_filters(df,type,homeaway,general,dir,handi)

    win_str=row.iloc[COL_WIN_ODDS]

    win_df=filtered[filtered.iloc[:,COL_WIN_ODDS]==win_str]
    win_dist=distribution(win_df)

    cond_str=filter_text(type,homeaway,general,dir,handi)

    return f"""
    <h2>배당 분석</h2>
    <div>적용조건: {cond_str}</div>
    {bar_html(win_dist["wp"],win_dist["승"])}
    {bar_html(win_dist["dp"],win_dist["무"],"draw")}
    {bar_html(win_dist["lp"],win_dist["패"],"lose")}
    """

# =====================================================
# 기타 페이지
# =====================================================

@app.get("/ledger", response_class=HTMLResponse)
def ledger():
    return "<h2>가계부</h2>"

@app.get("/memo", response_class=HTMLResponse)
def memo():
    return "<h2>메모장</h2>"

@app.get("/capture", response_class=HTMLResponse)
def capture():
    return "<h2>캡처</h2>"

@app.get("/favorites", response_class=HTMLResponse)
def favorites():
    return "<h2>즐겨찾기</h2>"

@app.get("/health")
def health():
    return {"rows":len(CURRENT_DF)}

# =====================================================
# 실행부
# =====================================================

if __name__=="__main__":
    import uvicorn
    uvicorn.run("main:app",
                host="0.0.0.0",
                port=8000,
                reload=True)