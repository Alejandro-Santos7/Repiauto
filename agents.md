Documentación Técnica y Hoja de Ruta
Este documento define la arquitectura, lógica de negocio y plan de ejecución para el sistema Repiauto, optimizado para correr en hardware limitado (4GB RAM, Intel i5-2400).
---
1. Arquitectura Técnica
Stack: FastAPI (Backend) + HTMX (Interactividad) + Tailwind CSS (CDN) + Neon (Postgres) + Render (Hosting).
Justificación de SSR + HTMX:
- Eficiencia de Memoria: Al utilizar Server-Side Rendering (SSR), el servidor entrega HTML listo para mostrar. HTMX permite actualizaciones parciales sin necesidad de frameworks pesados (React/Vue), lo cual es crítico para el hardware objetivo.
- Simplicidad de Estado: El estado reside en la base de datos, reduciendo la carga de procesamiento en el cliente.
---
2. Roles de Usuario
A. Oficinista (Administración y Entrada)
- Importación de Invoices: Carga de archivos Excel (China) para poblar productos y cajas.
- Creación de IDs de Cajas: Generación de etiquetas LPN.
- Definición de Mapa: Gestión lógica de las ubicaciones físicas.
B. Logística (Operaciones de Almacén)
- Traslados: Registro de movimientos entre Almacén 1 y Almacén 2.
- Desglose: Proceso de extraer vidrios de cajas (Containers) para colocarlos individualmente en racks.
---
3. Lógica de Identificación y Ubicación
Identificación de Cajas (LPN)
Formato: [FACTURA]-[NRO_CAJA]
- Ejemplo: 0989-08 (Factura 0989, Caja 08).
Nomenclatura de Ubicaciones
- Almacén 1 (Racks): 1-P[1-2]-[LETRA]-[NIVEL]
  - Ejemplo: 1-P2-A-3 (Almacén 1, Pasillo 2, Rack A, Nivel 3).
- Almacén 2 (Cuadrícula): 2-[FILA]-[COL]-[NIVEL]
  - Ejemplo: 2-B-05-4 (Almacén 2, Fila B, Columna 05, Nivel 4).
---
4. Esquema de Base de Datos (SQLAlchemy)
Entidad: Product
class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True)
    sku_usa = Column(String, index=True, unique=True)   # El DNI comercial
    sku_china = Column(String, index=True)             # El DNI de fábrica
    name = Column(String)                       # Lo que es el vidrio
Otras Entidades Clave:
- Container: id, lpn_code (Unique), invoice_ref, status.
- Location: id, full_code, warehouse_id, capacity.
- Inventory: id, product_id, location_id, container_id (Optional).
  * Nota: Si container_id es NULL, el producto está suelto en el rack.
- AuditLog: id, user_id, action, timestamp, payload (JSON).
---
5. Hitos de Desarrollo (Roadmap)
Fase	Nombre	Entregables
1	Importación	Setup de FastAPI, modelos y script de carga masiva de Excel (Pandas).
2	Mapa de Ubicaciones	Visualización y gestión de Racks y Cuadrículas.
3	Movimientos HTMX	Interfaz reactiva para traslados y desglose de cajas.
4	PDFs y Etiquetas	Generación de reportes de inventario y etiquetas de cajas/ubicaciones.
---
6. Guía de Inicio
1. Entorno Virtual:
      python -m venv venv
   .\venv\Scripts\activate
   
2. Instalación de Dependencias:
      pip install fastapi uvicorn sqlalchemy psycopg2-binary pandas openpyxl jinja2 python-multipart
   
3. Ejecución:
      uvicorn main:app --reload
   ,filePath:C:\Users\alelo\Documents\Repiauto\agents.md}