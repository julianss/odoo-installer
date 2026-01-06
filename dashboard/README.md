# Odoo Management Dashboard - Phase 1

A Flask-based web dashboard for managing Odoo Docker environments.

## Phase 1: Container Management ✅

**Features Implemented:**
- ✅ Container status display (running/stopped/uptime)
- ✅ Start/stop/restart controls for each environment
- ✅ Resource statistics (CPU/Memory/Network I/O)
- ✅ Auto-refresh every 10 seconds
- ✅ Confirmation dialogs for production operations
- ✅ HTTP Basic Authentication
- ✅ Responsive UI with Tailwind CSS

## Installation

### 1. Install Dependencies

```bash
cd dashboard
pip3 install -r requirements.txt
```

Or install system-wide with sudo:

```bash
cd dashboard
sudo pip3 install -r requirements.txt
```

### 2. Run the Dashboard

**Development Mode:**
```bash
cd dashboard
python3 dashboard.py
```

**Production Mode (as root):**
```bash
cd dashboard
sudo python3 dashboard.py
```

The dashboard will be available at: **http://localhost:9998**

### 3. Login Credentials

**Default credentials:**
- Username: `admin`
- Password: `admin`

⚠️ **IMPORTANT:** These are temporary credentials for Phase 1. They will be configurable in Phase 6.

## Usage

### Container Management

The dashboard home page displays three container cards (Test, Staging, Production):

**Each card shows:**
- Environment name and status (running/stopped)
- Container ID
- Uptime (for running containers)
- CPU usage
- Memory usage
- Network I/O

**Available actions:**
- **Start** - Start a stopped container
- **Stop** - Stop a running container (requires confirmation for production)
- **Restart** - Restart a running container (requires confirmation for production)
- **View Logs** - Navigate to log viewer (Phase 2 feature)

### API Endpoints

All API endpoints require HTTP Basic Authentication.

#### Get All Container Status
```bash
GET /api/containers/status
```

Returns status for all three environments.

#### Get Single Container Status
```bash
GET /api/containers/<env>/status
```

Where `<env>` is `test`, `staging`, or `prod`.

#### Start Container
```bash
POST /api/containers/<env>/start
```

#### Stop Container
```bash
POST /api/containers/<env>/stop
```

#### Restart Container
```bash
POST /api/containers/<env>/restart
```

#### Get Container Stats
```bash
GET /api/containers/<env>/stats
```

### Example API Usage

```bash
# Get all container status
curl -u admin:admin http://localhost:9998/api/containers/status

# Start test environment
curl -u admin:admin -X POST http://localhost:9998/api/containers/test/start

# Stop staging environment
curl -u admin:admin -X POST http://localhost:9998/api/containers/staging/stop

# Restart production environment
curl -u admin:admin -X POST http://localhost:9998/api/containers/prod/restart
```

## Directory Structure

```
dashboard/
├── dashboard.py                # Main Flask application
├── config.py                   # Configuration management
├── requirements.txt            # Python dependencies
├── services/
│   ├── __init__.py
│   └── container_service.py   # Docker container operations
├── templates/
│   ├── base.html              # Base layout with navbar
│   └── index.html             # Container status page
├── static/
│   ├── css/
│   │   └── dashboard.css      # Custom styles
│   └── js/
│       └── containers.js      # Container management UI
└── data/
    └── dashboard.log          # Application logs
```

## Configuration

### Port Configuration

Default port is **9998**. To change:

```bash
DASHBOARD_PORT=8080 python3 dashboard.py
```

### Paths

The dashboard expects Odoo to be installed at `/srv/odoo` with the following structure:

```
/srv/odoo/
├── docker-compose.yml
├── test/
├── staging/
└── prod/
```

These paths can be modified in `config.py`.

## Troubleshooting

### Dashboard won't start

**Error:** `ModuleNotFoundError: No module named 'flask'`
- **Solution:** Install dependencies: `pip3 install -r requirements.txt`

**Error:** `Permission denied`
- **Solution:** Run with sudo: `sudo python3 dashboard.py`

### Containers not showing

**Error:** Containers show as "not_found"
- **Cause:** Docker containers don't exist or are named differently
- **Solution:** Verify containers exist: `docker ps -a | grep odoo`
- **Expected names:** `odoo-test`, `odoo-staging`, `odoo-prod`

**Error:** `Cannot connect to the Docker daemon`
- **Cause:** Docker is not running or insufficient permissions
- **Solution:**
  - Check Docker is running: `sudo systemctl status docker`
  - Add user to docker group: `sudo usermod -aG docker $USER` (then logout/login)
  - Or run dashboard as root: `sudo python3 dashboard.py`

### Stats not showing

**Issue:** CPU/Memory stats show as "N/A"
- **Cause:** Container is stopped or Docker stats failed
- **Solution:** Start the container and refresh the page

## Logging

Logs are written to:
- **Console:** Standard output
- **File:** `dashboard/data/dashboard.log`

View logs in real-time:
```bash
tail -f dashboard/data/dashboard.log
```

## Development

### Enable Debug Mode

Edit `dashboard.py` and change:
```python
app.run(debug=True, ...)
```

This enables:
- Auto-reload on code changes
- Detailed error pages
- Interactive debugger

### Testing Without Docker

The dashboard gracefully handles missing containers by showing "not_found" status.

## Next Steps (Upcoming Phases)

- **Phase 2:** Log Viewer (real-time log streaming with SSE)
- **Phase 3:** Git Repository Management (clone/pull repos)
- **Phase 4:** Backup System (create and upload backups)
- **Phase 5:** Scheduled Backups (automated cron jobs)
- **Phase 6:** Settings & Polish (configurable auth, systemd service)

## Security Notes

⚠️ **Phase 1 Security Limitations:**
- Default credentials (`admin/admin`) are hardcoded
- HTTP only (no HTTPS)
- No audit logging
- No rate limiting

These will be addressed in Phase 6.

## Support

For issues related to:
- **Dashboard:** Check logs in `dashboard/data/dashboard.log`
- **Docker:** Run `docker logs odoo-<env>`
- **Installation:** Review the main installer README

## License

Part of the Odoo Multi-Environment Docker Installer project.
