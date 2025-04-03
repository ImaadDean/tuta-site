import uuid
from jose import jwt
from datetime import datetime, timedelta
from app.utils.email import send_email
from pydantic import EmailStr
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.token import PasswordResetToken, PasswordResetTokenCreate
from app.models.user import User
from app.auth import templates as auth_templates

# Configuration settings
SECRET_KEY = "your-secret-key-here"  # You should use os.getenv() in production
ALGORITHM = "HS256"
RESET_TOKEN_EXPIRE_MINUTES = 30

async def create_password_reset_token(email: str, db: AsyncIOMotorDatabase) -> str:
    # Find the user
    user = await User.find_one({"email": email})
    if not user:
        raise ValueError("User not found")
    
    # Invalidate any existing tokens for this user
    existing_tokens = await PasswordResetToken.find(
        {
            "user_id": user.id,
            "is_used": False,
            "expires_at": {"$gt": datetime.utcnow()}
        }
    ).to_list()
    
    for token_record in existing_tokens:
        token_record.is_used = True
        await token_record.save()
    
    # Create expiration time
    expires_delta = timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + expires_delta
    
    # Create token payload
    to_encode = {
        "sub": email,
        "exp": expire,
        "type": "password_reset",
        "jti": str(uuid.uuid4())
    }
    
    # Generate the JWT token
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    # Store the token in the database
    token_record = PasswordResetToken(
        user_id=user.id,
        token=encoded_jwt,
        created_at=datetime.utcnow(),
        expires_at=expire,
        is_used=False
    )
    
    await token_record.insert()
    
    return encoded_jwt

async def verify_password_reset_token(token: str, db: AsyncIOMotorDatabase) -> str:
    try:
        # Decode the token to verify it's valid
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("type") != "password_reset":
            raise ValueError("Invalid token type")
        
        email: str = payload.get("sub")
        if email is None:
            raise ValueError("Invalid token")
        
        # Find the token in the database
        token_record = await PasswordResetToken.find_one(
            {
                "token": token,
                "is_used": False,
                "expires_at": {"$gt": datetime.utcnow()}
            }
        )
        
        if not token_record:
            raise ValueError("Token not found or already used")
        
        return email
    except jwt.JWTError:
        raise ValueError("Invalid token")

async def mark_token_as_used(token: str, db: AsyncIOMotorDatabase) -> None:
    token_record = await PasswordResetToken.find_one({"token": token})
    
    if token_record:
        token_record.is_used = True
        await token_record.save()

async def send_password_reset_email(email: EmailStr, reset_url: str, db: AsyncIOMotorDatabase):
    # Get the user from the database to include their name
    user = await User.find_one({"email": email})
    
    subject = "Password Reset Request"
    recipients = [email]
    body = f"Click the following link to reset your password: {reset_url}"
    
    # Render the HTML template with user name
    html_body = auth_templates.get_template("password-reset.html").render(
        reset_url=reset_url,
        username=user.username if user else "User"
    )
    
    await send_email(subject, recipients, body, html_body)