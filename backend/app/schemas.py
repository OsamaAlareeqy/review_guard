from pydantic import BaseModel, EmailStr, HttpUrl
from datetime import datetime
from typing import Optional, List
from enum import Enum

class UserRole(str, Enum):
    FREE = "free"
    PRO = "pro"

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    company_name: Optional[str]
    role: UserRole
    created_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class BusinessCreate(BaseModel):
    google_maps_url: HttpUrl
    business_name: Optional[str] = None

class BusinessResponse(BaseModel):
    id: int
    google_maps_url: str
    business_name: str
    business_address: Optional[str]
    is_active: bool
    created_at: datetime
    last_scraped_at: Optional[datetime]
    negative_review_count: Optional[int] = 0
    total_reviews: Optional[int] = 0
    
    class Config:
        from_attributes = True

class ReviewResponse(BaseModel):
    id: int
    reviewer_name: str
    rating: float
    review_text: str
    review_date: datetime
    complaint_category: Optional[str]
    urgency_score: Optional[int]
    complaint_summary: Optional[str]
    
    class Config:
        from_attributes = True

class AlertResponse(BaseModel):
    id: int
    business_name: str
    review_text: str
    rating: float
    urgency_level: str
    alert_type: str
    sent_at: datetime
    
    class Config:
        from_attributes = True

class DashboardStats(BaseModel):
    total_negative_reviews: int
    total_businesses: int
    critical_alerts: int
    reputation_status: str  # 'Stable', 'Warning', 'Critical'
    recent_negative_reviews: List[ReviewResponse]
    top_complaint_categories: dict
    alerts_by_urgency: dict

class SubscriptionCreate(BaseModel):
    payment_method_id: str

class SubscriptionResponse(BaseModel):
    status: str
    plan: str
    expires_at: Optional[datetime]