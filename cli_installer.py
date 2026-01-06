#!/usr/bin/env python3
"""
Odoo Multi-Environment Docker Installer - Interactive CLI Version
A beautiful, user-friendly command-line installer for setting up Odoo with Docker.

Features:
- Interactive CLI with questionary for user-friendly prompts
- Rich console output with progress bars and formatted text
- All features from the web version in a CLI interface
- No web server required
"""

import os
import sys
import subprocess
import logging
import secrets
import string
import re
import socket
from datetime import datetime
from pathlib import Path
import json
import time

# Auto-install dependencies if needed
def check_and_install_dependencies():
    """Check and install required packages."""
    required_packages = {
        'questionary': 'python3-questionary',
        'rich': 'python3-rich'
    }

    for package, apt_package in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            print(f"Installing {package}...")

            # Try pip first
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode == 0:
                print(f"✓ {package} installed via pip")
                continue

            # Pip failed - check if it's an externally managed environment error
            stderr_output = result.stderr or ""
            if "externally-managed-environment" in stderr_output or "externally managed" in stderr_output.lower():
                print(f"  Python environment is externally managed, trying apt...")

                # Try apt install
                apt_update = subprocess.run(
                    ["apt-get", "update", "-qq"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                apt_install = subprocess.run(
                    ["apt-get", "install", "-y", "-qq", apt_package],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True
                )

                if apt_install.returncode == 0:
                    print(f"✓ {package} installed via apt")
                    continue

                # APT failed - try pip with override
                print(f"  apt package {apt_package} not available, trying pip with override...")

                pip_override = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--break-system-packages", package],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                if pip_override.returncode == 0:
                    print(f"✓ {package} installed via pip (with override)")
                    continue

                # Everything failed
                print(f"✗ Failed to install {package}. Please install manually:")
                print(f"  sudo apt install {apt_package}")
                print(f"  OR: pip install --break-system-packages {package}")
                sys.exit(1)
            else:
                # Some other pip error
                print(f"✗ Failed to install {package} via pip: {stderr_output}")
                sys.exit(1)

check_and_install_dependencies()

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.prompt import Confirm, Prompt
from rich import box
from rich.markdown import Markdown
from rich.syntax import Syntax

# ============================================
# GLOBAL CONFIGURATION
# ============================================

APP_VERSION = "2.0.2-CLI"
LOG_FILE = "/var/log/odoo-installer.log"

# Custom style for questionary prompts
custom_style = Style([
    ('qmark', 'fg:#673ab7 bold'),       # Question mark
    ('question', 'bold'),                # Question text
    ('answer', 'fg:#f44336 bold'),      # User's answer
    ('pointer', 'fg:#673ab7 bold'),     # Pointer in select
    ('highlighted', 'fg:#673ab7 bold'), # Highlighted choice
    ('selected', 'fg:#cc5454'),         # Selected choice
    ('separator', 'fg:#cc5454'),        # Separator
    ('instruction', ''),                 # Instructions
    ('text', ''),                        # Plain text
    ('disabled', 'fg:#858585 italic')   # Disabled choice
])

console = Console()

# ============================================
# LOGGING SETUP
# ============================================

def setup_logging():
    """Initialize logging to file and console."""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'

    logger = logging.getLogger('odoo_installer')
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # Console handler with lower level
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(console_handler)

    # File handler (only if running as root)
    if os.geteuid() == 0:
        try:
            file_handler = logging.FileHandler(LOG_FILE)
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter(log_format))
            logger.addHandler(file_handler)
        except PermissionError:
            logger.warning(f"Cannot write to {LOG_FILE}, logging to console only")

    return logger

logger = setup_logging()

# ============================================
# HELPER FUNCTIONS
# ============================================

def check_root_permissions():
    """Verify the script is running as root."""
    if os.geteuid() != 0:
        console.print(Panel.fit(
            "[bold red]❌ ERROR: This installer must be run as root[/bold red]\n\n"
            "Please run with: [yellow]sudo python3 cli_installer.py[/yellow]",
            title="Permission Denied",
            border_style="red"
        ))
        sys.exit(1)
    logger.info("Root permission check: OK")

def safe_ask(question):
    """
    Safely ask a questionary question and handle Ctrl+C properly.
    Questionary returns None when Ctrl+C is pressed, so we convert it to KeyboardInterrupt.
    """
    result = question.ask()
    if result is None:
        raise KeyboardInterrupt
    return result

def safe_confirm(prompt, default=True):
    """
    Safely ask a rich Confirm question and handle Ctrl+C properly.
    Rich Confirm may also return None on Ctrl+C.
    """
    try:
        result = Confirm.ask(prompt, default=default)
        return result
    except (EOFError, KeyboardInterrupt):
        raise KeyboardInterrupt

def generate_secure_password(length=24):
    """Generate a cryptographically secure password."""
    charset = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(charset) for _ in range(length))
    return password

def validate_domain(domain):
    """Validate domain name format."""
    if not domain or len(domain) > 255:
        return False, "Domain name is required and must be less than 255 characters"

    pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    if not re.match(pattern, domain):
        return False, "Invalid domain format (e.g., example.com)"

    return True, "Valid domain"

def validate_port(port):
    """Validate port number."""
    try:
        port = int(port)
    except (ValueError, TypeError):
        return False

    return 1024 <= port <= 65535

def check_port_available(port):
    """Check if a port is available on the system."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', port))
            return result != 0
    except Exception as e:
        logger.warning(f"Error checking port {port}: {e}")
        return True

def validate_database_name(db_name):
    """Validate PostgreSQL database name."""
    if not db_name:
        return False, "Database name is required"

    if len(db_name) > 63:
        return False, "Database name must be 63 characters or less"

    pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*$'
    if not re.match(pattern, db_name):
        return False, "Database name must start with letter/underscore and contain only letters, numbers, underscores"

    return True, "Valid database name"

def validate_path(path):
    """Validate file system path."""
    if not path:
        return False, "Path is required"

    if not os.path.isabs(path):
        return False, "Path must be absolute (start with /)"

    if any(char in path for char in ['\0', '\n', '\r']):
        return False, "Path contains invalid characters"

    return True, "Valid path"

def run_command(command, description="", check=True):
    """Execute a shell command with logging."""
    logger.info(f"Running: {description or command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=check,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        if result.stdout:
            logger.debug(f"Output: {result.stdout.strip()}")
        if result.stderr:
            logger.warning(f"Stderr: {result.stderr.strip()}")
        return True, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {command}")
        return False, "", "Command timed out"
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {command}")
        logger.error(f"Error: {e.stderr}")
        return False, e.stdout or "", e.stderr or str(e)
    except Exception as e:
        logger.error(f"Unexpected error running command: {e}")
        return False, "", str(e)

def check_package_installed(package_name):
    """Check if a package is installed via dpkg."""
    success, stdout, _ = run_command(
        f"dpkg -l | grep -E '^ii.*{package_name}' || true",
        f"Checking if {package_name} is installed",
        check=False
    )
    return success and stdout.strip() != ""

# ============================================
# INSTALLATION FUNCTIONS
# ============================================

def install_docker():
    """Install Docker from official repository."""
    logger.info("Installing Docker...")

    if check_package_installed("docker-ce"):
        return True, "Docker is already installed"

    steps = [
        ("apt-get update -qq", "Updating package list"),
        ("apt-get install -y -qq ca-certificates curl gnupg", "Installing prerequisites"),
        ("install -m 0755 -d /etc/apt/keyrings", "Creating keyrings directory"),
        ("curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc || curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc", "Downloading Docker GPG key"),
        ("chmod a+r /etc/apt/keyrings/docker.asc", "Setting GPG key permissions"),
    ]

    for cmd, desc in steps:
        success, _, stderr = run_command(cmd, desc)
        if not success:
            return False, f"Failed: {desc} - {stderr}"

    # Add Docker repository
    repo_cmd = '''echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null || echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null'''

    success, _, stderr = run_command(repo_cmd, "Adding Docker repository")
    if not success:
        return False, f"Failed to add Docker repository: {stderr}"

    success, _, stderr = run_command("apt-get update -qq", "Updating package list")
    if not success:
        return False, f"Failed to update package list: {stderr}"

    success, _, stderr = run_command(
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
        "Installing Docker packages"
    )
    if not success:
        return False, f"Failed to install Docker: {stderr}"

    return True, "Docker installed successfully"

def install_postgresql():
    """Install PostgreSQL via apt."""
    logger.info("Installing PostgreSQL...")

    if check_package_installed("postgresql"):
        return True, "PostgreSQL is already installed"

    success, _, stderr = run_command("apt-get update -qq", "Updating package list")
    if not success:
        return False, f"Failed to update package list: {stderr}"

    success, _, stderr = run_command(
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql postgresql-contrib",
        "Installing PostgreSQL"
    )
    if not success:
        return False, f"Failed to install PostgreSQL: {stderr}"

    # Start PostgreSQL
    success, _, stderr = run_command("systemctl enable postgresql", "Enabling PostgreSQL")
    success, _, stderr = run_command("systemctl start postgresql", "Starting PostgreSQL")

    return True, "PostgreSQL installed successfully"

def install_nginx():
    """Install Nginx via apt."""
    logger.info("Installing Nginx...")

    if check_package_installed("nginx"):
        return True, "Nginx is already installed"

    success, _, stderr = run_command(
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx",
        "Installing Nginx"
    )
    if not success:
        return False, f"Failed to install Nginx: {stderr}"

    success, _, stderr = run_command("systemctl enable nginx", "Enabling Nginx")
    success, _, stderr = run_command("systemctl start nginx", "Starting Nginx")

    return True, "Nginx installed successfully"

def configure_postgresql(config):
    """Configure PostgreSQL for Docker network access."""
    logger.info("Configuring PostgreSQL...")

    # Find PostgreSQL config directory
    success, pg_config_dir, _ = run_command(
        "find /etc/postgresql -type d -name 'main' | head -1",
        "Finding PostgreSQL config directory",
        check=False
    )

    if not success or not pg_config_dir.strip():
        return False, "Could not find PostgreSQL configuration directory"

    pg_config_dir = pg_config_dir.strip()
    pg_hba_conf = f"{pg_config_dir}/pg_hba.conf"
    postgresql_conf = f"{pg_config_dir}/postgresql.conf"

    # Backup files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_command(f"cp {pg_hba_conf} {pg_hba_conf}.backup_{timestamp}", "Backing up pg_hba.conf")
    run_command(f"cp {postgresql_conf} {postgresql_conf}.backup_{timestamp}", "Backing up postgresql.conf")

    # Add Docker networks to pg_hba.conf
    # Use 172.16.0.0/12 to cover all Docker bridge networks (172.16.0.0 - 172.31.255.255)
    docker_hba_entry = "host    all    all    172.16.0.0/12    md5"
    success, _, _ = run_command(
        f"grep -q '172.16.0.0/12' {pg_hba_conf} || echo '{docker_hba_entry}' >> {pg_hba_conf}",
        "Adding Docker network range to pg_hba.conf"
    )

    # Set listen_addresses
    success, _, _ = run_command(
        f"sed -i \"s/#listen_addresses = 'localhost'/listen_addresses = '*'/g\" {postgresql_conf}",
        "Setting listen_addresses in postgresql.conf"
    )
    success, _, _ = run_command(
        f"sed -i \"s/listen_addresses = 'localhost'/listen_addresses = '*'/g\" {postgresql_conf}",
        "Setting listen_addresses in postgresql.conf"
    )

    # Restart PostgreSQL
    success, _, stderr = run_command("systemctl restart postgresql", "Restarting PostgreSQL")
    if not success:
        return False, f"Failed to restart PostgreSQL: {stderr}"

    return True, "PostgreSQL configured successfully"

def create_database_users(config):
    """Create database users for each environment."""
    logger.info("Creating database users...")

    for env, env_name in [('Test', 'test'), ('Staging', 'staging'), ('Prod', 'prod')]:
        db_user = config[f'dbUser{env}']
        db_pass = config[f'dbPass{env}']

        # Check if user exists
        check_cmd = f"sudo -u postgres psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='{db_user}'\" 2>/dev/null || true"
        success, stdout, _ = run_command(check_cmd, f"Checking if user {db_user} exists", check=False)

        if stdout.strip() == '1':
            logger.info(f"User {db_user} already exists, skipping creation")
        else:
            # Create user with CREATEDB privilege so Odoo can create databases
            create_cmd = f"sudo -u postgres psql -c \"CREATE USER {db_user} WITH LOGIN PASSWORD '{db_pass}' CREATEDB;\""
            success, _, stderr = run_command(create_cmd, f"Creating user {db_user}")
            if not success:
                return False, f"Failed to create user {db_user}: {stderr}"
            logger.info(f"Created user {db_user} with CREATEDB privilege")

    logger.info("PostgreSQL user creation completed")
    return True, "Database users created successfully. Databases will be created by Odoo on first access."

def create_directory_structure(config):
    """Create directory structure for Odoo."""
    logger.info("Creating directory structure...")

    base_path = config['basePath']

    for env in ['test', 'staging', 'prod']:
        dirs = [
            f"{base_path}/{env}/addons",
            f"{base_path}/{env}/filestore"
        ]

        for directory in dirs:
            Path(directory).mkdir(parents=True, exist_ok=True)
            # Set ownership to Odoo container user (UID 100, GID 101)
            run_command(f"chown -R 100:101 {directory}", f"Setting ownership for {directory}")

    return True, "Directory structure created successfully"

def generate_docker_compose(config):
    """Generate docker-compose.yml content."""
    odoo_version = config['odooVersion']
    base_path = config['basePath']

    services = {}

    for env, env_name in [('Test', 'test'), ('Staging', 'staging'), ('Prod', 'prod')]:
        db_user = config[f'dbUser{env}']
        db_pass = config[f'dbPass{env}']
        http_port = config[f'portHttp{env}']
        lp_port = config[f'portLp{env}']
        container_name = config[f'containerName{env}']

        services[container_name] = {
            'image': f'odoo:{odoo_version}',
            'container_name': container_name,
            'restart': 'unless-stopped',
            'ports': [
                f'{http_port}:8069',
                f'{lp_port}:8072'
            ],
            'environment': {
                'HOST': 'host.docker.internal',
                'USER': db_user,
                'PASSWORD': db_pass
            },
            'volumes': [
                f'{base_path}/{env_name}/addons:/mnt/extra-addons',
                f'{base_path}/{env_name}/filestore:/var/lib/odoo'
            ],
            'extra_hosts': [
                'host.docker.internal:host-gateway'
            ]
        }

    compose_content = {
        'version': '3.8',
        'services': services
    }

    # Convert to YAML-like format manually (to avoid pyyaml dependency)
    yaml_content = "version: '3.8'\n\nservices:\n"

    for service_name, service_config in services.items():
        yaml_content += f"  {service_name}:\n"
        yaml_content += f"    image: {service_config['image']}\n"
        yaml_content += f"    container_name: {service_config['container_name']}\n"
        yaml_content += f"    restart: {service_config['restart']}\n"
        yaml_content += "    ports:\n"
        for port in service_config['ports']:
            yaml_content += f"      - '{port}'\n"
        yaml_content += "    environment:\n"
        for key, value in service_config['environment'].items():
            yaml_content += f"      {key}: {value}\n"
        yaml_content += "    volumes:\n"
        for volume in service_config['volumes']:
            yaml_content += f"      - {volume}\n"
        yaml_content += "    extra_hosts:\n"
        for host in service_config['extra_hosts']:
            yaml_content += f"      - {host}\n"
        yaml_content += "\n"

    return yaml_content

def generate_nginx_config(config):
    """Generate Nginx configuration."""
    skip_ssl = config.get('skipSSL', False)

    nginx_conf = ""

    for env, env_name in [('Test', 'test'), ('Staging', 'staging'), ('Prod', 'prod')]:
        domain = config[f'domain{env}']
        http_port = config[f'portHttp{env}']
        lp_port = config[f'portLp{env}']

        if skip_ssl:
            # HTTP only
            nginx_conf += f"""
# {env} Environment - HTTP Only
server {{
    listen 80;
    server_name {domain};

    client_max_body_size 100M;

    location / {{
        proxy_pass http://127.0.0.1:{http_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }}

    location /longpolling {{
        proxy_pass http://127.0.0.1:{lp_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}

"""
        else:
            # HTTPS
            ssl_cert = config[f'sslCert{env}']
            ssl_key = config[f'sslKey{env}']

            nginx_conf += f"""
# {env} Environment - HTTPS
server {{
    listen 80;
    server_name {domain};
    return 301 https://$server_name$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {domain};

    ssl_certificate {ssl_cert};
    ssl_certificate_key {ssl_key};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 100M;

    location / {{
        proxy_pass http://127.0.0.1:{http_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;
    }}

    location /longpolling {{
        proxy_pass http://127.0.0.1:{lp_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }}
}}

"""

    return nginx_conf

def write_configuration_files(config):
    """Write docker-compose.yml and nginx config."""
    logger.info("Writing configuration files...")

    base_path = config['basePath']

    # Generate and write docker-compose.yml
    docker_compose = generate_docker_compose(config)
    docker_compose_path = f"{base_path}/docker-compose.yml"

    # Backup existing file if present
    if os.path.exists(docker_compose_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_command(f"cp {docker_compose_path} {docker_compose_path}.backup_{timestamp}", "Backing up docker-compose.yml")

    with open(docker_compose_path, 'w') as f:
        f.write(docker_compose)

    # Skip Nginx configuration if requested
    if config.get('skipNginx', False):
        logger.info("Skipping Nginx configuration (skipNginx=True)")
        return True, "Docker configuration written successfully (Nginx skipped)"

    # Generate and write nginx config
    nginx_conf = generate_nginx_config(config)
    nginx_conf_path = "/etc/nginx/sites-available/odoo"

    # Backup existing file if present
    if os.path.exists(nginx_conf_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_command(f"cp {nginx_conf_path} {nginx_conf_path}.backup_{timestamp}", "Backing up nginx config")

    with open(nginx_conf_path, 'w') as f:
        f.write(nginx_conf)

    # Create symlink
    symlink_path = "/etc/nginx/sites-enabled/odoo"
    if os.path.exists(symlink_path):
        os.remove(symlink_path)
    os.symlink(nginx_conf_path, symlink_path)

    # Test nginx config
    success, _, stderr = run_command("nginx -t", "Testing Nginx configuration")
    if not success:
        return False, f"Nginx configuration test failed: {stderr}"

    # Reload nginx
    success, _, stderr = run_command("systemctl reload nginx", "Reloading Nginx")
    if not success:
        return False, f"Failed to reload Nginx: {stderr}"

    return True, "Configuration files written successfully"

def start_docker_containers(config):
    """Start Docker containers."""
    logger.info("Starting Docker containers...")

    base_path = config['basePath']
    odoo_version = config['odooVersion']

    # Pull Odoo image
    success, _, stderr = run_command(
        f"docker pull odoo:{odoo_version}",
        f"Pulling Odoo {odoo_version} image"
    )
    if not success:
        return False, f"Failed to pull Odoo image: {stderr}"

    # Start containers
    success, _, stderr = run_command(
        f"cd {base_path} && docker compose up -d",
        "Starting Docker containers"
    )
    if not success:
        return False, f"Failed to start containers: {stderr}"

    # Wait a bit for containers to start
    time.sleep(3)

    # Verify containers are running
    success, stdout, _ = run_command(
        "docker ps --format '{{.Names}}'",
        "Checking container status",
        check=False
    )

    running_containers = stdout.strip().split('\n') if stdout.strip() else []
    expected_containers = [
        config['containerNameTest'],
        config['containerNameStaging'],
        config['containerNameProd']
    ]

    if not all(container in running_containers for container in expected_containers):
        return False, f"Not all containers started. Running: {running_containers}"

    return True, "All Docker containers started successfully"

def save_credentials(config):
    """Save installation credentials to a JSON file."""
    credentials = {
        'installation_date': datetime.now().isoformat(),
        'odoo_version': config['odooVersion'],
        'base_path': config['basePath'],
        'environments': {
            'test': {
                'container_name': config['containerNameTest'],
                'domain': config['domainTest'],
                'db_user': config['dbUserTest'],
                'db_password': config['dbPassTest'],
                'http_port': config['portHttpTest'],
                'longpolling_port': config['portLpTest']
            },
            'staging': {
                'container_name': config['containerNameStaging'],
                'domain': config['domainStaging'],
                'db_user': config['dbUserStaging'],
                'db_password': config['dbPassStaging'],
                'http_port': config['portHttpStaging'],
                'longpolling_port': config['portLpStaging']
            },
            'production': {
                'container_name': config['containerNameProd'],
                'domain': config['domainProd'],
                'db_user': config['dbUserProd'],
                'db_password': config['dbPassProd'],
                'http_port': config['portHttpProd'],
                'longpolling_port': config['portLpProd']
            }
        },
        'urls': {
            'test': f"http://localhost:{config['portHttpTest']}" if config.get('skipNginx') else f"{'https' if not config.get('skipSSL') else 'http'}://{config['domainTest']}",
            'staging': f"http://localhost:{config['portHttpStaging']}" if config.get('skipNginx') else f"{'https' if not config.get('skipSSL') else 'http'}://{config['domainStaging']}",
            'production': f"http://localhost:{config['portHttpProd']}" if config.get('skipNginx') else f"{'https' if not config.get('skipSSL') else 'http'}://{config['domainProd']}"
        },
        'nginx_installed': not config.get('skipNginx', False)
    }

    # Save to file
    creds_file = "/root/odoo-installation-credentials.json"
    with open(creds_file, 'w') as f:
        json.dump(credentials, f, indent=2)

    os.chmod(creds_file, 0o600)  # Only root can read

    return creds_file

# ============================================
# INTERACTIVE CLI FUNCTIONS
# ============================================

def show_welcome():
    """Display welcome screen."""
    console.clear()

    welcome_text = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║       ODOO MULTI-ENVIRONMENT DOCKER INSTALLER             ║
    ║                   Interactive CLI Version                 ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝

    This installer will set up Odoo across three isolated environments:
    • Test Environment
    • Staging Environment
    • Production Environment

    What will be installed:
    ✓ Docker & Docker Compose
    ✓ PostgreSQL Database
    ✓ Nginx Reverse Proxy (optional)
    ✓ Odoo (3 separate instances)

    Requirements:
    • Ubuntu 20.04+ or Debian 11+
    • Root access
    • Domain names for each environment
    • SSL certificates (optional)
    """

    console.print(Panel(welcome_text, border_style="cyan", box=box.DOUBLE))

    if not safe_confirm("\n[bold cyan]Ready to begin?[/bold cyan]", default=True):
        console.print("\n[yellow]Installation cancelled.[/yellow]")
        sys.exit(0)

def collect_odoo_version():
    """Ask for Odoo version."""
    console.print("\n[bold cyan]Step 1: Odoo Version[/bold cyan]")

    version = safe_ask(questionary.select(
        "Select the Odoo version to install:",
        choices=[
            '14.0',
            '15.0',
            '16.0',
            '17.0',
            '18.0',
            '19.0'
        ],
        style=custom_style,
        default='17.0'
    ))

    return version

def collect_database_config():
    """Collect database configuration."""
    console.print("\n[bold cyan]Step 2: Database Configuration[/bold cyan]")

    config = {}

    # Note: No PostgreSQL superuser password needed - we use 'sudo -u postgres' which works when running as root

    # For each environment
    for env, env_display in [('Test', 'Test'), ('Staging', 'Staging'), ('Prod', 'Production')]:
        console.print(f"\n[yellow]● {env_display} Environment[/yellow]")

        # Database user
        while True:
            default_user = f"odoo_{env.lower()}"
            db_user = safe_ask(questionary.text(
                f"  Database user:",
                default=default_user,
                style=custom_style
            ))

            valid, msg = validate_database_name(db_user)
            if valid:
                config[f'dbUser{env}'] = db_user
                break
            else:
                console.print(f"  [red]❌ {msg}[/red]")

        # Database password
        if safe_ask(questionary.confirm(
            f"  Generate secure password automatically?",
            default=True,
            style=custom_style
        )):
            db_password = generate_secure_password()
            console.print(f"  [green]✓ Generated password: {db_password}[/green]")
            config[f'dbPass{env}'] = db_password
        else:
            while True:
                db_password = safe_ask(questionary.password(
                    f"  Database password:",
                    style=custom_style
                ))
                if len(db_password) >= 8:
                    config[f'dbPass{env}'] = db_password
                    break
                else:
                    console.print("  [red]❌ Password must be at least 8 characters.[/red]")

    return config

def collect_domain_ssl_config():
    """Collect domain and SSL configuration."""
    console.print("\n[bold cyan]Step 3: Domain & SSL Configuration[/bold cyan]")

    config = {}

    # Ask if Nginx should be installed
    install_nginx = safe_ask(questionary.confirm(
        "Install and configure Nginx reverse proxy? (Choose 'No' for local development)",
        default=True,
        style=custom_style
    ))

    config['skipNginx'] = not install_nginx

    # If skipping Nginx, no need for domains or SSL
    if not install_nginx:
        console.print("[yellow]→ Skipping Nginx configuration. Access Odoo directly via ports.[/yellow]")
        config['skipSSL'] = True
        # Set placeholder domains (not used but needed for config structure)
        for env in ['Test', 'Staging', 'Prod']:
            config[f'domain{env}'] = f"{env.lower()}.local"
        return config

    # Ask if SSL should be configured
    skip_ssl = not safe_ask(questionary.confirm(
        "Configure SSL/HTTPS? (Choose 'No' for HTTP-only testing)",
        default=True,
        style=custom_style
    ))

    config['skipSSL'] = skip_ssl

    # For each environment
    for env, env_display in [('Test', 'Test'), ('Staging', 'Staging'), ('Prod', 'Production')]:
        console.print(f"\n[yellow]● {env_display} Environment[/yellow]")

        # Domain
        while True:
            default_domain = f"{env.lower()}.example.com" if env != 'Prod' else "odoo.example.com"
            domain = safe_ask(questionary.text(
                f"  Domain name:",
                default=default_domain,
                style=custom_style
            ))

            valid, msg = validate_domain(domain)
            if valid:
                config[f'domain{env}'] = domain
                break
            else:
                console.print(f"  [red]❌ {msg}[/red]")

        # SSL certificate paths
        if not skip_ssl:
            while True:
                default_cert = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
                ssl_cert = safe_ask(questionary.text(
                    f"  SSL certificate path:",
                    default=default_cert,
                    style=custom_style
                ))

                if os.path.exists(ssl_cert) and os.path.isfile(ssl_cert):
                    config[f'sslCert{env}'] = ssl_cert
                    break
                else:
                    console.print(f"  [red]❌ File does not exist: {ssl_cert}[/red]")

            while True:
                default_key = f"/etc/letsencrypt/live/{domain}/privkey.pem"
                ssl_key = safe_ask(questionary.text(
                    f"  SSL private key path:",
                    default=default_key,
                    style=custom_style
                ))

                if os.path.exists(ssl_key) and os.path.isfile(ssl_key):
                    config[f'sslKey{env}'] = ssl_key
                    break
                else:
                    console.print(f"  [red]❌ File does not exist: {ssl_key}[/red]")

    return config

def collect_directory_config():
    """Collect directory configuration."""
    console.print("\n[bold cyan]Step 4: Directory Configuration[/bold cyan]")

    while True:
        base_path = safe_ask(questionary.text(
            "Base directory for Odoo data:",
            default="/srv/odoo",
            style=custom_style
        ))

        valid, msg = validate_path(base_path)
        if valid:
            console.print(f"\n[dim]Directory structure that will be created:[/dim]")
            for env in ['test', 'staging', 'prod']:
                console.print(f"[dim]  • {base_path}/{env}/addons[/dim]")
                console.print(f"[dim]  • {base_path}/{env}/filestore[/dim]")

            if safe_confirm("\nContinue with this path?", default=True):
                return {'basePath': base_path}
        else:
            console.print(f"[red]❌ {msg}[/red]")

def collect_port_config():
    """Collect port configuration."""
    console.print("\n[bold cyan]Step 5: Port Configuration[/bold cyan]")

    config = {}
    used_ports = []

    defaults = {
        'Test': {'http': 8071, 'lp': 8074},
        'Staging': {'http': 8070, 'lp': 8073},
        'Prod': {'http': 8069, 'lp': 8072}
    }

    for env, env_display in [('Test', 'Test'), ('Staging', 'Staging'), ('Prod', 'Production')]:
        console.print(f"\n[yellow]● {env_display} Environment[/yellow]")

        # HTTP port
        while True:
            http_port = safe_ask(questionary.text(
                f"  HTTP port:",
                default=str(defaults[env]['http']),
                style=custom_style
            ))

            if validate_port(http_port) and int(http_port) not in used_ports:
                if check_port_available(int(http_port)):
                    config[f'portHttp{env}'] = int(http_port)
                    used_ports.append(int(http_port))
                    break
                else:
                    console.print(f"  [red]❌ Port {http_port} is already in use.[/red]")
            else:
                console.print(f"  [red]❌ Invalid port or already used in configuration.[/red]")

        # Long-polling port
        while True:
            lp_port = safe_ask(questionary.text(
                f"  Long-polling port:",
                default=str(defaults[env]['lp']),
                style=custom_style
            ))

            if validate_port(lp_port) and int(lp_port) not in used_ports:
                if check_port_available(int(lp_port)):
                    config[f'portLp{env}'] = int(lp_port)
                    used_ports.append(int(lp_port))
                    break
                else:
                    console.print(f"  [red]❌ Port {lp_port} is already in use.[/red]")
            else:
                console.print(f"  [red]❌ Invalid port or already used in configuration.[/red]")

    return config

def collect_container_names():
    """Collect container names for each environment."""
    console.print("\n[bold cyan]Step 6: Container Names[/bold cyan]")
    console.print("[dim]Customize the Docker container names for each environment.[/dim]\n")

    config = {}

    defaults = {
        'Test': 'odoo-test',
        'Staging': 'odoo-staging',
        'Prod': 'odoo-prod'
    }

    for env, env_display in [('Test', 'Test'), ('Staging', 'Staging'), ('Prod', 'Production')]:
        console.print(f"[yellow]● {env_display} Environment[/yellow]")

        while True:
            container_name = safe_ask(questionary.text(
                f"  Container name:",
                default=defaults[env],
                style=custom_style
            ))

            # Validate container name (Docker naming rules)
            # Container names must match: [a-zA-Z0-9][a-zA-Z0-9_.-]*
            if not container_name:
                console.print("  [red]❌ Container name cannot be empty.[/red]")
                continue

            if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$', container_name):
                console.print("  [red]❌ Invalid container name. Must start with letter/number and contain only letters, numbers, underscores, dots, and hyphens.[/red]")
                continue

            # Check for uniqueness
            existing_names = [config.get(f'containerName{e}') for e in ['Test', 'Staging', 'Prod'] if f'containerName{e}' in config]
            if container_name in existing_names:
                console.print("  [red]❌ Container name already used for another environment.[/red]")
                continue

            config[f'containerName{env}'] = container_name
            break

    return config

def review_configuration(config):
    """Display configuration summary for review."""
    console.print("\n[bold cyan]Step 7: Review Configuration[/bold cyan]")

    # Create summary table
    table = Table(title="Installation Configuration Summary", box=box.ROUNDED, show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    table.add_row("Odoo Version", config['odooVersion'])
    table.add_row("Base Path", config['basePath'])
    table.add_row("Nginx Installation", "No (Direct port access)" if config.get('skipNginx') else "Yes")
    table.add_row("SSL Enabled", "No (HTTP only)" if config.get('skipSSL') else "Yes (HTTPS)")
    table.add_row("", "")

    for env, env_display in [('Test', 'Test'), ('Staging', 'Staging'), ('Prod', 'Production')]:
        table.add_row(f"[bold]{env_display} Environment[/bold]", "")
        table.add_row(f"  Container Name", config[f'containerName{env}'])
        if not config.get('skipNginx'):
            table.add_row(f"  Domain", config[f'domain{env}'])
        table.add_row(f"  DB User", config[f'dbUser{env}'])
        table.add_row(f"  HTTP Port", str(config[f'portHttp{env}']))
        table.add_row(f"  Long-polling Port", str(config[f'portLp{env}']))
        if not config.get('skipSSL') and not config.get('skipNginx'):
            table.add_row(f"  SSL Certificate", config[f'sslCert{env}'])
        table.add_row("", "")

    console.print(table)

    return safe_ask(questionary.confirm(
        "\nProceed with installation?",
        default=True,
        style=custom_style
    ))

def run_installation(config):
    """Execute the full installation with progress tracking."""
    console.print("\n[bold green]Starting Installation...[/bold green]\n")

    steps = [
        ("Installing Docker", install_docker),
        ("Installing PostgreSQL", install_postgresql),
    ]

    # Add Nginx installation only if not skipped
    if not config.get('skipNginx', False):
        steps.append(("Installing Nginx", install_nginx))

    steps.extend([
        ("Configuring PostgreSQL", lambda: configure_postgresql(config)),
        ("Creating database users", lambda: create_database_users(config)),
        ("Creating directory structure", lambda: create_directory_structure(config)),
        ("Writing configuration files", lambda: write_configuration_files(config)),
        ("Starting Docker containers", lambda: start_docker_containers(config)),
    ])

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:

        overall_task = progress.add_task("[cyan]Overall Progress", total=len(steps))

        for step_name, step_func in steps:
            current_task = progress.add_task(f"[yellow]{step_name}...", total=1)

            success, message = step_func()

            if not success:
                progress.update(current_task, completed=1, description=f"[red]✗ {step_name} - FAILED")
                console.print(f"\n[bold red]Installation failed at: {step_name}[/bold red]")
                console.print(f"[red]Error: {message}[/red]")
                console.print(f"\n[yellow]Check logs at: {LOG_FILE}[/yellow]")
                return False

            progress.update(current_task, completed=1, description=f"[green]✓ {step_name}")
            progress.update(overall_task, advance=1)

    console.print("\n[bold green]✓ Installation completed successfully![/bold green]")
    return True

def show_completion_summary(config):
    """Display installation completion summary."""
    console.print("\n" + "="*70)
    console.print("[bold green]INSTALLATION COMPLETE![/bold green]")
    console.print("="*70 + "\n")

    # Save credentials
    creds_file = save_credentials(config)

    # Display access information
    table = Table(title="Your Odoo Environments", box=box.DOUBLE, show_header=True, header_style="bold cyan")
    table.add_column("Environment", style="cyan", no_wrap=True)
    table.add_column("URL", style="green")

    skip_nginx = config.get('skipNginx', False)

    if skip_nginx:
        # Show direct port access
        for env, env_display in [('Test', 'Test'), ('Staging', 'Staging'), ('Prod', 'Production')]:
            url = f"http://localhost:{config[f'portHttp{env}']}"
            table.add_row(env_display, url)
    else:
        # Show domain access
        protocol = "http" if config.get('skipSSL') else "https"
        for env, env_display in [('Test', 'Test'), ('Staging', 'Staging'), ('Prod', 'Production')]:
            url = f"{protocol}://{config[f'domain{env}']}"
            table.add_row(env_display, url)

    console.print(table)

    console.print(f"\n[bold cyan]Important Information:[/bold cyan]")
    console.print(f"  • Credentials saved to: [yellow]{creds_file}[/yellow]")
    console.print(f"  • Docker Compose file: [yellow]{config['basePath']}/docker-compose.yml[/yellow]")
    if not skip_nginx:
        console.print(f"  • Nginx config: [yellow]/etc/nginx/sites-available/odoo[/yellow]")
    console.print(f"  • Installation logs: [yellow]{LOG_FILE}[/yellow]")

    console.print(f"\n[bold cyan]Next Steps:[/bold cyan]")
    if skip_nginx:
        console.print("  1. Navigate to your Odoo URL via direct port access:")
        console.print(f"     • Test: [yellow]http://localhost:{config['portHttpTest']}[/yellow]")
        console.print(f"     • Staging: [yellow]http://localhost:{config['portHttpStaging']}[/yellow]")
        console.print(f"     • Production: [yellow]http://localhost:{config['portHttpProd']}[/yellow]")
    else:
        console.print("  1. Navigate to your Odoo URL (e.g., https://odoo.example.com)")
    console.print("  2. Create your first database through the Odoo web interface:")
    console.print("     • Set a master password (for database management)")
    console.print("     • Choose a database name (any valid name you prefer)")
    console.print("     • Fill in admin email and password")
    console.print("     • Odoo will create and initialize the database automatically")

    console.print(f"\n[bold cyan]Container Management:[/bold cyan]")
    console.print(f"  • View logs: [yellow]docker logs {config['containerNameProd']}[/yellow]")
    console.print(f"  • Restart: [yellow]cd {config['basePath']} && docker compose restart[/yellow]")
    console.print(f"  • Stop: [yellow]cd {config['basePath']} && docker compose stop[/yellow]")

    console.print("\n" + "="*70 + "\n")

# ============================================
# MAIN PROGRAM
# ============================================

def main():
    """Main program entry point."""
    try:
        # Check root permissions
        check_root_permissions()

        # Show welcome screen
        show_welcome()

        # Collect configuration
        config = {}

        # Step 1: Odoo version
        config['odooVersion'] = collect_odoo_version()

        # Step 2: Database configuration
        config.update(collect_database_config())

        # Step 3: Domain and SSL
        config.update(collect_domain_ssl_config())

        # Step 4: Directory structure
        config.update(collect_directory_config())

        # Step 5: Port configuration
        config.update(collect_port_config())

        # Step 6: Container names
        config.update(collect_container_names())

        # Step 7: Review and confirm
        if not review_configuration(config):
            console.print("\n[yellow]Installation cancelled by user.[/yellow]")
            return

        # Run installation
        success = run_installation(config)

        if success:
            show_completion_summary(config)
        else:
            console.print("\n[bold red]Installation failed. Please check the logs and try again.[/bold red]")
            sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Installation cancelled by user.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error: {e}[/bold red]")
        logger.exception("Unexpected error during installation")
        sys.exit(1)

if __name__ == "__main__":
    main()
