import os
import traceback
import logging
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, relationship, joinedload
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import IntegrityError, OperationalError, DataError, SQLAlchemyError
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repiauto")

# ==================== HELPERS ====================

def error_redirect(url: str, message: str):
    if "?" in url:
        return RedirectResponse(url=f"{url}&error={quote(message)}", status_code=303)
    return RedirectResponse(url=f"{url}?error={quote(message)}", status_code=303)

def success_redirect(url: str, message: str):
    if "?" in url:
        return RedirectResponse(url=f"{url}&success={quote(message)}", status_code=303)
    return RedirectResponse(url=f"{url}?success={quote(message)}", status_code=303)

def safe_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def safe_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()

from urllib.parse import quote

# ==================== DB SETUP ====================

class Base(DeclarativeBase):
    pass

class ContainerStatus:
    PENDING = "pending"
    ARRIVED = "arrived"
    COMPLETED = "completed"

class BoxStatus:
    PENDING = "pending"
    IN_INVENTORY = "in_inventory"

# ==================== MODELOS ====================

class ProductCatalog(Base):
    __tablename__ = "product_catalog"
    id = mapped_column(Integer, primary_key=True)
    sku_usa = mapped_column(String(50), index=True)
    sku_china = mapped_column(String(50), index=True, nullable=True)
    name = mapped_column(String(200))
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    box_items = relationship("BoxItem", back_populates="product")

class ShippingContainer(Base):
    __tablename__ = "shipping_containers"
    id = mapped_column(Integer, primary_key=True)
    invoice_number = mapped_column(String(100), unique=True, index=True)
    arrival_date = mapped_column(DateTime, nullable=True)
    status = mapped_column(String(20), default=ContainerStatus.PENDING)
    notes = mapped_column(String(500), nullable=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    orders = relationship("Order", back_populates="container", cascade="all, delete-orphan")

class Order(Base):
    __tablename__ = "orders"
    id = mapped_column(Integer, primary_key=True)
    container_id = mapped_column(ForeignKey("shipping_containers.id", ondelete="CASCADE"))
    invoice_number = mapped_column(String(100))
    supplier = mapped_column(String(200), nullable=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    container = relationship("ShippingContainer", back_populates="orders")
    boxes = relationship("Box", back_populates="order", cascade="all, delete-orphan")

class Box(Base):
    __tablename__ = "boxes"
    id = mapped_column(Integer, primary_key=True)
    order_id = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    box_number = mapped_column(Integer)
    lpn_code = mapped_column(String(50), unique=True)
    status = mapped_column(String(20), default=BoxStatus.PENDING)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    order = relationship("Order", back_populates="boxes")
    items = relationship("BoxItem", back_populates="box", cascade="all, delete-orphan")
    inventory = relationship("Inventory", back_populates="box", uselist=False, cascade="all, delete-orphan")

class BoxItem(Base):
    __tablename__ = "box_items"
    id = mapped_column(Integer, primary_key=True)
    box_id = mapped_column(ForeignKey("boxes.id", ondelete="CASCADE"))
    product_id = mapped_column(ForeignKey("product_catalog.id", ondelete="CASCADE"))
    quantity = mapped_column(Integer, default=1)
    box = relationship("Box", back_populates="items")
    product = relationship("ProductCatalog", back_populates="box_items")

class Location(Base):
    __tablename__ = "locations"
    id = mapped_column(Integer, primary_key=True)
    full_code = mapped_column(String(50), unique=True, index=True)
    warehouse_id = mapped_column(Integer, default=1)
    capacity = mapped_column(Integer, default=1)
    description = mapped_column(String(200), nullable=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)
    inventories = relationship("Inventory", back_populates="location")

class Inventory(Base):
    __tablename__ = "inventory"
    id = mapped_column(Integer, primary_key=True)
    box_id = mapped_column(ForeignKey("boxes.id", ondelete="CASCADE"), unique=True)
    location_id = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    status = mapped_column(String(20), default="stored")
    moved_at = mapped_column(DateTime, default=datetime.utcnow)
    box = relationship("Box", back_populates="inventory")
    location = relationship("Location", back_populates="inventories")

# ==================== DATABASE ====================

def get_db_url():
    return os.getenv("DATABASE_URL", "sqlite:///./repiauto.db")

url = get_db_url()
if "postgresql" in url:
    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 10})
else:
    engine = create_engine(url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        raise

init_db()

# ==================== APP ====================

app = FastAPI(title="Repiauto")
templates = Jinja2Templates(directory="templates")

# ==================== ERROR HANDLING ====================

@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("error.html", {"request": request, "title": "Página no encontrada", "message": "La página que buscas no existe."}, status_code=404)

@app.exception_handler(405)
async def method_not_allowed(request: Request, exc):
    return templates.TemplateResponse("error.html", {"request": request, "title": "Método no permitido", "message": "Acción no válida para esta ruta."}, status_code=405)

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc):
    return templates.TemplateResponse("error.html", {"request": request, "title": "Datos inválidos", "message": "Revisa los datos ingresados."}, status_code=422)

@app.exception_handler(500)
async def server_error(request: Request, exc):
    logger.error(f"500 error: {traceback.format_exc()}")
    return templates.TemplateResponse("error.html", {"request": request, "title": "Error interno", "message": "Ocurrió un error inesperado. Intenta de nuevo."}, status_code=500)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc):
    logger.error(f"Unhandled exception: {traceback.format_exc()}")
    return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Algo salió mal. Intenta de nuevo."}, status_code=500)

# ==================== HELPERS ====================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except:
            pass

def safe_db_operation(db, operation, error_msg="Error de base de datos"):
    try:
        return operation()
    except IntegrityError as e:
        db.rollback()
        if "UNIQUE" in str(e):
            raise HTTPException(400, f"Ya existe un registro con ese valor.")
        raise HTTPException(400, error_msg)
    except OperationalError:
        db.rollback()
        raise HTTPException(500, "Error de conexión a la base de datos.")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, error_msg)

# ==================== ROUTES ====================

# --- DASHBOARD ---

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    try:
        db = SessionLocal()
        try:
            stats = {
                "total_products": db.query(ProductCatalog).count(),
                "total_containers": db.query(ShippingContainer).count(),
                "total_boxes": db.query(Box).count(),
                "total_inventory": db.query(Inventory).count(),
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        stats = {"total_products": 0, "total_containers": 0, "total_boxes": 0, "total_inventory": 0}
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})

# --- PRODUCTS ---

@app.get("/products", response_class=HTMLResponse)
async def products(request: Request):
    try:
        db = SessionLocal()
        try:
            prods = db.query(ProductCatalog).order_by(ProductCatalog.created_at.desc()).all()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Products error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "No se pudieron cargar los productos."})
    return templates.TemplateResponse("products.html", {"request": request, "products": prods})

@app.post("/products")
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
            db.add(ProductCatalog(sku_usa=sku_usa, sku_china=sku_china, name=name))
            db.commit()
            return success_redirect("/products", "Producto creado correctamente.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/products", f"El SKU '{sku_usa}' ya está registrado.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Product create error: {e}")
        return error_redirect("/products", "Error al crear el producto.")

@app.post("/products/{product_id}/update")
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
            return error_redirect("/products", f"El SKU '{sku_usa}' ya está en uso.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Product update error: {e}")
        return error_redirect("/products", "Error al actualizar el producto.")

@app.post("/products/{product_id}/delete")
async def products_delete(request: Request, product_id: int):
    try:
        db = SessionLocal()
        try:
            p = db.get(ProductCatalog, product_id)
            if not p:
                return error_redirect("/products", "Producto no encontrado.")
            db.delete(p)
            db.commit()
            return success_redirect("/products", "Producto eliminado.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/products", "No se puede eliminar: está siendo usado en algún pedido.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Product delete error: {e}")
        return error_redirect("/products", "Error al eliminar el producto.")

# --- CONTAINERS ---

@app.get("/containers", response_class=HTMLResponse)
async def containers(request: Request):
    try:
        db = SessionLocal()
        try:
            raw = db.query(ShippingContainer).order_by(ShippingContainer.created_at.desc()).all()
            result = []
            for c in raw:
                order_count = db.query(Order).filter(Order.container_id == c.id).count()
                result.append(c)
                result[-1].order_count = order_count
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Containers error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "No se pudieron cargar los contenedores."})
    return templates.TemplateResponse("containers.html", {"request": request, "containers": result})

@app.post("/containers")
async def containers_create(request: Request, invoice_number: str = Form(None), arrival_date: str = Form(None), notes: str = Form(None)):
    invoice_number = safe_str(invoice_number)
    notes = safe_str(notes)
    if not invoice_number:
        return error_redirect("/containers", "El número de factura es obligatorio.")

    try:
        db = SessionLocal()
        try:
            arrival = datetime.fromisoformat(arrival_date) if arrival_date else None
            c = ShippingContainer(invoice_number=invoice_number, arrival_date=arrival, notes=notes, status=ContainerStatus.ARRIVED)
            db.add(c)
            db.commit()
            db.refresh(c)
            return success_redirect(f"/containers/{c.id}", "Contenedor creado correctamente.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/containers", f"El número de factura '{invoice_number}' ya existe.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container create error: {e}")
        return error_redirect("/containers", "Error al crear el contenedor.")

@app.post("/containers/{container_id}/update")
async def containers_update(request: Request, container_id: int, invoice_number: str = Form(None), arrival_date: str = Form(None), notes: str = Form(None)):
    invoice_number = safe_str(invoice_number)
    notes = safe_str(notes)
    if not invoice_number:
        return error_redirect(f"/containers/{container_id}", "El número de factura es obligatorio.")

    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c:
                return error_redirect("/containers", "Contenedor no encontrado.")
            c.invoice_number = invoice_number
            c.arrival_date = datetime.fromisoformat(arrival_date) if arrival_date else None
            c.notes = notes
            db.commit()
            return success_redirect(f"/containers/{container_id}", "Contenedor actualizado.")
        except IntegrityError:
            db.rollback()
            return error_redirect(f"/containers/{container_id}", "Ese número de factura ya existe.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container update error: {e}")
        return error_redirect(f"/containers/{container_id}", "Error al actualizar el contenedor.")

@app.post("/containers/{container_id}/delete")
async def containers_delete(request: Request, container_id: int):
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c:
                return error_redirect("/containers", "Contenedor no encontrado.")
            db.delete(c)
            db.commit()
            return success_redirect("/containers", "Contenedor eliminado.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container delete error: {e}")
        return error_redirect("/containers", "Error al eliminar el contenedor.")

@app.get("/containers/{container_id}", response_class=HTMLResponse)
async def container_detail(request: Request, container_id: int):
    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c:
                return templates.TemplateResponse("error.html", {"request": request, "title": "No encontrado", "message": "Ese contenedor no existe."}, status_code=404)

            orders_raw = db.query(Order).filter(Order.container_id == container_id).all()
            orders = []
            for o in orders_raw:
                boxes_raw = db.query(Box).filter(Box.order_id == o.id).all()
                boxes = []
                for b in boxes_raw:
                    items_raw = db.query(BoxItem).options(joinedload(BoxItem.product)).filter(BoxItem.box_id == b.id).all()
                    items = []
                    for i in items_raw:
                        items.append({
                            "id": i.id, "quantity": i.quantity,
                            "product_sku_usa": i.product.sku_usa if i.product else "",
                            "product_name": i.product.name if i.product else "",
                        })
                boxes.append({"id": b.id, "lpn_code": b.lpn_code, "box_number": b.box_number, "status": b.status, "product_list": items})
                orders.append({"id": o.id, "invoice_number": o.invoice_number, "supplier": o.supplier, "boxes": boxes})

            products_raw = db.query(ProductCatalog).all()
            products = [{"id": p.id, "sku_usa": p.sku_usa, "name": p.name} for p in products_raw]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Container detail error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Error al cargar el contenedor."})

    return templates.TemplateResponse("container_detail.html", {"request": request, "container": c, "orders": orders, "products": products})

@app.post("/containers/{container_id}/orders")
async def orders_create(request: Request, container_id: int, invoice_number: str = Form(None), supplier: str = Form(None)):
    invoice_number = safe_str(invoice_number)
    if not invoice_number:
        return error_redirect(f"/containers/{container_id}", "El número de factura del pedido es obligatorio.")

    try:
        db = SessionLocal()
        try:
            c = db.get(ShippingContainer, container_id)
            if not c:
                return error_redirect(f"/containers/{container_id}", "Contenedor no encontrado.")
            db.add(Order(container_id=container_id, invoice_number=invoice_number, supplier=safe_str(supplier) or None))
            db.commit()
            return success_redirect(f"/containers/{container_id}", "Pedido agregado.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Order create error: {e}")
        return error_redirect(f"/containers/{container_id}", "Error al crear el pedido.")

@app.post("/containers/{container_id}/orders/{order_id}/delete")
async def order_delete(request: Request, container_id: int, order_id: int):
    try:
        db = SessionLocal()
        try:
            o = db.get(Order, order_id)
            if o:
                db.delete(o)
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Order delete error: {e}")
    return success_redirect(f"/containers/{container_id}", "Pedido eliminado.")

# --- BOXES ---

@app.get("/containers/{container_id}/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(request: Request, container_id: int, order_id: int):
    try:
        db = SessionLocal()
        try:
            order_raw = db.get(Order, order_id)
            if not order_raw:
                return templates.TemplateResponse("error.html", {"request": request, "title": "No encontrado", "message": "Pedido no encontrado."}, status_code=404)

            order = {"id": order_raw.id, "invoice_number": order_raw.invoice_number, "supplier": order_raw.supplier}

            boxes_raw = db.query(Box).filter(Box.order_id == order_id).all()
            boxes = []
            for b in boxes_raw:
                items_raw = db.query(BoxItem).options(joinedload(BoxItem.product)).filter(BoxItem.box_id == b.id).all()
                items = []
                for i in items_raw:
                    items.append({
                        "id": i.id, "quantity": i.quantity,
                        "product_sku_usa": i.product.sku_usa if i.product else "",
                        "product_name": i.product.name if i.product else "",
                        "product_sku_china": i.product.sku_china if i.product else "",
                    })
                boxes.append({"id": b.id, "lpn_code": b.lpn_code, "box_number": b.box_number, "status": b.status, "product_list": items})

            products_raw = db.query(ProductCatalog).all()
            products = [{"id": p.id, "sku_usa": p.sku_usa, "name": p.name} for p in products_raw]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Order detail error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Error al cargar el pedido."})

    return templates.TemplateResponse("order_detail.html", {"request": request, "order": order, "boxes": boxes, "products": products, "container_id": container_id})

@app.post("/containers/{container_id}/orders/{order_id}/boxes")
async def boxes_create(request: Request, container_id: int, order_id: int, box_number: int = Form(None)):
    box_number = safe_int(box_number)
    if not box_number or box_number < 1:
        return error_redirect(f"/containers/{container_id}/orders/{order_id}", "El número de caja debe ser 1 o mayor.")

    try:
        db = SessionLocal()
        try:
            o = db.get(Order, order_id)
            if not o:
                return error_redirect(f"/containers/{container_id}", "Pedido no encontrado.")

            invoice_last4 = o.invoice_number[-4:] if len(o.invoice_number) >= 4 else o.invoice_number
            lpn_code = f"{invoice_last4}-{box_number:02d}"

            if db.query(Box).filter(Box.lpn_code == lpn_code).first():
                return error_redirect(f"/containers/{container_id}/orders/{order_id}", f"El LPN '{lpn_code}' ya existe.")

            db.add(Box(order_id=order_id, box_number=box_number, lpn_code=lpn_code))
            db.commit()
            return success_redirect(f"/containers/{container_id}/orders/{order_id}", f"Caja {lpn_code} creada.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box create error: {e}")
        return error_redirect(f"/containers/{container_id}/orders/{order_id}", "Error al crear la caja.")

@app.post("/containers/{container_id}/orders/{order_id}/boxes/{box_id}/update")
async def box_update(request: Request, container_id: int, order_id: int, box_id: int, box_number: int = Form(None)):
    box_number = safe_int(box_number)
    if not box_number or box_number < 1:
        return error_redirect(f"/containers/{container_id}/orders/{order_id}", "El número de caja debe ser 1 o mayor.")

    try:
        db = SessionLocal()
        try:
            b = db.get(Box, box_id)
            if not b:
                return error_redirect(f"/containers/{container_id}/orders/{order_id}", "Caja no encontrada.")

            o = db.get(Order, order_id)
            invoice_last4 = o.invoice_number[-4:] if o and len(o.invoice_number) >= 4 else "XXXX"
            new_lpn = f"{invoice_last4}-{box_number:02d}"

            existing = db.query(Box).filter(Box.lpn_code == new_lpn, Box.id != box_id).first()
            if existing:
                return error_redirect(f"/containers/{container_id}/orders/{order_id}", f"El LPN '{new_lpn}' ya está en uso.")

            b.box_number = box_number
            b.lpn_code = new_lpn
            db.commit()
            return success_redirect(f"/containers/{container_id}/orders/{order_id}", "Caja actualizada.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box update error: {e}")
        return error_redirect(f"/containers/{container_id}/orders/{order_id}", "Error al actualizar la caja.")

@app.post("/containers/{container_id}/orders/{order_id}/boxes/{box_id}/delete")
async def box_delete(request: Request, container_id: int, order_id: int, box_id: int):
    try:
        db = SessionLocal()
        try:
            b = db.get(Box, box_id)
            if b:
                db.delete(b)
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box delete error: {e}")
        return error_redirect(f"/containers/{container_id}/orders/{order_id}", "Error al eliminar la caja.")
    return success_redirect(f"/containers/{container_id}/orders/{order_id}", "Caja eliminada.")

@app.post("/containers/{container_id}/orders/{order_id}/boxes/{box_id}/items")
async def box_items_create(request: Request, container_id: int, order_id: int, box_id: int, product_id: int = Form(None), quantity: int = Form(None)):
    product_id = safe_int(product_id)
    quantity = safe_int(quantity)

    if not product_id:
        return error_redirect(f"/containers/{container_id}/orders/{order_id}", "Selecciona un producto.")
    if not quantity or quantity < 1:
        return error_redirect(f"/containers/{container_id}/orders/{order_id}", "La cantidad debe ser 1 o mayor.")

    try:
        db = SessionLocal()
        try:
            b = db.get(Box, box_id)
            if not b:
                return error_redirect(f"/containers/{container_id}/orders/{order_id}", "Caja no encontrada.")
            p = db.get(ProductCatalog, product_id)
            if not p:
                return error_redirect(f"/containers/{container_id}/orders/{order_id}", "Producto no encontrado.")

            db.add(BoxItem(box_id=box_id, product_id=product_id, quantity=quantity))
            db.commit()
            return success_redirect(f"/containers/{container_id}/orders/{order_id}", "Producto agregado a la caja.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Box item create error: {e}")
        return error_redirect(f"/containers/{container_id}/orders/{order_id}", "Error al agregar el producto.")

@app.post("/containers/{container_id}/orders/{order_id}/finalize")
async def order_finalize(request: Request, container_id: int, order_id: int):
    try:
        db = SessionLocal()
        try:
            o = db.get(Order, order_id)
            if not o:
                return error_redirect(f"/containers/{container_id}", "Pedido no encontrado.")

            boxes = db.query(Box).filter(Box.order_id == order_id).all()
            count = 0
            for box in boxes:
                item_count = db.query(BoxItem).filter(BoxItem.box_id == box.id).count()
                if item_count == 0:
                    continue
                box.status = BoxStatus.PENDING
                existing = db.query(Inventory).filter(Inventory.box_id == box.id).first()
                if not existing:
                    db.add(Inventory(box_id=box.id, status="pending_location"))
                count += 1

            db.commit()
            return success_redirect(f"/containers/{container_id}", f"{count} caja(s) enviadas a inventario.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Finalize error: {e}")
        return error_redirect(f"/containers/{container_id}", "Error al finalizar el pedido.")

# --- INVENTORY ---

@app.get("/inventory", response_class=HTMLResponse)
async def inventory(request: Request):
    try:
        db = SessionLocal()
        try:
            rows = db.query(Inventory).options(
                joinedload(Inventory.box).joinedload(Box.order),
                joinedload(Inventory.box).joinedload(Box.items).joinedload(BoxItem.product),
                joinedload(Inventory.location)
            ).all()

            items = []
            for r in rows:
                box = r.box
                products_list = []
                if box:
                    for i in box.items:
                        if i.product:
                            products_list.append((i.product.sku_usa, i.quantity))
                items.append({
                    "id": r.id,
                    "box_id": r.box_id,
                    "location_id": r.location_id,
                    "status": r.status,
                    "box_lpn": box.lpn_code if box else "?",
                    "order_invoice": box.order.invoice_number if box and box.order else "?",
                    "products": products_list,
                    "location_code": r.location.full_code if r.location else None,
                })

            locs = db.query(Location).all()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Inventory error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Error al cargar el inventario."})

    return templates.TemplateResponse("inventory.html", {"request": request, "items": items, "locations": locs})

@app.post("/inventory/{inventory_id}/assign")
async def inventory_assign(request: Request, inventory_id: int, location_id: int = Form(None)):
    location_id = safe_int(location_id)
    if not location_id:
        return error_redirect("/inventory", "Selecciona una ubicación.")

    try:
        db = SessionLocal()
        try:
            loc = db.get(Location, location_id)
            if not loc:
                return error_redirect("/inventory", "Ubicación no encontrada.")

            inv = db.get(Inventory, inventory_id)
            if not inv:
                return error_redirect("/inventory", "Item de inventario no encontrado.")

            inv.location_id = location_id
            inv.status = "stored"
            inv.moved_at = datetime.utcnow()

            box = db.get(Box, inv.box_id)
            if box:
                box.status = BoxStatus.IN_INVENTORY

            db.commit()
            return success_redirect("/inventory", f"Ubicación {loc.full_code} asignada.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Inventory assign error: {e}")
        return error_redirect("/inventory", "Error al asignar ubicación.")

# --- LOCATIONS ---

@app.get("/locations", response_class=HTMLResponse)
async def locations(request: Request):
    try:
        db = SessionLocal()
        try:
            locs = db.query(Location).all()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Locations error: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Error al cargar ubicaciones."})
    return templates.TemplateResponse("locations.html", {"request": request, "locations": locs})

@app.post("/locations")
async def locations_create(request: Request, full_code: str = Form(None), warehouse_id: int = Form(None), capacity: int = Form(None), description: str = Form(None)):
    full_code = safe_str(full_code)
    warehouse_id = safe_int(warehouse_id, 1)
    capacity = safe_int(capacity, 1)

    if not full_code:
        return error_redirect("/locations", "El código de ubicación es obligatorio.")

    try:
        db = SessionLocal()
        try:
            db.add(Location(full_code=full_code, warehouse_id=warehouse_id, capacity=capacity, description=safe_str(description) or None))
            db.commit()
            return success_redirect("/locations", f"Ubicación {full_code} creada.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/locations", f"La ubicación '{full_code}' ya existe.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Location create error: {e}")
        return error_redirect("/locations", "Error al crear la ubicación.")

@app.post("/locations/{location_id}/delete")
async def locations_delete(request: Request, location_id: int):
    try:
        db = SessionLocal()
        try:
            l = db.get(Location, location_id)
            if not l:
                return error_redirect("/locations", "Ubicación no encontrada.")
            db.delete(l)
            db.commit()
            return success_redirect("/locations", "Ubicación eliminada.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/locations", "No se puede eliminar: está siendo usada.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Location delete error: {e}")
        return error_redirect("/locations", "Error al eliminar la ubicación.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
