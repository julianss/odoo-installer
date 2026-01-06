#!/usr/bin/env python3
"""
Password Sync Script for Odoo Installer

This script reads passwords from docker-compose.yml and updates them in PostgreSQL.
Use this to fix password mismatches caused by shell variable expansion during installation.

Usage:
    sudo python3 fix_passwords.py
"""

import os
import re
import subprocess
import sys

DOCKER_COMPOSE_PATH = '/srv/odoo/docker-compose.yml'

def parse_docker_compose():
    """Parse docker-compose.yml and extract USER/PASSWORD for each service."""
    if not os.path.exists(DOCKER_COMPOSE_PATH):
        print(f"Error: {DOCKER_COMPOSE_PATH} not found")
        sys.exit(1)

    with open(DOCKER_COMPOSE_PATH, 'r') as f:
        content = f.read()

    # Find services section
    services_match = re.search(r'^services:\s*$', content, re.MULTILINE)
    if not services_match:
        print("Error: No services section found in docker-compose.yml")
        sys.exit(1)

    services_content = content[services_match.end():]

    # Find each service block
    service_pattern = re.compile(r'^  ([a-zA-Z0-9_-]+):\s*$', re.MULTILINE)
    service_matches = list(service_pattern.finditer(services_content))

    credentials = []

    for i, match in enumerate(service_matches):
        service_name = match.group(1)

        # Get service block content
        start = match.end()
        end = service_matches[i + 1].start() if i + 1 < len(service_matches) else len(services_content)
        service_block = services_content[start:end]

        # Extract environment variables
        env_section = re.search(r'environment:\s*\n((?:\s+.+\n?)+?)(?=\n    \w|\n  \w|$)', service_block)
        if not env_section:
            continue

        env_vars = {}
        for line in env_section.group(1).strip().split('\n'):
            line = line.strip()
            # Format: KEY: value
            match = re.match(r'(\w+):\s*(.+)', line)
            if match:
                env_vars[match.group(1)] = match.group(2).strip()

        user = env_vars.get('USER')
        password = env_vars.get('PASSWORD')

        if user and password:
            credentials.append({
                'service': service_name,
                'user': user,
                'password': password
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
    credentials = parse_docker_compose()

    if not credentials:
        print("No credentials found in docker-compose.yml")
        sys.exit(1)

    print(f"Found {len(credentials)} service(s) with credentials")
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
