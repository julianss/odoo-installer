#!/usr/bin/env python3
"""
Odoo Management Dashboard
A Flask-based web dashboard for managing Odoo Docker environments
"""

import os
import sys
import logging
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, jsonify, request, Response, stream_with_context

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from services import container_service
from services import log_service
from services import git_service
from services import backup_service
from services import scheduler_service

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(config.DATA_DIR, 'dashboard.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('odoo_dashboard')

# Ensure data directory exists
config.ensure_data_dir()


# ============================================================================
# Authentication (HTTP Basic Auth - same as installer)
# ============================================================================

# Simple in-memory auth store (credentials can be changed via settings)
_auth_config = {'username': 'admin', 'password': 'admin'}


def check_auth(username, password):
    """Check if username/password combination is valid."""
    return username == _auth_config.get('username', 'admin') and password == _auth_config.get('password', 'admin')


def authenticate():
    """Send 401 response for authentication."""
    return Response(
        'Authentication required\n',
        401,
        {'WWW-Authenticate': 'Basic realm="Odoo Dashboard"'}
    )


def requires_auth(f):
    """Decorator to require HTTP Basic Auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


# ============================================================================
# Web Routes
# ============================================================================

@app.route('/')
@requires_auth
def index():
    """Dashboard home page - container status."""
    return render_template('index.html')


@app.route('/logs')
@requires_auth
def logs():
    """Log viewer page."""
    # Get selected environment from query params, default to first available
    selected_env = request.args.get('env', config.ENVIRONMENTS[0] if config.ENVIRONMENTS else 'test')
    return render_template('logs.html', environments=config.ENVIRONMENTS, selected_env=selected_env)


@app.route('/git')
@requires_auth
def git():
    """Git repository management page."""
    selected_env = request.args.get('env', config.ENVIRONMENTS[0] if config.ENVIRONMENTS else 'test')
    return render_template('git.html', environments=config.ENVIRONMENTS, selected_env=selected_env)


@app.route('/backups')
@requires_auth
def backups():
    """Backup management page."""
    selected_env = request.args.get('env', config.ENVIRONMENTS[0] if config.ENVIRONMENTS else 'test')
    return render_template('backups.html', environments=config.ENVIRONMENTS, selected_env=selected_env)


@app.route('/settings')
@requires_auth
def settings():
    """Settings page."""
    return render_template('settings.html',
                           version=config.APP_VERSION,
                           odoo_base_dir=config.ODOO_BASE_DIR,
                           environments=config.ENVIRONMENTS,
                           port=config.APP_PORT,
                           data_dir=config.DATA_DIR)


# ============================================================================
# API Routes - Container Management
# ============================================================================

@app.route('/api/containers/status')
@requires_auth
def api_container_status():
    """Get status of all containers."""
    try:
        statuses = container_service.get_all_container_status()
        return jsonify(statuses)
    except Exception as e:
        logger.error(f"Error getting container status: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/containers/<env>/status')
@requires_auth
def api_single_container_status(env):
    """Get status of a single container."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        status = container_service.get_container_status(env)
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting {env} container status: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/containers/<env>/start', methods=['POST'])
@requires_auth
def api_start_container(env):
    """Start a container."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        logger.info(f"Starting {env} container")
        result = container_service.start_container(env)

        if result['success']:
            logger.info(f"Successfully started {env} container")
        else:
            logger.warning(f"Failed to start {env} container: {result['message']}")

        return jsonify(result)
    except Exception as e:
        logger.error(f"Error starting {env} container: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/containers/<env>/stop', methods=['POST'])
@requires_auth
def api_stop_container(env):
    """Stop a container."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        logger.info(f"Stopping {env} container")
        result = container_service.stop_container(env)

        if result['success']:
            logger.info(f"Successfully stopped {env} container")
        else:
            logger.warning(f"Failed to stop {env} container: {result['message']}")

        return jsonify(result)
    except Exception as e:
        logger.error(f"Error stopping {env} container: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/containers/<env>/restart', methods=['POST'])
@requires_auth
def api_restart_container(env):
    """Restart a container."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        logger.info(f"Restarting {env} container")
        result = container_service.restart_container(env)

        if result['success']:
            logger.info(f"Successfully restarted {env} container")
        else:
            logger.warning(f"Failed to restart {env} container: {result['message']}")

        return jsonify(result)
    except Exception as e:
        logger.error(f"Error restarting {env} container: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/containers/<env>/stats')
@requires_auth
def api_container_stats(env):
    """Get container resource statistics."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        stats = container_service.get_container_stats(env)
        if stats is None:
            return jsonify({'error': 'Could not retrieve stats'}), 404
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting {env} container stats: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API Routes - Log Management
# ============================================================================

@app.route('/api/logs/<env>')
@requires_auth
def api_get_logs(env):
    """Get last N lines of container logs."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        lines = request.args.get('lines', 100, type=int)
        lines = min(max(lines, 1), 10000)  # Limit between 1 and 10000

        timestamps = request.args.get('timestamps', 'false').lower() == 'true'
        level = request.args.get('level')  # Optional log level filter
        search = request.args.get('search')  # Optional search filter

        result = log_service.get_logs(env, lines=lines, timestamps=timestamps)

        if not result['success']:
            return jsonify(result), 500

        # Apply filters if specified
        if level or search:
            result['logs'] = log_service.filter_logs(result['logs'], level=level, search=search)

        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting {env} logs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs/<env>/stream')
@requires_auth
def api_stream_logs(env):
    """Server-Sent Events endpoint for log streaming."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    tail = request.args.get('tail', 50, type=int)
    tail = min(max(tail, 1), 500)  # Limit between 1 and 500

    def generate():
        try:
            for log_line in log_service.stream_logs(env, tail=tail):
                yield log_line
        except GeneratorExit:
            logger.info(f"Client disconnected from {env} log stream")
        except Exception as e:
            logger.error(f"Error in {env} log stream: {e}")
            yield f"data: [ERROR] Log stream error: {e}\n\n"

    logger.info(f"Starting log stream for {env}")

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # Disable nginx buffering
            'Connection': 'keep-alive'
        }
    )


@app.route('/api/logs/<env>/download')
@requires_auth
def api_download_logs(env):
    """Download container logs as text file."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        lines = request.args.get('lines', 1000, type=int)
        lines = min(max(lines, 1), 50000)  # Allow up to 50000 lines for download

        content = log_service.get_logs_download(env, lines=lines, timestamps=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"odoo-{env}-logs-{timestamp}.txt"

        return Response(
            content,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Error downloading {env} logs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/logs/<env>/stats')
@requires_auth
def api_log_stats(env):
    """Get log statistics for an environment."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        stats = log_service.get_log_stats(env)
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting {env} log stats: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API Routes - Git Repository Management
# ============================================================================

@app.route('/api/repos')
@requires_auth
def api_get_all_repos():
    """Get all repositories across all environments."""
    try:
        repos = git_service.get_all_repos_status()
        return jsonify(repos)
    except Exception as e:
        logger.error(f"Error getting all repos: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/repos/<env>')
@requires_auth
def api_get_repos(env):
    """Get repositories for a specific environment."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        repos = git_service.list_repositories(env)
        return jsonify(repos)
    except Exception as e:
        logger.error(f"Error getting {env} repos: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/repos/<env>/add', methods=['POST'])
@requires_auth
def api_add_repo(env):
    """Clone a new repository."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        url = data.get('url', '').strip()
        dirname = data.get('dirname', '').strip()
        branch = data.get('branch', 'main').strip() or 'main'
        name = data.get('name', '').strip() or None
        auto_restart = data.get('auto_restart', True)

        # Validate URL
        if not git_service.validate_git_url(url):
            return jsonify({'error': 'Invalid git URL format'}), 400

        # Validate directory name
        valid, error = git_service.validate_dirname(dirname)
        if not valid:
            return jsonify({'error': error}), 400

        logger.info(f"Cloning repository {url} to {env}/{dirname}")
        repo_id = git_service.clone_repository(
            env=env,
            url=url,
            dirname=dirname,
            branch=branch,
            name=name,
            auto_restart=auto_restart
        )

        logger.info(f"Successfully cloned repository: {repo_id}")
        return jsonify({'success': True, 'repo_id': repo_id})

    except ValueError as e:
        logger.warning(f"Clone failed for {env}: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error cloning repository to {env}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/repos/<env>/<repo_id>/status')
@requires_auth
def api_repo_status(env, repo_id):
    """Get detailed status of a repository."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        status = git_service.get_repo_status(env, repo_id)
        return jsonify(status)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error getting status for {repo_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/repos/<env>/<repo_id>/pull', methods=['POST'])
@requires_auth
def api_pull_repo(env, repo_id):
    """Pull latest changes from remote."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        logger.info(f"Pulling repository {repo_id} in {env}")
        result = git_service.pull_repository(env, repo_id)

        # Auto-restart container if enabled and commits were pulled
        if result.get('auto_restart') and result.get('commits_pulled', 0) > 0:
            logger.info(f"Auto-restarting {env} container after pull")
            restart_result = container_service.restart_container(env)
            result['container_restarted'] = restart_result.get('success', False)

        return jsonify(result)

    except ValueError as e:
        logger.warning(f"Pull failed for {repo_id}: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error pulling {repo_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/repos/<env>/<repo_id>', methods=['DELETE'])
@requires_auth
def api_delete_repo(env, repo_id):
    """Remove repository from registry."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        delete_files = request.args.get('delete_files', 'false').lower() == 'true'

        logger.info(f"Removing repository {repo_id} from {env} (delete_files={delete_files})")
        success = git_service.remove_repository(env, repo_id, delete_files=delete_files)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Repository not found'}), 404

    except Exception as e:
        logger.error(f"Error removing {repo_id}: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API Routes - Backup Management
# ============================================================================

@app.route('/api/backups')
@requires_auth
def api_list_all_backups():
    """List all backups across all environments."""
    try:
        backups = backup_service.list_backups()
        return jsonify(backups)
    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/<env>')
@requires_auth
def api_list_backups(env):
    """List backups for a specific environment."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        backups = backup_service.list_backups(env)
        return jsonify(backups)
    except Exception as e:
        logger.error(f"Error listing {env} backups: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/<env>/create', methods=['POST'])
@requires_auth
def api_create_backup(env):
    """Create a new backup."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        data = request.get_json() or {}
        backup_type = data.get('type', 'full')
        description = data.get('description', '')
        upload = data.get('upload', False)

        logger.info(f"Creating {backup_type} backup for {env}")

        result = backup_service.create_backup(
            env=env,
            backup_type=backup_type,
            description=description
        )

        logger.info(f"Backup created: {result['backup_id']}")

        # Upload if requested
        if upload:
            try:
                upload_result = backup_service.upload_backup(result['backup_id'], env)
                result['upload'] = upload_result
            except Exception as e:
                logger.warning(f"Upload failed: {e}")
                result['upload'] = {'uploaded': False, 'error': str(e)}

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error creating backup for {env}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/<env>/<backup_id>')
@requires_auth
def api_get_backup(env, backup_id):
    """Get details of a specific backup."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        details = backup_service.get_backup_details(env, backup_id)
        return jsonify(details)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error getting backup {backup_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/<env>/<backup_id>/download')
@requires_auth
def api_download_backup(env, backup_id):
    """Download a backup file."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        file_type = request.args.get('type', 'database')
        file_path = backup_service.get_backup_file_path(env, backup_id, file_type)

        if not file_path:
            return jsonify({'error': 'Backup file not found'}), 404

        from flask import send_file
        return send_file(
            file_path,
            as_attachment=True,
            download_name=os.path.basename(file_path)
        )

    except Exception as e:
        logger.error(f"Error downloading backup {backup_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/<env>/<backup_id>/upload', methods=['POST'])
@requires_auth
def api_upload_backup(env, backup_id):
    """Upload a backup to remote storage."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        logger.info(f"Uploading backup {backup_id} to remote storage")
        result = backup_service.upload_backup(backup_id, env)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error uploading backup {backup_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/<env>/<backup_id>', methods=['DELETE'])
@requires_auth
def api_delete_backup(env, backup_id):
    """Delete a backup."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        logger.info(f"Deleting backup {backup_id}")
        success = backup_service.delete_backup(env, backup_id)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Backup not found'}), 404

    except Exception as e:
        logger.error(f"Error deleting backup {backup_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/config')
@requires_auth
def api_get_backup_config():
    """Get backup configuration."""
    try:
        backup_config = config.load_backup_config()
        # Remove secret key from response for security
        if 's3' in backup_config and 'secret_key' in backup_config['s3']:
            backup_config['s3']['secret_key'] = ''
        return jsonify(backup_config)
    except Exception as e:
        logger.error(f"Error getting backup config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/config', methods=['POST'])
@requires_auth
def api_save_backup_config():
    """Save backup configuration."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Load existing config to preserve secret key if not provided
        existing_config = config.load_backup_config()

        # Preserve existing secret key if new one is empty
        if 's3' in data and not data['s3'].get('secret_key'):
            data['s3']['secret_key'] = existing_config.get('s3', {}).get('secret_key', '')

        logger.info("Saving backup configuration")
        config.save_backup_config(data)

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error saving backup config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/test-s3', methods=['POST'])
@requires_auth
def api_test_s3():
    """Test S3 connection."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = backup_service.test_s3_connection(data)
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error testing S3 connection: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/backups/test-rsync', methods=['POST'])
@requires_auth
def api_test_rsync():
    """Test rsync connection."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = backup_service.test_rsync_connection(data)
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error testing rsync connection: {e}")
        return jsonify({'success': False, 'message': str(e)})


# ============================================================================
# API Routes - Database Copy
# ============================================================================

@app.route('/api/databases/info')
@requires_auth
def api_get_database_info():
    """Get database info for all environments."""
    try:
        info = {}
        for env in config.ENVIRONMENTS:
            info[env] = backup_service.get_database_info(env)
        return jsonify(info)
    except Exception as e:
        logger.error(f"Error getting database info: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/databases/copy', methods=['POST'])
@requires_auth
def api_copy_database():
    """Copy database between environments."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        source_env = data.get('source_env')
        target_env = data.get('target_env')
        include_filestore = data.get('include_filestore', True)
        include_addons = data.get('include_addons', True)
        target_db_name = data.get('target_db_name')  # Optional: name for new database

        if not source_env or not target_env:
            return jsonify({'error': 'source_env and target_env are required'}), 400

        if source_env not in config.ENVIRONMENTS:
            return jsonify({'error': f'Invalid source environment: {source_env}'}), 400

        if target_env not in config.ENVIRONMENTS:
            return jsonify({'error': f'Invalid target environment: {target_env}'}), 400

        logger.warning(f"DESTRUCTIVE: Copying database from {source_env} to {target_env}" +
                      (f" (new db name: {target_db_name})" if target_db_name else ""))

        result = backup_service.copy_database(
            source_env=source_env,
            target_env=target_env,
            include_filestore=include_filestore,
            include_addons=include_addons,
            target_db_name=target_db_name
        )

        if result['success']:
            logger.info(f"Database copy completed: {source_env} -> {target_env}")
        else:
            logger.error(f"Database copy failed: {result.get('errors')}")

        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error copying database: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API Routes - Backup Schedules
# ============================================================================

@app.route('/api/schedules')
@requires_auth
def api_get_schedules():
    """Get all backup schedules and job info."""
    try:
        schedules = scheduler_service.get_all_schedules()
        jobs = scheduler_service.get_scheduled_jobs()

        return jsonify({
            'schedules': schedules,
            'jobs': jobs
        })
    except Exception as e:
        logger.error(f"Error getting schedules: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/schedules/<env>')
@requires_auth
def api_get_schedule(env):
    """Get schedule for a specific environment."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        schedule = scheduler_service.get_schedule(env)
        job_info = scheduler_service.get_job_info(env)

        return jsonify({
            'schedule': schedule,
            'job': job_info
        })
    except Exception as e:
        logger.error(f"Error getting schedule for {env}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/schedules/<env>', methods=['POST'])
@requires_auth
def api_save_schedule(env):
    """Save schedule for an environment."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        logger.info(f"Saving schedule for {env}: enabled={data.get('enabled')}")
        scheduler_service.save_schedule(env, data)

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error saving schedule for {env}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/schedules/<env>/trigger', methods=['POST'])
@requires_auth
def api_trigger_backup(env):
    """Manually trigger a backup for an environment."""
    if env not in config.ENVIRONMENTS:
        return jsonify({'error': 'Invalid environment'}), 400

    try:
        logger.info(f"Manually triggering backup for {env}")
        result = scheduler_service.trigger_backup_now(env)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error triggering backup for {env}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/schedules/history')
@requires_auth
def api_get_backup_history():
    """Get backup history from audit log."""
    try:
        env = request.args.get('env')
        limit = request.args.get('limit', 50, type=int)

        history = scheduler_service.get_backup_history(env=env, limit=limit)

        return jsonify(history)
    except Exception as e:
        logger.error(f"Error getting backup history: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API Routes - Settings
# ============================================================================

@app.route('/api/settings/auth', methods=['POST'])
@requires_auth
def api_save_auth():
    """Save authentication settings."""
    global _auth_config

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        username = data.get('username', '').strip()
        password = data.get('password')

        if not username:
            return jsonify({'error': 'Username is required'}), 400

        _auth_config['username'] = username
        if password:
            _auth_config['password'] = password

        # Log the change
        log_audit_event('auth', 'credentials_changed', f'Username: {username}')

        logger.info(f"Auth credentials updated: username={username}")
        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error saving auth settings: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/audit')
@requires_auth
def api_get_audit_log():
    """Get audit log entries."""
    try:
        category = request.args.get('category')
        limit = request.args.get('limit', 100, type=int)

        audit_file = os.path.join(config.DATA_DIR, 'audit.log')
        logs = []

        if os.path.exists(audit_file):
            with open(audit_file, 'r') as f:
                lines = f.readlines()

            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue

                try:
                    parts = line.split(' | ')
                    if len(parts) >= 3:
                        entry = {
                            'timestamp': parts[0],
                            'category': parts[1],
                            'action': parts[2],
                            'details': parts[3] if len(parts) > 3 else ''
                        }

                        if category and entry['category'] != category:
                            continue

                        logs.append(entry)

                        if len(logs) >= limit:
                            break
                except Exception:
                    continue

        return jsonify(logs)

    except Exception as e:
        logger.error(f"Error getting audit log: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/restart-all', methods=['POST'])
@requires_auth
def api_restart_all():
    """Restart all containers."""
    try:
        logger.warning("Restarting all containers")
        results = {}

        for env in config.ENVIRONMENTS:
            result = container_service.restart_container(env)
            results[env] = result.get('success', False)

        log_audit_event('container', 'restart_all', f'Results: {results}')

        return jsonify({'success': True, 'results': results})

    except Exception as e:
        logger.error(f"Error restarting containers: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/cleanup-backups', methods=['POST'])
@requires_auth
def api_cleanup_backups():
    """Cleanup old backups."""
    try:
        data = request.get_json()
        days = data.get('days', 7) if data else 7

        total_deleted = 0

        for env in config.ENVIRONMENTS:
            deleted = backup_service.cleanup_old_backups(env, days)
            total_deleted += deleted

        log_audit_event('backup', 'cleanup', f'Deleted {total_deleted} backups older than {days} days')
        logger.info(f"Cleaned up {total_deleted} old backups")

        return jsonify({'success': True, 'deleted': total_deleted})

    except Exception as e:
        logger.error(f"Error cleaning up backups: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/logs/dashboard/download')
@requires_auth
def api_download_dashboard_logs():
    """Download dashboard logs."""
    try:
        log_file = os.path.join(config.DATA_DIR, 'dashboard.log')

        if not os.path.exists(log_file):
            return jsonify({'error': 'Log file not found'}), 404

        from flask import send_file
        return send_file(
            log_file,
            as_attachment=True,
            download_name=f'dashboard-{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        )

    except Exception as e:
        logger.error(f"Error downloading dashboard logs: {e}")
        return jsonify({'error': str(e)}), 500


def log_audit_event(category, action, details=''):
    """Log an event to the audit log."""
    audit_file = os.path.join(config.DATA_DIR, 'audit.log')

    try:
        timestamp = datetime.now().isoformat()

        with open(audit_file, 'a') as f:
            f.write(f"{timestamp} | {category} | {action} | {details}\n")
    except IOError as e:
        logger.warning(f"Failed to write audit log: {e}")


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the dashboard."""
    print("=" * 60)
    print("Odoo Management Dashboard")
    print("=" * 60)
    print(f"Version: {config.APP_VERSION}")
    print(f"Port: {config.APP_PORT}")
    print(f"Data Directory: {config.DATA_DIR}")
    print(f"Odoo Base Directory: {config.ODOO_BASE_DIR}")
    print(f"Docker Compose: {config.DOCKER_COMPOSE_FILE}")
    print(f"Environments: {', '.join(config.ENVIRONMENTS)}")
    print("=" * 60)
    print()
    print("IMPORTANT: Default credentials are admin/admin")
    print("Please change these in production!")
    print()
    print(f"Dashboard will be available at: http://localhost:{config.APP_PORT}")
    print()
    print("Press Ctrl+C to stop the dashboard")
    print("=" * 60)

    # Initialize the backup scheduler
    try:
        scheduler_service.init_scheduler()
        print("Backup scheduler initialized")
    except Exception as e:
        logger.warning(f"Could not initialize scheduler: {e}")

    try:
        app.run(
            host='0.0.0.0',
            port=config.APP_PORT,
            debug=False,  # Set to True for development
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n\nShutting down dashboard...")
        scheduler_service.shutdown_scheduler()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error starting dashboard: {e}")
        scheduler_service.shutdown_scheduler()
        sys.exit(1)


if __name__ == '__main__':
    main()
