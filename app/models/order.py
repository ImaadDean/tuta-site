from beanie import Document, Link
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime, timezone
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
    PARTIAL_PAID = "partial_paid"
    FULLY_PAID = "fully_paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"

class VariantInfo(BaseModel):
    """Information about a product variant in an order"""
    id: str
    value: str
    price: int
    discount_percentage: Optional[float] = None

class OrderItem(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    total_price: float
    variant: Optional[VariantInfo] = None

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
    guest_email: Optional[str] = None  # For guest checkout
    guest_data: Optional[Dict[str, Any]] = None  # Additional guest user data
    items: List[OrderItem]
    shipping_address: ShippingAddress
    address_id: Optional[str] = None  # Reference to saved address if applicable
    total_amount: float
    payment_method: str
    amount_paid: float = 0
    payment_status: PaymentStatus = PaymentStatus.PENDING
    status: OrderStatus = OrderStatus.PENDING
    tracking_number: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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

    @property
    def created_at_formatted(self) -> str:
        """Return the created_at date formatted as 'YYYY-MM-DD'"""
        if isinstance(self.created_at, datetime):
            return self.created_at.strftime('%Y-%m-%d')
        return str(self.created_at)

    @property
    def created_at_time(self) -> str:
        """Return the created_at time formatted as 'HH:MM:SS'"""
        if isinstance(self.created_at, datetime):
            return self.created_at.strftime('%H:%M:%S')
        return ""

    @property
    def formatted_amount(self) -> str:
        """Return the total amount formatted with commas"""
        return f"{int(self.total_amount):,}"

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