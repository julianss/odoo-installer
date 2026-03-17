"""
Docker container operations for Odoo Management Dashboard
"""
import subprocess
import json
from datetime import datetime
import sys
import os

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_container_name, get_environments


def get_container_status(env):
    """Get status of Odoo container."""
    container_name = get_container_name(env)

    # Check if container exists and is running
    result = subprocess.run(
        ['docker', 'inspect', container_name],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return {'status': 'not_found', 'env': env}

    try:
        data = json.loads(result.stdout)[0]
    except (json.JSONDecodeError, IndexError):
        return {'status': 'error', 'env': env, 'error': 'Failed to parse container info'}

    state = data.get('State', {})

    return {
        'env': env,
        'status': 'running' if state.get('Running') else 'stopped',
        'uptime': state.get('StartedAt'),
        'exit_code': state.get('ExitCode', 0),
        'container_id': data.get('Id', '')[:12],
        'health': state.get('Health', {}).get('Status', 'unknown') if state.get('Health') else 'none'
    }


def get_all_container_status():
    """Get status of all Odoo containers."""
    environments = get_environments()
    statuses = {}

    for env in environments:
        status = get_container_status(env)
        # Also get stats if running
        if status['status'] == 'running':
            stats = get_container_stats(env)
            if stats:
                status['stats'] = stats
        statuses[env] = status

    return statuses


def start_container(env):
    """Start Odoo container."""
    container_name = get_container_name(env)
    result = subprocess.run(
        ['docker', 'start', container_name],
        capture_output=True,
        text=True
    )

    return {
        'success': result.returncode == 0,
        'message': result.stdout if result.returncode == 0 else result.stderr
    }


def stop_container(env):
    """Stop Odoo container."""
    container_name = get_container_name(env)
    result = subprocess.run(
        ['docker', 'stop', container_name],
        capture_output=True,
        text=True
    )

    return {
        'success': result.returncode == 0,
        'message': result.stdout if result.returncode == 0 else result.stderr
    }


def restart_container(env):
    """Restart Odoo container."""
    container_name = get_container_name(env)
    result = subprocess.run(
        ['docker', 'restart', container_name],
        capture_output=True,
        text=True
    )

    return {
        'success': result.returncode == 0,
        'message': result.stdout if result.returncode == 0 else result.stderr
    }


def get_container_stats(env):
    """Get container resource usage."""
    container_name = get_container_name(env)

    result = subprocess.run(
        ['docker', 'stats', '--no-stream', '--format', '{{json .}}', container_name],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return None

    try:
        stats = json.loads(result.stdout)
        return {
            'cpu': stats.get('CPUPerc', 'N/A'),
            'memory': stats.get('MemUsage', 'N/A'),
            'memory_percent': stats.get('MemPerc', 'N/A'),
            'net_io': stats.get('NetIO', 'N/A'),
            'block_io': stats.get('BlockIO', 'N/A')
        }
    except (json.JSONDecodeError, KeyError):
        return None


def get_container_logs(env, lines=100):
    """Get container logs."""
    container_name = get_container_name(env)

    result = subprocess.run(
        ['docker', 'logs', '--tail', str(lines), container_name],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return {'success': False, 'error': result.stderr}

    return {
        'success': True,
        'logs': result.stdout.split('\n') if result.stdout else []
    }
