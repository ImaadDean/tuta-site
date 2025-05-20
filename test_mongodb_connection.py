"""
Simple script to test MongoDB connection.
Run this script to verify that your MongoDB connection works.
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys

async def test_connection():
    # Connection parameters
    username = "imaad"
    password = "Ertdfgxc"
    host = "129.213.8.146"
    port = 27017
    database = "perfumes_more"
    
    # Try different connection string formats
    connection_strings = [
        # Format 1: Standard format with database
        f"mongodb://{username}:{password}@{host}:{port}/{database}",
        
        # Format 2: Standard format without database
        f"mongodb://{username}:{password}@{host}:{port}",
        
        # Format 3: With authSource=admin
        f"mongodb://{username}:{password}@{host}:{port}/?authSource=admin",
        
        # Format 4: With authSource=admin and database
        f"mongodb://{username}:{password}@{host}:{port}/{database}?authSource=admin",
        
        # Format 5: With slash before host (from your example)
        f"mongodb://{username}:{password}@/{host}:{port}",
        
        # Format 6: Without authentication
        f"mongodb://{host}:{port}"
    ]
    
    # Try each connection string
    for i, uri in enumerate(connection_strings):
        print(f"\nTrying connection format {i+1}: {uri.replace(password, '********')}")
        try:
            # Create client
            client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
            
            # Force a connection to verify it works
            server_info = await client.admin.command('ping')
            print(f"✅ Connection successful! Server info: {server_info}")
            
            # Try to list databases
            try:
                databases = await client.list_database_names()
                print(f"📋 Available databases: {databases}")
            except Exception as e:
                print(f"❌ Could not list databases: {str(e)}")
            
            # If we specified a database, try to access it
            if database:
                try:
                    db = client[database]
                    collections = await db.list_collection_names()
                    print(f"📋 Collections in {database}: {collections}")
                except Exception as e:
                    print(f"❌ Could not list collections in {database}: {str(e)}")
            
            # Close the connection
            client.close()
            
        except Exception as e:
            print(f"❌ Connection failed: {str(e)}")
    
    print("\nConnection test completed.")

if __name__ == "__main__":
    print("MongoDB Connection Test")
    print("======================")
    asyncio.run(test_connection())
