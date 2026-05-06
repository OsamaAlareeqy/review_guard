from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import sqlite3
import hashlib
import secrets
import uvicorn
import os

# Get the current directory for database
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reviewmonitor.db")

app = FastAPI(title="Google Maps Review Monitor")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session store
sessions = {}

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables with correct schema"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Users table - with correct column names
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Reviews table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                reviewer_name TEXT,
                rating REAL,
                review_text TEXT,
                review_date TIMESTAMP,
                is_negative INTEGER DEFAULT 0,
                complaint_category TEXT,
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
                email_sent INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (business_id) REFERENCES businesses (id),
                FOREIGN KEY (review_id) REFERENCES reviews (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ Database initialized with correct schema at:", DB_PATH)
        return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

# Models
class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: str
    password: str

class BusinessCreate(BaseModel):
    google_maps_url: str
    business_name: Optional[str] = None

# Helper functions
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def get_current_user(authorization: str = None):
    if not authorization:
        raise HTTPException(401, "Not authenticated")
    token = authorization.replace("Bearer ", "")
    user_id = sessions.get(token)
    if not user_id:
        raise HTTPException(401, "Invalid session")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, full_name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(401, "User not found")
    return dict(user)

# API Routes
@app.post("/api/auth/signup")
async def signup(user: UserCreate):
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (user.email,))
        if cursor.fetchone():
            raise HTTPException(400, "Email already registered")
        
        # Create user - using correct column names
        cursor.execute(
            "INSERT INTO users (email, password, full_name) VALUES (?, ?, ?)",
            (user.email, hash_password(user.password), user.full_name)
        )
        conn.commit()
        conn.close()
        return {"success": True, "message": "User created successfully"}
    except Exception as e:
        print(f"Signup error: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/auth/login")
async def login(user: UserLogin):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, full_name, password FROM users WHERE email = ?", (user.email,))
        db_user = cursor.fetchone()
        conn.close()
        
        if not db_user or not verify_password(user.password, db_user['password']):
            raise HTTPException(401, "Invalid credentials")
        
        token = secrets.token_urlsafe(32)
        sessions[token] = db_user['id']
        return {
            "access_token": token, 
            "token_type": "bearer", 
            "user": {"id": db_user['id'], "email": db_user['email'], "full_name": db_user['full_name']}
        }
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(500, str(e))

@app.get("/api/auth/me")
async def get_me(authorization: str = None):
    return get_current_user(authorization)

@app.post("/api/businesses")
async def add_business(business: BusinessCreate, authorization: str = None):
    user = get_current_user(authorization)
    conn = get_db()
    cursor = conn.cursor()
    name = business.business_name or f"Business {datetime.now().strftime('%Y%m%d%H%M%S')}"
    cursor.execute(
        "INSERT INTO businesses (user_id, google_maps_url, business_name) VALUES (?, ?, ?)",
        (user['id'], business.google_maps_url, name)
    )
    conn.commit()
    biz_id = cursor.lastrowid
    conn.close()
    return {"id": biz_id, "message": "Business added successfully"}

@app.get("/api/businesses")
async def get_businesses(authorization: str = None):
    user = get_current_user(authorization)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM businesses WHERE user_id = ? ORDER BY created_at DESC", (user['id'],))
    businesses = cursor.fetchall()
    conn.close()
    return [dict(b) for b in businesses]

@app.delete("/api/businesses/{business_id}")
async def delete_business(business_id: int, authorization: str = None):
    user = get_current_user(authorization)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM businesses WHERE id = ? AND user_id = ?", (business_id, user['id']))
    conn.commit()
    conn.close()
    return {"message": "Business deleted successfully"}

@app.get("/api/dashboard/stats")
async def get_stats(authorization: str = None):
    user = get_current_user(authorization)
    conn = get_db()
    cursor = conn.cursor()
    
    # Get total businesses
    cursor.execute("SELECT COUNT(*) as count FROM businesses WHERE user_id = ?", (user['id'],))
    total_businesses = cursor.fetchone()['count']
    
    # Get total negative reviews
    cursor.execute('''
        SELECT COUNT(*) as count FROM reviews r
        JOIN businesses b ON r.business_id = b.id
        WHERE b.user_id = ? AND r.is_negative = 1
    ''', (user['id'],))
    total_negative = cursor.fetchone()['count']
    
    # Get critical alerts
    cursor.execute('''
        SELECT COUNT(*) as count FROM alerts a
        JOIN businesses b ON a.business_id = b.id
        WHERE b.user_id = ? AND a.urgency_level = 'critical'
    ''', (user['id'],))
    critical_alerts = cursor.fetchone()['count']
    
    conn.close()
    
    # Determine reputation status
    if total_negative == 0:
        reputation_status = "Stable"
    elif total_negative < 5:
        reputation_status = "Warning"
    else:
        reputation_status = "Critical"
    
    return {
        "total_negative_reviews": total_negative,
        "total_businesses": total_businesses,
        "critical_alerts": critical_alerts,
        "reputation_status": reputation_status,
        "recent_negative_reviews": [],
        "top_complaint_categories": {}
    }

@app.get("/api/alerts")
async def get_alerts(authorization: str = None):
    user = get_current_user(authorization)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.*, b.business_name, r.review_text, r.rating
        FROM alerts a
        JOIN businesses b ON a.business_id = b.id
        JOIN reviews r ON a.review_id = r.id
        WHERE b.user_id = ?
        ORDER BY a.sent_at DESC LIMIT 50
    ''', (user['id'],))
    alerts = cursor.fetchall()
    conn.close()
    return [dict(a) for a in alerts]

# HTML Pages
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Login - Review Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .card {
            background: white;
            border-radius: 16px;
            padding: 40px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { text-align: center; margin-bottom: 30px; color: #333; }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            margin-top: 20px;
        }
        .link { text-align: center; margin-top: 20px; color: #666; }
        .link a { color: #667eea; text-decoration: none; }
        .error { color: #ef4444; margin-top: 10px; text-align: center; }
        .success { color: #10b981; margin-top: 10px; text-align: center; }
    </style>
</head>
<body>
    <div class="card">
        <h1>🔐 Login</h1>
        <input type="email" id="email" placeholder="Email">
        <input type="password" id="password" placeholder="Password">
        <button onclick="login()">Login</button>
        <div class="link">Don't have an account? <a href="/signup">Sign up</a></div>
        <div id="message" class="error"></div>
    </div>
    <script>
        async function login() {
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const messageDiv = document.getElementById('message');
            
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            
            if (res.ok) {
                const data = await res.json();
                localStorage.setItem('token', data.access_token);
                messageDiv.className = 'success';
                messageDiv.innerText = 'Login successful! Redirecting...';
                setTimeout(() => window.location.href = '/dashboard', 1000);
            } else {
                messageDiv.className = 'error';
                messageDiv.innerText = 'Invalid email or password';
            }
        }
    </script>
</body>
</html>
"""

SIGNUP_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Sign Up - Review Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .card {
            background: white;
            border-radius: 16px;
            padding: 40px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { text-align: center; margin-bottom: 30px; color: #333; }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            margin-top: 20px;
        }
        .link { text-align: center; margin-top: 20px; color: #666; }
        .link a { color: #667eea; text-decoration: none; }
        .message { margin-top: 10px; text-align: center; }
        .error { color: #ef4444; }
        .success { color: #10b981; }
    </style>
</head>
<body>
    <div class="card">
        <h1>📝 Create Account</h1>
        <input type="text" id="name" placeholder="Full Name">
        <input type="email" id="email" placeholder="Email">
        <input type="password" id="password" placeholder="Password">
        <button onclick="signup()">Sign Up</button>
        <div class="link">Already have an account? <a href="/login">Login</a></div>
        <div id="message" class="message"></div>
    </div>
    <script>
        async function signup() {
            const name = document.getElementById('name').value;
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const messageDiv = document.getElementById('message');
            
            if (!name || !email || !password) {
                messageDiv.className = 'message error';
                messageDiv.innerText = 'Please fill in all fields';
                return;
            }
            
            const res = await fetch('/api/auth/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, full_name: name })
            });
            
            if (res.ok) {
                messageDiv.className = 'message success';
                messageDiv.innerText = 'Account created successfully! Redirecting to login...';
                setTimeout(() => window.location.href = '/login', 2000);
            } else {
                const data = await res.json();
                messageDiv.className = 'message error';
                messageDiv.innerText = data.detail || 'Signup failed. Email may already exist.';
            }
        }
    </script>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard - Review Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: white;
            border-radius: 12px;
            padding: 20px 30px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 { color: #333; font-size: 24px; }
        .logout-btn {
            background: #ef4444;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
        }
        .nav {
            background: white;
            padding: 15px 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            display: flex;
            gap: 20px;
        }
        .nav a {
            color: #666;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 8px;
        }
        .nav a:hover, .nav a.active { background: #667eea; color: white; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .stat-value { font-size: 36px; font-weight: bold; color: #667eea; }
        .stat-label { color: #666; margin-top: 5px; }
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        .stable { background: #10b981; color: white; }
        .warning { background: #f59e0b; color: white; }
        .critical { background: #ef4444; color: white; }
        .welcome {
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Review Monitor Dashboard</h1>
            <button class="logout-btn" onclick="logout()">Logout</button>
        </div>
        <div class="nav">
            <a href="/dashboard" class="active">Dashboard</a>
            <a href="/businesses">Businesses</a>
            <a href="/alerts">Alerts</a>
        </div>
        <div class="welcome" id="welcomeMsg"></div>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="negativeCount">0</div>
                <div class="stat-label">Negative Reviews</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="businessCount">0</div>
                <div class="stat-label">Businesses</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="alertCount">0</div>
                <div class="stat-label">Critical Alerts</div>
            </div>
            <div class="stat-card">
                <div class="stat-value"><span id="statusBadge" class="status-badge stable">Stable</span></div>
                <div class="stat-label">Reputation Status</div>
            </div>
        </div>
    </div>
    <script>
        const token = localStorage.getItem('token');
        if (!token) window.location.href = '/login';
        
        async function apiCall(endpoint) {
            const res = await fetch('/api' + endpoint, {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            if (res.status === 401) { 
                localStorage.removeItem('token'); 
                window.location.href = '/login';
                return null;
            }
            return res.json();
        }
        
        async function loadDashboard() {
            const stats = await apiCall('/dashboard/stats');
            if (stats) {
                document.getElementById('negativeCount').innerText = stats.total_negative_reviews || 0;
                document.getElementById('businessCount').innerText = stats.total_businesses || 0;
                document.getElementById('alertCount').innerText = stats.critical_alerts || 0;
                const badge = document.getElementById('statusBadge');
                const status = stats.reputation_status || 'Stable';
                badge.innerText = status;
                badge.className = 'status-badge ' + status.toLowerCase();
            }
        }
        
        async function loadUser() {
            const user = await apiCall('/auth/me');
            if (user && user.full_name) {
                document.getElementById('welcomeMsg').innerHTML = `<h2>Welcome back, ${user.full_name}! 👋</h2><p>Your business reputation is being monitored.</p>`;
            }
        }
        
        function logout() { 
            localStorage.removeItem('token'); 
            window.location.href = '/login'; 
        }
        
        loadUser();
        loadDashboard();
    </script>
</body>
</html>
"""

BUSINESSES_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Businesses - Review Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: white;
            border-radius: 12px;
            padding: 20px 30px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .nav {
            background: white;
            padding: 15px 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            display: flex;
            gap: 20px;
        }
        .nav a { color: #666; text-decoration: none; padding: 8px 16px; border-radius: 8px; }
        .nav a:hover, .nav a.active { background: #667eea; color: white; }
        .add-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            margin-bottom: 20px;
            font-size: 16px;
        }
        .business-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .business-name { font-weight: bold; font-size: 18px; color: #333; }
        .business-url { color: #666; font-size: 12px; margin-top: 5px; word-break: break-all; }
        .delete-btn {
            background: #ef4444;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
        }
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .modal-content {
            background: white;
            padding: 30px;
            border-radius: 16px;
            width: 90%;
            max-width: 500px;
        }
        .modal-content h3 { margin-bottom: 20px; }
        .modal input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 8px;
        }
        .modal button {
            padding: 10px 20px;
            margin: 10px 5px 0 0;
            border: none;
            border-radius: 8px;
            cursor: pointer;
        }
        .save-btn { background: #667eea; color: white; }
        .cancel-btn { background: #999; color: white; }
        .logout-btn { background: #ef4444; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; }
        .empty { background: white; padding: 40px; text-align: center; border-radius: 12px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🏢 My Businesses</h2>
            <button class="logout-btn" onclick="logout()">Logout</button>
        </div>
        <div class="nav">
            <a href="/dashboard">Dashboard</a>
            <a href="/businesses" class="active">Businesses</a>
            <a href="/alerts">Alerts</a>
        </div>
        <button class="add-btn" onclick="showModal()">+ Add Business</button>
        <div id="businessesList"></div>
    </div>
    
    <div id="modal" class="modal">
        <div class="modal-content">
            <h3>Add Business to Monitor</h3>
            <input type="text" id="businessUrl" placeholder="Google Maps URL (e.g., https://maps.google.com/...)">
            <input type="text" id="businessName" placeholder="Business Name (optional)">
            <button class="save-btn" onclick="addBusiness()">Add</button>
            <button class="cancel-btn" onclick="closeModal()">Cancel</button>
        </div>
    </div>
    
    <script>
        const token = localStorage.getItem('token');
        if (!token) window.location.href = '/login';
        
        async function apiCall(endpoint, options = {}) {
            const res = await fetch('/api' + endpoint, {
                ...options,
                headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }
            });
            if (res.status === 401) { 
                localStorage.removeItem('token'); 
                window.location.href = '/login';
                return null;
            }
            return res.json();
        }
        
        async function loadBusinesses() {
            const businesses = await apiCall('/businesses');
            const container = document.getElementById('businessesList');
            if (!businesses) return;
            
            if (businesses.length === 0) {
                container.innerHTML = '<div class="empty">No businesses added yet. Click "Add Business" to start monitoring reviews.</div>';
                return;
            }
            
            container.innerHTML = businesses.map(b => `
                <div class="business-card">
                    <div>
                        <div class="business-name">${escapeHtml(b.business_name)}</div>
                        <div class="business-url">${escapeHtml(b.google_maps_url)}</div>
                        <div style="margin-top: 8px; font-size: 12px; color: #888;">Added: ${new Date(b.created_at).toLocaleDateString()}</div>
                    </div>
                    <button class="delete-btn" onclick="deleteBusiness(${b.id})">Delete</button>
                </div>
            `).join('');
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        async function addBusiness() {
            const url = document.getElementById('businessUrl').value;
            const name = document.getElementById('businessName').value;
            
            if (!url) { 
                alert('Please enter a Google Maps URL'); 
                return; 
            }
            
            const result = await apiCall('/businesses', { 
                method: 'POST', 
                body: JSON.stringify({ google_maps_url: url, business_name: name }) 
            });
            
            if (result) {
                closeModal();
                loadBusinesses();
                alert('Business added successfully!');
            }
        }
        
        async function deleteBusiness(id) {
            if (confirm('Delete this business? You will no longer monitor its reviews.')) {
                await apiCall(`/businesses/${id}`, { method: 'DELETE' });
                loadBusinesses();
            }
        }
        
        function showModal() { 
            document.getElementById('modal').style.display = 'flex'; 
            document.getElementById('businessUrl').value = '';
            document.getElementById('businessName').value = '';
        }
        function closeModal() { document.getElementById('modal').style.display = 'none'; }
        function logout() { 
            localStorage.removeItem('token'); 
            window.location.href = '/login'; 
        }
        
        loadBusinesses();
    </script>
</body>
</html>
"""

ALERTS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Alerts - Review Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: white;
            border-radius: 12px;
            padding: 20px 30px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .nav {
            background: white;
            padding: 15px 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            display: flex;
            gap: 20px;
        }
        .nav a { color: #666; text-decoration: none; padding: 8px 16px; border-radius: 8px; }
        .nav a:hover, .nav a.active { background: #667eea; color: white; }
        .logout-btn { background: #ef4444; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; }
        .empty { background: white; padding: 40px; text-align: center; border-radius: 12px; color: #666; }
        .alert-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            border-left: 4px solid #ef4444;
        }
        .alert-business { font-weight: bold; font-size: 18px; margin-bottom: 10px; }
        .alert-text { color: #666; margin-top: 10px; }
        .alert-date { font-size: 12px; color: #999; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🔔 Alerts</h2>
            <button class="logout-btn" onclick="logout()">Logout</button>
        </div>
        <div class="nav">
            <a href="/dashboard">Dashboard</a>
            <a href="/businesses">Businesses</a>
            <a href="/alerts" class="active">Alerts</a>
        </div>
        <div id="alertsList" class="empty">No alerts yet. When you receive negative reviews, they will appear here.</div>
    </div>
    <script>
        const token = localStorage.getItem('token');
        if (!token) window.location.href = '/login';
        
        async function loadAlerts() {
            const res = await fetch('/api/alerts', {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            if (res.status === 401) {
                localStorage.removeItem('token');
                window.location.href = '/login';
                return;
            }
            const alerts = await res.json();
            const container = document.getElementById('alertsList');
            
            if (!alerts || alerts.length === 0) {
                container.innerHTML = '<div class="empty">No alerts yet. When you receive negative reviews, they will appear here.</div>';
                return;
            }
            
            container.innerHTML = alerts.map(a => `
                <div class="alert-card">
                    <div class="alert-business">🏢 ${escapeHtml(a.business_name)}</div>
                    <div>⭐ Rating: ${a.rating}/5</div>
                    <div class="alert-text">${escapeHtml(a.review_text || 'No review text')}</div>
                    <div class="alert-date">${new Date(a.sent_at).toLocaleString()}</div>
                </div>
            `).join('');
        }
        
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function logout() { 
            localStorage.removeItem('token'); 
            window.location.href = '/login'; 
        }
        
        loadAlerts();
    </script>
</body>
</html>
"""

# Route handlers
@app.get("/")
@app.get("/login")
async def login_page():
    return HTMLResponse(LOGIN_HTML)

@app.get("/signup")
async def signup_page():
    return HTMLResponse(SIGNUP_HTML)

@app.get("/dashboard")
async def dashboard_page():
    return HTMLResponse(DASHBOARD_HTML)

@app.get("/businesses")
async def businesses_page():
    return HTMLResponse(BUSINESSES_HTML)

@app.get("/alerts")
async def alerts_page():
    return HTMLResponse(ALERTS_HTML)

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 Starting Google Maps Review Monitor...")
    print("="*50)
    

    # Initialize database
    if init_db():
        print("\n✅ Setup complete!")
        print(f"📁 Database location: {DB_PATH}")
        print("\n🌐 Server will start on http://localhost:8000")
        print("📝 Sign up at: http://localhost:8000/signup")
        print("🔐 Login at: http://localhost:8000/login")
        print("\n⚠️  Press CTRL+C to stop the server")
        print("="*50 + "\n")
        
        # Run the server
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        print("❌ Failed to initialize database. Check permissions.")