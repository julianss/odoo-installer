"""
Backup operations for Odoo Management Dashboard

Handles:
- Database backups (pg_dump)
- Filestore backups (tar.gz)
- Upload to S3-compatible storage
- Upload to rsync.net
- Database copy between environments
- Backup listing and deletion
"""

import os
import subprocess
import json
import gzip
import shutil
from datetime import datetime
import sys
import re

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


# ============================================================================
# Database Credential Functions
# ============================================================================

def get_db_credentials(env):
    """
    Extract PostgreSQL credentials from docker-compose.yml.

    Uses config.get_service_config() to dynamically discover service names
    rather than hardcoding them.

    Returns:
        dict: {'user': str, 'password': str, 'host': str, 'port': str}
    """
    # Use config's service discovery (same as Containers tab)
    service_config = config.get_service_config(env)

    if not service_config:
        raise ValueError(f"Environment {env} not found in docker-compose.yml")

    environment = service_config.get('environment', {})

    if not environment:
        raise ValueError(f"No environment variables found for {env} in docker-compose.yml")

    user = environment.get('USER', '')
    password = environment.get('PASSWORD', '')

    if not user:
        raise ValueError(f"USER not found in environment for {env}")

    if not password:
        raise ValueError(f"PASSWORD not found in environment for {env}")

    return {
        'user': user,
        'password': password,
        'host': 'localhost',  # Containers connect via host.docker.internal, we connect locally
        'port': environment.get('PORT', '5432'),
        'service_name': service_config.get('service_name'),
        'container_name': service_config.get('container_name')
    }


def discover_databases(env):
    """
    Discover databases owned by the Odoo user for an environment.

    Returns:
        list: List of database names
    """
    creds = get_db_credentials(env)

    if not creds['password']:
        raise ValueError(f"No password found for {env} environment")

    env_vars = os.environ.copy()
    env_vars['PGPASSWORD'] = creds['password']

    # Query PostgreSQL for databases owned by this user
    query = f"""
        SELECT datname
        FROM pg_database
        WHERE datdba = (SELECT usesysid FROM pg_user WHERE usename = '{creds['user']}')
        AND datname NOT IN ('postgres', 'template0', 'template1')
    """

    result = subprocess.run(
        ['psql', '-h', creds['host'], '-p', creds['port'], '-U', creds['user'],
         '-d', 'postgres', '-t', '-A', '-c', query],
        capture_output=True,
        text=True,
        env=env_vars
    )

    if result.returncode != 0:
        raise ValueError(f"Failed to query databases: {result.stderr}")

    databases = [db.strip() for db in result.stdout.strip().split('\n') if db.strip()]
    return databases


def get_primary_database(env):
    """Get the primary (or only) database for an environment."""
    databases = discover_databases(env)

    if not databases:
        raise ValueError(f"No database found for {env} environment")

    # If multiple databases, prefer one matching the environment name
    if len(databases) > 1:
        for db in databases:
            if env in db.lower():
                return db

    return databases[0]


# ============================================================================
# Backup Creation Functions
# ============================================================================

def create_backup(env, backup_type='full', description='', database_name=None):
    """
    Create database and/or filestore backup.

    Args:
        env: Environment name (test, staging, prod)
        backup_type: 'full', 'database', or 'filestore'
        description: Optional description
        database_name: Specific database name (auto-detected if not provided)

    Returns:
        dict: Backup result with backup_id, manifest, and file paths
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_id = f"{env}_{backup_type}_{timestamp}"
    env_backup_dir = os.path.join(config.BACKUP_DIR, env)

    os.makedirs(env_backup_dir, exist_ok=True)

    files = {}

    # Database backup
    if backup_type in ['full', 'database']:
        db_name = database_name or get_primary_database(env)
        db_file = os.path.join(env_backup_dir, f"{env}_db_{timestamp}.sql.gz")

        creds = get_db_credentials(env)

        env_vars = os.environ.copy()
        env_vars['PGPASSWORD'] = creds['password']

        # Use pg_dump with gzip compression
        with gzip.open(db_file, 'wb') as f:
            proc = subprocess.Popen(
                ['pg_dump', '-h', creds['host'], '-p', creds['port'],
                 '-U', creds['user'], '-d', db_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env_vars
            )

            for chunk in iter(lambda: proc.stdout.read(8192), b''):
                f.write(chunk)

            proc.wait()

            if proc.returncode != 0:
                stderr = proc.stderr.read().decode()
                # Clean up partial file
                if os.path.exists(db_file):
                    os.remove(db_file)
                raise Exception(f"pg_dump failed: {stderr}")

        files['database'] = db_file

    # Filestore backup
    if backup_type in ['full', 'filestore']:
        filestore_path = os.path.join(config.ODOO_BASE_DIR, env, 'filestore')
        filestore_file = os.path.join(env_backup_dir, f"{env}_filestore_{timestamp}.tar.gz")

        if os.path.exists(filestore_path) and os.listdir(filestore_path):
            result = subprocess.run(
                ['tar', '-czf', filestore_file, '-C', filestore_path, '.'],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise Exception(f"tar failed: {result.stderr}")

            files['filestore'] = filestore_file
        else:
            # Create empty tarball if filestore is empty or doesn't exist
            files['filestore'] = None

    # Create manifest
    manifest = {
        'backup_id': backup_id,
        'timestamp': datetime.now().isoformat(),
        'environment': env,
        'type': backup_type,
        'description': description,
        'database_name': database_name or (get_primary_database(env) if backup_type in ['full', 'database'] else None),
        'files': {k: v for k, v in files.items() if v},  # Only include non-None files
        'sizes': {k: os.path.getsize(v) for k, v in files.items() if v}
    }

    manifest_file = os.path.join(env_backup_dir, f"{backup_id}.manifest.json")
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)

    return {
        'backup_id': backup_id,
        'manifest': manifest,
        'files': [v for v in files.values() if v] + [manifest_file]
    }


# ============================================================================
# Upload Functions
# ============================================================================

def upload_to_s3(local_file, remote_key, s3_config):
    """
    Upload file to S3-compatible storage.

    Args:
        local_file: Path to local file
        remote_key: S3 key (path in bucket)
        s3_config: S3 configuration dict

    Returns:
        bool: Success status
    """
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError:
        raise ImportError("boto3 is required for S3 uploads. Install with: pip install boto3")

    endpoint = s3_config.get('endpoint', '')
    if endpoint and not endpoint.startswith('http'):
        endpoint = f"https://{endpoint}"

    s3_client = boto3.client(
        's3',
        endpoint_url=endpoint or None,
        aws_access_key_id=s3_config['access_key'],
        aws_secret_access_key=s3_config['secret_key'],
        region_name=s3_config.get('region', 'us-east-1'),
        config=BotoConfig(signature_version='s3v4')
    )

    file_size = os.path.getsize(local_file)

    # Use multipart upload for files > 100MB
    if file_size > 100 * 1024 * 1024:
        from boto3.s3.transfer import TransferConfig
        transfer_config = TransferConfig(
            multipart_threshold=25 * 1024 * 1024,  # 25MB
            max_concurrency=10
        )
        s3_client.upload_file(
            local_file,
            s3_config['bucket'],
            remote_key,
            Config=transfer_config
        )
    else:
        s3_client.upload_file(local_file, s3_config['bucket'], remote_key)

    return True


def upload_to_rsync(local_file, remote_path, rsync_config):
    """
    Upload file to rsync.net via rsync.

    Args:
        local_file: Path to local file
        remote_path: Remote path (relative to configured base)
        rsync_config: Rsync configuration dict

    Returns:
        bool: Success status
    """
    remote_dest = f"{rsync_config['username']}@{rsync_config['host']}:{rsync_config['remote_path']}/{remote_path}"

    ssh_cmd = f"ssh -i {rsync_config['ssh_key_path']} -o StrictHostKeyChecking=no"

    cmd = [
        'rsync',
        '-avz',
        '--progress',
        '-e', ssh_cmd,
        local_file,
        remote_dest
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        raise Exception(f"Rsync failed: {result.stderr}")

    return True


def upload_backup(backup_id, env):
    """
    Upload backup to configured remote storage.

    Args:
        backup_id: Backup identifier
        env: Environment name

    Returns:
        dict: Upload result
    """
    backup_config = config.load_backup_config()
    backend = backup_config.get('storage_backend', 'local')

    if backend == 'local':
        return {'uploaded': False, 'message': 'Local storage only - no remote upload configured'}

    # Load manifest
    manifest_file = os.path.join(config.BACKUP_DIR, env, f"{backup_id}.manifest.json")

    if not os.path.exists(manifest_file):
        raise ValueError(f"Backup {backup_id} not found")

    with open(manifest_file, 'r') as f:
        manifest = json.load(f)

    uploaded_files = []

    # Upload all backup files
    for file_type, local_file in manifest['files'].items():
        if not os.path.exists(local_file):
            continue

        remote_key = f"{env}/{os.path.basename(local_file)}"

        if backend == 's3':
            upload_to_s3(local_file, remote_key, backup_config['s3'])
        elif backend == 'rsync':
            upload_to_rsync(local_file, remote_key, backup_config['rsync'])

        uploaded_files.append(local_file)

    # Upload manifest
    manifest_remote = f"{env}/{backup_id}.manifest.json"
    if backend == 's3':
        upload_to_s3(manifest_file, manifest_remote, backup_config['s3'])
    elif backend == 'rsync':
        upload_to_rsync(manifest_file, manifest_remote, backup_config['rsync'])

    return {
        'uploaded': True,
        'backend': backend,
        'files': uploaded_files,
        'backup_id': backup_id
    }


def test_s3_connection(s3_config):
    """
    Test S3 connection by listing bucket contents.

    Returns:
        dict: Test result with success status and message
    """
    try:
        import boto3
        from botocore.config import Config as BotoConfig
        from botocore.exceptions import ClientError
    except ImportError:
        return {'success': False, 'message': 'boto3 not installed'}

    try:
        endpoint = s3_config.get('endpoint', '')
        if endpoint and not endpoint.startswith('http'):
            endpoint = f"https://{endpoint}"

        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint or None,
            aws_access_key_id=s3_config['access_key'],
            aws_secret_access_key=s3_config['secret_key'],
            region_name=s3_config.get('region', 'us-east-1'),
            config=BotoConfig(signature_version='s3v4')
        )

        # Try to list bucket contents
        s3_client.list_objects_v2(Bucket=s3_config['bucket'], MaxKeys=1)

        return {'success': True, 'message': 'Connection successful'}

    except ClientError as e:
        return {'success': False, 'message': f'S3 error: {e.response["Error"]["Message"]}'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


def test_rsync_connection(rsync_config):
    """
    Test rsync connection by listing remote directory.

    Returns:
        dict: Test result with success status and message
    """
    try:
        ssh_cmd = f"ssh -i {rsync_config['ssh_key_path']} -o StrictHostKeyChecking=no -o BatchMode=yes"

        cmd = [
            'rsync',
            '-n',  # Dry run
            '-e', ssh_cmd,
            f"{rsync_config['username']}@{rsync_config['host']}:{rsync_config['remote_path']}/"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            return {'success': True, 'message': 'Connection successful'}
        else:
            return {'success': False, 'message': f'Rsync error: {result.stderr}'}

    except subprocess.TimeoutExpired:
        return {'success': False, 'message': 'Connection timeout'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


# ============================================================================
# Backup Listing and Management
# ============================================================================

def list_backups(env=None):
    """
    List available backups.

    Args:
        env: Environment name (optional, lists all if not specified)

    Returns:
        dict: Backups organized by environment
    """
    backups = {}

    environments = [env] if env else config.ENVIRONMENTS

    for environment in environments:
        env_backup_dir = os.path.join(config.BACKUP_DIR, environment)
        backups[environment] = []

        if not os.path.exists(env_backup_dir):
            continue

        # Find all manifest files
        for filename in os.listdir(env_backup_dir):
            if filename.endswith('.manifest.json'):
                manifest_path = os.path.join(env_backup_dir, filename)

                try:
                    with open(manifest_path, 'r') as f:
                        manifest = json.load(f)

                    # Verify files exist
                    files_exist = all(
                        os.path.exists(f) for f in manifest.get('files', {}).values()
                    )

                    backups[environment].append({
                        'backup_id': manifest['backup_id'],
                        'timestamp': manifest['timestamp'],
                        'type': manifest['type'],
                        'description': manifest.get('description', ''),
                        'database_name': manifest.get('database_name'),
                        'sizes': manifest.get('sizes', {}),
                        'total_size': sum(manifest.get('sizes', {}).values()),
                        'files_exist': files_exist
                    })
                except (json.JSONDecodeError, IOError):
                    continue

        # Sort by timestamp (newest first)
        backups[environment].sort(key=lambda x: x['timestamp'], reverse=True)

    return backups if not env else backups.get(env, [])


def get_backup_details(env, backup_id):
    """Get detailed information about a specific backup."""
    manifest_file = os.path.join(config.BACKUP_DIR, env, f"{backup_id}.manifest.json")

    if not os.path.exists(manifest_file):
        raise ValueError(f"Backup {backup_id} not found")

    with open(manifest_file, 'r') as f:
        manifest = json.load(f)

    # Check file existence and update sizes
    for file_type, file_path in manifest.get('files', {}).items():
        if os.path.exists(file_path):
            manifest['sizes'][file_type] = os.path.getsize(file_path)

    manifest['total_size'] = sum(manifest.get('sizes', {}).values())

    return manifest


def delete_backup(env, backup_id):
    """
    Delete a backup and its files.

    Args:
        env: Environment name
        backup_id: Backup identifier

    Returns:
        bool: Success status
    """
    manifest_file = os.path.join(config.BACKUP_DIR, env, f"{backup_id}.manifest.json")

    if not os.path.exists(manifest_file):
        return False

    with open(manifest_file, 'r') as f:
        manifest = json.load(f)

    # Delete all backup files
    for file_path in manifest.get('files', {}).values():
        if os.path.exists(file_path):
            os.remove(file_path)

    # Delete manifest
    os.remove(manifest_file)

    return True


def cleanup_old_backups(env, retention_days=7):
    """
    Remove backups older than retention period.

    Args:
        env: Environment name
        retention_days: Number of days to keep backups

    Returns:
        int: Number of backups deleted
    """
    from datetime import timedelta

    cutoff = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0

    backups = list_backups(env)

    for backup in backups:
        backup_time = datetime.fromisoformat(backup['timestamp'])

        if backup_time < cutoff:
            if delete_backup(env, backup['backup_id']):
                deleted_count += 1

    return deleted_count


def get_backup_file_path(env, backup_id, file_type):
    """
    Get the path to a backup file for download.

    Args:
        env: Environment name
        backup_id: Backup identifier
        file_type: 'database' or 'filestore'

    Returns:
        str: Path to the file, or None if not found
    """
    manifest_file = os.path.join(config.BACKUP_DIR, env, f"{backup_id}.manifest.json")

    if not os.path.exists(manifest_file):
        return None

    with open(manifest_file, 'r') as f:
        manifest = json.load(f)

    file_path = manifest.get('files', {}).get(file_type)

    if file_path and os.path.exists(file_path):
        return file_path

    return None


# ============================================================================
# Database Copy Functions
# ============================================================================

def copy_database(source_env, target_env, include_filestore=True, include_addons=True, target_db_name=None):
    """
    Copy database (and optionally filestore/addons) from one environment to another.

    WARNING: This is a destructive operation that overwrites the target database!

    Args:
        source_env: Source environment (test, staging, prod)
        target_env: Target environment (test, staging, prod)
        include_filestore: Also copy filestore directory
        include_addons: Also copy addons directory
        target_db_name: Name for the target database. If not provided:
            - If target has existing database, uses that name
            - If target has no database, raises ValueError

    Returns:
        dict: Operation result
    """
    if source_env == target_env:
        raise ValueError("Source and target environments must be different")

    if source_env not in config.ENVIRONMENTS:
        raise ValueError(f"Invalid source environment: {source_env}")

    if target_env not in config.ENVIRONMENTS:
        raise ValueError(f"Invalid target environment: {target_env}")

    result = {
        'success': False,
        'source': source_env,
        'target': target_env,
        'database_copied': False,
        'filestore_copied': False,
        'addons_copied': False,
        'errors': []
    }

    source_creds = get_db_credentials(source_env)
    target_creds = get_db_credentials(target_env)

    # Get source database name
    source_db = get_primary_database(source_env)

    # Determine target database name
    if target_db_name:
        # Use the provided name
        target_db = target_db_name
    else:
        # Try to get existing target database name
        try:
            target_db = get_primary_database(target_env)
        except ValueError:
            # Target database doesn't exist and no name was provided
            raise ValueError(f"No database exists in {target_env} environment. Please provide a database name.")

    # Step 1: Stop target container
    from services import container_service
    container_result = container_service.stop_container(target_env)

    if not container_result.get('success'):
        # Container might not be running, continue anyway
        pass

    try:
        # Step 2: Drop and recreate target database
        env_vars = os.environ.copy()
        env_vars['PGPASSWORD'] = target_creds['password']

        # Terminate existing connections to target database
        terminate_query = f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{target_db}'
            AND pid <> pg_backend_pid()
        """

        subprocess.run(
            ['psql', '-h', target_creds['host'], '-p', target_creds['port'],
             '-U', target_creds['user'], '-d', 'postgres', '-c', terminate_query],
            capture_output=True,
            env=env_vars
        )

        # Drop target database if it exists
        drop_result = subprocess.run(
            ['psql', '-h', target_creds['host'], '-p', target_creds['port'],
             '-U', target_creds['user'], '-d', 'postgres',
             '-c', f'DROP DATABASE IF EXISTS "{target_db}"'],
            capture_output=True,
            text=True,
            env=env_vars
        )

        # Create new target database
        create_result = subprocess.run(
            ['psql', '-h', target_creds['host'], '-p', target_creds['port'],
             '-U', target_creds['user'], '-d', 'postgres',
             '-c', f'CREATE DATABASE "{target_db}"'],
            capture_output=True,
            text=True,
            env=env_vars
        )

        if create_result.returncode != 0:
            result['errors'].append(f"Failed to create database: {create_result.stderr}")
            return result

        # Step 3: Copy data using pg_dump | psql
        source_env_vars = os.environ.copy()
        source_env_vars['PGPASSWORD'] = source_creds['password']

        # Pipe pg_dump output directly to psql
        dump_proc = subprocess.Popen(
            ['pg_dump', '-h', source_creds['host'], '-p', source_creds['port'],
             '-U', source_creds['user'], '-d', source_db],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=source_env_vars
        )

        restore_proc = subprocess.Popen(
            ['psql', '-h', target_creds['host'], '-p', target_creds['port'],
             '-U', target_creds['user'], '-d', target_db],
            stdin=dump_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env_vars
        )

        dump_proc.stdout.close()
        stdout, stderr = restore_proc.communicate()

        if restore_proc.returncode != 0:
            result['errors'].append(f"Database restore failed: {stderr.decode()}")
        else:
            result['database_copied'] = True

        # Step 4: Copy filestore if requested
        if include_filestore:
            source_filestore = os.path.join(config.ODOO_BASE_DIR, source_env, 'filestore')
            target_filestore = os.path.join(config.ODOO_BASE_DIR, target_env, 'filestore')

            if os.path.exists(source_filestore):
                # Remove target filestore contents
                if os.path.exists(target_filestore):
                    shutil.rmtree(target_filestore)

                # Copy source to target
                shutil.copytree(source_filestore, target_filestore)

                # Fix ownership (Odoo container user: UID 100, GID 101)
                subprocess.run(
                    ['chown', '-R', '100:101', target_filestore],
                    capture_output=True
                )

                result['filestore_copied'] = True

        # Step 5: Copy addons if requested
        if include_addons:
            source_addons = os.path.join(config.ODOO_BASE_DIR, source_env, 'addons')
            target_addons = os.path.join(config.ODOO_BASE_DIR, target_env, 'addons')

            if os.path.exists(source_addons) and os.listdir(source_addons):
                # Remove target addons contents
                if os.path.exists(target_addons):
                    shutil.rmtree(target_addons)

                # Copy source to target
                shutil.copytree(source_addons, target_addons)

                # Fix ownership (Odoo container user: UID 100, GID 101)
                subprocess.run(
                    ['chown', '-R', '100:101', target_addons],
                    capture_output=True
                )

                result['addons_copied'] = True

        result['success'] = result['database_copied']
        result['target_db_name'] = target_db
        result['source_db_name'] = source_db

    finally:
        # Step 5: Restart target container
        container_service.start_container(target_env)

    return result


def get_database_info(env):
    """
    Get information about the database for an environment.

    Returns:
        dict: Database info including name, size, table count
    """
    debug_info = {'steps': []}

    try:
        # Step 0: Get service config from docker-compose
        debug_info['steps'].append(f'Getting service config for env={env}...')
        try:
            service_config = config.get_service_config(env)
            if service_config:
                debug_info['steps'].append(f'Service found: {service_config.get("service_name")}, container: {service_config.get("container_name")}')
                env_vars = service_config.get('environment', {})
                debug_info['steps'].append(f'Environment vars found: {list(env_vars.keys())}')
            else:
                debug_info['steps'].append(f'FAILED: No service config found for {env}')
                raise ValueError(f"Environment {env} not found in docker-compose.yml")
        except Exception as e:
            debug_info['steps'].append(f'FAILED to get service config: {e}')
            raise

        # Step 1: Get credentials
        debug_info['steps'].append('Getting credentials...')
        try:
            creds = get_db_credentials(env)
            debug_info['steps'].append(f'Credentials found: user={creds["user"]}, has_password={bool(creds["password"])}')
        except Exception as e:
            debug_info['steps'].append(f'FAILED to get credentials: {e}')
            raise

        # Step 2: Discover database
        debug_info['steps'].append('Discovering database...')
        try:
            db_name = get_primary_database(env)
            debug_info['steps'].append(f'Database found: {db_name}')
        except Exception as e:
            debug_info['steps'].append(f'FAILED to discover database: {e}')
            raise

        env_vars = os.environ.copy()
        env_vars['PGPASSWORD'] = creds['password']

        # Step 3: Get database size
        debug_info['steps'].append('Getting database size...')
        size_query = f"SELECT pg_size_pretty(pg_database_size('{db_name}'))"

        result = subprocess.run(
            ['psql', '-h', creds['host'], '-p', creds['port'],
             '-U', creds['user'], '-d', db_name, '-t', '-A', '-c', size_query],
            capture_output=True,
            text=True,
            env=env_vars
        )

        if result.returncode == 0:
            db_size = result.stdout.strip()
            debug_info['steps'].append(f'Size query success: {db_size}')
        else:
            db_size = 'Unknown'
            debug_info['steps'].append(f'Size query FAILED: {result.stderr}')

        # Step 4: Get table count
        debug_info['steps'].append('Getting table count...')
        table_query = "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"

        result = subprocess.run(
            ['psql', '-h', creds['host'], '-p', creds['port'],
             '-U', creds['user'], '-d', db_name, '-t', '-A', '-c', table_query],
            capture_output=True,
            text=True,
            env=env_vars
        )

        if result.returncode == 0:
            table_count = int(result.stdout.strip())
            debug_info['steps'].append(f'Table count success: {table_count}')
        else:
            table_count = 0
            debug_info['steps'].append(f'Table count FAILED: {result.stderr}')

        return {
            'name': db_name,
            'size': db_size,
            'table_count': table_count,
            'user': creds['user'],
            'available': True,
            'debug': debug_info
        }

    except Exception as e:
        debug_info['steps'].append(f'EXCEPTION: {type(e).__name__}: {e}')
        return {
            'name': None,
            'size': 'Unknown',
            'table_count': 0,
            'user': None,
            'available': False,
            'error': str(e),
            'debug': debug_info
        }
