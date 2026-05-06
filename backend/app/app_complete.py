from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import sqlite3
import hashlib
import secrets
import uvicorn
import os

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

# Database
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "reviewmonitor.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
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
    conn.commit()
    conn.close()
    print("✅ Database ready")

# Models
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class BusinessCreate(BaseModel):
    google_maps_url: str
    business_name: Optional[str] = None

# Helpers
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
    return dict(user)

# API Routes
@app.post("/api/auth/signup")
async def signup(user: UserCreate):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (user.email,))
    if cursor.fetchone():
        raise HTTPException(400, "Email already registered")
    cursor.execute("INSERT INTO users (email, password, full_name) VALUES (?, ?, ?)",
                   (user.email, hash_password(user.password), user.full_name))
    conn.commit()
    conn.close()
    return {"success": True, "message": "User created"}

@app.post("/api/auth/login")
async def login(user: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, full_name, password FROM users WHERE email = ?", (user.email,))
    db_user = cursor.fetchone()
    conn.close()
    if not db_user or not verify_password(user.password, db_user['password']):
        raise HTTPException(401, "Invalid credentials")
    token = secrets.token_urlsafe(32)
    sessions[token] = db_user['id']
    return {"access_token": token, "token_type": "bearer", "user": dict(db_user)}

@app.get("/api/auth/me")
async def get_me(authorization: str = None):
    return get_current_user(authorization)

@app.post("/api/businesses")
async def add_business(business: BusinessCreate, authorization: str = None):
    user = get_current_user(authorization)
    conn = get_db()
    cursor = conn.cursor()
    name = business.business_name or f"Business {datetime.now().strftime('%Y%m%d%H%M%S')}"
    cursor.execute("INSERT INTO businesses (user_id, google_maps_url, business_name) VALUES (?, ?, ?)",
                   (user['id'], business.google_maps_url, name))
    conn.commit()
    biz_id = cursor.lastrowid
    conn.close()
    return {"id": biz_id, "message": "Business added"}

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
    return {"message": "Deleted"}

@app.get("/api/dashboard/stats")
async def get_stats(authorization: str = None):
    user = get_current_user(authorization)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM businesses WHERE user_id = ?", (user['id'],))
    total_businesses = cursor.fetchone()['count']
    conn.close()
    return {
        "total_negative_reviews": 0,
        "total_businesses": total_businesses,
        "critical_alerts": 0,
        "reputation_status": "Stable",
        "recent_negative_reviews": [],
        "top_complaint_categories": {}
    }

# HTML Dashboard (built-in)
HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Review Monitor - Dashboard</title>
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
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
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
            font-size: 14px;
        }
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
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .stat-value { font-size: 36px; font-weight: bold; color: #667eea; }
        .stat-label { color: #666; margin-top: 5px; }
        .reviews-table {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { color: #666; font-weight: 600; }
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
        .nav {
            display: flex;
            gap: 20px;
            margin-bottom: 30px;
            background: white;
            padding: 15px 30px;
            border-radius: 12px;
        }
        .nav a {
            color: #666;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        .nav a:hover, .nav a.active { background: #667eea; color: white; }
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
        <div class="reviews-table">
            <h3 style="margin-bottom: 20px;">Recent Negative Reviews</h3>
            <div id="reviewsList">No reviews yet</div>
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
            if (res.status === 401) { localStorage.removeItem('token'); window.location.href = '/login'; }
            return res.json();
        }
        
        async function loadDashboard() {
            const stats = await apiCall('/dashboard/stats');
            document.getElementById('negativeCount').innerText = stats.total_negative_reviews;
            document.getElementById('businessCount').innerText = stats.total_businesses;
            document.getElementById('alertCount').innerText = stats.critical_alerts;
            const badge = document.getElementById('statusBadge');
            badge.innerText = stats.reputation_status;
            badge.className = 'status-badge ' + stats.reputation_status.toLowerCase();
        }
        
        function logout() { localStorage.removeItem('token'); window.location.href = '/login'; }
        
        loadDashboard();
    </script>
</body>
</html>
"""

HTML_LOGIN = """
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
    </style>
</head>
<body>
    <div class="card">
        <h1>🔐 Login</h1>
        <input type="email" id="email" placeholder="Email" autocomplete="email">
        <input type="password" id="password" placeholder="Password">
        <button onclick="login()">Login</button>
        <div class="link">Don't have an account? <a href="/signup">Sign up</a></div>
        <div id="error" class="error"></div>
    </div>
    <script>
        async function login() {
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            if (res.ok) {
                const data = await res.json();
                localStorage.setItem('token', data.access_token);
                window.location.href = '/dashboard';
            } else {
                document.getElementById('error').innerText = 'Invalid credentials';
            }
        }
    </script>
</body>
</html>
"""

HTML_SIGNUP = """
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
        .error { color: #ef4444; margin-top: 10px; text-align: center; }
        .success { color: #10b981; margin-top: 10px; text-align: center; }
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
        <div id="message" class="error"></div>
    </div>
    <script>
        async function signup() {
            const name = document.getElementById('name').value;
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const res = await fetch('/api/auth/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, full_name: name })
            });
            if (res.ok) {
                document.getElementById('message').className = 'success';
                document.getElementById('message').innerText = 'Account created! Redirecting to login...';
                setTimeout(() => window.location.href = '/login', 2000);
            } else {
                const data = await res.json();
                document.getElementById('message').innerText = data.detail || 'Signup failed';
            }
        }
    </script>
</body>
</html>
"""

HTML_BUSINESSES = """
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
        .nav a:hover { background: #667eea; color: white; }
        .add-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
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
        .business-name { font-weight: bold; font-size: 18px; }
        .business-url { color: #666; font-size: 12px; margin-top: 5px; }
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
        }
        .modal-content {
            background: white;
            padding: 30px;
            border-radius: 16px;
            width: 90%;
            max-width: 500px;
        }
        .modal input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 8px;
        }
        .modal button {
            padding: 10px 20px;
            margin: 10px 5px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
        }
        .logout-btn { background: #ef4444; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; }
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
            <h3>Add Business</h3>
            <input type="text" id="businessUrl" placeholder="Google Maps URL">
            <input type="text" id="businessName" placeholder="Business Name (optional)">
            <button onclick="addBusiness()">Add</button>
            <button onclick="closeModal()">Cancel</button>
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
            if (res.status === 401) { localStorage.removeItem('token'); window.location.href = '/login'; }
            return res.json();
        }
        
        async function loadBusinesses() {
            const businesses = await apiCall('/businesses');
            const container = document.getElementById('businessesList');
            if (businesses.length === 0) {
                container.innerHTML = '<div style="background:white; padding:40px; text-align:center; border-radius:12px;">No businesses added yet. Click "Add Business" to start.</div>';
                return;
            }
            container.innerHTML = businesses.map(b => `
                <div class="business-card">
                    <div>
                        <div class="business-name">${b.business_name}</div>
                        <div class="business-url">${b.google_maps_url}</div>
                    </div>
                    <button class="delete-btn" onclick="deleteBusiness(${b.id})">Delete</button>
                </div>
            `).join('');
        }
        
        async function addBusiness() {
            const url = document.getElementById('businessUrl').value;
            const name = document.getElementById('businessName').value;
            if (!url) { alert('Please enter a URL'); return; }
            await apiCall('/businesses', { method: 'POST', body: JSON.stringify({ google_maps_url: url, business_name: name }) });
            closeModal();
            loadBusinesses();
        }
        
        async function deleteBusiness(id) {
            if (confirm('Delete this business?')) {
                await apiCall(`/businesses/${id}`, { method: 'DELETE' });
                loadBusinesses();
            }
        }
        
        function showModal() { document.getElementById('modal').style.display = 'flex'; }
        function closeModal() { document.getElementById('modal').style.display = 'none'; }
        function logout() { localStorage.removeItem('token'); window.location.href = '/login'; }
        
        loadBusinesses();
    </script>
</body>
</html>
"""

HTML_ALERTS = """
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
        .alert-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            border-left: 4px solid #ef4444;
        }
        .logout-btn { background: #ef4444; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; }
        .empty { background: white; padding: 40px; text-align: center; border-radius: 12px; }
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
        <div id="alertsList"></div>
    </div>
    <script>
        const token = localStorage.getItem('token');
        if (!token) window.location.href = '/login';
        
        async function apiCall(endpoint) {
            const res = await fetch('/api' + endpoint, {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            if (res.status === 401) { localStorage.removeItem('token'); window.location.href = '/login'; }
            return res.json();
        }
        
        async function loadAlerts() {
            const alerts = await apiCall('/alerts');
            const container = document.getElementById('alertsList');
            if (alerts.length === 0) {
                container.innerHTML = '<div class="empty">No alerts yet. When you get negative reviews, they will appear here.</div>';
                return;
            }
            container.innerHTML = alerts.map(a => `<div class="alert-card"><strong>${a.business_name}</strong><p>${a.review_text || 'No text'}</p></div>`).join('');
        }
        
        function logout() { localStorage.removeItem('token'); window.location.href = '/login'; }
        loadAlerts();
    </script>
</body>
</html>
"""

# Route handlers
@app.get("/")
@app.get("/login")
async def login_page():
    return HTMLResponse(HTML_LOGIN)

@app.get("/signup")
async def signup_page():
    return HTMLResponse(HTML_SIGNUP)

@app.get("/dashboard")
async def dashboard_page():
    return HTMLResponse(HTML_DASHBOARD)

@app.get("/businesses")
async def businesses_page():
    return HTMLResponse(HTML_BUSINESSES)

@app.get("/alerts")
async def alerts_page():
    return HTMLResponse(HTML_ALERTS)

if __name__ == "__main__":
    init_db()
    print("\n" + "="*50)
    print("🚀 Google Maps Review Monitor is RUNNING!")
    print("📍 Open your browser and go to: http://localhost:8000")
    print("📝 Sign up for a new account at: http://localhost:8000/signup")
    print("="*50 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8001)