import uuid
import threading
import logging
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


_import_progress = {}


def progress_html(task_id: str, current: int, total: int, percent: int, created: int, updated: int, skipped: int, status: str):
    if status == "done":
        parts = []
        if created:
            parts.append(f"{created} creados")
        if updated:
            parts.append(f"{updated} actualizados")
        if skipped:
            parts.append(f"{skipped} omitidos")
        msg = ", ".join(parts) if parts else "Sin cambios"
        return f"""<div id="import-progress" class="space-y-4 text-center">
            <div class="text-4xl">&#x2705;</div>
            <p class="text-green-600 text-lg font-bold">Importacion completada</p>
            <p class="text-slate-600">{msg}</p>
            <button onclick="closeModal(); window.location.href='/products'"
                class="mt-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Ver productos</button>
        </div>"""

    return f"""<div id="import-progress" class="space-y-4">
        <p class="text-sm text-slate-600">Procesando fila {current}/{total}&hellip;</p>
        <div class="w-full bg-slate-200 rounded-full h-5 overflow-hidden">
            <div class="bg-green-500 h-5 rounded-full transition-all duration-300" style="width: {percent}%"></div>
        </div>
        <div class="flex justify-between text-xs text-slate-500">
            <span>{percent}% completado</span>
            <span>C:{created} A:{updated} O:{skipped}</span>
        </div>
        <div hx-get="/products/import/progress/{task_id}" hx-trigger="every 500ms"
            hx-target="#import-progress" hx-swap="outerHTML"></div>
    </div>"""


def run_import(task_id: str, rows_data: list):
    try:
        created = updated = skipped = 0
        total = len(rows_data)
        db = SessionLocal()
        try:
            for idx, row in enumerate(rows_data):
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
                current = idx + 1
                _import_progress[task_id] = {
                    "status": "processing",
                    "current": current, "total": total,
                    "percent": int(current / total * 100),
                    "created": created, "updated": updated, "skipped": skipped,
                }
            db.commit()
            _import_progress[task_id] = {
                "status": "done",
                "current": total, "total": total, "percent": 100,
                "created": created, "updated": updated, "skipped": skipped,
            }
        except Exception as e:
            db.rollback()
            _import_progress[task_id] = {"status": "error", "message": str(e)}
        finally:
            db.close()
    except Exception as e:
        _import_progress[task_id] = {"status": "error", "message": str(e)}


def get_import_progress(task_id: str):
    return _import_progress.get(task_id)


def pop_import_progress(task_id: str):
    return _import_progress.pop(task_id, None)


def set_import_progress(task_id: str, data: dict):
    _import_progress[task_id] = data
