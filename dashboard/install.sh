#!/bin/bash
#
# Odoo Management Dashboard Installer
# This script installs the dashboard and sets it up as a systemd service
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
INSTALL_DIR="/opt/odoo-dashboard"
ODOO_BASE_DIR="${ODOO_BASE_DIR:-/srv/odoo}"
DASHBOARD_PORT="${DASHBOARD_PORT:-9998}"
DATA_DIR="${DATA_DIR:-/var/lib/odoo-dashboard}"

echo ""
echo "========================================"
echo "  Odoo Management Dashboard Installer"
echo "========================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root${NC}"
    exit 1
fi

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required but not installed${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}Found Python $PYTHON_VERSION${NC}"

# Check for docker-compose.yml
if [ ! -f "$ODOO_BASE_DIR/docker-compose.yml" ]; then
    echo -e "${YELLOW}Warning: docker-compose.yml not found at $ODOO_BASE_DIR${NC}"
    echo "You can set ODOO_BASE_DIR environment variable to specify the correct path"
    echo ""
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."

# Try pip install first, then apt-get for externally-managed environments
install_pip_package() {
    local package=$1

    # Try standard pip install
    if pip3 install "$package" 2>/dev/null; then
        return 0
    fi

    # Try apt-get for system packages
    local apt_package="python3-${package}"
    if apt-get install -y "$apt_package" 2>/dev/null; then
        return 0
    fi

    # Try pip with --break-system-packages (last resort)
    if pip3 install --break-system-packages "$package" 2>/dev/null; then
        return 0
    fi

    return 1
}

# Required packages
PACKAGES="flask apscheduler boto3"

for pkg in $PACKAGES; do
    echo "  Installing $pkg..."
    if ! install_pip_package "$pkg"; then
        echo -e "${RED}Failed to install $pkg${NC}"
        exit 1
    fi
done

echo -e "${GREEN}Dependencies installed successfully${NC}"

# Create installation directory
echo ""
echo "Creating installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$DATA_DIR"

# Copy files
echo "Copying files..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cp "$SCRIPT_DIR/dashboard.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/config.py" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/services" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/templates" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/static" "$INSTALL_DIR/"

echo -e "${GREEN}Files copied to $INSTALL_DIR${NC}"

# Create/update systemd service file
echo ""
echo "Installing systemd service..."

cat > /etc/systemd/system/odoo-dashboard.service << EOF
[Unit]
Description=Odoo Management Dashboard
Documentation=https://github.com/yourusername/odoo-installer
After=network.target docker.service postgresql.service
Wants=docker.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1
Environment=ODOO_BASE_DIR=$ODOO_BASE_DIR
Environment=DASHBOARD_PORT=$DASHBOARD_PORT
Environment=DATA_DIR=$DATA_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/dashboard.py
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=odoo-dashboard

# Security hardening
NoNewPrivileges=false
ProtectSystem=false
ProtectHome=false
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

echo -e "${GREEN}Systemd service installed${NC}"

# Enable and start service
echo ""
read -p "Start the dashboard service now? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    systemctl enable odoo-dashboard
    systemctl start odoo-dashboard

    # Wait a moment for startup
    sleep 2

    if systemctl is-active --quiet odoo-dashboard; then
        echo -e "${GREEN}Dashboard service started successfully${NC}"
    else
        echo -e "${RED}Service failed to start. Check: journalctl -u odoo-dashboard${NC}"
        exit 1
    fi
else
    echo "You can start the service later with:"
    echo "  systemctl enable odoo-dashboard"
    echo "  systemctl start odoo-dashboard"
fi

# Print summary
echo ""
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "Dashboard URL:    http://localhost:$DASHBOARD_PORT"
echo "Default login:    admin / admin"
echo ""
echo "Important commands:"
echo "  systemctl status odoo-dashboard    # Check status"
echo "  systemctl restart odoo-dashboard   # Restart service"
echo "  journalctl -u odoo-dashboard -f    # View logs"
echo ""
echo "Configuration:"
echo "  Install dir:    $INSTALL_DIR"
echo "  Data dir:       $DATA_DIR"
echo "  Odoo base:      $ODOO_BASE_DIR"
echo ""
echo -e "${YELLOW}IMPORTANT: Change the default credentials (admin/admin) in production!${NC}"
echo ""
