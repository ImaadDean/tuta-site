import asyncio
import httpx
from app.core.config import settings
from app.db.mongodb import init_db

async def migrate_banners():
    # Initialize database connection
    await init_db()
    
    # Create an HTTP client
    async with httpx.AsyncClient() as client:
        # Call the migration endpoint
        response = await client.post(
            f"{settings.BASE_URL}/admin/banner/api/banners/migrate-home-bottom",
            headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"Success: {result['message']}")
            print(f"Migrated {result['count']} banners")
        else:
            print(f"Error: {response.text}")

if __name__ == "__main__":
    asyncio.run(migrate_banners()) 