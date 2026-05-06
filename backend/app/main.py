from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import sqlite3
import hashlib
import jwt
import uvicorn
from contextlib import contextmanager
import os

# Create FastAPI app
app = FastAPI(title="Google Maps Review Monitor")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT settings
SECRET_KEY = "your-super-secret-key-change-this-in-production-12345"
ALGORITHM = "HS256"

# Database setup
DB_PATH = "reviewmonitor.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            company_name TEXT,
            role TEXT DEFAULT 'free',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Businesses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            google_maps_url TEXT NOT NULL,
            business_name TEXT NOT NULL,
            business_address TEXT,
            place_id TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_scraped_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Reviews table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            review_id TEXT UNIQUE,
            reviewer_name TEXT,
            rating REAL,
            review_text TEXT,
            review_date TIMESTAMP,
            is_negative INTEGER DEFAULT 0,
            complaint_category TEXT,
            urgency_score INTEGER DEFAULT 0,
            complaint_summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (business_id) REFERENCES businesses (id)
        )
    ''')
    
    # Alerts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            business_id INTEGER NOT NULL,
            review_id INTEGER NOT NULL,
            alert_type TEXT,
            urgency_level TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            email_sent INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (business_id) REFERENCES businesses (id),
            FOREIGN KEY (review_id) REFERENCES reviews (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

# Pydantic models
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class BusinessCreate(BaseModel):
    google_maps_url: str
    business_name: Optional[str] = None

class BusinessResponse(BaseModel):
    id: int
    google_maps_url: str
    business_name: str
    is_active: bool
    created_at: str
    total_reviews: int = 0
    negative_count: int = 0

class ReviewResponse(BaseModel):
    id: int
    reviewer_name: str
    rating: float
    review_text: str
    review_date: str
    complaint_category: Optional[str]
    urgency_score: Optional[int]

class DashboardStats(BaseModel):
    total_negative_reviews: int
    total_businesses: int
    critical_alerts: int
    reputation_status: str
    recent_negative_reviews: List[Dict]
    top_complaint_categories: Dict

# Helper functions
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def create_token(user_id: int, email: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_current_user(authorization: str = None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.replace("Bearer ", "")
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, full_name, role FROM users WHERE id = ?", (payload['sub'],))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return dict(user)

# API Routes
@app.post("/api/auth/signup")
async def signup(user: UserCreate):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute("SELECT id FROM users WHERE email = ?", (user.email,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    try:
        cursor.execute(
            "INSERT INTO users (email, password, full_name, company_name, role) VALUES (?, ?, ?, ?, ?)",
            (user.email, hash_password(user.password), user.full_name, user.company_name, "free")
        )
        conn.commit()
        return {"message": "User created successfully", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/auth/login")
async def login(user: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, email, password, role FROM users WHERE email = ?", (user.email,))
    db_user = cursor.fetchone()
    conn.close()
    
    if not db_user or not verify_password(user.password, db_user['password']):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(db_user['id'], db_user['email'], db_user['role'])
    return {"access_token": token, "token_type": "bearer", "user": dict(db_user)}

@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

@app.post("/api/businesses")
async def add_business(business: BusinessCreate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    business_name = business.business_name or f"Business {datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    cursor.execute(
        "INSERT INTO businesses (user_id, google_maps_url, business_name) VALUES (?, ?, ?)",
        (current_user['id'], business.google_maps_url, business_name)
    )
    conn.commit()
    business_id = cursor.lastrowid
    conn.close()
    
    return {"message": "Business added successfully", "id": business_id}

@app.get("/api/businesses")
async def get_businesses(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.*, 
               COUNT(r.id) as total_reviews,
               SUM(CASE WHEN r.is_negative = 1 THEN 1 ELSE 0 END) as negative_count
        FROM businesses b
        LEFT JOIN reviews r ON b.id = r.business_id
        WHERE b.user_id = ? AND b.is_active = 1
        GROUP BY b.id
        ORDER BY b.created_at DESC
    ''', (current_user['id'],))
    
    businesses = cursor.fetchall()
    conn.close()
    
    return [dict(b) for b in businesses]

@app.delete("/api/businesses/{business_id}")
async def delete_business(business_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify ownership
    cursor.execute("SELECT id FROM businesses WHERE id = ? AND user_id = ?", (business_id, current_user['id']))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Business not found")
    
    cursor.execute("UPDATE businesses SET is_active = 0 WHERE id = ?", (business_id,))
    conn.commit()
    conn.close()
    
    return {"message": "Business deleted successfully"}

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    # Get total negative reviews
    cursor.execute('''
        SELECT COUNT(*) as count FROM reviews r
        JOIN businesses b ON r.business_id = b.id
        WHERE b.user_id = ? AND r.is_negative = 1
    ''', (current_user['id'],))
    total_negative = cursor.fetchone()['count']
    
    # Get total businesses
    cursor.execute("SELECT COUNT(*) as count FROM businesses WHERE user_id = ? AND is_active = 1", (current_user['id'],))
    total_businesses = cursor.fetchone()['count']
    
    # Get critical alerts count
    cursor.execute('''
        SELECT COUNT(*) as count FROM alerts a
        JOIN businesses b ON a.business_id = b.id
        WHERE b.user_id = ? AND a.urgency_level = 'critical'
    ''', (current_user['id'],))
    critical_alerts = cursor.fetchone()['count']
    
    # Get recent negative reviews
    cursor.execute('''
        SELECT r.*, b.business_name 
        FROM reviews r
        JOIN businesses b ON r.business_id = b.id
        WHERE b.user_id = ? AND r.is_negative = 1
        ORDER BY r.review_date DESC LIMIT 10
    ''', (current_user['id'],))
    recent_reviews = cursor.fetchall()
    
    # Get complaint categories
    cursor.execute('''
        SELECT complaint_category, COUNT(*) as count
        FROM reviews r
        JOIN businesses b ON r.business_id = b.id
        WHERE b.user_id = ? AND r.is_negative = 1 AND r.complaint_category IS NOT NULL
        GROUP BY complaint_category
        ORDER BY count DESC
    ''', (current_user['id'],))
    categories = cursor.fetchall()
    
    # Determine reputation status
    if total_negative == 0:
        reputation_status = "Stable"
    elif total_negative < 5:
        reputation_status = "Warning"
    else:
        reputation_status = "Critical"
    
    conn.close()
    
    return {
        "total_negative_reviews": total_negative,
        "total_businesses": total_businesses,
        "critical_alerts": critical_alerts,
        "reputation_status": reputation_status,
        "recent_negative_reviews": [dict(r) for r in recent_reviews],
        "top_complaint_categories": {c['complaint_category']: c['count'] for c in categories}
    }

@app.get("/api/reviews")
async def get_reviews(business_id: Optional[int] = None, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    if business_id:
        cursor.execute('''
            SELECT r.*, b.business_name
            FROM reviews r
            JOIN businesses b ON r.business_id = b.id
            WHERE b.user_id = ? AND r.business_id = ? AND r.is_negative = 1
            ORDER BY r.review_date DESC
        ''', (current_user['id'], business_id))
    else:
        cursor.execute('''
            SELECT r.*, b.business_name
            FROM reviews r
            JOIN businesses b ON r.business_id = b.id
            WHERE b.user_id = ? AND r.is_negative = 1
            ORDER BY r.review_date DESC LIMIT 50
        ''', (current_user['id'],))
    
    reviews = cursor.fetchall()
    conn.close()
    
    return [dict(r) for r in reviews]

@app.get("/api/alerts")
async def get_alerts(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.*, b.business_name, r.review_text, r.rating
        FROM alerts a
        JOIN businesses b ON a.business_id = b.id
        JOIN reviews r ON a.review_id = r.id
        WHERE b.user_id = ?
        ORDER BY a.sent_at DESC LIMIT 50
    ''', (current_user['id'],))
    
    alerts = cursor.fetchall()
    conn.close()
    
    return [dict(a) for a in alerts]

# Serve static files
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/js", StaticFiles(directory=os.path.join(frontend_path, "js")), name="js")

@app.get("/")
@app.get("/{full_path:path}")
async def serve_frontend(full_path: str = ""):
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
    
    # Map routes to HTML files
    html_files = {
        "": "index.html",
        "login": "login.html",
        "signup": "signup.html",
        "dashboard": "dashboard.html",
        "businesses": "businesses.html",
        "alerts": "alerts.html",
        "settings": "settings.html"
    }
    
    if full_path in html_files:
        file_path = os.path.join(frontend_dir, html_files[full_path])
        if os.path.exists(file_path):
            return FileResponse(file_path)
    
    # Check if it's a direct file request
    file_path = os.path.join(frontend_dir, full_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Default to index.html
    return FileResponse(os.path.join(frontend_dir, "index.html"))

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()
    print("🚀 Server is ready!")
    print("📍 Visit http://localhost:8000")
    print("📊 Dashboard: http://localhost:8000/dashboard")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)