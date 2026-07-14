import traceback
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

import database  # triggers init_db() after all models are imported
from config import templates
from routes import dashboard_router, products_router, imports_router, inventory_router, locations_router, warehouse_router

logger = logging.getLogger("repiauto")


class CacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app = FastAPI(title="Repiauto")

app.add_middleware(CacheStaticMiddleware)

app.include_router(dashboard_router)
app.include_router(products_router)
app.include_router(imports_router)
app.include_router(inventory_router)
app.include_router(locations_router)
app.include_router(warehouse_router)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("error.html", {"request": request, "title": "Pagina no encontrada", "message": "La pagina que buscas no existe."}, status_code=404)


@app.exception_handler(405)
async def method_not_allowed(request: Request, exc):
    return templates.TemplateResponse("error.html", {"request": request, "title": "Metodo no permitido", "message": "Accion no valida para esta ruta."}, status_code=405)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc):
    return templates.TemplateResponse("error.html", {"request": request, "title": "Datos invalidos", "message": "Revisa los datos ingresados."}, status_code=422)


@app.exception_handler(500)
async def server_error(request: Request, exc):
    logger.error(f"500 error: {traceback.format_exc()}")
    return templates.TemplateResponse("error.html", {"request": request, "title": "Error interno", "message": "Ocurrio un error inesperado. Intenta de nuevo."}, status_code=500)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc):
    logger.error(f"Unhandled exception: {traceback.format_exc()}")
    return templates.TemplateResponse("error.html", {"request": request, "title": "Error", "message": "Algo salio mal. Intenta de nuevo."}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
