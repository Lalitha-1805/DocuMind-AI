const API_BASE_URL = 'http://localhost:8000/api';

// Utility to handle JSON API requests
async function apiRequest(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: {},
    };

    if (body) {
        if (body instanceof FormData) {
            options.body = body;
            // Native fetch sets Content-Type for FormData automatically
        } else {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }
    }

    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
        const data = await response.json();
        return { status: response.status, data };
    } catch (error) {
        console.error('API Error:', error);
        return { status: 500, data: { detail: 'Network or server error' } };
    }
}

// Authentication Logic
const Auth = {
    login: (userData) => {
        localStorage.setItem('hr_user', JSON.stringify(userData));
        window.location.href = '/dashboard';
    },

    logout: () => {
        localStorage.removeItem('hr_user');
        window.location.href = '/login';
    },

    getUser: () => {
        const user = localStorage.getItem('hr_user');
        return user ? JSON.parse(user) : null;
    },

    isAuthenticated: () => {
        return localStorage.getItem('hr_user') !== null;
    },

    requireAuth: () => {
        if (!Auth.isAuthenticated()) {
            window.location.href = '/login';
        }
    },

    requireGuest: () => {
        if (Auth.isAuthenticated()) {
            window.location.href = '/dashboard';
        }
    },

    hasRole: (roles) => {
        // Since we replaced specific roles with 'profession', 
        // we'll allow all registered users access to management for now, 
        // or the user can define admin logic later.
        return Auth.isAuthenticated();
    }
};

// Navigation Mapping for Sidebar
const NAV_ITEMS = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊', path: '/dashboard' },
    { id: 'chat', label: 'Chat', icon: '💬', path: '/chat' },
    { id: 'upload', label: 'Upload', icon: '📤', path: '/upload' },
    { id: 'insights', label: 'Insights', icon: '🔍', path: '/insights' },
    { id: 'leave-calculator', label: 'Leave Calculator', icon: '📅', path: '/leave-calculator' },
];

// UI Component Renderer: Sidebar
function renderSidebar() {
    const sidebar = document.getElementById('sidebar-container');
    if (!sidebar) return;

    const user = Auth.getUser();
    if (!user) return;

    const currentPath = window.location.pathname;

    sidebar.innerHTML = `
        <div class="sidebar">
            <a href="/dashboard" class="sidebar-logo">
                <span style="font-size: 1.5rem;">🚀</span> DocuMind
            </a>
            
            <ul class="nav-menu">
                ${NAV_ITEMS.map(item => `
                    <li class="nav-item">
                        <a href="${item.path}" class="nav-link ${currentPath === item.path ? 'active' : ''}">
                            <span class="nav-icon">${item.icon}</span>
                            <span>${item.label}</span>
                        </a>
                    </li>
                `).join('')}
            </ul>

            <div class="sidebar-footer">
                <div class="user-profile-sm">
                    <div class="user-avatar-sm">
                        ${user.profile_pic ? `<img src="${user.profile_pic}" style="width: 100%; height: 100%; object-fit: cover; display: block;">` : '👤'}
                    </div>
                    <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-grow: 1;">
                        <div style="font-weight: 600; font-size: 0.9rem;">${user.name}</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted);">${user.email}</div>
                    </div>
                </div>
                <a href="/profile" class="nav-link" style="margin-bottom: 0.5rem; display: flex; align-items: center; gap: 12px;">
                    <span class="user-avatar-xs" style="width: 24px; height: 24px; border-radius: 50%; overflow: hidden; display: flex; align-items: center; justify-content: center; background: var(--background-alt); font-size: 0.8rem; flex-shrink: 0;">
                        ${user.profile_pic ? `<img src="${user.profile_pic}" style="width: 100%; height: 100%; object-fit: cover;">` : '👤'}
                    </span>
                    <span>View Profile</span>
                </a>
                <button onclick="Auth.logout()" class="btn btn-secondary btn-block" style="font-size: 0.85rem; padding: 0.6rem;">
                    Sign out
                </button>
            </div>
        </div>
    `;
}

// Wait for DOM to load, then initialize common UI
document.addEventListener('DOMContentLoaded', () => {
    renderSidebar();
});
