from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import pandas as pd
from io import BytesIO

app = FastAPI()

# =====================================================
# 절대참조 컬럼 인덱스
# =====================================================

COL_NO=0; COL_YEAR=1; COL_ROUND=2; COL_MATCH=3
COL_SPORT=4; COL_LEAGUE=5
COL_HOME=6; COL_AWAY=7
COL_WIN_ODDS=8; COL_DRAW_ODDS=9; COL_LOSE_ODDS=10
COL_GENERAL=11; COL_HANDI=12
COL_RESULT=13; COL_TYPE=14; COL_DIR=15; COL_HOMEAWAY=16

CURRENT_DF = pd.DataFrame()

# =====================================================
# 루프엔진
# =====================================================

def base_filter(df):
    return df[
        (df.iloc[:,COL_RESULT]=="경기전") &
        (df.iloc[:,COL_TYPE].isin(["일반","핸디1"]))
    ]

def run_filter(df, cond):
    for c,v in cond.items():
        df = df[df.iloc[:,c]==v]
    return df

def distribution(df):
    total=len(df)
    if total==0:
        return {"총":0,"승":0,"무":0,"패":0}
    r=df.iloc[:,COL_RESULT]
    return {
        "총":total,
        "승":int((r=="승").sum()),
        "무":int((r=="무").sum()),
        "패":int((r=="패").sum())
    }

# =====================================================
# 업로드
# =====================================================

@app.post("/upload-data")
def upload(file: UploadFile = File(...)):
    global CURRENT_DF
    df=pd.read_csv(BytesIO(file.file.read()),low_memory=False)

    df.iloc[:,COL_WIN_ODDS]=pd.to_numeric(df.iloc[:,COL_WIN_ODDS],errors="coerce").fillna(0)
    df.iloc[:,COL_DRAW_ODDS]=pd.to_numeric(df.iloc[:,COL_DRAW_ODDS],errors="coerce").fillna(0)
    df.iloc[:,COL_LOSE_ODDS]=pd.to_numeric(df.iloc[:,COL_LOSE_ODDS],errors="coerce").fillna(0)

    CURRENT_DF=df
    return {"rows":len(df)}

# =====================================================
# 페이지1
# =====================================================

@app.get("/matches")
def matches():
    return base_filter(CURRENT_DF).values.tolist()

# =====================================================
# 페이지2
# =====================================================

@app.get("/page2")
def page2(year:int, match:int):

    df=CURRENT_DF
    row=df[(df.iloc[:,COL_YEAR]==year)&(df.iloc[:,COL_MATCH]==match)].iloc[0]

    cond={
        COL_TYPE:row.iloc[COL_TYPE],
        COL_HOMEAWAY:row.iloc[COL_HOMEAWAY],
        COL_GENERAL:row.iloc[COL_GENERAL],
        COL_DIR:row.iloc[COL_DIR],
        COL_HANDI:row.iloc[COL_HANDI]
    }

    base_df=run_filter(df,cond)

    return {
        "기본":distribution(base_df)
    }

# =====================================================
# detail 페이지
# =====================================================

@app.get("/detail",response_class=HTMLResponse)
def detail(year:int,match:int):
    return f"""
    <html>
    <head>
    <style>
    body{{background:#0d1117;color:white;font-family:Arial;padding:30px}}
    .card{{background:#161b22;padding:40px;border-radius:25px;font-size:24px}}
    .back{{margin-bottom:20px;display:inline-block;
    background:linear-gradient(135deg,#00e0b8,#00b3ff);
    padding:15px 25px;border-radius:20px;color:black;text-decoration:none}}
    </style>
    </head>
    <body>
    <a class='back' href='/'>← 경기목록</a>
    <div id='box'></div>
    <script>
    fetch(`/page2?year={year}&match={match}`)
    .then(r=>r.json())
    .then(d=>{
        document.getElementById("box").innerHTML=`
        <div class="card">
        기본조건<br><br>
        승: ${'{'}d.기본.승{'}'}<br>
        무: ${'{'}d.기본.무{'}'}<br>
        패: ${'{'}d.기본.패{'}'}
        </div>`;
    });
    </script>
    </body>
    </html>
    """

# =====================================================
# 메인 UI
# =====================================================

@app.get("/",response_class=HTMLResponse)
def home():
    return """
<html>
<head>
<style>
body{background:#0d1117;color:white;font-family:Arial;padding:30px}
h1{font-size:42px}
.card{
    background:#161b22;
    margin-bottom:30px;
    padding:35px;
    border-radius:25px;
}
.row{
    display:flex;
    justify-content:space-between;
    align-items:center;
}
.title{font-size:28px;font-weight:bold}
.sub{color:#aaa;margin-top:10px}
.odds{margin-top:10px;color:#ccc}
.info-btn{
    width:70px;height:70px;
    border-radius:20px;
    background:linear-gradient(135deg,#00e0b8,#00b3ff);
    border:none;
    font-weight:bold;
    cursor:pointer;
}
.main-btn{
    background:linear-gradient(135deg,#00e0b8,#00b3ff);
    padding:20px 40px;
    border-radius:20px;
    border:none;
    font-size:20px;
    margin-bottom:40px;
}
</style>
</head>
<body>
<h1>SecretCore PRO</h1>

<button class="main-btn" onclick="load()">경기목록 불러오기</button>
<div id="list"></div>

<script>

async function load(){
    let r=await fetch('/matches');
    let d=await r.json();
    let html="";
    d.forEach((m)=>{
        html+=`
        <div class="card">
        <div class="row">
            <div>
                <div class="title">${m[6]} vs ${m[7]}</div>
                <div class="sub">${m[14]} · ${m[16]} · ${m[11]} · ${m[15]}</div>
                <div class="odds">배당: 승 ${m[8]} | 무 ${m[9]} | 패 ${m[10]}</div>
            </div>
            <button class="info-btn" onclick="goDetail(${m[1]},${m[3]})">정보</button>
        </div>
        </div>`;
    });
    document.getElementById("list").innerHTML=html;
}

function goDetail(y,m){
    window.location.href=`/detail?year=${y}&match=${m}`;
}

</script>
</body>
</html>
"""