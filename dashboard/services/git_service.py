"""
Git repository management service for Odoo Dashboard

Handles cloning, pulling, and status checking of git repositories
in Odoo addon directories.
"""

import os
import subprocess
import logging
from datetime import datetime
from git import Repo, GitCommandError
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger('odoo_dashboard')


def load_registry():
    """Load git repository registry."""
    return config.load_git_repos()


def save_registry(registry):
    """Save git repository registry."""
    return config.save_git_repos(registry)


def get_addons_path(env):
    """Get the addons directory path for an environment."""
    return os.path.join(config.ODOO_BASE_DIR, env, 'addons')


def list_repositories(env):
    """
    List all repositories for an environment with their status.

    Args:
        env: Environment name (test, staging, prod)

    Returns:
        list: List of repository info dicts
    """
    registry = load_registry()
    repos = registry.get(env, [])

    result = []
    for repo_info in repos:
        try:
            status = get_repo_status(env, repo_info['id'])
            result.append(status)
        except Exception as e:
            # Return basic info if status check fails
            result.append({
                'id': repo_info['id'],
                'name': repo_info.get('name', repo_info['dirname']),
                'path': repo_info['path'],
                'error': str(e),
                'status': 'error'
            })

    return result


def clone_repository(env, url, dirname, branch='main', name=None, auto_restart=True):
    """
    Clone a git repository to the addons directory.

    Args:
        env: Environment name (test, staging, prod)
        url: Git repository URL
        dirname: Directory name for the clone
        branch: Branch to checkout (default: main)
        name: Display name for the repository
        auto_restart: Whether to restart container after pull

    Returns:
        str: Repository ID

    Raises:
        ValueError: If directory already exists or clone fails
    """
    addons_path = get_addons_path(env)
    target_path = os.path.join(addons_path, dirname)

    # Check if directory already exists
    if os.path.exists(target_path):
        raise ValueError(f"Directory {dirname} already exists in {env} addons")

    # Ensure addons directory exists
    os.makedirs(addons_path, exist_ok=True)

    try:
        # Clone repository
        logger.info(f"Cloning {url} to {target_path} (branch: {branch})")
        repo = Repo.clone_from(url, target_path, branch=branch)

        # Fix ownership for Odoo container (UID 100, GID 101)
        subprocess.run(['chown', '-R', '100:101', target_path], check=True)

        # Add to git safe.directory to avoid "dubious ownership" errors when running as root
        subprocess.run(['git', 'config', '--global', '--add', 'safe.directory', target_path], check=False)

        # Generate unique repository ID
        repo_id = f"{env}-{dirname}-{int(datetime.now().timestamp())}"

        # Add to registry
        registry = load_registry()
        if env not in registry:
            registry[env] = []

        registry[env].append({
            'id': repo_id,
            'name': name or dirname,
            'url': url,
            'path': target_path,
            'dirname': dirname,
            'branch': branch,
            'added_at': datetime.now().isoformat(),
            'auto_restart': auto_restart
        })

        save_registry(registry)

        logger.info(f"Successfully cloned repository {repo_id}")
        return repo_id

    except GitCommandError as e:
        # Clean up partial clone if it exists
        if os.path.exists(target_path):
            import shutil
            shutil.rmtree(target_path, ignore_errors=True)
        raise ValueError(f"Git clone failed: {e}")


def get_repo_status(env, repo_id):
    """
    Get detailed status of a repository.

    Args:
        env: Environment name
        repo_id: Repository ID

    Returns:
        dict: Repository status information
    """
    registry = load_registry()
    repo_info = next((r for r in registry.get(env, []) if r['id'] == repo_id), None)

    if not repo_info:
        raise ValueError(f"Repository {repo_id} not found")

    path = repo_info['path']

    # Check if directory exists
    if not os.path.exists(path):
        return {
            'id': repo_id,
            'name': repo_info.get('name', repo_info['dirname']),
            'path': path,
            'status': 'missing',
            'error': 'Repository directory not found'
        }

    try:
        repo = Repo(path)

        # Get current branch
        try:
            current_branch = repo.active_branch.name
        except TypeError:
            # Detached HEAD state
            current_branch = repo.head.commit.hexsha[:7]

        # Check dirty state - use subprocess for reliability
        is_dirty = False
        untracked_count = 0
        try:
            # Use git status --porcelain for reliable dirty check
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                lines = [l for l in result.stdout.strip().split('\n') if l]
                is_dirty = len(lines) > 0
                untracked_count = len([l for l in lines if l.startswith('??')])
        except Exception:
            # Fall back to GitPython if subprocess fails
            try:
                is_dirty = repo.is_dirty(untracked_files=True)
                untracked_count = len(repo.untracked_files)
            except Exception:
                pass

        # Build status dict
        status = {
            'id': repo_id,
            'name': repo_info.get('name', repo_info['dirname']),
            'path': path,
            'url': repo_info.get('url', ''),
            'dirname': repo_info.get('dirname', ''),
            'current_branch': current_branch,
            'configured_branch': repo_info.get('branch', 'main'),
            'is_dirty': is_dirty,
            'untracked_files': untracked_count,
            'auto_restart': repo_info.get('auto_restart', True),
            'added_at': repo_info.get('added_at', ''),
            'status': 'ok'
        }

        # Get last commit info
        try:
            commit = repo.head.commit
            status['last_commit'] = {
                'hash': commit.hexsha[:7],
                'message': commit.message.strip().split('\n')[0][:80],  # First line, truncated
                'author': str(commit.author),
                'date': commit.committed_datetime.isoformat()
            }
        except Exception:
            status['last_commit'] = None

        # Check ahead/behind (requires fetch)
        try:
            # Add to safe.directory in case it wasn't added during clone
            subprocess.run(['git', 'config', '--global', '--add', 'safe.directory', path],
                          capture_output=True, check=False)

            origin = repo.remotes.origin
            # Fetch with timeout
            origin.fetch()

            local_commit = repo.head.commit
            remote_branch = repo_info.get('branch', 'main')

            # Try to get remote branch ref
            remote_ref = None
            for ref in origin.refs:
                if ref.name == f'origin/{remote_branch}':
                    remote_ref = ref
                    break

            if remote_ref:
                remote_commit = remote_ref.commit

                # Count commits ahead and behind
                ahead = len(list(repo.iter_commits(f'{remote_commit}..{local_commit}')))
                behind = len(list(repo.iter_commits(f'{local_commit}..{remote_commit}')))

                status['ahead'] = ahead
                status['behind'] = behind
            else:
                status['sync_error'] = f"Remote branch {remote_branch} not found"

        except Exception as e:
            status['sync_error'] = str(e)

        # Get modified files if dirty - use subprocess for reliability
        if status['is_dirty']:
            try:
                result = subprocess.run(
                    ['git', 'status', '--porcelain'],
                    cwd=path,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    lines = [l for l in result.stdout.strip().split('\n') if l]
                    # Parse porcelain output: first 2 chars are status, rest is filename
                    modified = []
                    staged = []
                    for line in lines[:10]:  # Limit to first 10
                        if len(line) > 3:
                            xy = line[:2]
                            filename = line[3:]
                            if xy[0] != ' ' and xy[0] != '?':
                                staged.append(filename)
                            if xy[1] != ' ' and xy[1] != '?':
                                modified.append(filename)
                    status['modified_files'] = modified
                    status['staged_files'] = staged
            except Exception:
                pass

        return status

    except Exception as e:
        return {
            'id': repo_id,
            'name': repo_info.get('name', repo_info['dirname']),
            'path': path,
            'status': 'error',
            'error': str(e)
        }


def pull_repository(env, repo_id):
    """
    Pull latest changes from remote.

    Args:
        env: Environment name
        repo_id: Repository ID

    Returns:
        dict: Pull result with commits pulled and auto_restart flag

    Raises:
        ValueError: If pull fails or repo has uncommitted changes
    """
    registry = load_registry()
    repo_info = next((r for r in registry.get(env, []) if r['id'] == repo_id), None)

    if not repo_info:
        raise ValueError(f"Repository {repo_id} not found")

    path = repo_info['path']

    if not os.path.exists(path):
        raise ValueError(f"Repository directory not found: {path}")

    try:
        # Add to safe.directory in case it wasn't added during clone
        subprocess.run(['git', 'config', '--global', '--add', 'safe.directory', path],
                      capture_output=True, check=False)

        repo = Repo(path)

        # Check for uncommitted changes using subprocess for reliability
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=path,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            # Filter out untracked files (lines starting with ??)
            changes = [l for l in result.stdout.strip().split('\n') if l and not l.startswith('??')]
            if changes:
                dirty_files = [l[3:] if len(l) > 3 else l for l in changes[:5]]
                raise ValueError(f"Repository has uncommitted changes: {', '.join(dirty_files)}")

        # Get current HEAD for comparison
        old_head = repo.head.commit.hexsha

        # Pull from remote
        origin = repo.remotes.origin
        pull_info = origin.pull()

        # Get new HEAD
        new_head = repo.head.commit.hexsha

        # Count commits pulled
        commits = []
        if old_head != new_head:
            try:
                for commit in repo.iter_commits(f'{old_head}..{new_head}'):
                    commits.append({
                        'hash': commit.hexsha[:7],
                        'message': commit.message.strip().split('\n')[0][:80],
                        'author': str(commit.author),
                        'date': commit.committed_datetime.isoformat()
                    })
            except Exception:
                pass

        # Fix ownership after pull
        subprocess.run(['chown', '-R', '100:101', path], check=True)

        logger.info(f"Pulled {len(commits)} commits for {repo_id}")

        return {
            'success': True,
            'commits_pulled': len(commits),
            'commits': commits[:10],  # Limit to 10 most recent
            'auto_restart': repo_info.get('auto_restart', True),
            'message': f"Pulled {len(commits)} commit(s)" if commits else "Already up to date"
        }

    except GitCommandError as e:
        raise ValueError(f"Git pull failed: {e}")


def remove_repository(env, repo_id, delete_files=False):
    """
    Remove repository from registry.

    Args:
        env: Environment name
        repo_id: Repository ID
        delete_files: Whether to also delete the files (default: False)

    Returns:
        bool: True if removed successfully
    """
    registry = load_registry()

    if env not in registry:
        return False

    # Find the repo
    repo_info = next((r for r in registry[env] if r['id'] == repo_id), None)

    if not repo_info:
        return False

    # Optionally delete files
    if delete_files and os.path.exists(repo_info['path']):
        import shutil
        try:
            shutil.rmtree(repo_info['path'])
            logger.info(f"Deleted repository files at {repo_info['path']}")
        except Exception as e:
            logger.error(f"Failed to delete repository files: {e}")

    # Remove from registry
    registry[env] = [r for r in registry[env] if r['id'] != repo_id]
    save_registry(registry)

    logger.info(f"Removed repository {repo_id} from registry")
    return True


def get_all_repos_status():
    """
    Get status of all repositories across all environments.

    Returns:
        dict: Mapping of environment to list of repo statuses
    """
    result = {}
    registry = load_registry()

    for env in config.ENVIRONMENTS:
        result[env] = list_repositories(env)

    return result


def validate_git_url(url):
    """
    Validate a git URL format.

    Args:
        url: Git repository URL

    Returns:
        bool: True if URL looks valid
    """
    if not url:
        return False

    # Basic validation for common git URL formats
    valid_prefixes = [
        'git@',
        'https://',
        'http://',
        'ssh://',
        'git://'
    ]

    return any(url.startswith(prefix) for prefix in valid_prefixes)


def validate_dirname(dirname):
    """
    Validate directory name for a repository.

    Args:
        dirname: Directory name

    Returns:
        tuple: (is_valid, error_message)
    """
    if not dirname:
        return False, "Directory name is required"

    if len(dirname) > 100:
        return False, "Directory name too long (max 100 characters)"

    # Check for valid characters
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', dirname):
        return False, "Directory name can only contain letters, numbers, hyphens, and underscores"

    # Reserved names
    reserved = ['addons', 'filestore', 'config', 'data', 'logs']
    if dirname.lower() in reserved:
        return False, f"'{dirname}' is a reserved name"

    return True, None
