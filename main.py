from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import pandas as pd
from io import BytesIO
import os
import math

# =====================================================
# APP
# =====================================================

app = FastAPI()

DATA_FILE = "data_store.csv"
CURRENT_DF = pd.DataFrame()

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_csv(DATA_FILE)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# =====================================================
# 고정 열 인덱스 (A~Q 절대참조)
# =====================================================

COL_NO = 0
COL_YEAR = 1
COL_ROUND = 2
COL_MATCH = 3
COL_SPORT = 4
COL_LEAGUE = 5
COL_HOME = 6
COL_AWAY = 7
COL_ODD_WIN = 8
COL_ODD_DRAW = 9
COL_ODD_LOSE = 10
COL_GENERAL = 11
COL_HANDI = 12
COL_RESULT = 13
COL_TYPE = 14
COL_REV = 15
COL_HOMEAWAY = 16

# =====================================================
# UTIL
# =====================================================

def safe_float(v):
    try:
        f = float(v)
        if math.isnan(f):
            return 0.0
        return f
    except:
        return 0.0

def bar(p):
    filled = int(p / 5)
    return "█"*filled + "-"*(20-filled)

def distribution(df):
    total = len(df)
    if total == 0:
        return {"총":0,"승":"-","무":"-","패":"-","wp":0,"dp":0,"lp":0}

    results = df.iloc[:, COL_RESULT]

    win = (results == "승").sum()
    draw = (results == "무").sum()
    lose = (results == "패").sum()

    wp = win/total*100
    dp = draw/total*100
    lp = lose/total*100

    return {
        "총": int(total),
        "승": f"{bar(wp)} {round(wp,2)}% ({win})",
        "무": f"{bar(dp)} {round(dp,2)}% ({draw})",
        "패": f"{bar(lp)} {round(lp,2)}% ({lose})",
        "wp": float(wp),
        "dp": float(dp),
        "lp": float(lp)
    }

# =====================================================
# 루프 통합엔진 (절대참조)
# =====================================================

def loop_filter(df, cond):
    f = df.copy()
    for col_idx, val in cond.items():
        f = f[f.iloc[:, col_idx] == val]
    return f

# =====================================================
# 업로드
# =====================================================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...)):
    global CURRENT_DF

    raw = file.file.read()
    df = pd.read_csv(BytesIO(raw), encoding="utf-8")

    # 공백 제거
    df.columns = df.columns.str.strip()

    # ===== 절대참조 컬럼 위치 =====
    # A=0 NO.
    # B=1 년도
    # C=2 회차
    # D=3 순번
    # E=4 종목
    # F=5 리그
    # G=6 홈팀
    # H=7 원정팀
    # I=8 승
    # J=9 무
    # K=10 패
    # L=11 일반구분
    # M=12 핸디구분
    # N=13 결과
    # O=14 유형
    # P=15 정역
    # Q=16 홈원정

    # ===== 숫자 강제 변환 (승/무/패) =====
    df.iloc[:, 8] = pd.to_numeric(df.iloc[:, 8], errors="coerce").fillna(0)
    df.iloc[:, 9] = pd.to_numeric(df.iloc[:, 9], errors="coerce").fillna(0)
    df.iloc[:, 10] = pd.to_numeric(df.iloc[:, 10], errors="coerce").fillna(0)

    # ===== 결과값 정리 =====
    df.iloc[:, 13] = df.iloc[:, 13].astype(str).str.strip()

    # ===== 유형 필터 (일반, 핸디1만 사용) =====
    df = df[df.iloc[:, 14].isin(["일반", "핸디1"])]

    print("컬럼 개수:", len(df.columns))
    print("컬럼 리스트:", df.columns.tolist())
    print("첫 행 데이터:", df.iloc[0].tolist())
    print("shape:", df.shape)

    CURRENT_DF = df
    save_data(df)

    return {
        "total": int(len(df)),
        "경기전": int((df.iloc[:, 13] == "경기전").sum())
    }

# =====================================================
# 페이지1 경기목록
# =====================================================

@app.get("/matches")
def matches():
    df = CURRENT_DF

    # 결과 열이 몇 번째인지 (A=0 기준)
    COL_RESULT = 13   # 결과

    m = df[df.iloc[:, COL_RESULT] == "경기전"]

    # 🔥 컬럼명 제거 → 값 배열로 반환
    return m.values.tolist()

# =====================================================
# 페이지2 기본정보
# =====================================================

@app.get("/page2")
def page2(year:int, match:int):
    df = CURRENT_DF
    row = df[(df.iloc[:,COL_YEAR]==year) &
             (df.iloc[:,COL_MATCH]==match)].iloc[0]

    cond = {
        COL_TYPE: row.iloc[COL_TYPE],
        COL_HOMEAWAY: row.iloc[COL_HOMEAWAY],
        COL_GENERAL: row.iloc[COL_GENERAL],
        COL_REV: row.iloc[COL_REV],
        COL_HANDI: row.iloc[COL_HANDI]
    }

    base = loop_filter(df, cond)
    return distribution(base)

# =====================================================
# 페이지3 팀스캔
# =====================================================

@app.get("/page3")
def page3(team:str):
    df = CURRENT_DF
    team_df = df[(df.iloc[:,COL_HOME]==team) |
                 (df.iloc[:,COL_AWAY]==team)]
    return distribution(team_df)

# =====================================================
# 페이지4 배당스캔
# =====================================================

@app.get("/page4")
def page4(win:float, draw:float, lose:float):
    df = CURRENT_DF
    f = df[(df.iloc[:,COL_ODD_WIN]==win) &
           (df.iloc[:,COL_ODD_DRAW]==draw) &
           (df.iloc[:,COL_ODD_LOSE]==lose)]
    return distribution(f)

# =====================================================
# UI
# =====================================================

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<html>
<head>
<style>
body{background:#111;color:white;font-family:Arial}
.card{background:#222;padding:10px;margin:10px;border-radius:10px}
.center{text-align:center}
.toggle{cursor:pointer;color:#00ffcc}
.hidden{display:none}
</style>
</head>
<body>

<h2>SecretCore 통합설계</h2>
<button onclick="load()">경기목록</button>
<div id="list"></div>

<script>

async function load(){
    let r=await fetch('/matches');
    let d=await r.json();
    let html="";
    d.forEach((m,i)=>{
        html+=`
        <div class="card">
        <b>${m[6]}</b> vs <b>${m[7]}</b><br>
        ${m[14]}.${m[16]}.${m[11]}.${m[15]}.${m[12]}<br>
        <span class="toggle" onclick="p2(${m[1]},'${m[2]}',${m[3]},${i})">정보</span> |
        <span class="toggle" onclick="p3('${m[6]}')">${m[6]}</span> |
        <span class="toggle" onclick="p3('${m[7]}')">${m[7]}</span> |
        <span class="toggle" onclick="p4('${m[8]}','${m[9]}','${m[10]}')">승무패</span>
        <div id="d${i}" class="hidden"></div>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

async function p2(y,rn,m,i){
    let r=await fetch(`/page2?year=${y}&round=${rn}&match=${m}`);
    let d=await r.json();
    let box=document.getElementById("d"+i);
    box.innerHTML=`${d.승}<br>${d.무}<br>${d.패}`;
    box.classList.toggle("hidden");
}

async function p3(t){
    let r=await fetch(`/page3?team=${t}`);
    let d=await r.json();
    alert("팀분포\n"+d.승+"\n"+d.무+"\n"+d.패);
}

async function p4(w,d,l){
    let r=await fetch(`/page4?win=${w}&draw=${d}&lose=${l}`);
    let x=await r.json();
    alert("배당분포\n"+x.승+"\n"+x.무+"\n"+x.패);
}

</script>
</body>
</html>
"""