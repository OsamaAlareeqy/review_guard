import subprocess
import sys
import os
import asyncio
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

async def init_db():
    """Initialize database tables"""
    from app.database import engine, Base
    import app.models  # Import all models
    
    async with engine.begin() as conn:
        # Drop all tables (careful in production!)
        # await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ Database initialized!")

def main():
    print("🚀 Starting Google Maps Review Monitor...")
    
    # Initialize database
    asyncio.run(init_db())
    
    # Start FastAPI server
    print("📡 Starting API server at http://localhost:8000")
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload"
    ])

if __name__ == "__main__":
    main()