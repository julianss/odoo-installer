/**
 * Log Viewer JavaScript
 * Handles SSE streaming, log display, filtering, and controls
 */

// State variables
let eventSource = null;
let isStreaming = false;
let autoScroll = true;
let lineCount = 0;
const MAX_LINES = 1000;  // Maximum lines to keep in DOM

// DOM Elements (initialized on load)
let logContainer;
let statusDot;
let statusText;
let lineCountEl;
let streamToggle;
let streamIcon;
let streamText;
let autoScrollCheckbox;

/**
 * Initialize DOM element references
 */
function initElements() {
    logContainer = document.getElementById('log-output');
    statusDot = document.getElementById('status-dot');
    statusText = document.getElementById('status-text');
    lineCountEl = document.getElementById('line-count');
    streamToggle = document.getElementById('stream-toggle');
    streamIcon = document.getElementById('stream-icon');
    streamText = document.getElementById('stream-text');
    autoScrollCheckbox = document.getElementById('auto-scroll');

    // Set up event listeners
    if (autoScrollCheckbox) {
        autoScrollCheckbox.addEventListener('change', function() {
            autoScroll = this.checked;
        });
    }

    // Environment change listener
    const envSelect = document.getElementById('env-select');
    if (envSelect) {
        envSelect.addEventListener('change', function() {
            // Update URL
            const url = new URL(window.location);
            url.searchParams.set('env', this.value);
            window.history.pushState({}, '', url);

            // Restart stream if streaming
            if (isStreaming) {
                stopLogStream();
                clearLogs();
                startLogStream();
            } else {
                clearLogs();
                loadLogs();
            }
        });
    }

    // Search input listener (debounced)
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                filterDisplayedLogs();
            }, 300);
        });
    }

    // Level filter listener
    const levelFilter = document.getElementById('level-filter');
    if (levelFilter) {
        levelFilter.addEventListener('change', function() {
            filterDisplayedLogs();
        });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboardShortcuts);
}

/**
 * Get current selected environment
 */
function getSelectedEnv() {
    const envSelect = document.getElementById('env-select');
    return envSelect ? envSelect.value : 'test';
}

/**
 * Get number of lines to load
 */
function getLineCount() {
    const linesSelect = document.getElementById('lines-count');
    return linesSelect ? parseInt(linesSelect.value) : 100;
}

/**
 * Update connection status indicator
 */
function updateStatus(connected, message) {
    if (statusDot) {
        statusDot.className = `w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-gray-400'}`;
    }
    if (statusText) {
        statusText.textContent = message;
    }
}

/**
 * Update line count display
 */
function updateLineCount() {
    if (lineCountEl) {
        lineCountEl.textContent = `${lineCount} lines`;
    }
}

/**
 * Load logs via REST API (non-streaming)
 */
async function loadLogs() {
    const env = getSelectedEnv();
    const lines = getLineCount();

    updateStatus(false, 'Loading...');

    try {
        const response = await fetch(`/api/logs/${env}?lines=${lines}`);
        const data = await response.json();

        if (data.success) {
            clearLogs();
            data.logs.forEach(line => {
                if (line.trim()) {
                    appendLogLine(line, false);
                }
            });
            updateStatus(false, `Loaded ${lineCount} lines`);
            scrollToBottom();
        } else {
            appendLogLine(`[ERROR] ${data.error}`, false);
            updateStatus(false, 'Error loading logs');
        }
    } catch (error) {
        appendLogLine(`[ERROR] Failed to load logs: ${error.message}`, false);
        updateStatus(false, 'Connection error');
    }
}

/**
 * Start SSE log streaming
 */
function startLogStream() {
    if (eventSource) {
        eventSource.close();
    }

    const env = getSelectedEnv();
    updateStatus(false, 'Connecting...');

    eventSource = new EventSource(`/api/logs/${env}/stream?tail=50`);

    eventSource.onopen = function() {
        isStreaming = true;
        updateStatus(true, `Streaming (${env})`);
        updateStreamButton(true);
    };

    eventSource.onmessage = function(event) {
        appendLogLine(event.data, true);
    };

    eventSource.onerror = function(error) {
        console.error('SSE error:', error);
        updateStatus(false, 'Connection lost');

        if (eventSource.readyState === EventSource.CLOSED) {
            isStreaming = false;
            updateStreamButton(false);

            // Auto-reconnect after 5 seconds
            appendLogLine('--- Connection lost. Reconnecting in 5 seconds... ---', false);
            setTimeout(() => {
                if (!isStreaming) {
                    startLogStream();
                }
            }, 5000);
        }
    };
}

/**
 * Stop SSE log streaming
 */
function stopLogStream() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    isStreaming = false;
    updateStatus(false, 'Stopped');
    updateStreamButton(false);
}

/**
 * Toggle streaming on/off
 */
function toggleStream() {
    if (isStreaming) {
        stopLogStream();
    } else {
        startLogStream();
    }
}

/**
 * Update the stream button appearance
 */
function updateStreamButton(streaming) {
    if (streamToggle) {
        if (streaming) {
            streamToggle.className = 'inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500';
            if (streamIcon) streamIcon.innerHTML = '&#9632;';  // Square (stop)
            if (streamText) streamText.textContent = 'Stop';
        } else {
            streamToggle.className = 'inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500';
            if (streamIcon) streamIcon.innerHTML = '&#9654;';  // Triangle (play)
            if (streamText) streamText.textContent = 'Stream';
        }
    }
}

/**
 * Append a log line to the container
 */
function appendLogLine(line, checkFilter = true) {
    if (!logContainer) return;

    // Remove placeholder if present
    const placeholder = logContainer.querySelector('.text-center');
    if (placeholder) {
        placeholder.remove();
    }

    const lineElement = document.createElement('div');
    lineElement.className = 'log-line py-0.5 hover:bg-gray-800';
    lineElement.textContent = line;

    // Apply color coding based on log level
    if (line.includes('ERROR') || line.includes('error') || line.includes('Error')) {
        lineElement.classList.add('text-red-400');
    } else if (line.includes('WARNING') || line.includes('warning') || line.includes('Warning')) {
        lineElement.classList.add('text-yellow-400');
    } else if (line.includes('INFO') || line.includes('info')) {
        lineElement.classList.add('text-blue-300');
    } else if (line.includes('DEBUG') || line.includes('debug')) {
        lineElement.classList.add('text-gray-500');
    } else {
        lineElement.classList.add('text-gray-300');
    }

    // Store original text for filtering
    lineElement.dataset.original = line;

    logContainer.appendChild(lineElement);
    lineCount++;

    // Apply current filter
    if (checkFilter) {
        const searchInput = document.getElementById('search-input');
        const levelFilter = document.getElementById('level-filter');
        const search = searchInput ? searchInput.value.toLowerCase() : '';
        const level = levelFilter ? levelFilter.value : '';

        if (level || search) {
            const matchesLevel = !level || line.toUpperCase().includes(level);
            const matchesSearch = !search || line.toLowerCase().includes(search);
            if (!matchesLevel || !matchesSearch) {
                lineElement.style.display = 'none';
            }
        }
    }

    // Limit lines in DOM
    while (logContainer.children.length > MAX_LINES) {
        logContainer.removeChild(logContainer.firstChild);
        lineCount--;
    }

    updateLineCount();

    // Auto-scroll
    if (autoScroll) {
        scrollToBottom();
    }
}

/**
 * Scroll log container to bottom
 */
function scrollToBottom() {
    if (logContainer) {
        logContainer.scrollTop = logContainer.scrollHeight;
    }
}

/**
 * Clear all log lines
 */
function clearLogs() {
    if (logContainer) {
        logContainer.innerHTML = '';
        lineCount = 0;
        updateLineCount();
    }
}

/**
 * Filter displayed log lines based on current search and level
 */
function filterDisplayedLogs() {
    const searchInput = document.getElementById('search-input');
    const levelFilter = document.getElementById('level-filter');
    const search = searchInput ? searchInput.value.toLowerCase() : '';
    const level = levelFilter ? levelFilter.value : '';

    const lines = logContainer.querySelectorAll('.log-line');
    let visibleCount = 0;

    lines.forEach(line => {
        const text = line.dataset.original || line.textContent;
        const matchesLevel = !level || text.toUpperCase().includes(level);
        const matchesSearch = !search || text.toLowerCase().includes(search);

        if (matchesLevel && matchesSearch) {
            line.style.display = '';
            visibleCount++;
        } else {
            line.style.display = 'none';
        }
    });

    // Update line count to show filtered count
    if (lineCountEl) {
        if (search || level) {
            lineCountEl.textContent = `${visibleCount} of ${lineCount} lines`;
        } else {
            lineCountEl.textContent = `${lineCount} lines`;
        }
    }
}

/**
 * Download logs as text file
 */
function downloadLogs() {
    const env = getSelectedEnv();
    const lines = getLineCount();
    window.location.href = `/api/logs/${env}/download?lines=${Math.max(lines, 1000)}`;
}

/**
 * Handle keyboard shortcuts
 */
function handleKeyboardShortcuts(event) {
    // Ignore if typing in an input
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'SELECT' || event.target.tagName === 'TEXTAREA') {
        return;
    }

    switch (event.key.toLowerCase()) {
        case 'r':
            event.preventDefault();
            loadLogs();
            break;
        case 's':
            event.preventDefault();
            toggleStream();
            break;
        case 'a':
            event.preventDefault();
            if (autoScrollCheckbox) {
                autoScrollCheckbox.checked = !autoScrollCheckbox.checked;
                autoScroll = autoScrollCheckbox.checked;
            }
            break;
        case 'c':
            event.preventDefault();
            clearLogs();
            break;
    }
}

/**
 * Clean up on page unload
 */
window.addEventListener('beforeunload', function() {
    if (eventSource) {
        eventSource.close();
    }
});

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', initElements);
