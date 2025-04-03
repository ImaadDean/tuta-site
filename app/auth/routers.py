from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_db
from app.models.user import User, UserRole
from app.auth.jwt import (
    verify_password,
    get_password_hash,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    get_current_user
)
from app.auth.email import (
    send_password_reset_email,
    create_password_reset_token,
    verify_password_reset_token,
    mark_token_as_used
)
from datetime import timedelta
import uuid
from app.auth import router, templates
from typing import Optional
from pydantic import EmailStr
from app.auth.jwt import is_logged_in

@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(is_logged_in)
):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None}
    )

@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(is_logged_in)
):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "error": None}
    )


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    phone_number: str = Form(None),  # Added phone number field
    password: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Check if email already exists
        existing_email_user = await User.find_one({"email": email})
        if existing_email_user:
            return templates.TemplateResponse(
                "register.html",
                {
                    "request": request,
                    "error": "Email already registered"
                },
                status_code=400
            )
        
        # Check if username already exists
        existing_username_user = await User.find_one({"username": username})
        if existing_username_user:
            return templates.TemplateResponse(
                "register.html",
                {
                    "request": request,
                    "error": "Username already taken"
                },
                status_code=400
            )
        
        # Create new user
        hashed_password = get_password_hash(password)
        
        # Create Beanie document
        new_user = User(
            id=str(uuid.uuid4()),
            email=email,
            username=username,
            phone_number=phone_number,
            hashed_password=hashed_password,
            role=UserRole.CLIENT,
            is_active=True,
            profile_picture=None
        )
        
        # Insert the user
        await new_user.insert()
        
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        print(f"Registration error: {e}")
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Could not register user"
            },
            status_code=500
        )
    
@router.post("/login")
async def login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        print(f"Login attempt for user: {login}")
        
        # Find user by email (case-insensitive) or username (case-sensitive)
        # MongoDB doesn't support case-insensitive search directly in queries like SQLAlchemy
        # We'll use a regex for case-insensitive email search
        user = await User.find_one({"$or": [
            {"email": {"$regex": f"^{login}$", "$options": "i"}},  # Case-insensitive email match
            {"username": login}  # Case-sensitive username match
        ]})

        if not user:
            print(f"No user found with login: {login}")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "No account found with this email or username"
                },
                status_code=401
            )

        if not verify_password(password, user.hashed_password):
            print(f"Invalid password for user: {login}")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Incorrect password"
                },
                status_code=401
            )
        
        # Check if the account is active
        if not user.is_active:
            print(f"Inactive account for user: {login}")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Your account has been deactivated. Please contact support for assistance."
                },
                status_code=401
            )
        
        print(f"User authenticated: {user.username}, ID: {user.id}, Role: {user.role}")
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=access_token_expires
        )
        
        print(f"Created token for user {user.username}, first 10 chars: {access_token[:10]}...")
        
        # Set redirect based on role
        redirect_url = "/admin/" if user.role == UserRole.ADMIN else "/"
        print(f"Redirecting user to: {redirect_url}")
        
        response = RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_303_SEE_OTHER
        )
        
        # Set the token in cookies
        response.set_cookie(
            key="access_token",
            value=f"Bearer {access_token}",
            httponly=True,
            max_age=31536000,  # 1 year in seconds (365 days * 24 hours * 60 minutes * 60 seconds)
            expires=31536000,
            samesite="lax",
            secure=False  # Set to True in production with HTTPS
        )
        
        print(f"Cookie set for {user.username}")
        return response

    except Exception as e:
        print(f"Login error: {e}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "An error occurred during login. Please try again."
            },
            status_code=500
        )

@router.get("/logout")
async def logout():
    response = RedirectResponse(
        url="/",
        status_code=status.HTTP_303_SEE_OTHER
    )
    
    # Clear the access token cookie
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax"
    )
    
    return response

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(
    request: Request,
    success: Optional[str] = None
):
    return templates.TemplateResponse(
        "forgot-password.html",
        {"request": request, "error": None, "success": success}
    )

@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password(
    request: Request,
    email: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Check if user exists
        user = await User.find_one({"email": {"$regex": f"^{email}$", "$options": "i"}})
        
        if not user:
            return templates.TemplateResponse(
                "forgot-password.html",
                {
                    "request": request,
                    "error": "No account found with this email address."
                }
            )
        
        # Generate password reset token
        token = await create_password_reset_token(user.email, db)
        
        # Create reset URL
        reset_url = f"{request.base_url}auth/reset-password?token={token}"
        
        # Send password reset email
        await send_password_reset_email(user.email, reset_url, db)
        
        return templates.TemplateResponse(
            "forgot-password.html",
            {
                "request": request,
                "success": "A password reset link has been sent to your email address."
            }
        )
        
    except Exception as e:
        print(f"Password reset request error: {e}")
        return templates.TemplateResponse(
            "forgot-password.html",
            {
                "request": request,
                "error": "An error occurred. Please try again later."
            },
            status_code=500
        )

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token: str = Query(...),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Verify token without revealing if it's valid or not
        await verify_password_reset_token(token, db)
        
        return templates.TemplateResponse(
            "reset-password.html",
            {"request": request, "token": token, "error": None}
        )
    except Exception:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid or expired password reset link. Please request a new one."
            }
        )

@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        # Check if passwords match
        if password != confirm_password:
            return templates.TemplateResponse(
                "reset-password.html",
                {
                    "request": request,
                    "token": token,
                    "error": "Passwords do not match"
                }
            )
        
        # Verify token and get email
        email = await verify_password_reset_token(token, db)
        
        # Find user by email
        user = await User.find_one({"email": {"$regex": f"^{email}$", "$options": "i"}})
        
        if not user:
            return templates.TemplateResponse(
                "reset-password.html",
                {
                    "request": request,
                    "token": token,
                    "error": "User not found"
                }
            )
        
        # Update password
        user.hashed_password = get_password_hash(password)
        await user.save()
        
        # Mark token as used
        await mark_token_as_used(token, db)
        
        # Redirect to login page with success message
        return RedirectResponse(
            url="/auth/login?success=Your password has been reset successfully. Please log in with your new password.",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        
    except Exception as e:
        print(f"Password reset error: {e}")
        return templates.TemplateResponse(
            "reset-password.html",
            {
                "request": request,
                "token": token,
                "error": "An error occurred. Please try again later."
            },
            status_code=500
        ) 