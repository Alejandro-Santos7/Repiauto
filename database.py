import models
from config import init_db, engine, logger
from sqlalchemy import text, inspect

try:
    init_db()
except Exception as e:
    logger.warning(f"DB init deferred: {e}")


def _migrate():
    inspector = inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("locations")]
    if "custom_name" not in cols:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE locations ADD COLUMN custom_name VARCHAR(100)"))
                conn.commit()
            logger.info("Migration: added custom_name column to locations")
        except Exception as e:
            logger.warning(f"Migration custom_name skipped: {e}")


_migrate()
