import asyncio
import getpass
from app.database import initialize_mongodb
from app.models.user import User, UserRole, UserStatus
from app.auth.jwt import get_password_hash

async def create_admin_user():
    """Prompt for admin user details and create an admin user"""
    
    print("=== Admin User Creation Tool ===")
    
    # Prompt for user details
    email = input("Enter admin email: ").strip()
    username = input("Enter admin username: ").strip()
    
    # Validate input
    if not email or not username:
        print("Error: Email and username are required!")
        return
    
    # Prompt for password (hidden input)
    while True:
        password = getpass.getpass("Enter admin password (8-16 characters): ")
        confirm_password = getpass.getpass("Confirm password: ")
        
        if password != confirm_password:
            print("Passwords do not match! Please try again.")
            continue
            
        if len(password) < 8 or len(password) > 16:
            print("Password must be between 8 and 16 characters!")
            continue
            
        break
    
    try:
        # Initialize MongoDB connection
        await initialize_mongodb()
        print("Connected to database successfully.")
        
        # Check if user already exists
        existing_user = await User.find_one({"$or": [
            {"email": email},
            {"username": username}
        ]})
        
        if existing_user:
            print(f"User with email '{email}' or username '{username}' already exists.")
            
            # If user exists but is not admin, ask if we should make them admin
            if existing_user.role != UserRole.ADMIN:
                make_admin = input(f"User exists but is not admin. Make {username} an admin? (y/n): ").strip().lower()
                if make_admin == 'y':
                    existing_user.role = UserRole.ADMIN
                    await existing_user.save()
                    print(f"User {username} has been made an admin.")
                else:
                    print("Operation cancelled.")
                    return
            else:
                print(f"User {username} is already an admin.")
                return
        
        # Hash the password
        hashed_password = get_password_hash(password)
        
        # Create new admin user
        admin_user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            is_active=True
        )
        
        # Save to database
        await admin_user.insert()
        print(f"Admin user '{username}' created successfully!")
        
        # Verify creation
        created_user = await User.find_one({"username": username})
        if created_user and created_user.role == UserRole.ADMIN:
            print("Verification successful: User is an admin.")
        else:
            print("Warning: Could not verify admin status.")
            
    except Exception as e:
        print(f"Error creating admin user: {str(e)}")
    finally:
        print("Admin creation process completed.")

if __name__ == "__main__":
    asyncio.run(create_admin_user())