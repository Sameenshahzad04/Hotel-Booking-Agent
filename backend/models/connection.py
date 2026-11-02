from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config import config

engine = create_engine(
    config.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI database dependency yielding an isolated session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
