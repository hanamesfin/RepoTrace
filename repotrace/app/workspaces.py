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
import time
import uuid
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


def auto_capture_versions(ws_id, repo, limit=20, root=None):
    """Read the latest commits from the repo and add them as versions.

    This is called when opening a workspace to keep it up-to-date.
    Returns the updated workspace.
    """
    from repotrace.changes.git_snapshot import run_git, GitError
    ws = _load(ws_id, root)
    if ws is None:
        raise ValueError('Workspace not found.')
    try:
        lines = run_git(repo, 'log', '-n', str(limit),
                        '--format=%H%x09%cs%x09%an%x09%s').decode('utf-8', 'replace').splitlines()
    except GitError:
        return ws  # the repo may have been moved; don't crash
    for line in lines:
        parts = (line.split('\t') + [''] * 4)[:4]
        commit, date, author, subject = parts
        if not commit:
            continue
        add_version(ws_id, commit, subject=subject, author=author, root=root)
    # reload after all additions
    return _load(ws_id, root)


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
