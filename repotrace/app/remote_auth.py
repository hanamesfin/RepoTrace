"""GitLab and Azure DevOps integrations for RepoTrace.

Saves tokens safely in ~/.repotrace/gitlab.json and ~/.repotrace/azure.json (file mode 0600).
Public responses never include tokens. Git commands receive tokens via isolated environment
variables only, never on CLI arguments or in stored git config.
"""
import base64
import json
import os
import re
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from repotrace.app import github_auth


class RemoteAuthError(ValueError):
    """A remote service refused the request or returned an error."""


def scrub_text(value, *secrets_list):
    return github_auth.scrub_text(value, *secrets_list)


def scrub_public(value):
    return github_auth.scrub_public(value)


def _safe_request(url, headers, timeout=25):
    """Execute an HTTPS request and return (status, json_data)."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            body = response.read().decode('utf-8', errors='replace')
            try:
                data = json.loads(body)
            except Exception:
                data = {}
            return status, data
    except urllib.error.HTTPError as exc:
        msg = f"Remote returned HTTP {exc.code}"
        try:
            err_body = exc.read().decode('utf-8', errors='replace')
            err_json = json.loads(err_body)
            if isinstance(err_json, dict):
                msg = err_json.get('message') or err_json.get('error') or err_json.get('error_description') or msg
        except Exception:
            pass
        raise RemoteAuthError(msg)
    except urllib.error.URLError as exc:
        raise RemoteAuthError(f"Could not reach remote service: {getattr(exc, 'reason', exc)}")


# ------------------------------------------------------------------ GitLab
class GitLabSession:
    def __init__(self, home=None):
        self.home = Path(home) if home else Path.home()
        self._lock = threading.Lock()
        self._hidden = set()

    def _private_dir(self):
        path = self.home / '.repotrace'
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
        return path

    def _file(self):
        return self._private_dir() / 'gitlab.json'

    def _save(self, token, login, name='', instance='https://gitlab.com'):
        path = self._file()
        token = str(token or '').strip()
        instance = str(instance or 'https://gitlab.com').strip().rstrip('/')
        if not instance.startswith(('http://', 'https://')):
            instance = 'https://' + instance
        self._hidden.add(token)
        blob = json.dumps({
            'token': token,
            'login': login,
            'name': name,
            'instance': instance,
        }, indent=2)
        tmp = path.parent / f'.gitlab-{secrets.token_hex(8)}.tmp'
        try:
            tmp.write_text(blob, encoding='utf-8')
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
        path = self._file()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not data.get('token') or not data.get('login'):
                return None
            self._hidden.add(data['token'])
            return data
        except Exception:
            return None

    def status(self):
        with self._lock:
            cred = self._load()
            if not cred:
                return {'signed_in': False, 'login': None, 'name': None, 'instance': 'https://gitlab.com'}
            return {
                'signed_in': True,
                'login': cred.get('login'),
                'name': cred.get('name') or cred.get('login'),
                'instance': cred.get('instance', 'https://gitlab.com'),
            }

    def accept_token(self, token, instance='https://gitlab.com'):
        token = str(token or '').strip()
        if not token:
            raise RemoteAuthError('Enter a GitLab personal access token.')
        instance = str(instance or 'https://gitlab.com').strip().rstrip('/')
        if not instance.startswith(('http://', 'https://')):
            instance = 'https://' + instance
        
        # Verify token by fetching user profile
        headers = {
            'PRIVATE-TOKEN': token,
            'User-Agent': 'RepoTrace',
            'Accept': 'application/json',
        }
        url = f"{instance}/api/v4/user"
        status, data = _safe_request(url, headers)
        if not isinstance(data, dict) or not data.get('username'):
            raise RemoteAuthError('Invalid GitLab personal access token.')
        
        login = data['username']
        name = data.get('name') or login
        with self._lock:
            self._save(token, login, name=name, instance=instance)
        return self.status()

    def logout(self):
        with self._lock:
            try:
                self._file().unlink()
            except FileNotFoundError:
                pass
        return self.status()

    def list_repos(self):
        cred = self._load()
        if not cred:
            raise RemoteAuthError('Connect to GitLab first.')
        instance = cred.get('instance', 'https://gitlab.com').rstrip('/')
        token = cred['token']
        headers = {
            'PRIVATE-TOKEN': token,
            'User-Agent': 'RepoTrace',
            'Accept': 'application/json',
        }
        url = f"{instance}/api/v4/projects?membership=true&simple=true&per_page=50&order_by=updated_at"
        status, data = _safe_request(url, headers)
        if not isinstance(data, list):
            return []
        
        repos = []
        for p in data:
            if not isinstance(p, dict):
                continue
            repos.append({
                'id': str(p.get('id', '')),
                'name': p.get('name', ''),
                'full_name': p.get('path_with_namespace', ''),
                'clone_url': p.get('http_url_to_repo', ''),
                'ssh_url': p.get('ssh_url_to_repo', ''),
                'description': p.get('description') or '',
                'updated_at': p.get('last_activity_at') or '',
                'default_branch': p.get('default_branch') or 'main',
            })
        return repos

    def get_token(self):
        cred = self._load()
        return cred.get('token') if cred else None


# ------------------------------------------------------------------ Azure DevOps
class AzureSession:
    def __init__(self, home=None):
        self.home = Path(home) if home else Path.home()
        self._lock = threading.Lock()
        self._hidden = set()

    def _private_dir(self):
        path = self.home / '.repotrace'
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
        return path

    def _file(self):
        return self._private_dir() / 'azure.json'

    def _clean_org(self, raw_org):
        org = str(raw_org or '').strip().rstrip('/')
        if 'dev.azure.com/' in org:
            org = org.split('dev.azure.com/')[-1].split('/')[0]
        elif 'visualstudio.com' in org:
            org = org.split('.visualstudio.com')[0].split('//')[-1]
        org = org.strip().lstrip('/')
        return org

    def _save(self, token, organization, login=''):
        path = self._file()
        token = str(token or '').strip()
        org = self._clean_org(organization)
        self._hidden.add(token)
        blob = json.dumps({
            'token': token,
            'organization': org,
            'login': login or org,
        }, indent=2)
        tmp = path.parent / f'.azure-{secrets.token_hex(8)}.tmp'
        try:
            tmp.write_text(blob, encoding='utf-8')
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
        path = self._file()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not data.get('token') or not data.get('organization'):
                return None
            self._hidden.add(data['token'])
            return data
        except Exception:
            return None

    def status(self):
        with self._lock:
            cred = self._load()
            if not cred:
                return {'signed_in': False, 'organization': None, 'login': None}
            return {
                'signed_in': True,
                'organization': cred.get('organization'),
                'login': cred.get('login') or cred.get('organization'),
            }

    def accept_token(self, token, organization):
        token = str(token or '').strip()
        if not token:
            raise RemoteAuthError('Enter an Azure DevOps Personal Access Token (PAT).')
        org = self._clean_org(organization)
        if not org:
            raise RemoteAuthError('Enter your Azure DevOps Organization name.')

        # Verify token by querying projects API
        basic_auth = base64.b64encode(f":{token}".encode()).decode('ascii')
        headers = {
            'Authorization': f'Basic {basic_auth}',
            'User-Agent': 'RepoTrace',
            'Accept': 'application/json',
        }
        url = f"https://dev.azure.com/{org}/_apis/projects?api-version=6.0&$top=1"
        status, data = _safe_request(url, headers)
        if not isinstance(data, dict) or 'value' not in data:
            raise RemoteAuthError('Invalid Azure DevOps Personal Access Token or Organization.')

        with self._lock:
            self._save(token, org, login=org)
        return self.status()

    def logout(self):
        with self._lock:
            try:
                self._file().unlink()
            except FileNotFoundError:
                pass
        return self.status()

    def list_repos(self):
        cred = self._load()
        if not cred:
            raise RemoteAuthError('Connect to Azure DevOps first.')
        org = cred['organization']
        token = cred['token']
        basic_auth = base64.b64encode(f":{token}".encode()).decode('ascii')
        headers = {
            'Authorization': f'Basic {basic_auth}',
            'User-Agent': 'RepoTrace',
            'Accept': 'application/json',
        }
        url = f"https://dev.azure.com/{org}/_apis/git/repositories?api-version=6.0"
        status, data = _safe_request(url, headers)
        items = data.get('value', []) if isinstance(data, dict) else []
        
        repos = []
        for r in items:
            if not isinstance(r, dict):
                continue
            proj_name = r.get('project', {}).get('name', '') if isinstance(r.get('project'), dict) else ''
            repo_name = r.get('name', '')
            full_name = f"{proj_name}/{repo_name}" if proj_name else repo_name
            repos.append({
                'id': str(r.get('id', '')),
                'name': repo_name,
                'project': proj_name,
                'full_name': full_name,
                'clone_url': r.get('remoteUrl') or r.get('webUrl') or '',
                'ssh_url': r.get('sshUrl') or '',
                'default_branch': (r.get('defaultBranch') or 'main').replace('refs/heads/', ''),
            })
        return repos

    def get_token(self):
        cred = self._load()
        return cred.get('token') if cred else None
