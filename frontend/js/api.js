// API Configuration
const API_BASE_URL = 'http://localhost:8000/api';

// Store token in localStorage
let authToken = localStorage.getItem('access_token');

// API Client
const api = {
    async request(endpoint, method = 'GET', data = null) {
        const headers = {
            'Content-Type': 'application/json',
        };
        
        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }
        
        const config = {
            method,
            headers,
        };
        
        if (data) {
            config.body = JSON.stringify(data);
        }
        
        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
            
            if (response.status === 401) {
                // Token expired, redirect to login
                localStorage.removeItem('access_token');
                window.location.href = '/login';
                return null;
            }
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || 'Request failed');
            }
            
            return data;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },
    
    // Auth endpoints
    async signup(email, password, fullName, companyName = null) {
        return this.request('/auth/signup', 'POST', {
            email,
            password,
            full_name: fullName,
            company_name: companyName
        });
    },
    
    async login(email, password) {
        const data = await this.request('/auth/login', 'POST', {
            email,
            password
        });
        
        if (data.access_token) {
            authToken = data.access_token;
            localStorage.setItem('access_token', authToken);
            localStorage.setItem('user', JSON.stringify(data.user));
            return true;
        }
        return false;
    },
    
    logout() {
        authToken = null;
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
    },
    
    async getMe() {
        return this.request('/auth/me', 'GET');
    },
    
    // Businesses
    async getBusinesses() {
        return this.request('/businesses', 'GET');
    },
    
    async addBusiness(url, name = null) {
        return this.request('/businesses', 'POST', {
            google_maps_url: url,
            business_name: name
        });
    },
    
    async deleteBusiness(businessId) {
        return this.request(`/businesses/${businessId}`, 'DELETE');
    },
    
    // Dashboard
    async getDashboardStats() {
        return this.request('/dashboard/stats', 'GET');
    },
    
    // Reviews
    async getReviews(businessId = null) {
        const endpoint = businessId ? `/reviews?business_id=${businessId}` : '/reviews';
        return this.request(endpoint, 'GET');
    },
    
    // Alerts
    async getAlerts() {
        return this.request('/alerts', 'GET');
    }
};

// Helper function to show notifications
function showNotification(message, type = 'info') {
    // Remove existing notification
    const existing = document.querySelector('.notification');
    if (existing) existing.remove();
    
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        background: ${type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : '#3b82f6'};
        color: white;
        border-radius: 8px;
        z-index: 10000;
        animation: slideIn 0.3s ease;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    `;
    
    // Add animation styles if not present
    if (!document.querySelector('#notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            @keyframes slideIn {
                from {
                    transform: translateX(100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            @keyframes slideOut {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(100%);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(style);
    }
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, 3000);
}

// Check auth on protected pages
function checkAuth() {
    const protectedPages = ['dashboard', 'businesses', 'alerts', 'settings'];
    const currentPage = window.location.pathname.split('/').pop().replace('.html', '');
    
    if (protectedPages.includes(currentPage) || currentPage === '') {
        if (!authToken) {
            window.location.href = '/login';
            return false;
        }
    }
    return true;
}

// Load dashboard data
async function loadDashboard() {
    if (!checkAuth()) return;
    
    try {
        const stats = await api.getDashboardStats();
        
        // Update stats cards
        const negativeEl = document.getElementById('totalNegativeReviews');
        if (negativeEl) negativeEl.textContent = stats.total_negative_reviews || 0;
        
        const businessesEl = document.getElementById('totalBusinesses');
        if (businessesEl) businessesEl.textContent = stats.total_businesses || 0;
        
        const alertsEl = document.getElementById('criticalAlerts');
        if (alertsEl) alertsEl.textContent = stats.critical_alerts || 0;
        
        // Update reputation status
        const statusEl = document.getElementById('reputationStatus');
        if (statusEl) {
            statusEl.textContent = stats.reputation_status || 'Stable';
            statusEl.className = `status-badge ${(stats.reputation_status || 'stable').toLowerCase()}`;
        }
        
        // Update recent reviews table
        const reviewsTable = document.getElementById('recentReviews');
        if (reviewsTable && stats.recent_negative_reviews) {
            if (stats.recent_negative_reviews.length === 0) {
                reviewsTable.innerHTML = '<tr><td colspan="5" style="text-align: center;">No negative reviews found</td></tr>';
            } else {
                reviewsTable.innerHTML = stats.recent_negative_reviews.map(review => `
                    <tr>
                        <td>${review.reviewer_name || 'Anonymous'}</td>
                        <td>${'⭐'.repeat(Math.floor(review.rating))}${review.rating % 1 ? '½' : ''}</td>
                        <td>${(review.review_text || '').substring(0, 100)}${(review.review_text || '').length > 100 ? '...' : ''}</td>
                        <td>${review.review_date ? new Date(review.review_date).toLocaleDateString() : 'N/A'}</td>
                        <td><span class="category-badge">${review.complaint_category || 'Uncategorized'}</span></td>
                    </tr>
                `).join('');
            }
        }
        
        // Update categories chart
        if (stats.top_complaint_categories) {
            updateCategoriesChart(stats.top_complaint_categories);
        }
        
    } catch (error) {
        console.error('Error loading dashboard:', error);
        showNotification('Failed to load dashboard data', 'error');
    }
}

// Update complaint categories chart
function updateCategoriesChart(categories) {
    const container = document.getElementById('categoriesChart');
    if (!container) return;
    
    const entries = Object.entries(categories);
    if (entries.length === 0) {
        container.innerHTML = '<p>No complaints categorized yet</p>';
        return;
    }
    
    const maxCount = Math.max(...entries.map(([_, count]) => count), 1);
    
    container.innerHTML = entries.map(([category, count]) => `
        <div class="category-item">
            <div class="category-label">${category}</div>
            <div class="category-bar-container">
                <div class="category-bar" style="width: ${(count / maxCount) * 100}%"></div>
                <span class="category-count">${count}</span>
            </div>
        </div>
    `).join('');
}

// Load businesses
async function loadBusinesses() {
    if (!checkAuth()) return;
    
    try {
        const businesses = await api.getBusinesses();
        const container = document.getElementById('businessesList');
        
        if (!container) return;
        
        if (businesses.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No businesses added yet</p><button onclick="showAddBusinessModal()" class="btn-primary">Add Your First Business</button></div>';
            return;
        }
        
        container.innerHTML = businesses.map(business => `
            <div class="business-card">
                <h3>${business.business_name}</h3>
                <p class="business-url">${business.google_maps_url}</p>
                <div class="business-stats">
                    <span>📊 Total: ${business.total_reviews || 0}</span>
                    <span>⚠️ Negative: ${business.negative_count || 0}</span>
                </div>
                <button onclick="viewBusinessReviews(${business.id})" class="btn-secondary">View Reviews</button>
                <button onclick="deleteBusiness(${business.id})" class="btn-danger">Delete</button>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Error loading businesses:', error);
        showNotification('Failed to load businesses', 'error');
    }
}

// Add business handler
async function handleAddBusiness(event) {
    event.preventDefault();
    
    const url = document.getElementById('businessUrl').value;
    const name = document.getElementById('businessName').value;
    
    if (!url) {
        showNotification('Please enter a Google Maps URL', 'error');
        return;
    }
    
    try {
        await api.addBusiness(url, name);
        showNotification('Business added successfully!', 'success');
        closeModal();
        loadBusinesses();
    } catch (error) {
        showNotification('Failed to add business: ' + error.message, 'error');
    }
}

// Delete business
async function deleteBusiness(businessId) {
    if (!confirm('Are you sure you want to delete this business?')) return;
    
    try {
        await api.deleteBusiness(businessId);
        showNotification('Business deleted successfully', 'success');
        loadBusinesses();
    } catch (error) {
        showNotification('Failed to delete business', 'error');
    }
}

// Modal functions
function showAddBusinessModal() {
    const modal = document.getElementById('addBusinessModal');
    if (modal) modal.style.display = 'block';
}

function closeModal() {
    const modal = document.getElementById('addBusinessModal');
    if (modal) modal.style.display = 'none';
}

// Load alerts
async function loadAlerts() {
    if (!checkAuth()) return;
    
    try {
        const alerts = await api.getAlerts();
        const container = document.getElementById('alertsList');
        
        if (!container) return;
        
        if (alerts.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No alerts yet</p></div>';
            return;
        }
        
        container.innerHTML = alerts.map(alert => `
            <div class="alert-card alert-${alert.urgency_level || 'low'}">
                <div class="alert-header">
                    <span class="business-name">${alert.business_name}</span>
                    <span class="alert-rating">${'⭐'.repeat(Math.floor(alert.rating))}</span>
                    <span class="alert-date">${new Date(alert.sent_at).toLocaleString()}</span>
                </div>
                <div class="alert-content">
                    <p>${alert.review_text || 'No review text'}</p>
                </div>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Error loading alerts:', error);
        showNotification('Failed to load alerts', 'error');
    }
}

// Initialize page based on current path
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;
    
    // Setup forms
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            
            try {
                const success = await api.login(email, password);
                if (success) {
                    showNotification('Login successful!', 'success');
                    window.location.href = '/dashboard';
                } else {
                    showNotification('Invalid credentials', 'error');
                }
            } catch (error) {
                showNotification('Login failed: ' + error.message, 'error');
            }
        });
    }
    
    const signupForm = document.getElementById('signupForm');
    if (signupForm) {
        signupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const fullName = document.getElementById('fullName').value;
            const companyName = document.getElementById('companyName')?.value;
            
            try {
                await api.signup(email, password, fullName, companyName);
                showNotification('Account created! Please login.', 'success');
                setTimeout(() => {
                    window.location.href = '/login';
                }, 1500);
            } catch (error) {
                showNotification('Signup failed: ' + error.message, 'error');
            }
        });
    }
    
    const addBusinessForm = document.getElementById('addBusinessForm');
    if (addBusinessForm) {
        addBusinessForm.addEventListener('submit', handleAddBusiness);
    }
    
    // Load page-specific data
    if (path.includes('dashboard')) {
        loadDashboard();
    }
    
    if (path.includes('businesses')) {
        loadBusinesses();
    }
    
    if (path.includes('alerts')) {
        loadAlerts();
    }
    
    // Add logout button handler
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            api.logout();
        });
    }
});