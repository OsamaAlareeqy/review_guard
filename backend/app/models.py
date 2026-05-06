from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class UserRole(str, enum.Enum):
    FREE = "free"
    PRO = "pro"

class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"

class Business(Base):
    __tablename__ = "businesses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    google_maps_url = Column(String(500), nullable=False)
    business_name = Column(String(200), nullable=False)
    business_address = Column(String(500))
    place_id = Column(String(100), unique=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_scraped_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User", back_populates="businesses")
    reviews = relationship("Review", back_populates="business", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="business")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    full_name = Column(String(100))
    company_name = Column(String(100))
    role = Column(Enum(UserRole), default=UserRole.FREE)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Subscription
    stripe_customer_id = Column(String(100))
    subscription_status = Column(Enum(SubscriptionStatus), default=None)
    subscription_end_date = Column(DateTime(timezone=True))
    
    # Settings
    email_notifications = Column(Boolean, default=True)
    instant_alerts_enabled = Column(Boolean, default=False)
    daily_summary_enabled = Column(Boolean, default=True)
    
    # Relationships
    businesses = relationship("Business", back_populates="user")
    alerts = relationship("Alert", back_populates="user")

class Review(Base):
    __tablename__ = "reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    review_id = Column(String(100), unique=True, index=True)  # Google's review ID
    reviewer_name = Column(String(100))
    rating = Column(Float, nullable=False)  # 1-5 stars
    review_text = Column(Text)
    review_date = Column(DateTime(timezone=True))
    is_negative = Column(Boolean, default=False)
    is_processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # AI Analysis
    complaint_category = Column(String(50))
    urgency_score = Column(Integer, default=0)  # 1-10
    complaint_summary = Column(String(200))
    
    # Relationships
    business = relationship("Business", back_populates="reviews")
    alerts = relationship("Alert", back_populates="review")

class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    review_id = Column(Integer, ForeignKey("reviews.id"), nullable=False)
    alert_type = Column(String(20))  # 'instant' or 'daily'
    urgency_level = Column(String(20))  # 'low', 'medium', 'high', 'critical'
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    email_sent = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", back_populates="alerts")
    business = relationship("Business", back_populates="alerts")
    review = relationship("Review", back_populates="alerts")

class ScraperLog(Base):
    __tablename__ = "scraper_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    status = Column(String(20))  # 'success', 'failed', 'running'
    reviews_found = Column(Integer, default=0)
    reviews_new = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

# Update relationships
User.alerts = relationship("Alert", back_populates="user")
User.businesses = relationship("Business", back_populates="user")
Review.alerts = relationship("Alert", back_populates="review")