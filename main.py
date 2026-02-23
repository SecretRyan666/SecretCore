# =====================================================
# MARK 1.3 MASTER COMPLETE BUILD
# PART 1
# =====================================================

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import pandas as pd
import os
import json

app = FastAPI()

# =====================================================
# 절대참조 인덱스
# =====================================================

COL_NO=0; COL_YEAR=1; COL_ROUND=2; COL_MATCH=3
COL_SPORT=4; COL_LEAGUE=5; COL_HOME=6; COL_AWAY=7
COL_WIN_ODDS=8; COL_DRAW_ODDS=9; COL_LOSE_ODDS=10
COL_GENERAL=11; COL_HANDI=12; COL_RESULT=13
COL_TYPE=14; COL_DIR=15; COL_HOMEAWAY=16

EXPECTED_COLS=17
DATA_FILE="current_data.csv"

CURRENT_DF=pd.DataFrame()
LOGGED_IN=False
FAVORITES=[]

DIST_CACHE={}
FIVE_COND_DIST={}
LEAGUE_WEIGHT={}
MIN_CONFIDENCE=0.32
STRATEGY_HISTORY_FILE="strategy_history.json"

# =====================================================
# 데이터 로드
# =====================================================

def load_data():
    global CURRENT_DF
    if os.path.exists(DATA_FILE):
        df=pd.read_csv(
            DATA_FILE,
            encoding="utf-8-sig",
            dtype=str,
            low_memory=False
        )
        if df.shape[1]==EXPECTED_COLS:
            CURRENT_DF=df
            build_five_cond_cache(df)
            build_league_weight(df)

load_data()

# =====================================================
# 필터 엔진
# =====================================================

def apply_filters(df,type,homeaway,general,dir,handi):
    if type: df=df[df.iloc[:,COL_TYPE].isin(type.split(","))]
    if homeaway: df=df[df.iloc[:,COL_HOMEAWAY].isin(homeaway.split(","))]
    if general: df=df[df.iloc[:,COL_GENERAL].isin(general.split(","))]
    if dir: df=df[df.iloc[:,COL_DIR].isin(dir.split(","))]
    if handi: df=df[df.iloc[:,COL_HANDI].isin(handi.split(","))]
    return df

def filter_text(type,homeaway,general,dir,handi):
    parts=[]
    if type: parts.append(f"유형={type}")
    if homeaway: parts.append(f"홈/원정={homeaway}")
    if general: parts.append(f"일반={general}")
    if dir: parts.append(f"정역={dir}")
    if handi: parts.append(f"핸디={handi}")
    return " · ".join(parts) if parts else "기본조건"

# =====================================================
# 분포 엔진
# =====================================================

def distribution(df):
    key=tuple(df.index)
    if key in DIST_CACHE:
        return DIST_CACHE[key]

    total=len(df)
    if total==0:
        r={"총":0,"승":0,"무":0,"패":0,"wp":0,"dp":0,"lp":0}
        DIST_CACHE[key]=r
        return r

    result_col=df.iloc[:,COL_RESULT]
    win=(result_col=="승").sum()
    draw=(result_col=="무").sum()
    lose=(result_col=="패").sum()

    r={
        "총":int(total),
        "승":int(win),
        "무":int(draw),
        "패":int(lose),
        "wp":round(win/total*100,2),
        "dp":round(draw/total*100,2),
        "lp":round(lose/total*100,2)
    }

    DIST_CACHE[key]=r
    return r

# =====================================================
# 5조건 캐시
# =====================================================

def build_five_cond_cache(df):
    FIVE_COND_DIST.clear()
    if df.empty:
        return

    group_cols=[COL_TYPE,COL_HOMEAWAY,COL_GENERAL,COL_DIR,COL_HANDI]

    grouped=df.groupby(
        df.columns[group_cols].tolist()+
        [df.columns[COL_RESULT]]
    ).size().unstack(fill_value=0)

    for key,row in grouped.iterrows():
        total=row.sum()
        FIVE_COND_DIST[key]={
            "총":int(total),
            "wp":round(row.get("승",0)/total*100,2) if total else 0,
            "dp":round(row.get("무",0)/total*100,2) if total else 0,
            "lp":round(row.get("패",0)/total*100,2) if total else 0,
        }

# =====================================================
# 리그 가중치
# =====================================================

def build_league_weight(df):
    LEAGUE_WEIGHT.clear()
    if df.empty:
        return

    counts=df.iloc[:,COL_LEAGUE].value_counts()

    for league,count in counts.items():
        if count>=800:
            LEAGUE_WEIGHT[league]=1.05
        elif count>=300:
            LEAGUE_WEIGHT[league]=1.0
        else:
            LEAGUE_WEIGHT[league]=0.9

# =====================================================
# EV 계산
# =====================================================

def safe_ev(dist,row):
    try:
        w=float(row.iloc[COL_WIN_ODDS])
        d=float(row.iloc[COL_DRAW_ODDS])
        l=float(row.iloc[COL_LOSE_ODDS])
    except:
        return {"EV":{"승":0,"무":0,"패":0},"추천":"없음"}

    ev={
        "승":round(dist["wp"]/100*w-1,3),
        "무":round(dist["dp"]/100*d-1,3),
        "패":round(dist["lp"]/100*l-1,3)
    }

    best=max(ev,key=ev.get)
    return {"EV":ev,"추천":best}

# =====================================================
# SECRET FAST
# =====================================================

def secret_score_fast(row):
    key=(
        row.iloc[COL_TYPE],
        row.iloc[COL_HOMEAWAY],
        row.iloc[COL_GENERAL],
        row.iloc[COL_DIR],
        row.iloc[COL_HANDI]
    )

    dist=FIVE_COND_DIST.get(
        key,
        {"총":0,"wp":0,"dp":0,"lp":0}
    )

    if dist["총"]<10:
        return {"score":0,"sample":dist["총"],"추천":"없음"}

    ev=safe_ev(dist,row)
    return {
        "score":max(ev["EV"].values()),
        "sample":dist["총"],
        "추천":ev["추천"]
    }

# =====================================================
# SecretPick Brain
# =====================================================

def secret_pick_brain(row,df):

    key=(
        row.iloc[COL_TYPE],
        row.iloc[COL_HOMEAWAY],
        row.iloc[COL_GENERAL],
        row.iloc[COL_DIR],
        row.iloc[COL_HANDI]
    )

    p5=FIVE_COND_DIST.get(key,{"총":0,"wp":0,"dp":0,"lp":0})
    sample=p5.get("총",0)

    if sample<20: w5=0.4
    elif sample<50: w5=0.5
    elif sample<150: w5=0.65
    else: w5=0.75

    w_exact=1-w5

    exact_df=df[
        (df.iloc[:,COL_WIN_ODDS]==row.iloc[COL_WIN_ODDS])&
        (df.iloc[:,COL_DRAW_ODDS]==row.iloc[COL_DRAW_ODDS])&
        (df.iloc[:,COL_LOSE_ODDS]==row.iloc[COL_LOSE_ODDS])
    ]

    exact_dist=distribution(exact_df)

    sp_w=w5*p5.get("wp",0)+w_exact*exact_dist.get("wp",0)
    sp_d=w5*p5.get("dp",0)+w_exact*exact_dist.get("dp",0)
    sp_l=w5*p5.get("lp",0)+w_exact*exact_dist.get("lp",0)

    sp_map={
        "승":round(sp_w,2),
        "무":round(sp_d,2),
        "패":round(sp_l,2)
    }

    best=max(sp_map,key=sp_map.get)

    league=row.iloc[COL_LEAGUE]
    league_weight=LEAGUE_WEIGHT.get(league,1.0)

    adjusted_conf=round((sp_map[best]/100)*league_weight,3)

    return {
        "추천":best,
        "확률":sp_map,
        "confidence":adjusted_conf,
        "sample":sample
    }

# =====================================================
# 로그인
# =====================================================

@app.post("/login")
def login(username:str=Form(...),password:str=Form(...)):
    global LOGGED_IN
    if username=="ryan" and password=="963258":
        LOGGED_IN=True
    return RedirectResponse("/",302)

@app.get("/logout")
def logout():
    global LOGGED_IN
    LOGGED_IN=False
    return RedirectResponse("/",302)

# =====================================================
# 업로드
# =====================================================

@app.post("/upload-data")
def upload(file:UploadFile=File(...)):
    global CURRENT_DF

    df=pd.read_csv(
        file.file,
        encoding="utf-8-sig",
        dtype=str,
        low_memory=False
    )

    if df.shape[1]!=EXPECTED_COLS:
        return {"error":"컬럼 불일치"}

    df.to_csv(DATA_FILE,index=False,encoding="utf-8-sig")
    CURRENT_DF=df

    DIST_CACHE.clear()
    build_five_cond_cache(df)
    build_league_weight(df)

    return RedirectResponse("/",302)

# =====================================================
# Health
# =====================================================

@app.get("/health")
def health():
    return {
        "rows":len(CURRENT_DF),
        "cache":len(DIST_CACHE),
        "five_cond":len(FIVE_COND_DIST)
    }

# =====================================================
# 필터 목록 API
# =====================================================

@app.get("/filters")
def filters():
    df=CURRENT_DF
    if df.empty:
        return {}

    df=df[df.iloc[:,COL_RESULT]=="경기전"]

    return {
        "type":sorted(df.iloc[:,COL_TYPE].dropna().unique().tolist()),
        "homeaway":sorted(df.iloc[:,COL_HOMEAWAY].dropna().unique().tolist()),
        "general":sorted(df.iloc[:,COL_GENERAL].dropna().unique().tolist()),
        "dir":sorted(df.iloc[:,COL_DIR].dropna().unique().tolist()),
        "handi":sorted(df.iloc[:,COL_HANDI].dropna().unique().tolist())
    }

# =====================================================
# matches API
# =====================================================

@app.get("/matches")
def matches(
    type:str=None,
    homeaway:str=None,
    general:str=None,
    dir:str=None,
    handi:str=None
):

    df=CURRENT_DF
    if df.empty:
        return []

    base_df=df[
        (df.iloc[:,COL_RESULT]=="경기전")&
        (
            (df.iloc[:,COL_TYPE]=="일반")|
            (df.iloc[:,COL_TYPE]=="핸디1")
        )
    ]

    base_df=apply_filters(base_df,type,homeaway,general,dir,handi)

    result=[]

    for _,row in base_df.iterrows():
        sec=secret_score_fast(row)
        brain=secret_pick_brain(row,df)

        is_secret=(
            sec["score"]>0.05 and
            sec["sample"]>=20 and
            sec["추천"]!="없음"
        )

        result.append({
            "row":list(map(str,row.values.tolist())),
            "secret":is_secret,
            "pick":sec["추천"] if is_secret else "",
            "confidence":brain["confidence"],
            "filter_text":filter_text(type,homeaway,general,dir,handi)
        })

    return result

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
# Page2 - 상세 분석 (완전 안정화)
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

    home = row.iloc[COL_HOME]
    away = row.iloc[COL_AWAY]
    league = row.iloc[COL_LEAGUE]

    filtered_df = apply_filters(
        df, type, homeaway, general, dir, handi
    )

    # 5조건 완전일치
    key = (
        row.iloc[COL_TYPE],
        row.iloc[COL_HOMEAWAY],
        row.iloc[COL_GENERAL],
        row.iloc[COL_DIR],
        row.iloc[COL_HANDI]
    )

    base_dist = FIVE_COND_DIST.get(
        key,
        {"총":0,"wp":0,"dp":0,"lp":0}
    )

    # 동일리그 5조건
    league_df = filtered_df[
        (filtered_df.iloc[:, COL_LEAGUE] == league) &
        (filtered_df.iloc[:, COL_TYPE] == row.iloc[COL_TYPE]) &
        (filtered_df.iloc[:, COL_HOMEAWAY] == row.iloc[COL_HOMEAWAY]) &
        (filtered_df.iloc[:, COL_GENERAL] == row.iloc[COL_GENERAL]) &
        (filtered_df.iloc[:, COL_DIR] == row.iloc[COL_DIR]) &
        (filtered_df.iloc[:, COL_HANDI] == row.iloc[COL_HANDI])
    ]

    league_dist = distribution(league_df)

    # EV 계산
    secret_data = safe_ev(base_dist, row)
    best_ev = max(secret_data["EV"], key=secret_data["EV"].get)

    ev_html = ""
    for k,v in secret_data["EV"].items():

        highlight = ""
        if k == best_ev:
            highlight += "border:2px solid #22c55e;"

        if v > 0.08:
            highlight += "box-shadow:0 0 12px #22c55e;"
        elif v < -0.05:
            highlight += "background:#7f1d1d;"

        ev_html += f"""
        <div style="
            flex:1;
            background:#1e293b;
            padding:16px;
            border-radius:16px;
            {highlight}
        ">
            <b>{k}</b><br>
            EV {v}
        </div>
        """

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

    <div style="display:flex;gap:20px;">

        <div style="flex:1;background:#1e293b;
                    padding:18px;border-radius:18px;">
            <h3>5조건 완전일치</h3>
            총 {base_dist["총"]}경기
            <div>승 {base_dist["wp"]}%</div>
            {bar_html(base_dist["wp"],"win")}
            <div>무 {base_dist["dp"]}%</div>
            {bar_html(base_dist["dp"],"draw")}
            <div>패 {base_dist["lp"]}%</div>
            {bar_html(base_dist["lp"],"lose")}
        </div>

        <div style="flex:1;background:#1e293b;
                    padding:18px;border-radius:18px;">
            <h3>동일리그 5조건</h3>
            총 {league_dist["총"]}경기
            <div>승 {league_dist["wp"]}%</div>
            {bar_html(league_dist["wp"],"win")}
            <div>무 {league_dist["dp"]}%</div>
            {bar_html(league_dist["dp"],"draw")}
            <div>패 {league_dist["lp"]}%</div>
            {bar_html(league_dist["lp"],"lose")}
        </div>

    </div>

    <br><br>

    <div style="background:#1e293b;
                padding:18px;border-radius:18px;">
        <h3>시크릿 EV</h3>
        <div style="display:flex;gap:12px;">
        {ev_html}
        </div>
    </div>

    <br><br>
    <a href="/page3?no={no}">팀 분석</a><br>
    <a href="/page4?no={no}">배당 분석</a><br><br>

    <button onclick="history.back()">← 뒤로</button>
    </body>
    </html>
    """

# =====================================================
# Page3 - 팀 분석
# =====================================================

@app.get("/page3", response_class=HTMLResponse)
def page3(no:str=None):

    if not no:
        return "잘못된 접근"

    df=CURRENT_DF
    row_df=df[df.iloc[:,COL_NO]==str(no)]
    if row_df.empty:
        return "경기 없음"

    row=row_df.iloc[0]
    team=row.iloc[COL_HOME]

    team_df=df[
        (df.iloc[:,COL_HOME]==team)|
        (df.iloc[:,COL_AWAY]==team)
    ]

    dist=distribution(team_df)

    return f"""
    <html><body style="background:#0f1720;color:white;padding:20px;">
    <h2>{team} 팀 통계</h2>
    총 {dist["총"]}경기
    <div>승 {dist["wp"]}%</div>
    {bar_html(dist["wp"],"win")}
    <div>무 {dist["dp"]}%</div>
    {bar_html(dist["dp"],"draw")}
    <div>패 {dist["lp"]}%</div>
    {bar_html(dist["lp"],"lose")}
    <br><button onclick="history.back()">← 뒤로</button>
    </body></html>
    """

# =====================================================
# Page4 - 배당 분석
# =====================================================

@app.get("/page4", response_class=HTMLResponse)
def page4(no:str=None):

    if not no:
        return "잘못된 접근"

    df=CURRENT_DF
    row_df=df[df.iloc[:,COL_NO]==str(no)]
    if row_df.empty:
        return "경기 없음"

    row=row_df.iloc[0]

    win_df=df[df.iloc[:,COL_WIN_ODDS]==row.iloc[COL_WIN_ODDS]]
    win_dist=distribution(win_df)

    return f"""
    <html><body style="background:#0f1720;color:white;padding:20px;">
    <h2>배당 분석</h2>
    승 동일 배당 통계
    총 {win_dist["총"]}경기
    <div>승 {win_dist["wp"]}%</div>
    {bar_html(win_dist["wp"],"win")}
    <div>무 {win_dist["dp"]}%</div>
    {bar_html(win_dist["dp"],"draw")}
    <div>패 {win_dist["lp"]}%</div>
    {bar_html(win_dist["lp"],"lose")}
    <br><button onclick="history.back()">← 뒤로</button>
    </body></html>
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
    candidates = [c for c in candidates if c["confidence"] >= MIN_CONFIDENCE]

    if len(candidates) < 12:
        return {"error": "경기 수 부족"}

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

    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    candidates = [c for c in candidates if c["confidence"] >= MIN_CONFIDENCE]

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
                "combo_odds": round(a["odds"] * b["odds"], 2)
            })

    return {
        "port1": port1,
        "port2": port2,
        "total_combos": len(combos)
    }

# =====================================================
# 전략 평가 + ROI
# =====================================================

def evaluate_strategy1():

    df = CURRENT_DF
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
            if not row.empty and row.iloc[0][COL_RESULT] == item["pick"]:
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
                        if all(
                            not r.empty and
                            r.iloc[0][COL_RESULT]==pick["pick"]
                            for r,pick in zip(rows,[p1,p2,p3,p4])
                        ):
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