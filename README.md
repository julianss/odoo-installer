# Odoo Multi-Environment Docker Installer

A comprehensive, single-file Python installer that automates the setup of Odoo across three isolated environments (Test, Staging, Production) using Docker, PostgreSQL, and Nginx.

## Features

- **🎯 Single-File Installer** - Everything embedded in one Python file
- **🔐 Secure Setup** - HTTP Basic Auth protection, auto-shutdown after inactivity
- **🖥️ Web-Based Wizard** - Modern, responsive 6-step configuration interface
- **🐳 Docker-Based** - Uses official Odoo Docker images
- **🔄 Multi-Environment** - Automatically configures test, staging, and production
- **✅ Idempotent** - Safe to run multiple times
- **🔍 Dry-Run Mode** - Preview changes before applying
- **📊 Real-Time Progress** - Live installation logs and progress tracking
- **🔒 SSL Support** - Automatic HTTPS configuration with your certificates

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
# Download installer.py to your server
wget https://your-server.com/installer.py

# Or copy it directly to your server
scp installer.py root@your-server:/root/
```

### 2. Run the Installer

```bash
# SSH into your server as root
ssh root@your-server

# Run the installer
python3 installer.py
```

### 3. Set Up Access Credentials

When prompted, create credentials for accessing the web installer:

```
Admin username: admin
Admin password: ********
```

These credentials are stored in memory only and never written to disk.

### 4. Access the Web Interface

The installer will display access information:

```
============================================================
  🌐 INSTALLER WEB UI IS READY
============================================================

  Access the installer at:
  → http://YOUR_SERVER_IP:9999
  → http://localhost:9999 (if local)

  Username: admin
  Password: (the password you just set)

  ⚠️  Auto-shutdown after 60 minutes of inactivity
  📝 Logs: /var/log/odoo-installer.log
============================================================
```

### 5. Complete the 6-Step Wizard

Navigate through the configuration wizard:

1. **Odoo Version** - Select version (14.0, 15.0, 16.0, 17.0, or 18.0)
2. **Database Configuration** - PostgreSQL credentials and database setup
3. **Domains & SSL** - Configure domains and SSL certificates
4. **Directory Structure** - Set base path for Odoo data
5. **Port Configuration** - Configure HTTP and long-polling ports
6. **Review & Install** - Review configuration and start installation

### 6. Download Credentials

After successful installation, download and save your credentials file containing:
- Database passwords
- Access URLs
- Port configurations

## Configuration Guide

### Step 1: Odoo Version

Choose the Odoo version you want to install:
- **14.0** (LTS) - Long Term Support
- **15.0**
- **16.0** (LTS) - Long Term Support
- **17.0** (Recommended)
- **18.0** (Latest)

All three environments will use the same version.

### Step 2: Database Configuration

**PostgreSQL Superuser Password**
- Password for the `postgres` user
- Required to create databases and users
- Must already be set on your PostgreSQL installation

**Database Names** (defaults provided):
- Test: `odoo_test_db`
- Staging: `odoo_staging_db`
- Production: `odoo_prod_db`

**Database Users** (defaults provided):
- Test: `odoo_test`
- Staging: `odoo_staging`
- Production: `odoo_prod`

**Database Passwords**:
- Click "Generate Secure Password" for each environment
- 24-character cryptographically secure passwords
- Displayed immediately for copying

### Step 3: Domain & SSL Configuration

**Domains**:
- Enter the FQDN for each environment
- Example: `test.example.com`, `staging.example.com`, `odoo.example.com`

**SSL Certificates** (optional):
- Provide paths to SSL certificate files
- Typically: `/etc/letsencrypt/live/your-domain.com/fullchain.pem`
- Private key: `/etc/letsencrypt/live/your-domain.com/privkey.pem`
- Check "Skip SSL configuration" for HTTP-only (testing)

### Step 4: Directory Structure

**Base Path** (default: `/srv/odoo`):
- All Odoo data will be stored here
- Subdirectories created automatically:
  - `/srv/odoo/test/addons` - Custom modules (test)
  - `/srv/odoo/test/filestore` - File storage (test)
  - `/srv/odoo/staging/addons` - Custom modules (staging)
  - `/srv/odoo/staging/filestore` - File storage (staging)
  - `/srv/odoo/prod/addons` - Custom modules (production)
  - `/srv/odoo/prod/filestore` - File storage (production)

### Step 5: Port Configuration

**HTTP Ports** (defaults):
- Test: `8069`
- Staging: `8070`
- Production: `8071`

**Long-Polling/WebSocket Ports** (defaults):
- Test: `8072`
- Staging: `8073`
- Production: `8074`

All ports must be:
- Between 1024 and 65535
- Unique (no duplicates)
- Available (not in use)

### Step 6: Review & Install

**Dry-Run Mode**:
- Check this box to preview changes without applying them
- Useful for:
  - Reviewing what will be installed
  - Checking configuration before committing
  - Educational purposes

**Start Installation**:
- Validates all configuration
- Shows real-time progress
- Displays live logs
- Reports completion status

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

3. **Database Setup** (35-55%)
   - Create three database users
   - Create three databases
   - Grant privileges

4. **Directory Structure** (55-65%)
   - Create base directories
   - Set ownership to Odoo container user (UID/GID 101)
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

1. Navigate to your Odoo URL
2. Fill in the database creation form:
   - Master Password: Create a new master password for Odoo
   - Database Name: Use the database created by installer
   - Email: Your admin email
   - Password: Admin password for Odoo
   - Language: Choose your language
   - Country: Choose your country

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
- **Auto-Shutdown**: Installer shuts down after 60 minutes of inactivity
- **Basic Auth**: Protected by HTTP Basic Authentication
- **Self-Destruct**: Renames itself to `.done` after completion
- **Memory-Only Credentials**: Web auth credentials stored in memory only

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
sudo python3 installer.py
```

**Problem**: `Flask not found`
```bash
# Solution: The installer will auto-install Flask
# If it fails, install manually:
pip3 install flask
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
sudo grep "172.17.0.0" /etc/postgresql/*/main/pg_hba.conf

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

# Set correct ownership
chown -R 101:101 /srv/odoo/prod/addons/your_module

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

### Version 1.0.0 (2025-12-06)
- Initial release
- Support for Odoo versions 14.0 - 18.0
- Multi-environment setup (test, staging, production)
- Web-based configuration wizard
- Dry-run mode
- SSL/HTTPS support
- Automated Docker, PostgreSQL, and Nginx installation
- Real-time installation progress monitoring
- Credential download feature
- Self-destruct after completion

---

**Made with ❤️ for simplified Odoo deployments**
