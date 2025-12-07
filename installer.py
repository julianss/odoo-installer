#!/usr/bin/env python3
"""
Odoo Multi-Environment Docker Installer with Web GUI
A Flask-based web installer for setting up Odoo with Docker across three environments.

Security: Runs as root, protected by HTTP Basic Auth, auto-shuts down after 60 min inactivity.
"""

import os
import sys
import subprocess
import logging
import secrets
import string
import re
import socket
from datetime import datetime, timedelta
from functools import wraps
from threading import Thread, Lock
import time

# Check if Flask is installed, if not, install it
try:
    from flask import Flask, request, session, jsonify, Response
    from werkzeug.security import check_password_hash, generate_password_hash
except ImportError:
    print("Flask not found. Installing Flask...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
    from flask import Flask, request, session, jsonify, Response
    from werkzeug.security import check_password_hash, generate_password_hash

# ============================================
# GLOBAL CONFIGURATION
# ============================================

APP_VERSION = "1.0.0"
APP_PORT = int(os.getenv("APP_PORT", "9999"))
LOG_FILE = "/var/log/odoo-installer.log"
INACTIVITY_TIMEOUT = 60 * 60  # 60 minutes in seconds

# In-memory storage for Basic Auth credentials
auth_credentials = {
    'username': None,
    'password_hash': None,
    'initialized': False
}

# Activity tracking for auto-shutdown
last_activity = {
    'timestamp': datetime.now(),
    'lock': Lock()
}

# Installation progress tracking
installation_state = {
    'running': False,
    'dry_run': False,
    'current_step': '',
    'progress': 0,
    'logs': [],
    'success': False,
    'error': None,
    'lock': Lock()
}

# ============================================
# LOGGING SETUP
# ============================================

def setup_logging():
    """Initialize logging to file and console."""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'

    # Create logger
    logger = logging.getLogger('odoo_installer')
    logger.setLevel(logging.INFO)

    # Clear any existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
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
# ROOT PERMISSION CHECK
# ============================================

def check_root_permissions():
    """Verify the script is running as root."""
    if os.geteuid() != 0:
        logger.error("This installer must be run as root (UID 0)")
        print("\n❌ ERROR: This installer must be run as root")
        print("Please run with: sudo python3 installer.py")
        sys.exit(1)
    logger.info("Root permission check: OK")

# ============================================
# ACTIVITY TRACKING
# ============================================

def update_activity():
    """Update the last activity timestamp."""
    with last_activity['lock']:
        last_activity['timestamp'] = datetime.now()

def get_inactivity_duration():
    """Get seconds since last activity."""
    with last_activity['lock']:
        return (datetime.now() - last_activity['timestamp']).total_seconds()

def activity_monitor():
    """Background thread to monitor inactivity and shutdown if needed."""
    while True:
        time.sleep(60)  # Check every minute
        inactive_seconds = get_inactivity_duration()

        if inactive_seconds >= INACTIVITY_TIMEOUT:
            logger.warning(f"Inactivity timeout reached ({inactive_seconds:.0f}s). Shutting down installer.")
            print(f"\n⚠️  Installer shutting down due to {INACTIVITY_TIMEOUT/60:.0f} minutes of inactivity")
            os._exit(0)

        remaining = INACTIVITY_TIMEOUT - inactive_seconds
        if remaining < 600:  # Less than 10 minutes remaining
            logger.info(f"Auto-shutdown in {remaining/60:.1f} minutes due to inactivity")

# ============================================
# FLASK APP INITIALIZATION
# ============================================

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Secure random secret key
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# ============================================
# AUTHENTICATION SETUP
# ============================================

def prompt_for_credentials():
    """Prompt for admin credentials on first run (interactive mode)."""
    if auth_credentials['initialized']:
        return

    print("\n" + "="*60)
    print("  ODOO INSTALLER - INITIAL SETUP")
    print("="*60)
    print("\nSet up credentials for the web installer:")
    print("(These will be stored in memory only)")
    print()

    while True:
        username = input("Admin username: ").strip()
        if len(username) >= 3:
            break
        print("❌ Username must be at least 3 characters")

    while True:
        password = input("Admin password: ").strip()
        if len(password) >= 8:
            password_confirm = input("Confirm password: ").strip()
            if password == password_confirm:
                break
            print("❌ Passwords do not match")
        else:
            print("❌ Password must be at least 8 characters")

    auth_credentials['username'] = username
    auth_credentials['password_hash'] = generate_password_hash(password)
    auth_credentials['initialized'] = True

    logger.info(f"Credentials set for user: {username}")
    print("\n✅ Credentials saved to memory")

def check_auth(username, password):
    """Validate username and password."""
    if not auth_credentials['initialized']:
        return False

    return (username == auth_credentials['username'] and
            check_password_hash(auth_credentials['password_hash'], password))

def authenticate():
    """Send 401 response that enables Basic Auth."""
    return Response(
        'Authentication required. Please log in with your credentials.',
        401,
        {'WWW-Authenticate': 'Basic realm="Odoo Installer"'}
    )

def requires_auth(f):
    """Decorator to require HTTP Basic Authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            logger.warning(f"Failed authentication attempt from {request.remote_addr}")
            return authenticate()

        # Update activity on successful auth
        update_activity()
        return f(*args, **kwargs)
    return decorated

# ============================================
# CONFIGURATION VALIDATION FUNCTIONS
# ============================================

def generate_secure_password(length=24):
    """Generate a cryptographically secure password."""
    charset = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(charset) for _ in range(length))
    return password

def validate_domain(domain):
    """Validate domain name format."""
    if not domain or len(domain) > 255:
        return False, "Domain name is required and must be less than 255 characters"

    # Basic domain regex pattern
    pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    if not re.match(pattern, domain):
        return False, "Invalid domain format (e.g., example.com)"

    return True, "Valid domain"

def validate_port(port, port_list=None):
    """Validate port number and check if it's in valid range."""
    try:
        port = int(port)
    except (ValueError, TypeError):
        return False, "Port must be a valid number"

    if port < 1024 or port > 65535:
        return False, "Port must be between 1024 and 65535"

    if port_list and port in port_list:
        return False, f"Port {port} is already used in configuration"

    return True, "Valid port"

def check_port_available(port):
    """Check if a port is available on the system."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', port))
            if result == 0:
                return False, f"Port {port} is already in use"
            return True, f"Port {port} is available"
    except Exception as e:
        logger.warning(f"Error checking port {port}: {e}")
        return True, f"Port {port} status unknown (assuming available)"

def validate_ssl_file(file_path):
    """Validate that an SSL certificate/key file exists and is readable."""
    if not file_path:
        return False, "SSL file path is required"

    if not os.path.exists(file_path):
        return False, f"File does not exist: {file_path}"

    if not os.path.isfile(file_path):
        return False, f"Path is not a file: {file_path}"

    if not os.access(file_path, os.R_OK):
        return False, f"File is not readable: {file_path}"

    return True, f"File exists and is readable: {file_path}"

def validate_database_name(db_name):
    """Validate PostgreSQL database name."""
    if not db_name:
        return False, "Database name is required"

    if len(db_name) > 63:
        return False, "Database name must be 63 characters or less"

    # PostgreSQL database name rules
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

    # Check if path contains invalid characters
    if any(char in path for char in ['\0', '\n', '\r']):
        return False, "Path contains invalid characters"

    return True, "Valid path"

def validate_configuration(config):
    """Validate the entire configuration object."""
    errors = []

    # Validate Odoo version
    valid_versions = ['14.0', '15.0', '16.0', '17.0', '18.0', '19.0']
    if config.get('odooVersion') not in valid_versions:
        errors.append("Invalid Odoo version selected")

    # Validate database configuration
    if not config.get('pgPassword'):
        errors.append("PostgreSQL superuser password is required")

    # Validate database names
    for env in ['Test', 'Staging', 'Prod']:
        db_name = config.get(f'dbName{env}')
        valid, msg = validate_database_name(db_name)
        if not valid:
            errors.append(f"{env} database: {msg}")

    # Validate database users
    for env in ['Test', 'Staging', 'Prod']:
        db_user = config.get(f'dbUser{env}')
        valid, msg = validate_database_name(db_user)  # Same rules as db name
        if not valid:
            errors.append(f"{env} user: {msg}")

    # Validate database passwords
    for env in ['Test', 'Staging', 'Prod']:
        db_pass = config.get(f'dbPass{env}')
        if not db_pass or len(db_pass) < 8:
            errors.append(f"{env} database password must be at least 8 characters")

    # Validate domains
    for env in ['Test', 'Staging', 'Prod']:
        domain = config.get(f'domain{env}')
        valid, msg = validate_domain(domain)
        if not valid:
            errors.append(f"{env} domain: {msg}")

    # Validate SSL files if SSL is not skipped
    skip_ssl = config.get('skipSSL', False)
    if not skip_ssl:
        for env in ['Test', 'Staging', 'Prod']:
            cert_path = config.get(f'sslCert{env}')
            key_path = config.get(f'sslKey{env}')

            if cert_path:
                valid, msg = validate_ssl_file(cert_path)
                if not valid:
                    errors.append(f"{env} SSL cert: {msg}")
            else:
                errors.append(f"{env} SSL certificate path is required")

            if key_path:
                valid, msg = validate_ssl_file(key_path)
                if not valid:
                    errors.append(f"{env} SSL key: {msg}")
            else:
                errors.append(f"{env} SSL key path is required")

    # Validate base path
    base_path = config.get('basePath')
    valid, msg = validate_path(base_path)
    if not valid:
        errors.append(f"Base path: {msg}")

    # Validate ports
    all_ports = []
    for env in ['Test', 'Staging', 'Prod']:
        http_port = config.get(f'portHttp{env}')
        lp_port = config.get(f'portLp{env}')

        valid, msg = validate_port(http_port, all_ports)
        if not valid:
            errors.append(f"{env} HTTP port: {msg}")
        else:
            all_ports.append(int(http_port))

        valid, msg = validate_port(lp_port, all_ports)
        if not valid:
            errors.append(f"{env} long-polling port: {msg}")
        else:
            all_ports.append(int(lp_port))

    return len(errors) == 0, errors

# ============================================
# INSTALLATION ENGINE FUNCTIONS
# ============================================

def run_command(command, description="", check=True, capture_output=True):
    """Execute a shell command with logging and error handling."""
    logger.info(f"Running: {description or command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=check,
            capture_output=capture_output,
            text=True,
            timeout=300  # 5 minute timeout
        )
        if result.stdout:
            logger.debug(f"Output: {result.stdout.strip()}")
        if result.stderr:
            logger.warning(f"Stderr: {result.stderr.strip()}")
        return True, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {command}")
        return False, "", "Command timed out after 5 minutes"
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

def install_docker():
    """Install Docker from official repository."""
    logger.info("Installing Docker...")

    # Check if already installed
    if check_package_installed("docker-ce"):
        logger.info("Docker is already installed")
        return True, "Docker already installed"

    steps = [
        ("apt-get update", "Updating package list"),
        ("apt-get install -y ca-certificates curl gnupg", "Installing prerequisites"),
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

    # Install Docker
    success, _, stderr = run_command("apt-get update", "Updating package list")
    if not success:
        return False, f"Failed to update package list: {stderr}"

    success, _, stderr = run_command(
        "apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
        "Installing Docker packages"
    )
    if not success:
        return False, f"Failed to install Docker: {stderr}"

    logger.info("Docker installed successfully")
    return True, "Docker installed successfully"

def install_postgresql():
    """Install PostgreSQL via apt."""
    logger.info("Installing PostgreSQL...")

    if check_package_installed("postgresql"):
        logger.info("PostgreSQL is already installed")
        return True, "PostgreSQL already installed"

    success, _, stderr = run_command("apt-get update", "Updating package list")
    if not success:
        return False, f"Failed to update package list: {stderr}"

    success, _, stderr = run_command(
        "apt-get install -y postgresql postgresql-contrib",
        "Installing PostgreSQL"
    )
    if not success:
        return False, f"Failed to install PostgreSQL: {stderr}"

    logger.info("PostgreSQL installed successfully")
    return True, "PostgreSQL installed successfully"

def install_nginx():
    """Install Nginx via apt."""
    logger.info("Installing Nginx...")

    if check_package_installed("nginx"):
        logger.info("Nginx is already installed")
        return True, "Nginx already installed"

    success, _, stderr = run_command("apt-get update", "Updating package list")
    if not success:
        return False, f"Failed to update package list: {stderr}"

    success, _, stderr = run_command("apt-get install -y nginx", "Installing Nginx")
    if not success:
        return False, f"Failed to install Nginx: {stderr}"

    logger.info("Nginx installed successfully")
    return True, "Nginx installed successfully"

def configure_postgresql(config):
    """Configure PostgreSQL for Docker network access."""
    logger.info("Configuring PostgreSQL...")

    # Find PostgreSQL version and config directory
    success, stdout, _ = run_command(
        "ls -d /etc/postgresql/*/main 2>/dev/null | head -1",
        "Finding PostgreSQL config directory",
        check=False
    )

    if not success or not stdout.strip():
        return False, "Could not find PostgreSQL configuration directory"

    pg_config_dir = stdout.strip()
    pg_hba_conf = f"{pg_config_dir}/pg_hba.conf"
    postgresql_conf = f"{pg_config_dir}/postgresql.conf"

    # Backup pg_hba.conf
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{pg_hba_conf}.backup_{timestamp}"

    success, _, stderr = run_command(f"cp {pg_hba_conf} {backup_file}", f"Backing up pg_hba.conf to {backup_file}")
    if not success:
        logger.warning(f"Failed to backup pg_hba.conf: {stderr}")

    # Add Docker network rules to pg_hba.conf (if not already present)
    docker_rules = [
        "# Allow Docker containers to connect",
        "host    all    all    172.17.0.0/16    md5",
        "host    all    all    172.18.0.0/16    md5",
        "host    all    all    172.19.0.0/16    md5",
    ]

    try:
        with open(pg_hba_conf, 'r') as f:
            current_content = f.read()

        # Check if rules already exist
        if "172.17.0.0/16" not in current_content:
            with open(pg_hba_conf, 'a') as f:
                f.write("\n" + "\n".join(docker_rules) + "\n")
            logger.info("Added Docker network rules to pg_hba.conf")
        else:
            logger.info("Docker network rules already present in pg_hba.conf")
    except Exception as e:
        return False, f"Failed to modify pg_hba.conf: {e}"

    # Backup postgresql.conf
    backup_file = f"{postgresql_conf}.backup_{timestamp}"
    success, _, stderr = run_command(f"cp {postgresql_conf} {backup_file}", f"Backing up postgresql.conf")
    if not success:
        logger.warning(f"Failed to backup postgresql.conf: {stderr}")

    # Set listen_addresses to '*'
    try:
        with open(postgresql_conf, 'r') as f:
            lines = f.readlines()

        modified = False
        new_lines = []
        for line in lines:
            if line.strip().startswith("listen_addresses"):
                if "*" not in line:
                    new_lines.append("listen_addresses = '*'\n")
                    modified = True
                    continue
            elif line.strip().startswith("#listen_addresses"):
                new_lines.append("listen_addresses = '*'\n")
                modified = True
                continue
            new_lines.append(line)

        if modified:
            with open(postgresql_conf, 'w') as f:
                f.writelines(new_lines)
            logger.info("Set listen_addresses = '*' in postgresql.conf")
        else:
            logger.info("listen_addresses already configured correctly")
    except Exception as e:
        return False, f"Failed to modify postgresql.conf: {e}"

    # Restart PostgreSQL
    success, _, stderr = run_command("systemctl restart postgresql", "Restarting PostgreSQL")
    if not success:
        return False, f"Failed to restart PostgreSQL: {stderr}"

    logger.info("PostgreSQL configured successfully")
    return True, "PostgreSQL configured successfully"

def create_databases_and_users(config):
    """Create PostgreSQL databases and users for all environments."""
    logger.info("Creating PostgreSQL databases and users...")

    pg_password = config.get('pgPassword')

    environments = ['Test', 'Staging', 'Prod']

    for env in environments:
        db_name = config.get(f'dbName{env}')
        db_user = config.get(f'dbUser{env}')
        db_pass = config.get(f'dbPass{env}')

        # Check if user already exists
        check_user_cmd = f"PGPASSWORD='{pg_password}' psql -U postgres -tAc \"SELECT 1 FROM pg_roles WHERE rolname='{db_user}'\" 2>/dev/null || true"
        success, stdout, _ = run_command(check_user_cmd, f"Checking if user {db_user} exists", check=False)

        if stdout.strip() == "1":
            logger.info(f"User {db_user} already exists, skipping creation")
        else:
            # Create user
            create_user_cmd = f"PGPASSWORD='{pg_password}' psql -U postgres -c \"CREATE USER {db_user} WITH LOGIN PASSWORD '{db_pass}';\""
            success, _, stderr = run_command(create_user_cmd, f"Creating user {db_user}")
            if not success:
                return False, f"Failed to create user {db_user}: {stderr}"
            logger.info(f"Created user {db_user}")

        # Check if database already exists
        check_db_cmd = f"PGPASSWORD='{pg_password}' psql -U postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='{db_name}'\" 2>/dev/null || true"
        success, stdout, _ = run_command(check_db_cmd, f"Checking if database {db_name} exists", check=False)

        if stdout.strip() == "1":
            logger.info(f"Database {db_name} already exists, skipping creation")
        else:
            # Create database
            create_db_cmd = f"PGPASSWORD='{pg_password}' psql -U postgres -c \"CREATE DATABASE {db_name} OWNER {db_user};\""
            success, _, stderr = run_command(create_db_cmd, f"Creating database {db_name}")
            if not success:
                return False, f"Failed to create database {db_name}: {stderr}"
            logger.info(f"Created database {db_name}")

        # Grant privileges
        grant_cmd = f"PGPASSWORD='{pg_password}' psql -U postgres -c \"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};\""
        success, _, stderr = run_command(grant_cmd, f"Granting privileges on {db_name} to {db_user}")
        if not success:
            logger.warning(f"Failed to grant privileges: {stderr}")

    logger.info("Database and user creation completed")
    return True, "Databases and users created successfully"

def create_directory_structure(config):
    """Create directory structure with proper ownership for Odoo."""
    logger.info("Creating directory structure...")

    base_path = config.get('basePath', '/srv/odoo')
    environments = ['test', 'staging', 'prod']

    directories = []
    for env in environments:
        directories.append(f"{base_path}/{env}/addons")
        directories.append(f"{base_path}/{env}/filestore")

    for directory in directories:
        try:
            os.makedirs(directory, mode=0o755, exist_ok=True)
            logger.info(f"Created directory: {directory}")

            # Set ownership to UID 101, GID 101 (Odoo container user)
            os.chown(directory, 101, 101)
            logger.info(f"Set ownership to 101:101 for {directory}")
        except Exception as e:
            return False, f"Failed to create directory {directory}: {e}"

    logger.info("Directory structure created successfully")
    return True, "Directory structure created successfully"

def pull_docker_image(config):
    """Pull the Odoo Docker image."""
    logger.info("Pulling Odoo Docker image...")

    odoo_version = config.get('odooVersion', '17.0')
    image = f"odoo:{odoo_version}"

    success, _, stderr = run_command(
        f"docker pull {image}",
        f"Pulling Docker image {image}",
        capture_output=False  # Show progress in real-time
    )

    if not success:
        return False, f"Failed to pull Docker image: {stderr}"

    logger.info(f"Successfully pulled {image}")
    return True, f"Successfully pulled {image}"

def enable_and_start_services():
    """Enable and start Docker, PostgreSQL, and Nginx services."""
    logger.info("Enabling and starting services...")

    services = ['docker', 'postgresql', 'nginx']

    for service in services:
        # Enable service
        success, _, stderr = run_command(f"systemctl enable {service}", f"Enabling {service}")
        if not success:
            logger.warning(f"Failed to enable {service}: {stderr}")

        # Start service
        success, _, stderr = run_command(f"systemctl start {service}", f"Starting {service}")
        if not success:
            return False, f"Failed to start {service}: {stderr}"

        # Check status
        success, _, _ = run_command(f"systemctl is-active {service}", f"Checking {service} status", check=False)
        if success:
            logger.info(f"{service} is running")
        else:
            logger.warning(f"{service} may not be running properly")

    logger.info("All services enabled and started")
    return True, "All services enabled and started"

# ============================================
# CONFIGURATION FILE GENERATORS
# ============================================

def generate_docker_compose(config):
    """Generate docker-compose.yml content."""
    base_path = config.get('basePath', '/srv/odoo')
    odoo_version = config.get('odooVersion', '17.0')

    # Get credentials for each environment
    db_pass_test = config.get('dbPassTest', '')
    db_pass_staging = config.get('dbPassStaging', '')
    db_pass_prod = config.get('dbPassProd', '')

    db_user_test = config.get('dbUserTest', 'odoo_test')
    db_user_staging = config.get('dbUserStaging', 'odoo_staging')
    db_user_prod = config.get('dbUserProd', 'odoo_prod')

    # Get ports
    port_http_test = config.get('portHttpTest', '8069')
    port_http_staging = config.get('portHttpStaging', '8070')
    port_http_prod = config.get('portHttpProd', '8071')

    port_lp_test = config.get('portLpTest', '8072')
    port_lp_staging = config.get('portLpStaging', '8073')
    port_lp_prod = config.get('portLpProd', '8074')

    docker_compose = f"""version: '3.8'

services:
  odoo-test:
    image: odoo:{odoo_version}
    container_name: odoo-test
    restart: unless-stopped
    ports:
      - "{port_http_test}:8069"
      - "{port_lp_test}:8072"
    volumes:
      - {base_path}/test/addons:/mnt/extra-addons
      - {base_path}/test/filestore:/var/lib/odoo/filestore
    environment:
      - HOST=host.docker.internal
      - PORT=5432
      - USER={db_user_test}
      - PASSWORD={db_pass_test}
    extra_hosts:
      - "host.docker.internal:host-gateway"

  odoo-staging:
    image: odoo:{odoo_version}
    container_name: odoo-staging
    restart: unless-stopped
    ports:
      - "{port_http_staging}:8069"
      - "{port_lp_staging}:8072"
    volumes:
      - {base_path}/staging/addons:/mnt/extra-addons
      - {base_path}/staging/filestore:/var/lib/odoo/filestore
    environment:
      - HOST=host.docker.internal
      - PORT=5432
      - USER={db_user_staging}
      - PASSWORD={db_pass_staging}
    extra_hosts:
      - "host.docker.internal:host-gateway"

  odoo-prod:
    image: odoo:{odoo_version}
    container_name: odoo-prod
    restart: unless-stopped
    ports:
      - "{port_http_prod}:8069"
      - "{port_lp_prod}:8072"
    volumes:
      - {base_path}/prod/addons:/mnt/extra-addons
      - {base_path}/prod/filestore:/var/lib/odoo/filestore
    environment:
      - HOST=host.docker.internal
      - PORT=5432
      - USER={db_user_prod}
      - PASSWORD={db_pass_prod}
    extra_hosts:
      - "host.docker.internal:host-gateway"
"""
    return docker_compose

def generate_nginx_config(config):
    """Generate nginx configuration for all environments."""
    skip_ssl = config.get('skipSSL', False)

    # Get domains
    domain_test = config.get('domainTest', 'test.example.com')
    domain_staging = config.get('domainStaging', 'staging.example.com')
    domain_prod = config.get('domainProd', 'odoo.example.com')

    # Get SSL paths
    ssl_cert_test = config.get('sslCertTest', '')
    ssl_key_test = config.get('sslKeyTest', '')
    ssl_cert_staging = config.get('sslCertStaging', '')
    ssl_key_staging = config.get('sslKeyStaging', '')
    ssl_cert_prod = config.get('sslCertProd', '')
    ssl_key_prod = config.get('sslKeyProd', '')

    # Get ports
    port_http_test = config.get('portHttpTest', '8069')
    port_http_staging = config.get('portHttpStaging', '8070')
    port_http_prod = config.get('portHttpProd', '8071')

    port_lp_test = config.get('portLpTest', '8072')
    port_lp_staging = config.get('portLpStaging', '8073')
    port_lp_prod = config.get('portLpProd', '8074')

    # Start building config
    nginx_conf = """# Odoo Multi-Environment Nginx Configuration
# Generated by Odoo Installer

# Upstream definitions
upstream odoo-test {
    server 127.0.0.1:""" + port_http_test + """;
}
upstream odoo-test-chat {
    server 127.0.0.1:""" + port_lp_test + """;
}

upstream odoo-staging {
    server 127.0.0.1:""" + port_http_staging + """;
}
upstream odoo-staging-chat {
    server 127.0.0.1:""" + port_lp_staging + """;
}

upstream odoo-prod {
    server 127.0.0.1:""" + port_http_prod + """;
}
upstream odoo-prod-chat {
    server 127.0.0.1:""" + port_lp_prod + """;
}

# Map for WebSocket upgrade
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

"""

    # Generate configuration for each environment
    for env_name, domain, ssl_cert, ssl_key, upstream, upstream_chat in [
        ('TEST', domain_test, ssl_cert_test, ssl_key_test, 'odoo-test', 'odoo-test-chat'),
        ('STAGING', domain_staging, ssl_cert_staging, ssl_key_staging, 'odoo-staging', 'odoo-staging-chat'),
        ('PRODUCTION', domain_prod, ssl_cert_prod, ssl_key_prod, 'odoo-prod', 'odoo-prod-chat'),
    ]:
        nginx_conf += f"""# ============================================
# {env_name} ENVIRONMENT
# ============================================

"""
        if skip_ssl:
            # HTTP only configuration
            nginx_conf += f"""server {{
    listen 80;
    server_name {domain};

    # Proxy settings
    proxy_read_timeout 720s;
    proxy_connect_timeout 720s;
    proxy_send_timeout 720s;

    # Proxy headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;

    # Increase buffer size for large requests
    proxy_buffers 16 64k;
    proxy_buffer_size 128k;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # Main application
    location / {{
        proxy_pass http://{upstream};
        proxy_redirect off;
    }}

    # Long polling / WebSocket
    location /websocket {{
        proxy_pass http://{upstream_chat};
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }}

    # For older Odoo versions that use /longpolling
    location /longpolling {{
        proxy_pass http://{upstream_chat};
    }}

    # Static files caching
    location ~* /web/static/ {{
        proxy_pass http://{upstream};
        proxy_cache_valid 200 90m;
        proxy_buffering on;
        expires 864000;
    }}
}}

"""
        else:
            # HTTPS configuration with redirect
            nginx_conf += f"""# Redirect HTTP to HTTPS
server {{
    listen 80;
    server_name {domain};
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {domain};

    # SSL Configuration
    ssl_certificate {ssl_cert};
    ssl_certificate_key {ssl_key};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # Proxy settings
    proxy_read_timeout 720s;
    proxy_connect_timeout 720s;
    proxy_send_timeout 720s;

    # Proxy headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;

    # Increase buffer size for large requests
    proxy_buffers 16 64k;
    proxy_buffer_size 128k;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # Main application
    location / {{
        proxy_pass http://{upstream};
        proxy_redirect off;
    }}

    # Long polling / WebSocket
    location /websocket {{
        proxy_pass http://{upstream_chat};
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }}

    # For older Odoo versions that use /longpolling
    location /longpolling {{
        proxy_pass http://{upstream_chat};
    }}

    # Static files caching
    location ~* /web/static/ {{
        proxy_pass http://{upstream};
        proxy_cache_valid 200 90m;
        proxy_buffering on;
        expires 864000;
    }}
}}

"""

    return nginx_conf

def write_docker_compose(config):
    """Write docker-compose.yml file."""
    base_path = config.get('basePath', '/srv/odoo')
    compose_file = f"{base_path}/docker-compose.yml"

    # Generate content
    content = generate_docker_compose(config)

    # Create backup if file exists
    if os.path.exists(compose_file):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{compose_file}.backup_{timestamp}"
        try:
            run_command(f"cp {compose_file} {backup_file}", f"Backing up docker-compose.yml")
            logger.info(f"Backed up existing docker-compose.yml to {backup_file}")
        except Exception as e:
            logger.warning(f"Failed to backup docker-compose.yml: {e}")

    # Write new file
    try:
        with open(compose_file, 'w') as f:
            f.write(content)
        os.chmod(compose_file, 0o644)
        logger.info(f"Written docker-compose.yml to {compose_file}")
        return True, f"docker-compose.yml written to {compose_file}"
    except Exception as e:
        logger.error(f"Failed to write docker-compose.yml: {e}")
        return False, f"Failed to write docker-compose.yml: {e}"

def write_nginx_config(config):
    """Write nginx configuration file."""
    nginx_file = "/etc/nginx/sites-available/odoo"
    nginx_enabled = "/etc/nginx/sites-enabled/odoo"

    # Generate content
    content = generate_nginx_config(config)

    # Create backup if file exists
    if os.path.exists(nginx_file):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{nginx_file}.backup_{timestamp}"
        try:
            run_command(f"cp {nginx_file} {backup_file}", f"Backing up nginx config")
            logger.info(f"Backed up existing nginx config to {backup_file}")
        except Exception as e:
            logger.warning(f"Failed to backup nginx config: {e}")

    # Write new file
    try:
        with open(nginx_file, 'w') as f:
            f.write(content)
        os.chmod(nginx_file, 0o644)
        logger.info(f"Written nginx config to {nginx_file}")
    except Exception as e:
        logger.error(f"Failed to write nginx config: {e}")
        return False, f"Failed to write nginx config: {e}"

    # Create symlink to sites-enabled
    if not os.path.exists(nginx_enabled):
        try:
            os.symlink(nginx_file, nginx_enabled)
            logger.info(f"Created symlink {nginx_enabled}")
        except Exception as e:
            logger.warning(f"Failed to create symlink: {e}")

    # Remove default site if exists
    default_site = "/etc/nginx/sites-enabled/default"
    if os.path.exists(default_site):
        try:
            os.remove(default_site)
            logger.info("Removed default nginx site")
        except Exception as e:
            logger.warning(f"Failed to remove default site: {e}")

    # Test nginx configuration
    success, _, stderr = run_command("nginx -t", "Testing nginx configuration")
    if not success:
        logger.error(f"Nginx configuration test failed: {stderr}")
        return False, f"Nginx configuration test failed: {stderr}"

    # Reload nginx
    success, _, stderr = run_command("systemctl reload nginx", "Reloading nginx")
    if not success:
        logger.error(f"Failed to reload nginx: {stderr}")
        return False, f"Failed to reload nginx: {stderr}"

    logger.info("Nginx configuration written and reloaded successfully")
    return True, "Nginx configuration written and reloaded successfully"

def start_docker_containers(config):
    """Start Docker containers using docker-compose."""
    base_path = config.get('basePath', '/srv/odoo')
    compose_file = f"{base_path}/docker-compose.yml"

    if not os.path.exists(compose_file):
        return False, f"docker-compose.yml not found at {compose_file}"

    # Start containers
    success, _, stderr = run_command(
        f"cd {base_path} && docker compose up -d",
        "Starting Docker containers",
        capture_output=False
    )

    if not success:
        return False, f"Failed to start Docker containers: {stderr}"

    logger.info("Docker containers started successfully")
    return True, "Docker containers started successfully"

# ============================================
# INSTALLATION ORCHESTRATOR
# ============================================

def add_install_log(message):
    """Add a log message to the installation state."""
    with installation_state['lock']:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        installation_state['logs'].append(log_entry)
        logger.info(message)

def update_install_progress(step, progress):
    """Update the current installation step and progress."""
    with installation_state['lock']:
        installation_state['current_step'] = step
        installation_state['progress'] = progress

def run_installation(config, dry_run=False):
    """Main installation orchestrator."""
    with installation_state['lock']:
        if installation_state['running']:
            return False, "Installation is already running"

        installation_state['running'] = True
        installation_state['dry_run'] = dry_run
        installation_state['logs'] = []
        installation_state['success'] = False
        installation_state['error'] = None
        installation_state['current_step'] = 'Starting...'
        installation_state['progress'] = 0

    try:
        if dry_run:
            add_install_log("=== DRY RUN MODE - No changes will be made ===")
            return run_dry_run_installation(config)
        else:
            return run_full_installation(config)
    except Exception as e:
        logger.error(f"Installation failed with exception: {e}")
        with installation_state['lock']:
            installation_state['error'] = str(e)
            installation_state['running'] = False
        add_install_log(f"ERROR: {e}")
        return False, str(e)

def run_dry_run_installation(config):
    """Simulate installation without making changes."""
    add_install_log("Starting dry-run installation simulation")

    # Step 1: Check prerequisites
    update_install_progress("Checking prerequisites", 10)
    add_install_log("Would check if running as root")
    add_install_log("Would check for Docker installation")
    add_install_log("Would check for PostgreSQL installation")
    add_install_log("Would check for Nginx installation")

    # Step 2: PostgreSQL configuration
    update_install_progress("Checking PostgreSQL configuration", 20)
    add_install_log("Would configure pg_hba.conf for Docker networks")
    add_install_log("Would set listen_addresses = '*' in postgresql.conf")
    add_install_log("Would restart PostgreSQL service")

    # Step 3: Database setup
    update_install_progress("Checking database setup", 35)
    for env in ['test', 'staging', 'prod']:
        add_install_log(f"Would create database user for {env}")
        add_install_log(f"Would create database for {env}")
        add_install_log(f"Would grant privileges for {env}")

    # Step 4: Directory structure
    update_install_progress("Checking directory structure", 50)
    base_path = config.get('basePath', '/srv/odoo')
    for env in ['test', 'staging', 'prod']:
        add_install_log(f"Would create directory: {base_path}/{env}/addons")
        add_install_log(f"Would create directory: {base_path}/{env}/filestore")
        add_install_log(f"Would set ownership to 101:101")

    # Step 5: Docker setup
    update_install_progress("Checking Docker setup", 65)
    odoo_version = config.get('odooVersion', '17.0')
    add_install_log(f"Would pull Docker image: odoo:{odoo_version}")

    # Step 6: Configuration files
    update_install_progress("Generating configuration files", 75)
    docker_compose = generate_docker_compose(config)
    nginx_conf = generate_nginx_config(config)
    add_install_log(f"Generated docker-compose.yml ({len(docker_compose)} bytes)")
    add_install_log(f"Generated nginx.conf ({len(nginx_conf)} bytes)")
    add_install_log(f"Would write to {base_path}/docker-compose.yml")
    add_install_log("Would write to /etc/nginx/sites-available/odoo")

    # Step 7: Start services
    update_install_progress("Checking services", 90)
    add_install_log("Would enable and start Docker service")
    add_install_log("Would enable and start PostgreSQL service")
    add_install_log("Would enable and start Nginx service")
    add_install_log("Would start Docker containers")

    # Complete
    update_install_progress("Dry-run complete", 100)
    add_install_log("=== DRY RUN COMPLETE - No changes were made ===")
    add_install_log("Review the logs above to see what would be done")
    add_install_log("Uncheck 'Dry-run mode' and run again to perform actual installation")

    with installation_state['lock']:
        installation_state['success'] = True
        installation_state['running'] = False

    return True, "Dry-run completed successfully"

def run_full_installation(config):
    """Execute full installation."""
    add_install_log("=== STARTING FULL INSTALLATION ===")

    # Step 1: Install prerequisites
    update_install_progress("Installing prerequisites", 5)
    add_install_log("Installing Docker...")
    success, message = install_docker()
    add_install_log(message)
    if not success:
        raise Exception(f"Docker installation failed: {message}")

    update_install_progress("Installing PostgreSQL", 10)
    add_install_log("Installing PostgreSQL...")
    success, message = install_postgresql()
    add_install_log(message)
    if not success:
        raise Exception(f"PostgreSQL installation failed: {message}")

    update_install_progress("Installing Nginx", 15)
    add_install_log("Installing Nginx...")
    success, message = install_nginx()
    add_install_log(message)
    if not success:
        raise Exception(f"Nginx installation failed: {message}")

    # Step 2: Enable and start services
    update_install_progress("Starting services", 20)
    add_install_log("Enabling and starting services...")
    success, message = enable_and_start_services()
    add_install_log(message)
    if not success:
        raise Exception(f"Service startup failed: {message}")

    # Step 3: Configure PostgreSQL
    update_install_progress("Configuring PostgreSQL", 30)
    add_install_log("Configuring PostgreSQL for Docker access...")
    success, message = configure_postgresql(config)
    add_install_log(message)
    if not success:
        raise Exception(f"PostgreSQL configuration failed: {message}")

    # Step 4: Create databases and users
    update_install_progress("Creating databases and users", 45)
    add_install_log("Creating PostgreSQL databases and users...")
    success, message = create_databases_and_users(config)
    add_install_log(message)
    if not success:
        raise Exception(f"Database creation failed: {message}")

    # Step 5: Create directory structure
    update_install_progress("Creating directory structure", 55)
    add_install_log("Creating Odoo directory structure...")
    success, message = create_directory_structure(config)
    add_install_log(message)
    if not success:
        raise Exception(f"Directory creation failed: {message}")

    # Step 6: Pull Docker image
    update_install_progress("Pulling Docker image", 65)
    add_install_log("Pulling Odoo Docker image...")
    success, message = pull_docker_image(config)
    add_install_log(message)
    if not success:
        raise Exception(f"Docker image pull failed: {message}")

    # Step 7: Write docker-compose.yml
    update_install_progress("Writing docker-compose.yml", 75)
    add_install_log("Writing docker-compose.yml...")
    success, message = write_docker_compose(config)
    add_install_log(message)
    if not success:
        raise Exception(f"docker-compose.yml creation failed: {message}")

    # Step 8: Write nginx configuration
    update_install_progress("Configuring Nginx", 85)
    add_install_log("Writing Nginx configuration...")
    success, message = write_nginx_config(config)
    add_install_log(message)
    if not success:
        raise Exception(f"Nginx configuration failed: {message}")

    # Step 9: Start Docker containers
    update_install_progress("Starting Odoo containers", 95)
    add_install_log("Starting Odoo Docker containers...")
    success, message = start_docker_containers(config)
    add_install_log(message)
    if not success:
        raise Exception(f"Container startup failed: {message}")

    # Complete
    update_install_progress("Installation complete", 100)
    add_install_log("=== INSTALLATION COMPLETED SUCCESSFULLY ===")
    add_install_log("")
    add_install_log("Your Odoo environments are now ready:")
    add_install_log(f"  Test: http://{config.get('domainTest')}")
    add_install_log(f"  Staging: http://{config.get('domainStaging')}")
    add_install_log(f"  Production: http://{config.get('domainProd')}")

    with installation_state['lock']:
        installation_state['success'] = True
        installation_state['running'] = False

    return True, "Installation completed successfully"

# ============================================
# WIZARD HTML GENERATOR
# ============================================

def get_wizard_html():
    """Generate the complete 6-step wizard HTML with embedded CSS and JavaScript."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Odoo Multi-Environment Installer</title>
    <style>
        /* ============================================
           GLOBAL STYLES
           ============================================ */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #714B67;
            --primary-dark: #5a3a52;
            --success: #4caf50;
            --warning: #ff9800;
            --danger: #f44336;
            --info: #2196f3;
            --gray-50: #fafafa;
            --gray-100: #f5f5f5;
            --gray-200: #eeeeee;
            --gray-300: #e0e0e0;
            --gray-600: #757575;
            --gray-700: #616161;
            --gray-900: #212121;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
        }

        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }

        /* ============================================
           HEADER
           ============================================ */
        .header {
            background: var(--primary);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 28px;
            margin-bottom: 10px;
        }

        .header p {
            opacity: 0.9;
            font-size: 14px;
        }

        /* ============================================
           PROGRESS BAR
           ============================================ */
        .progress-container {
            background: var(--gray-100);
            padding: 20px 30px;
            border-bottom: 1px solid var(--gray-300);
        }

        .progress-steps {
            display: flex;
            justify-content: space-between;
            position: relative;
            margin-bottom: 10px;
        }

        .progress-steps::before {
            content: '';
            position: absolute;
            top: 20px;
            left: 0;
            right: 0;
            height: 2px;
            background: var(--gray-300);
            z-index: 0;
        }

        .progress-line {
            position: absolute;
            top: 20px;
            left: 0;
            height: 2px;
            background: var(--primary);
            z-index: 1;
            transition: width 0.3s ease;
        }

        .progress-step {
            position: relative;
            z-index: 2;
            text-align: center;
            flex: 1;
        }

        .progress-step-circle {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: white;
            border: 2px solid var(--gray-300);
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 8px;
            font-weight: bold;
            color: var(--gray-600);
            transition: all 0.3s ease;
        }

        .progress-step.active .progress-step-circle {
            border-color: var(--primary);
            background: var(--primary);
            color: white;
        }

        .progress-step.completed .progress-step-circle {
            border-color: var(--success);
            background: var(--success);
            color: white;
        }

        .progress-step-label {
            font-size: 12px;
            color: var(--gray-600);
        }

        .progress-step.active .progress-step-label {
            color: var(--primary);
            font-weight: 600;
        }

        /* ============================================
           WIZARD CONTENT
           ============================================ */
        .wizard-content {
            padding: 40px;
        }

        .step {
            display: none;
        }

        .step.active {
            display: block;
            animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .step-title {
            font-size: 24px;
            color: var(--gray-900);
            margin-bottom: 10px;
        }

        .step-description {
            color: var(--gray-600);
            margin-bottom: 30px;
        }

        /* ============================================
           FORM ELEMENTS
           ============================================ */
        .form-group {
            margin-bottom: 24px;
        }

        .form-group label {
            display: block;
            font-weight: 600;
            color: var(--gray-700);
            margin-bottom: 8px;
            font-size: 14px;
        }

        .form-group input[type="text"],
        .form-group input[type="password"],
        .form-group select {
            width: 100%;
            padding: 12px;
            border: 2px solid var(--gray-300);
            border-radius: 6px;
            font-size: 14px;
            transition: border-color 0.2s;
        }

        .form-group input:focus,
        .form-group select:focus {
            outline: none;
            border-color: var(--primary);
        }

        .form-group small {
            display: block;
            color: var(--gray-600);
            margin-top: 4px;
            font-size: 12px;
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }

        .form-row-3 {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 16px;
        }

        .checkbox-group {
            display: flex;
            align-items: center;
            margin-bottom: 16px;
        }

        .checkbox-group input[type="checkbox"] {
            width: 18px;
            height: 18px;
            margin-right: 8px;
            cursor: pointer;
        }

        .checkbox-group label {
            margin: 0;
            cursor: pointer;
            font-weight: normal;
        }

        /* ============================================
           BUTTONS
           ============================================ */
        .button-group {
            display: flex;
            justify-content: space-between;
            margin-top: 40px;
            padding-top: 30px;
            border-top: 1px solid var(--gray-300);
        }

        .btn {
            padding: 12px 30px;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .btn-primary {
            background: var(--primary);
            color: white;
        }

        .btn-primary:hover:not(:disabled) {
            background: var(--primary-dark);
        }

        .btn-secondary {
            background: var(--gray-300);
            color: var(--gray-700);
        }

        .btn-secondary:hover:not(:disabled) {
            background: var(--gray-600);
            color: white;
        }

        .btn-success {
            background: var(--success);
            color: white;
        }

        .btn-generate {
            padding: 8px 16px;
            font-size: 12px;
            background: var(--info);
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin-top: 4px;
        }

        .btn-generate:hover {
            opacity: 0.9;
        }

        .btn-copy {
            padding: 6px 12px;
            font-size: 12px;
            background: var(--gray-200);
            color: var(--gray-700);
            border: 1px solid var(--gray-300);
            border-radius: 4px;
            cursor: pointer;
            margin-left: 8px;
        }

        .btn-copy:hover {
            background: var(--gray-300);
        }

        /* ============================================
           ALERTS
           ============================================ */
        .alert {
            padding: 16px;
            border-radius: 6px;
            margin-bottom: 20px;
            border-left: 4px solid;
        }

        .alert-info {
            background: #e3f2fd;
            border-color: var(--info);
            color: #1565c0;
        }

        .alert-warning {
            background: #fff3e0;
            border-color: var(--warning);
            color: #e65100;
        }

        .alert-success {
            background: #e8f5e9;
            border-color: var(--success);
            color: #2e7d32;
        }

        /* ============================================
           PREVIEW BOX
           ============================================ */
        .preview-box {
            background: var(--gray-50);
            border: 1px solid var(--gray-300);
            border-radius: 6px;
            padding: 16px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            color: var(--gray-700);
            margin-top: 12px;
            max-height: 200px;
            overflow-y: auto;
        }

        .preview-box pre {
            margin: 0;
            white-space: pre-wrap;
        }

        /* ============================================
           SUMMARY TABLE
           ============================================ */
        .summary-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }

        .summary-table th,
        .summary-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--gray-300);
        }

        .summary-table th {
            background: var(--gray-100);
            font-weight: 600;
            color: var(--gray-700);
        }

        .summary-table td {
            color: var(--gray-700);
        }

        .summary-section {
            margin-bottom: 30px;
        }

        .summary-section h3 {
            color: var(--primary);
            margin-bottom: 12px;
            font-size: 18px;
        }

        /* ============================================
           RESPONSIVE
           ============================================ */
        @media (max-width: 768px) {
            .wizard-content {
                padding: 20px;
            }

            .form-row,
            .form-row-3 {
                grid-template-columns: 1fr;
            }

            .progress-step-label {
                font-size: 10px;
            }

            .header h1 {
                font-size: 22px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>Odoo Multi-Environment Installer</h1>
            <p>Configure and deploy Odoo across Test, Staging, and Production environments</p>
        </div>

        <!-- Progress Bar -->
        <div class="progress-container">
            <div class="progress-steps">
                <div class="progress-line" id="progressLine"></div>
                <div class="progress-step active" data-step="1">
                    <div class="progress-step-circle">1</div>
                    <div class="progress-step-label">Version</div>
                </div>
                <div class="progress-step" data-step="2">
                    <div class="progress-step-circle">2</div>
                    <div class="progress-step-label">Database</div>
                </div>
                <div class="progress-step" data-step="3">
                    <div class="progress-step-circle">3</div>
                    <div class="progress-step-label">Domains</div>
                </div>
                <div class="progress-step" data-step="4">
                    <div class="progress-step-circle">4</div>
                    <div class="progress-step-label">Directories</div>
                </div>
                <div class="progress-step" data-step="5">
                    <div class="progress-step-circle">5</div>
                    <div class="progress-step-label">Ports</div>
                </div>
                <div class="progress-step" data-step="6">
                    <div class="progress-step-circle">6</div>
                    <div class="progress-step-label">Review</div>
                </div>
            </div>
        </div>

        <!-- Wizard Content -->
        <div class="wizard-content">
            <form id="wizardForm">
                <!-- Step 1: Odoo Version -->
                <div class="step active" data-step="1">
                    <h2 class="step-title">Select Odoo Version</h2>
                    <p class="step-description">Choose the Odoo version you want to install across all environments.</p>

                    <div class="form-group">
                        <label for="odooVersion">Odoo Version</label>
                        <select id="odooVersion" name="odooVersion" required>
                            <option value="">-- Select Version --</option>
                            <option value="14.0">14.0</option>
                            <option value="15.0">15.0</option>
                            <option value="16.0">16.0</option>
                            <option value="17.0">17.0</option>
                            <option value="18.0" selected>18.0</option>
                            <option value="19.0">19.0</option>
                        </select>
                        <small>This version will be used for all three environments (test, staging, production)</small>
                    </div>
                </div>

                <!-- Step 2: Database Configuration -->
                <div class="step" data-step="2">
                    <h2 class="step-title">Database Configuration</h2>
                    <p class="step-description">Configure PostgreSQL connection and create database credentials for each environment.</p>

                    <div class="alert alert-warning">
                        <strong>Important:</strong> PostgreSQL must already be installed and running. The installer will configure access and create databases/users.
                    </div>

                    <div class="form-group">
                        <label for="pgPassword">PostgreSQL Superuser Password</label>
                        <input type="password" id="pgPassword" name="pgPassword" placeholder="Enter postgres user password" required>
                        <small>Password for the PostgreSQL 'postgres' superuser account</small>
                    </div>

                    <h3 style="margin: 30px 0 20px 0; color: var(--gray-700);">Database Names</h3>
                    <div class="form-row-3">
                        <div class="form-group">
                            <label for="dbNameTest">Test Database</label>
                            <input type="text" id="dbNameTest" name="dbNameTest" value="odoo_test_db" required>
                        </div>
                        <div class="form-group">
                            <label for="dbNameStaging">Staging Database</label>
                            <input type="text" id="dbNameStaging" name="dbNameStaging" value="odoo_staging_db" required>
                        </div>
                        <div class="form-group">
                            <label for="dbNameProd">Production Database</label>
                            <input type="text" id="dbNameProd" name="dbNameProd" value="odoo_prod_db" required>
                        </div>
                    </div>

                    <h3 style="margin: 30px 0 20px 0; color: var(--gray-700);">Database Users</h3>
                    <div class="form-row-3">
                        <div class="form-group">
                            <label for="dbUserTest">Test User</label>
                            <input type="text" id="dbUserTest" name="dbUserTest" value="odoo_test" required>
                        </div>
                        <div class="form-group">
                            <label for="dbUserStaging">Staging User</label>
                            <input type="text" id="dbUserStaging" name="dbUserStaging" value="odoo_staging" required>
                        </div>
                        <div class="form-group">
                            <label for="dbUserProd">Production User</label>
                            <input type="text" id="dbUserProd" name="dbUserProd" value="odoo_prod" required>
                        </div>
                    </div>

                    <h3 style="margin: 30px 0 20px 0; color: var(--gray-700);">Database Passwords</h3>
                    <div class="form-row-3">
                        <div class="form-group">
                            <label for="dbPassTest">Test Password</label>
                            <input type="text" id="dbPassTest" name="dbPassTest" readonly>
                            <button type="button" class="btn-generate" onclick="generatePassword('dbPassTest')">Generate Secure Password</button>
                        </div>
                        <div class="form-group">
                            <label for="dbPassStaging">Staging Password</label>
                            <input type="text" id="dbPassStaging" name="dbPassStaging" readonly>
                            <button type="button" class="btn-generate" onclick="generatePassword('dbPassStaging')">Generate Secure Password</button>
                        </div>
                        <div class="form-group">
                            <label for="dbPassProd">Production Password</label>
                            <input type="text" id="dbPassProd" name="dbPassProd" readonly>
                            <button type="button" class="btn-generate" onclick="generatePassword('dbPassProd')">Generate Secure Password</button>
                        </div>
                    </div>
                </div>

                <!-- Step 3: Domain & SSL Configuration -->
                <div class="step" data-step="3">
                    <h2 class="step-title">Domain & SSL Configuration</h2>
                    <p class="step-description">Configure domain names and SSL certificates for each environment.</p>

                    <div class="checkbox-group">
                        <input type="checkbox" id="skipSSL" name="skipSSL" onchange="toggleSSLFields()">
                        <label for="skipSSL">Skip SSL configuration (HTTP only - for testing environments)</label>
                    </div>

                    <div class="alert alert-warning" id="sslWarning" style="display: none;">
                        <strong>Warning:</strong> SSL is disabled. Your Odoo instances will be accessible via HTTP only (not secure for production).
                    </div>

                    <h3 style="margin: 30px 0 20px 0; color: var(--gray-700);">Test Environment</h3>
                    <div class="form-group">
                        <label for="domainTest">Domain Name</label>
                        <input type="text" id="domainTest" name="domainTest" placeholder="test.example.com" required>
                    </div>
                    <div id="sslFieldsTest" class="ssl-fields">
                        <div class="form-row">
                            <div class="form-group">
                                <label for="sslCertTest">SSL Certificate Path</label>
                                <input type="text" id="sslCertTest" name="sslCertTest" placeholder="/etc/letsencrypt/live/test.example.com/fullchain.pem">
                            </div>
                            <div class="form-group">
                                <label for="sslKeyTest">SSL Private Key Path</label>
                                <input type="text" id="sslKeyTest" name="sslKeyTest" placeholder="/etc/letsencrypt/live/test.example.com/privkey.pem">
                            </div>
                        </div>
                    </div>

                    <h3 style="margin: 30px 0 20px 0; color: var(--gray-700);">Staging Environment</h3>
                    <div class="form-group">
                        <label for="domainStaging">Domain Name</label>
                        <input type="text" id="domainStaging" name="domainStaging" placeholder="staging.example.com" required>
                    </div>
                    <div id="sslFieldsStaging" class="ssl-fields">
                        <div class="form-row">
                            <div class="form-group">
                                <label for="sslCertStaging">SSL Certificate Path</label>
                                <input type="text" id="sslCertStaging" name="sslCertStaging" placeholder="/etc/letsencrypt/live/staging.example.com/fullchain.pem">
                            </div>
                            <div class="form-group">
                                <label for="sslKeyStaging">SSL Private Key Path</label>
                                <input type="text" id="sslKeyStaging" name="sslKeyStaging" placeholder="/etc/letsencrypt/live/staging.example.com/privkey.pem">
                            </div>
                        </div>
                    </div>

                    <h3 style="margin: 30px 0 20px 0; color: var(--gray-700);">Production Environment</h3>
                    <div class="form-group">
                        <label for="domainProd">Domain Name</label>
                        <input type="text" id="domainProd" name="domainProd" placeholder="odoo.example.com" required>
                    </div>
                    <div id="sslFieldsProd" class="ssl-fields">
                        <div class="form-row">
                            <div class="form-group">
                                <label for="sslCertProd">SSL Certificate Path</label>
                                <input type="text" id="sslCertProd" name="sslCertProd" placeholder="/etc/letsencrypt/live/odoo.example.com/fullchain.pem">
                            </div>
                            <div class="form-group">
                                <label for="sslKeyProd">SSL Private Key Path</label>
                                <input type="text" id="sslKeyProd" name="sslKeyProd" placeholder="/etc/letsencrypt/live/odoo.example.com/privkey.pem">
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Step 4: Directory Structure -->
                <div class="step" data-step="4">
                    <h2 class="step-title">Directory Structure</h2>
                    <p class="step-description">Specify the base directory for Odoo data. Subdirectories will be created automatically.</p>

                    <div class="form-group">
                        <label for="basePath">Base Path for Odoo Data</label>
                        <input type="text" id="basePath" name="basePath" value="/srv/odoo" required>
                        <small>All Odoo data, configurations, and file storage will be under this directory</small>
                    </div>

                    <div class="alert alert-info">
                        <strong>Directory Preview:</strong> The following directories will be created with proper permissions (UID 101, GID 101 for Odoo container user):
                    </div>

                    <div class="preview-box" id="directoryPreview">
                        <pre>/srv/odoo/test/addons
/srv/odoo/test/filestore
/srv/odoo/staging/addons
/srv/odoo/staging/filestore
/srv/odoo/prod/addons
/srv/odoo/prod/filestore
/srv/odoo/docker-compose.yml</pre>
                    </div>
                </div>

                <!-- Step 5: Port Configuration -->
                <div class="step" data-step="5">
                    <h2 class="step-title">Port Configuration</h2>
                    <p class="step-description">Configure HTTP and long-polling/websocket ports for each environment.</p>

                    <div class="alert alert-info">
                        <strong>Note:</strong> These are the host ports that will be mapped to the Odoo containers. Ensure they are not already in use.
                    </div>

                    <h3 style="margin: 30px 0 20px 0; color: var(--gray-700);">HTTP Ports</h3>
                    <div class="form-row-3">
                        <div class="form-group">
                            <label for="portHttpTest">Test HTTP Port</label>
                            <input type="number" id="portHttpTest" name="portHttpTest" value="8069" min="1024" max="65535" required>
                        </div>
                        <div class="form-group">
                            <label for="portHttpStaging">Staging HTTP Port</label>
                            <input type="number" id="portHttpStaging" name="portHttpStaging" value="8070" min="1024" max="65535" required>
                        </div>
                        <div class="form-group">
                            <label for="portHttpProd">Production HTTP Port</label>
                            <input type="number" id="portHttpProd" name="portHttpProd" value="8071" min="1024" max="65535" required>
                        </div>
                    </div>

                    <h3 style="margin: 30px 0 20px 0; color: var(--gray-700);">Long-Polling/WebSocket Ports</h3>
                    <div class="form-row-3">
                        <div class="form-group">
                            <label for="portLpTest">Test Long-Polling Port</label>
                            <input type="number" id="portLpTest" name="portLpTest" value="8072" min="1024" max="65535" required>
                        </div>
                        <div class="form-group">
                            <label for="portLpStaging">Staging Long-Polling Port</label>
                            <input type="number" id="portLpStaging" name="portLpStaging" value="8073" min="1024" max="65535" required>
                        </div>
                        <div class="form-group">
                            <label for="portLpProd">Production Long-Polling Port</label>
                            <input type="number" id="portLpProd" name="portLpProd" value="8074" min="1024" max="65535" required>
                        </div>
                    </div>
                </div>

                <!-- Step 6: Review & Install -->
                <div class="step" data-step="6">
                    <h2 class="step-title">Review Configuration</h2>
                    <p class="step-description">Review your configuration before starting the installation.</p>

                    <div class="checkbox-group">
                        <input type="checkbox" id="dryRun" name="dryRun">
                        <label for="dryRun"><strong>Dry-run mode</strong> (preview only - make no changes)</label>
                    </div>

                    <div id="configSummary"></div>

                    <div class="alert alert-warning" style="margin-top: 30px;">
                        <strong>Important:</strong> This installer will make system-level changes including installing packages, modifying PostgreSQL configuration, and configuring Nginx. Make sure you have reviewed all settings above.
                    </div>
                </div>

                <!-- Navigation Buttons -->
                <div class="button-group">
                    <button type="button" class="btn btn-secondary" id="prevBtn" onclick="changeStep(-1)" style="display: none;">Previous</button>
                    <div></div>
                    <button type="button" class="btn btn-primary" id="nextBtn" onclick="changeStep(1)">Next</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        // ============================================
        // WIZARD STATE
        // ============================================
        let currentStep = 1;
        const totalSteps = 6;

        // ============================================
        // NAVIGATION
        // ============================================
        function changeStep(direction) {
            // Validate current step before moving forward
            if (direction === 1 && !validateStep(currentStep)) {
                return;
            }

            // Update step
            const newStep = currentStep + direction;
            if (newStep < 1 || newStep > totalSteps) {
                return;
            }

            // Hide current step
            document.querySelector(`.step[data-step="${currentStep}"]`).classList.remove('active');

            // Show new step
            currentStep = newStep;
            document.querySelector(`.step[data-step="${currentStep}"]`).classList.add('active');

            // Update progress
            updateProgress();

            // Update buttons
            updateButtons();

            // If moving to step 4, update directory preview
            if (currentStep === 4) {
                updateDirectoryPreview();
            }

            // If moving to step 6, generate summary
            if (currentStep === 6) {
                generateSummary();
            }

            // Scroll to top
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function updateProgress() {
            // Update step indicators
            document.querySelectorAll('.progress-step').forEach(step => {
                const stepNum = parseInt(step.getAttribute('data-step'));
                step.classList.remove('active', 'completed');

                if (stepNum === currentStep) {
                    step.classList.add('active');
                } else if (stepNum < currentStep) {
                    step.classList.add('completed');
                }
            });

            // Update progress line
            const progress = ((currentStep - 1) / (totalSteps - 1)) * 100;
            document.getElementById('progressLine').style.width = progress + '%';
        }

        function updateButtons() {
            const prevBtn = document.getElementById('prevBtn');
            const nextBtn = document.getElementById('nextBtn');

            // Show/hide previous button
            prevBtn.style.display = currentStep === 1 ? 'none' : 'block';

            // Update next button text
            if (currentStep === totalSteps) {
                nextBtn.textContent = 'Start Installation';
                nextBtn.className = 'btn btn-success';
                nextBtn.onclick = startInstallation;
            } else {
                nextBtn.textContent = 'Next';
                nextBtn.className = 'btn btn-primary';
                nextBtn.onclick = () => changeStep(1);
            }
        }

        // ============================================
        // VALIDATION
        // ============================================
        function validateStep(step) {
            let valid = true;

            if (step === 1) {
                const version = document.getElementById('odooVersion').value;
                if (!version) {
                    alert('Please select an Odoo version');
                    return false;
                }
            }

            if (step === 2) {
                const pgPassword = document.getElementById('pgPassword').value;
                if (!pgPassword) {
                    alert('Please enter PostgreSQL superuser password');
                    return false;
                }

                const passwords = ['dbPassTest', 'dbPassStaging', 'dbPassProd'];
                for (const id of passwords) {
                    if (!document.getElementById(id).value) {
                        alert('Please generate passwords for all database users');
                        return false;
                    }
                }
            }

            if (step === 3) {
                const domains = ['domainTest', 'domainStaging', 'domainProd'];
                for (const id of domains) {
                    const value = document.getElementById(id).value;
                    if (!value) {
                        alert('Please enter all domain names');
                        return false;
                    }
                }

                // If SSL is not skipped, validate SSL paths
                if (!document.getElementById('skipSSL').checked) {
                    const sslFields = ['sslCertTest', 'sslKeyTest', 'sslCertStaging', 'sslKeyStaging', 'sslCertProd', 'sslKeyProd'];
                    for (const id of sslFields) {
                        if (!document.getElementById(id).value) {
                            alert('Please enter all SSL certificate paths or enable "Skip SSL"');
                            return false;
                        }
                    }
                }
            }

            if (step === 4) {
                const basePath = document.getElementById('basePath').value;
                if (!basePath) {
                    alert('Please enter base path for Odoo data');
                    return false;
                }
            }

            if (step === 5) {
                const ports = ['portHttpTest', 'portHttpStaging', 'portHttpProd', 'portLpTest', 'portLpStaging', 'portLpProd'];
                const portValues = [];

                for (const id of ports) {
                    const port = parseInt(document.getElementById(id).value);
                    if (!port || port < 1024 || port > 65535) {
                        alert('All ports must be between 1024 and 65535');
                        return false;
                    }
                    if (portValues.includes(port)) {
                        alert('All ports must be unique');
                        return false;
                    }
                    portValues.push(port);
                }
            }

            return valid;
        }

        // ============================================
        // PASSWORD GENERATION
        // ============================================
        function generatePassword(fieldId) {
            const length = 24;
            const charset = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
            let password = '';

            // Use crypto.getRandomValues for secure random generation
            const array = new Uint32Array(length);
            crypto.getRandomValues(array);

            for (let i = 0; i < length; i++) {
                password += charset[array[i] % charset.length];
            }

            document.getElementById(fieldId).value = password;
        }

        // ============================================
        // SSL TOGGLE
        // ============================================
        function toggleSSLFields() {
            const skipSSL = document.getElementById('skipSSL').checked;
            const sslFields = document.querySelectorAll('.ssl-fields');
            const sslWarning = document.getElementById('sslWarning');

            sslFields.forEach(field => {
                field.style.display = skipSSL ? 'none' : 'block';
            });

            sslWarning.style.display = skipSSL ? 'block' : 'none';

            // Clear SSL fields if skipping
            if (skipSSL) {
                ['sslCertTest', 'sslKeyTest', 'sslCertStaging', 'sslKeyStaging', 'sslCertProd', 'sslKeyProd'].forEach(id => {
                    document.getElementById(id).value = '';
                });
            }
        }

        // ============================================
        // DIRECTORY PREVIEW
        // ============================================
        function updateDirectoryPreview() {
            const basePath = document.getElementById('basePath').value || '/srv/odoo';
            const preview = `${basePath}/test/addons
${basePath}/test/filestore
${basePath}/staging/addons
${basePath}/staging/filestore
${basePath}/prod/addons
${basePath}/prod/filestore
${basePath}/docker-compose.yml`;
            document.getElementById('directoryPreview').innerHTML = '<pre>' + preview + '</pre>';
        }

        // ============================================
        // SUMMARY GENERATION
        // ============================================
        function generateSummary() {
            const config = getFormData();
            const skipSSL = document.getElementById('skipSSL').checked;

            let html = '<div class="summary-section"><h3>Odoo Version</h3>';
            html += '<p><strong>Version:</strong> ' + config.odooVersion + '</p></div>';

            html += '<div class="summary-section"><h3>Database Configuration</h3>';
            html += '<table class="summary-table"><thead><tr><th>Environment</th><th>Database</th><th>User</th><th>Password</th></tr></thead><tbody>';
            html += '<tr><td>Test</td><td>' + config.dbNameTest + '</td><td>' + config.dbUserTest + '</td><td>' + maskPassword(config.dbPassTest) + '</td></tr>';
            html += '<tr><td>Staging</td><td>' + config.dbNameStaging + '</td><td>' + config.dbUserStaging + '</td><td>' + maskPassword(config.dbPassStaging) + '</td></tr>';
            html += '<tr><td>Production</td><td>' + config.dbNameProd + '</td><td>' + config.dbUserProd + '</td><td>' + maskPassword(config.dbPassProd) + '</td></tr>';
            html += '</tbody></table></div>';

            html += '<div class="summary-section"><h3>Domain & SSL Configuration</h3>';
            html += '<table class="summary-table"><thead><tr><th>Environment</th><th>Domain</th><th>SSL</th></tr></thead><tbody>';
            html += '<tr><td>Test</td><td>' + config.domainTest + '</td><td>' + (skipSSL ? 'HTTP Only' : 'HTTPS Enabled') + '</td></tr>';
            html += '<tr><td>Staging</td><td>' + config.domainStaging + '</td><td>' + (skipSSL ? 'HTTP Only' : 'HTTPS Enabled') + '</td></tr>';
            html += '<tr><td>Production</td><td>' + config.domainProd + '</td><td>' + (skipSSL ? 'HTTP Only' : 'HTTPS Enabled') + '</td></tr>';
            html += '</tbody></table></div>';

            html += '<div class="summary-section"><h3>Directories</h3>';
            html += '<p><strong>Base Path:</strong> ' + config.basePath + '</p></div>';

            html += '<div class="summary-section"><h3>Port Configuration</h3>';
            html += '<table class="summary-table"><thead><tr><th>Environment</th><th>HTTP Port</th><th>Long-Polling Port</th></tr></thead><tbody>';
            html += '<tr><td>Test</td><td>' + config.portHttpTest + '</td><td>' + config.portLpTest + '</td></tr>';
            html += '<tr><td>Staging</td><td>' + config.portHttpStaging + '</td><td>' + config.portLpStaging + '</td></tr>';
            html += '<tr><td>Production</td><td>' + config.portHttpProd + '</td><td>' + config.portLpProd + '</td></tr>';
            html += '</tbody></table></div>';

            document.getElementById('configSummary').innerHTML = html;
        }

        function maskPassword(password) {
            return '•'.repeat(8) + ' <button type="button" class="btn-copy" onclick="copyToClipboard(\\'' + password + '\\')">Copy</button>';
        }

        // ============================================
        // UTILITY FUNCTIONS
        // ============================================
        function getFormData() {
            const formElements = document.getElementById('wizardForm').elements;
            const data = {};

            for (let element of formElements) {
                if (element.name && element.type !== 'button') {
                    if (element.type === 'checkbox') {
                        data[element.name] = element.checked;
                    } else {
                        data[element.name] = element.value;
                    }
                }
            }

            return data;
        }

        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(() => {
                alert('Copied to clipboard!');
            }).catch(err => {
                console.error('Failed to copy:', err);
            });
        }

        // ============================================
        // INSTALLATION
        // ============================================
        let installationPolling = null;

        function startInstallation() {
            const config = getFormData();
            const isDryRun = document.getElementById('dryRun').checked;

            const message = isDryRun
                ? 'Are you ready to run in DRY-RUN mode? No changes will be made to your system.'
                : 'Are you ready to start the installation? This will make system-level changes to your server.';

            if (!confirm(message)) {
                return;
            }

            // Show installation modal
            showInstallationModal(isDryRun);

            // Start installation
            fetch('/api/start-installation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    config: config,
                    dryRun: isDryRun
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    addInstallLog('Installation started...');
                    startPolling();
                } else {
                    addInstallLog('ERROR: Failed to start installation');
                    if (data.errors) {
                        data.errors.forEach(err => addInstallLog('  - ' + err));
                    } else if (data.error) {
                        addInstallLog('  - ' + data.error);
                    }
                }
            })
            .catch(error => {
                addInstallLog('ERROR: ' + error);
            });
        }

        function showInstallationModal(isDryRun) {
            const modal = document.createElement('div');
            modal.id = 'installModal';
            modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 9999; display: flex; align-items: center; justify-content: center;';

            const content = document.createElement('div');
            content.style.cssText = 'background: white; border-radius: 12px; max-width: 800px; width: 90%; max-height: 80vh; display: flex; flex-direction: column;';

            const header = document.createElement('div');
            header.style.cssText = 'padding: 20px; border-bottom: 1px solid #e0e0e0;';
            header.innerHTML = '<h2 style="margin: 0;">' + (isDryRun ? '🔍 Dry-Run Mode' : '⚙️ Installation in Progress') + '</h2>';

            const progressBar = document.createElement('div');
            progressBar.style.cssText = 'padding: 20px;';
            progressBar.innerHTML = `
                <div style="margin-bottom: 10px;">
                    <strong id="currentStep">Initializing...</strong>
                </div>
                <div style="background: #e0e0e0; border-radius: 4px; height: 24px; overflow: hidden;">
                    <div id="progressBar" style="background: #714B67; height: 100%; width: 0%; transition: width 0.3s;"></div>
                </div>
                <div style="margin-top: 5px; text-align: right;">
                    <span id="progressPercent">0%</span>
                </div>
            `;

            const logContainer = document.createElement('div');
            logContainer.style.cssText = 'flex: 1; overflow-y: auto; padding: 20px; background: #f5f5f5; font-family: monospace; font-size: 12px; border-top: 1px solid #e0e0e0; border-bottom: 1px solid #e0e0e0;';
            logContainer.id = 'installLogs';

            const footer = document.createElement('div');
            footer.style.cssText = 'padding: 20px; display: none;';
            footer.id = 'installFooter';
            footer.innerHTML = `
                <button onclick="downloadCredentials()" class="btn btn-primary" style="margin-right: 10px;">Download Credentials</button>
                <button onclick="shutdownInstaller()" class="btn btn-secondary">Finish & Close Installer</button>
            `;

            content.appendChild(header);
            content.appendChild(progressBar);
            content.appendChild(logContainer);
            content.appendChild(footer);
            modal.appendChild(content);
            document.body.appendChild(modal);
        }

        function addInstallLog(message) {
            const logContainer = document.getElementById('installLogs');
            if (logContainer) {
                const logEntry = document.createElement('div');
                logEntry.textContent = message;
                logContainer.appendChild(logEntry);
                logContainer.scrollTop = logContainer.scrollHeight;
            }
        }

        function startPolling() {
            installationPolling = setInterval(() => {
                fetch('/api/installation-status')
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            updateInstallationStatus(data.status);
                        }
                    })
                    .catch(error => {
                        console.error('Polling error:', error);
                    });
            }, 1000); // Poll every second
        }

        function updateInstallationStatus(status) {
            // Update progress bar
            const progressBar = document.getElementById('progressBar');
            const progressPercent = document.getElementById('progressPercent');
            const currentStep = document.getElementById('currentStep');

            if (progressBar) {
                progressBar.style.width = status.progress + '%';
            }
            if (progressPercent) {
                progressPercent.textContent = status.progress + '%';
            }
            if (currentStep) {
                currentStep.textContent = status.current_step;
            }

            // Update logs (only add new ones)
            const logContainer = document.getElementById('installLogs');
            if (logContainer && status.logs) {
                const currentLogCount = logContainer.children.length;
                const newLogs = status.logs.slice(currentLogCount);
                newLogs.forEach(log => addInstallLog(log));
            }

            // Check if installation completed
            if (!status.running) {
                clearInterval(installationPolling);

                if (status.success) {
                    addInstallLog('');
                    addInstallLog('✅ Installation completed successfully!');
                    document.getElementById('installFooter').style.display = 'block';
                } else if (status.error) {
                    addInstallLog('');
                    addInstallLog('❌ Installation failed: ' + status.error);
                }
            }
        }

        function downloadCredentials() {
            fetch('/api/download-credentials')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const blob = new Blob([JSON.stringify(data.credentials, null, 2)], { type: 'application/json' });
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'odoo-credentials-' + new Date().toISOString().split('T')[0] + '.json';
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(url);
                        addInstallLog('✅ Credentials downloaded');
                    } else {
                        alert('Failed to download credentials: ' + data.error);
                    }
                })
                .catch(error => {
                    alert('Error downloading credentials: ' + error);
                });
        }

        function shutdownInstaller() {
            if (!confirm('This will shut down the installer and rename it to .done. Continue?')) {
                return;
            }

            addInstallLog('Shutting down installer...');

            fetch('/api/shutdown-installer', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    addInstallLog('✅ Installer shutdown initiated');
                    setTimeout(() => {
                        document.body.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100vh; font-family: sans-serif;"><div style="text-align: center;"><h1>✅ Installation Complete</h1><p>The installer has been shut down.</p><p>You can now close this window.</p></div></div>';
                    }, 2000);
                } else {
                    alert('Failed to shutdown: ' + data.error);
                }
            })
            .catch(error => {
                alert('Error shutting down: ' + error);
            });
        }

        // ============================================
        // INITIALIZATION
        // ============================================
        document.addEventListener('DOMContentLoaded', function() {
            // Generate all passwords on load
            generatePassword('dbPassTest');
            generatePassword('dbPassStaging');
            generatePassword('dbPassProd');

            // Update directory preview
            updateDirectoryPreview();

            // Set up base path change listener
            document.getElementById('basePath').addEventListener('input', updateDirectoryPreview);
        });
    </script>
</body>
</html>
"""

# ============================================
# ROUTES
# ============================================

@app.route('/')
@requires_auth
def index():
    """Main landing page with 6-step installation wizard."""
    update_activity()
    logger.info(f"Access to index from {request.remote_addr}")

    return get_wizard_html()

@app.route('/health')
def health():
    """Health check endpoint (no auth required)."""
    update_activity()
    return jsonify({
        'status': 'ok',
        'version': APP_VERSION,
        'inactivity_seconds': int(get_inactivity_duration())
    })

@app.route('/api/generate-password', methods=['POST'])
@requires_auth
def api_generate_password():
    """Generate a secure password."""
    update_activity()
    try:
        data = request.get_json() or {}
        length = int(data.get('length', 24))
        if length < 8 or length > 128:
            length = 24

        password = generate_secure_password(length)
        logger.info("Generated secure password")
        return jsonify({'success': True, 'password': password})
    except Exception as e:
        logger.error(f"Error generating password: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/validate-config', methods=['POST'])
@requires_auth
def api_validate_config():
    """Validate configuration data."""
    update_activity()
    try:
        config = request.get_json()
        if not config:
            return jsonify({'success': False, 'errors': ['No configuration data provided']}), 400

        is_valid, errors = validate_configuration(config)

        logger.info(f"Configuration validation: {'passed' if is_valid else 'failed'}")
        if not is_valid:
            logger.warning(f"Validation errors: {errors}")

        return jsonify({
            'success': is_valid,
            'errors': errors if not is_valid else []
        })
    except Exception as e:
        logger.error(f"Error validating configuration: {e}")
        return jsonify({'success': False, 'errors': [str(e)]}), 500

@app.route('/api/check-ports', methods=['POST'])
@requires_auth
def api_check_ports():
    """Check if specified ports are available."""
    update_activity()
    try:
        data = request.get_json()
        ports = data.get('ports', [])

        if not isinstance(ports, list):
            return jsonify({'success': False, 'error': 'Ports must be an array'}), 400

        results = {}
        for port in ports:
            try:
                port_num = int(port)
                available, message = check_port_available(port_num)
                results[str(port)] = {
                    'available': available,
                    'message': message
                }
            except (ValueError, TypeError):
                results[str(port)] = {
                    'available': False,
                    'message': 'Invalid port number'
                }

        logger.info(f"Checked availability of {len(ports)} ports")
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        logger.error(f"Error checking ports: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/save-config', methods=['POST'])
@requires_auth
def api_save_config():
    """Save configuration to session."""
    update_activity()
    try:
        config = request.get_json()
        if not config:
            return jsonify({'success': False, 'error': 'No configuration data provided'}), 400

        # Validate before saving
        is_valid, errors = validate_configuration(config)
        if not is_valid:
            return jsonify({'success': False, 'errors': errors}), 400

        # Save to session
        session['odoo_config'] = config
        session.modified = True

        logger.info("Configuration saved to session")
        return jsonify({'success': True, 'message': 'Configuration saved'})
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get-config', methods=['GET'])
@requires_auth
def api_get_config():
    """Retrieve configuration from session."""
    update_activity()
    try:
        config = session.get('odoo_config', {})
        logger.info("Configuration retrieved from session")
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        logger.error(f"Error retrieving configuration: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/validate-ssl-files', methods=['POST'])
@requires_auth
def api_validate_ssl_files():
    """Validate SSL certificate files."""
    update_activity()
    try:
        data = request.get_json()
        files = data.get('files', {})

        if not isinstance(files, dict):
            return jsonify({'success': False, 'error': 'Files must be an object'}), 400

        results = {}
        for name, path in files.items():
            valid, message = validate_ssl_file(path)
            results[name] = {
                'valid': valid,
                'message': message
            }

        logger.info(f"Validated {len(files)} SSL file paths")
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        logger.error(f"Error validating SSL files: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/start-installation', methods=['POST'])
@requires_auth
def api_start_installation():
    """Start the installation process."""
    update_activity()
    try:
        data = request.get_json()
        config = data.get('config', {})
        dry_run = data.get('dryRun', False)

        if not config:
            return jsonify({'success': False, 'error': 'No configuration provided'}), 400

        # Validate configuration
        is_valid, errors = validate_configuration(config)
        if not is_valid:
            return jsonify({'success': False, 'errors': errors}), 400

        # Start installation in background thread
        def run_install():
            run_installation(config, dry_run=dry_run)

        install_thread = Thread(target=run_install, daemon=True)
        install_thread.start()

        logger.info(f"Installation started (dry_run={dry_run})")
        return jsonify({'success': True, 'message': 'Installation started'})
    except Exception as e:
        logger.error(f"Error starting installation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/installation-status', methods=['GET'])
@requires_auth
def api_installation_status():
    """Get installation status and logs."""
    update_activity()
    try:
        with installation_state['lock']:
            status = {
                'running': installation_state['running'],
                'dry_run': installation_state['dry_run'],
                'current_step': installation_state['current_step'],
                'progress': installation_state['progress'],
                'logs': installation_state['logs'].copy(),
                'success': installation_state['success'],
                'error': installation_state['error']
            }
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        logger.error(f"Error getting installation status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download-credentials', methods=['GET'])
@requires_auth
def api_download_credentials():
    """Download installation credentials as JSON."""
    update_activity()
    try:
        config = session.get('odoo_config', {})
        if not config:
            return jsonify({'success': False, 'error': 'No configuration found'}), 404

        credentials = {
            'installation_date': datetime.now().isoformat(),
            'odoo_version': config.get('odooVersion'),
            'base_path': config.get('basePath'),
            'environments': {
                'test': {
                    'domain': config.get('domainTest'),
                    'database': config.get('dbNameTest'),
                    'db_user': config.get('dbUserTest'),
                    'db_password': config.get('dbPassTest'),
                    'http_port': config.get('portHttpTest'),
                    'longpolling_port': config.get('portLpTest')
                },
                'staging': {
                    'domain': config.get('domainStaging'),
                    'database': config.get('dbNameStaging'),
                    'db_user': config.get('dbUserStaging'),
                    'db_password': config.get('dbPassStaging'),
                    'http_port': config.get('portHttpStaging'),
                    'longpolling_port': config.get('portLpStaging')
                },
                'production': {
                    'domain': config.get('domainProd'),
                    'database': config.get('dbNameProd'),
                    'db_user': config.get('dbUserProd'),
                    'db_password': config.get('dbPassProd'),
                    'http_port': config.get('portHttpProd'),
                    'longpolling_port': config.get('portLpProd')
                }
            },
            'urls': {
                'test': f"{'https' if not config.get('skipSSL') else 'http'}://{config.get('domainTest')}",
                'staging': f"{'https' if not config.get('skipSSL') else 'http'}://{config.get('domainStaging')}",
                'production': f"{'https' if not config.get('skipSSL') else 'http'}://{config.get('domainProd')}"
            }
        }

        logger.info("Credentials downloaded")
        return jsonify({'success': True, 'credentials': credentials})
    except Exception as e:
        logger.error(f"Error downloading credentials: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/shutdown-installer', methods=['POST'])
@requires_auth
def api_shutdown_installer():
    """Shutdown the installer and rename file to .done."""
    update_activity()
    logger.info("Installer shutdown requested")

    def rename_and_shutdown():
        time.sleep(2)
        try:
            # Rename installer.py to installer.py.done
            current_file = os.path.abspath(__file__)
            done_file = current_file + '.done'
            os.rename(current_file, done_file)
            logger.info(f"Renamed {current_file} to {done_file}")
        except Exception as e:
            logger.error(f"Failed to rename installer: {e}")
        finally:
            logger.info("Shutting down installer")
            os._exit(0)

    Thread(target=rename_and_shutdown).start()
    return jsonify({'success': True, 'message': 'Installer shutting down'})

@app.route('/shutdown', methods=['POST'])
@requires_auth
def shutdown():
    """Manual shutdown endpoint."""
    logger.info("Manual shutdown requested")

    def delayed_shutdown():
        time.sleep(1)
        logger.info("Shutting down installer")
        os._exit(0)

    Thread(target=delayed_shutdown).start()
    return jsonify({'status': 'shutting down'})

# ============================================
# MAIN ENTRY POINT
# ============================================

def main():
    """Main entry point for the installer."""

    # Check root permissions
    check_root_permissions()

    logger.info("="*60)
    logger.info("Odoo Multi-Environment Installer Starting")
    logger.info(f"Version: {APP_VERSION}")
    logger.info("="*60)

    # Prompt for credentials
    prompt_for_credentials()

    # Start activity monitor thread
    monitor_thread = Thread(target=activity_monitor, daemon=True)
    monitor_thread.start()
    logger.info("Activity monitor started (60 minute timeout)")

    # Get server IP for display
    try:
        import socket
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
    except:
        ip_address = "YOUR_SERVER_IP"

    # Display access information
    print("\n" + "="*60)
    print("  🌐 INSTALLER WEB UI IS READY")
    print("="*60)
    print(f"\n  Access the installer at:")
    print(f"  → http://{ip_address}:{APP_PORT}")
    print(f"  → http://localhost:{APP_PORT} (if local)")
    print(f"\n  Username: {auth_credentials['username']}")
    print(f"  Password: (the password you just set)")
    print(f"\n  ⚠️  Auto-shutdown after 60 minutes of inactivity")
    print(f"  📝 Logs: {LOG_FILE}")
    print("\n" + "="*60 + "\n")

    # Start Flask server
    logger.info(f"Starting Flask server on 0.0.0.0:{APP_PORT}")

    try:
        app.run(
            host='0.0.0.0',
            port=APP_PORT,
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("Installer stopped by user (Ctrl+C)")
        print("\n\n✅ Installer stopped")
    except Exception as e:
        logger.error(f"Error starting server: {e}")
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
