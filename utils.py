from urllib.parse import quote

from fastapi.responses import RedirectResponse

from config import SessionLocal, logger
from models import ProductCatalog


def safe_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def error_redirect(url: str, message: str):
    sep = "&" if "?" in url else "?"
    return RedirectResponse(url=f"{url}{sep}error={quote(message)}", status_code=303)


def success_redirect(url: str, message: str):
    sep = "&" if "?" in url else "?"
    return RedirectResponse(url=f"{url}{sep}success={quote(message)}", status_code=303)


def do_import(rows_data: list):
    created = updated = skipped = 0
    total = len(rows_data)
    db = SessionLocal()
    try:
        for row in rows_data:
            sku_china = row["sku_china"]
            name = row["name"]
            if not sku_china or not name:
                skipped += 1
            else:
                existing = db.query(ProductCatalog).filter(ProductCatalog.sku_china == sku_china).first()
                if existing:
                    existing.name = name
                    existing.sku_usa = sku_china
                    updated += 1
                else:
                    db.add(ProductCatalog(sku_usa=sku_china, sku_china=sku_china, name=name))
                    created += 1
        db.commit()
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()
    return {"created": created, "updated": updated, "skipped": skipped, "total": total}
