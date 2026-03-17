"""
Scheduler service for automated backups using APScheduler.

Handles:
- Configuring backup schedules per environment
- Running scheduled backup tasks
- Managing job lifecycle
"""

import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError
import sys
import os

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger('odoo_dashboard.scheduler')

# Global scheduler instance
scheduler = BackgroundScheduler(
    job_defaults={
        'coalesce': True,  # Combine multiple missed runs into one
        'max_instances': 1,  # Only one instance of each job at a time
        'misfire_grace_time': 3600  # Allow 1 hour grace for missed jobs
    }
)

# Track if scheduler has been started
_scheduler_started = False


def init_scheduler():
    """Initialize and start the scheduler."""
    global _scheduler_started

    if _scheduler_started:
        logger.debug("Scheduler already started")
        return

    try:
        # Load and apply saved schedules
        load_schedules()

        # Start the scheduler
        scheduler.start()
        _scheduler_started = True
        logger.info("Backup scheduler started")

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    global _scheduler_started

    if _scheduler_started:
        scheduler.shutdown(wait=False)
        _scheduler_started = False
        logger.info("Backup scheduler stopped")


def load_schedules():
    """Load schedules from backup config and create jobs."""
    backup_config = config.load_backup_config()
    schedules = backup_config.get('schedules', {})

    for env, schedule in schedules.items():
        if schedule.get('enabled', False):
            try:
                add_backup_schedule(env, schedule)
            except Exception as e:
                logger.error(f"Failed to load schedule for {env}: {e}")


def add_backup_schedule(env, schedule):
    """
    Add or update a backup schedule for an environment.

    Args:
        env: Environment name (test, staging, prod)
        schedule: Schedule configuration dict with:
            - enabled: bool
            - frequency: 'daily', 'weekly', 'monthly'
            - time: 'HH:MM' format
            - day: day of week for weekly (monday, tuesday, etc.)
            - day_of_month: day of month for monthly (1-31)
            - type: backup type ('full', 'database', 'filestore')
            - upload: whether to upload to remote storage
    """
    job_id = f"backup_{env}"

    # Remove existing job if any
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass

    if not schedule.get('enabled', False):
        logger.info(f"Schedule for {env} is disabled")
        return

    frequency = schedule.get('frequency', 'daily')
    time_str = schedule.get('time', '02:00')
    backup_type = schedule.get('type', 'full')
    upload = schedule.get('upload', False)

    # Parse time
    try:
        hour, minute = map(int, time_str.split(':'))
    except ValueError:
        hour, minute = 2, 0
        logger.warning(f"Invalid time format '{time_str}', using 02:00")

    # Create cron trigger based on frequency
    if frequency == 'daily':
        trigger = CronTrigger(hour=hour, minute=minute)
    elif frequency == 'weekly':
        day = schedule.get('day', 'sunday').lower()
        day_map = {
            'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
            'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun'
        }
        day_abbr = day_map.get(day, 'sun')
        trigger = CronTrigger(day_of_week=day_abbr, hour=hour, minute=minute)
    elif frequency == 'monthly':
        day_of_month = schedule.get('day_of_month', 1)
        trigger = CronTrigger(day=day_of_month, hour=hour, minute=minute)
    else:
        logger.warning(f"Unknown frequency '{frequency}', using daily")
        trigger = CronTrigger(hour=hour, minute=minute)

    # Add the job
    scheduler.add_job(
        func=run_scheduled_backup,
        trigger=trigger,
        args=[env, backup_type, upload],
        id=job_id,
        name=f"{env.capitalize()} Backup ({frequency})",
        replace_existing=True
    )

    logger.info(f"Scheduled {frequency} {backup_type} backup for {env} at {time_str}")


def run_scheduled_backup(env, backup_type, upload):
    """
    Execute a scheduled backup.

    This function is called by APScheduler when a backup is due.
    """
    from services import backup_service

    logger.info(f"Starting scheduled {backup_type} backup for {env}")

    try:
        # Create the backup
        result = backup_service.create_backup(
            env=env,
            backup_type=backup_type,
            description=f'Scheduled backup ({datetime.now().strftime("%Y-%m-%d %H:%M")})'
        )

        backup_id = result['backup_id']
        logger.info(f"Scheduled backup created: {backup_id}")

        # Upload if configured
        if upload:
            try:
                upload_result = backup_service.upload_backup(backup_id, env)
                if upload_result.get('uploaded'):
                    logger.info(f"Backup {backup_id} uploaded to {upload_result.get('backend')}")
                else:
                    logger.warning(f"Upload skipped: {upload_result.get('message')}")
            except Exception as e:
                logger.error(f"Failed to upload backup {backup_id}: {e}")

        # Cleanup old backups
        backup_config = config.load_backup_config()
        retention_days = backup_config.get('retention', {}).get('local_days', 7)

        deleted = backup_service.cleanup_old_backups(env, retention_days)
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old backup(s) for {env}")

        # Log to audit
        log_backup_event(env, backup_id, 'scheduled', True)

        return {'success': True, 'backup_id': backup_id}

    except Exception as e:
        logger.error(f"Scheduled backup failed for {env}: {e}")
        log_backup_event(env, None, 'scheduled', False, str(e))
        return {'success': False, 'error': str(e)}


def log_backup_event(env, backup_id, trigger_type, success, error=None):
    """Log backup event to audit log."""
    audit_file = os.path.join(config.DATA_DIR, 'backup-audit.log')

    try:
        with open(audit_file, 'a') as f:
            timestamp = datetime.now().isoformat()
            status = 'SUCCESS' if success else 'FAILED'
            error_msg = f' - {error}' if error else ''
            f.write(f"{timestamp} | {env} | {trigger_type} | {status} | {backup_id or 'N/A'}{error_msg}\n")
    except IOError as e:
        logger.warning(f"Failed to write audit log: {e}")


def save_schedule(env, schedule):
    """
    Save a schedule configuration.

    Args:
        env: Environment name
        schedule: Schedule configuration dict
    """
    backup_config = config.load_backup_config()

    if 'schedules' not in backup_config:
        backup_config['schedules'] = {}

    backup_config['schedules'][env] = schedule
    config.save_backup_config(backup_config)

    # Apply the schedule
    if schedule.get('enabled', False):
        add_backup_schedule(env, schedule)
    else:
        # Remove job if disabled
        try:
            scheduler.remove_job(f"backup_{env}")
        except JobLookupError:
            pass

    logger.info(f"Schedule saved for {env}: enabled={schedule.get('enabled')}")


def get_schedule(env):
    """Get schedule configuration for an environment."""
    backup_config = config.load_backup_config()
    return backup_config.get('schedules', {}).get(env, {
        'enabled': False,
        'frequency': 'daily',
        'time': '02:00',
        'day': 'sunday',
        'day_of_month': 1,
        'type': 'full',
        'upload': False
    })


def get_all_schedules():
    """Get all schedule configurations."""
    backup_config = config.load_backup_config()
    schedules = backup_config.get('schedules', {})

    # Ensure all environments have a schedule entry
    result = {}
    for env in config.ENVIRONMENTS:
        result[env] = schedules.get(env, {
            'enabled': False,
            'frequency': 'daily',
            'time': '02:00',
            'day': 'sunday',
            'day_of_month': 1,
            'type': 'full',
            'upload': False
        })

    return result


def get_scheduled_jobs():
    """
    Get list of scheduled jobs with their next run times.

    Returns:
        list: List of job info dicts
    """
    jobs = []

    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': next_run.isoformat() if next_run else None,
            'next_run_formatted': next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else 'Not scheduled',
            'trigger': str(job.trigger)
        })

    return jobs


def get_job_info(env):
    """Get info about a specific environment's backup job."""
    job_id = f"backup_{env}"

    try:
        job = scheduler.get_job(job_id)
        if job:
            next_run = job.next_run_time
            return {
                'exists': True,
                'id': job.id,
                'name': job.name,
                'next_run': next_run.isoformat() if next_run else None,
                'next_run_formatted': next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else 'Not scheduled',
                'trigger': str(job.trigger)
            }
    except Exception:
        pass

    return {'exists': False}


def trigger_backup_now(env):
    """
    Manually trigger a backup for an environment.

    Uses the saved schedule configuration for backup type and upload settings.
    """
    schedule = get_schedule(env)
    backup_type = schedule.get('type', 'full')
    upload = schedule.get('upload', False)

    logger.info(f"Manually triggering {backup_type} backup for {env}")

    result = run_scheduled_backup(env, backup_type, upload)

    # Log as manual trigger
    log_backup_event(env, result.get('backup_id'), 'manual', result.get('success', False))

    return result


def get_backup_history(env=None, limit=50):
    """
    Get backup history from audit log.

    Args:
        env: Optional environment filter
        limit: Maximum number of entries to return

    Returns:
        list: List of backup history entries
    """
    audit_file = os.path.join(config.DATA_DIR, 'backup-audit.log')
    history = []

    if not os.path.exists(audit_file):
        return history

    try:
        with open(audit_file, 'r') as f:
            lines = f.readlines()

        # Parse lines in reverse order (newest first)
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue

            try:
                parts = line.split(' | ')
                if len(parts) >= 5:
                    entry = {
                        'timestamp': parts[0],
                        'environment': parts[1],
                        'trigger': parts[2],
                        'status': parts[3],
                        'backup_id': parts[4].split(' - ')[0]
                    }

                    # Extract error if present
                    if ' - ' in parts[4]:
                        entry['error'] = parts[4].split(' - ', 1)[1]

                    # Filter by environment if specified
                    if env and entry['environment'] != env:
                        continue

                    history.append(entry)

                    if len(history) >= limit:
                        break

            except Exception:
                continue

    except IOError as e:
        logger.warning(f"Failed to read audit log: {e}")

    return history
