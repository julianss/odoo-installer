// Settings page JavaScript

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadAuditLog();
});

// ============================================================================
// Authentication Settings
// ============================================================================

async function saveAuthSettings() {
    const username = document.getElementById('auth-username').value.trim();
    const password = document.getElementById('auth-password').value;
    const confirmPassword = document.getElementById('auth-password-confirm').value;

    if (!username) {
        showMessage('Username is required', 'error');
        return;
    }

    if (password && password !== confirmPassword) {
        showMessage('Passwords do not match', 'error');
        return;
    }

    if (password && password.length < 6) {
        showMessage('Password must be at least 6 characters', 'error');
        return;
    }

    try {
        const response = await fetch('/api/settings/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: username,
                password: password || undefined
            })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Failed to save settings');
        }

        showMessage('Credentials saved. Please log in again with new credentials.', 'success');

        // Clear password fields
        document.getElementById('auth-password').value = '';
        document.getElementById('auth-password-confirm').value = '';

    } catch (error) {
        console.error('Error saving auth settings:', error);
        showMessage(`Failed to save: ${error.message}`, 'error');
    }
}

// ============================================================================
// Audit Log
// ============================================================================

async function loadAuditLog() {
    const filter = document.getElementById('audit-filter').value;
    const tbody = document.getElementById('audit-tbody');

    try {
        const url = filter ? `/api/settings/audit?category=${filter}` : '/api/settings/audit';
        const response = await fetch(url);
        const logs = await response.json();

        if (logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="px-4 py-4 text-center text-gray-500">No audit logs found</td></tr>';
            return;
        }

        tbody.innerHTML = logs.map(entry => `
            <tr>
                <td class="px-4 py-2 text-sm text-gray-600">${formatTimestamp(entry.timestamp)}</td>
                <td class="px-4 py-2 text-sm">
                    <span class="px-2 py-1 text-xs rounded ${getCategoryClass(entry.category)}">${entry.category}</span>
                </td>
                <td class="px-4 py-2 text-sm text-gray-900">${escapeHtml(entry.action)}</td>
                <td class="px-4 py-2 text-sm text-gray-500">${escapeHtml(entry.details || '')}</td>
            </tr>
        `).join('');

    } catch (error) {
        console.error('Error loading audit log:', error);
        tbody.innerHTML = '<tr><td colspan="4" class="px-4 py-4 text-center text-red-500">Failed to load audit log</td></tr>';
    }
}

function getCategoryClass(category) {
    const classes = {
        'backup': 'bg-blue-100 text-blue-800',
        'container': 'bg-green-100 text-green-800',
        'git': 'bg-purple-100 text-purple-800',
        'auth': 'bg-yellow-100 text-yellow-800',
        'system': 'bg-gray-100 text-gray-800'
    };
    return classes[category] || 'bg-gray-100 text-gray-800';
}

// ============================================================================
// Quick Actions
// ============================================================================

async function restartAllContainers() {
    if (!confirm('Are you sure you want to restart ALL containers? This will briefly interrupt all Odoo services.')) {
        return;
    }

    showMessage('Restarting all containers...', 'info');

    try {
        const response = await fetch('/api/settings/restart-all', {
            method: 'POST'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Failed to restart containers');
        }

        showMessage('All containers restarted successfully', 'success');

    } catch (error) {
        console.error('Error restarting containers:', error);
        showMessage(`Failed to restart: ${error.message}`, 'error');
    }
}

async function cleanupOldBackups() {
    const days = prompt('Delete backups older than how many days?', '7');

    if (!days) return;

    const daysNum = parseInt(days);
    if (isNaN(daysNum) || daysNum < 1) {
        showMessage('Please enter a valid number of days', 'error');
        return;
    }

    if (!confirm(`This will delete all backups older than ${daysNum} days. Continue?`)) {
        return;
    }

    try {
        const response = await fetch('/api/settings/cleanup-backups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ days: daysNum })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Cleanup failed');
        }

        showMessage(`Cleaned up ${result.deleted} old backup(s)`, 'success');

    } catch (error) {
        console.error('Error cleaning up backups:', error);
        showMessage(`Cleanup failed: ${error.message}`, 'error');
    }
}

// ============================================================================
// Utility Functions
// ============================================================================

function formatTimestamp(isoString) {
    try {
        const date = new Date(isoString);
        return date.toLocaleString();
    } catch (e) {
        return isoString;
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showMessage(message, type = 'info') {
    const messageArea = document.getElementById('message-area');
    const alertBox = document.getElementById('alert-box');
    const alertMessage = document.getElementById('alert-message');
    const alertIcon = document.getElementById('alert-icon');

    alertMessage.textContent = message;

    alertBox.className = 'rounded-md p-4';

    if (type === 'success') {
        alertBox.classList.add('bg-green-50', 'text-green-800');
        alertIcon.textContent = '✓';
    } else if (type === 'error') {
        alertBox.classList.add('bg-red-50', 'text-red-800');
        alertIcon.textContent = '✗';
    } else if (type === 'warning') {
        alertBox.classList.add('bg-yellow-50', 'text-yellow-800');
        alertIcon.textContent = '⚠';
    } else {
        alertBox.classList.add('bg-blue-50', 'text-blue-800');
        alertIcon.textContent = 'i';
    }

    messageArea.classList.remove('hidden');

    setTimeout(hideMessage, 5000);
}

function hideMessage() {
    const messageArea = document.getElementById('message-area');
    messageArea.classList.add('hidden');
}
