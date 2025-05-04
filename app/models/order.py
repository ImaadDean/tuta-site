from beanie import Document, Link
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"

class OrderItem(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    total_price: float

class ShippingAddress(BaseModel):
    street: str
    city: str
    state: str
    postal_code: str
    country: str = "Uganda"
    phone: Optional[str] = None

class Order(Document):
    """MongoDB Order document model using Beanie ODM"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_no: str
    user_id: Optional[str] = None  # Reference to User id, optional for guest checkout
    items: List[OrderItem]
    shipping_address: ShippingAddress
    total_amount: float
    payment_method: str
    payment_status: PaymentStatus = PaymentStatus.PENDING
    status: OrderStatus = OrderStatus.PENDING
    tracking_number: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # This will be used to store the user object when needed
    user: Optional[Any] = None
    
    class Settings:
        name = "orders"
        indexes = [
            "order_no",  
            "user_id",
            "status",
            "payment_status",
            "created_at"
        ]

# Pydantic models for API
class OrderCreate(BaseModel):
    items: List[OrderItem]
    shipping_address: ShippingAddress
    payment_method: str
    notes: Optional[str] = None

class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    payment_status: Optional[PaymentStatus] = None
    tracking_number: Optional[str] = None
    notes: Optional[str] = None

class OrderOut(BaseModel):
    id: str
    user_id: str
    items: List[OrderItem]
    shipping_address: ShippingAddress
    total_amount: float
    payment_method: str
    payment_status: PaymentStatus
    status: OrderStatus
    tracking_number: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime 