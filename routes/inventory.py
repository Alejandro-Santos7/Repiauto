from datetime import datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from config import SessionLocal, templates, logger
from models import ProductCatalog, ShippingContainer, Box, BoxItem, Location, Inventory
from utils import safe_str, safe_int, error_redirect, success_redirect

router = APIRouter()


@router.get("/inventory", response_class=HTMLResponse)
async def inventory(request: Request, q: str = ""):
    q = safe_str(q)
    try:
        db = SessionLocal()
        try:
            query = db.query(Inventory).options(
                joinedload(Inventory.box).joinedload(Box.container),
                joinedload(Inventory.box).joinedload(Box.items).joinedload(BoxItem.product),
                joinedload(Inventory.location)
            )

            if q:
                search = f"%{q}%"
                matching_ids = (
                    db.query(Inventory.id)
                    .join(Box, Inventory.box_id == Box.id)
                    .join(ShippingContainer, Box.container_id == ShippingContainer.id)
                    .outerjoin(Location, Inventory.location_id == Location.id)
                    .outerjoin(BoxItem, BoxItem.box_id == Box.id)
                    .outerjoin(ProductCatalog, BoxItem.product_id == ProductCatalog.id)
                    .filter(or_(
                        Box.lpn_code.ilike(search),
                        ShippingContainer.invoice_number.ilike(search),
                        ProductCatalog.sku_usa.ilike(search),
                        ProductCatalog.sku_china.ilike(search),
                        ProductCatalog.name.ilike(search),
                        Location.full_code.ilike(search),
                    ))
                    .distinct()
                    .subquery()
                )
                query = query.filter(Inventory.id.in_(matching_ids))

            rows = query.limit(50).all()
            items = []
            for r in rows:
                box = r.box
                products_list = []
                if box:
                    for i in box.items:
                        if i.product:
                            products_list.append((i.product.sku_usa, i.quantity))
                items.append({
                    "id": r.id, "box_id": r.box_id, "location_id": r.location_id,
                    "status": r.status,
                    "box_lpn": box.lpn_code if box else "?",
                    "container_invoice": box.container.invoice_number if box and box.container else "?",
                    "products": products_list,
                    "location_code": r.location.full_code if r.location else None,
                })
            locs = db.query(Location).all()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Inventory error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Error al cargar el inventario."})
    return templates.TemplateResponse("inventory.html", {"request": request, "items": items, "locations": locs, "query": q})


@router.post("/inventory/{inventory_id}/assign")
async def inventory_assign(request: Request, inventory_id: int, location_id: int = Form(None)):
    location_id = safe_int(location_id)
    if not location_id:
        return error_redirect("/inventory", "Selecciona una ubicacion.")
    try:
        db = SessionLocal()
        try:
            loc = db.get(Location, location_id)
            if not loc:
                return error_redirect("/inventory", "Ubicacion no encontrada.")
            inv = db.get(Inventory, inventory_id)
            if not inv:
                return error_redirect("/inventory", "Item de inventario no encontrado.")
            inv.location_id = location_id
            inv.status = "stored"
            inv.moved_at = datetime.utcnow()
            box = db.get(Box, inv.box_id)
            if box:
                box.status = "located"
            db.commit()
            return success_redirect("/inventory", f"Ubicacion {loc.full_code} asignada.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Inventory assign error: {e}")
        return error_redirect("/inventory", "Error al asignar ubicacion.")
