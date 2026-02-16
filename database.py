import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 로컬 개발용 기본 DB (환경변수 없으면 자동 사용)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./secretcore.db"
)

# SQLite일 경우 check_same_thread 필요
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()