from datetime import datetime, date
from typing import Optional
from sqlalchemy import Integer, String, DateTime, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import Base


class ProductCatalog(Base):
    __tablename__ = "product_catalog"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_usa: Mapped[str] = mapped_column(String(50), index=True)
    sku_china: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    box_items = relationship("BoxItem", back_populates="product")


class OrderChina(Base):
    __tablename__ = "orders_china"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    pi_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    supplier: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    containers = relationship("ShippingContainer", back_populates="order_china", cascade="all, delete-orphan")


class ShippingContainer(Base):
    __tablename__ = "shipping_containers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    ref_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bill_number: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    orders_china_id: Mapped[int] = mapped_column(ForeignKey("orders_china.id", ondelete="RESTRICT"))
    order_china = relationship("OrderChina", back_populates="containers")
    arrival_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    boxes = relationship("Box", back_populates="container", cascade="all, delete-orphan")


class Box(Base):
    __tablename__ = "boxes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("shipping_containers.id", ondelete="CASCADE"))
    container = relationship("ShippingContainer", back_populates="boxes")
    box_number: Mapped[int] = mapped_column(Integer)
    lpn_code: Mapped[str] = mapped_column(String(50), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items = relationship("BoxItem", back_populates="box", cascade="all, delete-orphan")
    inventory = relationship("Inventory", back_populates="box", uselist=False, cascade="all, delete-orphan")


class BoxItem(Base):
    __tablename__ = "box_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("boxes.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product_catalog.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    box = relationship("Box", back_populates="items")
    product = relationship("ProductCatalog", back_populates="box_items")


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    warehouse_id: Mapped[int] = mapped_column(Integer, default=1)
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    custom_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    inventories = relationship("Inventory", back_populates="location")


class Inventory(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("boxes.id", ondelete="CASCADE"), unique=True)
    location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_location")
    moved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    box = relationship("Box", back_populates="inventory")
    location = relationship("Location", back_populates="inventories")
