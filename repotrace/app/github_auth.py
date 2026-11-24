"""GitHub sign-in for the local RepoTrace app.

The browser may send a personal access token once. After that only this process
keeps it, in ~/.repotrace/github.json (file mode 0600, directory 0700).
Public responses never include the token, a client secret, or a device code.
"""
import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CLIENT_ID_ENV = 'REPO_TRACE_GITHUB_CLIENT_ID'
SCOPE = 'read:user repo'
GRANT_TYPE = 'urn:ietf:params:oauth:grant-type:device_code'
DEVICE_CODE_URL = 'https://github.com/login/device/code'
TOKEN_URL = 'https://github.com/login/oauth/access_token'
USER_URL = 'https://api.github.com/user'
REPOS_URL = 'https://api.github.com/user/repos?per_page=50&sort=updated'
VERIFICATION_URI = 'https://github.com/login/device'
NOT_CONFIGURED = (
    'GitHub sign-in cannot start until you create a GitHub OAuth app, '
    'set its homepage to http://127.0.0.1 and its callback URL to http://127.0.0.1, '
    'and start RepoTrace with that client id in REPO_TRACE_GITHUB_CLIENT_ID.'
)
SECRET_KEYS = frozenset({
    'access_token', 'token', 'authorization', 'client_secret', 'device_code',
    'refresh_token', 'password', 'avatar_url',
})
_NAME = re.compile(r'^(?!\.\.?$)[A-Za-z0-9_.-]{1,100}$')
_MISSING = object()
_HOOKS = None


class GitHubError(ValueError):
    """GitHub refused the request, or the saved sign-in cannot be used."""


def scrub_text(value, *secrets):
    text = '' if value is None else str(value)
    for secret in secrets:
        if secret:
            text = text.replace(str(secret), '[redacted]')
    return text.replace('\n', ' ').replace('\r', ' ')[:500]


def scrub_public(value):
    """Drop every secret key before a dict can be sent to the browser."""
    if isinstance(value, dict):
        return {str(key): scrub_public(item) for key, item in value.items() if str(key).lower() not in SECRET_KEYS}
    if isinstance(value, list):
        return [scrub_public(item) for item in value]
    return value


def parse_github_json(raw):
    if raw is None or (isinstance(raw, (bytes, str)) and not raw.strip()):
        return {}
    try:
        text = raw.decode('utf-8') if isinstance(raw, bytes) else raw
        data = json.loads(text)
    except (ValueError, UnicodeError, AttributeError):
        raise GitHubError('GitHub returned something this app cannot read.')
    if not isinstance(data, (dict, list)):
        raise GitHubError('GitHub returned something this app cannot read.')
    return data


def github_message(status, payload):
    if isinstance(payload, dict):
        for key in ('error_description', 'message', 'error'):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return scrub_text(value.strip())
    return f'GitHub returned {status}.'


def _error(status, payload, *extra):
    leaked = _secret_strings(payload if isinstance(payload, dict) else {})
    raise GitHubError(scrub_text(github_message(status, payload), *leaked, *extra))


def _scrub_strings(value, hidden):
    """Replace secret values wherever they appear. Leave every other string unchanged."""
    if isinstance(value, dict):
        return {key: _scrub_strings(item, hidden) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_strings(item, hidden) for item in value]
    if isinstance(value, str) and any(secret and secret in value for secret in hidden):
        return scrub_text(value, *hidden)
    return value


def _single_line(value, empty_message):
    value = '' if value is None else str(value).strip()
    if not value:
        raise GitHubError(empty_message)
    if any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise GitHubError('GitHub returned a value this app will not use.')
    return value


def device_code_body(client_id):
    """Body for POST /login/device/code. A client secret is never part of it."""
    body = {'client_id': _single_line(client_id, NOT_CONFIGURED), 'scope': SCOPE}
    if 'client_secret' in body or set(body) & SECRET_KEYS:
        raise GitHubError('Refusing to send a client secret.')
    return body


def token_request_body(client_id, device_code):
    """Body for the device-code grant. Still no client secret."""
    body = {
        'client_id': _single_line(client_id, NOT_CONFIGURED),
        'device_code': _single_line(device_code, 'GitHub did not return a device code.'),
        'grant_type': GRANT_TYPE,
    }
    if 'client_secret' in body:
        raise GitHubError('Refusing to send a client secret.')
    return body


def clean_token(token):
    token = '' if token is None else token
    if not isinstance(token, str):
        raise GitHubError('Paste a personal access token.')
    token = token.strip()
    if not token:
        raise GitHubError('Paste a personal access token.')
    if any(ch.isspace() or ord(ch) < 32 for ch in token) or len(token) > 2048:
        raise GitHubError('That token is not valid.')
    return token


def safe_verification_uri(value):
    return VERIFICATION_URI if value == VERIFICATION_URI else VERIFICATION_URI


def _stored_login(credentials):
    if not isinstance(credentials, dict):
        return None
    login = credentials.get('login')
    token = credentials.get('token')
    if not isinstance(login, str) or not login.strip() or not isinstance(token, str) or not token:
        return None
    if any(ord(ch) < 32 for ch in login):
        return None
    return login.strip()


def _secret_strings(*dicts):
    found = []
    for item in dicts:
        if not isinstance(item, dict):
            continue
        for key in ('token', 'access_token', 'authorization', 'device_code', 'client_secret', 'password', 'refresh_token'):
            value = item.get(key)
            if isinstance(value, str) and value:
                found.append(value)
    return found


def public_status(configured, credentials=None, flow=None):
    """What the browser is allowed to see. Never the access token."""
    flow = flow if isinstance(flow, dict) else None
    flow_state = (flow or {}).get('status')
    login = _stored_login(credentials)
    secrets = _secret_strings(credentials, flow)
    state = 'signed-out'
    shown_login = None
    extra = {}
    if flow_state == 'pending':
        state = 'pending'
        code = flow.get('user_code') if isinstance(flow.get('user_code'), str) else ''
        extra['user_code'] = scrub_text(code.strip(), *secrets)
        extra['verification_uri'] = safe_verification_uri(flow.get('verification_uri'))
    elif login:
        state = 'signed-in'
        shown_login = login
    elif flow_state == 'error':
        state = 'error'
        extra['error'] = scrub_text(flow.get('error') or 'GitHub sign-in failed.', *secrets)
    out = {'configured': bool(configured), 'signed_in': state == 'signed-in', 'login': shown_login, 'state': state}
    out.update(extra)
    return scrub_public(out)


def split_repo_name(full_name):
    text = '' if full_name is None else str(full_name).strip()
    owner, sep, repo = text.partition('/')
    if not sep or '/' in repo or not _NAME.match(owner) or not _NAME.match(repo):
        raise GitHubError('Choose a repository GitHub listed.')
    return owner, repo


def github_clone_url(owner, repo):
    owner, repo = split_repo_name(f'{owner}/{repo}')
    return f'https://github.com/{owner}/{repo}.git'


def mirror_directory(home, owner, repo):
    root = (Path(home) / '.repotrace' / 'mirrors').resolve()
    dest = root / owner / repo
    if dest.parent.parent != root:
        raise GitHubError('That repository name cannot be used as a folder.')
    return dest


def header_get(headers, name):
    if not headers or not hasattr(headers, 'get'):
        return ''
    value = headers.get(name)
    if value:
        return value
    return headers.get(name.lower()) or ''


def next_page(link_header, token=None):
    """The next GitHub page, or None. Only api.github.com, and never a URL that contains the token."""
    if not link_header:
        return None
    for part in str(link_header).split(','):
        pieces = [bit.strip() for bit in part.split(';')]
        if not pieces:
            continue
        url = pieces[0]
        if url.startswith('<') and url.endswith('>'):
            url = url[1:-1]
        rel_next = any(bit.replace(' ', '') in ('rel="next"', "rel='next'") for bit in pieces[1:])
        if not rel_next:
            continue
        if token and token in url:
            return None
        if url.startswith('https://api.github.com/'):
            return url
    return None


def git_invocation(args, token=None, hooks=None):
    """git plus an environment for this command only.

    http.extraheader is set with GIT_CONFIG_KEY/VALUE, which git does not write
    into .git/config. The token is not an argument and not part of the URL.
    """
    cmd = ['git']
    cmd.extend(str(arg) for arg in args)
    if token and any(token in part for part in cmd):
        raise GitHubError('Refusing to put the GitHub token on the git command line.')
    env = os.environ.copy()
    for key in ('GIT_ASKPASS', 'SSH_ASKPASS', 'GIT_CONFIG_PARAMETERS'):
        env.pop(key, None)
    for key in list(env):
        if key == 'GIT_CONFIG_COUNT' or key.startswith('GIT_CONFIG_KEY_') or key.startswith('GIT_CONFIG_VALUE_'):
            env.pop(key, None)
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GIT_CONFIG_NOSYSTEM'] = '1'
    env['GIT_CONFIG_GLOBAL'] = os.devnull
    env['GIT_CONFIG_SYSTEM'] = os.devnull
    env['GCM_INTERACTIVE'] = 'Never'
    configs = []
    if hooks:
        configs.append(('core.hooksPath', str(hooks)))
    configs.append(('credential.helper', ''))
    if token:
        configs.append(('http.extraheader', authorization_header(token)))
    env['GIT_CONFIG_COUNT'] = str(len(configs))
    for index, (key, value) in enumerate(configs):
        env['GIT_CONFIG_KEY_%d' % index] = key
        env['GIT_CONFIG_VALUE_%d' % index] = value
    return cmd, env


def authorization_header(token, scheme='bearer'):
    token_str = str(token).strip()
    if token_str.lower().startswith(('bearer ', 'basic ')):
        return f'AUTHORIZATION: {token_str}'
    return f'AUTHORIZATION: {scheme} {token_str}'


def empty_hooks_dir():
    global _HOOKS
    if _HOOKS is None:
        _HOOKS = Path(tempfile.mkdtemp(prefix='repotrace-no-hooks-'))
    return _HOOKS


def run_git(args, token=None, timeout=300):
    cmd, env = git_invocation(args, token=token, hooks=empty_hooks_dir())
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
    except FileNotFoundError:
        raise GitHubError('Git is not installed on this computer, or it is not on the PATH.')
    except subprocess.TimeoutExpired:
        raise GitHubError('Git took too long.')
    if done.returncode != 0:
        message = done.stderr.decode('utf-8', 'replace').strip() or f'git {args[0]} failed.'
        raise GitHubError(scrub_text(message, token))
    return done.stdout


def reject_token_in_clone(dest, token):
    config = Path(dest) / '.git' / 'config'
    try:
        text = config.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return
    encoded = urllib.parse.quote(token, safe='') if token else ''
    leaked = bool(token) and (token in text or (encoded and encoded != token and encoded in text))
    if leaked:
        cleaned = text.replace(token, '')
        if encoded and encoded != token:
            cleaned = cleaned.replace(encoded, '')
        config.write_text(cleaned)
        os.chmod(config, 0o600)
        raise GitHubError('Git stored the token inside the local copy. RepoTrace removed it from the Git config and stopped.')
    if 'extraheader' in text.lower():
        raise GitHubError('Git stored an HTTP header inside the local copy. RepoTrace will not use that copy.')


def github_request(opener, url, method='GET', fields=None, token=None, accept='application/json', timeout=30):
    if not (str(url).startswith('https://github.com/') or str(url).startswith('https://api.github.com/')):
        raise GitHubError('Refusing to send a GitHub request to another site.')
    headers = {'Accept': accept, 'User-Agent': 'RepoTrace'}
    data = None
    if fields is not None:
        if 'client_secret' in fields or 'token' in fields or 'access_token' in fields or 'password' in fields:
            raise GitHubError('Refusing to send a client secret.')
        data = urllib.parse.urlencode(fields).encode('utf-8')
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        method = 'POST'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if str(url).startswith('https://api.github.com/'):
        headers['X-GitHub-Api-Version'] = '2022-11-28'
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, 'status', None) or response.getcode()
            response_headers = response.headers
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_headers = exc.headers
        try:
            raw = exc.read()
        finally:
            exc.close()
    except urllib.error.URLError as exc:
        raise GitHubError('Could not reach GitHub: ' + scrub_text(getattr(exc, 'reason', exc), token))
    return status, parse_github_json(raw), response_headers


class GitHubSession:
    def __init__(self, home=None, opener=None, client_id=_MISSING, wait=None, now=None, git_run=None):
        self.home = Path(home) if home is not None else Path.home()
        self.opener = opener or urllib.request.build_opener()
        self._client_id_override = client_id
        self._wait = wait or (lambda stop, seconds: stop.wait(seconds))
        self._now = now or time.monotonic
        self.git_run = git_run or run_git
        self._lock = threading.RLock()
        self._hidden = []
        self._generation = 0
        self._cancel = threading.Event()
        self._flow = None

    def remember_secret(self, value):
        if not isinstance(value, str) or len(value) < 8:
            return
        with self._lock:
            if value not in self._hidden:
                self._hidden.append(value)

    def redact(self, value):
        with self._lock:
            hidden = tuple(self._hidden)
        return scrub_text(value, *hidden)

    def publish(self, value):
        with self._lock:
            hidden = tuple(self._hidden)
        return _scrub_strings(scrub_public(value), hidden)

    def client_id(self):
        if self._client_id_override is not _MISSING:
            value = self._client_id_override
        else:
            value = os.environ.get(CLIENT_ID_ENV, '')
        value = '' if value is None else str(value).strip()
        if not value or any(ch.isspace() or ord(ch) < 32 for ch in value):
            return None
        return value

    def close(self):
        with self._lock:
            self._generation += 1
            self._cancel.set()

    def credentials_path(self):
        return self._private_dir() / 'github.json'

    def _private_dir(self):
        path = Path(self.home) / '.repotrace'
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
        return path

    def _save(self, token, login):
        self.remember_secret(token)
        path = self.credentials_path()
        os.chmod(path.parent, 0o700)
        blob = json.dumps({'login': login, 'token': token}) + '\n'
        tmp = path.parent / f'.github-{secrets.token_hex(8)}.tmp'
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(blob)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
            os.chmod(path, 0o600)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    def _load(self):
        path = Path(self.home) / '.repotrace' / 'github.json'
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        if _stored_login(data) is None:
            return None
        self.remember_secret(data['token'])
        return {'login': data['login'].strip(), 'token': data['token']}

    def _delete_credentials(self):
        try:
            (Path(self.home) / '.repotrace' / 'github.json').unlink()
        except FileNotFoundError:
            return

    def status(self):
        credentials = self._load()
        with self._lock:
            flow = dict(self._flow) if isinstance(self._flow, dict) else None
        return self.publish(public_status(bool(self.client_id()), credentials, flow))

    def _set_flow(self, generation, flow):
        with self._lock:
            if generation != self._generation:
                return
            cleaned = scrub_public(flow)
            if isinstance(cleaned, dict):
                for key in ('error', 'user_code', 'login'):
                    if isinstance(cleaned.get(key), str):
                        cleaned[key] = scrub_text(cleaned[key], *self._hidden)
            self._flow = cleaned

    def _current_generation(self):
        with self._lock:
            return self._generation

    def logout(self):
        with self._lock:
            self._generation += 1
            self._cancel.set()
            self._flow = None
        self._delete_credentials()
        return self.status()

    def accept_token(self, token):
        token = clean_token(token)
        self.remember_secret(token)
        status, payload, _ = github_request(self.opener, USER_URL, token=token, accept='application/vnd.github+json')
        if status != 200 or not isinstance(payload, dict):
            _error(status, payload, token)
        login = payload.get('login')
        if not isinstance(login, str) or not login.strip() or any(ord(ch) < 32 for ch in login) or token in login:
            raise GitHubError('GitHub did not return a login.')
        login = login.strip()
        with self._lock:
            self._save(token, login)
            self._generation += 1
            self._cancel.set()
            self._flow = {'status': 'signed-in', 'login': login}
        return self.status()

    def start_device_flow(self, poll=True):
        client = self.client_id()
        if not client:
            raise GitHubError(NOT_CONFIGURED)
        fields = device_code_body(client)
        status, payload, _ = github_request(self.opener, DEVICE_CODE_URL, method='POST', fields=fields, accept='application/json')
        if status != 200 or not isinstance(payload, dict) or payload.get('error'):
            _error(status, payload)
        device_code = _single_line(payload.get('device_code'), 'GitHub did not return a sign-in code.')
        self.remember_secret(device_code)
        user_code = payload.get('user_code')
        if not isinstance(user_code, str):
            raise GitHubError('GitHub did not return a sign-in code.')
        user_code = user_code.strip()
        if not user_code or any(ord(ch) < 32 for ch in user_code) or len(user_code) > 64:
            raise GitHubError('GitHub did not return a sign-in code.')
        interval = _positive_int(payload.get('interval'), 5)
        expires_in = _positive_int(payload.get('expires_in'), 900)
        verification = safe_verification_uri(payload.get('verification_uri'))
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._cancel.set()
            self._cancel = threading.Event()
            stop = self._cancel
            self._flow = {'status': 'pending', 'user_code': user_code, 'verification_uri': verification}
        if poll:
            threading.Thread(
                target=self._poll,
                args=(client, device_code, interval, expires_in, stop, generation),
                daemon=True,
            ).start()
        return self.publish({
            'configured': True,
            'signed_in': False,
            'login': None,
            'state': 'pending',
            'user_code': user_code,
            'verification_uri': verification,
            'expires_in': expires_in,
        })

    def _poll(self, client_id, device_code, interval, expires_in, stop, generation):
        deadline = self._now() + max(1, int(expires_in))
        interval = max(1, int(interval))
        try:
            while True:
                if generation != self._current_generation():
                    return
                if self._now() >= deadline:
                    self._set_flow(generation, {'status': 'error', 'error': 'The GitHub code expired. Start sign-in again.'})
                    return
                delay = min(interval, max(0, deadline - self._now()))
                if delay > 0 and self._wait(stop, delay):
                    return
                if generation != self._current_generation() or self._now() >= deadline:
                    if generation == self._current_generation() and self._now() >= deadline:
                        self._set_flow(generation, {'status': 'error', 'error': 'The GitHub code expired. Start sign-in again.'})
                    return
                fields = token_request_body(client_id, device_code)
                status, payload, _ = github_request(
                    self.opener, TOKEN_URL, method='POST', fields=fields, accept='application/json')
                if not isinstance(payload, dict):
                    self._set_flow(generation, {'status': 'error', 'error': 'GitHub returned something this app cannot read.'})
                    return
                err = payload.get('error')
                access = payload.get('access_token') if status == 200 and not err else None
                if isinstance(access, str) and access:
                    self.remember_secret(access)
                    self._finish_token(access, generation)
                    return
                if err == 'authorization_pending':
                    continue
                if err == 'slow_down':
                    interval += 5
                    continue
                if err in ('expired_token', 'expired'):
                    self._set_flow(generation, {'status': 'error', 'error': 'The GitHub code expired. Start sign-in again.'})
                    return
                if err == 'access_denied':
                    self._set_flow(generation, {'status': 'error', 'error': 'GitHub did not approve the sign-in.'})
                    return
                leaked = access if isinstance(access, str) else ''
                self._set_flow(generation, {
                    'status': 'error',
                    'error': scrub_text(github_message(status, payload), leaked, device_code),
                })
                return
        except Exception as exc:
            self._set_flow(generation, {'status': 'error', 'error': scrub_text(exc, device_code)})

    def _finish_token(self, token, generation):
        if generation != self._current_generation():
            return
        try:
            status, payload, _ = github_request(self.opener, USER_URL, token=token, accept='application/vnd.github+json')
        except GitHubError as exc:
            self._set_flow(generation, {'status': 'error', 'error': scrub_text(exc, token)})
            return
        login = payload.get('login') if isinstance(payload, dict) else None
        if status != 200 or not isinstance(login, str) or not login.strip() or token in login:
            self._set_flow(generation, {'status': 'error', 'error': scrub_text(github_message(status, payload), token)})
            return
        login = login.strip()
        with self._lock:
            if generation != self._generation:
                return
            self._save(token, login)
            self._flow = {'status': 'signed-in', 'login': login}

    def list_repos(self):
        credentials = self._load()
        if not credentials:
            raise GitHubError('Sign in to GitHub first.')
        token = credentials['token']
        url = REPOS_URL
        repos = []
        follows = 0
        while url and len(repos) < 100:
            status, payload, headers = github_request(self.opener, url, token=token, accept='application/vnd.github+json')
            if status != 200:
                _error(status, payload, token)
            if not isinstance(payload, list):
                raise GitHubError('GitHub did not return a repository list.')
            for item in payload:
                if len(repos) >= 100:
                    break
                if isinstance(item, dict):
                    repos.append(self._public_repo(item))
            if len(repos) >= 100 or follows >= 2:
                break
            nxt = next_page(header_get(headers, 'Link'), token)
            if not nxt or nxt == url:
                break
            follows += 1
            url = nxt
        return self.publish({'repos': repos})

    def _public_repo(self, item):
        owner = item.get('owner') if isinstance(item.get('owner'), dict) else {}
        owner_login = owner.get('login') if isinstance(owner.get('login'), str) else ''
        name = item.get('name') if isinstance(item.get('name'), str) else ''
        full = item.get('full_name') if isinstance(item.get('full_name'), str) else ''
        if not full and owner_login and name:
            full = owner_login + '/' + name
        mirror, mirrored = '', False
        try:
            repo_owner, repo_name = split_repo_name(full)
            dest = mirror_directory(self.home, repo_owner, repo_name)
            mirror = str(dest)
            mirrored = (dest / '.git').is_dir()
        except GitHubError:
            mirror = ''
        private = bool(item.get('private')) if 'private' in item else None
        branch = item.get('default_branch') if isinstance(item.get('default_branch'), str) else ''
        updated = item.get('updated_at') if isinstance(item.get('updated_at'), str) else ''
        return {
            'name': name, 'full_name': full, 'private': private, 'default_branch': branch,
            'updated_at': updated, 'owner': owner_login, 'mirror': mirror, 'mirrored': mirrored,
        }

    def use_repo(self, full_name):
        if not isinstance(full_name, str):
            raise GitHubError('Choose a repository GitHub listed.')
        credentials = self._load()
        if not credentials:
            raise GitHubError('Sign in to GitHub first.')
        owner, repo = split_repo_name(full_name)
        token = credentials['token']
        status, payload, _ = github_request(
            self.opener, f'https://api.github.com/repos/{owner}/{repo}', token=token, accept='application/vnd.github+json')
        if status != 200 or not isinstance(payload, dict):
            _error(status, payload, token)
        url = github_clone_url(owner, repo)
        if token in url:
            raise GitHubError('Refusing to put the GitHub token in the clone URL.')
        self._private_dir()
        dest = mirror_directory(self.home, owner, repo)
        git_error = None
        try:
            if (dest / '.git').is_dir():
                self.git_run(['-C', str(dest), 'fetch', '--prune'], token=token)
            elif dest.exists():
                raise GitHubError(f'{dest} already exists and is not a Git clone. RepoTrace will not replace it.')
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.chmod(self._private_dir(), 0o700)
                self.git_run(['clone', '--origin', 'origin', url, str(dest)], token=token)
        except GitHubError as exc:
            git_error = exc
        if (dest / '.git' / 'config').is_file():
            reject_token_in_clone(dest, token)
        if git_error:
            raise git_error
        return self.publish({'repo': str(dest), 'name': repo, 'full_name': f'{owner}/{repo}'})


def _positive_int(value, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default
