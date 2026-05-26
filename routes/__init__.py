from routes.dashboard import router as dashboard_router
from routes.products import router as products_router
from routes.imports import router as imports_router
from routes.inventory import router as inventory_router
from routes.locations import router as locations_router
from routes.warehouse import router as warehouse_router

__all__ = [
    "dashboard_router",
    "products_router",
    "imports_router",
    "inventory_router",
    "locations_router",
    "warehouse_router",
]
