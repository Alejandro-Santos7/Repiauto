Documentación Técnica y Hoja de Ruta
Este documento define la arquitectura, lógica de negocio y plan de ejecución para el sistema Repiauto, optimizado para correr en hardware limitado (4GB RAM, Intel i5-2400).

---
1. Arquitectura Técnica
Stack: FastAPI (Backend) + HTMX (Interactividad) + Tailwind CSS (CDN) + Neon (Postgres) + Render (Hosting).

Justificación de SSR + HTMX:
- Eficiencia de Memoria: Al utilizar Server-Side Rendering (SSR), el servidor entrega HTML listo para mostrar. HTMX permite actualizaciones parciales sin necesidad de frameworks pesados (React/Vue).
- Simplicidad de Estado: El estado reside en la base de datos, reduciendo la carga de procesamiento en el cliente.

---
2. Estructura del Proyecto

```
Repiauto/
├── main.py              # Entry point: app=FastAPI(), exception handlers, include routers
├── config.py            # DB URL, engine, SessionLocal, Base, init_db(), templates
├── models.py            # 7 SQLAlchemy models (ProductCatalog, OrderChina, ShippingContainer, Box, BoxItem, Location, Inventory)
├── database.py          # import models + trigger init_db()
├── utils.py             # safe_int, safe_str, error_redirect, success_redirect, import progress logic
├── routes/
│   ├── __init__.py      # Re-exports all routers for clean import in main.py
│   ├── dashboard.py     # GET / — Dashboard stats
│   ├── products.py      # /products — CRUD, Excel import, delete-all, /products/search
│   ├── imports.py       # /imports — Orders, containers, boxes, items, labels
│   ├── inventory.py     # /inventory — List/search, assign location
│   └── locations.py     # /locations — CRUD
├── templates/           # Jinja2 templates (base, index, products, imports, inventory, locations, labels, error)
├── .env                 # DATABASE_URL, secrets
└── repiauto.db          # SQLite fallback (when no DATABASE_URL set)
```

Responsabilidades de cada módulo:
- **config.py**: Configuración global: conexión a BD, engine, SessionLocal, Base, Jinja2Templates, logger. Define `init_db()` que crea tablas. NO importa models.
- **models.py**: Todos los modelos SQLAlchemy. Importa `Base` de config.py.
- **database.py**: Importa models.py (para registrar todos los modelos en Base.metadata) y ejecuta `init_db()`. Debe importarse antes de crear la app FastAPI.
- **utils.py**: Funciones utilitarias puras y lógica de importación Excel con progreso. NO depende de FastAPI Request/Response directamente (usa RedirectResponse).
- **routes/**: Cada archivo define un `APIRouter`. Importan modelos de models.py, sesiones de config.py, helpers de utils.py.
- **main.py**: Entry point. Importa database (dispara init_db), crea FastAPI app, incluye todos los routers, registra exception handlers.

Orden de imports (crítico para evitar circular imports):
1. config.py (no imports de proyecto)
2. models.py (importa config.Base)
3. database.py (importa models, llama init_db)
4. utils.py (importa config, models)
5. routes/*.py (importan config, models, utils)
6. main.py (importa database, routes)

---
3. Convenciones de Código

- **Todo es POST excepto GETs**: Las acciones que modifican datos usan POST. Los GETs solo leen.
- **Manejo de sesiones**: Cada endpoint abre `SessionLocal()`, usa try/finally para cerrar.
- **Redirecciones**: Usar `success_redirect(url, msg)` y `error_redirect(url, msg)` de utils.py. Retornan RedirectResponse 303 con query params.
- **Nombrado de rutas**: Las URLs mantienen el formato REST existente: `/imports/{order_id}/containers/{container_id}/boxes/{box_id}/items`.
- **Form inputs**: Usar `name="q"` para parámetros de búsqueda que mapean al parámetro `q: str = ""` del backend.
- **HTMX en modales**: Siempre llamar `htmx.process(element)` después de inyectar HTML dinámico con `innerHTML`.

---
4. Flujo de Negocio (Workflow)

Paso 1: Orden China (orders_china)
- Se crea una orden con invoice_number (factura/packing list del proveedor chino) y supplier
- Campos adicionales: pi_number (opcional), created_date, status (open/closed)

Paso 2: Contenedor (shipping_containers)
- Vinculado a una orden china
- Contiene: invoice_number, ref_number, bill_number, arrival_date, notes
- Estados: pending → arrived → completed (reversible: completed → arrived)

Paso 3: Cajas (boxes)
- Creadas dentro del contenedor
- LPN: [invoice_last4]-[box_number:02d] (ej: 0989-01)
- Estados: pending → closed (reversible) → to_locate → located

Paso 4: Items (box_items)
- Se agregan productos a cada caja (product_id + cantidad)
- Búsqueda de productos vía HTMX: /products/search?q=...

Paso 5: Finalización
- Contenedor → completed, cajas con items → to_locate
- Se crea Inventory por cada caja con items

Paso 6: Asignación de Ubicación
- Inventory recibe location_id, box → located, inventory → stored

---
5. Modelos de Base de Datos

```
ProductCatalog (product_catalog)
├── id, sku_usa (indexed), sku_china (indexed, nullable), name, created_at

OrderChina (orders_china)
├── id, invoice_number (unique, indexed), pi_number, supplier
├── status (open/closed), created_date, created_at

ShippingContainer (shipping_containers)
├── id, invoice_number (unique, indexed), ref_number, bill_number
├── orders_china_id (FK), arrival_date, status (pending/arrived/completed)
├── notes, created_date, created_at

Box (boxes)
├── id, container_id (FK), box_number, lpn_code (unique)
├── status (pending/closed/to_locate/located), created_at

BoxItem (box_items)
├── id, box_id (FK), product_id (FK), quantity

Location (locations)
├── id, full_code (unique, indexed), warehouse_id, capacity, description, created_at

Inventory (inventory)
├── id, box_id (FK, unique), location_id (FK, nullable)
├── status (pending_location/stored), moved_at
```

Relaciones:
- OrderChina 1 → N ShippingContainer (cascade delete-orphan)
- ShippingContainer 1 → N Box (cascade delete-orphan)
- Box 1 → N BoxItem (cascade delete-orphan)
- BoxItem N → 1 ProductCatalog
- Box 1 → 1 Inventory (cascade delete-orphan)
- Location 1 → N Inventory (SET NULL on delete)

---
6. Rutas (Endpoints)

| URL | Método | Archivo | Descripción |
|-----|--------|---------|-------------|
| / | GET | dashboard.py | Dashboard con estadísticas |
| /products | GET | products.py | Listar productos |
| /products | POST | products.py | Crear producto |
| /products/{id}/update | POST | products.py | Actualizar producto |
| /products/{id}/delete | POST | products.py | Eliminar producto |
| /products/import | POST | products.py | Importar Excel (con barra progreso) |
| /products/import/progress/{task_id} | GET | products.py | Polling de progreso import |
| /products/delete-all | POST | products.py | Eliminar todos los productos |
| /products/search | GET | products.py | Búsqueda HTMX (q=) |
| /imports | GET | imports.py | Listar órdenes |
| /imports | POST | imports.py | Crear orden |
| /imports/{order_id} | GET | imports.py | Detalle orden + contenedores |
| /imports/{order_id}/update | POST | imports.py | Actualizar orden |
| /imports/{order_id}/close | POST | imports.py | Cerrar orden |
| /imports/{order_id}/open | POST | imports.py | Reabrir orden |
| /imports/{order_id}/delete | POST | imports.py | Eliminar orden |
| /imports/{order_id}/containers | POST | imports.py | Crear contenedor |
| /imports/{order_id}/containers/{id} | GET | imports.py | Detalle contenedor + cajas |
| /imports/{order_id}/containers/{id}/update | POST | imports.py | Actualizar contenedor |
| /imports/{order_id}/containers/{id}/status | POST | imports.py | Cambiar estado |
| /imports/{order_id}/containers/{id}/close | POST | imports.py | Cerrar contenedor |
| /imports/{order_id}/containers/{id}/open | POST | imports.py | Reabrir contenedor |
| /imports/{order_id}/containers/{id}/delete | POST | imports.py | Eliminar contenedor |
| /imports/{order_id}/containers/{id}/boxes | POST | imports.py | Crear caja |
| /imports/{order_id}/containers/{id}/boxes/{box_id}/update | POST | imports.py | Editar caja |
| /imports/{order_id}/containers/{id}/boxes/{box_id}/close | POST | imports.py | Cerrar caja |
| /imports/{order_id}/containers/{id}/boxes/{box_id}/open | POST | imports.py | Reabrir caja |
| /imports/{order_id}/containers/{id}/boxes/{box_id}/delete | POST | imports.py | Eliminar caja |
| /imports/{order_id}/containers/{id}/boxes/{box_id}/items | POST | imports.py | Agregar item |
| /imports/{order_id}/containers/{id}/boxes/{box_id}/items/{item_id}/delete | POST | imports.py | Eliminar item |
| /imports/{order_id}/containers/{id}/finalize | POST | imports.py | Finalizar → inventario |
| /imports/{order_id}/containers/{id}/print-labels | GET | imports.py | Imprimir etiquetas |
| /imports/{order_id}/containers/{id}/boxes/{box_id}/print-label | GET | imports.py | Imprimir etiqueta caja |
| /inventory | GET | inventory.py | Listar inventario (q= búsqueda) |
| /inventory/{id}/assign | POST | inventory.py | Asignar ubicación |
| /locations | GET | locations.py | Listar ubicaciones |
| /locations | POST | locations.py | Crear ubicación |
| /locations/{id}/delete | POST | locations.py | Eliminar ubicación |

---
7. Debugging y Errores Comunes

- **Búsqueda no funciona**: Verificar que el input usa `name="q"` (no `name="search"`). El backend espera `q: str = ""`.
- **Modal no procesa HTMX**: El contenido inyectado con innerHTML requiere `htmx.process(container)` después de la inyección.
- **Templates no se actualizan**: uvicorn --reload solo recarga con cambios en .py. Tocar main.py (ej: añadir/borrar comentario) fuerza reload de templates.
- **Indicador HTMX no aparece**: CSS usa `opacity` (no `display`): `.htmx-indicator { opacity: 0 }` y `.htmx-request .htmx-indicator, .htmx-indicator.htmx-request { opacity: 1 }`.

---
8. Hitos de Desarrollo (Roadmap)
Fase | Nombre | Entregables
1 | Importación | Setup FastAPI, modelos, carga masiva Excel con barra progreso.
2 | Mapa de Ubicaciones | Visualización y gestión de Racks y Cuadrículas.
3 | Movimientos HTMX | Búsqueda reactiva en inventario y asignación de productos a cajas.
4 | PDFs y Etiquetas | Generación de reportes y etiquetas de cajas/ubicaciones.

---
9. Guía de Inicio
1. Entorno Virtual:
   python -m venv .venv
   .\.venv\Scripts\activate

2. Variables de Entorno (.env):
   DATABASE_URL=postgresql://neondb_owner:TU_PASSWORD@ep-xxx.eu-central-1.aws.neon.tech/repiauto?sslmode=require

3. Instalación:
   pip install fastapi uvicorn sqlalchemy psycopg2-binary pandas openpyxl jinja2 python-multipart python-dotenv

4. Ejecución:
   uvicorn main:app --reload

5. Acceso:
   http://127.0.0.1:8000
