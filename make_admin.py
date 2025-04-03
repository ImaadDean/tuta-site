import asyncio
from app.database import initialize_mongodb
from app.models.user import User, UserRole

async def make_user_admin(username):
    # Initialize MongoDB connection
    await initialize_mongodb()
    
    # Find the user
    user = await User.find_one({"username": username})
    
    if not user:
        print(f"User {username} not found")
        return
    
    print(f"Found user: {user.username}, current role: {user.role}")
    
    # Update user role to admin
    user.role = UserRole.ADMIN
    await user.save()
    
    print(f"Updated {user.username} to admin role")
    
    # Verify all users in the system
    users = await User.find_all().to_list()
    print(f"All users in the system ({len(users)}):")
    for u in users:
        print(f"- {u.username}: {u.role} (ID: {u.id})")

if __name__ == "__main__":
    # Replace 'username_to_update' with the actual username you want to make admin
    asyncio.run(make_user_admin("imaad")) 