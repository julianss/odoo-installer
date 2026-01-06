#!/bin/bash
# Cleanup script to reset Odoo installation for fresh reinstall
# Run this as root: sudo bash cleanup.sh

set -e

echo "========================================"
echo "Odoo Installation Cleanup Script"
echo "========================================"
echo ""
echo "This will remove:"
echo "  - Docker containers (odoo-test, odoo-staging, odoo-prod)"
echo "  - Docker compose configuration"
echo "  - Directory structure (/srv/odoo)"
echo "  - Nginx configuration"
echo "  - PostgreSQL users (optional)"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Step 1: Stopping and removing Docker containers..."
if command -v docker &> /dev/null; then
    # Stop containers if running
    docker stop odoo-test odoo-staging odoo-prod 2>/dev/null || echo "  (Containers not running or don't exist)"

    # Remove containers
    docker rm odoo-test odoo-staging odoo-prod 2>/dev/null || echo "  (Containers don't exist)"

    echo "  ✓ Docker containers removed"
else
    echo "  (Docker not installed, skipping)"
fi

echo ""
echo "Step 2: Removing Docker Compose file and directory structure..."
if [ -d "/srv/odoo" ]; then
    # Stop via docker-compose if it exists
    if [ -f "/srv/odoo/docker-compose.yml" ]; then
        cd /srv/odoo && docker compose down 2>/dev/null || true
    fi

    # Remove entire directory
    rm -rf /srv/odoo
    echo "  ✓ Removed /srv/odoo"
else
    echo "  (Directory /srv/odoo doesn't exist)"
fi

echo ""
echo "Step 3: Removing Nginx configuration..."
if [ -f "/etc/nginx/sites-enabled/odoo" ]; then
    rm -f /etc/nginx/sites-enabled/odoo
    echo "  ✓ Removed /etc/nginx/sites-enabled/odoo"
fi

if [ -f "/etc/nginx/sites-available/odoo" ]; then
    rm -f /etc/nginx/sites-available/odoo
    echo "  ✓ Removed /etc/nginx/sites-available/odoo"
fi

# Test and reload nginx if it's running
if systemctl is-active --quiet nginx; then
    nginx -t && systemctl reload nginx
    echo "  ✓ Nginx reloaded"
fi

echo ""
echo "Step 4: PostgreSQL cleanup (optional)..."
read -p "Do you want to remove PostgreSQL users and databases? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Drop databases and users
    sudo -u postgres psql <<EOF 2>/dev/null || echo "  (Some databases/users may not exist)"
-- Drop databases
DROP DATABASE IF EXISTS odoo_test_db;
DROP DATABASE IF EXISTS odoo_staging_db;
DROP DATABASE IF EXISTS odoo_prod_db;

-- Drop users
DROP USER IF EXISTS odoo_test;
DROP USER IF EXISTS odoo_staging;
DROP USER IF EXISTS odoo_prod;
EOF
    echo "  ✓ PostgreSQL users and databases removed"
else
    echo "  Skipped PostgreSQL cleanup"
    echo "  Note: Existing database users will be reused if passwords match"
fi

echo ""
echo "========================================"
echo "✅ Cleanup complete!"
echo "========================================"
echo ""
echo "You can now run the installer again with:"
echo "  sudo python3 cli_installer.py"
echo ""
echo "The installer will create everything fresh with the new configuration."
