/**
 * Git Repository Management UI
 * Handles repository listing, cloning, pulling, and removal
 */

// State
let reposByEnv = {};
let deleteRepoId = null;
let deleteRepoEnv = null;

// ============================================================================
// Environment Tab Management
// ============================================================================

function selectEnvironment(env) {
    window.currentEnv = env;

    // Update tab styling
    document.querySelectorAll('.env-tab').forEach(tab => {
        const tabEnv = tab.id.replace('tab-', '');
        if (tabEnv === env) {
            tab.classList.remove('border-transparent', 'text-gray-500');
            tab.classList.add('border-indigo-500', 'text-indigo-600');
            // Update count badge
            const count = tab.querySelector('span');
            if (count) {
                count.classList.remove('bg-gray-100', 'text-gray-600');
                count.classList.add('bg-indigo-100', 'text-indigo-600');
            }
        } else {
            tab.classList.remove('border-indigo-500', 'text-indigo-600');
            tab.classList.add('border-transparent', 'text-gray-500');
            // Update count badge
            const count = tab.querySelector('span');
            if (count) {
                count.classList.remove('bg-indigo-100', 'text-indigo-600');
                count.classList.add('bg-gray-100', 'text-gray-600');
            }
        }
    });

    // Render repositories for selected environment
    renderRepositories();
}

// ============================================================================
// Repository Loading
// ============================================================================

async function loadAllRepositories() {
    try {
        const response = await fetch('/api/repos');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        reposByEnv = await response.json();

        // Update counts
        updateRepoCounts();

        // Render current environment
        renderRepositories();
    } catch (error) {
        console.error('Error loading repositories:', error);
        showError('Failed to load repositories: ' + error.message);
    }
}

function updateRepoCounts() {
    for (const env of window.environments) {
        const count = (reposByEnv[env] || []).length;
        const countEl = document.getElementById(`count-${env}`);
        if (countEl) {
            countEl.textContent = count;
        }
    }
}

// ============================================================================
// Repository Rendering
// ============================================================================

function renderRepositories() {
    const grid = document.getElementById('repo-grid');
    const repos = reposByEnv[window.currentEnv] || [];

    if (repos.length === 0) {
        grid.innerHTML = `
            <div class="text-center py-12">
                <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path>
                </svg>
                <h3 class="mt-2 text-sm font-medium text-gray-900">No repositories</h3>
                <p class="mt-1 text-sm text-gray-500">Get started by adding a git repository.</p>
                <div class="mt-6">
                    <button onclick="showAddRepoModal()" class="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700">
                        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
                        </svg>
                        Add Repository
                    </button>
                </div>
            </div>
        `;
        return;
    }

    grid.innerHTML = repos.map(repo => createRepoCard(repo)).join('');
}

function createRepoCard(repo) {
    const statusColor = getStatusColor(repo);
    const statusIcon = getStatusIcon(repo);
    const syncStatus = getSyncStatus(repo);

    return `
        <div class="bg-white shadow rounded-lg overflow-hidden">
            <div class="p-6">
                <div class="flex items-center justify-between">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <svg class="h-8 w-8 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path>
                            </svg>
                        </div>
                        <div class="ml-4">
                            <h3 class="text-lg font-medium text-gray-900">${escapeHtml(repo.name)}</h3>
                            <p class="text-sm text-gray-500">${escapeHtml(repo.dirname || repo.path)}</p>
                        </div>
                    </div>
                    <div class="flex items-center space-x-2">
                        <span class="${statusColor} inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium">
                            ${statusIcon} ${repo.status || 'unknown'}
                        </span>
                    </div>
                </div>

                ${repo.status === 'error' || repo.status === 'missing' ? `
                    <div class="mt-4 bg-red-50 rounded-md p-3">
                        <p class="text-sm text-red-700">${escapeHtml(repo.error || 'Unknown error')}</p>
                    </div>
                ` : `
                    <div class="mt-4 grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <span class="text-gray-500">Branch:</span>
                            <span class="ml-2 font-medium">${escapeHtml(repo.current_branch || 'N/A')}</span>
                        </div>
                        <div>
                            <span class="text-gray-500">Sync:</span>
                            <span class="ml-2">${syncStatus}</span>
                        </div>
                        ${repo.last_commit ? `
                            <div class="col-span-2">
                                <span class="text-gray-500">Last Commit:</span>
                                <span class="ml-2 font-mono text-xs">${escapeHtml(repo.last_commit.hash)}</span>
                                <span class="ml-2 text-gray-600 truncate">${escapeHtml(repo.last_commit.message)}</span>
                            </div>
                        ` : ''}
                    </div>

                    ${repo.is_dirty ? `
                        <div class="mt-4 bg-yellow-50 rounded-md p-3">
                            <div class="flex">
                                <svg class="h-5 w-5 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                                </svg>
                                <p class="ml-3 text-sm text-yellow-700">
                                    Repository has uncommitted changes
                                    ${repo.modified_files ? `(${repo.modified_files.length} modified)` : ''}
                                </p>
                            </div>
                        </div>
                    ` : ''}
                `}

                <div class="mt-6 flex items-center justify-between">
                    <div class="flex space-x-3">
                        <button onclick="pullRepository('${repo.id}')"
                                ${repo.status !== 'ok' || repo.is_dirty ? 'disabled' : ''}
                                class="inline-flex items-center px-3 py-1.5 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed">
                            <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
                            </svg>
                            Pull
                        </button>
                        <button onclick="showRepoDetail('${repo.id}')"
                                class="inline-flex items-center px-3 py-1.5 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">
                            <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                            </svg>
                            Details
                        </button>
                    </div>
                    <button onclick="showDeleteModal('${repo.id}', '${escapeHtml(repo.name)}')"
                            class="inline-flex items-center px-3 py-1.5 border border-red-300 shadow-sm text-sm font-medium rounded-md text-red-700 bg-white hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500">
                        <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                        </svg>
                        Remove
                    </button>
                </div>
            </div>
        </div>
    `;
}

function getStatusColor(repo) {
    switch (repo.status) {
        case 'ok':
            return repo.is_dirty ? 'bg-yellow-100 text-yellow-800' : 'bg-green-100 text-green-800';
        case 'error':
        case 'missing':
            return 'bg-red-100 text-red-800';
        default:
            return 'bg-gray-100 text-gray-800';
    }
}

function getStatusIcon(repo) {
    switch (repo.status) {
        case 'ok':
            return repo.is_dirty ? '!' : '&#10003;';
        case 'error':
        case 'missing':
            return '&#10007;';
        default:
            return '?';
    }
}

function getSyncStatus(repo) {
    if (repo.sync_error) {
        return `<span class="text-red-600" title="${escapeHtml(repo.sync_error)}">sync error</span>`;
    }

    const ahead = repo.ahead || 0;
    const behind = repo.behind || 0;

    if (ahead === 0 && behind === 0) {
        return '<span class="text-green-600">up to date</span>';
    }

    let parts = [];
    if (ahead > 0) {
        parts.push(`<span class="text-blue-600">${ahead} ahead</span>`);
    }
    if (behind > 0) {
        parts.push(`<span class="text-orange-600">${behind} behind</span>`);
    }

    return parts.join(', ');
}

// ============================================================================
// Add Repository Modal
// ============================================================================

function showAddRepoModal() {
    const modal = document.getElementById('add-repo-modal');
    modal.classList.remove('hidden');

    // Set current environment as default
    document.getElementById('repo-env').value = window.currentEnv;

    // Clear form
    document.getElementById('repo-url').value = '';
    document.getElementById('repo-dirname').value = '';
    document.getElementById('repo-branch').value = 'main';
    document.getElementById('repo-name').value = '';
    document.getElementById('auto-restart').checked = true;

    // Hide error
    document.getElementById('add-repo-error').classList.add('hidden');
}

function closeAddRepoModal() {
    document.getElementById('add-repo-modal').classList.add('hidden');
}

async function addRepository() {
    const env = document.getElementById('repo-env').value;
    const url = document.getElementById('repo-url').value.trim();
    const dirname = document.getElementById('repo-dirname').value.trim();
    const branch = document.getElementById('repo-branch').value.trim() || 'main';
    const name = document.getElementById('repo-name').value.trim();
    const autoRestart = document.getElementById('auto-restart').checked;

    // Validation
    if (!url) {
        showAddRepoError('Git URL is required');
        return;
    }
    if (!dirname) {
        showAddRepoError('Directory name is required');
        return;
    }

    // Disable submit button
    const submitBtn = document.getElementById('add-repo-submit');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<svg class="animate-spin h-4 w-4 mr-2 inline" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Cloning...';

    try {
        const response = await fetch(`/api/repos/${env}/add`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                url,
                dirname,
                branch,
                name: name || null,
                auto_restart: autoRestart
            })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Clone failed');
        }

        // Success
        closeAddRepoModal();

        // Switch to the environment where repo was added
        window.currentEnv = env;

        // Reload repositories
        await loadAllRepositories();

        // Show success message
        showToast(`Repository cloned successfully: ${result.repo_id}`, 'success');

    } catch (error) {
        console.error('Error adding repository:', error);
        showAddRepoError(error.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
    }
}

function showAddRepoError(message) {
    const errorEl = document.getElementById('add-repo-error');
    const errorText = document.getElementById('add-repo-error-text');
    errorText.textContent = message;
    errorEl.classList.remove('hidden');
}

// ============================================================================
// Pull Repository
// ============================================================================

async function pullRepository(repoId) {
    const env = window.currentEnv;

    // Find the repo card and show loading state
    const card = document.querySelector(`button[onclick="pullRepository('${repoId}')"]`);
    if (card) {
        card.disabled = true;
        card.innerHTML = '<svg class="animate-spin h-4 w-4 mr-1.5 inline" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Pulling...';
    }

    try {
        const response = await fetch(`/api/repos/${env}/${repoId}/pull`, {
            method: 'POST'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Pull failed');
        }

        // Show result
        let message = result.message || `Pulled ${result.commits_pulled} commit(s)`;
        if (result.auto_restart && result.commits_pulled > 0) {
            message += ' - Container restarted';
        }

        showToast(message, 'success');

        // Reload repositories to update status
        await loadAllRepositories();

    } catch (error) {
        console.error('Error pulling repository:', error);
        showToast(`Pull failed: ${error.message}`, 'error');
    }
}

// ============================================================================
// Repository Detail Modal
// ============================================================================

async function showRepoDetail(repoId) {
    const modal = document.getElementById('repo-detail-modal');
    const content = document.getElementById('repo-detail-content');

    // Show loading
    content.innerHTML = `
        <div class="text-center py-8">
            <svg class="mx-auto h-8 w-8 text-gray-400 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <p class="mt-2 text-gray-500">Loading details...</p>
        </div>
    `;
    modal.classList.remove('hidden');

    try {
        const env = window.currentEnv;
        const response = await fetch(`/api/repos/${env}/${repoId}/status`);
        const repo = await response.json();

        if (!response.ok) {
            throw new Error(repo.error || 'Failed to load details');
        }

        content.innerHTML = `
            <div>
                <h3 class="text-lg font-medium text-gray-900">${escapeHtml(repo.name)}</h3>
                <p class="mt-1 text-sm text-gray-500">${escapeHtml(repo.path)}</p>
            </div>

            <div class="mt-6 border-t border-gray-200 pt-6">
                <dl class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2">
                    <div>
                        <dt class="text-sm font-medium text-gray-500">URL</dt>
                        <dd class="mt-1 text-sm text-gray-900 font-mono break-all">${escapeHtml(repo.url || 'N/A')}</dd>
                    </div>
                    <div>
                        <dt class="text-sm font-medium text-gray-500">Status</dt>
                        <dd class="mt-1 text-sm text-gray-900">${getStatusBadge(repo)}</dd>
                    </div>
                    <div>
                        <dt class="text-sm font-medium text-gray-500">Current Branch</dt>
                        <dd class="mt-1 text-sm text-gray-900">${escapeHtml(repo.current_branch || 'N/A')}</dd>
                    </div>
                    <div>
                        <dt class="text-sm font-medium text-gray-500">Configured Branch</dt>
                        <dd class="mt-1 text-sm text-gray-900">${escapeHtml(repo.configured_branch || 'N/A')}</dd>
                    </div>
                    <div>
                        <dt class="text-sm font-medium text-gray-500">Auto-restart</dt>
                        <dd class="mt-1 text-sm text-gray-900">${repo.auto_restart ? 'Yes' : 'No'}</dd>
                    </div>
                    <div>
                        <dt class="text-sm font-medium text-gray-500">Added</dt>
                        <dd class="mt-1 text-sm text-gray-900">${formatDate(repo.added_at)}</dd>
                    </div>
                    ${repo.ahead !== undefined ? `
                    <div>
                        <dt class="text-sm font-medium text-gray-500">Commits Ahead</dt>
                        <dd class="mt-1 text-sm text-gray-900">${repo.ahead}</dd>
                    </div>
                    <div>
                        <dt class="text-sm font-medium text-gray-500">Commits Behind</dt>
                        <dd class="mt-1 text-sm text-gray-900">${repo.behind}</dd>
                    </div>
                    ` : ''}
                </dl>
            </div>

            ${repo.last_commit ? `
            <div class="mt-6 border-t border-gray-200 pt-6">
                <h4 class="text-sm font-medium text-gray-900">Last Commit</h4>
                <div class="mt-2 bg-gray-50 rounded-md p-4">
                    <p class="font-mono text-sm text-gray-700">${escapeHtml(repo.last_commit.hash)}</p>
                    <p class="mt-1 text-sm text-gray-900">${escapeHtml(repo.last_commit.message)}</p>
                    <p class="mt-1 text-xs text-gray-500">
                        by ${escapeHtml(repo.last_commit.author)} on ${formatDate(repo.last_commit.date)}
                    </p>
                </div>
            </div>
            ` : ''}

            ${repo.modified_files && repo.modified_files.length > 0 ? `
            <div class="mt-6 border-t border-gray-200 pt-6">
                <h4 class="text-sm font-medium text-gray-900">Modified Files</h4>
                <ul class="mt-2 text-sm text-gray-600 font-mono">
                    ${repo.modified_files.map(f => `<li class="truncate">${escapeHtml(f)}</li>`).join('')}
                </ul>
            </div>
            ` : ''}

            ${repo.sync_error ? `
            <div class="mt-6 bg-red-50 rounded-md p-4">
                <p class="text-sm text-red-700">Sync Error: ${escapeHtml(repo.sync_error)}</p>
            </div>
            ` : ''}
        `;

    } catch (error) {
        console.error('Error loading repo details:', error);
        content.innerHTML = `
            <div class="text-center py-8">
                <svg class="mx-auto h-12 w-12 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                </svg>
                <p class="mt-2 text-red-600">${escapeHtml(error.message)}</p>
            </div>
        `;
    }
}

function closeDetailModal() {
    document.getElementById('repo-detail-modal').classList.add('hidden');
}

function getStatusBadge(repo) {
    const color = getStatusColor(repo);
    return `<span class="${color} inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium">
        ${repo.status || 'unknown'}
        ${repo.is_dirty ? ' (dirty)' : ''}
    </span>`;
}

// ============================================================================
// Delete Repository Modal
// ============================================================================

function showDeleteModal(repoId, repoName) {
    deleteRepoId = repoId;
    deleteRepoEnv = window.currentEnv;

    document.getElementById('delete-confirm-text').textContent =
        `Are you sure you want to remove "${repoName}" from the registry?`;
    document.getElementById('delete-files-checkbox').checked = false;
    document.getElementById('delete-confirm-modal').classList.remove('hidden');
}

function closeDeleteModal() {
    document.getElementById('delete-confirm-modal').classList.add('hidden');
    deleteRepoId = null;
    deleteRepoEnv = null;
}

async function confirmDelete() {
    if (!deleteRepoId || !deleteRepoEnv) return;

    const deleteFiles = document.getElementById('delete-files-checkbox').checked;

    const btn = document.getElementById('delete-confirm-btn');
    btn.disabled = true;
    btn.textContent = 'Removing...';

    try {
        const response = await fetch(`/api/repos/${deleteRepoEnv}/${deleteRepoId}?delete_files=${deleteFiles}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Delete failed');
        }

        closeDeleteModal();
        showToast('Repository removed successfully', 'success');
        await loadAllRepositories();

    } catch (error) {
        console.error('Error deleting repository:', error);
        showToast(`Failed to remove: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Remove';
    }
}

// ============================================================================
// Helper Functions
// ============================================================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    try {
        const date = new Date(dateStr);
        return date.toLocaleString();
    } catch {
        return dateStr;
    }
}

function showError(message) {
    const grid = document.getElementById('repo-grid');
    grid.innerHTML = `
        <div class="text-center py-12">
            <svg class="mx-auto h-12 w-12 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
            </svg>
            <h3 class="mt-2 text-sm font-medium text-gray-900">Error</h3>
            <p class="mt-1 text-sm text-red-600">${escapeHtml(message)}</p>
            <div class="mt-6">
                <button onclick="loadAllRepositories()" class="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700">
                    Retry
                </button>
            </div>
        </div>
    `;
}

function showToast(message, type = 'info') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg text-white z-50 transition-opacity duration-300 ${
        type === 'success' ? 'bg-green-600' :
        type === 'error' ? 'bg-red-600' :
        'bg-blue-600'
    }`;
    toast.textContent = message;

    document.body.appendChild(toast);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Load initial data
    loadAllRepositories();

    // Auto-refresh every 60 seconds
    setInterval(loadAllRepositories, 60000);
});
