from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import IntegrityError

from config import SessionLocal, templates, logger
from models import Location
from utils import safe_str, safe_int, error_redirect, success_redirect

router = APIRouter()


@router.get("/locations", response_class=HTMLResponse)
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


@router.post("/locations")
async def locations_create(request: Request, full_code: str = Form(None), warehouse_id: int = Form(None), capacity: int = Form(None), description: str = Form(None)):
    full_code = safe_str(full_code)
    warehouse_id = safe_int(warehouse_id, 1)
    capacity = safe_int(capacity, 1)
    if not full_code:
        return error_redirect("/locations", "El codigo de ubicacion es obligatorio.")
    try:
        db = SessionLocal()
        try:
            db.add(Location(full_code=full_code, warehouse_id=warehouse_id, capacity=capacity, description=safe_str(description) or None))
            db.commit()
            return success_redirect("/locations", f"Ubicacion {full_code} creada.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/locations", f"La ubicacion '{full_code}' ya existe.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Location create error: {e}")
        return error_redirect("/locations", "Error al crear la ubicacion.")


@router.post("/locations/{location_id}/delete")
async def locations_delete(request: Request, location_id: int):
    try:
        db = SessionLocal()
        try:
            l = db.get(Location, location_id)
            if not l:
                return error_redirect("/locations", "Ubicacion no encontrada.")
            db.delete(l)
            db.commit()
            return success_redirect("/locations", "Ubicacion eliminada.")
        except IntegrityError:
            db.rollback()
            return error_redirect("/locations", "No se puede eliminar: esta siendo usada.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Location delete error: {e}")
        return error_redirect("/locations", "Error al eliminar la ubicacion.")
