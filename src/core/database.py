import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Use PostgreSQL on Render, SQLite locally
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gaitscan.db")

# Fix for older Render PostgreSQL URLs (postgres:// → postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from src.core.models import Session, Finding, Exercise
    from src.models.user import User  # ADD THIS
    Base.metadata.create_all(bind=engine)
    print("Database tables created.")