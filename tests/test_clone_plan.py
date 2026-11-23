"""Clone planning stays inside the mirror folder and never puts a token on the command line."""
import json
import tempfile
import unittest
from pathlib import Path

from repotrace.app import github_auth
from repotrace.app import server as app

TOKEN = 'ghp_environmentonly0000001'


class ClonePlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_https_github_waits_under_mirrors_and_keeps_the_token_off_the_command(self):
        plan = app.plan_clone(self.home, 'https://github.com/octo/hello.git', 'https')
        self.assertTrue(plan['dest'].endswith('/.repotrace/mirrors/octo/hello'))
        self.assertNotIn('/mirrors/github.com/', plan['dest'])
        self.assertFalse(Path(plan['dest']).exists())
        self.assertEqual(plan['action'], 'clone')
        calls = []

        def fake(args, token=None, timeout=300):
            calls.append((list(args), token))
            return b''

        done = app.perform_clone(self.home, 'https://github.com/octo/hello.git', 'https', plan['dest'], token=TOKEN, git_run=fake)
        self.assertEqual(done['action'], 'clone')
        self.assertEqual(calls[0][1], TOKEN)
        self.assertEqual(calls[0][0][0], 'clone')
        self.assertNotIn(TOKEN, calls[0][0])
        self.assertNotIn('pull', calls[0][0])
        self.assertNotIn('reset', calls[0][0])
        self.assertNotIn('checkout', calls[0][0])
        cmd, env = github_auth.git_invocation(
            ['clone', 'https://github.com/octo/hello.git', plan['dest']], token=TOKEN, hooks=str(self.home / 'hooks'))
        self.assertNotIn(TOKEN, ' '.join(cmd))
        keys = [key for key, value in env.items() if value == 'http.extraheader']
        self.assertEqual(len(keys), 1)
        index = keys[0].rsplit('_', 1)[1]
        self.assertIn(TOKEN, env['GIT_CONFIG_VALUE_' + index])

    def test_existing_mirror_fetches_without_pull_reset_or_checkout(self):
        plan = app.plan_clone(self.home, 'https://github.com/octo/hello.git', 'https')
        dest = Path(plan['dest'])
        (dest / '.git').mkdir(parents=True)
        again = app.plan_clone(self.home, 'https://github.com/octo/hello.git', 'https')
        self.assertEqual(again['action'], 'fetch')
        self.assertFalse(again['blocked'])
        calls = []

        def fake(args, token=None, timeout=300):
            calls.append(list(args))
            return b''

        app.perform_clone(self.home, 'https://github.com/octo/hello.git', 'https', again['dest'], token=TOKEN, git_run=fake)
        self.assertEqual(calls, [['-C', again['dest'], 'fetch', '--prune']])

    def test_confirm_must_match_and_other_hosts_do_not_receive_the_github_token(self):
        plan = app.plan_clone(self.home, 'https://gitlab.com/acme/widget.git', 'https')
        self.assertIn('/.repotrace/mirrors/gitlab.com/acme/widget', plan['dest'])
        calls = []

        def fake(args, token=None, timeout=300):
            calls.append((list(args), token))
            return b''

        with self.assertRaises(ValueError):
            app.perform_clone(self.home, 'https://gitlab.com/acme/widget.git', 'https', plan['dest'] + '-no', token=TOKEN, git_run=fake)
        self.assertEqual(calls, [])
        app.perform_clone(self.home, 'https://gitlab.com/acme/widget.git', 'https', plan['dest'], token=TOKEN, git_run=fake)
        self.assertIsNone(calls[0][1])
        self.assertNotIn(TOKEN, json.dumps(calls))

    def test_ssh_clone_uses_the_address_and_does_not_take_a_token_or_a_key(self):
        secret = 'ghp_publicstatussecret0001'
        with self.assertRaises(ValueError) as caught:
            app.plan_clone(self.home, 'https://x-access-token:' + secret + '@github.com/octo/hello.git', 'https')
        self.assertNotIn(secret, str(caught.exception))
        with self.assertRaises(ValueError):
            app.plan_clone(self.home, 'git@github.com:../hello.git', 'ssh')
        plan = app.plan_clone(self.home, 'git@example.com:group/sub/repo.git', 'ssh')
        self.assertTrue(plan['dest'].endswith('/.repotrace/mirrors/example.com/group/sub/repo'))
        self.assertEqual(plan['url'], 'git@example.com:group/sub/repo.git')
        calls = []

        def fake(args, token=None, timeout=300):
            calls.append((list(args), token))
            return b''

        app.perform_clone(self.home, 'git@example.com:group/sub/repo.git', 'ssh', plan['dest'], token=secret, git_run=fake)
        self.assertIsNone(calls[0][1])
        self.assertEqual(calls[0][0][0], 'clone')
        self.assertIn('git@example.com:group/sub/repo.git', calls[0][0])
        self.assertNotIn(secret, json.dumps(calls))
        self.assertNotIn('pull', calls[0][0])

    def test_a_non_git_folder_is_not_replaced(self):
        plan = app.plan_clone(self.home, 'https://github.com/octo/hello.git', 'https')
        Path(plan['dest']).mkdir(parents=True)
        blocked = app.plan_clone(self.home, 'https://github.com/octo/hello.git', 'https')
        self.assertTrue(blocked['blocked'])
        calls = []
        with self.assertRaises(ValueError):
            app.perform_clone(self.home, 'https://github.com/octo/hello.git', 'https', blocked['dest'], git_run=lambda *a, **k: calls.append(1))
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
