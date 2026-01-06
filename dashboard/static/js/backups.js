// Backup management JavaScript

let currentTab = 'backups';
let pendingConfirmAction = null;
let refreshInterval = null;
let databaseInfo = {};  // Store database info for copy operations

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadBackups();
    loadBackupConfig();
    loadDatabaseInfo();
    loadSchedules();
    startAutoRefresh();
});

// ============================================================================
// Tab Management
// ============================================================================

function switchTab(tabName) {
    currentTab = tabName;

    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('border-indigo-500', 'text-indigo-600');
        btn.classList.add('border-transparent', 'text-gray-500');
    });

    const activeTab = document.getElementById(`tab-${tabName}`);
    if (activeTab) {
        activeTab.classList.remove('border-transparent', 'text-gray-500');
        activeTab.classList.add('border-indigo-500', 'text-indigo-600');
    }

    // Show/hide panels
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.add('hidden');
    });

    const activePanel = document.getElementById(`panel-${tabName}`);
    if (activePanel) {
        activePanel.classList.remove('hidden');
    }

    // Load data for tab
    if (tabName === 'backups') {
        loadBackups();
    } else if (tabName === 'schedules') {
        loadSchedules();
    } else if (tabName === 'copy') {
        loadDatabaseInfo();
    } else if (tabName === 'config') {
        loadBackupConfig();
    }
}

// ============================================================================
// Backup List
// ============================================================================

async function loadBackups() {
    const envFilter = document.getElementById('env-filter').value;
    const listContainer = document.getElementById('backup-list');
    const loadingEl = document.getElementById('backup-loading');

    if (loadingEl) {
        loadingEl.classList.remove('hidden');
    }

    try {
        const url = envFilter ? `/api/backups/${envFilter}` : '/api/backups';
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (loadingEl) {
            loadingEl.classList.add('hidden');
        }

        renderBackupList(data, envFilter);

    } catch (error) {
        console.error('Error loading backups:', error);
        if (loadingEl) {
            loadingEl.classList.add('hidden');
        }
        listContainer.innerHTML = `
            <div class="text-center py-8 text-red-600">
                Failed to load backups: ${error.message}
            </div>
        `;
    }
}

function renderBackupList(data, envFilter) {
    const listContainer = document.getElementById('backup-list');

    // Handle both single environment and all environments response
    let allBackups = [];

    if (Array.isArray(data)) {
        // Single environment response
        allBackups = data.map(b => ({ ...b, env: envFilter }));
    } else {
        // All environments response
        for (const [env, backups] of Object.entries(data)) {
            allBackups.push(...backups.map(b => ({ ...b, env })));
        }
        // Sort by timestamp
        allBackups.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    }

    if (allBackups.length === 0) {
        listContainer.innerHTML = `
            <div class="text-center py-8 text-gray-500">
                <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                </svg>
                <p class="mt-2">No backups found</p>
                <button onclick="showCreateBackupModal()" class="mt-4 btn btn-primary btn-sm">
                    Create Your First Backup
                </button>
            </div>
        `;
        return;
    }

    listContainer.innerHTML = allBackups.map(backup => createBackupCard(backup)).join('');
}

function createBackupCard(backup) {
    const timestamp = new Date(backup.timestamp);
    const formattedDate = timestamp.toLocaleString();
    const totalSize = formatBytes(backup.total_size || 0);

    const typeColors = {
        'full': 'bg-green-100 text-green-800',
        'database': 'bg-blue-100 text-blue-800',
        'filestore': 'bg-yellow-100 text-yellow-800'
    };

    const envColors = {
        'test': 'text-blue-600',
        'staging': 'text-yellow-600',
        'prod': 'text-red-600'
    };

    return `
        <div class="bg-white shadow rounded-lg p-4 hover:shadow-md transition-shadow">
            <div class="flex justify-between items-start">
                <div class="flex-1">
                    <div class="flex items-center space-x-2 mb-2">
                        <span class="font-semibold uppercase ${envColors[backup.env] || 'text-gray-600'}">${backup.env}</span>
                        <span class="px-2 py-1 text-xs font-medium rounded ${typeColors[backup.type] || 'bg-gray-100 text-gray-800'}">${backup.type}</span>
                        ${!backup.files_exist ? '<span class="px-2 py-1 text-xs font-medium rounded bg-red-100 text-red-800">Files Missing</span>' : ''}
                    </div>
                    <p class="text-sm text-gray-600">${formattedDate}</p>
                    ${backup.description ? `<p class="text-sm text-gray-500 mt-1">${escapeHtml(backup.description)}</p>` : ''}
                    <p class="text-sm text-gray-500 mt-1">
                        ${backup.database_name ? `Database: ${backup.database_name} | ` : ''}
                        Size: ${totalSize}
                    </p>
                </div>
                <div class="flex space-x-2">
                    ${backup.files_exist && (backup.type === 'full' || backup.type === 'database') ? `
                        <button onclick="downloadBackup('${backup.env}', '${backup.backup_id}', 'database')" class="btn btn-sm btn-secondary" title="Download Database">
                            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                            DB
                        </button>
                    ` : ''}
                    ${backup.files_exist && (backup.type === 'full' || backup.type === 'filestore') ? `
                        <button onclick="downloadBackup('${backup.env}', '${backup.backup_id}', 'filestore')" class="btn btn-sm btn-secondary" title="Download Filestore">
                            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                            Files
                        </button>
                    ` : ''}
                    <button onclick="uploadBackup('${backup.env}', '${backup.backup_id}')" class="btn btn-sm btn-info" title="Upload to Remote">
                        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                        </svg>
                    </button>
                    <button onclick="confirmDeleteBackup('${backup.env}', '${backup.backup_id}')" class="btn btn-sm btn-error" title="Delete">
                        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    `;
}

// ============================================================================
// Create Backup
// ============================================================================

function showCreateBackupModal() {
    document.getElementById('create-backup-modal').classList.remove('hidden');
}

function closeCreateBackupModal() {
    document.getElementById('create-backup-modal').classList.add('hidden');
    document.getElementById('backup-description').value = '';
    document.getElementById('backup-upload').checked = false;
}

async function createBackup() {
    const env = document.getElementById('backup-env').value;
    const type = document.getElementById('backup-type').value;
    const description = document.getElementById('backup-description').value;
    const upload = document.getElementById('backup-upload').checked;

    const btn = document.getElementById('create-backup-btn');
    btn.disabled = true;
    btn.textContent = 'Creating...';

    try {
        const response = await fetch(`/api/backups/${env}/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, description, upload })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Backup creation failed');
        }

        showMessage(`Backup created successfully: ${result.backup_id}`, 'success');
        closeCreateBackupModal();
        loadBackups();

    } catch (error) {
        console.error('Error creating backup:', error);
        showMessage(`Failed to create backup: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Create Backup';
    }
}

// ============================================================================
// Backup Actions
// ============================================================================

function downloadBackup(env, backupId, fileType) {
    window.location.href = `/api/backups/${env}/${backupId}/download?type=${fileType}`;
}

async function uploadBackup(env, backupId) {
    showMessage('Uploading backup to remote storage...', 'info');

    try {
        const response = await fetch(`/api/backups/${env}/${backupId}/upload`, {
            method: 'POST'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Upload failed');
        }

        if (result.uploaded) {
            showMessage(`Backup uploaded to ${result.backend}`, 'success');
        } else {
            showMessage(result.message || 'Upload not configured', 'warning');
        }

    } catch (error) {
        console.error('Error uploading backup:', error);
        showMessage(`Failed to upload backup: ${error.message}`, 'error');
    }
}

function confirmDeleteBackup(env, backupId) {
    pendingConfirmAction = () => deleteBackup(env, backupId);

    document.getElementById('confirm-title').textContent = 'Delete Backup?';
    document.getElementById('confirm-message').textContent =
        `Are you sure you want to delete backup "${backupId}"? This action cannot be undone.`;
    document.getElementById('confirm-modal').classList.remove('hidden');
}

async function deleteBackup(env, backupId) {
    closeConfirmModal();

    try {
        const response = await fetch(`/api/backups/${env}/${backupId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Delete failed');
        }

        showMessage('Backup deleted successfully', 'success');
        loadBackups();

    } catch (error) {
        console.error('Error deleting backup:', error);
        showMessage(`Failed to delete backup: ${error.message}`, 'error');
    }
}

// ============================================================================
// Database Copy
// ============================================================================

async function loadDatabaseInfo() {
    try {
        const response = await fetch('/api/databases/info');
        const data = await response.json();

        // Store database info globally for copy operations
        databaseInfo = data;

        console.log('Database info response:', data);

        for (const [env, info] of Object.entries(data)) {
            console.log(`Database info for ${env}:`, info);

            // Log debug steps if available
            if (info.debug && info.debug.steps) {
                console.log(`Debug steps for ${env}:`, info.debug.steps);
            }

            const nameEl = document.getElementById(`db-name-${env}`);
            const sizeEl = document.getElementById(`db-size-${env}`);
            const tablesEl = document.getElementById(`db-tables-${env}`);
            const cardEl = document.getElementById(`db-info-${env}`);

            if (nameEl) {
                nameEl.textContent = info.name || 'Not available';
            }
            if (sizeEl) {
                sizeEl.textContent = info.size || 'Unknown';
            }
            if (tablesEl) {
                tablesEl.textContent = info.table_count || 0;
            }

            // Show error and debug info if not available
            if (!info.available && cardEl) {
                let debugHtml = '';
                if (info.error) {
                    debugHtml += `<p class="text-red-600 text-xs mt-2">Error: ${escapeHtml(info.error)}</p>`;
                }
                if (info.debug && info.debug.steps) {
                    debugHtml += `<details class="mt-2 text-xs"><summary class="cursor-pointer text-blue-600">Debug steps</summary><ul class="mt-1 text-gray-500">`;
                    for (const step of info.debug.steps) {
                        const isError = step.includes('FAILED') || step.includes('EXCEPTION');
                        debugHtml += `<li class="${isError ? 'text-red-500' : ''}">${escapeHtml(step)}</li>`;
                    }
                    debugHtml += `</ul></details>`;
                }

                // Find or create debug container
                let debugContainer = cardEl.querySelector('.debug-info');
                if (!debugContainer) {
                    debugContainer = document.createElement('div');
                    debugContainer.className = 'debug-info';
                    cardEl.appendChild(debugContainer);
                }
                debugContainer.innerHTML = debugHtml;
            }
        }

    } catch (error) {
        console.error('Error loading database info:', error);
    }
}

function startDatabaseCopy() {
    const source = document.getElementById('copy-source').value;
    const target = document.getElementById('copy-target').value;
    const includeFilestore = document.getElementById('copy-filestore').checked;
    const includeAddons = document.getElementById('copy-addons').checked;

    if (source === target) {
        showMessage('Source and target environments must be different', 'error');
        return;
    }

    // Check if source has a database
    const sourceInfo = databaseInfo[source];
    if (!sourceInfo || !sourceInfo.available || !sourceInfo.name) {
        showMessage(`No database found in ${source} environment`, 'error');
        return;
    }

    // Check if target has a database
    const targetInfo = databaseInfo[target];
    const targetHasDb = targetInfo && targetInfo.available && targetInfo.name;

    if (targetHasDb) {
        // Target has existing database - use same name, show confirmation
        showCopyConfirmation(source, target, includeFilestore, includeAddons, targetInfo.name, sourceInfo.name);
    } else {
        // Target has no database - prompt for a name
        promptForDatabaseName(source, target, includeFilestore, includeAddons, sourceInfo.name);
    }
}

function promptForDatabaseName(source, target, includeFilestore, includeAddons, sourceDbName) {
    // Create a simple prompt for the database name
    const defaultName = `${target}_odoo`;
    const dbName = prompt(
        `No database exists in ${target.toUpperCase()} environment.\n\n` +
        `Enter a name for the new database:`,
        defaultName
    );

    if (dbName === null) {
        // User cancelled
        return;
    }

    const trimmedName = dbName.trim();
    if (!trimmedName) {
        showMessage('Database name cannot be empty', 'error');
        return;
    }

    // Validate database name (PostgreSQL rules)
    if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(trimmedName)) {
        showMessage('Invalid database name. Use letters, numbers, and underscores only. Must start with a letter or underscore.', 'error');
        return;
    }

    if (trimmedName.length > 63) {
        showMessage('Database name must be 63 characters or less', 'error');
        return;
    }

    showCopyConfirmation(source, target, includeFilestore, includeAddons, trimmedName, sourceDbName, true);
}

function showCopyConfirmation(source, target, includeFilestore, includeAddons, targetDbName, sourceDbName, isNewDb = false) {
    pendingConfirmAction = () => executeDatabaseCopy(source, target, includeFilestore, includeAddons, targetDbName);

    const actionText = isNewDb ? 'CREATE new database' : 'OVERWRITE existing database';
    const copyAction = isNewDb ? 'copied' : 'overwritten';

    let fileCopyInfo = [];
    if (includeFilestore) fileCopyInfo.push('filestore');
    if (includeAddons) fileCopyInfo.push('addons');
    const fileCopyText = fileCopyInfo.length > 0
        ? `${fileCopyInfo.join(' and ')} will also be ${copyAction}.`
        : 'Filestore and addons will NOT be copied.';

    document.getElementById('confirm-title').textContent = isNewDb ? 'Create Database?' : 'DANGER: Overwrite Database?';
    document.getElementById('confirm-message').innerHTML = `
        <strong class="${isNewDb ? 'text-blue-600' : 'text-red-600'}">This will ${actionText} in ${target.toUpperCase()}!</strong><br><br>
        Copying from: <strong>${source}</strong> (database: ${sourceDbName})<br>
        Copying to: <strong>${target}</strong> (database: ${targetDbName})<br>
        ${fileCopyText}<br><br>
        ${isNewDb ? 'Continue?' : 'This action CANNOT be undone. Continue?'}
    `;
    document.getElementById('confirm-btn').textContent = isNewDb ? 'Yes, Create Database' : 'Yes, Overwrite Everything';
    document.getElementById('confirm-modal').classList.remove('hidden');
}

async function executeDatabaseCopy(source, target, includeFilestore, includeAddons, targetDbName = null) {
    closeConfirmModal();

    const btn = document.getElementById('copy-btn');
    const progress = document.getElementById('copy-progress');
    const status = document.getElementById('copy-status');

    btn.disabled = true;
    progress.classList.remove('hidden');
    status.textContent = `Stopping ${target} container...`;

    try {
        const requestBody = {
            source_env: source,
            target_env: target,
            include_filestore: includeFilestore,
            include_addons: includeAddons
        };

        // Only include target_db_name if provided (for new databases)
        if (targetDbName) {
            requestBody.target_db_name = targetDbName;
        }

        const response = await fetch('/api/databases/copy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Copy failed');
        }

        if (result.success) {
            let message = `Database copied from ${source} to ${target}`;
            if (result.target_db_name) {
                message += ` (database: ${result.target_db_name})`;
            }
            let extras = [];
            if (result.filestore_copied) extras.push('filestore');
            if (result.addons_copied) extras.push('addons');
            if (extras.length > 0) {
                message += ` including ${extras.join(' and ')}`;
            }
            showMessage(message, 'success');
            loadDatabaseInfo();
        } else {
            showMessage(`Copy partially failed: ${result.errors.join(', ')}`, 'warning');
        }

    } catch (error) {
        console.error('Error copying database:', error);
        showMessage(`Failed to copy database: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        progress.classList.add('hidden');
    }
}

// ============================================================================
// Configuration
// ============================================================================

async function loadBackupConfig() {
    try {
        const response = await fetch('/api/backups/config');
        const config = await response.json();

        // Storage backend
        const backend = config.storage_backend || 'local';
        document.querySelector(`input[name="storage-backend"][value="${backend}"]`).checked = true;
        toggleStorageConfig();

        // S3 config
        if (config.s3) {
            document.getElementById('s3-endpoint').value = config.s3.endpoint || '';
            document.getElementById('s3-bucket').value = config.s3.bucket || '';
            document.getElementById('s3-access-key').value = config.s3.access_key || '';
            document.getElementById('s3-region').value = config.s3.region || 'us-east-1';
            // Don't load secret key for security
        }

        // Rsync config
        if (config.rsync) {
            document.getElementById('rsync-host').value = config.rsync.host || '';
            document.getElementById('rsync-username').value = config.rsync.username || '';
            document.getElementById('rsync-remote-path').value = config.rsync.remote_path || '';
            document.getElementById('rsync-ssh-key').value = config.rsync.ssh_key_path || '/root/.ssh/id_rsa';
        }

        // Retention
        if (config.retention) {
            document.getElementById('retention-local').value = config.retention.local_days || 7;
            document.getElementById('retention-remote').value = config.retention.remote_days || 30;
        }

    } catch (error) {
        console.error('Error loading config:', error);
    }
}

function toggleStorageConfig() {
    const backend = document.querySelector('input[name="storage-backend"]:checked').value;

    document.getElementById('s3-config').classList.add('hidden');
    document.getElementById('rsync-config').classList.add('hidden');

    if (backend === 's3') {
        document.getElementById('s3-config').classList.remove('hidden');
    } else if (backend === 'rsync') {
        document.getElementById('rsync-config').classList.remove('hidden');
    }
}

async function saveBackupConfig() {
    const backend = document.querySelector('input[name="storage-backend"]:checked').value;

    const config = {
        storage_backend: backend,
        s3: {
            endpoint: document.getElementById('s3-endpoint').value,
            bucket: document.getElementById('s3-bucket').value,
            access_key: document.getElementById('s3-access-key').value,
            secret_key: document.getElementById('s3-secret-key').value,
            region: document.getElementById('s3-region').value
        },
        rsync: {
            host: document.getElementById('rsync-host').value,
            username: document.getElementById('rsync-username').value,
            remote_path: document.getElementById('rsync-remote-path').value,
            ssh_key_path: document.getElementById('rsync-ssh-key').value
        },
        retention: {
            local_days: parseInt(document.getElementById('retention-local').value) || 7,
            remote_days: parseInt(document.getElementById('retention-remote').value) || 30
        }
    };

    try {
        const response = await fetch('/api/backups/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Save failed');
        }

        showMessage('Configuration saved successfully', 'success');

    } catch (error) {
        console.error('Error saving config:', error);
        showMessage(`Failed to save configuration: ${error.message}`, 'error');
    }
}

async function testS3Connection() {
    const config = {
        endpoint: document.getElementById('s3-endpoint').value,
        bucket: document.getElementById('s3-bucket').value,
        access_key: document.getElementById('s3-access-key').value,
        secret_key: document.getElementById('s3-secret-key').value,
        region: document.getElementById('s3-region').value
    };

    showMessage('Testing S3 connection...', 'info');

    try {
        const response = await fetch('/api/backups/test-s3', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (result.success) {
            showMessage('S3 connection successful!', 'success');
        } else {
            showMessage(`S3 connection failed: ${result.message}`, 'error');
        }

    } catch (error) {
        showMessage(`Test failed: ${error.message}`, 'error');
    }
}

async function testRsyncConnection() {
    const config = {
        host: document.getElementById('rsync-host').value,
        username: document.getElementById('rsync-username').value,
        remote_path: document.getElementById('rsync-remote-path').value,
        ssh_key_path: document.getElementById('rsync-ssh-key').value
    };

    showMessage('Testing rsync connection...', 'info');

    try {
        const response = await fetch('/api/backups/test-rsync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (result.success) {
            showMessage('Rsync connection successful!', 'success');
        } else {
            showMessage(`Rsync connection failed: ${result.message}`, 'error');
        }

    } catch (error) {
        showMessage(`Test failed: ${error.message}`, 'error');
    }
}

// ============================================================================
// Confirmation Modal
// ============================================================================

function closeConfirmModal() {
    document.getElementById('confirm-modal').classList.add('hidden');
    document.getElementById('confirm-btn').textContent = 'Confirm';
    pendingConfirmAction = null;
}

function confirmAction() {
    if (pendingConfirmAction) {
        pendingConfirmAction();
    }
}

// ============================================================================
// Schedules
// ============================================================================

async function loadSchedules() {
    try {
        const response = await fetch('/api/schedules');
        const data = await response.json();

        // Load schedule configurations
        for (const [env, schedule] of Object.entries(data.schedules || {})) {
            applyScheduleToUI(env, schedule);
        }

        // Load job info (next run times)
        for (const job of (data.jobs || [])) {
            const env = job.id.replace('backup_', '');
            const nextEl = document.getElementById(`schedule-next-${env}`);
            if (nextEl && job.next_run_formatted) {
                nextEl.textContent = `Next run: ${job.next_run_formatted}`;
            }
        }

        // Load backup history
        loadBackupHistory();

    } catch (error) {
        console.error('Error loading schedules:', error);
    }
}

function applyScheduleToUI(env, schedule) {
    const enabledEl = document.getElementById(`schedule-enabled-${env}`);
    const frequencyEl = document.getElementById(`schedule-frequency-${env}`);
    const timeEl = document.getElementById(`schedule-time-${env}`);
    const dayEl = document.getElementById(`schedule-day-${env}`);
    const dayOfMonthEl = document.getElementById(`schedule-dayofmonth-${env}`);
    const typeEl = document.getElementById(`schedule-type-${env}`);
    const uploadEl = document.getElementById(`schedule-upload-${env}`);

    if (enabledEl) enabledEl.checked = schedule.enabled || false;
    if (frequencyEl) frequencyEl.value = schedule.frequency || 'daily';
    if (timeEl) timeEl.value = schedule.time || '02:00';
    if (dayEl) dayEl.value = schedule.day || 'sunday';
    if (dayOfMonthEl) dayOfMonthEl.value = schedule.day_of_month || 1;
    if (typeEl) typeEl.value = schedule.type || 'full';
    if (uploadEl) uploadEl.checked = schedule.upload || false;

    updateScheduleUI(env);
}

function updateScheduleUI(env) {
    const frequency = document.getElementById(`schedule-frequency-${env}`).value;
    const dayContainer = document.getElementById(`schedule-day-container-${env}`);
    const dayOfMonthContainer = document.getElementById(`schedule-dayofmonth-container-${env}`);

    // Show/hide day selector based on frequency
    if (dayContainer) {
        dayContainer.classList.toggle('hidden', frequency !== 'weekly');
    }
    if (dayOfMonthContainer) {
        dayOfMonthContainer.classList.toggle('hidden', frequency !== 'monthly');
    }
}

function toggleSchedule(env) {
    const enabled = document.getElementById(`schedule-enabled-${env}`).checked;
    const optionsEl = document.getElementById(`schedule-options-${env}`);

    if (optionsEl) {
        optionsEl.style.opacity = enabled ? '1' : '0.5';
    }
}

async function saveSchedule(env) {
    const schedule = {
        enabled: document.getElementById(`schedule-enabled-${env}`).checked,
        frequency: document.getElementById(`schedule-frequency-${env}`).value,
        time: document.getElementById(`schedule-time-${env}`).value,
        day: document.getElementById(`schedule-day-${env}`).value,
        day_of_month: parseInt(document.getElementById(`schedule-dayofmonth-${env}`).value) || 1,
        type: document.getElementById(`schedule-type-${env}`).value,
        upload: document.getElementById(`schedule-upload-${env}`).checked
    };

    try {
        const response = await fetch(`/api/schedules/${env}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(schedule)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Failed to save schedule');
        }

        showMessage(`Schedule for ${env} saved successfully`, 'success');

        // Reload to get updated next run time
        loadSchedules();

    } catch (error) {
        console.error('Error saving schedule:', error);
        showMessage(`Failed to save schedule: ${error.message}`, 'error');
    }
}

async function triggerBackupNow(env) {
    if (!confirm(`Run backup for ${env.toUpperCase()} now?`)) {
        return;
    }

    showMessage(`Starting backup for ${env}...`, 'info');

    try {
        const response = await fetch(`/api/schedules/${env}/trigger`, {
            method: 'POST'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Backup failed');
        }

        if (result.success) {
            showMessage(`Backup completed: ${result.backup_id}`, 'success');
            loadBackups();
            loadBackupHistory();
        } else {
            throw new Error(result.error || 'Backup failed');
        }

    } catch (error) {
        console.error('Error triggering backup:', error);
        showMessage(`Backup failed: ${error.message}`, 'error');
    }
}

async function loadBackupHistory() {
    try {
        const response = await fetch('/api/schedules/history');
        const history = await response.json();

        const tbody = document.getElementById('history-tbody');
        if (!tbody) return;

        if (history.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-4 text-center text-gray-500">No backup history yet</td></tr>';
            return;
        }

        tbody.innerHTML = history.map(entry => {
            const statusClass = entry.status === 'SUCCESS' ? 'text-green-600' : 'text-red-600';
            const statusIcon = entry.status === 'SUCCESS' ? '✓' : '✗';

            return `
                <tr>
                    <td class="px-4 py-2 text-sm text-gray-600">${formatTimestamp(entry.timestamp)}</td>
                    <td class="px-4 py-2 text-sm font-medium uppercase">${entry.environment}</td>
                    <td class="px-4 py-2 text-sm text-gray-600">${entry.trigger}</td>
                    <td class="px-4 py-2 text-sm ${statusClass}">${statusIcon} ${entry.status}</td>
                    <td class="px-4 py-2 text-sm font-mono text-gray-500">${entry.backup_id || '-'}</td>
                </tr>
            `;
        }).join('');

    } catch (error) {
        console.error('Error loading backup history:', error);
    }
}

function formatTimestamp(isoString) {
    try {
        const date = new Date(isoString);
        return date.toLocaleString();
    } catch (e) {
        return isoString;
    }
}

// ============================================================================
// Utility Functions
// ============================================================================

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function escapeHtml(text) {
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

    messageArea.classList.remove('hidden');

    setTimeout(hideMessage, 5000);
}

function hideMessage() {
    const messageArea = document.getElementById('message-area');
    messageArea.classList.add('hidden');
}

function startAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }

    // Refresh backups every 60 seconds
    refreshInterval = setInterval(() => {
        if (currentTab === 'backups') {
            loadBackups();
        }
    }, 60000);
}

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
});
