from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import joinedload
from datetime import datetime

from config import SessionLocal, templates, logger
from models import Location, Inventory, Box, BoxItem, ProductCatalog, ShippingContainer
from utils import safe_str, safe_int

router = APIRouter()


def _rack_data(location):
    used = location.inventories if hasattr(location, 'inventories') and location.inventories else 0
    if isinstance(used, list):
        used = len(used)
    return {
        "id": location.id,
        "full_code": location.full_code,
        "custom_name": location.custom_name,
        "display_name": location.custom_name or location.full_code,
        "capacity": location.capacity,
        "used_capacity": used,
    }


def _get_rack_glasses(location_id, db):
    glasses = []
    inventories = db.query(Inventory).filter(Inventory.location_id == location_id).all()
    for inv in inventories:
        box = db.query(Box).options(joinedload(Box.items).joinedload(BoxItem.product)).filter(Box.id == inv.box_id).first()
        if box:
            for item in box.items:
                glasses.append({
                    "id": item.id,
                    "sku_usa": item.product.sku_usa,
                    "name": item.product.name,
                    "quantity": item.quantity,
                    "rack_id": location_id,
                })
    return glasses


@router.get("/warehouse", response_class=HTMLResponse)
async def warehouse_page(request: Request):
    return templates.TemplateResponse("warehouse/index.html", {"request": request})


@router.get("/warehouse/selector", response_class=HTMLResponse)
async def warehouse_selector(request: Request):
    return templates.TemplateResponse("warehouse/selector.html", {"request": request})


@router.get("/warehouse/1", response_class=HTMLResponse)
async def warehouse_1(request: Request):
    try:
        db = SessionLocal()
        try:
            locs = db.query(Location).filter(
                Location.warehouse_id == 1,
                Location.full_code.like("%1-P1-%")
            ).all()
            racks = [_rack_data(loc) for loc in locs]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Warehouse 1 error: {e}")
        racks = []
    return templates.TemplateResponse("warehouse/page_1.html", {"request": request, "floor": 1, "racks": racks})


@router.get("/warehouse/2", response_class=HTMLResponse)
async def warehouse_2(request: Request):
    cells = {}
    try:
        db = SessionLocal()
        try:
            locs = db.query(Location).filter(Location.warehouse_id == 2).all()
            for loc in locs:
                parts = loc.full_code.split("-")
                if len(parts) >= 3:
                    prefix = f"2-{parts[1]}-{parts[2]}"
                    invs = db.query(Inventory).filter(Inventory.location_id == loc.id).all()
                    count = len(invs)
                    if prefix not in cells:
                        cells[prefix] = {"has_items": False, "label": f"{parts[1]}-{parts[2]}", "count": 0}
                    if count > 0:
                        cells[prefix]["has_items"] = True
                        cells[prefix]["count"] += count
                        cells[prefix]["label"] = loc.custom_name or f"{parts[1]}-{parts[2]}"
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Warehouse 2 error: {e}")
    return templates.TemplateResponse("warehouse/page_2.html", {"request": request, "cells": cells})


@router.get("/warehouse/1/floor/{floor_num}", response_class=HTMLResponse)
async def warehouse_1_floor(request: Request, floor_num: int):
    try:
        db = SessionLocal()
        try:
            pattern = f"%1-P{floor_num}-%"
            locs = db.query(Location).filter(
                Location.warehouse_id == 1,
                Location.full_code.like(pattern)
            ).all()
            racks = [_rack_data(loc) for loc in locs]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Floor {floor_num} error: {e}")
        racks = []
    return templates.TemplateResponse("warehouse/_racks_grid.html", {"request": request, "racks": racks})


@router.get("/warehouse/1/rack/{location_id}", response_class=HTMLResponse)
async def rack_detail(request: Request, location_id: int):
    try:
        db = SessionLocal()
        try:
            loc = db.query(Location).filter(Location.id == location_id).first()
            if not loc:
                return HTMLResponse("<p class='text-red-500 p-4'>Rack no encontrado</p>")
            rack = _rack_data(loc)
            glasses = _get_rack_glasses(location_id, db)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Rack detail error: {e}")
        return HTMLResponse(f"<p class='text-red-500 p-4'>Error: {e}</p>")
    return templates.TemplateResponse("warehouse/_rack_detail.html", {"request": request, "rack": rack, "glasses": glasses, "g": {"id": 0, "quantity": 1}})


@router.post("/warehouse/1/rack/{location_id}/update-name", response_class=HTMLResponse)
async def rack_update_name(request: Request, location_id: int, custom_name: str = Form(None)):
    name = safe_str(custom_name)
    try:
        db = SessionLocal()
        try:
            loc = db.query(Location).filter(Location.id == location_id).first()
            if loc:
                loc.custom_name = name or None
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Update rack name error: {e}")
    return HTMLResponse("<span class='text-green-600'>✓ Guardado</span>")


@router.post("/warehouse/1/rack/{location_id}/update-code", response_class=HTMLResponse)
async def rack_update_code(request: Request, location_id: int, full_code: str = Form(None)):
    code = safe_str(full_code)
    if not code:
        return HTMLResponse("<span class='text-red-500'>Código obligatorio</span>")
    try:
        db = SessionLocal()
        try:
            loc = db.query(Location).filter(Location.id == location_id).first()
            if loc:
                existing = db.query(Location).filter(Location.full_code == code, Location.id != location_id).first()
                if existing:
                    return HTMLResponse("<span class='text-red-500'>Código duplicado</span>")
                loc.full_code = code
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Update rack code error: {e}")
        return HTMLResponse("<span class='text-red-500'>Error al guardar</span>")
    return HTMLResponse("<span class='text-green-600'>✓ Guardado</span>")


@router.post("/warehouse/1/glass/{item_id}/sell", response_class=HTMLResponse)
async def glass_sell(request: Request, item_id: int, qty: int = Form(None)):
    qty = safe_int(qty, 1)
    try:
        db = SessionLocal()
        try:
            item = db.query(BoxItem).options(joinedload(BoxItem.box).joinedload(Box.inventory)).filter(BoxItem.id == item_id).first()
            if item:
                if item.quantity <= qty:
                    db.delete(item)
                else:
                    item.quantity -= qty
                db.commit()
                location_id = item.box.inventory.location_id if item.box.inventory else None
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Sell glass error: {e}")
        return HTMLResponse("<p class='text-red-500 p-4'>Error al vender</p>")
    if location_id:
        return await rack_detail(request, location_id)
    return HTMLResponse("<p class='text-slate-400 p-4'>Vendido. Recarga para ver cambios.</p>")


@router.post("/warehouse/1/glass/{item_id}/move-form", response_class=HTMLResponse)
async def glass_move_form(request: Request, item_id: int, qty: int = Form(None)):
    qty = safe_int(qty, 1)
    g = {"id": item_id, "quantity": qty}
    return templates.TemplateResponse("warehouse/_destination_search.html", {"request": request, "g": g, "results": []})


@router.post("/warehouse/1/glass/{item_id}/move", response_class=HTMLResponse)
async def glass_move(request: Request, item_id: int, dest_id: int = Form(None), qty: int = Form(None)):
    qty = safe_int(qty, 1)
    if not dest_id:
        return HTMLResponse("<p class='text-red-500 p-4'>Selecciona un destino</p>")
    try:
        db = SessionLocal()
        try:
            item = db.query(BoxItem).options(
                joinedload(BoxItem.box).joinedload(Box.inventory),
                joinedload(BoxItem.box).joinedload(Box.container)
            ).filter(BoxItem.id == item_id).first()
            if not item:
                return HTMLResponse("<p class='text-red-500 p-4'>Vidrio no encontrado</p>")

            location_id = item.box.inventory.location_id if item.box.inventory else None
            source_container_id = item.box.container_id

            dest_inv = db.query(Inventory).filter(Inventory.location_id == dest_id).first()
            if dest_inv:
                dest_box = dest_inv.box
            else:
                max_bn = db.query(Box.box_number).filter(
                    Box.container_id == source_container_id
                ).order_by(Box.box_number.desc()).first()
                next_num = (max_bn[0] + 1) if max_bn else 1
                container = db.query(ShippingContainer).filter(ShippingContainer.id == source_container_id).first()
                inv_suffix = container.invoice_number[-4:] if container and container.invoice_number else "0000"
                dest_box = Box(
                    container_id=source_container_id,
                    box_number=next_num,
                    lpn_code=f"{inv_suffix}-{next_num:02d}",
                    status="pending"
                )
                db.add(dest_box)
                db.flush()
                new_inv = Inventory(box_id=dest_box.id, location_id=dest_id, status="pending_location")
                db.add(new_inv)
                db.flush()

            if item.quantity <= qty:
                item.box_id = dest_box.id
            else:
                item.quantity -= qty
                new_item = BoxItem(box_id=dest_box.id, product_id=item.product_id, quantity=qty)
                db.add(new_item)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Move glass error: {e}")
        return HTMLResponse(f"<p class='text-red-500 p-4'>Error al mover</p>")
    if location_id:
        return await rack_detail(request, location_id)
    return HTMLResponse("<p class='text-green-600 p-4'>Movido correctamente</p>")


@router.post("/warehouse/1/glass/{item_id}/delete", response_class=HTMLResponse)
async def glass_delete(request: Request, item_id: int):
    try:
        db = SessionLocal()
        try:
            item = db.query(BoxItem).options(joinedload(BoxItem.box).joinedload(Box.inventory)).filter(BoxItem.id == item_id).first()
            location_id = None
            if item:
                location_id = item.box.inventory.location_id if item.box.inventory else None
                db.delete(item)
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Delete glass error: {e}")
        return HTMLResponse("<p class='text-red-500 p-4'>Error al eliminar</p>")
    if location_id:
        return await rack_detail(request, location_id)
    return HTMLResponse("<p class='text-slate-400 p-4'>Eliminado</p>")


@router.get("/warehouse/1/destinations/search", response_class=HTMLResponse)
async def destination_search(request: Request, q: str = "", item_id: int = None, qty: int = None):
    q = safe_str(q)
    item_id = safe_int(item_id)
    qty = safe_int(qty, 1)
    g = {"id": item_id, "quantity": qty}
    results = []
    if q:
        try:
            db = SessionLocal()
            try:
                from sqlalchemy import or_
                search = f"%{q}%"
                locs = db.query(Location).filter(
                    or_(
                        Location.full_code.ilike(search),
                        Location.custom_name.ilike(search)
                    )
                ).limit(10).all()
                for loc in locs:
                    invs = db.query(Inventory).filter(Inventory.location_id == loc.id).all()
                    results.append({
                        "id": loc.id,
                        "display_name": loc.custom_name or loc.full_code,
                        "full_code": loc.full_code,
                        "capacity": loc.capacity,
                        "used": len(invs),
                    })
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Destination search error: {e}")
    return templates.TemplateResponse("warehouse/_destination_results.html", {"request": request, "g": g, "results": results})


@router.get("/warehouse/2/cell/{row}/{col}", response_class=HTMLResponse)
async def cell_detail(request: Request, row: str, col: int):
    levels = []
    try:
        db = SessionLocal()
        try:
            for level in range(1, 5):
                code = f"2-{row}-{col:02d}-{level}"
                loc = db.query(Location).filter(Location.full_code == code).first()
                box_data = None
                if loc:
                    inv = db.query(Inventory).options(joinedload(Inventory.box)).filter(Inventory.location_id == loc.id).first()
                    if inv and inv.box:
                        box_data = {"id": inv.box.id, "lpn_code": inv.box.lpn_code}
                levels.append({"num": level, "box": box_data, "location_code": code})
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Cell detail error: {e}")
    return templates.TemplateResponse("warehouse/_cell_detail.html", {"request": request, "row": row, "col": col, "levels": levels})


@router.get("/warehouse/2/box/{box_id}", response_class=HTMLResponse)
async def box_contents(request: Request, box_id: int):
    try:
        db = SessionLocal()
        try:
            box = db.query(Box).filter(Box.id == box_id).first()
            if not box:
                return HTMLResponse("<p class='text-red-500 p-4'>Caja no encontrada</p>")

            inv = db.query(Inventory).filter(Inventory.box_id == box.id).first()
            loc_code = None
            if inv and inv.location_id:
                loc = db.query(Location).filter(Location.id == inv.location_id).first()
                loc_code = loc.custom_name or loc.full_code if loc else None

            box_data = {
                "lpn_code": box.lpn_code,
                "location_code": loc_code,
            }

            items = []
            for item in box.items:
                items.append({
                    "sku_usa": item.product.sku_usa,
                    "name": item.product.name,
                    "quantity": item.quantity,
                })
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box contents error: {e}")
        return HTMLResponse(f"<p class='text-red-500 p-4'>Error: {e}</p>")

    return templates.TemplateResponse("warehouse/_box_contents.html", {"request": request, "box": box_data, "items": items})


@router.get("/warehouse/unassigned", response_class=HTMLResponse)
async def unassigned_items(request: Request):
    try:
        db = SessionLocal()
        try:
            invs = db.query(Inventory).filter(
                Inventory.location_id.is_(None),
                Inventory.status == "pending_location"
            ).options(
                joinedload(Inventory.box).joinedload(Box.items).joinedload(BoxItem.product),
                joinedload(Inventory.box).joinedload(Box.container).joinedload(ShippingContainer.order_china)
            ).all()

            items = []
            for inv in invs:
                products = []
                for bi in inv.box.items:
                    products.append((bi.product.sku_usa, bi.quantity))
                items.append({
                    "id": inv.id,
                    "box_lpn": inv.box.lpn_code,
                    "container_invoice": inv.box.container.invoice_number if inv.box.container else "?",
                    "products": products,
                })

            locs = db.query(Location).all()
            locations = [{"id": loc.id, "display_name": loc.custom_name or loc.full_code} for loc in locs]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Unassigned error: {e}")
        items = []
        locations = []
    return templates.TemplateResponse("warehouse/_unassigned.html", {"request": request, "items": items, "locations": locations})


@router.post("/warehouse/unassigned/{inventory_id}/assign", response_class=HTMLResponse)
async def assign_inventory(request: Request, inventory_id: int, location_id: int = Form(None)):
    if not location_id:
        return HTMLResponse("<p class='text-red-500 p-4'>Selecciona una ubicación</p>")
    try:
        db = SessionLocal()
        try:
            inv = db.query(Inventory).filter(Inventory.id == inventory_id).first()
            if inv:
                inv.location_id = location_id
                inv.status = "stored"
                inv.moved_at = datetime.utcnow()
                box = db.query(Box).filter(Box.id == inv.box_id).first()
                if box:
                    box.status = "located"
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Assign inventory error: {e}")
        return HTMLResponse(f"<p class='text-red-500 p-4'>Error al asignar</p>")
    return await unassigned_items(request)
