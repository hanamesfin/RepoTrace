"""GitHub sign-in without calling GitHub.

The public status, the device-flow body, logout, and a fake HTTP 401 are covered
here. Nothing in this file opens a socket to github.com.
"""
import io
import json
import os
import stat
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
from pathlib import Path

from repotrace.app import github_auth
from repotrace.app import server as app

SECRET = 'ghp_publicstatussecret0001'
DEVICE = 'device-code-secret-value'
CLIENT = 'lab-client'


def assert_public(test, payload, secret=SECRET):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    test.assertNotIn(secret, raw)
    test.assertNotIn(DEVICE, raw)
    test.assertNotIn('access_token', raw)
    test.assertNotIn('authorization', raw)
    test.assertNotIn('"token"', raw)
    test.assertNotIn('token', raw)
    test.assertNotIn('client_secret', raw)
    test.assertNotIn('device_code', raw)
    return raw


class Response:
    def __init__(self, status, raw, headers):
        self.status = status
        self.headers = headers
        self._raw = raw

    def read(self):
        return self._raw

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Scripted:
    """A urllib opener that never touches the network."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        if self.steps:
            status, body, headers = self.steps.pop(0)
        else:
            status, body, headers = 200, {'error': 'authorization_pending'}, {}
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        headers = headers or {}
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, 'error', headers, io.BytesIO(raw))
        return Response(status, raw, headers)


def posted(request):
    return urllib.parse.parse_qs(request.data.decode())


def device_payload(interval=5, expires_in=900):
    return {
        'device_code': DEVICE,
        'user_code': 'ABCD-EFGH',
        'verification_uri': 'https://github.com/login/device',
        'interval': interval,
        'expires_in': expires_in,
    }


class Clock:
    def __init__(self):
        self.now_at = 0
        self.waits = []

    def now(self):
        return self.now_at

    def wait(self, stop, seconds):
        self.waits.append(seconds)
        self.now_at += seconds
        return stop.is_set()


class GitHubCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def session(self, steps, client_id=None, **kwargs):
        opener = Scripted(steps)
        session = github_auth.GitHubSession(home=self.home, opener=opener, client_id=client_id, **kwargs)
        self.addCleanup(session.close)
        session.opener = opener
        return session


class PublicStatusTests(GitHubCase):
    def test_public_status_never_contains_a_token(self):
        flow = {
            'status': 'pending',
            'user_code': 'ABCD-EFGH',
            'verification_uri': 'https://github.com/login/device',
            'access_token': SECRET,
            'token': SECRET,
            'authorization': 'Bearer ' + SECRET,
            'device_code': DEVICE,
            'client_secret': 'client-secret-value',
        }
        pending = github_auth.public_status(False, {'login': 'octocat', 'token': SECRET}, flow)
        assert_public(self, pending)
        self.assertEqual(pending['state'], 'pending')
        self.assertEqual(pending['user_code'], 'ABCD-EFGH')
        self.assertFalse(pending['configured'])
        self.assertNotIn('device_code', pending)
        self.assertNotIn('access_token', pending)

        failed = github_auth.public_status(False, None, {'status': 'error', 'error': 'failed ' + SECRET, 'token': SECRET})
        assert_public(self, failed)
        self.assertEqual(failed['state'], 'error')
        self.assertNotIn(SECRET, failed['error'])

        signed = github_auth.public_status(False, {'login': 'octocat', 'token': SECRET}, None)
        assert_public(self, signed)
        self.assertEqual((signed['state'], signed['login'], signed['configured'], signed['signed_in']),
                         ('signed-in', 'octocat', False, True))

    def test_status_endpoint_hides_the_saved_token_and_is_unconfigured_without_a_client_id(self):
        session = self.session([])
        session._save(SECRET, 'octocat')
        mirror = self.home / '.repotrace' / 'mirrors' / 'octo' / 'demo'
        mirror.mkdir(parents=True)
        (mirror / 'keep.txt').write_text('stay')
        server, state = app.make_server(recent_file=self.home / 'recent.json', browse=lambda: None, github=session)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(state.cleanup)

        status, body = self.request(server, state, 'GET', '/api/github/status')
        self.assertEqual(status, 200)
        assert_public(self, body)
        self.assertEqual(body['configured'], False)
        self.assertEqual(body['state'], 'signed-in')
        self.assertEqual(body['login'], 'octocat')

        status, body = self.request(server, state, 'POST', '/api/github/logout', {})
        self.assertEqual(status, 200)
        assert_public(self, body)
        self.assertEqual(body['state'], 'signed-out')
        self.assertFalse((self.home / '.repotrace' / 'github.json').exists())
        self.assertTrue((mirror / 'keep.txt').exists())

    def test_missing_client_id_env_leaves_device_sign_in_unconfigured(self):
        key = github_auth.CLIENT_ID_ENV
        old = os.environ.pop(key, None)
        try:
            session = github_auth.GitHubSession(home=self.home, opener=Scripted([]))
            self.addCleanup(session.close)
            shown = session.status()
        finally:
            if old is not None:
                os.environ[key] = old
        self.assertFalse(shown['configured'])
        self.assertEqual(shown['state'], 'signed-out')
        assert_public(self, shown, 'unused-secret-value')

    def request(self, server, state, method, path, body=None):
        import http.client
        conn = http.client.HTTPConnection('127.0.0.1', state.port, timeout=5)
        headers = {'Host': '127.0.0.1:%s' % state.port, 'X-RepoTrace-Token': state.token}
        data = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(body)
        conn.request(method, path, data, headers)
        response = conn.getresponse()
        raw = response.read().decode()
        conn.close()
        return response.status, json.loads(raw)


class DeviceFlowTests(GitHubCase):
    def test_device_flow_body_has_the_client_id_and_no_client_secret(self):
        body = github_auth.device_code_body(CLIENT)
        self.assertEqual(body['client_id'], CLIENT)
        self.assertEqual(body['scope'], 'read:user repo')
        self.assertNotIn('client_secret', body)
        encoded = urllib.parse.urlencode(body)
        self.assertIn('client_id=%s' % CLIENT, encoded)
        self.assertNotIn('client_secret', encoded)

        os.environ['REPO_TRACE_GITHUB_CLIENT_SECRET'] = 'super-secret-value'
        try:
            session = self.session([(200, device_payload(), {})], client_id=CLIENT)
            shown = session.start_device_flow(poll=False)
        finally:
            os.environ.pop('REPO_TRACE_GITHUB_CLIENT_SECRET', None)
        request = session.opener.requests[0]
        self.assertEqual(request.full_url, github_auth.DEVICE_CODE_URL)
        self.assertEqual(request.get_header('Accept'), 'application/json')
        parsed = posted(request)
        self.assertEqual(parsed['client_id'], [CLIENT])
        self.assertEqual(parsed['scope'], ['read:user repo'])
        self.assertNotIn('client_secret', parsed)
        self.assertNotIn('super-secret-value', request.data.decode())
        assert_public(self, shown)
        self.assertEqual(shown['state'], 'pending')
        self.assertEqual(shown['user_code'], 'ABCD-EFGH')
        self.assertEqual(shown['verification_uri'], 'https://github.com/login/device')

    def test_device_polling_honors_interval_slow_down_and_access_denied_without_storing(self):
        clock = Clock()
        steps = [
            (200, device_payload(), {}),
            (200, {'error': 'authorization_pending'}, {}),
            (200, {'error': 'slow_down'}, {}),
            (200, {'error': 'access_denied'}, {}),
        ]
        session = self.session(steps, client_id=CLIENT, wait=clock.wait, now=clock.now)
        session.start_device_flow(poll=True)
        self.wait_until(lambda: session.status()['state'] == 'error')
        self.assertEqual(clock.waits, [5, 5, 10])
        token_calls = [posted(request) for request in session.opener.requests if request.full_url == github_auth.TOKEN_URL]
        self.assertEqual(len(token_calls), 3)
        for body in token_calls:
            self.assertEqual(body['client_id'], [CLIENT])
            self.assertEqual(body['device_code'], [DEVICE])
            self.assertEqual(body['grant_type'], [github_auth.GRANT_TYPE])
            self.assertNotIn('client_secret', body)
        shown = session.status()
        assert_public(self, shown)
        self.assertIn('did not approve', shown['error'])
        self.assertFalse((self.home / '.repotrace' / 'github.json').exists())

    def test_an_expired_device_code_is_not_stored(self):
        clock = Clock()
        steps = [(200, device_payload(), {}), (200, {'error': 'expired_token'}, {})]
        session = self.session(steps, client_id=CLIENT, wait=clock.wait, now=clock.now)
        session.start_device_flow(poll=True)
        self.wait_until(lambda: session.status()['state'] == 'error')
        shown = session.status()
        assert_public(self, shown)
        self.assertIn('expired', shown['error'])
        self.assertFalse((self.home / '.repotrace' / 'github.json').exists())

    def test_a_token_github_rejects_with_401_is_not_stored(self):
        secret = 'ghp_rejectedtokenvalue0001'
        session = self.session([(401, {'message': secret, 'token': secret}, {})])
        with self.assertRaises(github_auth.GitHubError) as caught:
            session.accept_token(secret)
        self.assertNotIn(secret, str(caught.exception))
        self.assertFalse((self.home / '.repotrace' / 'github.json').exists())
        self.assertIsNone(session._load())

        session._save('ghp_goodtokenvalue000001', 'octocat')
        before = (self.home / '.repotrace' / 'github.json').read_text()
        session.opener.steps.append((401, {'message': 'Bad credentials'}, {}))
        with self.assertRaises(github_auth.GitHubError):
            session.accept_token('ghp_othertokenvalue00001')
        self.assertEqual((self.home / '.repotrace' / 'github.json').read_text(), before)
        self.assertNotIn('ghp_othertokenvalue00001', before)

    def test_device_flow_does_not_store_a_token_when_the_profile_returns_401(self):
        secret = 'gho_devicetokenvalue000001'
        clock = Clock()
        steps = [
            (200, device_payload(), {}),
            (200, {'access_token': secret}, {}),
            (401, {'message': secret}, {}),
        ]
        session = self.session(steps, client_id=CLIENT, wait=clock.wait, now=clock.now)
        session.start_device_flow(poll=True)
        self.wait_until(lambda: session.status()['state'] == 'error')
        shown = session.status()
        assert_public(self, shown, secret)
        self.assertFalse((self.home / '.repotrace' / 'github.json').exists())

    def wait_until(self, ready):
        deadline = time.time() + 2
        while time.time() < deadline:
            if ready():
                return
            time.sleep(0.01)
        self.fail('timed out')


class LogoutTests(GitHubCase):
    def test_logout_removes_the_token_file_and_leaves_the_mirror(self):
        session = self.session([])
        session._save(SECRET, 'octocat')
        path = self.home / '.repotrace' / 'github.json'
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        mirror = path.parent / 'mirrors' / 'octo' / 'demo'
        mirror.mkdir(parents=True)
        (mirror / 'keep.txt').write_text('stay')
        shown = session.logout()
        self.assertFalse(path.exists())
        self.assertTrue((mirror / 'keep.txt').exists())
        assert_public(self, shown)
        self.assertEqual(shown['state'], 'signed-out')
        self.assertFalse(shown['signed_in'])


class CloneTests(GitHubCase):
    def test_git_auth_is_only_in_the_command_environment(self):
        token = 'ghp_localtesttokenvalue0001'
        url = 'https://github.com/octo/demo.git'
        cmd, env = github_auth.git_invocation(['clone', '--origin', 'origin', url, '/tmp/demo'], token=token)
        self.assertNotIn(token, ' '.join(cmd))
        self.assertNotIn('extraheader', ' '.join(cmd).lower())
        self.assertNotIn(token, url)
        found = [env['GIT_CONFIG_VALUE_%d' % i] for i in range(int(env['GIT_CONFIG_COUNT']))
                 if env['GIT_CONFIG_KEY_%d' % i] == 'http.extraheader']
        self.assertEqual(found, ['AUTHORIZATION: bearer ' + token])
        for key, value in env.items():
            if key.startswith('GIT_CONFIG_VALUE_'):
                continue
            self.assertNotIn(token, str(value))

    def test_a_local_clone_and_fetch_do_not_store_the_token(self):
        token = 'ghp_localtesttokenvalue0001'
        src = self.home / 'src'
        src.mkdir()
        env = os.environ.copy()
        env.update({
            'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.com',
            'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.com',
            'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_SYSTEM': os.devnull,
        })
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(src)], check=True, env=env)
        (src / 'a.py').write_text('x = 1\n')
        subprocess.run(['git', '-C', str(src), 'add', 'a.py'], check=True, env=env)
        subprocess.run(['git', '-C', str(src), 'commit', '-q', '-m', 'init'], check=True, env=env)
        dest = self.home / 'mirror'
        github_auth.run_git(['clone', '--origin', 'origin', str(src), str(dest)], token=token)
        github_auth.run_git(['-C', str(dest), 'fetch', '--prune'], token=token)
        config = (dest / '.git' / 'config').read_text()
        self.assertNotIn(token, config)
        self.assertNotIn('extraheader', config.lower())
        self.assertNotIn('pull', config)
        remote = subprocess.run(['git', '-C', str(dest), 'remote', 'get-url', 'origin'],
                                check=True, capture_output=True, text=True, env=env)
        self.assertNotIn(token, remote.stdout)

    def test_use_repo_clones_then_fetches_without_putting_the_token_in_the_url(self):
        token = 'ghp_userepotokenvalue00001'
        calls = []

        def git_run(args, token=None, timeout=300):
            calls.append(list(args))
            self.assertNotIn('ghp_userepotokenvalue00001', ' '.join(args))
            if args[0] == 'clone':
                dest = Path(args[-1])
                (dest / '.git').mkdir(parents=True)
                (dest / '.git' / 'config').write_text(
                    '[remote "origin"]\n\turl = https://github.com/octo/demo.git\n')
            return b''

        repo = {'private': True, 'default_branch': 'main'}
        session = self.session([(200, repo, {}), (200, repo, {})], git_run=git_run)
        session._save(token, 'octo')
        copied = session.use_repo('octo/demo')
        self.assertEqual(calls[0][:3], ['clone', '--origin', 'origin'])
        self.assertEqual(calls[0][3], 'https://github.com/octo/demo.git')
        self.assertNotIn(token, calls[0][3])
        self.assertTrue(copied['repo'].endswith('/.repotrace/mirrors/octo/demo') or copied['repo'].endswith(
            '%s.repotrace%smirrors%socto%sdemo' % (os.sep, os.sep, os.sep, os.sep)))
        again = session.use_repo('octo/demo')
        self.assertEqual(calls[1], ['-C', again['repo'], 'fetch', '--prune'])
        for word in ('pull', 'reset', 'checkout'):
            self.assertNotIn(word, calls[1])

    def test_repository_list_follows_two_pages_and_drops_secrets(self):
        def page(number, count, nxt):
            items = []
            for index in range(count):
                items.append({
                    'name': 'r%s_%s' % (number, index),
                    'full_name': 'octo/r%s_%s' % (number, index),
                    'private': index % 2 == 0,
                    'default_branch': 'main',
                    'updated_at': '2026-01-02T03:04:05Z',
                    'owner': {'login': 'octo', 'avatar_url': 'https://avatars.githubusercontent.com/u/1'},
                    'access_token': SECRET,
                    'clone_url': 'https://%s@github.com/octo/r.git' % SECRET,
                })
            headers = {'Link': '<%s>; rel="next"' % nxt} if nxt else {}
            return 200, items, headers

        steps = [
            page(1, 40, 'https://api.github.com/user/repos?per_page=50&sort=updated&page=2'),
            page(2, 40, 'https://api.github.com/user/repos?per_page=50&sort=updated&page=3'),
            page(3, 40, 'https://api.github.com/user/repos?per_page=50&sort=updated&page=4'),
        ]
        session = self.session(steps)
        session._save(SECRET, 'octo')
        shown = session.list_repos()
        assert_public(self, shown)
        self.assertEqual(len(shown['repos']), 100)
        self.assertEqual(len(session.opener.requests), 3)
        self.assertIn('per_page=50', session.opener.requests[0].full_url)
        self.assertIn('sort=updated', session.opener.requests[0].full_url)
        self.assertNotIn('avatars.githubusercontent.com', json.dumps(shown))
        first = shown['repos'][0]
        self.assertEqual(first['private'], True)
        self.assertEqual(first['default_branch'], 'main')
        self.assertIn('2026-01-02', first['updated_at'])
        self.assertTrue(first['mirror'].endswith('octo%s%s' % (os.sep, 'r1_0')))


class LabSourceTests(unittest.TestCase):
    def test_the_lab_page_does_not_embed_a_token_or_skip_the_sign_in_panel(self):
        lab = Path(__file__).resolve().parents[1] / 'repotrace' / 'report' / 'lab'
        picker = (lab / 'picker.js').read_text()
        app_js = (lab / 'app.js').read_text()
        html = (lab / 'index.html').read_text()
        for text in (picker, app_js, html):
            self.assertNotIn('ghp_', text)
            self.assertNotIn('github_pat_', text)
            self.assertNotRegex(text, r'client_secret\s*[:=]')
        self.assertNotIn('localStorage', picker)
        self.assertIn('mountGitHub(boot, epoch)', picker)
        self.assertIn('https://github.com/signup', picker)
        self.assertIn('https://github.com/login/device', picker)
        self.assertIn('Sign-in cannot start', picker)
        self.assertIn('Clone a local copy for reading', picker)
        self.assertIn('Update the local copy for reading', picker)


if __name__ == '__main__':
    unittest.main()
