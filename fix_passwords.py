#!/usr/bin/env python3
"""
Password Sync Script for Odoo Installer

This script reads passwords from docker-compose.yml and updates them in PostgreSQL.
Use this to fix password mismatches caused by shell variable expansion during installation.

Usage:
    sudo python3 fix_passwords.py
"""

import os
import subprocess
import sys

DOCKER_COMPOSE_PATH = '/srv/odoo/docker-compose.yml'


def parse_docker_compose():
    """Parse docker-compose.yml and extract USER/PASSWORD for each service."""
    if not os.path.exists(DOCKER_COMPOSE_PATH):
        print(f"Error: {DOCKER_COMPOSE_PATH} not found")
        sys.exit(1)

    with open(DOCKER_COMPOSE_PATH, 'r') as f:
        lines = f.readlines()

    credentials = []
    current_service = None
    in_environment = False
    env_vars = {}

    for line in lines:
        stripped = line.rstrip()

        # Detect service name (2-space indent, ends with colon)
        if line.startswith('  ') and not line.startswith('    ') and stripped.endswith(':'):
            # Save previous service if it had credentials
            if current_service and env_vars.get('USER') and env_vars.get('PASSWORD'):
                credentials.append({
                    'service': current_service,
                    'user': env_vars['USER'],
                    'password': env_vars['PASSWORD']
                })

            current_service = stripped.strip().rstrip(':')
            in_environment = False
            env_vars = {}
            continue

        # Detect environment section (4-space indent)
        if line.startswith('    environment:'):
            in_environment = True
            continue

        # Detect end of environment section (4-space indent, not 6-space)
        if in_environment and line.startswith('    ') and not line.startswith('      '):
            in_environment = False
            continue

        # Parse environment variables (6-space indent)
        if in_environment and line.startswith('      '):
            # Handle both "KEY: value" and "- KEY=value" formats
            content = stripped.strip()

            if ': ' in content and not content.startswith('-'):
                # Format: KEY: value
                key, value = content.split(': ', 1)
                env_vars[key] = value
            elif content.startswith('- ') and '=' in content:
                # Format: - KEY=value
                content = content[2:]  # Remove "- "
                key, value = content.split('=', 1)
                env_vars[key] = value

    # Don't forget the last service
    if current_service and env_vars.get('USER') and env_vars.get('PASSWORD'):
        credentials.append({
            'service': current_service,
            'user': env_vars['USER'],
            'password': env_vars['PASSWORD']
        })

    return credentials


def update_postgresql_password(user, password):
    """Update PostgreSQL user password using a secure method."""
    # Escape single quotes in password for SQL (double them)
    escaped_password = password.replace("'", "''")
    sql = f"ALTER USER {user} WITH PASSWORD '{escaped_password}';"

    # Use list form to avoid shell interpretation
    result = subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-c', sql],
        capture_output=True,
        text=True
    )

    return result.returncode == 0, result.stderr


def test_password(user, password):
    """Test if a password works for a PostgreSQL user."""
    env = os.environ.copy()
    env['PGPASSWORD'] = password

    result = subprocess.run(
        ['psql', '-h', 'localhost', '-U', user, '-d', 'postgres', '-c', 'SELECT 1'],
        capture_output=True,
        text=True,
        env=env
    )

    return result.returncode == 0


def main():
    if os.geteuid() != 0:
        print("Error: This script must be run as root (sudo)")
        sys.exit(1)

    print("=" * 60)
    print("Odoo Password Sync Script")
    print("=" * 60)
    print()

    # Parse docker-compose.yml
    print(f"Reading credentials from {DOCKER_COMPOSE_PATH}...")

    # Debug: show first few lines of file
    print()
    print("Debug: First 30 lines of docker-compose.yml:")
    print("-" * 40)
    with open(DOCKER_COMPOSE_PATH, 'r') as f:
        for i, line in enumerate(f):
            if i >= 30:
                print("...")
                break
            print(f"{i+1:3}: {repr(line)}")
    print("-" * 40)
    print()

    credentials = parse_docker_compose()

    if not credentials:
        print("No credentials found in docker-compose.yml")
        print()
        print("Expected format:")
        print("  service-name:")
        print("    environment:")
        print("      USER: username")
        print("      PASSWORD: password")
        sys.exit(1)

    print(f"Found {len(credentials)} service(s) with credentials:")
    for cred in credentials:
        print(f"  - {cred['service']}: user={cred['user']}")
    print()

    # Process each set of credentials
    for cred in credentials:
        service = cred['service']
        user = cred['user']
        password = cred['password']

        print(f"Processing: {service}")
        print(f"  User: {user}")
        print(f"  Password: {'*' * min(len(password), 8)}... ({len(password)} chars)")

        # Test current password
        print(f"  Testing current password... ", end='', flush=True)
        if test_password(user, password):
            print("OK (already working)")
            print()
            continue
        else:
            print("FAILED")

        # Update password in PostgreSQL
        print(f"  Updating password in PostgreSQL... ", end='', flush=True)
        success, error = update_postgresql_password(user, password)

        if success:
            print("OK")
            # Verify it works now
            print(f"  Verifying new password... ", end='', flush=True)
            if test_password(user, password):
                print("OK")
            else:
                print("FAILED (still not working)")
        else:
            print(f"FAILED: {error}")

        print()

    print("=" * 60)
    print("Done!")
    print()
    print("If passwords were updated, restart your Odoo containers:")
    print("  cd /srv/odoo && docker compose restart")
    print()


if __name__ == '__main__':
    main()
