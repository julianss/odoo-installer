"""
Configuration management for Odoo Dashboard
"""
import json
import os

# Base paths
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(DASHBOARD_DIR, 'data')

# Configuration file paths
GIT_REPOS_FILE = os.path.join(DATA_DIR, 'git-repos.json')
BACKUP_CONFIG_FILE = os.path.join(DATA_DIR, 'backup-config.json')

# Application settings
APP_PORT = int(os.environ.get('DASHBOARD_PORT', 9998))
APP_VERSION = '1.0.0-DASHBOARD'

# Odoo environment paths
def _detect_odoo_base_dir():
    """Auto-detect Odoo installation directory."""
    # Check environment variable first
    if os.environ.get('ODOO_BASE_DIR'):
        return os.environ.get('ODOO_BASE_DIR')

    # Check common locations
    common_paths = [
        '/srv/odoo',
        '/home/odoo19',
        '/home/odoo',
        '/opt/odoo',
        os.path.expanduser('~/odoo'),
    ]

    for path in common_paths:
        docker_compose = os.path.join(path, 'docker-compose.yml')
        if os.path.exists(docker_compose):
            return path

    # Default fallback
    return '/srv/odoo'

ODOO_BASE_DIR = _detect_odoo_base_dir()
DOCKER_COMPOSE_FILE = os.path.join(ODOO_BASE_DIR, 'docker-compose.yml')
BACKUP_DIR = os.path.join(ODOO_BASE_DIR, 'backups')

# Default environment names (used as fallback)
DEFAULT_ENVIRONMENTS = ['test', 'staging', 'prod']


def parse_docker_compose():
    """
    Parse docker-compose.yml to discover containers and their environments.

    Returns:
        dict: Mapping of environment name to container info, e.g.:
              {'test': {'container_name': 'odoo-test', 'service_name': 'odoo-test'},
               'staging': {'container_name': 'odoo-staging', 'service_name': 'odoo-staging'},
               'prod': {'container_name': 'odoo-prod', 'service_name': 'odoo-prod'}}
    """
    import re

    if not os.path.exists(DOCKER_COMPOSE_FILE):
        # Return defaults if file doesn't exist
        return {env: {'container_name': f'odoo-{env}', 'service_name': f'odoo-{env}'}
                for env in DEFAULT_ENVIRONMENTS}

    try:
        with open(DOCKER_COMPOSE_FILE, 'r') as f:
            content = f.read()
    except IOError:
        return {env: {'container_name': f'odoo-{env}', 'service_name': f'odoo-{env}'}
                for env in DEFAULT_ENVIRONMENTS}

    # Simple YAML parsing (avoid pyyaml dependency)
    # Find all services and their container_name and volumes
    containers = {}

    # Split into service blocks
    # Services section starts after "services:" line
    services_match = re.search(r'^services:\s*$', content, re.MULTILINE)
    if not services_match:
        return {env: {'container_name': f'odoo-{env}', 'service_name': f'odoo-{env}'}
                for env in DEFAULT_ENVIRONMENTS}

    services_content = content[services_match.end():]

    # Find each service block (2-space indented service name)
    service_pattern = re.compile(r'^  ([a-zA-Z0-9_-]+):\s*$', re.MULTILINE)
    service_matches = list(service_pattern.finditer(services_content))

    for i, match in enumerate(service_matches):
        service_name = match.group(1)

        # Get the content of this service block (until next service or end)
        start = match.end()
        end = service_matches[i + 1].start() if i + 1 < len(service_matches) else len(services_content)
        service_block = services_content[start:end]

        # Extract container_name
        container_match = re.search(r'container_name:\s*([^\s\n]+)', service_block)
        container_name = container_match.group(1) if container_match else service_name

        # Determine environment from volumes path (e.g., /srv/odoo/test/addons)
        volume_match = re.search(r'/([^/]+)/addons:/mnt/extra-addons', service_block)
        if volume_match:
            env = volume_match.group(1)
            containers[env] = {
                'container_name': container_name,
                'service_name': service_name
            }

    # If no containers found, return defaults
    if not containers:
        return {env: {'container_name': f'odoo-{env}', 'service_name': f'odoo-{env}'}
                for env in DEFAULT_ENVIRONMENTS}

    return containers


def get_environments():
    """Get list of environment names from docker-compose.yml."""
    containers = parse_docker_compose()
    return list(containers.keys())


def get_container_name(env):
    """Get container name for a given environment."""
    containers = parse_docker_compose()
    if env in containers:
        return containers[env]['container_name']
    # Fallback to default naming
    return f'odoo-{env}'


def get_service_name(env):
    """Get docker-compose service name for a given environment."""
    containers = parse_docker_compose()
    if env in containers:
        return containers[env]['service_name']
    # Fallback to default naming
    return f'odoo-{env}'


def get_service_config(env):
    """
    Get full service configuration from docker-compose.yml for an environment.

    Returns dict with service_name, container_name, and environment variables.
    """
    import re

    containers = parse_docker_compose()
    if env not in containers:
        return None

    service_name = containers[env]['service_name']

    # Re-parse to get environment variables
    if not os.path.exists(DOCKER_COMPOSE_FILE):
        return {'service_name': service_name, 'container_name': containers[env]['container_name'], 'environment': {}}

    try:
        with open(DOCKER_COMPOSE_FILE, 'r') as f:
            content = f.read()
    except IOError:
        return {'service_name': service_name, 'container_name': containers[env]['container_name'], 'environment': {}}

    # Find the service block
    services_match = re.search(r'^services:\s*$', content, re.MULTILINE)
    if not services_match:
        return {'service_name': service_name, 'container_name': containers[env]['container_name'], 'environment': {}}

    services_content = content[services_match.end():]

    # Find this specific service
    service_pattern = re.compile(rf'^  {re.escape(service_name)}:\s*$', re.MULTILINE)
    service_match = service_pattern.search(services_content)

    if not service_match:
        return {'service_name': service_name, 'container_name': containers[env]['container_name'], 'environment': {}}

    # Find the end of this service block (next service at same indentation or end)
    start = service_match.end()
    next_service = re.search(r'^  [a-zA-Z0-9_-]+:\s*$', services_content[start:], re.MULTILINE)
    end = start + next_service.start() if next_service else len(services_content)
    service_block = services_content[start:end]

    # Extract environment variables
    environment = {}

    # Look for environment section - handles both formats:
    # Format 1 (list): - KEY=value
    # Format 2 (dict): KEY: value
    env_section_match = re.search(r'environment:\s*\n((?:\s+.+\n?)+?)(?=\n    \w|\n  \w|$)', service_block)
    if env_section_match:
        env_lines = env_section_match.group(1)
        for line in env_lines.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            # Format 1: - KEY=value
            match = re.match(r'-\s*(\w+)=(.+)', line)
            if match:
                environment[match.group(1)] = match.group(2).strip()
                continue
            # Format 2: KEY: value (YAML dict style)
            match = re.match(r'(\w+):\s*(.+)', line)
            if match:
                environment[match.group(1)] = match.group(2).strip()

    return {
        'service_name': service_name,
        'container_name': containers[env]['container_name'],
        'environment': environment
    }


# Dynamic environments (parsed from docker-compose.yml)
ENVIRONMENTS = get_environments()


def ensure_data_dir():
    """Ensure data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def load_json_file(file_path, default=None):
    """Load JSON configuration file."""
    if not os.path.exists(file_path):
        return default if default is not None else {}

    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading {file_path}: {e}")
        return default if default is not None else {}


def save_json_file(file_path, data):
    """Save JSON configuration file."""
    ensure_data_dir()

    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except IOError as e:
        print(f"Error saving {file_path}: {e}")
        return False


def load_git_repos():
    """Load git repository registry."""
    default = {env: [] for env in ENVIRONMENTS}
    return load_json_file(GIT_REPOS_FILE, default)


def save_git_repos(repos):
    """Save git repository registry."""
    return save_json_file(GIT_REPOS_FILE, repos)


def load_backup_config():
    """Load backup configuration."""
    default = {
        'storage_backend': 'local',
        's3': {
            'endpoint': '',
            'access_key': '',
            'secret_key': '',
            'bucket': '',
            'region': 'us-east-1'
        },
        'rsync': {
            'host': '',
            'username': '',
            'remote_path': '',
            'ssh_key_path': ''
        },
        'schedules': {},
        'retention': {
            'local_days': 7,
            'remote_days': 30
        }
    }
    return load_json_file(BACKUP_CONFIG_FILE, default)


def save_backup_config(config):
    """Save backup configuration."""
    return save_json_file(BACKUP_CONFIG_FILE, config)
