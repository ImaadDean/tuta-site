from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_db
from app.models.user import User, UserRole
from urllib.parse import quote

# Configuration settings remain the same
SECRET_KEY = "your-secret-key-here"  # You should use os.getenv() in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 525600  # Changed from 30 minutes to 1 year (365 days * 24 hours * 60 minutes)

# Configure password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

def validate_password(password: str) -> tuple[bool, str]:
    """
    Validates that a password meets the following requirements:
    - Length between 8 and 16 characters
    - Only allows special characters: @, #, $, %, and &
    
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    # Check length
    if len(password) < 8 or len(password) > 16:
        return False, "Password must be between 8 and 16 characters long"
    
    # Check for invalid special characters
    allowed_special_chars = {'@', '#', '$', '%', '&'}
    for char in password:
        if not char.isalnum() and char not in allowed_special_chars:
            return False, f"Only the following special characters are allowed: @, #, $, %, and &"
    
    return True, ""

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against a hashed password.
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """
    Validates and hashes a password.
    """
    try:
        # Validate password before hashing
        is_valid, error_message = validate_password(password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        
        return pwd_context.hash(password)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing password"
        )

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create access token"
        )


# Updated get_token_from_cookie function in jwt.py
async def get_token_from_cookie(request: Request) -> Optional[str]:
    """Extract the token from cookies with better error handling"""
    try:
        token = request.cookies.get("access_token")
        
        if not token:
            print("No access_token cookie found")
            return None
        
        # Strip 'Bearer ' prefix if present
        if token.startswith("Bearer "):
            token = token.replace("Bearer ", "")
            
        print(f"Token extracted from cookie: {token[:10]}...")
        return token
    except Exception as e:
        print(f"Error extracting token from cookie: {e}")
        return None

async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Try to get token from cookie if not in header
    if not token:
        token = await get_token_from_cookie(request)
        if not token:
            raise credentials_exception
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    try:
        # First try to find by exact ID match
        user = await User.find_one({"id": user_id})
        
        if user is None:
            # Some MongoDB drivers might store the ID differently
            user = await User.find_one({"_id": user_id})
            
        if user is None:
            raise credentials_exception
            
    except Exception:
        raise credentials_exception
        
    return user

async def get_current_active_admin(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != UserRole.ADMIN:
        # For non-admin users, redirect to login with error message
        response = RedirectResponse(
            url=f"/auth/login?error={quote('You do not have admin privileges.')}",
            status_code=303
        )
        response.delete_cookie("access_token")
        return response
    
    return current_user

async def is_logged_in(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> Optional[User]:
    """
    Check if a user is logged in and redirect based on role.
    
    This function can be used as a dependency in routes where you want to:
    1. Check if a user is already logged in
    2. Redirect them to the appropriate page based on their role
    
    Returns:
        None if the user is not logged in
        Raises HTTPException with RedirectResponse if user is logged in
    """
    # Get token from cookie
    token = request.cookies.get("access_token")
    
    # If no token, user is not logged in
    if not token or not token.startswith("Bearer "):
        return None
    
    token = token.replace("Bearer ", "")
    
    try:
        # Decode the token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        
        if user_id is None:
            return None
            
        # Get user from database
        user = await User.find_one({"id": user_id})
        
        if user is None:
            return None
            
        # User is logged in, redirect based on role
        redirect_url = "/admin" if user.role == UserRole.ADMIN else "/"
        
        # Raise an exception with the redirect response
        raise HTTPException(
            status_code=303,
            headers={"Location": redirect_url}
        )
            
    except (JWTError, ValueError):
        # Invalid token or UUID, user is not logged in
        return None

async def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> Optional[User]:
    """
    Similar to get_current_user, but does not raise an exception if the user is not authenticated.
    This enables guest checkout and other features where authentication is optional.
    
    Returns:
        User object if authenticated
        None if not authenticated
    """
    # Try to get token from cookie if not in header
    if not token:
        token = await get_token_from_cookie(request)
        if not token:
            print("No token found in cookie or header")
            return None
    
    try:
        print(f"Decoding token: {token[:10]}...")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            print("No user_id found in token payload")
            return None
        print(f"User ID from token: {user_id}")
    except JWTError as e:
        print(f"JWT decode error: {e}")
        return None
        
    try:
        print(f"Looking up user with ID: {user_id}")
        # Try different ways to find the user
        user = None
        
        # Method 1: Direct ID lookup
        user = await User.find_one({"id": user_id})
        
        # Method 2: Try with _id if method 1 fails
        if user is None:
            print("Trying with _id field")
            user = await User.find_one({"_id": user_id})
        
        # Method 3: Try with string comparison if methods 1 and 2 fail
        if user is None:
            print("Trying with string comparison")
            all_users = await User.find().to_list()
            for u in all_users:
                if str(u.id) == user_id:
                    user = u
                    print(f"Found user with string comparison: {u.username}")
                    break
        
        if user:
            print(f"Found user: {user.username}, role: {user.role}")
        else:
            print(f"No user found with ID: {user_id}")
            # Debug: Print all user IDs to see what's in the database
            all_users = await User.find().to_list()
            print(f"All user IDs in database: {[str(u.id) for u in all_users]}")
    except Exception as e:
        print(f"Database error when looking up user: {e}")
        return None
        
    return user