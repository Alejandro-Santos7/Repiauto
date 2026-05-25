from datetime import datetime, date

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from config import SessionLocal, templates, logger
from models import ProductCatalog, OrderChina, ShippingContainer, Box, BoxItem, Inventory
from utils import safe_str, safe_int, error_redirect, success_redirect

router = APIRouter()


# ==================== ORDERS ====================

@router.get("/imports", response_class=HTMLResponse)
async def imports_list(request: Request):
    try:
        db = SessionLocal()
        try:
            rows = db.query(OrderChina).order_by(OrderChina.created_at.desc()).all()
            result = []
            for o in rows:
                container_count = db.query(ShippingContainer).filter(ShippingContainer.orders_china_id == o.id).count()
                result.append({
                    "id": o.id,
                    "pi_number": o.pi_number or o.invoice_number,
                    "invoice_number": o.invoice_number,
                    "supplier": o.supplier,
                    "status": o.status,
                    "created_date": o.created_date,
                    "created_at": o.created_at,
                    "container_count": container_count,
                })
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Imports error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "No se pudieron cargar las importaciones."})
    return templates.TemplateResponse("imports.html", {"request": request, "orders": result})


@router.post("/imports")
async def imports_create(
    request: Request,
    invoice_number: str = Form(None),
    pi_number: str = Form(None),
    supplier: str = Form(None),
    created_date: str = Form(None),
):
    invoice_number = safe_str(invoice_number)
    pi_number = safe_str(pi_number)
    if not pi_number:
        pi_number = invoice_number
    if not invoice_number:
        return error_redirect("/imports", "El PI NO / Factura es obligatorio.")
    try:
        db = SessionLocal()
        try:
            cdate = datetime.strptime(created_date, "%Y-%m-%d").date() if created_date else date.today()
            o = OrderChina(
                invoice_number=invoice_number,
                pi_number=pi_number,
                supplier=safe_str(supplier) or None,
                created_date=cdate,
                status="open",
            )
            db.add(o)
            db.commit()
            db.refresh(o)
            return success_redirect(f"/imports/{o.id}", "Orden creada correctamente.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/imports", f"El PI NO '{invoice_number}' ya existe.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Order create error: {e}")
        return error_redirect("/imports", "Error al crear la orden.")


@router.get("/imports/{order_id}", response_class=HTMLResponse)
async def import_order_detail(request: Request, order_id: int):
    try:
        db = SessionLocal()
        try:
            o = db.get(OrderChina, order_id)
            if not o:
                return templates.TemplateResponse("error.html", {"request": request, "title": "No encontrado", "message": "Esa orden no existe."}, status_code=404)
            containers = db.query(ShippingContainer).options(
                joinedload(ShippingContainer.boxes)
            ).filter(ShippingContainer.orders_china_id == order_id).order_by(ShippingContainer.created_at.desc()).all()
            container_data = []
            for c in containers:
                container_data.append({
                    "id": c.id, "invoice_number": c.invoice_number, "ref_number": c.ref_number,
                    "bill_number": c.bill_number, "status": c.status, "arrival_date": c.arrival_date,
                    "notes": c.notes, "box_count": len(c.boxes),
                })
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Order detail error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Error al cargar la orden."})
    return templates.TemplateResponse("import_order_detail.html", {"request": request, "order": o, "containers": container_data})


@router.post("/imports/{order_id}/update")
async def import_order_update(
    request: Request, order_id: int,
    invoice_number: str = Form(None), pi_number: str = Form(None),
    supplier: str = Form(None), created_date: str = Form(None),
):
    invoice_number = safe_str(invoice_number)
    pi_number = safe_str(pi_number)
    if not invoice_number:
        return error_redirect(f"/imports/{order_id}", "El PI NO es obligatorio.")
    try:
        db = SessionLocal()
        try:
            o = db.get(OrderChina, order_id)
            if not o:
                return error_redirect("/imports", "Orden no encontrada.")
            o.invoice_number = invoice_number
            o.pi_number = pi_number or invoice_number
            o.supplier = safe_str(supplier) or None
            if created_date:
                o.created_date = datetime.strptime(created_date, "%Y-%m-%d").date()
            db.commit()
            return success_redirect(f"/imports/{order_id}", "Orden actualizada.")
        except IntegrityError:
            db.rollback()
            return error_redirect(f"/imports/{order_id}", "Ese PI NO ya existe.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Order update error: {e}")
        return error_redirect(f"/imports/{order_id}", "Error al actualizar.")


@router.post("/imports/{order_id}/close")
async def import_order_close(request: Request, order_id: int):
    try:
        db = SessionLocal()
        try:
            o = db.get(OrderChina, order_id)
            if not o:
                return error_redirect("/imports", "Orden no encontrada.")
            o.status = "closed"
            db.commit()
            return success_redirect(f"/imports/{order_id}", "Orden cerrada. No se pueden agregar mas contenedores.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Order close error: {e}")
        return error_redirect(f"/imports/{order_id}", "Error al cerrar la orden.")


@router.post("/imports/{order_id}/open")
async def import_order_open(request: Request, order_id: int):
    try:
        db = SessionLocal()
        try:
            o = db.get(OrderChina, order_id)
            if not o:
                return error_redirect("/imports", "Orden no encontrada.")
            o.status = "open"
            db.commit()
            return success_redirect(f"/imports/{order_id}", "Orden reabierta.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Order open error: {e}")
        return error_redirect(f"/imports/{order_id}", "Error al reabrir la orden.")


@router.post("/imports/{order_id}/delete")
async def import_order_delete(request: Request, order_id: int):
    try:
        db = SessionLocal()
        try:
            o = db.get(OrderChina, order_id)
            if not o:
                return error_redirect("/imports", "Orden no encontrada.")
            db.delete(o)
            db.commit()
            return success_redirect("/imports", "Orden eliminada.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/imports", "No se puede eliminar: tiene contenedores asociados.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Order delete error: {e}")
        return error_redirect("/imports", "Error al eliminar.")


# ==================== CONTAINERS ====================

@router.post("/imports/{order_id}/containers")
async def import_container_create(
    request: Request, order_id: int,
    invoice_number: str = Form(None), ref_number: str = Form(None),
    bill_number: str = Form(None), arrival_date: str = Form(None),
    created_date: str = Form(None), notes: str = Form(None),
):
    invoice_number = safe_str(invoice_number)
    ref_number = safe_str(ref_number)
    if not invoice_number:
        return error_redirect(f"/imports/{order_id}", "El numero de factura (Invoice No) es obligatorio.")
    try:
        db = SessionLocal()
        try:
            o = db.get(OrderChina, order_id)
            if not o:
                return error_redirect("/imports", "Orden no encontrada.")
            if o.status == "closed":
                return error_redirect(f"/imports/{order_id}", "La orden esta cerrada. Reabrela para agregar contenedores.")
            arrival = datetime.fromisoformat(arrival_date) if arrival_date else None
            cdate = datetime.strptime(created_date, "%Y-%m-%d").date() if created_date else date.today()
            c = ShippingContainer(
                invoice_number=invoice_number, ref_number=ref_number,
                bill_number=safe_str(bill_number) or None, orders_china_id=order_id,
                arrival_date=arrival, created_date=cdate, notes=safe_str(notes), status="pending",
            )
            db.add(c)
            db.commit()
            db.refresh(c)
            return success_redirect(f"/imports/{order_id}/containers/{c.id}", "Contenedor creado correctamente.")
        except IntegrityError:
            db.rollback()
            return error_redirect(f"/imports/{order_id}", f"El numero de factura '{invoice_number}' ya existe.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container create error: {e}")
        return error_redirect(f"/imports/{order_id}", "Error al crear el contenedor.")


@router.get("/imports/{order_id}/containers/{container_id}", response_class=HTMLResponse)
async def import_container_detail(request: Request, order_id: int, container_id: int):
    try:
        db = SessionLocal()
        try:
            o = db.get(OrderChina, order_id)
            if not o:
                return templates.TemplateResponse("error.html", {"request": request, "title": "No encontrado", "message": "Esa orden no existe."}, status_code=404)
            c = db.get(ShippingContainer, container_id)
            if not c or c.orders_china_id != order_id:
                return templates.TemplateResponse("error.html", {"request": request, "title": "No encontrado", "message": "Ese contenedor no existe."}, status_code=404)
            c.order_china
            boxes_raw = db.query(Box).options(joinedload(Box.items).joinedload(BoxItem.product)).filter(Box.container_id == container_id).order_by(Box.box_number).all()
            boxes = []
            for b in boxes_raw:
                items = []
                for i in b.items:
                    items.append({"id": i.id, "quantity": i.quantity, "product_sku_usa": i.product.sku_usa if i.product else "", "product_name": i.product.name if i.product else ""})
                boxes.append({"id": b.id, "box_number": b.box_number, "lpn_code": b.lpn_code, "status": b.status, "product_list": items})
            products_raw = db.query(ProductCatalog).limit(50).all()
            products = [{"id": p.id, "sku_usa": p.sku_usa, "name": p.name} for p in products_raw]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container detail error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Error al cargar el contenedor."})
    return templates.TemplateResponse("import_container_detail.html", {
        "request": request, "order": o, "container": c, "boxes": boxes, "products": products,
    })


@router.post("/imports/{order_id}/containers/{container_id}/update")
async def import_container_update(
    request: Request, order_id: int, container_id: int,
    invoice_number: str = Form(None), ref_number: str = Form(None),
    bill_number: str = Form(None), arrival_date: str = Form(None),
    created_date: str = Form(None), notes: str = Form(None),
):
    invoice_number = safe_str(invoice_number)
    if not invoice_number:
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "El numero de factura es obligatorio.")
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c or c.orders_china_id != order_id:
                return error_redirect(f"/imports/{order_id}", "Contenedor no encontrado.")
            c.invoice_number = invoice_number
            c.ref_number = safe_str(ref_number) or None
            c.bill_number = safe_str(bill_number) or None
            c.arrival_date = datetime.fromisoformat(arrival_date) if arrival_date else None
            if created_date:
                c.created_date = datetime.strptime(created_date, "%Y-%m-%d").date()
            c.notes = safe_str(notes)
            db.commit()
            return success_redirect(f"/imports/{order_id}/containers/{container_id}", "Contenedor actualizado.")
        except IntegrityError:
            db.rollback()
            return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Ese numero de factura ya existe.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container update error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al actualizar el contenedor.")


@router.post("/imports/{order_id}/containers/{container_id}/status")
async def import_container_status(request: Request, order_id: int, container_id: int, status: str = Form(None)):
    if status not in ("pending", "arrived", "completed"):
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Estado no valido.")
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c or c.orders_china_id != order_id:
                return error_redirect(f"/imports/{order_id}", "Contenedor no encontrado.")
            c.status = status
            db.commit()
            return success_redirect(f"/imports/{order_id}/containers/{container_id}", f"Estado cambiado a '{status}'.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container status error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al cambiar estado.")


@router.post("/imports/{order_id}/containers/{container_id}/close")
async def import_container_close(request: Request, order_id: int, container_id: int):
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c or c.orders_china_id != order_id:
                return error_redirect(f"/imports/{order_id}", "Contenedor no encontrado.")
            c.status = "completed"
            for box in db.query(Box).filter(Box.container_id == container_id).all():
                box.status = "closed"
            db.commit()
            return success_redirect(f"/imports/{order_id}/containers/{container_id}", "Contenedor cerrado. No se pueden agregar mas cajas.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container close error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al cerrar el contenedor.")


@router.post("/imports/{order_id}/containers/{container_id}/open")
async def import_container_open(request: Request, order_id: int, container_id: int):
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c or c.orders_china_id != order_id:
                return error_redirect(f"/imports/{order_id}", "Contenedor no encontrado.")
            if c.status == "completed":
                c.status = "arrived"
            for box in db.query(Box).filter(Box.container_id == container_id, Box.status == "closed").all():
                box.status = "pending"
            db.commit()
            return success_redirect(f"/imports/{order_id}/containers/{container_id}", "Contenedor reabierto.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container open error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al reabrir el contenedor.")


@router.post("/imports/{order_id}/containers/{container_id}/delete")
async def import_container_delete(request: Request, order_id: int, container_id: int):
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c or c.orders_china_id != order_id:
                return error_redirect(f"/imports/{order_id}", "Contenedor no encontrado.")
            db.delete(c)
            db.commit()
            return success_redirect(f"/imports/{order_id}", "Contenedor eliminado.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container delete error: {e}")
        return error_redirect(f"/imports/{order_id}", "Error al eliminar el contenedor.")


@router.post("/imports/{order_id}/containers/{container_id}/finalize")
async def import_container_finalize(request: Request, order_id: int, container_id: int):
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c or c.orders_china_id != order_id:
                return error_redirect(f"/imports/{order_id}", "Contenedor no encontrado.")
            if c.status == "completed":
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "El contenedor ya esta completado.")
            count = 0
            for box in db.query(Box).filter(Box.container_id == container_id).all():
                if db.query(BoxItem).filter(BoxItem.box_id == box.id).count() == 0:
                    continue
                box.status = "to_locate"
                if not db.query(Inventory).filter(Inventory.box_id == box.id).first():
                    db.add(Inventory(box_id=box.id, status="pending_location"))
                count += 1
            c.status = "completed"
            db.commit()
            return success_redirect(f"/imports/{order_id}/containers/{container_id}", f"{count} caja(s) enviadas a inventario.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Finalize error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al finalizar.")


# ==================== BOXES ====================

@router.post("/imports/{order_id}/containers/{container_id}/boxes")
async def import_box_create(request: Request, order_id: int, container_id: int, box_number: int = Form(None)):
    box_number = safe_int(box_number)
    if not box_number or box_number < 1:
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "El numero de caja debe ser 1 o mayor.")
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c or c.orders_china_id != order_id:
                return error_redirect(f"/imports/{order_id}", "Contenedor no encontrado.")
            if c.status == "completed":
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "El contenedor esta cerrado. Reabrelo para agregar cajas.")
            invoice_last4 = c.invoice_number[-4:] if c.invoice_number and len(c.invoice_number) >= 4 else c.invoice_number
            lpn_code = f"{invoice_last4}-{box_number:02d}"
            if db.query(Box).filter(Box.lpn_code == lpn_code).first():
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", f"El LPN '{lpn_code}' ya existe.")
            db.add(Box(container_id=container_id, box_number=box_number, lpn_code=lpn_code))
            db.commit()
            return success_redirect(f"/imports/{order_id}/containers/{container_id}", f"Caja {lpn_code} creada.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box create error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al crear la caja.")


@router.post("/imports/{order_id}/containers/{container_id}/boxes/{box_id}/update")
async def import_box_update(request: Request, order_id: int, container_id: int, box_id: int, box_number: int = Form(None)):
    box_number = safe_int(box_number)
    if not box_number or box_number < 1:
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "El numero de caja debe ser 1 o mayor.")
    try:
        db = SessionLocal()
        try:
            b = db.query(Box).filter(Box.id == box_id, Box.container_id == container_id).first()
            if not b:
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Caja no encontrada.")
            if b.status in ("to_locate", "located"):
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "No se puede editar una caja enviada a inventario.")
            c = b.container
            invoice_last4 = c.invoice_number[-4:] if c and c.invoice_number and len(c.invoice_number) >= 4 else "XXXX"
            new_lpn = f"{invoice_last4}-{box_number:02d}"
            if db.query(Box).filter(Box.lpn_code == new_lpn, Box.id != box_id).first():
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", f"El LPN '{new_lpn}' ya esta en uso.")
            b.box_number = box_number
            b.lpn_code = new_lpn
            db.commit()
            return success_redirect(f"/imports/{order_id}/containers/{container_id}", "Caja actualizada.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box update error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al actualizar la caja.")


@router.post("/imports/{order_id}/containers/{container_id}/boxes/{box_id}/close")
async def import_box_close(request: Request, order_id: int, container_id: int, box_id: int):
    try:
        db = SessionLocal()
        try:
            b = db.query(Box).filter(Box.id == box_id, Box.container_id == container_id).first()
            if not b:
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Caja no encontrada.")
            b.status = "closed"
            db.commit()
            return success_redirect(f"/imports/{order_id}/containers/{container_id}", "Caja cerrada. No se pueden agregar mas productos.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box close error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al cerrar la caja.")


@router.post("/imports/{order_id}/containers/{container_id}/boxes/{box_id}/open")
async def import_box_open(request: Request, order_id: int, container_id: int, box_id: int):
    try:
        db = SessionLocal()
        try:
            b = db.query(Box).filter(Box.id == box_id, Box.container_id == container_id).first()
            if not b:
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Caja no encontrada.")
            if b.status in ("to_locate", "located"):
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "No se puede reabrir una caja que ya fue enviada a inventario.")
            b.status = "pending"
            db.commit()
            return success_redirect(f"/imports/{order_id}/containers/{container_id}", "Caja reabierta.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box open error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al reabrir la caja.")


@router.post("/imports/{order_id}/containers/{container_id}/boxes/{box_id}/delete")
async def import_box_delete(request: Request, order_id: int, container_id: int, box_id: int):
    try:
        db = SessionLocal()
        try:
            b = db.query(Box).filter(Box.id == box_id, Box.container_id == container_id).first()
            if not b:
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Caja no encontrada.")
            if b.status in ("to_locate", "located", "closed"):
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "No se puede eliminar una caja cerrada o en inventario.")
            db.delete(b)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box delete error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al eliminar la caja.")
    return success_redirect(f"/imports/{order_id}/containers/{container_id}", "Caja eliminada.")


# ==================== BOX ITEMS ====================

@router.post("/imports/{order_id}/containers/{container_id}/boxes/{box_id}/items")
async def import_box_items_create(
    request: Request, order_id: int, container_id: int, box_id: int,
    product_id: int = Form(None), quantity: int = Form(None),
):
    product_id = safe_int(product_id)
    quantity = safe_int(quantity)
    if not product_id:
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Selecciona un producto.")
    if not quantity or quantity < 1:
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "La cantidad debe ser 1 o mayor.")
    try:
        db = SessionLocal()
        try:
            b = db.query(Box).filter(Box.id == box_id, Box.container_id == container_id).first()
            if not b:
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Caja no encontrada en este contenedor.")
            if b.status == "closed":
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "La caja esta cerrada. Reabrela para agregar productos.")
            if b.status in ("to_locate", "located"):
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "La caja ya fue enviada a inventario.")
            p = db.get(ProductCatalog, product_id)
            if not p:
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Producto no encontrado.")
            db.add(BoxItem(box_id=box_id, product_id=product_id, quantity=quantity))
            db.commit()
            return success_redirect(f"/imports/{order_id}/containers/{container_id}", "Producto agregado a la caja.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box item create error: {e}")
        return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Error al agregar el producto.")


@router.post("/imports/{order_id}/containers/{container_id}/boxes/{box_id}/items/{item_id}/delete")
async def import_box_items_delete(request: Request, order_id: int, container_id: int, box_id: int, item_id: int):
    try:
        db = SessionLocal()
        try:
            box = db.query(Box).filter(Box.id == box_id, Box.container_id == container_id).first()
            if not box:
                return error_redirect(f"/imports/{order_id}/containers/{container_id}", "Caja no encontrada.")
            item = db.get(BoxItem, item_id)
            if item:
                db.delete(item)
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box item delete error: {e}")
    return success_redirect(f"/imports/{order_id}/containers/{container_id}", "Producto eliminado de la caja.")


# ==================== LABEL PRINTING ====================

@router.get("/imports/{order_id}/containers/{container_id}/print-labels", response_class=HTMLResponse)
async def print_container_labels(request: Request, order_id: int, container_id: int):
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c or c.orders_china_id != order_id:
                return templates.TemplateResponse("error.html", {"request": request, "title": "No encontrado", "message": "Contenedor no encontrado."}, status_code=404)
            o = db.get(OrderChina, order_id)
            boxes = db.query(Box).options(joinedload(Box.items).joinedload(BoxItem.product)).filter(Box.container_id == container_id).order_by(Box.box_number).all()
            box_data = []
            for b in boxes:
                items = [{"name": i.product.name if i.product else "?", "qty": i.quantity} for i in b.items]
                box_data.append({"lpn": b.lpn_code, "number": b.box_number, "status": b.status, "products": items})
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Print labels error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Error al cargar etiquetas."})
    return templates.TemplateResponse("label_print.html", {
        "request": request, "order_pi": o.pi_number or o.invoice_number if o else "?",
        "container_invoice": c.invoice_number, "container_ref": c.ref_number, "boxes": box_data,
    })


@router.get("/imports/{order_id}/containers/{container_id}/boxes/{box_id}/print-label", response_class=HTMLResponse)
async def print_box_label(request: Request, order_id: int, container_id: int, box_id: int):
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c or c.orders_china_id != order_id:
                return templates.TemplateResponse("error.html", {"request": request, "title": "No encontrado", "message": "Contenedor no encontrado."}, status_code=404)
            o = db.get(OrderChina, order_id)
            b = db.query(Box).options(joinedload(Box.items).joinedload(BoxItem.product)).filter(Box.id == box_id, Box.container_id == container_id).first()
            if not b:
                return templates.TemplateResponse("error.html", {"request": request, "title": "No encontrado", "message": "Caja no encontrada."}, status_code=404)
            items = [{"name": i.product.name if i.product else "?", "qty": i.quantity} for i in b.items]
            box_data = [{"lpn": b.lpn_code, "number": b.box_number, "status": b.status, "products": items}]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Print label error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Error al cargar etiqueta."})
    return templates.TemplateResponse("label_print.html", {
        "request": request, "order_pi": o.pi_number or o.invoice_number if o else "?",
        "container_invoice": c.invoice_number, "container_ref": c.ref_number, "boxes": box_data,
    })
