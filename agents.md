Documentación Técnica y Hoja de Ruta
Este documento define la arquitectura, lógica de negocio y plan de ejecución para el sistema Repiauto, optimizado para correr en hardware limitado (4GB RAM, Intel i5-2400).

---
1. Arquitectura Técnica
Stack: FastAPI (Backend) + HTMX (Interactividad) + Tailwind CSS (CDN) + Neon (Postgres) + Render (Hosting).

Justificación de SSR + HTMX:
- Eficiencia de Memoria: Al utilizar Server-Side Rendering (SSR), el servidor entrega HTML listo para mostrar. HTMX permite actualizaciones parciales sin necesidad de frameworks pesados (React/Vue), lo cual es crítico para el hardware objetivo.
- Simplicidad de Estado: El estado reside en la base de datos, reduciendo la carga de procesamiento en el cliente.

---
2. Flujo de Negocio (Workflow)

Paso 1: Orden China (orders_china)
- Se crea una orden con invoice_number (factura/packing list del proveedor chino) y supplier
- Una orden puede tener muchos contenedores

Paso 2: Contenedor (shipping_containers)
- Se crea un contenedor vinculado a una orden china
- Contiene: invoice_number (ID del packing list digital), bill_number (Bill of Lading)
- Estados: pending (en tránsito), arrived (llegó), completed (procesado)
- El contenedor tiene cajas directamente (sin capa intermedia de "pedido")

Paso 3: Cajas (boxes)
- Se crean cajas dentro del contenedor
- LPN se genera automáticamente: [invoice_last4]-[box_number:02d]
- Ejemplo: 0989-01 (Factura 0989, Caja 01)
- Estados: pending (en contenedor), to_locate (enviada a inventario), located (ubicada)

Paso 4: Items (box_items)
- Se agregan productos a cada caja (product_id + cantidad)
- El inventario se vincula a la caja, no al producto individual

Paso 5: Finalización
- Al finalizar, el contenedor pasa a "completed" y las cajas cambian a "to_locate"
- Se crea automáticamente un registro en Inventory por cada caja con items

Paso 6: Asignación de Ubicación
- Se asigna una ubicación a cada caja en inventario
- La caja pasa a "located" y el inventario a "stored"

---
3. Roles de Usuario
A. Oficinista (Administración y Entrada)
- Crear Ordenes China: Registro de facturas de proveedores
- Crear Contenedores: Recepción de mercancía
- Gestión de Cajas: Crear cajas, agregar productos
- Finalizar Contenedores: Enviar cajas al inventario

B. Logística (Operaciones de Almacén)
- Asignar Ubicaciones: Ubicar cajas en racks
- Gestión de Inventario: Ver estado y ubicación de productos

---
4. Lógica de Identificación y Ubicación
Identificación de Cajas (LPN)
Formato: [FACTURA_ÚLTIMOS_4]-[NRO_CAJA]
- Ejemplo: 0989-08 (Factura 0989, Caja 08).

Nomenclatura de Ubicaciones
- Almacén 1 (Racks): 1-P[1-2]-[LETRA]-[NIVEL]
  - Ejemplo: 1-P2-A-3 (Almacén 1, Pasillo 2, Rack A, Nivel 3).
- Almacén 2 (Cuadrícula): 2-[FILA]-[COL]-[NIVEL]
  - Ejemplo: 2-B-05-4 (Almacén 2, Fila B, Columna 05, Nivel 4).

---
5. Esquema de Base de Datos (SQLAlchemy)

Entidades Principales:

```python
class ProductCatalog(Base):
    __tablename__ = "product_catalog"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_usa: Mapped[str] = mapped_column(String(50), index=True)      # SKU comercial USA
    sku_china: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(200))                    # Descripción del vidrio
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class OrderChina(Base):
    __tablename__ = "orders_china"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # Factura China
    supplier: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    containers = relationship("ShippingContainer", back_populates="order_china")

class ShippingContainer(Base):
    __tablename__ = "shipping_containers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # ID packing list
    bill_number: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)   # Bill of Lading
    orders_china_id: Mapped[int] = mapped_column(ForeignKey("orders_china.id", ondelete="RESTRICT"))
    arrival_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/arrived/completed
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    boxes = relationship("Box", back_populates="container", cascade="all, delete-orphan")

class Box(Base):
    __tablename__ = "boxes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("shipping_containers.id", ondelete="CASCADE"))
    box_number: Mapped[int] = mapped_column(Integer)
    lpn_code: Mapped[str] = mapped_column(String(50), unique=True)  # Formato: FACTURA-CAJA
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/to_locate/located
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items = relationship("BoxItem", back_populates="box", cascade="all, delete-orphan")
    inventory = relationship("Inventory", back_populates="box", uselist=False, cascade="all, delete-orphan")

class BoxItem(Base):
    __tablename__ = "box_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("boxes.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product_catalog.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # 1-P2-A-3
    warehouse_id: Mapped[int] = mapped_column(Integer, default=1)
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    inventories = relationship("Inventory", back_populates="location")

class Inventory(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("boxes.id", ondelete="CASCADE"), unique=True)
    location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_location")  # pending_location/stored
    moved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

Relaciones:
- OrderChina 1 → N ShippingContainer
- ShippingContainer 1 → N Box
- Box 1 → N BoxItem
- BoxItem N → 1 ProductCatalog
- Box 1 → 1 Inventory
- Location 1 → N Inventory

---
6. Rutas (Endpoints)

| URL | Método | Descripción |
|-----|--------|-------------|
| / | GET | Dashboard con estadísticas |
| /products | GET/POST | CRUD productos |
| /orders-china | GET/POST | CRUD órdenes China |
| /orders-china/{id}/update | POST | Actualizar orden |
| /orders-china/{id}/delete | POST | Eliminar orden |
| /containers | GET/POST | Listar/crear contenedores |
| /containers/{id} | GET | Detalle con cajas e items |
| /containers/{id}/update | POST | Actualizar contenedor |
| /containers/{id}/status | POST | Cambiar estado (pending/arrived/completed) |
| /containers/{id}/delete | POST | Eliminar contenedor |
| /containers/{id}/boxes | POST | Crear caja |
| /containers/{id}/boxes/{box_id}/update | POST | Editar número de caja |
| /containers/{id}/boxes/{box_id}/delete | POST | Eliminar caja |
| /containers/{id}/boxes/{box_id}/items | POST | Agregar item a caja |
| /containers/{id}/boxes/{box_id}/items/{item_id}/delete | POST | Eliminar item |
| /containers/{id}/finalize | POST | Enviar cajas a inventario |
| /inventory | GET | Listar inventario |
| /inventory/{id}/assign | POST | Asignar ubicación |
| /locations | GET/POST | CRUD ubicaciones |

---
7. Hitos de Desarrollo (Roadmap)
Fase | Nombre | Entregables
1 | Importación | Setup de FastAPI, modelos, script de carga masiva de Excel (Pandas).
2 | Mapa de Ubicaciones | Visualización y gestión de Racks y Cuadrículas.
3 | Movimientos HTMX | Interfaz reactiva para traslados y desglose de cajas.
4 | PDFs y Etiquetas | Generación de reportes de inventario y etiquetas de cajas/ubicaciones.

---
8. Guía de Inicio
1. Entorno Virtual:
   python -m venv venv
   .\venv\Scripts\activate

2. Variables de Entorno (.env):
   DATABASE_URL=postgresql://neondb_owner:TU_PASSWORD@ep-xxx.eu-central-1.aws.neon.tech/repiauto?sslmode=require

3. Instalación de Dependencias:
   pip install fastapi uvicorn sqlalchemy psycopg2-binary pandas openpyxl jinja2 python-multipart python-dotenv

4. Ejecución:
   uvicorn main:app --reload

5. Acceso:
   http://127.0.0.1:8000