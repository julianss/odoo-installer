"""
Log service for Odoo Management Dashboard
Handles log retrieval and streaming for Docker containers
"""
import subprocess
import sys
import os
import signal

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_container_name


def get_logs(env, lines=100, timestamps=False):
    """
    Get last N lines of container logs.

    Args:
        env: Environment name (test, staging, prod)
        lines: Number of lines to retrieve
        timestamps: Whether to include timestamps

    Returns:
        dict with 'success', 'logs' list, and 'error' if failed
    """
    container_name = get_container_name(env)

    cmd = ['docker', 'logs', '--tail', str(lines), container_name]
    if timestamps:
        cmd.insert(2, '--timestamps')

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return {
            'success': False,
            'error': result.stderr or 'Failed to retrieve logs',
            'logs': []
        }

    # Docker logs go to stderr for Odoo, combine both
    combined_output = result.stdout + result.stderr
    log_lines = combined_output.strip().split('\n') if combined_output.strip() else []

    return {
        'success': True,
        'logs': log_lines
    }


def stream_logs(env, tail=50):
    """
    Generator for SSE log streaming.

    Yields log lines in SSE format for real-time streaming.

    Args:
        env: Environment name (test, staging, prod)
        tail: Number of initial lines to show

    Yields:
        SSE formatted log lines
    """
    container_name = get_container_name(env)

    proc = subprocess.Popen(
        ['docker', 'logs', '-f', '--tail', str(tail), container_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1  # Line buffered
    )

    try:
        for line in iter(proc.stdout.readline, ''):
            if line:
                # Escape special characters for SSE
                # Replace newlines within the line (shouldn't happen, but just in case)
                safe_line = line.rstrip('\n').replace('\n', '\\n')
                yield f"data: {safe_line}\n\n"
    except GeneratorExit:
        # Client disconnected
        pass
    finally:
        # Clean up the subprocess
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def get_logs_download(env, lines=1000, timestamps=True):
    """
    Get logs formatted for download.

    Args:
        env: Environment name
        lines: Number of lines (default 1000 for downloads)
        timestamps: Include timestamps (default True for downloads)

    Returns:
        String of log content ready for download
    """
    container_name = get_container_name(env)

    cmd = ['docker', 'logs', '--tail', str(lines), container_name]
    if timestamps:
        cmd.insert(2, '--timestamps')

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    # Combine stdout and stderr (Odoo logs go to stderr)
    content = result.stdout + result.stderr

    return content


def get_log_stats(env):
    """
    Get statistics about container logs.

    Returns:
        dict with log size and line count estimates
    """
    container_name = get_container_name(env)

    # Get a rough line count by checking last 10000 lines
    result = subprocess.run(
        ['docker', 'logs', '--tail', '10000', container_name],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return {
            'available': False,
            'error': 'Could not retrieve log stats'
        }

    combined = result.stdout + result.stderr
    line_count = len(combined.strip().split('\n')) if combined.strip() else 0

    return {
        'available': True,
        'line_count': line_count,
        'truncated': line_count >= 10000
    }


def filter_logs(logs, level=None, search=None):
    """
    Filter log lines by level or search term.

    Args:
        logs: List of log lines
        level: Log level to filter (ERROR, WARNING, INFO, DEBUG)
        search: Search string to filter

    Returns:
        Filtered list of log lines
    """
    filtered = logs

    if level:
        level_upper = level.upper()
        filtered = [line for line in filtered if level_upper in line.upper()]

    if search:
        search_lower = search.lower()
        filtered = [line for line in filtered if search_lower in line.lower()]

    return filtered
