from fastapi import Request, Depends, HTTPException, Response
from app.client.main import router, templates
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.product import Product, ProductCreate, ProductResponse
from app.models.banner import Banner
from app.models.collection import Collection
from app.models.category import Category
from app.models.user import User, UserRole
from app.database import get_db
from datetime import datetime
import uuid
import secrets

async def get_or_create_guest_user(request: Request, response: Response, db: AsyncSession):
    """
    Check for existing user ID in cookies. If found, verify user exists in database.
    If not found or user doesn't exist, create a new guest user in the database.
    Returns the user ID.
    """
    # Check if user already has a user ID in cookies
    user_id_str = request.cookies.get("user_id")
    
    # If user ID exists in cookies, verify it exists in the database
    if user_id_str:
        try:
            user_id = uuid.UUID(user_id_str)
            query = select(User).where(User.id == user_id)
            result = await db.execute(query)
            user = result.scalar_one_or_none()
            
            # If user exists in database, return the user ID
            if user:
                return str(user.id)
        except (ValueError, TypeError):
            # Invalid UUID format in cookie, will create a new user
            pass
    
    # Create a new guest user if no valid user ID was found
    random_suffix = secrets.token_hex(6)
    guest_username = f"guest_{random_suffix}"
    
    # Create a new guest user
    new_guest_user = User(
        id=uuid.uuid4(),
        email=f"{guest_username}@guest.temporary",
        username=guest_username,
        is_active=True,
        role=UserRole.GUEST,
        is_guest=True
    )
    
    # Add to database
    db.add(new_guest_user)
    await db.commit()
    await db.refresh(new_guest_user)
    
    # Set the user ID in a cookie
    user_id = str(new_guest_user.id)
    response.set_cookie(key="user_id", value=user_id, httponly=True)
    
    return user_id

@router.get("/")
async def home(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    # Get or create guest user
    # user_id = await get_or_create_guest_user(request, response, db)
    
    # Fetch active banners for the home page
    banner_query = select(Banner).where(
        Banner.is_active == True,
        Banner.position.in_(["home_top", "home_middle", "home_bottom"])
    ).order_by(Banner.created_at.desc())
    result = await db.execute(banner_query)
    banners = result.scalars().all()
    
    # Fetch active categories
    category_query = select(Category).where(Category.is_active == True)
    result = await db.execute(category_query)
    categories = result.scalars().all()
    
    # Fetch active collections
    collection_query = select(Collection).where(Collection.is_active == True)
    result = await db.execute(collection_query)
    collections = result.scalars().all()

    # Fetch featured products
    featured_query = select(Product).where(
        Product.featured == True,
        Product.status == "published"
    )
    result = await db.execute(featured_query)
    featured_products = result.scalars().all()
    
    # Fetch all products
    product_query = select(Product)
    result = await db.execute(product_query)
    products = result.scalars().all()
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "products": products, 
            "banners": banners,
            "featured_products": featured_products,
            "categories": categories,
            "collections": collections,
 # Pass the user ID to the template
        }
    )

# Keep the rest of your routes as they are
@router.get("/product/{product_id}")
async def product_detail(request: Request, product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    query = select(Product).where(Product.id == product_id)
    result = await db.execute(query)
    product = result.scalar_one_or_none()
    
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return templates.TemplateResponse(
        "product_detail.html", 
        {
            "request": request, 
            "product": product
        }
    )

@router.post("/products/", response_model=ProductResponse)
async def create_product(product: ProductCreate, db: AsyncSession = Depends(get_db)):
    db_product = Product(**product.dict(), id=uuid.uuid4())
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product