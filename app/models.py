from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Numeric, JSON
from sqlalchemy.orm import relationship
from .db import Base

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=now)

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    sort_order = Column(Integer, default=0)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    specs = Column(Text)          # one specification per line
    customization = Column(Text)  # available customization options
    moq = Column(Integer, default=1)
    etsy_url = Column(String(500))
    available = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)
    category = relationship("Category")
    media = relationship("Media", cascade="all, delete-orphan", order_by="Media.sort_order, Media.id")

class Media(Base):
    __tablename__ = "media"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    scope = Column(String(20), default="product")   # product | factory
    kind = Column(String(10), default="image")      # image | video
    path = Column(String(300), nullable=False)
    title = Column(String(200))
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)

class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    body = Column(Text)
    published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))
    company = Column(String(160))
    email = Column(String(190), index=True)
    whatsapp = Column(String(40))
    created_at = Column(DateTime, default=now)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    reference = Column(String(30), unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    type = Column(String(30), default="Bulk inquiry")  # Bulk inquiry | Sample request
    status = Column(String(30), default="New Inquiry", index=True)
    product_name = Column(String(200))
    quantity = Column(Integer)
    customization = Column(Text)   # customization request
    notes = Column(Text)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)
    customer = relationship("Customer")
    items = relationship("OrderItem", cascade="all, delete-orphan")
    attachments = relationship("Attachment", cascade="all, delete-orphan")
    documents = relationship("Document", cascade="all, delete-orphan", order_by="Document.id")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"))
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name = Column(String(200))
    quantity = Column(Integer)

class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"))
    original_name = Column(String(255))
    stored_name = Column(String(100))
    size = Column(Integer)
    created_at = Column(DateTime, default=now)

class Document(Base):  # quotations and invoices, with revision history
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"))
    kind = Column(String(20), default="quotation")
    number = Column(String(60), unique=True)
    version = Column(Integer, default=1)
    items = Column(JSON)
    subtotal = Column(Numeric(12, 2), default=0)
    tax_percent = Column(Numeric(5, 2), default=0)
    extra_charges = Column(Numeric(12, 2), default=0)
    extra_note = Column(String(200))
    total = Column(Numeric(12, 2), default=0)
    currency = Column(String(8), default="USD")
    terms = Column(Text)
    token = Column(String(64), unique=True)
    email_status = Column(String(20), default="not sent")
    whatsapp_status = Column(String(20), default="not sent")
    created_at = Column(DateTime, default=now)

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))
    company = Column(String(160))
    rating = Column(Integer, default=5)
    text = Column(Text)
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, nullable=True, index=True)
    channel = Column(String(20))
    recipient = Column(String(200))
    subject = Column(String(200))
    status = Column(String(20))
    detail = Column(Text)
    created_at = Column(DateTime, default=now)

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(80), primary_key=True)
    value = Column(JSON)
