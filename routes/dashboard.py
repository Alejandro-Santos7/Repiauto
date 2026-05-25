from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from config import SessionLocal, templates, logger
from models import ProductCatalog, OrderChina, ShippingContainer, Box, Inventory
from sqlalchemy.orm import joinedload

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    try:
        db = SessionLocal()
        try:
            stats = {
                "total_products": db.query(ProductCatalog).count(),
                "total_orders": db.query(OrderChina).count(),
                "open_orders": db.query(OrderChina).filter(OrderChina.status == "open").count(),
                "closed_orders": db.query(OrderChina).filter(OrderChina.status == "closed").count(),
                "total_containers": db.query(ShippingContainer).count(),
                "pending_containers": db.query(ShippingContainer).filter(ShippingContainer.status == "pending").count(),
                "arrived_containers": db.query(ShippingContainer).filter(ShippingContainer.status == "arrived").count(),
                "completed_containers": db.query(ShippingContainer).filter(ShippingContainer.status == "completed").count(),
                "total_boxes": db.query(Box).count(),
                "pending_boxes": db.query(Box).filter(Box.status == "pending").count(),
                "to_locate_boxes": db.query(Box).filter(Box.status == "to_locate").count(),
                "located_boxes": db.query(Box).filter(Box.status == "located").count(),
                "total_inventory": db.query(Inventory).count(),
                "pending_inventory": db.query(Inventory).filter(Inventory.status == "pending_location").count(),
                "stored_inventory": db.query(Inventory).filter(Inventory.status == "stored").count(),
                "recent_orders": db.query(OrderChina).order_by(OrderChina.created_at.desc()).limit(5).all(),
                "recent_containers": db.query(ShippingContainer).options(
                    joinedload(ShippingContainer.order_china)
                ).order_by(ShippingContainer.created_at.desc()).limit(5).all(),
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        stats = {
            "total_products": 0, "total_orders": 0, "open_orders": 0, "closed_orders": 0,
            "total_containers": 0, "pending_containers": 0, "arrived_containers": 0, "completed_containers": 0,
            "total_boxes": 0, "pending_boxes": 0, "to_locate_boxes": 0, "located_boxes": 0,
            "total_inventory": 0, "pending_inventory": 0, "stored_inventory": 0,
            "recent_orders": [], "recent_containers": [],
        }
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})
