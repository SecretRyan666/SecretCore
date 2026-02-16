from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jose import jwt, JWTError
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= AUTH =================

SECRET_KEY = "secretcorekey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 600

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
FAKE_USER = {"username": "admin", "password": "1234"}

def create_token(data: dict):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401)

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != FAKE_USER["username"] or form_data.password != FAKE_USER["password"]:
        raise HTTPException(status_code=401)
    token = create_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

# ================= DATA STORAGE =================

DATA_FILE = "data_store.csv"
CURRENT_DF = pd.DataFrame()

if os.path.exists(DATA_FILE):
    CURRENT_DF = pd.read_csv(DATA_FILE)

def save_data(df):
    df.to_csv(DATA_FILE, index=False)

# ================= UTIL =================

def bar(p):
    filled = int(p/5)
    return "█"*filled + "-"*(20-filled)

def dist(df):
    total = len(df)
    vc = df["결과"].value_counts()
    win = vc.get("승",0)
    draw = vc.get("무",0)
    lose = vc.get("패",0)
    wp = win/total*100 if total else 0
    dp = draw/total*100 if total else 0
    lp = lose/total*100 if total else 0
    return {
        "총": total,
        "승": f"{bar(wp)} {round(wp,2)}% ({win})",
        "무": f"{bar(dp)} {round(dp,2)}% ({draw})",
        "패": f"{bar(lp)} {round(lp,2)}% ({lose})",
        "wp": wp, "dp": dp, "lp": lp
    }

def ai_grade(score):
    if score >= 90: return "S+"
    if score >= 80: return "S"
    if score >= 70: return "A"
    if score >= 60: return "B"
    if score >= 50: return "C"
    return "D"

# ================= UPLOAD (엑셀 → CSV 변환) =================

@app.post("/upload-data")
def upload_data(file: UploadFile = File(...),
                user: str = Depends(get_current_user)):

    global CURRENT_DF

    try:
        df = pd.read_excel(
            file.file,
            sheet_name="원본",
            usecols="A:Q"   # ✅ 메모리 절감
        )
    except Exception as e:
        raise HTTPException(500, f"엑셀 로드 실패: {str(e)}")

    # 컬럼 강제 지정 (A~Q 고정 구조)
    df.columns = [
        "NO","년도","회차","순번","종목","리그",
        "홈팀","원정팀","승","무","패",
        "일반구분","핸디구분","결과","유형","정역","홈원정"
    ]

    df["결과"] = df["결과"].astype(str).str.strip()
    df["승"] = pd.to_numeric(df["승"], errors="coerce")
    df["무"] = pd.to_numeric(df["무"], errors="coerce")
    df["패"] = pd.to_numeric(df["패"], errors="coerce")

    df = df[df["유형"].isin(["일반","핸디1"])]

    CURRENT_DF = df
    save_data(df)

    return {
        "total_games": len(df),
        "target_games": len(df[df["결과"]=="경기전"])
    }

# ================= MATCH LIST =================

@app.get("/matches")
def matches(user:str=Depends(get_current_user)):
    if CURRENT_DF.empty:
        return []
    m = CURRENT_DF[CURRENT_DF["결과"]=="경기전"].copy()
    m = m.sort_values(["리그","일반구분"])
    return m.to_dict("records")

# ================= 통합스캔 =================

@app.get("/integrated-scan")
def scan(year:int, round_no:str, match_no:int,
         user:str=Depends(get_current_user)):

    df = CURRENT_DF

    target = df[(df["년도"]==year)&
                (df["회차"]==round_no)&
                (df["순번"]==match_no)]

    if target.empty:
        raise HTTPException(404)

    row = target.iloc[0]

    base = df[
        (df["유형"]==row["유형"])&
        (df["홈원정"]==row["홈원정"])&
        (df["일반구분"]==row["일반구분"])&
        (df["정역"]==row["정역"])&
        (df["핸디구분"]==row["핸디구분"])
    ]

    base_dist = dist(base)

    ev_w = base_dist["wp"]/100*row["승"]-1
    ev_d = base_dist["dp"]/100*row["무"]-1
    ev_l = base_dist["lp"]/100*row["패"]-1

    ev_dict = {"승":ev_w,"무":ev_d,"패":ev_l}
    best = max(ev_dict,key=ev_dict.get)

    score = max(base_dist["wp"],base_dist["dp"],base_dist["lp"])
    if ev_dict[best]>0: score+=5
    if base_dist["dp"]>=35: score-=5
    if base_dist["총"]<30: score-=5

    grade = ai_grade(score)

    return {
        "조건":{
            "유형":row["유형"],
            "홈원정":row["홈원정"],
            "일반":row["일반구분"],
            "정역":row["정역"],
            "핸디":row["핸디구분"]
        },
        "분포":base_dist,
        "EV":{k:round(v,3) for k,v in ev_dict.items()},
        "AI등급":grade,
        "추천":best
    }

# ================= UI =================

@app.get("/",response_class=HTMLResponse)
def home():
    return """
    <html>
    <body style="background:#111;color:white;font-family:Arial;padding:20px;">
    <h2>SecretCore PRO 안정버전</h2>
    <p>/docs 에서 로그인 → 업로드 후 사용</p>
    </body>
    </html>
    """