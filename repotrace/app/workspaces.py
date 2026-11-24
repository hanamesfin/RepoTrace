"""Workspace management for RepoTrace.

A workspace is a named container that tracks a project over time. Each time the
user opens the project (or pushes / uploads a new version), a snapshot is added.
The workspace remembers every version so the user can see how the project evolved
and use all platform features (change impact graph, recommendations, etc.) across
those versions.

Workspaces live in ~/.repotrace/workspaces/<id>.json. The JSON file is small
(metadata only, not the actual code). No code is copied or moved; each version
points to a commit in the original repository.

This module is entirely additive — it does not change any existing analysis,
server, or UI path.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

DEFAULT_DIR = Path.home() / '.repotrace' / 'workspaces'


def _ws_dir(root=None):
    d = Path(root) if root else DEFAULT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(ws_id, root=None):
    path = _ws_dir(root) / f'{ws_id}.json'
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _save(ws, root=None):
    path = _ws_dir(root) / f'{ws["id"]}.json'
    path.write_text(json.dumps(ws, indent=2))


# ---- public API ----

def create_workspace(name, repo, description='', root=None):
    """Create a new workspace linked to a repository path.

    Returns the workspace dict.
    """
    name = str(name or '').strip()
    if not name:
        raise ValueError('Give the workspace a name.')
    if len(name) > 100:
        raise ValueError('The workspace name is too long (100 characters max).')
    repo = str(repo or '').strip()
    if not repo:
        raise ValueError('Choose a project folder for the workspace.')
    ws_id = uuid.uuid4().hex[:12]
    repo_name = Path(repo).name
    ws = {
        'id': ws_id,
        'name': name,
        'description': str(description or '').strip()[:500],
        'repo': repo,
        'repo_name': repo_name,
        'created': int(time.time() * 1000),
        'updated': int(time.time() * 1000),
        'versions': [],
    }
    _save(ws, root)
    return ws


def add_version(ws_id, commit, subject='', author='', branch='', root=None):
    """Record a new version (commit) in the workspace.

    If the commit already exists, it is not duplicated; the timestamp is refreshed.
    Returns the updated workspace.
    """
    ws = _load(ws_id, root)
    if ws is None:
        raise ValueError('Workspace not found.')
    commit = str(commit or '').strip()
    if not commit:
        raise ValueError('No commit was given.')
    # deduplicate
    existing = next((v for v in ws['versions'] if v['commit'] == commit), None)
    if existing:
        existing['seen'] = int(time.time() * 1000)
    else:
        ws['versions'].append({
            'commit': commit,
            'short': commit[:8],
            'subject': str(subject or '').strip()[:120],
            'author': str(author or '').strip()[:80],
            'branch': str(branch or '').strip()[:80],
            'added': int(time.time() * 1000),
            'seen': int(time.time() * 1000),
        })
    ws['updated'] = int(time.time() * 1000)
    _save(ws, root)
    return ws


def list_workspaces(root=None):
    """Return all workspaces, most recently updated first."""
    d = _ws_dir(root)
    items = []
    for f in d.glob('*.json'):
        try:
            ws = json.loads(f.read_text())
            if isinstance(ws, dict) and ws.get('id'):
                items.append(ws)
        except (OSError, ValueError):
            pass
    items.sort(key=lambda w: w.get('updated', 0), reverse=True)
    return items


def get_workspace(ws_id, root=None):
    """Return one workspace by id, or None."""
    return _load(ws_id, root)


def rename_workspace(ws_id, name, root=None):
    """Rename a workspace. Returns the updated workspace."""
    ws = _load(ws_id, root)
    if ws is None:
        raise ValueError('Workspace not found.')
    name = str(name or '').strip()
    if not name:
        raise ValueError('Give the workspace a name.')
    if len(name) > 100:
        raise ValueError('The workspace name is too long (100 characters max).')
    ws['name'] = name
    ws['updated'] = int(time.time() * 1000)
    _save(ws, root)
    return ws


def delete_workspace(ws_id, root=None):
    """Delete a workspace. Returns True if it existed."""
    path = _ws_dir(root) / f'{ws_id}.json'
    if path.exists():
        path.unlink()
        return True
    return False


def is_git_repo(path):
    """Check if a path is inside a Git repository."""
    p = Path(path)
    if not p.is_dir():
        return False
    try:
        from repotrace.changes.git_snapshot import run_git
        out = run_git(p, 'rev-parse', '--is-inside-work-tree')
        return out.decode().strip() == 'true'
    except Exception:
        return False


def snapshot_working_tree(repo, subject=None, author=None):
    """Create a non-destructive Git snapshot commit of the working tree without moving HEAD or touching user index.

    Returns a dict with commit metadata, or None if the working tree has no uncommitted changes.
    """
    from repotrace.changes.git_snapshot import run_git, GitError, resolve_commit
    p = Path(repo).resolve()
    if not is_git_repo(p):
        return None
    try:
        status = run_git(p, 'status', '--porcelain').decode('utf-8', 'replace').strip()
    except GitError:
        return None
    if not status:
        return None

    try:
        head = resolve_commit(p, 'HEAD')
    except GitError:
        head = None

    temp_idx = Path(tempfile.gettempdir()) / f"rt_idx_{uuid.uuid4().hex}"
    env = dict(os.environ,
               GIT_OPTIONAL_LOCKS='0',
               GIT_TERMINAL_PROMPT='0',
               LC_ALL='C',
               GIT_INDEX_FILE=str(temp_idx))
    try:
        if head:
            subprocess.run(['git', '-C', str(p), 'read-tree', head], env=env, check=True, capture_output=True)
        subprocess.run(['git', '-C', str(p), 'add', '-A'], env=env, check=True, capture_output=True)
        tree_sha = subprocess.check_output(['git', '-C', str(p), 'write-tree'], env=env).decode().strip()
        if head:
            head_tree = subprocess.check_output(['git', '-C', str(p), 'rev-parse', f'{head}^{{tree}}'], env=env).decode().strip()
            if tree_sha == head_tree:
                return None

        now_str = time.strftime('%b %d, %H:%M')
        msg = str(subject or '').strip() or f'Working copy snapshot ({now_str})'
        auth = str(author or '').strip()
        if not auth:
            try:
                auth = subprocess.check_output(['git', '-C', str(p), 'config', 'user.name'], env=env).decode().strip()
            except Exception:
                auth = 'Working Copy'

        cmd = ['git', '-C', str(p), 'commit-tree', tree_sha]
        if head:
            cmd.extend(['-p', head])
        cmd.extend(['-m', msg])
        commit_sha = subprocess.check_output(cmd, env=env).decode().strip()
        return {
            'commit': commit_sha,
            'short': commit_sha[:8],
            'subject': msg[:120],
            'author': auth[:80],
            'is_snapshot': True,
        }
    except Exception:
        return None
    finally:
        if temp_idx.exists():
            try:
                temp_idx.unlink()
            except OSError:
                pass


def snapshot_directory_to_mirror(ws_id, source_dir, subject=None, author=None, root=None):
    """Mirror a non-git directory into a workspace git mirror and commit it as a new version."""
    from repotrace.changes.git_snapshot import run_git
    mirror = _ws_dir(root) / 'mirrors' / f"ws_{ws_id}"
    mirror.mkdir(parents=True, exist_ok=True)
    if not (mirror / '.git').is_dir():
        run_git(mirror, 'init', '-b', 'main')
        run_git(mirror, 'config', 'user.name', author or 'RepoTrace')
        run_git(mirror, 'config', 'user.email', 'repotrace@localhost')

    src = Path(source_dir).resolve()
    for item in mirror.iterdir():
        if item.name == '.git':
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            try:
                item.unlink()
            except OSError:
                pass

    for item in src.iterdir():
        if item.name in ('.git', '__pycache__', '.DS_Store'):
            continue
        dest = mirror / item.name
        if item.is_dir():
            shutil.copytree(item, dest, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc'))
        else:
            shutil.copy2(item, dest)

    run_git(mirror, 'add', '-A')
    status = run_git(mirror, 'status', '--porcelain').decode().strip()
    if not status:
        try:
            head = run_git(mirror, 'rev-parse', 'HEAD').decode().strip()
            return head, False
        except Exception:
            pass

    msg = str(subject or '').strip() or f"Version snapshot from {src.name} ({time.strftime('%b %d, %H:%M')})"
    auth = str(author or '').strip() or 'Local Directory'
    run_git(mirror, 'commit', '-m', msg)
    commit = run_git(mirror, 'rev-parse', 'HEAD').decode().strip()
    return commit, True


def snapshot_zip_to_mirror(ws_id, zip_bytes, filename='archive.zip', subject=None, author=None, root=None):
    """Extract an uploaded zip archive into a mirror and record it as a workspace version."""
    with tempfile.TemporaryDirectory() as td:
        zf_path = Path(td) / 'upload.zip'
        zf_path.write_bytes(zip_bytes)
        extract_dir = Path(td) / 'extracted'
        extract_dir.mkdir()
        with zipfile.ZipFile(zf_path, 'r') as zf:
            zf.extractall(extract_dir)
        children = [c for c in extract_dir.iterdir() if c.name != '__MACOSX' and not c.name.startswith('.')]
        content_dir = children[0] if (len(children) == 1 and children[0].is_dir()) else extract_dir
        msg = str(subject or '').strip() or f"Uploaded {filename} ({time.strftime('%b %d, %H:%M')})"
        auth = str(author or '').strip() or 'Upload'
        commit, is_new = snapshot_directory_to_mirror(ws_id, content_dir, subject=msg, author=auth, root=root)
        mirror = _ws_dir(root) / 'mirrors' / f"ws_{ws_id}"
        ws = _load(ws_id, root)
        if ws:
            ws['repo'] = str(mirror)
            ws['repo_name'] = filename
            _save(ws, root)
            if is_new:
                ws = add_version(ws_id, commit, subject=msg, author=auth, root=root)
        return ws, is_new


def update_workspace_repo(ws_id, new_repo, capture_snapshot=True, snapshot_note='', author='', root=None):
    """Update the repository folder of a workspace and capture its latest versions."""
    ws = _load(ws_id, root)
    if ws is None:
        raise ValueError('Workspace not found.')
    new_repo = str(new_repo or '').strip()
    p = Path(new_repo)
    if not p.is_dir():
        raise ValueError('The project folder does not exist.')
    ws['repo'] = str(p.resolve())
    ws['repo_name'] = p.name
    ws['updated'] = int(time.time() * 1000)
    _save(ws, root)
    return auto_capture_versions(ws_id, ws['repo'], capture_snapshot=capture_snapshot,
                                 snapshot_note=snapshot_note, author=author, root=root)


def fetch_workspace_updates(ws_id, root=None):
    """Run git fetch on the workspace repository if a remote exists, then capture new versions."""
    from repotrace.changes.git_snapshot import run_git, GitError
    ws = _load(ws_id, root)
    if ws is None:
        raise ValueError('Workspace not found.')
    repo = ws.get('repo', '')
    if not repo or not Path(repo).is_dir():
        raise ValueError('The workspace project folder does not exist.')
    try:
        remotes = run_git(repo, 'remote').decode().strip().splitlines()
        if remotes:
            remote_name = 'origin' if 'origin' in remotes else remotes[0].strip()
            run_git(repo, 'fetch', '--prune', remote_name)
    except GitError:
        pass  # fetch may fail if offline; still capture local commits
    return auto_capture_versions(ws_id, repo, limit=50, capture_snapshot=False, root=root)


def auto_capture_versions(ws_id, repo, limit=50, capture_snapshot=True, snapshot_note='', author='', root=None):
    """Read the latest commits from the repo and add them as versions.

    If uncommitted changes exist, snapshots them non-destructively.
    Returns the updated workspace.
    """
    from repotrace.changes.git_snapshot import run_git, GitError
    ws = _load(ws_id, root)
    if ws is None:
        raise ValueError('Workspace not found.')
    p = Path(repo).resolve()
    if not p.is_dir():
        return ws

    if not is_git_repo(p):
        commit, is_new = snapshot_directory_to_mirror(ws_id, p, subject=snapshot_note, author=author, root=root)
        mirror = _ws_dir(root) / 'mirrors' / f"ws_{ws_id}"
        ws['repo'] = str(mirror)
        _save(ws, root)
        if is_new:
            ws = add_version(ws_id, commit, subject=snapshot_note or f"Snapshot: {p.name}", author=author or 'Local', root=root)
        return _load(ws_id, root)

    try:
        lines = run_git(p, 'log', '-n', str(limit),
                        '--format=%H%x09%cs%x09%an%x09%s').decode('utf-8', 'replace').splitlines()
    except GitError:
        lines = []

    existing = {v['commit'] for v in ws.get('versions', [])}
    added_count = 0
    # Add commits in chronological order (oldest to newest)
    for line in reversed(lines):
        parts = (line.split('\t') + [''] * 4)[:4]
        commit, date, c_author, subject = parts
        if not commit or commit in existing:
            continue
        add_version(ws_id, commit, subject=subject, author=c_author, root=root)
        existing.add(commit)
        added_count += 1

    # Check uncommitted working tree changes
    if capture_snapshot:
        snap = snapshot_working_tree(p, subject=snapshot_note, author=author)
        if snap and snap['commit'] not in existing:
            is_dup_tree = False
            if ws.get('versions'):
                try:
                    last_c = ws['versions'][-1]['commit']
                    t_last = run_git(p, 'rev-parse', f'{last_c}^{{tree}}').decode().strip()
                    t_snap = run_git(p, 'rev-parse', f'{snap["commit"]}^{{tree}}').decode().strip()
                    if t_last == t_snap:
                        is_dup_tree = True
                except Exception:
                    pass
            if not is_dup_tree:
                add_version(ws_id, snap['commit'], subject=snap['subject'], author=snap['author'], root=root)
                existing.add(snap['commit'])
                added_count += 1

    ws = _load(ws_id, root)
    if ws is not None:
        ws['_last_added_count'] = added_count
    return ws


def compare_versions(ws_id, base_index, head_index, root=None):
    """Return the (base_commit, head_commit) for two version indices in a workspace.

    This lets the UI say "compare version 3 with version 5" without knowing commit hashes.
    """
    ws = _load(ws_id, root)
    if ws is None:
        raise ValueError('Workspace not found.')
    versions = ws.get('versions', [])
    if not (0 <= base_index < len(versions) and 0 <= head_index < len(versions)):
        raise ValueError('Version index out of range.')
    if base_index == head_index:
        raise ValueError('Choose two different versions to compare.')
    return versions[base_index]['commit'], versions[head_index]['commit']


def workspace_summary(ws):
    """A small public-safe dict for listing workspaces in the UI."""
    return {
        'id': ws['id'],
        'name': ws['name'],
        'description': ws.get('description', ''),
        'repo': ws['repo'],
        'repo_name': ws.get('repo_name', ''),
        'created': ws.get('created', 0),
        'updated': ws.get('updated', 0),
        'version_count': len(ws.get('versions', [])),
        'latest_version': ws['versions'][-1] if ws.get('versions') else None,
    }
