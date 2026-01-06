// Container management JavaScript

let refreshInterval = null;

// Load container status on page load
document.addEventListener('DOMContentLoaded', function() {
    loadContainerStatus();
    startAutoRefresh();
});

// Load container status from API
async function loadContainerStatus() {
    try {
        const response = await fetch('/api/containers/status');

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const containers = await response.json();
        renderContainers(containers);
    } catch (error) {
        console.error('Error loading container status:', error);
        showMessage('Failed to load container status: ' + error.message, 'error');
    }
}

// Render containers in the grid
function renderContainers(containers) {
    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';

    const envOrder = ['test', 'staging', 'prod'];

    envOrder.forEach(env => {
        const data = containers[env];
        if (data) {
            const card = createContainerCard(env, data);
            grid.appendChild(card);
        }
    });
}

// Create a container card element
function createContainerCard(env, data) {
    const card = document.createElement('div');
    card.className = 'container-card bg-white rounded-lg shadow-lg p-6 fade-in';

    const statusClass = getStatusClass(data.status);
    const statusIcon = getStatusIcon(data.status);
    const envClass = `env-${env}`;

    const statsHtml = data.stats ? `
        <div class="space-y-2 mb-4 pt-4 border-t border-gray-200">
            <div class="flex justify-between">
                <span class="stat-label">CPU</span>
                <span class="stat-value">${data.stats.cpu}</span>
            </div>
            <div class="flex justify-between">
                <span class="stat-label">Memory</span>
                <span class="stat-value">${data.stats.memory}</span>
            </div>
            <div class="flex justify-between">
                <span class="stat-label">Net I/O</span>
                <span class="stat-value text-xs">${data.stats.net_io}</span>
            </div>
        </div>
    ` : '';

    const uptimeHtml = data.uptime && data.status === 'running' ? `
        <p class="text-sm text-gray-600">Uptime: ${formatUptime(data.uptime)}</p>
    ` : '';

    const containerIdHtml = data.container_id ? `
        <p class="text-xs text-gray-500 font-mono">ID: ${data.container_id}</p>
    ` : '';

    card.innerHTML = `
        <div class="flex justify-between items-center mb-4">
            <h2 class="text-2xl font-bold uppercase ${envClass}">${env}</h2>
            <span class="status-badge status-${data.status}">
                ${statusIcon} ${data.status}
            </span>
        </div>

        <div class="mb-4">
            ${containerIdHtml}
            ${uptimeHtml}
        </div>

        ${statsHtml}

        <div class="flex flex-wrap gap-2">
            <button onclick="controlContainer('${env}', 'start')"
                    class="btn btn-sm btn-success flex-1"
                    ${data.status === 'running' ? 'disabled' : ''}>
                ▶ Start
            </button>
            <button onclick="controlContainer('${env}', 'stop')"
                    class="btn btn-sm btn-error flex-1"
                    ${data.status !== 'running' ? 'disabled' : ''}>
                ⏹ Stop
            </button>
            <button onclick="controlContainer('${env}', 'restart')"
                    class="btn btn-sm btn-warning flex-1"
                    ${data.status !== 'running' ? 'disabled' : ''}>
                🔄 Restart
            </button>
        </div>

        <div class="mt-3">
            <a href="/logs?env=${env}" class="btn btn-sm btn-info w-full">
                📋 View Logs
            </a>
        </div>
    `;

    return card;
}

// Get status CSS class
function getStatusClass(status) {
    const classes = {
        'running': 'status-running',
        'stopped': 'status-stopped',
        'not_found': 'status-not-found',
        'error': 'status-error'
    };
    return classes[status] || 'status-error';
}

// Get status icon
function getStatusIcon(status) {
    const icons = {
        'running': '🟢',
        'stopped': '🔴',
        'not_found': '⚠️',
        'error': '❌'
    };
    return icons[status] || '❓';
}

// Format uptime
function formatUptime(startedAt) {
    if (!startedAt) return 'N/A';

    try {
        const start = new Date(startedAt);
        const now = new Date();
        const diff = now - start;

        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

        if (days > 0) {
            return `${days}d ${hours}h ${minutes}m`;
        } else if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else {
            return `${minutes}m`;
        }
    } catch (error) {
        return 'N/A';
    }
}

// Control container (start, stop, restart)
async function controlContainer(env, action) {
    // Confirmation for production stops
    if (action === 'stop' && env === 'prod') {
        if (!confirm('⚠️ Are you sure you want to stop the PRODUCTION environment?')) {
            return;
        }
    }

    // Confirmation for production restarts
    if (action === 'restart' && env === 'prod') {
        if (!confirm('⚠️ Are you sure you want to restart the PRODUCTION environment?')) {
            return;
        }
    }

    try {
        const response = await fetch(`/api/containers/${env}/${action}`, {
            method: 'POST'
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showMessage(`Successfully ${action}ed ${env} container`, 'success');
            // Refresh status after a short delay
            setTimeout(loadContainerStatus, 2000);
        } else {
            throw new Error(result.message || 'Operation failed');
        }
    } catch (error) {
        console.error(`Error ${action}ing container:`, error);
        showMessage(`Failed to ${action} ${env} container: ${error.message}`, 'error');
    }
}

// Show message alert
function showMessage(message, type = 'info') {
    const messageArea = document.getElementById('message-area');
    const alertBox = document.getElementById('alert-box');
    const alertMessage = document.getElementById('alert-message');
    const alertIcon = document.getElementById('alert-icon');

    // Set message text
    alertMessage.textContent = message;

    // Remove all alert classes
    alertBox.className = 'rounded-md p-4';

    // Add appropriate class based on type
    if (type === 'success') {
        alertBox.classList.add('bg-green-50', 'text-green-800');
        alertIcon.textContent = '✅';
    } else if (type === 'error') {
        alertBox.classList.add('bg-red-50', 'text-red-800');
        alertIcon.textContent = '❌';
    } else if (type === 'warning') {
        alertBox.classList.add('bg-yellow-50', 'text-yellow-800');
        alertIcon.textContent = '⚠️';
    } else {
        alertBox.classList.add('bg-blue-50', 'text-blue-800');
        alertIcon.textContent = 'ℹ️';
    }

    // Show message area
    messageArea.classList.remove('hidden');

    // Auto-hide after 5 seconds
    setTimeout(hideMessage, 5000);
}

// Hide message alert
function hideMessage() {
    const messageArea = document.getElementById('message-area');
    messageArea.classList.add('hidden');
}

// Start auto-refresh
function startAutoRefresh() {
    // Clear any existing interval
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }

    // Refresh every 10 seconds
    refreshInterval = setInterval(loadContainerStatus, 10000);
}

// Stop auto-refresh (useful for debugging)
function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    stopAutoRefresh();
});
