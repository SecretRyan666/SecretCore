from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from jose import jwt, JWTError
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from io import BytesIO
import os
import asyncio
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, brier_score_loss
from typing import Dict, Any, List
import hashlib
from functools import lru_cache

# ================= 앱 설정 =================
app = FastAPI(title="토토 예측 PRO v2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # 보안 강화
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= 보안 =================
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-in-prod")
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
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != FAKE_USER["username"] or form_data.password != FAKE_USER["password"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

# ================= 데이터 관리 =================
DATA_FILE = "data_store.csv"
MODEL_FILE = "toto_model.pkl"
CURRENT_DF = pd.DataFrame()
FILTERED_DF = pd.DataFrame()
data_lock = asyncio.Lock()
MODEL = None
SCALER = None
LE_HOME = LabelEncoder()
LE_AWAY = LabelEncoder()
LE_LEAGUE = LabelEncoder()

def save_data(df):
    df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')

def preprocess_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """자동 전처리"""
    df.columns = df.columns.str.strip()
    
    # 숫자 컬럼
    for col in ['년도', '순번', '승', '무', '패']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 결과 표준화
    if '결과' in df.columns:
        df['결과'] = df['결과'].astype(str).str.strip()
        df['결과'] = df['결과'].replace({'W': '승', 'D': '무', 'L': '패', 'nan': '경기전'})
    
    # 유형 필터링
    if '유형' in df.columns:
        df = df[df['유형'].isin(['일반', '핸디1', '핸디2'])]
    
    return df.fillna(0)

def load_ml_model():
    """ML 모델 로드/학습"""
    global MODEL, SCALER
    if os.path.exists(MODEL_FILE):
        try:
            MODEL = joblib.load(MODEL_FILE)
            SCALER = joblib.load("scaler.pkl")
            return True
        except:
            pass
    
    if len(FILTERED_DF) > 50:
        train_model()
    return False

def train_model():
    """모델 학습"""
    global MODEL, SCALER
    
    train_df = FILTERED_DF[FILTERED_DF['결과'] != '경기전'].copy()
    if len(train_df) < 50:
        return False
    
    # 피처 준비
    train_df['home_encoded'] = LE_HOME.fit_transform(train_df['홈팀'].astype(str))
    train_df['away_encoded'] = LE_AWAY.fit_transform(train_df['원정팀'].astype(str))
    train_df['league_encoded'] = LE_LEAGUE.fit_transform(train_df['리그'].astype(str))
    
    features = ['승', '무', '패', 'home_encoded', 'away_encoded', 'league_encoded']
    X = train_df[features].fillna(0)
    y = (train_df['결과'] == '승').astype(int)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    SCALER = StandardScaler()
    X_train_scaled = SCALER.fit_transform(X_train)
    
    MODEL = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
    MODEL.fit(X_train_scaled, y_train)
    
    # 저장
    joblib.dump(MODEL, MODEL_FILE)
    joblib.dump(SCALER, "scaler.pkl")
    joblib.dump(LE_HOME, 'le_home.pkl')
    joblib.dump(LE_AWAY, 'le_away.pkl')
    joblib.dump(LE_LEAGUE, 'le_league.pkl')
    
    score = MODEL.score(SCALER.transform(X_test), y_test)
    print(f"✅ ML 모델 학습 완료: {score:.3f}")
    return True

# ================= 기존 유틸 =================
def bar(p):
    filled = int(p/5)
    return "█"*filled + "-"*(20-filled)

def distribution(df):
    total = len(df)
    if total == 0:
        return {"총":0,"승":"-","무":"-","패":"-","wp":0,"dp":0,"lp":0}

    vc = df["결과"].value_counts()
    win = vc.get("승",0)
    draw = vc.get("무",0)
    lose = vc.get("패",0)

    wp = win/total*100
    dp = draw/total*100
    lp = lose/total*100

    return {
        "총": total,
        "승": f"{bar(wp)} {round(wp,2)}% ({win})",
        "무": f"{bar(dp)} {round(dp,2)}% ({draw})",
        "패": f"{bar(lp)} {round(lp,2)}% ({lose})",
        "wp": wp, "dp": dp, "lp": lp
    }

def ai_grade(score):
    if score >= 92: return "S+"
    if score >= 85: return "S"
    if score >= 75: return "A"
    if score >= 65: return "B"
    if score >= 55: return "C"
    return "D"

# ================= 업로드 =================
@app.post("/upload-data")
async def upload_data(file: UploadFile = File(...), user: str = Depends(get_current_user)):
    global CURRENT_DF, FILTERED_DF
    
    async with data_lock:
        raw = await file.read()
        
        # 엑셀/CSV 자동 판별
        if file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(BytesIO(raw))
        else:
            try:
                df = pd.read_csv(BytesIO(raw), encoding='utf-8-sig')
            except:
                df = pd.read_csv(BytesIO(raw), encoding='cp949')
        
        # 전처리
        df = preprocess_dataframe(df)
        CURRENT_DF = df
        FILTERED_DF = df[df["유형"].isin(["일반","핸디1"])]
        
        save_data(FILTERED_DF)
        load_ml_model()  # ML 모델 학습
        
        return {
            "total_games": len(CURRENT_DF),
            "train_games": len(FILTERED_DF[FILTERED_DF["결과"] != "경기전"]),
            "predict_games": len(FILTERED_DF[FILTERED_DF["결과"] == "경기전"])
        }

# ================= 기존 API =================
@app.get("/matches")
def matches(user: str = Depends(get_current_user)):
    return FILTERED_DF[FILTERED_DF["결과"] == "경기전"].to_dict("records")

@app.get("/integrated-scan")
def integrated_scan(year: int, round_no: str, match_no: int, user: str = Depends(get_current_user)):
    df = FILTERED_DF
    row = df[(df["년도"] == year) & (df["회차"] == round_no) & (df["순번"] == match_no)]
    
    if row.empty:
        raise HTTPException(404, detail="경기 없음")
    
    row = row.iloc[0]
    
    # 기존 통합스캔 로직 (생략없이 그대로)
    base = df[(df["유형"] == row["유형"]) & (df["홈원정"] == row["홈원정"]) &
              (df["일반구분"] == row["일반구분"]) & (df["정역"] == row["정역"]) &
              (df["핸디구분"] == row["핸디구분"])]
    
    base_dist = distribution(base)
    level2 = df[(df["유형"] == row["유형"]) & (df["홈원정"] == row["홈원정"]) & (df["일반구분"] == row["일반구분"])]
    level2_dist = distribution(level2)
    level3 = df[df["유형"] == row["유형"]]
    level3_dist = distribution(level3)
    
    league_all = df[df["리그"] == row["리그"]]
    league_all_dist = distribution(league_all)
    league_match = league_all[(league_all["일반구분"] == row["일반구분"])]
    league_match_dist = distribution(league_match)
    
    home_team = df[df["홈팀"] == row["홈팀"]]
    away_team = df[df["원정팀"] == row["원정팀"]]
    
    odds_win_all = distribution(df[df["승"] == row["승"]])
    odds_win_match = distribution(base[base["승"] == row["승"]])
    odds_draw_all = distribution(df[df["무"] == row["무"]])
    odds_draw_match = distribution(base[base["무"] == row["무"]])
    odds_lose_all = distribution(df[df["패"] == row["패"]])
    odds_lose_match = distribution(base[base["패"] == row["패"]])
    
    ev_w = base_dist["wp"] / 100 * row["승"] - 1
    ev_d = base_dist["dp"] / 100 * row["무"] - 1
    ev_l = base_dist["lp"] / 100 * row["패"] - 1
    ev_dict = {"승": ev_w, "무": ev_d, "패": ev_l}
    best = max(ev_dict, key=ev_dict.get)
    
    score = max(base_dist["wp"], base_dist["dp"], base_dist["lp"])
    if ev_dict[best] > 0: score += 7
    if base_dist["총"] < 30: score -= 7
    if base_dist["dp"] >= 35: score -= 5
    
    grade = ai_grade(score)
    secret = ""
    if row["일반구분"] == "A" and base_dist["dp"] >= 30:
        secret = "🎯 무 시그널"
    if row["핸디구분"] in ["B", "C"] and base_dist["lp"] >= 50:
        secret = "⚠ 핸디 붕괴 위험"
    
    return {
        "추천": best,
        "AI등급": grade,
        "시크릿": secret,
        "기본조건키": base_dist,
        "2단계": level2_dist,
        "3단계": level3_dist,
        "리그전체": league_all_dist,
        "리그매칭": league_match_dist,
        "팀홈": distribution(home_team),
        "팀원정": distribution(away_team),
        "배당승전체": odds_win_all,
        "배당승매칭": odds_win_match,
        "배당무전체": odds_draw_all,
        "배당무매칭": odds_draw_match,
        "배당패전체": odds_lose_all,
        "배당패매칭": odds_lose_match
    }

# ================= ML 예측 =================
class PredictionRequest(BaseModel):
    년도: int
    회차: str
    순번: int
    홈팀: str
    원정팀: str
    리그: str
    승: float
    무: float
    패: float
    유형: str
    홈원정: str

class PredictionResponse(BaseModel):
    ml_win_prob: float
    ml_recommend: str
    ml_confidence: str
    통합추천: str

@app.post("/predict", response_model=PredictionResponse)
async def ml_predict(request: PredictionRequest, user: str = Depends(get_current_user)):
    if MODEL is None:
        load_ml_model()
    
    if MODEL is None:
        raise HTTPException(400, detail="모델 학습 데이터 부족")
    
    # 피처 생성
    feature_df = pd.DataFrame([{
        '승': request.승, '무': request.무, '패': request.패,
        'home_encoded': LE_HOME.transform([request.홈팀])[0] if request.홈팀 in LE_HOME.classes_ else 0,
        'away_encoded': LE_AWAY.transform([request.원정팀])[0] if request.원정팀 in LE_AWAY.classes_ else 0,
        'league_encoded': LE_LEAGUE.transform([request.리그])[0] if request.리그 in LE_LEAGUE.classes_ else 0
    }])
    
    X_scaled = SCALER.transform(feature_df)
    win_prob = MODEL.predict_proba(X_scaled)[0][1]
    
    confidence = "높음" if win_prob > 0.65 or win_prob < 0.35 else "보통"
    ml_recommend = "승" if win_prob > 0.6 else "패" if win_prob < 0.4 else "패스"
    
    return PredictionResponse(
        ml_win_prob=round(win_prob, 3),
        ml_recommend=ml_recommend,
        ml_confidence=confidence,
        통합추천=ml_recommend
    )

# ================= 통합 PRO + 모델 평가 =================
@app.get("/pro-performance")
async def pro_performance(user: str = Depends(get_current_user)):
    """모델 성능 + 통합스캔 대시보드"""
    if FILTERED_DF.empty:
        return {"status": "데이터 없음"}
    
    test_df = FILTERED_DF[FILTERED_DF['결과'] != '경기전'].tail(100)
    if len(test_df) < 20:
        return {"status": "평가 데이터 부족"}
    
    # ML 정확도
    features = ['승', '무', '패', 'home_encoded', 'away_encoded', 'league_encoded']
    test_df['home_encoded'] = LE_HOME.transform(test_df['홈팀'].astype(str))
    test_df['away_encoded'] = LE_AWAY.transform(test_df['원정팀'].astype(str))
    test_df['league_encoded'] = LE_LEAGUE.transform(test_df['리그'].astype(str))
    
    X_test = test_df[features].fillna(0)
    y_true = (test_df['결과'] == '승').astype(int)
    X_test_scaled = SCALER.transform(X_test)
    y_pred_proba = MODEL.predict_proba(X_test_scaled)[:, 1]
    y_pred = MODEL.predict(X_test_scaled)
    
    hit_rate = accuracy_score(y_true, y_pred)
    brier = brier_score_loss(y_true, y_pred_proba)
    
    return {
        "ML_적중률": f"{hit_rate:.1%}",
        "BrierScore": round(brier, 3),
        "평가경기수": len(test_df),
        "최근100경기_평균배당": f"{test_df['승'].mean():.2f}",
        "status": "🚦" if hit_rate > 0.57 else "🟡"
    }

# ================= 상태 =================
@app.get("/status")
def status():
    return {
        "total_games": len(FILTERED_DF),
        "pending_games": len(FILTERED_DF[FILTERED_DF["결과"] == "경기전"]),
        "model_loaded": MODEL is not None,
        "data_loaded": not FILTERED_DF.empty
    }

# ================= 시작 =================
@app.on_event("startup")
async def startup():
    if os.path.exists(DATA_FILE):
        global FILTERED_DF
        FILTERED_DF = pd.read_csv(DATA_FILE)
        load_ml_model()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)