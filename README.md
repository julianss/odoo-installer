# Odoo Multi-Environment Docker Installer

A comprehensive, single-file Python CLI installer that automates the setup of Odoo across three isolated environments (Test, Staging, Production) using Docker, PostgreSQL, and Nginx.

## Features

- **🎯 Single-File Installer** - Everything in one Python file
- **💻 Interactive CLI** - User-friendly command-line interface with Rich and Questionary
- **🐳 Docker-Based** - Uses official Odoo Docker images
- **🔄 Multi-Environment** - Automatically configures test, staging, and production
- **✅ Idempotent** - Safe to run multiple times
- **🔍 Dry-Run Mode** - Preview changes before applying
- **📊 Real-Time Progress** - Live installation progress tracking
- **🔒 SSL Support** - Automatic HTTPS configuration with your certificates
- **💾 Credential Management** - Saves installation credentials to JSON file

## Prerequisites

### System Requirements
- **OS**: Ubuntu 20.04+ or Debian 11+
- **User**: Must run as root (sudo)
- **RAM**: Minimum 4GB recommended
- **Disk**: 20GB+ free space

### Required Before Installation
- Domain names for each environment (e.g., test.example.com, staging.example.com, odoo.example.com)
- SSL certificates (optional, can skip for testing)
- PostgreSQL superuser (postgres) password

### What Will Be Installed
The installer will automatically install and configure:
- Docker (from official Docker repository)
- PostgreSQL (for database management)
- Nginx (as reverse proxy)
- Docker Compose
- Odoo Docker containers (3 instances)

## Quick Start

### 1. Download the Installer

```bash
# Download cli_installer.py to your server
wget https://your-server.com/cli_installer.py

# Or copy it directly to your server
scp cli_installer.py root@your-server:/root/
```

### 2. Run the Installer

```bash
# SSH into your server as root
ssh root@your-server

# Run the CLI installer
sudo python3 cli_installer.py
```

The installer will:
1. Auto-install required dependencies (Rich, Questionary)
2. Guide you through interactive configuration
3. Display a review screen before installation
4. Show real-time progress during installation
5. Save credentials to /root/odoo-installation-credentials.json

### 3. Follow the Interactive Prompts

The installer will ask you to configure:

1. **Odoo Version** - Select version (14.0, 15.0, 16.0, 17.0, 18.0, or 19.0)
2. **PostgreSQL Password** - Password for the postgres superuser
3. **Database Configuration** - Names and credentials for each environment
4. **Domain Configuration** - Domain names for test, staging, and production
5. **SSL Configuration** - Optional HTTPS setup with certificate paths
6. **Port Configuration** - HTTP and long-polling ports for each environment
7. **Installation Review** - Review all settings before proceeding

### 4. Installation Credentials

After successful installation, your credentials are saved to:
```
/root/odoo-installation-credentials.json
```

This file contains:
- Database passwords for all environments
- Access URLs
- Port configurations

## Configuration Guide

The CLI installer will prompt you for the following configuration:

### Odoo Version

Choose the Odoo version you want to install:
- 14.0, 15.0, 16.0, 17.0, 18.0, or 19.0
- All three environments will use the same version

### PostgreSQL Configuration

- **Superuser Password**: Password for the `postgres` user (required to create database users)
- **Database Names**: Reference names for each environment (default: odoo_test_db, odoo_staging_db, odoo_prod_db)
  - **Note:** Databases are NOT created by the installer - Odoo creates them on first access
- **Database Users**: PostgreSQL users for each environment (default: odoo_test, odoo_staging, odoo_prod)
  - Created with CREATEDB privilege
- **Database Passwords**: Auto-generated 24-character secure passwords (or provide your own)

### Domain & SSL Configuration

- **Domains**: FQDN for each environment (e.g., test.example.com, staging.example.com, odoo.example.com)
- **SSL Certificates** (optional):
  - Certificate file path (e.g., /etc/letsencrypt/live/your-domain.com/fullchain.pem)
  - Private key path (e.g., /etc/letsencrypt/live/your-domain.com/privkey.pem)
  - Can skip SSL for HTTP-only testing

### Directory Structure

- **Base Path** (default: /srv/odoo): All Odoo data stored here
- Subdirectories created automatically:
  - `/srv/odoo/{test,staging,prod}/addons` - Custom modules
  - `/srv/odoo/{test,staging,prod}/filestore` - File storage

### Port Configuration

- **HTTP Ports** (defaults: test=8069, staging=8070, prod=8069)
- **Long-Polling Ports** (defaults: test=8072, staging=8073, prod=8072)
- All ports must be 1024-65535, unique, and available

### Dry-Run Mode

- Option to preview changes without applying them
- Useful for reviewing what will be installed before committing

## Installation Process

The installer performs these steps automatically:

1. **System Prerequisites** (5-20%)
   - Install Docker from official repository
   - Install PostgreSQL
   - Install Nginx
   - Enable and start services

2. **PostgreSQL Configuration** (20-35%)
   - Configure Docker network access
   - Set listen_addresses for network connections
   - Restart PostgreSQL

3. **Database User Setup** (35-55%)
   - Create three database users with CREATEDB privilege
   - Users will be able to create their own databases through Odoo

4. **Directory Structure** (55-65%)
   - Create base directories
   - Set ownership to Odoo container user (UID 100/GID 101)
   - Set proper permissions

5. **Docker Setup** (65-75%)
   - Pull Odoo Docker image
   - Generate docker-compose.yml

6. **Nginx Configuration** (75-95%)
   - Generate nginx.conf with SSL or HTTP
   - Create symlinks
   - Test and reload configuration

7. **Container Startup** (95-100%)
   - Start all three Odoo containers
   - Verify containers are running

## Post-Installation

### Accessing Your Odoo Instances

After installation completes, access your environments:

**With SSL:**
- Test: https://test.example.com
- Staging: https://staging.example.com
- Production: https://odoo.example.com

**Without SSL:**
- Test: http://test.example.com
- Staging: http://staging.example.com
- Production: http://odoo.example.com

### First-Time Database Initialization

**Important:** The installer creates PostgreSQL users but NOT the databases themselves. Odoo will create and initialize the databases when you first access it.

1. Navigate to your Odoo URL (e.g., https://odoo.example.com)
2. You'll see Odoo's database creation form. Fill it in:
   - **Master Password**: Create a new master password for Odoo (this is NOT your PostgreSQL password)
   - **Database Name**: Enter the database name you configured in the installer (e.g., `odoo_prod_db`)
   - **Email**: Your admin email
   - **Password**: Admin password for Odoo
   - **Language**: Choose your language
   - **Country**: Choose your country
   - **Demo Data**: Uncheck unless you want sample data
3. Click "Create Database"
4. Odoo will create the database with all required tables and initialize it properly
5. You'll be logged in as the administrator

**Note:** You don't need to manually create the database in PostgreSQL. Odoo handles this automatically using the database user credentials provided during installation.

### Managing Docker Containers

```bash
# View running containers
docker ps

# Stop all containers
cd /srv/odoo && docker compose stop

# Start all containers
cd /srv/odoo && docker compose start

# Restart all containers
cd /srv/odoo && docker compose restart

# View logs
docker logs odoo-test
docker logs odoo-staging
docker logs odoo-prod

# Access container shell
docker exec -it odoo-test /bin/bash
```

### Checking Services

```bash
# Check Docker status
systemctl status docker

# Check PostgreSQL status
systemctl status postgresql

# Check Nginx status
systemctl status nginx

# Test Nginx configuration
nginx -t

# Reload Nginx
systemctl reload nginx
```

## Security Considerations

### Installer Security

- **Root Access Required**: The installer needs root to install packages and configure services
- **Credential Storage**: Installation credentials saved to /root/odoo-installation-credentials.json (mode 0600)
- **Secure Password Generation**: All passwords generated using cryptographically secure methods

### Post-Installation Security

1. **Firewall Configuration**:
   ```bash
   # Allow only necessary ports
   ufw allow 80/tcp    # HTTP
   ufw allow 443/tcp   # HTTPS
   ufw allow 22/tcp    # SSH
   ufw enable
   ```

2. **SSL Certificates**:
   - Use Let's Encrypt for free SSL certificates
   - Keep certificates renewed (set up auto-renewal)

3. **Database Security**:
   - Store database passwords securely
   - Don't expose PostgreSQL port to internet
   - Use strong master passwords in Odoo

4. **Regular Updates**:
   - Update system packages regularly
   - Update Docker images
   - Monitor Odoo security announcements

## Troubleshooting

### Installer Won't Start

**Problem**: `This installer must be run as root`
```bash
# Solution: Run with sudo or as root
sudo python3 cli_installer.py
```

**Problem**: Dependencies (Rich, Questionary) not found
```bash
# Solution: The installer auto-installs dependencies
# If it fails, install manually:
pip3 install rich questionary
# Or use apt:
apt-get install python3-rich python3-questionary
```

### Installation Failures

**Problem**: Docker installation fails
```bash
# Check if Docker repo is accessible
curl -fsSL https://download.docker.com/linux/ubuntu/gpg

# Check internet connection
ping google.com

# View detailed logs
tail -f /var/log/odoo-installer.log
```

**Problem**: PostgreSQL connection fails
```bash
# Check PostgreSQL is running
systemctl status postgresql

# Test local connection
sudo -u postgres psql -c "SELECT version();"

# Check listen_addresses
sudo grep listen_addresses /etc/postgresql/*/main/postgresql.conf
```

**Problem**: Port already in use
```bash
# Check what's using a port
sudo netstat -tlnp | grep :8069

# Or with lsof
sudo lsof -i :8069

# Stop the conflicting service or choose different ports
```

### Container Issues

**Problem**: Containers won't start
```bash
# Check container logs
docker logs odoo-test

# Check docker-compose.yml syntax
cd /srv/odoo && docker compose config

# Restart Docker service
systemctl restart docker

# Try starting manually
cd /srv/odoo && docker compose up
```

**Problem**: Can't connect to database from container
```bash
# Check pg_hba.conf includes Docker networks
sudo grep "172.16.0.0" /etc/postgresql/*/main/pg_hba.conf

# Check PostgreSQL is listening
sudo netstat -tlnp | grep 5432

# Test connection from host
PGPASSWORD='test_password' psql -h localhost -U odoo_test -d odoo_test_db
```

### Nginx Issues

**Problem**: 502 Bad Gateway
```bash
# Check if Odoo containers are running
docker ps | grep odoo

# Check Nginx error logs
tail -f /var/log/nginx/error.log

# Test backend connection
curl http://localhost:8069
```

**Problem**: SSL certificate errors
```bash
# Verify certificate files exist
ls -l /etc/letsencrypt/live/your-domain.com/

# Check certificate permissions
sudo chmod 644 /etc/letsencrypt/live/your-domain.com/fullchain.pem
sudo chmod 600 /etc/letsencrypt/live/your-domain.com/privkey.pem

# Test Nginx config
nginx -t

# Check Nginx error logs
tail -f /var/log/nginx/error.log
```

### DNS Issues

**Problem**: Domain doesn't resolve
```bash
# Check DNS records
dig your-domain.com
nslookup your-domain.com

# Test local resolution
ping your-domain.com

# Add to /etc/hosts for testing (temporary)
echo "YOUR_IP your-domain.com" | sudo tee -a /etc/hosts
```

## File Locations

### Generated Files
- `/srv/odoo/docker-compose.yml` - Docker Compose configuration
- `/etc/nginx/sites-available/odoo` - Nginx configuration
- `/etc/nginx/sites-enabled/odoo` - Nginx config symlink

### Logs
- `/var/log/odoo-installer.log` - Installer logs
- `/var/log/nginx/access.log` - Nginx access logs
- `/var/log/nginx/error.log` - Nginx error logs
- Docker logs: `docker logs odoo-{test|staging|prod}`

### Data Directories
- `/srv/odoo/test/addons` - Test custom modules
- `/srv/odoo/test/filestore` - Test file storage
- `/srv/odoo/staging/addons` - Staging custom modules
- `/srv/odoo/staging/filestore` - Staging file storage
- `/srv/odoo/prod/addons` - Production custom modules
- `/srv/odoo/prod/filestore` - Production file storage

### Backups
Configuration files are backed up before modification:
- `/etc/postgresql/*/main/pg_hba.conf.backup_TIMESTAMP`
- `/etc/postgresql/*/main/postgresql.conf.backup_TIMESTAMP`
- `/etc/nginx/sites-available/odoo.backup_TIMESTAMP`
- `/srv/odoo/docker-compose.yml.backup_TIMESTAMP`

## Advanced Usage

### Custom Module Installation

Add custom modules to the addons directory:

```bash
# Copy your module to addons directory
cp -r /path/to/your_module /srv/odoo/prod/addons/

# Set correct ownership (UID 100 = odoo user in container)
chown -R 100:101 /srv/odoo/prod/addons/your_module

# Restart container
docker restart odoo-prod

# Update module list in Odoo
# Go to Apps → Update Apps List
```

### Database Backup

```bash
# Backup production database
PGPASSWORD='prod_password' pg_dump -U odoo_prod -h localhost odoo_prod_db > backup.sql

# Restore database
PGPASSWORD='prod_password' psql -U odoo_prod -h localhost odoo_prod_db < backup.sql
```

### Upgrading Odoo Version

```bash
# 1. Backup everything first
cd /srv/odoo
docker compose down
tar -czf odoo-backup-$(date +%Y%m%d).tar.gz test staging prod

# 2. Update docker-compose.yml with new version
sed -i 's/odoo:17.0/odoo:18.0/g' docker-compose.yml

# 3. Pull new image
docker compose pull

# 4. Start containers
docker compose up -d
```

## Support

### Documentation
- [Odoo Documentation](https://www.odoo.com/documentation)
- [Docker Documentation](https://docs.docker.com/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

### Common Commands Reference

```bash
# View installer logs
tail -f /var/log/odoo-installer.log

# Check all services
systemctl status docker postgresql nginx

# Restart Odoo containers
cd /srv/odoo && docker compose restart

# View container logs
docker logs -f odoo-prod

# Access Odoo shell
docker exec -it odoo-prod odoo shell

# Test Nginx config
nginx -t && systemctl reload nginx

# Check disk space
df -h

# Monitor resources
htop
```

## License

This installer is provided as-is for deploying Odoo in multi-environment setups.

## Changelog

### Version 2.0.2-CLI (Current)
- CLI-only installer (Flask-based web installer removed)
- Support for Odoo versions 14.0 - 19.0
- Multi-environment setup (test, staging, production)
- Interactive CLI with Rich and Questionary
- Dry-run mode
- SSL/HTTPS support
- Automated Docker, PostgreSQL, and Nginx installation
- Real-time installation progress monitoring
- Credential saved to JSON file
- Auto-dependency installation with 3-tier fallback

---

**Made with ❤️ for simplified Odoo deployments**
