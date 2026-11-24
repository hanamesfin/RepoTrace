"""RepoTrace as a local app: pick a project and two commits in the browser, read the results.

    python3 -m repotrace [path/to/repo] [--port N] [--no-browser]

Runs only on this computer (127.0.0.1). It reads Git history; it never runs your project's code and
never changes your repository. Every request needs a random per-launch token, so other web pages
cannot talk to it. A GitHub sign-in, when you use one, keeps the token in ~/.repotrace on this
computer and out of the browser.
"""
import argparse
import hmac
import json
import hashlib
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlparse

from repotrace.app import examples, github_auth, remote_auth, workspaces
from repotrace.changes.change_impact import analyze_change_impact
from repotrace.graph.graph_explore import Explorer
from repotrace.graph.graph_index import GraphIndex
from repotrace.graph.structure import build_structure
from repotrace.mapping.repository import analyze_repository, pytest_source_roots
from repotrace.report import lab_data
from repotrace.report.dashboard import SourceReader, build_view, render_html
from repotrace.report.overview import SnapshotReader, build_overview
from repotrace.changes.git_snapshot import GitError, check_repository, run_git, worktree_is_dirty

MAX_BODY = 64 * 1024
MAX_JOBS = 12
TEMPLATE = Path(__file__).resolve().parent.parent / 'report' / 'dashboard_template.html'
LAB_DIR = Path(__file__).resolve().parent.parent / 'report' / 'lab'
LAB_FILES = {'app.js': 'application/javascript', 'model.js': 'application/javascript', 'picker.js': 'application/javascript',
             'theme.js': 'application/javascript', 'settings.js': 'application/javascript', 'style.css': 'text/css',
             'explore.html': 'text/html', 'explore.js': 'application/javascript', 'explore.css': 'text/css', 'icon.svg': 'image/svg+xml'}
LAB_CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-src 'self'; "
           "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
# the explorer page may only be shown inside this app, and it never talks to the network
EXPLORE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'")
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; "
       "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
STAGES = ['check', 'analyze_before', 'analyze_after', 'compare', 'impact', 'finish']


# ------------------------------------------------------------------ repository helpers

def no_map_message(folder, report, roots):
    """Say why there is no map: no Python files at all, files that could not be read, or settings that hide them."""
    found = python_files_on_disk(folder)
    if not found:
        return 'No Python files were found in that folder.'
    bad = [f for f in report.get('files', []) if f['status'] != 'ok']
    if bad:
        first = bad[0]
        reason = ((first.get('diagnostics') or [{}])[0]).get('message') or 'unknown problem'
        return f"Found {len(found)} Python file{'s' if len(found) != 1 else ''}, but none could be read. First problem: {first['file']}: {reason}"
    reason = ((report.get('diagnostics') or [{}])[0]).get('message')
    return (f"Found {len(found)} Python file{'s' if len(found) != 1 else ''}, but none were analyzed"
            f" with the source folder{'s' if len(roots) != 1 else ''} {', '.join(roots) or '.'}." + (f' {reason}' if reason else ' Check "Where your code lives".'))


def changed_on_disk(folder, file, sha):
    """True when the file on disk is no longer the one the map was made from."""
    try:
        return hashlib.sha256((Path(folder) / file).read_bytes()).hexdigest() != sha
    except OSError:
        return True


def friendly(error, base=None, head=None):
    """Plain-words version of a failure, for people who have never seen a traceback."""
    text = str(error)
    if ('not a Git working tree' in text or 'Choose an existing local repository' in text
            or 'not a git repository' in text.lower()):
        return ('That folder is not a Git project (it has no .git folder). Pick the top folder of a project '
                'that is tracked with Git.')
    if text.startswith('Cannot resolve'):
        return text.replace("to a commit in this repository.", 'in this project. Check the spelling, or pick it from the list.')
    if 'ambiguous argument' in text or 'unknown revision' in text or 'does not have any commits' in text:
        return 'This project has no commits yet, so there is nothing to compare.'
    if 'Git is not installed' in text:
        return 'Git is not installed on this computer, or it is not on the PATH.'
    if 'timed out' in text:
        return 'Git took too long to answer. Try again, or pick smaller commits.'
    return text


def _lines(repo, *args):
    return run_git(repo, *args).decode('utf-8', 'replace').splitlines()


def detect_source_roots(repo, commit='HEAD'):
    """Suggest source roots. A wrong root silently hides links, so say why we chose it."""
    return suggest_roots([p for p in _lines(repo, 'ls-tree', '-r', '--name-only', commit) if p.endswith('.py')])


def python_files_on_disk(folder, limit=20000):
    """Relative paths of the .py files in a folder, skipping hidden, virtual-environment and cache folders."""
    skip = {'venv', 'env', 'node_modules', '__pycache__', 'site-packages', 'build', 'dist'}
    found = []
    for here, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in skip]
        found += [os.path.relpath(os.path.join(here, f), folder).replace(os.sep, '/') for f in files if f.endswith('.py')]
        if len(found) >= limit:
            break
    return found


def suggest_roots(py):
    ignored = {'tests', 'test', 'scripts', 'docs', 'doc', 'examples', 'tools'}
    in_src = [p for p in py if p.startswith('src/')]
    other = [p for p in py if not p.startswith('src/') and p.split('/')[0] not in ignored
             and p not in {'setup.py', 'conftest.py'}]
    if in_src and len(in_src) >= len(other):
        return {'roots': ['src'], 'reason': 'Your code is under a src/ folder, so imports are read from src.'}
    return {'roots': ['.'], 'reason': 'Your code is at the top of the project, so imports are read from there.'}


def inspect_repo(path):
    repo = check_repository(path)
    try:
        head = run_git(repo, 'rev-parse', 'HEAD').decode().strip()
    except GitError:
        raise GitError('This project has no commits yet.')
    current = run_git(repo, 'rev-parse', '--abbrev-ref', 'HEAD').decode().strip()
    refs = {'branches': [], 'tags': []}
    fmt = '%(refname)%09%(refname:short)%09%(objectname)%09%(*objectname)%09%(creatordate:short)%09%(subject)'
    for line in _lines(repo, 'for-each-ref', f'--format={fmt}', 'refs/heads', 'refs/remotes', 'refs/tags'):
        full, short, obj, peeled, date, subject = (line.split('\t') + [''] * 6)[:6]
        if full.endswith('/HEAD'):
            continue
        entry = {'name': short, 'commit': peeled or obj, 'date': date, 'subject': subject[:80]}
        if full.startswith('refs/tags/'):
            refs['tags'].append(entry)
        else:
            entry['remote'] = full.startswith('refs/remotes/')
            entry['current'] = short == current
            refs['branches'].append(entry)
    log = [l.split('\t', 4) for l in _lines(repo, 'log', '-n', '80', '--format=%H%x09%h%x09%cs%x09%an%x09%s', head)]
    commits = [{'commit': c, 'short': s, 'date': d, 'author': a, 'subject': subj[:90]} for c, s, d, a, subj in log]
    default = next((b['name'] for b in refs['branches'] if b['name'] in ('main', 'master') and not b['remote']), None)
    return {'repo': str(repo), 'name': repo.name, 'head': head, 'current_branch': current,
            'default_branch': default, 'dirty': worktree_is_dirty(repo), 'commit_count': len(commits),
            'commits': commits, 'branches': refs['branches'], 'tags': sorted(refs['tags'], key=lambda t: t['date'], reverse=True),
            'source_roots': detect_source_roots(repo)}


DEMO_FILES = {
    'pricing.py': 'TAX = 1.15\n\n\ndef calculate_total(price):\n    return price * TAX\n\n\ndef old_discount(price):\n    return price * 0.9\n',
    'orders.py': 'from pricing import calculate_total\n\n\ndef place_order(price):\n    return calculate_total(price)\n',
    'checkout.py': 'from orders import place_order\n\n\ndef checkout(price):\n    return place_order(price)\n',
    'legacy.py': 'import pricing\n\n\ndef report(price):\n    return pricing.old_discount(price)\n'}


def make_demo_repo(parent):
    """A tiny two-commit project that shows the main ideas (changed function, forgotten caller)."""
    repo = Path(parent) / 'example-shop'
    repo.mkdir()
    env = {**os.environ, 'GIT_AUTHOR_NAME': 'Example', 'GIT_AUTHOR_EMAIL': 'example@example.com',
           'GIT_COMMITTER_NAME': 'Example', 'GIT_COMMITTER_EMAIL': 'example@example.com',
           'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_SYSTEM': os.devnull}

    def git(*args):
        subprocess.run(['git', '-C', str(repo), *args], env=env, check=True, capture_output=True)
    git('init', '-q', '-b', 'main')
    for name, text in DEMO_FILES.items():
        (repo / name).write_text(text)
    git('add', '.')
    git('commit', '-q', '-m', 'Add the shop code')
    (repo / 'pricing.py').write_text('TAX = 1.15\n\n\ndef calculate_total(price):\n    return round(price * TAX, 2)\n')
    git('commit', '-q', '-a', '-m', 'Round totals; remove old_discount')
    return repo


def browse_for_folder():
    """Ask macOS for a folder with its own dialog. Returns a path, or None if cancelled/unsupported."""
    if platform.system() != 'Darwin':
        return None
    try:
        done = subprocess.run(['osascript', '-e', 'POSIX path of (choose folder with prompt "Choose your project folder")'],
                              capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip().rstrip('/') or None if done.returncode == 0 else None


# ------------------------------------------------------------------ clone into ~/.repotrace/mirrors

_CLONE_HOST = re.compile(r'^[A-Za-z0-9.-]{1,253}$')
_CLONE_SEGMENT = re.compile(r'^[A-Za-z0-9_.-]{1,100}$')
_GITHUB_HOSTS = ('github.com', 'www.github.com')


def _folder_segment(part, strip_git=False):
    text = '' if part is None else str(part).strip()
    if strip_git and text.lower().endswith('.git'):
        text = text[:-4]
    if not text or not _CLONE_SEGMENT.fullmatch(text):
        raise ValueError('That address cannot be used as a folder name.')
    return text


def _clean_host(host):
    host = '' if host is None else str(host).strip().lower()
    if not host or not _CLONE_HOST.fullmatch(host) or '..' in host or host.startswith('.') or host.endswith('.'):
        raise ValueError('That address does not name a host RepoTrace can clone.')
    return host


def parse_clone_request(url, kind):
    """Turn a pasted address into a host and folder names. Rejects secrets and odd paths."""
    text = '' if url is None else str(url).strip()
    if not text or any(ch.isspace() or ord(ch) < 32 for ch in text) or text.startswith('-'):
        raise ValueError('Enter a repository address with no spaces.')
    kind = '' if kind is None else str(kind).strip().lower()
    if kind == 'ssh':
        return _parse_ssh_url(text)
    if kind == 'https':
        return _parse_https_url(text)
    raise ValueError('Choose Clone Repository or Connect via SSH.')


def _parse_https_url(text):
    if text.startswith('git@') or text.lower().startswith('ssh://'):
        raise ValueError('That is an SSH address. Use Connect via SSH.')
    if not text.lower().startswith('https://'):
        raise ValueError('Use an https address, for example https://github.com/owner/repo.git.')
    parts = urlsplit(text)
    if parts.username or parts.password:
        raise ValueError('That address includes a secret. Paste the repository address without a token.')
    if parts.query or parts.fragment:
        raise ValueError('Paste the repository address only, without a query or a fragment.')
    host = _clean_host(parts.hostname)
    raw = [piece for piece in parts.path.split('/') if piece]
    if len(raw) < 2 or any(piece in ('.', '..') for piece in raw):
        raise ValueError('That address needs an owner and a repository.')
    segments = [_folder_segment(piece, strip_git=(index == len(raw) - 1)) for index, piece in enumerate(raw)]
    return {
        'transport': 'https', 'host': host, 'segments': segments,
        'url': 'https://{host}/{path}.git'.format(host=host, path='/'.join(segments)),
    }


def _parse_ssh_url(text):
    lowered = text.lower()
    if lowered.startswith('https://') or lowered.startswith('http://') or lowered.startswith('ssh://'):
        raise ValueError('Use an SSH address like git@host:owner/repo.git.')
    if text.count('@') != 1:
        raise ValueError('Use an SSH address like git@host:owner/repo.git. RepoTrace does not collect SSH keys.')
    user, _, rest = text.partition('@')
    if user != 'git' or ':' not in rest or '\\' in rest:
        raise ValueError('Use an SSH address like git@host:owner/repo.git. RepoTrace does not collect SSH keys.')
    host, _, path = rest.partition(':')
    host = _clean_host(host)
    if not path or path.startswith(('/', '-')):
        raise ValueError('Use an SSH address like git@host:owner/repo.git.')
    raw = [piece for piece in path.split('/') if piece]
    if len(raw) < 2 or any(piece in ('.', '..') for piece in raw):
        raise ValueError('That SSH address needs an owner and a repository.')
    segments = [_folder_segment(piece, strip_git=(index == len(raw) - 1)) for index, piece in enumerate(raw)]
    return {
        'transport': 'ssh', 'host': host, 'segments': segments,
        'url': 'git@{host}:{path}.git'.format(host=host, path='/'.join(segments)),
    }


def clone_destination(home, parsed):
    """A folder under ~/.repotrace/mirrors, and nowhere else."""
    root = (Path(home) / '.repotrace' / 'mirrors').resolve()
    if parsed['host'] in _GITHUB_HOSTS and len(parsed['segments']) == 2:
        dest = root.joinpath(parsed['segments'][0], parsed['segments'][1])
    else:
        dest = root.joinpath(parsed['host'], *parsed['segments'])
    dest = dest.resolve()
    if dest == root or root not in dest.parents:
        raise ValueError('That address cannot be cloned into the mirror folder.')
    return dest


def plan_clone(home, url, kind):
    """Where a clone would go. Does not create the folder and does not run git."""
    parsed = parse_clone_request(url, kind)
    dest = clone_destination(home, parsed)
    exists = (dest / '.git').is_dir()
    return {
        'url': parsed['url'], 'dest': str(dest), 'exists': exists,
        'blocked': dest.exists() and not exists,
        'action': 'fetch' if exists else 'clone',
        'host': parsed['host'], 'transport': parsed['transport'],
    }


def clone_may_use_github_token(plan):
    """Only an https GitHub address may see the saved token, and only as an environment header."""
    return plan.get('transport') == 'https' and plan.get('host') in _GITHUB_HOSTS


def clone_may_use_remote_token(plan, state):
    """Check if the clone plan can use a saved token for GitHub, GitLab, or Azure DevOps."""
    if plan.get('transport') != 'https':
        return None
    host = plan.get('host', '').lower()
    if host in _GITHUB_HOSTS:
        saved = state.github._load()
        if saved and saved.get('token'):
            state.github.remember_secret(saved['token'])
            return saved['token']
    if 'gitlab' in host:
        token = state.gitlab.get_token()
        if token:
            return token
    if 'dev.azure.com' in host or 'visualstudio.com' in host:
        token = state.azure.get_token()
        if token:
            import base64
            return f"Basic {base64.b64encode(f':{token}'.encode()).decode('ascii')}"
    return None


def perform_clone(home, url, kind, confirm, token=None, git_run=None):
    """Clone, or fetch --prune when the mirror folder is already a Git checkout.

    ``confirm`` must be the destination ``plan_clone`` showed. Nothing is pulled,
    reset, or checked out on an existing folder. The token is never an argument.
    """
    plan = plan_clone(home, url, kind)
    if confirm != plan['dest']:
        raise ValueError('Confirm the folder shown on screen before cloning.')
    if plan['blocked']:
        raise ValueError(plan['dest'] + ' already exists and is not a Git clone. RepoTrace will not replace it.')
    if token and any(token in str(part) for part in (plan['url'], plan['dest'])):
        raise ValueError('Refusing to put the token in the clone.')
    root = Path(home) / '.repotrace'
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    (root / 'mirrors').mkdir(parents=True, exist_ok=True)
    runner = git_run or github_auth.run_git
    dest = Path(plan['dest'])
    if plan['action'] == 'fetch':
        runner(['-C', str(dest), 'fetch', '--prune'], token=token)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        runner(['clone', '--origin', 'origin', plan['url'], str(dest)], token=token)
    if token:
        github_auth.reject_token_in_clone(dest, token)
    return {'repo': str(dest), 'name': dest.name, 'action': plan['action']}


# ------------------------------------------------------------------ jobs

class Cancelled(Exception):
    """The person stopped the job. Raised from the progress callback, so the work unwinds at its next step."""


def lab_direction(base, head, reverse):
    """The one place a reversal is applied: (analysis_base, analysis_head, reversed).

    The analysis always runs base -> head. Reversing swaps the two commits once, here, and nowhere else,
    so asking again with the same pair and the opposite answer always gives the opposite direction.
    Only the analysis is turned around; the repository is never touched."""
    reverse = bool(reverse) and bool(base) and bool(head)
    return (head, base, True) if reverse else (base, head, False)


class Job:
    def __init__(self, params):
        self.id = uuid.uuid4().hex[:12]
        self.params = params
        self.state, self.stage, self.detail = 'running', 'check', ''
        self.seen = ['check']
        self.marks = {'check': 0.0}    # seconds after the start at which each step began
        self.cancelled = threading.Event()
        self.error = self.view = None
        self.explorers = {}
        self.snapshot = None           # a map keeps the source it was made from: {file: (text, sha256)}
        self.created = time.time()
        self.lock = threading.Lock()

    def update(self, stage, detail=''):
        if self.cancelled.is_set():
            raise Cancelled()
        with self.lock:
            self.stage, self.detail = stage, detail
            if stage not in self.seen:
                self.seen.append(stage)
                self.marks[stage] = round(time.time() - self.created, 1)

    def run_map(self):
        """Map the folder as it is on disk: no Git history and no second version needed."""
        p = self.params
        folder = Path(p['repo'])
        self.update('check', 'Looking for Python files')
        roots = p['source_roots'] or suggest_roots(python_files_on_disk(folder))['roots']
        self.update('analyze_after', 'Reading every file and linking the calls')
        report = analyze_repository(folder, source_roots=roots)
        if not report.get('files') or report['status'] == 'error':
            raise ValueError(no_map_message(folder, report, roots))
        self.update('finish', 'Preparing the map')
        index = GraphIndex(report, include_possible=True)
        explorer = Explorer(index)
        failed = [f for f in report['files'] if f['status'] != 'ok']
        snapshot = {f['file']: (f['source'], f['content_sha256']) for f in report['files'] if f['status'] == 'ok' and f.get('source') is not None}
        view = {'kind': 'map', 'made_at': time.strftime('%H:%M'), 'repository': folder.name, 'repo': str(folder), 'status': 'ok' if not failed else 'partial',
                'overview': build_overview(index, explorer, folder.name), 'structure': build_structure(report),
                'settings': {'source_roots': roots, 'include_possible': True},
                'coverage': {'after': {'calls': index.coverage['calls'], 'unresolved_calls': index.coverage['unresolved_calls']}},
                'gaps': [{'type': 'analysis_failed', 'file': f['file'], 'message': 'This file could not be read, so its functions are missing from the map.'}
                         for f in failed],
                'warnings': [d if isinstance(d, str) else str(d.get('message', d)) for d in report.get('diagnostics', [])][:40],
                'files': [], 'changes': [], 'summary': {}, 'source_available': True}
        with self.lock:
            self.view, self.explorers, self.snapshot, self.state = view, {'after': explorer}, snapshot, 'done'

    def run_lab(self):
        """The guided screens: the working folder as it is on disk, plus one comparison of two versions when asked."""
        p = self.params
        folder = Path(p['repo'])
        self.update('check', 'Looking for Python files')
        roots = p['source_roots'] or None
        if roots is None and not pytest_source_roots(folder)[0]:      # pytest's own declared paths win; else suggest src/ or the top folder
            roots = suggest_roots(python_files_on_disk(folder))['roots']
        self.update('map', 'Reading every file and linking the calls')
        report = analyze_repository(folder, source_roots=roots)
        if not report.get('files') or report['status'] == 'error':
            raise ValueError(no_map_message(folder, report, roots or ['.']))
        try:
            head = run_git(folder, 'rev-parse', '--short', 'HEAD').decode().strip()
            version = f"working folder (commit {head}{', plus unsaved edits' if worktree_is_dirty(folder) else ''})"
        except (GitError, OSError):
            version = 'working folder'
        main_graph, _ = lab_data.build_graph(report, version, folder.name)
        reviews, graphs = [], {}
        if p.get('base') and p.get('head'):
            keep = {}

            def tell(stage, detail):
                if stage == 'check':       # the engine repeats its own check; the page is already past that step
                    return
                self.update(stage, detail)

            change = analyze_change_impact(folder, p['base'], p['head'], source_roots=roots, include_possible=True, progress=tell, keep=keep)
            self.update('finish', 'Preparing the screens')
            view = build_view(change, str(folder))
            review, graph = lab_data.build_review(change, view, keep['reports'], str(folder), folder.name)
            reverse = bool(p.get('reverse'))
            # `selection` is the pair the person chose, before any reversal: asking for it again with the opposite answer flips the direction.
            review['reversed'] = reverse
            review['selection'] = ({'base': review['head_commit'], 'head': review['base_commit']} if reverse
                                   else {'base': review['base_commit'], 'head': review['head_commit']})
            if reverse:                    # the title names the change being undone: the newer version, which is the analysis' starting point
                review['label'] = (view['base'].get('subject') or '').strip() or review['label']
            reviews, graphs = [review], {review['graph']: graph}
        else:
            self.update('finish', 'Preparing the screens')
        data = lab_data.payload(folder.name, main_graph, reviews, graphs)
        data['project']['mode'] = 'live'
        data['project']['repo'] = str(folder)
        with self.lock:
            self.view, self.explorers, self.snapshot, self.state = {'kind': 'lab', 'data': data}, {}, {}, 'done'

    def run(self):
        p = self.params
        try:
            if p.get('kind') == 'map':
                self.run_map()
                return
            if p.get('kind') == 'lab':
                self.run_lab()
                return
            keep = {}
            report = analyze_change_impact(p['repo'], p['base'], p['head'], source_roots=p['source_roots'] or None,
                                           include_possible=p['include_possible'], progress=self.update, keep=keep)
            self.update('finish', 'Preparing the page')
            view = build_view(report, p['repo'])
            explorers = {'before': Explorer(keep['indexes']['before']), 'after': Explorer(keep['indexes']['after'])} \
                if 'indexes' in keep else {}
            with self.lock:
                self.view, self.explorers, self.state = view, explorers, 'done'
        except Cancelled:
            with self.lock:
                self.state = 'cancelled'
        except GitError as exc:
            with self.lock:
                self.error, self.state = {'message': friendly(exc), 'kind': 'input'}, 'error'
        except ValueError as exc:
            with self.lock:
                self.error, self.state = {'message': str(exc), 'kind': 'input'}, 'error'
        except Exception as exc:       # keep the server alive; show something useful, log the rest
            traceback.print_exc()
            with self.lock:
                self.error = {'message': 'Something went wrong while analyzing: ' + type(exc).__name__ + ': ' + str(exc)[:200],
                              'kind': 'internal'}
                self.state = 'error'

    def public(self, with_view=False):
        with self.lock:
            out = {'id': self.id, 'state': self.state, 'stage': self.stage, 'detail': self.detail,
                   'seen': list(self.seen), 'marks': dict(self.marks), 'error': self.error, 'seconds': round(time.time() - self.created, 1)}
            if with_view and self.state == 'done':
                out['view'] = self.view
            return out


# ------------------------------------------------------------------ server

class AppState:
    def __init__(self, initial_repo=None, recent_file=None, page_hook=None, browse=browse_for_folder, github=None, gitlab=None, azure=None):
        self.token = secrets.token_urlsafe(24)
        self.port = None
        self.jobs, self.lock = {}, threading.Lock()
        self.initial_repo = initial_repo
        self.recent_file = Path(recent_file or os.environ.get('REPOTRACE_RECENT') or Path.home() / '.repotrace' / 'recent.json')
        self.page_hook = page_hook
        self.browse = browse
        self.demo_dir = None
        self.examples_dir = None
        self.prepared = {}
        self.github = github if github is not None else github_auth.GitHubSession()
        self.gitlab = gitlab if gitlab is not None else remote_auth.GitLabSession()
        self.azure = azure if azure is not None else remote_auth.AzureSession()

    def prepare_example(self, example_id):
        if example_id not in self.prepared:
            if self.examples_dir is None:
                self.examples_dir = tempfile.mkdtemp(prefix='repotrace-examples-')
            self.prepared[example_id] = str(examples.prepare(example_id, self.examples_dir))
        return self.prepared[example_id]

    def is_temporary(self, repo):
        for folder in (self.demo_dir, self.examples_dir):
            if folder and Path(repo).is_relative_to(Path(folder).resolve()):
                return True
        return False

    def recent(self):
        try:
            items = json.loads(self.recent_file.read_text())
        except (OSError, ValueError, TypeError):
            return []
        return [r for r in items if isinstance(r, dict) and Path(str(r.get('path', ''))).is_dir()][:8]

    def remember(self, repo, name):
        items = [r for r in self.recent() if r.get('path') != repo]
        items.insert(0, {'path': repo, 'name': name, 'opened': int(time.time() * 1000)})
        try:
            self.recent_file.parent.mkdir(parents=True, exist_ok=True)
            self.recent_file.write_text(json.dumps(items[:8]))
        except OSError:
            pass     # remembering recent projects is a convenience; never fail because of it

    def start(self, params):
        job = Job(params)
        with self.lock:
            self.jobs[job.id] = job
            for old in sorted(self.jobs.values(), key=lambda j: j.created)[:-MAX_JOBS]:
                self.jobs.pop(old.id, None)
        threading.Thread(target=job.run, daemon=True).start()
        return job

    def page(self):
        html = TEMPLATE.read_text(encoding='utf-8').replace('__TITLE__', 'RepoTrace').replace('__DATA__', 'null')
        meta = f'<meta name="rt-live" content="1"><meta name="rt-token" content="{self.token}">'
        html = html.replace('</head>', meta + '</head>', 1)
        return self.page_hook(html) if self.page_hook else html

    def lab_page(self):
        html = (LAB_DIR / 'index.html').read_text(encoding='utf-8')
        meta = f'<meta name="rt-live" content="1"><meta name="rt-token" content="{self.token}">'
        return html.replace('</head>', meta + '</head>', 1)

    def cleanup(self):
        try:
            self.github.close()
        finally:
            for folder in (self.demo_dir, self.examples_dir):
                if folder:
                    shutil.rmtree(folder, ignore_errors=True)


def make_server(host='127.0.0.1', port=0, **kwargs):
    state = AppState(**kwargs)

    class Handler(BaseHTTPRequestHandler):
        server_version = 'RepoTrace'
        protocol_version = 'HTTP/1.1'

        def log_message(self, format, *args):      # keep the terminal quiet
            pass

        # ---- helpers
        def send(self, status, body, content_type, extra=None):
            data = body.encode('utf-8') if isinstance(body, str) else body
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            if status >= 400:
                self.send_header('Connection', 'close')
                self.close_connection = True
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def json(self, status, payload):
            self.send(status, json.dumps(payload), 'application/json; charset=utf-8')

        def allowed_hosts(self):
            return {f'127.0.0.1:{state.port}', f'localhost:{state.port}'}

        def guard(self, need_token=True, query_token=None):
            if self.headers.get('Host') not in self.allowed_hosts():
                self.json(403, {'error': 'Unexpected Host header.'})
                return False
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://{h}' for h in self.allowed_hosts()}:
                self.json(403, {'error': 'Unexpected Origin.'})
                return False
            if need_token:
                given = query_token or self.headers.get('X-RepoTrace-Token') or ''
                if not hmac.compare_digest(given, state.token):
                    self.json(401, {'error': 'Missing or wrong token. Reload the page.'})
                    return False
            return True

        def body(self):
            length = int(self.headers.get('Content-Length') or 0)
            if length > MAX_BODY:
                raise ValueError('Request too large.')
            if (self.headers.get('Content-Type') or '').split(';')[0] != 'application/json':
                raise ValueError('Expected JSON.')
            return json.loads(self.rfile.read(length) or b'{}')

        # ---- routes
        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == '/':
                if not self.guard(need_token=False):
                    return
                self.send(200, state.page(), 'text/html; charset=utf-8', {'Content-Security-Policy': CSP})
            elif url.path in ('/lab', '/lab/'):
                if not self.guard(need_token=False):
                    return
                self.send(200, state.lab_page(), 'text/html; charset=utf-8', {'Content-Security-Policy': LAB_CSP})
            elif url.path.startswith('/lab/') and url.path[5:] in LAB_FILES:
                if not self.guard(need_token=False):
                    return
                name = url.path[5:]
                kind = LAB_FILES[name] if name.endswith('.svg') else LAB_FILES[name] + '; charset=utf-8'
                self.send(200, (LAB_DIR / name).read_bytes(), kind, {'Content-Security-Policy': EXPLORE_CSP} if name == 'explore.html' else None)
            elif url.path == '/api/state':
                if not self.guard():
                    return
                self.json(200, {'recent': state.recent(), 'can_browse': platform.system() == 'Darwin',
                                'initial_repo': state.initial_repo, 'platform': platform.system(),
                                'workspaces': [workspaces.workspace_summary(w) for w in workspaces.list_workspaces()]})
            elif url.path == '/api/examples':
                if not self.guard():
                    return
                self.json(200, {'examples': examples.catalog()})
            elif url.path == '/api/job':
                if not self.guard():
                    return
                job = state.jobs.get((query.get('id') or [''])[0])
                self.json(200, job.public(with_view=True)) if job else self.json(404, {'error': 'Unknown job.'})
            elif url.path in ('/api/functions', '/api/neighbors', '/api/function'):
                if not self.guard():
                    return
                self.explore(url.path, query)
            elif url.path == '/api/github/status':
                if not self.guard():
                    return
                self.json(200, github_auth.scrub_public(state.github.status()))
            elif url.path == '/api/workspaces':
                if not self.guard():
                    return
                items = workspaces.list_workspaces()
                self.json(200, {'workspaces': [workspaces.workspace_summary(w) for w in items]})
            elif url.path == '/api/workspace':
                if not self.guard():
                    return
                ws_id = (query.get('id') or [''])[0]
                ws = workspaces.get_workspace(ws_id)
                if not ws:
                    self.json(404, {'error': 'Workspace not found.'})
                else:
                    self.json(200, ws)
            elif url.path == '/api/github/repos':
                if not self.guard():
                    return
                try:
                    self.json(200, github_auth.scrub_public(state.github.list_repos()))
                except github_auth.GitHubError as exc:
                    self.json(400, {'error': github_auth.scrub_text(str(exc))})
            elif url.path == '/api/gitlab/status':
                if not self.guard():
                    return
                self.json(200, state.gitlab.status())
            elif url.path == '/api/gitlab/repos':
                if not self.guard():
                    return
                try:
                    self.json(200, state.gitlab.list_repos())
                except Exception as exc:
                    self.json(400, {'error': str(exc)})
            elif url.path == '/api/azure/status':
                if not self.guard():
                    return
                self.json(200, state.azure.status())
            elif url.path == '/api/azure/repos':
                if not self.guard():
                    return
                try:
                    self.json(200, state.azure.list_repos())
                except Exception as exc:
                    self.json(400, {'error': str(exc)})
            elif url.path == '/api/integrations/status':
                if not self.guard():
                    return
                self.json(200, {
                    'github': github_auth.scrub_public(state.github.status()),
                    'gitlab': state.gitlab.status(),
                    'azure': state.azure.status(),
                })
            elif url.path == '/api/export':
                if not self.guard(query_token=(query.get('token') or [''])[0]):
                    return
                job = state.jobs.get((query.get('id') or [''])[0])
                if not job or job.state != 'done' or job.params.get('kind') in ('map', 'lab'):
                    self.json(404, {'error': 'Nothing to export.'})
                    return
                view = job.view
                name = f"repotrace-{view['repository']}-{view['base']['commit'][:8]}-{view['head']['commit'][:8]}.html"
                self.send(200, render_html(view), 'text/html; charset=utf-8',
                          {'Content-Disposition': f'attachment; filename="{name}"'})
            else:
                self.json(404, {'error': 'Not found.'})

        def explore(self, path, query):
            one = lambda name, default='': (query.get(name) or [default])[0]
            job = state.jobs.get(one('job'))
            side = one('side', 'after')
            if not job or job.state != 'done' or side not in job.explorers:
                self.json(404, {'error': 'This analysis is not available. Run it again.'})
                return
            explorer = job.explorers[side]
            try:
                if path == '/api/functions':
                    self.json(200, {'functions': explorer.search(one('q'))})
                elif path == '/api/neighbors':
                    direction = one('direction', 'both')
                    if direction not in ('both', 'callers', 'callees'):
                        raise ValueError('direction must be callers, callees or both.')
                    depth = max(1, min(int(one('depth', '1')), 3))
                    self.json(200, explorer.neighbors(one('id'), direction, depth, limit=max(10, min(int(one('limit', '80')), 150))))
                else:
                    symbol = explorer.index.symbols[one('id')]
                    first, last = symbol['span']['line'], min(symbol['span']['end_line'], symbol['span']['line'] + 60)
                    if job.params.get('kind') == 'map':
                        text, sha = job.snapshot.get(symbol['file'], (None, None))
                        code = SnapshotReader({symbol['file']: text}).lines(symbol['file'], first, last) if text is not None else None
                        self.json(200, {'node': explorer.node(one('id')), 'code': code, 'commit': None,
                                        'stale': text is not None and changed_on_disk(job.params['repo'], symbol['file'], sha), 'made_at': job.view['made_at']})
                        return
                    commit = job.view['head' if side == 'after' else 'base']['commit']
                    code = SourceReader(job.params['repo']).lines(commit, symbol['file'], first, last)
                    self.json(200, {'node': explorer.node(one('id')), 'code': code, 'commit': commit})
            except KeyError:
                self.json(404, {'error': 'Unknown function.'})
            except ValueError as exc:
                self.json(400, {'error': str(exc)})

        def do_POST(self):
            if not self.guard():
                return
            path = urlparse(self.path).path
            try:
                data = self.body()
                if path == '/api/inspect':
                    info = inspect_repo(str(data.get('repo', '')).strip())
                    if not state.is_temporary(info['repo']):       # throwaway examples are not worth remembering
                        state.remember(info['repo'], info['name'])
                    self.json(200, info)
                elif path == '/api/analyze':
                    repo = str(data.get('repo', '')).strip()
                    base, head = str(data.get('base', '')).strip(), str(data.get('head', '')).strip()
                    if not (repo and base and head):
                        raise GitError('Choose a project and both commits first.')
                    roots = [str(r) for r in (data.get('source_roots') or []) if isinstance(r, str)]
                    job = state.start({'repo': repo, 'base': base, 'head': head, 'source_roots': roots,
                                       'include_possible': bool(data.get('include_possible', True))})
                    self.json(200, {'job': job.id})
                elif path == '/api/map':
                    folder = Path(str(data.get('repo', '')).strip()).expanduser()
                    if not folder.is_dir():
                        raise ValueError('That folder was not found. Check the path and try again.')
                    folder = folder.resolve()
                    roots = [str(r) for r in (data.get('source_roots') or []) if isinstance(r, str)]
                    if not state.is_temporary(str(folder)):
                        state.remember(str(folder), folder.name)
                    job = state.start({'kind': 'map', 'repo': str(folder), 'source_roots': roots})
                    self.json(200, {'job': job.id})
                elif path == '/api/lab':
                    folder = Path(str(data.get('repo', '')).strip()).expanduser()
                    if not folder.is_dir():
                        raise ValueError('That folder was not found. Check the path and try again.')
                    folder = folder.resolve()
                    base, head = str(data.get('base') or '').strip(), str(data.get('head') or '').strip()
                    if bool(base) != bool(head):
                        raise ValueError('Choose both versions to compare, or neither.')
                    base, head, reverse = lab_direction(base, head, data.get('reverse'))
                    roots = [str(r) for r in (data.get('source_roots') or []) if isinstance(r, str)]
                    if not state.is_temporary(str(folder)):
                        state.remember(str(folder), folder.name)
                    job = state.start({'kind': 'lab', 'repo': str(folder), 'base': base, 'head': head, 'source_roots': roots, 'include_possible': True, 'reverse': reverse})
                    self.json(200, {'job': job.id})
                elif path == '/api/cancel':
                    job = state.jobs.get(str(data.get('job') or ''))
                    if job:
                        job.cancelled.set()
                    self.json(200, {'ok': bool(job)})
                elif path == '/api/example':
                    example = next((e for e in examples.catalog() if e['id'] == data.get('id')), None)
                    comparison = next((c for c in (example or {}).get('comparisons', []) if c['id'] == data.get('comparison')), None)
                    if not comparison:
                        self.json(404, {'error': 'That example is not available on this computer.'})
                        return
                    repo = state.prepare_example(example['id'])
                    self.json(200, {'repo': repo, 'base': comparison['base'], 'head': comparison['head'],
                                    'source_roots': comparison.get('source_roots', []),
                                    'example': {'project': example['title'], 'title': comparison['title'], 'aspect': comparison['aspect'],
                                                'shows': comparison['shows'], 'steps': comparison['steps']}})
                elif path == '/api/browse':
                    self.json(200, {'path': state.browse()})
                elif path == '/api/workspace/create':
                    ws = workspaces.create_workspace(
                        name=data.get('name', ''),
                        repo=data.get('repo', ''),
                        description=data.get('description', ''),
                    )
                    # Capture the latest commits right away
                    if Path(ws['repo']).is_dir():
                        try:
                            ws = workspaces.auto_capture_versions(ws['id'], ws['repo'])
                        except Exception:
                            pass  # workspace was created; version capture is best-effort
                    self.json(200, ws)
                elif path == '/api/workspace/add-version':
                    ws = workspaces.add_version(
                        ws_id=data.get('id', ''),
                        commit=data.get('commit', ''),
                        subject=data.get('subject', ''),
                        author=data.get('author', ''),
                        branch=data.get('branch', ''),
                    )
                    self.json(200, ws)
                elif path == '/api/workspace/refresh':
                    ws_id = data.get('id', '')
                    ws = workspaces.get_workspace(ws_id)
                    if not ws:
                        self.json(404, {'error': 'Workspace not found.'})
                        return
                    prev_len = len(ws.get('versions', []))
                    if data.get('fetch'):
                        ws = workspaces.fetch_workspace_updates(ws_id)
                    elif Path(ws['repo']).is_dir():
                        ws = workspaces.auto_capture_versions(ws_id, ws['repo'], capture_snapshot=True)
                    new_len = len(ws.get('versions', []))
                    added_count = new_len - prev_len
                    msg = f"Added {added_count} new version(s)." if added_count > 0 else "Workspace is up to date."
                    res = dict(ws)
                    res['added_count'] = added_count
                    res['message'] = msg
                    self.json(200, res)
                elif path == '/api/workspace/upload-version':
                    ws_id = data.get('id', '')
                    ws = workspaces.get_workspace(ws_id)
                    if not ws:
                        self.json(404, {'error': 'Workspace not found.'})
                        return
                    mode = data.get('mode', 'folder')
                    note = str(data.get('note') or '').strip()
                    author = str(data.get('author') or '').strip()
                    prev_len = len(ws.get('versions', []))
                    if mode == 'folder':
                        repo = data.get('repo') or ws['repo']
                        snapshot = bool(data.get('snapshot', True))
                        ws = workspaces.update_workspace_repo(
                            ws_id, repo, capture_snapshot=snapshot, snapshot_note=note, author=author
                        )
                    elif mode == 'fetch':
                        ws = workspaces.fetch_workspace_updates(ws_id)
                    elif mode == 'snapshot':
                        repo = data.get('repo') or ws['repo']
                        snap = workspaces.snapshot_working_tree(repo, subject=note, author=author)
                        if snap:
                            ws = workspaces.add_version(
                                ws_id=ws_id,
                                commit=snap['commit'],
                                subject=snap['subject'],
                                author=snap['author'],
                            )
                    elif mode == 'zip':
                        import base64
                        zip_b64 = data.get('zip_base64', '')
                        filename = str(data.get('filename') or 'archive.zip')
                        zip_bytes = base64.b64decode(zip_b64.split(',')[-1])
                        ws, is_new = workspaces.snapshot_zip_to_mirror(
                            ws_id, zip_bytes, filename=filename, subject=note, author=author
                        )
                    elif mode == 'commit':
                        ws = workspaces.add_version(
                            ws_id=ws_id,
                            commit=data.get('commit', ''),
                            subject=note or data.get('subject', ''),
                            author=author or data.get('author', ''),
                            branch=data.get('branch', ''),
                        )
                    new_len = len(ws.get('versions', []))
                    added_count = new_len - prev_len
                    if added_count > 0:
                        latest = ws['versions'][-1]
                        msg = f"Added {added_count} new version: {latest.get('subject') or latest.get('short')}"
                    else:
                        msg = "No new commits or uncommitted changes found. The workspace is up to date."
                    res = dict(ws)
                    res['added_count'] = added_count
                    res['message'] = msg
                    self.json(200, res)
                elif path == '/api/workspace/add-repo':
                    repo = str(data.get('repo', '')).strip()
                    if not repo:
                        raise ValueError('Choose a project folder.')
                    ws_id = data.get('id')
                    if ws_id:
                        ws = workspaces.get_workspace(ws_id)
                        if not ws:
                            self.json(404, {'error': 'Workspace not found.'})
                            return
                        ws = workspaces.update_workspace_repo(ws_id, repo, capture_snapshot=True)
                    else:
                        name = str(data.get('name') or Path(repo).name).strip()
                        ws = workspaces.create_workspace(name=name, repo=repo)
                        if Path(ws['repo']).is_dir():
                            try:
                                ws = workspaces.auto_capture_versions(ws['id'], ws['repo'], capture_snapshot=True)
                            except Exception:
                                pass
                    self.json(200, ws)
                elif path == '/api/workspace/rename':
                    ws = workspaces.rename_workspace(
                        ws_id=data.get('id', ''),
                        name=data.get('name', ''),
                    )
                    self.json(200, ws)
                elif path == '/api/workspace/delete':
                    deleted = workspaces.delete_workspace(data.get('id', ''))
                    self.json(200, {'ok': deleted})
                elif path == '/api/workspace/compare':
                    ws_id = data.get('id', '')
                    ws = workspaces.get_workspace(ws_id)
                    if not ws:
                        self.json(404, {'error': 'Workspace not found.'})
                        return
                    base, head = workspaces.compare_versions(
                        ws_id,
                        int(data.get('base_index', -1)),
                        int(data.get('head_index', -1)),
                    )
                    # Start a lab job with those commits
                    folder = Path(ws['repo'])
                    if not folder.is_dir():
                        raise ValueError('The workspace project folder was not found.')
                    roots = [str(r) for r in (data.get('source_roots') or []) if isinstance(r, str)]
                    reverse = bool(data.get('reverse'))
                    analysis_base, analysis_head, rev = lab_direction(base, head, reverse)
                    if not state.is_temporary(str(folder)):
                        state.remember(str(folder), folder.name)
                    job = state.start({
                        'kind': 'lab', 'repo': str(folder),
                        'base': analysis_base, 'head': analysis_head,
                        'source_roots': roots, 'include_possible': True, 'reverse': rev,
                    })
                    self.json(200, {'job': job.id, 'base': base, 'head': head, 'workspace': ws_id})
                elif path == '/api/demo':
                    if state.demo_dir is None:
                        state.demo_dir = tempfile.mkdtemp(prefix='repotrace-demo-')
                    repo = Path(state.demo_dir) / 'example-shop'
                    if not repo.exists():
                        make_demo_repo(state.demo_dir)
                    self.json(200, {'repo': str(repo)})
                elif path == '/api/github/device':
                    self.json(200, github_auth.scrub_public(state.github.start_device_flow()))
                elif path == '/api/github/token':
                    self.json(200, github_auth.scrub_public(state.github.accept_token(data.get('token'))))
                elif path == '/api/github/logout':
                    self.json(200, github_auth.scrub_public(state.github.logout()))
                elif path == '/api/github/use':
                    self.json(200, github_auth.scrub_public(state.github.use_repo(data.get('full_name'))))
                elif path == '/api/gitlab/token':
                    self.json(200, state.gitlab.accept_token(data.get('token'), data.get('instance') or 'https://gitlab.com'))
                elif path == '/api/gitlab/logout':
                    self.json(200, state.gitlab.logout())
                elif path == '/api/gitlab/use':
                    full_name = data.get('full_name')
                    token = state.gitlab.get_token()
                    cred = state.gitlab._load()
                    instance = cred.get('instance', 'https://gitlab.com').rstrip('/') if cred else 'https://gitlab.com'
                    clone_url = data.get('url') or f"{instance}/{full_name}.git"
                    plan = plan_clone(state.github.home, clone_url, 'https')
                    cloned = perform_clone(state.github.home, clone_url, 'https', plan['dest'], token=token)
                    self.json(200, cloned)
                elif path == '/api/azure/token':
                    self.json(200, state.azure.accept_token(data.get('token'), data.get('organization')))
                elif path == '/api/azure/logout':
                    self.json(200, state.azure.logout())
                elif path == '/api/azure/use':
                    clone_url = data.get('url')
                    token = state.azure.get_token()
                    import base64
                    basic_token = f"Basic {base64.b64encode(f':{token}'.encode()).decode('ascii')}" if token else None
                    plan = plan_clone(state.github.home, clone_url, 'https')
                    cloned = perform_clone(state.github.home, clone_url, 'https', plan['dest'], token=basic_token)
                    self.json(200, cloned)
                elif path == '/api/clone':
                    plan = plan_clone(state.github.home, data.get('url'), data.get('kind'))
                    public = {
                        'needs_confirm': True, 'dest': plan['dest'], 'exists': plan['exists'],
                        'blocked': plan['blocked'], 'action': plan['action'], 'url': plan['url'],
                    }
                    if data.get('confirm') != plan['dest']:
                        self.json(200, public)
                        return
                    token = clone_may_use_remote_token(plan, state)
                    cloned = perform_clone(state.github.home, data.get('url'), data.get('kind'), data.get('confirm'), token=token)
                    self.json(200, state.github.publish(cloned))
                else:
                    self.json(404, {'error': 'Not found.'})
            except GitError as exc:
                self.json(400, {'error': friendly(exc)})
            except (ValueError, KeyError) as exc:
                message = state.github.redact(str(exc)) if path.startswith('/api/github') or path == '/api/clone' else str(exc)
                self.json(400, {'error': message})

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.handle_error = lambda request, client_address: None    # a browser hanging up is not an error
    state.port = server.server_address[1]
    return server, state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('repo', nargs='?', type=Path, help='A Git project to open (optional)')
    parser.add_argument('--port', type=int, default=0, help='Port to use (default: any free port)')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--lab', action='store_true', help='Open the new guided screens (the default screen is the classic one for now)')
    args = parser.parse_args(argv)
    server, state = make_server(port=args.port, initial_repo=str(args.repo.resolve()) if args.repo else None)
    url = f'http://127.0.0.1:{state.port}/' + ('lab' if args.lab else '')
    print(f'RepoTrace is running at {url}\nIt only listens on this computer and never runs your code. Press Ctrl+C to stop.')
    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        server.server_close()
        state.cleanup()


if __name__ == '__main__':
    main()
