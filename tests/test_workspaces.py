import tempfile
import unittest
from pathlib import Path
from repotrace.app import workspaces
from repotrace.changes.git_snapshot import run_git


class TestWorkspaces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # Create a dummy git repo
        self.repo = self.root / 'test-repo'
        self.repo.mkdir()
        run_git(self.repo, 'init', '-b', 'main')
        run_git(self.repo, 'config', 'user.name', 'Tester')
        run_git(self.repo, 'config', 'user.email', 'test@example.com')
        (self.repo / 'main.py').write_text('def hello(): pass\n')
        run_git(self.repo, 'add', '.')
        run_git(self.repo, 'commit', '-m', 'Initial commit')
        (self.repo / 'main.py').write_text('def hello(): return 1\n')
        run_git(self.repo, 'commit', '-a', '-m', 'Second commit')

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_workspace(self):
        ws = workspaces.create_workspace('My Project', str(self.repo), description='A test workspace', root=self.root / 'ws')
        self.assertEqual(ws['name'], 'My Project')
        self.assertEqual(ws['repo'], str(self.repo))
        self.assertEqual(ws['description'], 'A test workspace')
        self.assertEqual(ws['versions'], [])
        self.assertIsNotNone(ws['id'])

    def test_create_workspace_validation(self):
        with self.assertRaises(ValueError):
            workspaces.create_workspace('', str(self.repo), root=self.root / 'ws')
        with self.assertRaises(ValueError):
            workspaces.create_workspace('Name', '', root=self.root / 'ws')

    def test_add_version(self):
        ws_root = self.root / 'ws'
        ws = workspaces.create_workspace('Test', str(self.repo), root=ws_root)
        updated = workspaces.add_version(ws['id'], 'abc1234567', subject='Fix something', author='Alice', root=ws_root)
        self.assertEqual(len(updated['versions']), 1)
        self.assertEqual(updated['versions'][0]['commit'], 'abc1234567')
        self.assertEqual(updated['versions'][0]['short'], 'abc12345')
        self.assertEqual(updated['versions'][0]['subject'], 'Fix something')

    def test_auto_capture_versions(self):
        ws_root = self.root / 'ws'
        ws = workspaces.create_workspace('Test', str(self.repo), root=ws_root)
        captured = workspaces.auto_capture_versions(ws['id'], str(self.repo), limit=10, root=ws_root)
        self.assertEqual(len(captured['versions']), 2)
        # Check commits are recorded
        subjects = [v['subject'] for v in captured['versions']]
        self.assertIn('Initial commit', subjects)
        self.assertIn('Second commit', subjects)

    def test_list_and_get_workspace(self):
        ws_root = self.root / 'ws'
        ws1 = workspaces.create_workspace('First', str(self.repo), root=ws_root)
        ws2 = workspaces.create_workspace('Second', str(self.repo), root=ws_root)
        all_ws = workspaces.list_workspaces(root=ws_root)
        self.assertEqual(len(all_ws), 2)
        got = workspaces.get_workspace(ws1['id'], root=ws_root)
        self.assertEqual(got['name'], 'First')

    def test_rename_and_delete_workspace(self):
        ws_root = self.root / 'ws'
        ws = workspaces.create_workspace('Original', str(self.repo), root=ws_root)
        renamed = workspaces.rename_workspace(ws['id'], 'New Name', root=ws_root)
        self.assertEqual(renamed['name'], 'New Name')
        self.assertTrue(workspaces.delete_workspace(ws['id'], root=ws_root))
        self.assertIsNone(workspaces.get_workspace(ws['id'], root=ws_root))

    def test_compare_versions(self):
        ws_root = self.root / 'ws'
        ws = workspaces.create_workspace('Test', str(self.repo), root=ws_root)
        workspaces.add_version(ws['id'], 'commit1', subject='First', root=ws_root)
        workspaces.add_version(ws['id'], 'commit2', subject='Second', root=ws_root)
        base, head = workspaces.compare_versions(ws['id'], 0, 1, root=ws_root)
        self.assertEqual(base, 'commit1')
        self.assertEqual(head, 'commit2')
        with self.assertRaises(ValueError):
            workspaces.compare_versions(ws['id'], 0, 0, root=ws_root)

    def test_snapshot_working_tree(self):
        # 1. Clean repo returns None
        self.assertIsNone(workspaces.snapshot_working_tree(self.repo))

        # 2. Modify file in repo
        (self.repo / 'main.py').write_text('def hello(): return 42\n')
        head_before = run_git(self.repo, 'rev-parse', 'HEAD').decode().strip()
        snap = workspaces.snapshot_working_tree(self.repo, subject='Test snapshot')
        self.assertIsNotNone(snap)
        self.assertEqual(snap['subject'], 'Test snapshot')
        self.assertTrue(snap.get('is_snapshot'))

        # Verify HEAD was NOT moved
        head_after = run_git(self.repo, 'rev-parse', 'HEAD').decode().strip()
        self.assertEqual(head_before, head_after)

        # Verify git diff between HEAD and snapshot commit
        diff = run_git(self.repo, 'diff', head_before, snap['commit']).decode()
        self.assertIn('+def hello(): return 42', diff)

    def test_snapshot_non_git_directory_and_zip(self):
        import io
        import zipfile
        ws_root = self.root / 'ws'
        plain_dir = self.root / 'plain-folder'
        plain_dir.mkdir()
        (plain_dir / 'script.py').write_text('print("hello from folder")\n')
        ws = workspaces.create_workspace('Plain', str(plain_dir), root=ws_root)
        captured = workspaces.auto_capture_versions(ws['id'], str(plain_dir), root=ws_root)
        self.assertEqual(len(captured['versions']), 1)

        # Test zip upload
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('app.py', 'print("hello from zip")\n')
        ws2, is_new = workspaces.snapshot_zip_to_mirror(
            ws['id'], buf.getvalue(), filename='release.zip', subject='Zip v1', root=ws_root
        )
        self.assertTrue(is_new)
        self.assertGreaterEqual(len(ws2['versions']), 2)


class TestWorkspaceServerAPI(unittest.TestCase):
    def setUp(self):
        import http.client
        import threading
        from repotrace.app import server as app
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ws_dir = self.root / 'workspaces'
        self.ws_dir.mkdir()
        # Patch default workspaces dir for testing
        self._orig_dir = workspaces.DEFAULT_DIR
        workspaces.DEFAULT_DIR = self.ws_dir

        # Create a real git repo
        self.repo = self.root / 'sample-repo'
        self.repo.mkdir()
        run_git(self.repo, 'init', '-b', 'main')
        run_git(self.repo, 'config', 'user.name', 'Tester')
        run_git(self.repo, 'config', 'user.email', 'test@example.com')
        (self.repo / 'app.py').write_text('def add(a, b): return a + b\n')
        run_git(self.repo, 'add', '.')
        run_git(self.repo, 'commit', '-m', 'Commit 1')
        (self.repo / 'app.py').write_text('def add(a, b): return a + b + 1\n')
        run_git(self.repo, 'commit', '-a', '-m', 'Commit 2')

        recent_file = self.root / 'recent.json'
        self.server, self.state = app.make_server(recent_file=recent_file)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        workspaces.DEFAULT_DIR = self._orig_dir
        self.server.shutdown()
        self.server.server_close()
        self.state.cleanup()
        self.tmp.cleanup()

    def call(self, method, path, body=None):
        import http.client
        import json
        conn = http.client.HTTPConnection('127.0.0.1', self.state.port, timeout=30)
        h = {'Host': f'127.0.0.1:{self.state.port}', 'X-RepoTrace-Token': self.state.token}
        if body is not None:
            h['Content-Type'] = 'application/json'
        conn.request(method, path, json.dumps(body) if body is not None else None, h)
        response = conn.getresponse()
        raw = response.read().decode('utf-8')
        conn.close()
        try:
            return response.status, json.loads(raw)
        except ValueError:
            return response.status, raw

    def test_workspace_crud_via_api(self):
        # 1. State includes workspaces
        status, data = self.call('GET', '/api/state')
        self.assertEqual(status, 200)
        self.assertIn('workspaces', data)
        self.assertEqual(len(data['workspaces']), 0)

        # 2. Create workspace
        status, ws = self.call('POST', '/api/workspace/create', {
            'name': 'API Workspace',
            'repo': str(self.repo),
            'description': 'Testing via HTTP',
        })
        self.assertEqual(status, 200)
        self.assertEqual(ws['name'], 'API Workspace')
        self.assertGreaterEqual(len(ws['versions']), 2)

        # 3. List workspaces
        status, data = self.call('GET', '/api/workspaces')
        self.assertEqual(status, 200)
        self.assertEqual(len(data['workspaces']), 1)
        self.assertEqual(data['workspaces'][0]['name'], 'API Workspace')

        # 4. Get workspace details
        status, got = self.call('GET', f'/api/workspace?id={ws["id"]}')
        self.assertEqual(status, 200)
        self.assertEqual(got['id'], ws['id'])

        # 5. Refresh workspace
        status, refreshed = self.call('POST', '/api/workspace/refresh', {'id': ws['id']})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(refreshed['versions']), 2)

        # 5b. Upload new version to workspace
        status, uploaded = self.call('POST', '/api/workspace/upload-version', {
            'id': ws['id'],
            'mode': 'commit',
            'commit': '9998887776',
            'subject': 'Uploaded manual version',
            'author': 'Tester',
        })
        self.assertEqual(status, 200)
        self.assertTrue(any(v['commit'] == '9998887776' for v in uploaded['versions']))

        # 5c. Add repo to workspace / create via add-repo
        status, added_ws = self.call('POST', '/api/workspace/add-repo', {
            'repo': str(self.repo),
            'name': 'Added From Repo',
        })
        self.assertEqual(status, 200)
        self.assertEqual(added_ws['name'], 'Added From Repo')
        self.assertGreaterEqual(len(added_ws['versions']), 2)

        # 6. Rename workspace
        status, renamed = self.call('POST', '/api/workspace/rename', {'id': ws['id'], 'name': 'Renamed WS'})
        self.assertEqual(status, 200)
        self.assertEqual(renamed['name'], 'Renamed WS')

        # 7. Compare workspace versions
        status, cmp_res = self.call('POST', '/api/workspace/compare', {
            'id': ws['id'],
            'base_index': 0,
            'head_index': 1,
        })
        self.assertEqual(status, 200)
        self.assertIn('job', cmp_res)
        self.assertIn('base', cmp_res)
        self.assertIn('head', cmp_res)

        # 8. Delete workspace
        status, del_res = self.call('POST', '/api/workspace/delete', {'id': ws['id']})
        self.assertEqual(status, 200)
        self.assertTrue(del_res['ok'])

    def test_upload_dirty_worktree_and_zip_via_api(self):
        import base64
        import io
        import zipfile

        # Create workspace with clean repo
        status, ws = self.call('POST', '/api/workspace/create', {
            'name': 'Dirty Repo WS',
            'repo': str(self.repo),
        })
        self.assertEqual(status, 200)
        initial_ver_count = len(ws['versions'])

        # 1. Upload without any changes -> added_count: 0
        status, res1 = self.call('POST', '/api/workspace/upload-version', {
            'id': ws['id'],
            'mode': 'folder',
            'repo': str(self.repo),
        })
        self.assertEqual(status, 200)
        self.assertEqual(res1['added_count'], 0)
        self.assertIn('up to date', res1['message'])

        # 2. Make uncommitted changes in repo
        (self.repo / 'app.py').write_text('def add(a, b): return a + b + 99\n')
        status, res2 = self.call('POST', '/api/workspace/upload-version', {
            'id': ws['id'],
            'mode': 'folder',
            'repo': str(self.repo),
            'note': 'Working snapshot via API',
        })
        self.assertEqual(status, 200)
        self.assertEqual(res2['added_count'], 1)
        self.assertIn('Working snapshot via API', res2['versions'][-1]['subject'])
        self.assertEqual(len(res2['versions']), initial_ver_count + 1)

        # 3. Upload zip via API
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('module.py', 'X = 123\n')
        zip_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        status, res3 = self.call('POST', '/api/workspace/upload-version', {
            'id': ws['id'],
            'mode': 'zip',
            'filename': 'bundle.zip',
            'zip_base64': zip_b64,
            'note': 'Zip release 1.0',
        })
        self.assertEqual(status, 200)
        self.assertEqual(res3['added_count'], 1)
        self.assertIn('Zip release 1.0', res3['versions'][-1]['subject'])



if __name__ == '__main__':
    unittest.main()
