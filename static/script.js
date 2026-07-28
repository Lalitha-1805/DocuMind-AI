/* =========================================
   Frontend Logic (Vanilla JS)
   ========================================= */

// --- Global State ---
let currentUser = null;
let currentScreen = 'welcome';

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    // Check local storage for session
    const savedUser = localStorage.getItem('hr_user');
    if (savedUser) {
        currentUser = JSON.parse(savedUser);
        updateUserUI();
        navigateTo('dashboard');
    } else {
        navigateTo('welcome');
    }

    // Attach form listeners
    document.getElementById('login-form').addEventListener('submit', handleLogin);
    document.getElementById('signup-form').addEventListener('submit', handleSignup);
    document.getElementById('chat-form').addEventListener('submit', handleChatSubmit);

    // File upload listener
    const fileInput = document.getElementById('policy-file');
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            document.getElementById('file-name-display').innerText = `Selected: ${e.target.files[0].name}`;
            document.getElementById('btn-process-doc').classList.remove('disabled');
        }
    });

    // Drag and Drop
    const dropZone = document.getElementById('drop-zone');
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
    });
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            document.getElementById('file-name-display').innerText = `Selected: ${fileInput.files[0].name}`;
            document.getElementById('btn-process-doc').classList.remove('disabled');
        }
    });
});

// --- Navigation ---
function navigateTo(screenId) {
    // Hide all screens
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));

    // Show target
    const target = document.getElementById(`${screenId}-section`);
    if (target) target.classList.add('active');

    currentScreen = screenId;

    // Sidebar visibility
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('main-content');

    if (['welcome', 'login', 'signup'].includes(screenId)) {
        sidebar.classList.add('hidden');
        mainContent.classList.add('full-width');
    } else {
        if (!currentUser) {
            // Protect routes
            navigateTo('welcome');
            return;
        }
        sidebar.classList.remove('hidden');
        mainContent.classList.remove('full-width');

        // Update Active Nav Link
        document.querySelectorAll('.nav-links li').forEach(li => li.classList.remove('active'));
        const activeLink = Array.from(document.querySelectorAll('.nav-links a')).find(a => a.getAttribute('onclick') === `navigateTo('${screenId}')`);
        if (activeLink) activeLink.parentElement.classList.add('active');
    }

    // specific screen actions
    if (screenId === 'dashboard') {
        document.getElementById('dash-welcome-text').innerText = `Welcome back, ${currentUser.name} 👋`;
        document.getElementById('dash-info-text').innerText = `You are logged in as ${currentUser.role} from the ${currentUser.dept} department.`;
    }
    if (screenId === 'insights') {
        loadInsights();
    }
    if (screenId === 'chat') {
        loadChatHistory();
        setTimeout(() => scrollToBottom('chat-history'), 100);
    }
}

function updateUserUI() {
    if (!currentUser) return;

    document.getElementById('nav-user-name').innerText = currentUser.name;
    document.getElementById('nav-user-role').innerText = currentUser.role;

    const isManager = ['HR Manager', 'Admin'].includes(currentUser.role);

    if (isManager) {
        document.getElementById('nav-upload-item').classList.remove('hidden');
        document.getElementById('nav-insights-item').classList.remove('hidden');
        document.getElementById('action-upload').classList.remove('hidden');
        document.getElementById('action-insights').classList.remove('hidden');
    } else {
        document.getElementById('nav-upload-item').classList.add('hidden');
        document.getElementById('nav-insights-item').classList.add('hidden');
        document.getElementById('action-upload').classList.add('hidden');
        document.getElementById('action-insights').classList.add('hidden');
    }
}

function logout() {
    currentUser = null;
    localStorage.removeItem('hr_user');
    navigateTo('welcome');
    showToast('Logged out successfully', 'success');
}

// --- API Calls ---

async function handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        const data = await res.json();
        if (res.ok) {
            currentUser = data.user;
            localStorage.setItem('hr_user', JSON.stringify(currentUser));
            updateUserUI();
            navigateTo('dashboard');
            showToast(`Welcome back, ${currentUser.name}!`, 'success');
        } else {
            showToast(data.detail || 'Login failed', 'error');
        }
    } catch (err) {
        showToast('Connection error', 'error');
    }
}

async function handleSignup(e) {
    e.preventDefault();
    const pwd = document.getElementById('signup-password').value;
    const confirm = document.getElementById('signup-confirm').value;

    if (pwd !== confirm) {
        showToast('Passwords do not match', 'error');
        return;
    }

    const payload = {
        name: document.getElementById('signup-name').value,
        emp_id: document.getElementById('signup-empid').value,
        email: document.getElementById('signup-email').value,
        dept: document.getElementById('signup-dept').value,
        role: document.getElementById('signup-role').value,
        password: pwd
    };

    try {
        const res = await fetch('/api/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok) {
            showToast('Account created! Please login.', 'success');
            navigateTo('login');
        } else {
            showToast(data.detail || 'Signup failed', 'error');
        }
    } catch (err) {
        showToast('Connection error', 'error');
    }
}

async function uploadPolicy() {
    const fileInput = document.getElementById('policy-file');
    if (!fileInput.files.length) return;

    const btn = document.getElementById('btn-process-doc');
    const statusDiv = document.getElementById('upload-status');

    btn.classList.add('hidden');
    statusDiv.classList.remove('hidden');

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        if (res.ok) {
            showToast(`Indexed ${data.filename} (${data.pages} pages, ${data.chunks} chunks)`, 'success');
            setTimeout(() => {
                navigateTo('chat');
            }, 1500);
        } else {
            showToast(data.detail || 'Upload failed', 'error');
        }
    } catch (err) {
        showToast('Connection error', 'error');
    } finally {
        statusDiv.classList.add('hidden');
        btn.classList.remove('hidden');
        btn.classList.add('disabled');
        fileInput.value = '';
        document.getElementById('file-name-display').innerText = '';
    }
}

// --- Chat Logic ---

function setQuestion(q) {
    document.getElementById('chat-input').value = q;
    document.getElementById('chat-input').focus();
}

async function handleChatSubmit(e) {
    e.preventDefault();
    const inputField = document.getElementById('chat-input');
    const q = inputField.value.trim();
    if (!q) return;

    const groqKey = document.getElementById('groq-key').value;
    if (!groqKey) {
        showToast('Please enter Groq API Key in settings', 'warning');
        return;
    }

    inputField.value = '';
    appendMessage(q, 'user');
    scrollToBottom('chat-history');

    // Add loading bubble
    const loadingId = 'loading-' + Date.now();
    appendLoading(loadingId);
    scrollToBottom('chat-history');

    const depth = parseInt(document.getElementById('retrieval-depth').value);

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_email: currentUser.email,
                question: q,
                groq_api_key: groqKey,
                retrieval_depth: depth,
                threshold: 1.0
            })
        });

        const data = await res.json();
        removeLoading(loadingId);

        if (res.ok) {
            appendMessage(data.answer, 'bot', data);
        } else {
            appendMessage(`Error: ${data.detail || 'Server error'}`, 'bot', { status: 'Not Answered' });
        }
    } catch (err) {
        removeLoading(loadingId);
        appendMessage('Connection error. Is the server running?', 'bot', { status: 'Not Answered' });
    }

    scrollToBottom('chat-history');
}

function appendMessage(text, sender, meta = null) {
    const container = document.getElementById('chat-history');
    const placeholder = container.querySelector('.chat-placeholder');
    if (placeholder) placeholder.remove();

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble chat-${sender}`;

    if (sender === 'user') {
        bubble.innerText = text;
    } else {
        // Simple Markdown parsing for bot
        let html = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');

        let contentHtml = `<div class="chat-bot-inner"><p>${html}</p></div>`;

        if (meta && meta.status === 'Not Answered' && text !== 'Error: No HR Policy indexed.') {
            contentHtml = `<div class="gap-alert"><i class="fa-solid fa-triangle-exclamation"></i> <strong>Policy Gap Alert:</strong> ${text}</div>`;
        }

        if (meta && meta.confidence !== undefined) {
            contentHtml += `
                <div class="chat-meta">
                    <div class="chat-meta-tags">
                        <span><i class="fa-solid fa-bullseye"></i> ${meta.confidence.toFixed(1)}%</span>
                        <span><i class="fa-solid fa-ruler"></i> ${meta.distance.toFixed(3)}</span>
                    </div>
                    <div class="chat-actions">
                        <button title="Download Answer" onclick="downloadTxt('${encodeURIComponent(text)}')"><i class="fa-solid fa-download"></i></button>
                    </div>
                </div>
            `;
        }
        bubble.innerHTML = contentHtml;
    }

    container.appendChild(bubble);
}

function appendLoading(id) {
    const container = document.getElementById('chat-history');
    const bubble = document.createElement('div');
    bubble.id = id;
    bubble.className = `chat-bubble chat-bot`;
    bubble.innerHTML = `<div class="spinner" style="width:20px;height:20px;border-width:2px;"></div>`;
    container.appendChild(bubble);
}

function removeLoading(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function scrollToBottom(id) {
    const el = document.getElementById(id);
    if (el) el.scrollTop = el.scrollHeight;
}

function downloadTxt(content) {
    const text = decodeURIComponent(content);
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'hr_answer.txt';
    a.click();
    URL.revokeObjectURL(url);
}

async function loadChatHistory() {
    if (!currentUser) return;

    try {
        const res = await fetch(`/api/chat/history?email=${encodeURIComponent(currentUser.email)}`);
        const data = await res.json();

        const container = document.getElementById('chat-history');
        if (data.length > 0) {
            container.innerHTML = ''; // clear placeholder
            data.forEach(msg => {
                appendMessage(msg.question, 'user');
                appendMessage(msg.answer, 'bot', {
                    status: msg.status,
                    confidence: msg.confidence,
                    distance: msg.distance
                });
            });
        }
    } catch (e) {
        console.error('Failed to load history', e);
    }
}

// --- Insights Logic ---

async function loadInsights() {
    try {
        const res = await fetch('/api/insights');
        const data = await res.json();

        // Updates
        document.getElementById('ins-total').innerText = data.total;
        document.getElementById('ins-ans-ratio').innerText = `${data.answered} / ${data.not_answered}`;
        document.getElementById('ins-avg-conf').innerText = `${data.average_confidence.toFixed(1)}%`;
        document.getElementById('ins-coverage').innerText = `${data.coverage_percentage.toFixed(1)}%`;

        // Risk Alert
        const alertBox = document.getElementById('risk-alert');
        if (data.not_answered > data.answered && data.total > 5) {
            alertBox.className = "alert alert-danger mt-3";
            alertBox.innerHTML = "🚨 <strong>High Risk:</strong> Too many unanswered questions. Consider updating the HR Policy document.";
        } else if (data.not_answered > 0) {
            alertBox.className = "alert alert-warning mt-3";
            alertBox.innerHTML = "⚠️ <strong>Moderate Risk:</strong> Some questions were unanswerable. Check recent queries to identify gaps.";
        } else if (data.total > 0) {
            alertBox.className = "alert alert-success mt-3";
            alertBox.innerHTML = "✅ <strong>Healthy:</strong> High policy coverage based on recent queries.";
        } else {
            alertBox.className = "alert alert-success mt-3";
            alertBox.innerHTML = "Awaiting queries to generate risk score.";
        }

        // Topics Chart
        const topicsList = document.getElementById('topics-list');
        topicsList.innerHTML = '';
        if (data.topics.length > 0) {
            const maxVal = Math.max(...data.topics.map(t => t.count));
            data.topics.forEach(t => {
                const width = (t.count / maxVal) * 100;
                topicsList.innerHTML += `
                    <div class="topic-bar-container">
                        <div class="topic-label">${t.topic}</div>
                        <div class="topic-track">
                            <div class="topic-fill" style="width: ${width}%"></div>
                        </div>
                        <div class="topic-count">${t.count}</div>
                    </div>
                `;
            });
        } else {
            topicsList.innerHTML = '<p class="text-muted">No topic data available yet.</p>';
        }

        // Unanswered list
        const uList = document.getElementById('unanswered-list');
        uList.innerHTML = '';
        if (data.recent_unanswered.length > 0) {
            data.recent_unanswered.forEach(q => {
                uList.innerHTML += `<li>${q}</li>`;
            });
        } else {
            uList.innerHTML = '<li style="list-style:none; padding-left:0;">No unanswered queries recently.</li>';
        }

    } catch (e) {
        showToast('Failed to load insights', 'error');
    }
}

// --- Utils ---

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    if (type === 'error') icon = 'fa-circle-exclamation';
    if (type === 'warning') icon = 'fa-triangle-exclamation';

    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
