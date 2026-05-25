import os
import logging
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from fastapi.templating import Jinja2Templates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repiauto")


class Base(DeclarativeBase):
    pass


def get_db_url():
    return os.getenv("DATABASE_URL", "sqlite:///./repiauto.db")


_url = get_db_url()
if "postgresql" in _url:
    engine = create_engine(_url, pool_size=5, max_overflow=10, pool_recycle=3600, pool_pre_ping=True, connect_args={"connect_timeout": 10})
else:
    engine = create_engine(_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
templates = Jinja2Templates(directory="templates")


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        raise
