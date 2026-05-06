from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./reviewmonitor.db"
    
    # JWT Authentication
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production-12345"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Email (optional for now)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL: str = ""
    
    # Stripe (optional for now)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLIC_KEY: str = ""
    PRO_PRICE_ID: str = "price_pro_monthly"
    
    # Scraper settings
    SCRAPE_INTERVAL_HOURS: int = 6
    MAX_REVIEWS_PER_BUSINESS: int = 100
    
    # Redis (optional for now)
    REDIS_URL: str = "redis://localhost:6379"
    
    class Config:
        env_file = ".env"

settings = Settings()