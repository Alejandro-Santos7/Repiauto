import uuid
import threading
import html as html_mod
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy import or_

from config import SessionLocal, templates, logger
from models import ProductCatalog
from utils import (
    safe_str, safe_int, error_redirect, success_redirect,
    progress_html, run_import, set_import_progress, get_import_progress, pop_import_progress,
)

router = APIRouter()


@router.get("/products", response_class=HTMLResponse)
async def products(request: Request, q: str = ""):
    q = safe_str(q)
    try:
        db = SessionLocal()
        try:
            query = db.query(ProductCatalog).order_by(ProductCatalog.created_at.desc())
            if q:
                search = f"%{q}%"
                query = query.filter(or_(
                    ProductCatalog.name.ilike(search),
                    ProductCatalog.sku_usa.ilike(search),
                    ProductCatalog.sku_china.ilike(search),
                ))
            prods = query.limit(50).all()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Products error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "No se pudieron cargar los productos."})
    return templates.TemplateResponse("products.html", {"request": request, "products": prods, "query": q})


@router.post("/products")
async def products_create(request: Request, sku_usa: str = Form(None), sku_china: str = Form(None), name: str = Form(None)):
    name = safe_str(name)
    sku_usa = safe_str(sku_usa)
    sku_china = safe_str(sku_china) or None
    if not name:
        return error_redirect("/products", "El nombre del producto es obligatorio.")
    if not sku_usa and not sku_china:
        return error_redirect("/products", "Debes proporcionar al menos un SKU (USA o China).")
    try:
        db = SessionLocal()
        try:
            from sqlalchemy.exc import IntegrityError
            db.add(ProductCatalog(sku_usa=sku_usa, sku_china=sku_china, name=name))
            db.commit()
            return success_redirect("/products", "Producto creado correctamente.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/products", f"El SKU '{sku_usa}' ya esta registrado.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Product create error: {e}")
        return error_redirect("/products", "Error al crear el producto.")


@router.post("/products/{product_id}/update")
async def products_update(request: Request, product_id: int, sku_usa: str = Form(None), sku_china: str = Form(None), name: str = Form(None)):
    name = safe_str(name)
    sku_usa = safe_str(sku_usa)
    sku_china = safe_str(sku_china) or None
    if not name:
        return error_redirect("/products", "El nombre del producto es obligatorio.")
    if not sku_usa and not sku_china:
        return error_redirect("/products", "Debes proporcionar al menos un SKU.")
    try:
        db = SessionLocal()
        try:
            from sqlalchemy.exc import IntegrityError
            p = db.get(ProductCatalog, product_id)
            if not p:
                return error_redirect("/products", "Producto no encontrado.")
            p.sku_usa = sku_usa
            p.sku_china = sku_china
            p.name = name
            db.commit()
            return success_redirect("/products", "Producto actualizado.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/products", f"El SKU '{sku_usa}' ya esta en uso.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Product update error: {e}")
        return error_redirect("/products", "Error al actualizar el producto.")


@router.post("/products/{product_id}/delete")
async def products_delete(request: Request, product_id: int):
    try:
        db = SessionLocal()
        try:
            from sqlalchemy.exc import IntegrityError
            p = db.get(ProductCatalog, product_id)
            if not p:
                return error_redirect("/products", "Producto no encontrado.")
            db.delete(p)
            db.commit()
            return success_redirect("/products", "Producto eliminado.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/products", "No se puede eliminar: esta siendo usado en algun pedido.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Product delete error: {e}")
        return error_redirect("/products", "Error al eliminar el producto.")


@router.post("/products/import")
async def products_import(request: Request, file: UploadFile = File(...)):
    if not file.filename or not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        return HTMLResponse("""<div id="import-progress" class="space-y-4 text-center">
            <p class="text-red-600">Solo se permiten archivos Excel (.xlsx o .xls).</p>
            <button onclick="closeModal()" class="px-4 py-2 bg-slate-600 text-white rounded-lg">Cerrar</button>
        </div>""")

    try:
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents))
    except Exception as e:
        return HTMLResponse(f"""<div id="import-progress" class="space-y-4 text-center">
            <p class="text-red-600">No se pudo leer el archivo: {str(e)}.</p>
            <button onclick="closeModal()" class="px-4 py-2 bg-slate-600 text-white rounded-lg">Cerrar</button>
        </div>""")

    column_map = {}
    for col in df.columns:
        col_clean = str(col).strip().upper()
        if col_clean in ("CODIGO_PRO", "CODIGO PRO", "CODIGO-PRO"):
            column_map["sku_china"] = col
        elif col_clean in ("NOMBRE_PRO", "NOMBRE PRO", "NOMBRE-PRO"):
            column_map["name"] = col

    if "sku_china" not in column_map or "name" not in column_map:
        return HTMLResponse("""<div id="import-progress" class="space-y-4 text-center">
            <p class="text-red-600">El Excel debe tener las columnas 'CODIGO_PRO' y 'nombre_pro'.</p>
            <button onclick="closeModal()" class="px-4 py-2 bg-slate-600 text-white rounded-lg">Cerrar</button>
        </div>""")

    rows_data = []
    for _, row in df.iterrows():
        sku_china = str(row[column_map["sku_china"]]).strip() if pd.notna(row[column_map["sku_china"]]) else ""
        name = str(row[column_map["name"]]).strip() if pd.notna(row[column_map["name"]]) else ""
        if sku_china and name:
            rows_data.append({"sku_china": sku_china, "name": name})

    if not rows_data:
        return HTMLResponse("""<div id="import-progress" class="space-y-4 text-center">
            <p class="text-red-600">No se encontraron productos validos en el archivo.</p>
            <button onclick="closeModal()" class="px-4 py-2 bg-slate-600 text-white rounded-lg">Cerrar</button>
        </div>""")

    task_id = str(uuid.uuid4())
    total = len(rows_data)
    set_import_progress(task_id, {
        "status": "processing",
        "current": 0, "total": total, "percent": 0,
        "created": 0, "updated": 0, "skipped": 0,
    })
    threading.Thread(target=run_import, args=(task_id, rows_data), daemon=True).start()
    return HTMLResponse(progress_html(task_id, 0, total, 0, 0, 0, 0, "processing"))


@router.get("/products/import/progress/{task_id}")
async def products_import_progress(task_id: str):
    data = get_import_progress(task_id)
    if not data:
        return HTMLResponse("""<div id="import-progress" class="space-y-4 text-center">
            <p class="text-red-600">Tarea no encontrada.</p>
            <button onclick="closeModal()" class="px-4 py-2 bg-slate-600 text-white rounded-lg">Cerrar</button>
        </div>""")

    status = data["status"]
    if status == "done":
        c, u, s = data["created"], data["updated"], data["skipped"]
        html = progress_html(task_id, data["total"], data["total"], 100, c, u, s, "done")
        pop_import_progress(task_id)
        return HTMLResponse(html)
    elif status == "error":
        msg = data.get("message", "Error desconocido")
        pop_import_progress(task_id)
        return HTMLResponse(f"""<div id="import-progress" class="space-y-4 text-center">
            <p class="text-red-600 font-medium">Error en la importacion</p>
            <p class="text-sm text-slate-600">{msg}</p>
            <button onclick="closeModal()" class="px-4 py-2 bg-slate-600 text-white rounded-lg">Cerrar</button>
        </div>""")
    else:
        return HTMLResponse(progress_html(
            task_id, data["current"], data["total"], data["percent"],
            data["created"], data["updated"], data["skipped"], "processing",
        ))


@router.post("/products/delete-all")
async def products_delete_all(request: Request):
    from sqlalchemy.exc import IntegrityError
    try:
        db = SessionLocal()
        try:
            count = db.query(ProductCatalog).count()
            db.query(ProductCatalog).delete()
            db.commit()
            return success_redirect("/products", f"{count} producto(s) eliminado(s).")
        except IntegrityError:
            db.rollback()
            return error_redirect("/products", "No se pueden eliminar todos los productos: hay referencias a ellos.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Delete all products error: {e}")
        return error_redirect("/products", "Error al eliminar los productos.")


@router.get("/products/search")
async def products_search(request: Request, q: str = ""):
    q = safe_str(q)
    if not q or len(q) < 1:
        return HTMLResponse("")
    search = f"%{q}%"
    try:
        db = SessionLocal()
        try:
            results = db.query(ProductCatalog).filter(
                or_(
                    ProductCatalog.sku_usa.ilike(search),
                    ProductCatalog.sku_china.ilike(search),
                    ProductCatalog.name.ilike(search),
                )
            ).limit(25).all()

            html_parts = ""
            for p in results:
                sku = p.sku_usa or p.sku_china or "-"
                name = p.name
                html_parts += f"""<div class="hover:bg-slate-100 px-3 py-2 cursor-pointer rounded flex justify-between items-center"
                    onclick="selectProduct(this)"
                    data-product-id="{p.id}" data-sku="{html_mod.escape(sku)}" data-name="{html_mod.escape(name)}">
                    <span class="font-medium text-sm truncate flex-1">{html_mod.escape(name)}</span>
                    <span class="text-xs text-slate-400 ml-3 shrink-0">{html_mod.escape(sku)}</span>
                </div>"""
            if not html_parts:
                html_parts = '<div class="text-slate-400 text-sm px-3 py-2">Sin resultados</div>'
            return HTMLResponse(f'<div class="p-1">{html_parts}</div>')
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Product search error: {e}")
        return HTMLResponse('<div class="text-red-600 text-sm px-3 py-2">Error al buscar</div>')
