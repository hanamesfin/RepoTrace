// Live start: choose a project folder, choose two versions to compare (or none), wait for the analysis, then start the Lab on the result.
// Talks only to the local app (same origin) with the per-launch token. Nothing here reads files or runs code.
(function (root) {
  'use strict';
  const $ = id => document.getElementById(id);
  const h = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const token = (document.querySelector('meta[name=rt-token]') || {}).content || '';
  const ico = name => `<svg class="ico" aria-hidden="true" focusable="false"><use href="#i-${name}"/></svg>`;
  const mark = (name, tone) => `<svg class="logo${tone ? ' ' + tone : ''}" aria-hidden="true" focusable="false"><use href="#i-${name}"/></svg>`;
  const calm = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // The steps, in the order the engine really runs them. A reversed run reads the newer version first, so the names say so.
  const STEPS = {check: 'Check the project', map: 'Map the working folder', analyze_before: 'Read the older version', analyze_after: 'Read the newer version',
    compare: 'Compare the two versions', impact: 'Find what could be affected', finish: 'Prepare the screens'};
  const REVERSED = {analyze_before: 'Read the starting version (the newer one)', analyze_after: 'Read the ending version (the older one)'};
  const FLOW = {compare: ['check', 'map', 'analyze_before', 'analyze_after', 'compare', 'impact', 'finish'], explore: ['check', 'map', 'finish']};
  const note = detail => {                                        // the part of the engine's sentence worth showing under a step
    const commit = String(detail || '').match(/\(([0-9a-f]{7,40})\)/i);
    if (commit) return `Commit ${commit[1].slice(0, 8)}`;
    const count = String(detail || '').match(/\((\d+) of (\d+)\)/);
    return count ? `${count[1]} of ${count[2]} changed definitions` : '';
  };
  const clock = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  const took = seconds => seconds < 60 ? `${seconds.toFixed(1)} s` : clock(seconds);

  async function api(path, body) {
    const res = await fetch(path, {method: body ? 'POST' : 'GET', headers: {'X-RepoTrace-Token': token, ...(body ? {'Content-Type': 'application/json'} : {})}, body: body ? JSON.stringify(body) : undefined});
    const data = await res.json().catch(() => ({error: 'The app answered in a way this page cannot read.'}));
    if (!res.ok) throw new Error(data.error || `The request failed (${res.status}).`);
    return data;
  }
  const page = html => { $('content').innerHTML = `<div class="compact picker">${html}</div>`; $('content').focus({preventScroll: true}); };
  const openHome = on => { const shell = document.querySelector('.shell'); if (shell) shell.classList.toggle('open-home', !!on); };
  const ago = ms => { if (!ms) return ''; const s = (Date.now() - Number(ms)) / 1000; if (!Number.isFinite(s) || s < 0) return ''; if (s < 60) return 'Just now'; if (s < 3600) return `${Math.floor(s / 60)}m ago`; if (s < 86400) return `${Math.floor(s / 3600)}h ago`; return `${Math.floor(s / 86400)}d ago`; };
  const busy = on => { const shell = document.querySelector('.shell'); if (shell) { if (on) shell.dataset.busy = '1'; else delete shell.dataset.busy; } };
  // An error that has a way out. `back` says where the button goes.
  const failPage = (message, label, back) => {
    busy(false);
    page(`<div class="notice"><strong>${h(message)}</strong></div><div class="action-row"><button class="primary" id="again">${h(label)}</button></div>`);
    $('again').addEventListener('click', back);
  };
  const fail = message => { const box = $('picker-error'); if (box) { box.textContent = message; box.hidden = false; box.scrollIntoView({block: 'nearest'}); } else failPage(message, 'Back', () => (root.PROTO ? root.RTLab(root.PROTO) : start(root.RTLab))); };

  let githubEpoch = 0;
  let githubTimer = 0;
  let githubSeen = {configured: false, signed_in: false, state: 'signed-out'};
  const SCOPE_NOTE = 'RepoTrace can read your GitHub profile and repository contents, including private repositories, so it can list repositories and clone one onto this computer. It cannot write to GitHub.';
  const PAT_NOTE = 'Create a fine-grained or classic token with read access to contents and to your profile. It is sent once to this computer and stays in ~/.repotrace on this computer. It is not kept in the page.';
  const SIGNUP = '<a class="github-link" href="https://github.com/signup" target="_blank" rel="noopener noreferrer">New to GitHub? Create an account</a>';

  function githubSignedIn(status) {
    return !!(status && status.signed_in && status.login);
  }
  function patForm() {
    return `<form id="github-token-form" class="github-token" method="post"><label for="github-token">Personal access token</label><input id="github-token" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" inputmode="text" aria-describedby="github-token-note"><button class="secondary" type="submit">Use this token</button><p id="github-token-note" class="help-text">${h(PAT_NOTE)}</p></form>`;
  }
  function githubError(status) {
    return status && status.state === 'error' && status.error ? `<div class="notice" role="alert"><strong>${h(status.error)}</strong></div>` : '';
  }
  function signedOutHtml(status) {
    const pending = status && status.state === 'pending';
    if (pending) {
      const code = status.user_code || '';
      const again = status.configured ? '<button type="button" class="secondary" id="github-device">Start again</button>' : '';
      return `<h2 id="github-title">${mark('github','gh')} GitHub</h2><p class="help-text">${h(SCOPE_NOTE)}</p>${githubError(status)}<p id="github-state">Enter this code on GitHub. This page stays signed out until GitHub approves it.</p><p class="github-code" aria-live="polite">${code ? h(code) : 'GitHub has not returned a code.'}</p><p><a class="github-link" href="https://github.com/login/device" target="_blank" rel="noopener noreferrer">https://github.com/login/device</a></p><p>${SIGNUP} Account creation happens on GitHub's site.</p><div class="action-row">${again}</div><p class="help-text">Waiting for GitHub. RepoTrace will not say you are signed in until GitHub approves the code.</p>${patForm()}`;
    }
    if (!status || !status.configured) {
      return `<h2 id="github-title">${mark('github','gh')} GitHub</h2>${githubError(status)}<p id="github-state">Signed out. Sign-in cannot start until you create a GitHub OAuth app. Set the homepage to http://127.0.0.1 and the callback URL to http://127.0.0.1, then start RepoTrace with that client id in REPO_TRACE_GITHUB_CLIENT_ID. This screen will not pretend to sign you in.</p><p class="help-text">${h(SCOPE_NOTE)}</p><p>${SIGNUP} Account creation happens on GitHub's site.</p>${patForm()}`;
    }
    return `<h2 id="github-title">${mark('github','gh')} GitHub</h2>${githubError(status)}<p id="github-state">Signed out. ${h(SCOPE_NOTE)}</p><div class="action-row"><button type="button" class="primary" id="github-device">Sign in with GitHub</button></div><p>${SIGNUP} Account creation happens on GitHub's site.</p>${patForm()}`;
  }
  function signedInHtml(status) {
    return `<h2 id="github-title">${mark('github','gh')} GitHub</h2><p id="github-state">Signed in as <strong>${h(status.login)}</strong>.</p><div class="action-row"><button type="button" class="secondary" id="github-logout">Sign out</button><button type="button" class="secondary" id="github-refresh">Refresh repositories</button></div><p class="help-text">Sign out removes the GitHub token from this computer. It does not delete the local copy.</p><div id="github-repos"><p class="help-text">Loading repositories…</p></div>`;
  }
  function repoButtonLabel(repo) {
    return repo && repo.mirrored ? 'Update the local copy for reading' : 'Clone a local copy for reading';
  }
  function repoHtml(repo) {
    const vis = repo.private === true ? 'Private' : repo.private === false ? 'Public' : 'Visibility not provided';
    const branch = repo.default_branch || 'no default branch';
    const when = repo.updated_at ? String(repo.updated_at).replace('T', ' ').replace('Z', ' UTC') : 'updated time not provided by GitHub';
    const name = repo.full_name || repo.name || 'Unnamed repository';
    return `<article class="github-repo"><div><strong>${h(name)}</strong><span>${h(vis)} · ${h(branch)} · ${h(when)}</span><span class="github-path">Local copy: ${h(repo.mirror || '')}</span></div><button type="button" class="secondary" data-repo="${h(repo.full_name || '')}">${h(repoButtonLabel(repo))}</button></article>`;
  }
  function paintGitHub(boot, status, epoch) {
    const panel = $('github-panel');
    if (!panel || epoch !== githubEpoch) return;
    clearTimeout(githubTimer);
    const current = status || {configured: false, signed_in: false, state: 'signed-out'};
    const fp = [current.state || '', current.configured ? '1' : '0', current.signed_in ? '1' : '0', current.login || '', current.user_code || '', current.error || ''].join('\n');
    if (current.state === 'pending' && panel.dataset.githubFp === fp && panel.querySelector('#github-token-form')) {
      githubTimer = setTimeout(() => refreshGitHub(boot, epoch), 2000);
      return;
    }
    panel.dataset.githubFp = fp;
    const signedIn = githubSignedIn(current);
    panel.innerHTML = signedIn ? signedInHtml(current) : signedOutHtml(current);
    bindGitHub(boot, current, epoch);
    if (signedIn) loadRepos(boot, epoch);
    else if (current.state === 'pending') githubTimer = setTimeout(() => refreshGitHub(boot, epoch), 2000);
  }
  async function refreshGitHub(boot, epoch) {
    if (epoch !== githubEpoch || !$('github-panel')) return;
    try {
      githubSeen = await api('/api/github/status');
      paintGitHub(boot, githubSeen, epoch);
    } catch (e) {
      paintGitHub(boot, {configured: !!githubSeen.configured, signed_in: false, login: null, state: 'error', error: e.message}, epoch);
    }
  }
  async function mountGitHub(boot, epoch) {
    if (epoch !== githubEpoch) return;
    try {
      githubSeen = await api('/api/github/status');
      paintGitHub(boot, githubSeen, epoch);
    } catch (e) {
      paintGitHub(boot, {configured: !!githubSeen.configured, signed_in: false, login: null, state: 'error', error: e.message}, epoch);
    }
  }
  async function loadRepos(boot, epoch) {
    const box = $('github-repos');
    if (!box || epoch !== githubEpoch) return;
    try {
      const data = await api('/api/github/repos');
      if (epoch !== githubEpoch || !$('github-repos')) return;
      const repos = data.repos || [];
      box.innerHTML = repos.length ? `<div class="github-repos">${repos.map(repoHtml).join('')}</div>` : '<p class="help-text">GitHub returned no repositories.</p>';
      box.querySelectorAll('[data-repo]').forEach(button => button.addEventListener('click', () => useRepo(boot, epoch, button)));
    } catch (e) {
      if ($('github-repos')) $('github-repos').innerHTML = `<div class="notice" role="alert"><strong>${h(e.message)}</strong></div>`;
    }
  }
  async function useRepo(boot, epoch, button) {
    if (epoch !== githubEpoch) return;
    const full = button.dataset.repo;
    button.disabled = true;
    const label = button.textContent;
    button.textContent = 'Copying the local copy for reading…';
    try {
      const copied = await api('/api/github/use', {full_name: full});
      const info = await api('/api/inspect', {repo: copied.repo});
      githubEpoch += 1;
      clearTimeout(githubTimer);
      stepTwo(boot, info);
    } catch (e) {
      button.disabled = false;
      button.textContent = label;
      fail(e.message);
    }
  }
  function bindGitHub(boot, status, epoch) {
    const device = $('github-device');
    if (device) device.addEventListener('click', async () => {
      device.disabled = true;
      try {
        const started = await api('/api/github/device', {});
        githubSeen = {configured: true, signed_in: false, login: null, state: 'pending', user_code: started.user_code, verification_uri: started.verification_uri};
        paintGitHub(boot, githubSeen, epoch);
      } catch (e) {
        const current = await api('/api/github/status').catch(() => ({configured: false}));
        paintGitHub(boot, {configured: !!current.configured, signed_in: false, login: null, state: 'error', error: e.message}, epoch);
      }
    });
    const form = $('github-token-form');
    if (form) form.addEventListener('submit', async ev => {
      ev.preventDefault();
      const input = $('github-token');
      const value = input ? input.value : '';
      if (input) input.value = '';
      try { paintGitHub(boot, await api('/api/github/token', {token: value}), epoch); }
      catch (e) {
        const current = await api('/api/github/status').catch(() => ({configured: !!(status && status.configured)}));
        if (githubSignedIn(current)) { paintGitHub(boot, current, epoch); return; }
        paintGitHub(boot, {configured: !!current.configured, signed_in: false, login: null, state: 'error', error: e.message}, epoch);
      }
    });
    const logout = $('github-logout');
    if (logout) logout.addEventListener('click', async () => {
      logout.disabled = true;
      try { paintGitHub(boot, await api('/api/github/logout', {}), epoch); }
      catch (e) { logout.disabled = false; fail(e.message); }
    });
    const refresh = $('github-refresh');
    if (refresh) refresh.addEventListener('click', () => loadRepos(boot, epoch));
  }

  function start(boot) {
    $('snapshot').textContent = 'Local · nothing is uploaded';
    $('location').textContent = 'Open a project';
    $('navigation').innerHTML = '';
    for (const id of ['project-card', 'rail-label']) { const el = $(id); if (el) el.hidden = true; }      // no project yet, so no project card
    document.querySelectorAll('[data-project]').forEach(el => { el.textContent = ''; });
    $('back').disabled = true;
    stepOne(boot);
  }

  function githubRowNote(status) {
    if (!status || !status.configured) return 'Sign-in is not configured';
    if (status.signed_in && status.login) return 'Signed in as ' + status.login;
    if (status.state === 'pending') return 'Waiting for GitHub. Not signed in yet.';
    if (status.state === 'error') return 'Signed out. GitHub did not finish sign-in.';
    return 'Signed out';
  }

  async function stepOne(boot) {
    githubEpoch += 1;
    clearTimeout(githubTimer);
    const epoch = githubEpoch;
    let info = {recent: [], can_browse: false, initial_repo: null};
    let gh = {configured: false, signed_in: false, state: 'signed-out'};
    const row = (title, note, panel, extra) => `<button type="button" class="menu-row" data-panel="${h(panel)}" ${extra || ''}><span class="menu-copy"><strong>${h(title)}</strong><small>${h(note)}</small></span><span class="menu-go" aria-hidden="true">${ico('arrow')}</span></button>`;
    const backBar = '<div class="action-row"><button type="button" class="secondary" id="menu-back">All open options</button></div>';
    const leave = () => { githubEpoch += 1; clearTimeout(githubTimer); };

    async function openCompare(path) {
      const box = $('picker-error'); if (box) box.hidden = true;
      try {
        const inspected = await api('/api/inspect', {repo: path});
        leave();
        stepTwo(boot, inspected);
      } catch (e) { fail(e.message); }
    }
    async function explore(path) {
      const box = $('picker-error'); if (box) box.hidden = true;
      if (!path) { fail('Type the project folder first.'); return; }
      try {
        const started = await api('/api/lab', {repo: path});
        leave();
        waiting(started.job, {compare: false, reverse: false, back: () => stepOne(boot)});
      } catch (e) { fail(e.message); }
    }
    function bindBack() {
      const back = $('menu-back');
      if (back) back.addEventListener('click', () => { clearTimeout(githubTimer); show('menu'); });
    }
    function pathPanel(mode) {
      const copy = {
        local: ['ON THIS MAC', 'On This Mac', 'Open a folder on this computer. A GitHub account is not required.', 'Open'],
        workspace: ['ONE FOLDER', 'Open another folder', 'This opens one folder, the same way as Open Folder. RepoTrace keeps one folder at a time. It does not add a second root.', 'Open this folder'],
        explore: ['MAP ONLY', 'Start from scratch', 'Map this folder only. No two versions are compared.', 'Explore without comparing'],
      }[mode];
      page(`${backBar}<div class="page-header"><span class="eyebrow">${copy[0]}</span><h1>${copy[1]}</h1><p>${copy[2]}</p></div>
        <form id="open-form" class="stack"><label class="field-label" for="repo-path">Project folder</label>
        <div class="search-form open-form"><span class="search-icon" aria-hidden="true">${ico('folder')}</span><input id="repo-path" aria-label="Path to the project folder" placeholder="/path/to/your/project" value="${h(info.initial_repo || '')}" autocomplete="off" required>${info.can_browse ? '<button type="button" class="secondary" id="browse">Browse…</button>' : ''}<button class="primary" type="submit">${copy[3]}</button></div></form>
        <div class="notice" id="picker-error" hidden></div>`);
      bindBack();
      const go = () => { const path = $('repo-path').value.trim(); if (mode === 'explore') explore(path); else openCompare(path); };
      $('open-form').addEventListener('submit', ev => { ev.preventDefault(); go(); });
      const browse = $('browse');
      if (browse) browse.addEventListener('click', async () => {
        try { const picked = await api('/api/browse', {}); if (picked.path) { $('repo-path').value = picked.path; go(); } }
        catch (e) { fail(e.message); }
      });
      $('repo-path').focus();
    }
    function clonePanel(kind) {
      const ssh = kind === 'ssh';
      page(`${backBar}<div class="page-header"><span class="eyebrow">${ssh ? 'SSH' : 'REMOTE'}</span><h1>${ssh ? ico('term') : ico('clone')} ${ssh ? 'Connect via SSH' : 'Clone repository'}</h1><p>${ssh
        ? 'Use an address like git@host:owner/repo.git. RepoTrace does not collect or store SSH keys. If Git cannot use the keys already on this computer, Git’s error is shown here.'
        : 'Paste an https repository address. RepoTrace clones into a folder under your home directory only after you confirm that path. If the folder is already there, it runs git fetch --prune and does not pull, reset, or check out.'}</p></div>
        <form id="clone-form" class="stack"><label class="field-label" for="clone-url">${ssh ? 'SSH address' : 'Repository URL'}</label>
        <div class="search-form open-form"><input id="clone-url" aria-label="${ssh ? 'SSH address' : 'Repository URL'}" placeholder="${ssh ? 'git@host:owner/repo.git' : 'https://host/owner/repo.git'}" autocomplete="off" spellcheck="false" required><button class="primary" type="submit">Show the local folder</button></div></form>
        <div id="clone-plan"></div><div class="notice" id="picker-error" hidden></div>`);
      bindBack();
      const paintPlan = plan => {
        const box = $('clone-plan'); if (!box) return;
        if (plan.blocked) {
          box.innerHTML = `<div class="notice" role="alert"><strong>That folder already exists and is not a Git clone.</strong><p>${h(plan.dest)} RepoTrace will not replace it.</p></div>`;
          return;
        }
        const verb = plan.action === 'fetch' ? 'Fetch' : 'Clone';
        const detail = plan.action === 'fetch'
          ? 'This folder already exists. After you confirm, RepoTrace runs git fetch --prune only. It does not pull, reset, or check out.'
          : 'After you confirm, RepoTrace runs git clone into this folder.';
        box.innerHTML = `<section class="card" aria-labelledby="dest-title"><h2 id="dest-title">${verb} into this folder</h2><p class="clone-path">${h(plan.dest)}</p><p>${detail}</p><button type="button" class="primary" id="clone-go">${verb} into this folder</button></section>`;
        $('clone-go').addEventListener('click', async () => {
          $('clone-go').disabled = true;
          try {
            const done = await api('/api/clone', {url: plan.url, kind, confirm: plan.dest});
            const inspected = await api('/api/inspect', {repo: done.repo});
            leave();
            stepTwo(boot, inspected);
          } catch (e) {
            if ($('clone-go')) $('clone-go').disabled = false;
            fail(e.message);
          }
        });
      };
      $('clone-url').addEventListener('input', () => { const box = $('clone-plan'); if (box) box.innerHTML = ''; });
      $('clone-form').addEventListener('submit', async ev => {
        ev.preventDefault();
        const submit = ev.target.querySelector('button[type="submit"]');
        if (submit) submit.disabled = true;
        try { paintPlan(await api('/api/clone', {url: $('clone-url').value.trim(), kind})); }
        catch (e) { fail(e.message); }
        finally { if (submit) submit.disabled = false; }
      });
      $('clone-url').focus();
    }
    function showGitHub() {
      page(`${backBar}<section class="github-panel" id="github-panel" aria-labelledby="github-title"><h2 id="github-title">GitHub</h2><p id="github-state">Reading GitHub sign-in…</p></section><div class="notice" id="picker-error" hidden></div>`);
      bindBack();
      mountGitHub(boot, epoch);
    }
    function showUnavailable(which) {
      const name = which === 'gitlab' ? 'GitLab' : 'Azure DevOps';
      const logo = which === 'gitlab' ? mark('gitlab','gl') : mark('azure','az');
      page(`${backBar}<div class="page-header"><span class="eyebrow">CONNECT</span><h1>${logo} ${name}</h1></div><div class="notice" role="status"><strong>${name} is not connected.</strong><p>This app has no ${name} OAuth client, so RepoTrace cannot sign you in. Nothing was connected.</p></div>`);
      bindBack();
    }

    // ---- Workspaces ----
    function wsCard(ws) {
      const when = ago(ws.updated);
      const versions = ws.version_count || 0;
      const latest = ws.latest_version;
      const sub = latest ? `Latest: ${h(latest.short || latest.commit?.slice(0, 8) || '?')} · ${h(latest.subject || '(no message)')}` : 'No versions yet';
      return `<article class="ws-card">
        <span class="ws-mark" aria-hidden="true">${ico('workspace')}</span>
        <div class="ws-id">
          <strong>${h(ws.name)}</strong>
          <small>${h(ws.repo_name || ws.repo)} · ${versions} version${versions !== 1 ? 's' : ''}</small>
          <small class="ws-sub">${h(sub)}</small>
        </div>
        ${when ? `<time>${h(when)}</time>` : ''}
        <button type="button" class="ws-open secondary" data-ws="${h(ws.id)}">Open</button>
      </article>`;
    }

    function showWorkspaces() {
      const wsList = (info.workspaces || []);
      const cards = wsList.map(wsCard).join('');
      page(`${backBar}<div class="page-header"><span class="eyebrow">WORKSPACES</span><h1>Your Workspaces</h1><p>A workspace tracks a project over time. Every version is remembered so you can compare any two, see the change impact graph, and use all platform features across versions.</p></div>
        <div class="action-row"><button type="button" class="primary" id="ws-create-btn">Create Workspace ${ico('arrow')}</button></div>
        ${cards ? `<section class="ws-list" aria-label="Workspaces">${cards}</section>` : '<div class="notice neutral"><strong>No workspaces yet.</strong><p>Create one to start tracking a project over time.</p></div>'}
        <div class="notice" id="picker-error" hidden></div>`);
      bindBack();
      const createBtn = $('ws-create-btn');
      if (createBtn) createBtn.addEventListener('click', () => showCreateWorkspace());
      document.querySelectorAll('[data-ws]').forEach(btn => btn.addEventListener('click', () => openWorkspace(btn.dataset.ws)));
    }

    function showCreateWorkspace() {
      page(`${backBar}<div class="page-header"><span class="eyebrow">NEW WORKSPACE</span><h1>Create a Workspace</h1><p>Name your workspace and choose a project folder. RepoTrace will track every version (commit) automatically.</p></div>
        <form id="ws-form" class="stack">
          <label class="field-label" for="ws-name">Workspace name</label>
          <div class="search-form open-form"><span class="search-icon" aria-hidden="true">${ico('workspace')}</span><input id="ws-name" aria-label="Workspace name" placeholder="e.g. My API project" autocomplete="off" required maxlength="100"></div>
          <label class="field-label" for="ws-desc">Description (optional)</label>
          <input id="ws-desc" class="ws-input" aria-label="Description" placeholder="What is this workspace for?" autocomplete="off" maxlength="500">
          <label class="field-label" for="ws-repo">Project folder</label>
          <div class="search-form open-form"><span class="search-icon" aria-hidden="true">${ico('folder')}</span><input id="ws-repo" aria-label="Project folder" placeholder="/path/to/your/project" value="${h(info.initial_repo || '')}" autocomplete="off" required>${info.can_browse ? '<button type="button" class="secondary" id="ws-browse">Browse…</button>' : ''}<button class="primary" type="submit">Create Workspace ${ico('arrow')}</button></div>
        </form>
        <div class="notice" id="picker-error" hidden></div>`);
      bindBack();
      const browse = $('ws-browse');
      if (browse) browse.addEventListener('click', async () => {
        try { const picked = await api('/api/browse', {}); if (picked.path) $('ws-repo').value = picked.path; }
        catch (e) { fail(e.message); }
      });
      $('ws-form').addEventListener('submit', async ev => {
        ev.preventDefault();
        const name = $('ws-name').value.trim();
        const repo = $('ws-repo').value.trim();
        const desc = $('ws-desc').value.trim();
        if (!name) { fail('Give the workspace a name.'); return; }
        if (!repo) { fail('Choose a project folder.'); return; }
        try {
          const ws = await api('/api/workspace/create', { name, repo, description: desc });
          // Refresh the info so the list is up-to-date
          try { info = await api('/api/state'); } catch (e) { /* still continue */ }
          openWorkspace(ws.id);
        } catch (e) { fail(e.message); }
      });
      $('ws-name').focus();
    }

    async function openWorkspace(wsId) {
      try {
        // Refresh versions
        const ws = await api('/api/workspace/refresh', { id: wsId });
        leave();
        stepWorkspace(boot, ws);
      } catch (e) { fail(e.message); }
    }
    function show(panel) {
      clearTimeout(githubTimer);
      openHome(false);
      if (panel === 'local' || panel === 'workspace-open' || panel === 'explore') { pathPanel(panel); return; }
      if (panel === 'remote' || panel === 'ssh') { clonePanel(panel === 'ssh' ? 'ssh' : 'https'); return; }
      if (panel === 'github') { showGitHub(); return; }
      if (panel === 'gitlab' || panel === 'azure') { showUnavailable(panel); return; }
      if (panel === 'workspace') { showWorkspaces(); return; }
      openHome(true);
      const pills = [['workspace','Workspace',ico('workspace')],['explore','Map only',ico('map')],['remote','Clone',ico('clone')],['ssh','SSH',ico('term')],['github','GitHub',mark('github','gh')],['gitlab','GitLab',mark('gitlab','gl')],['azure','Azure DevOps',mark('azure','az')]];
      const recentCards = info.recent.map((item, index) => {
        const when = ago(item.opened);
        return `<article class="recent-card${index > 2 ? ' is-extra' : ''}" ${index > 2 ? 'hidden' : ''}><span class="recent-mark" aria-hidden="true">${ico('folder')}</span><div class="recent-id"><strong>${h(item.name || 'Folder')}</strong><small>${h(item.path)}</small></div>${when ? `<time>${h(when)}</time>` : ''}<button type="button" class="recent-open" data-path="${h(item.path)}">Open</button></article>`;
      }).join('');
      const recent = info.recent.length ? `<section class="recent-block" aria-labelledby="recents-title"><div class="recent-head"><h2 id="recents-title">Recent Projects</h2>${info.recent.length > 3 ? '<button type="button" class="see-all" id="see-all">See all</button>' : ''}</div><div class="recent-list">${recentCards}</div></section>` : '';
      const wsItems = (info.workspaces || []).slice(0, 4);
      const wsSection = wsItems.length ? `<section class="ws-block" aria-labelledby="ws-title"><div class="recent-head"><h2 id="ws-title">Workspaces</h2><button type="button" class="see-all" data-panel="workspace">See all</button></div><div class="ws-mini-list">${wsItems.map(ws => `<article class="ws-mini-card"><span class="ws-mini-mark" aria-hidden="true">${ico('workspace')}</span><div><strong>${h(ws.name)}</strong><small>${h(ws.repo_name || '')} · ${ws.version_count || 0} versions</small></div><button type="button" class="ws-mini-open" data-ws-mini="${h(ws.id)}">Open</button></article>`).join('')}</div></section>` : '';
      const status = githubSignedIn(gh) ? gh.login : (gh.state === 'pending' ? 'Waiting' : 'Signed out');
      page(`<div class="open-stage"><header class="open-hero"><span class="spark" aria-hidden="true"></span><div><h1>Open a Project</h1><p>Choose a folder, clone a repo, or browse your projects</p></div></header>
        <form id="open-form" class="drop-card"><div class="drop-art" aria-hidden="true"><span class="orbit"></span><span class="folder-glyph">${ico('folder')}</span><span class="plus">+</span></div><div class="drop-main"><p class="drop-title">Drag and drop a folder here</p><input id="repo-path" aria-label="Path to the project folder" placeholder="or paste a path" value="${h(info.initial_repo || '')}" autocomplete="off" required><div class="drop-actions">${info.can_browse ? '<button type="button" class="ghost" id="browse">Browse Files</button>' : ''}<button class="primary" type="submit">Open Folder ${ico('arrow')}</button></div></div></form>
        <nav class="open-pills" aria-label="Ways to open"><button type="button" class="pill is-on" aria-current="page">${ico('folder')}<span>Recent</span></button>${pills.map(([id, title, icon]) => `<button type="button" class="pill" data-panel="${id}">${icon}<span>${h(title)}</span></button>`).join('')}<button type="button" class="pill pill-state" data-panel="github">${ico('user')}<span>${h(status)}</span></button></nav>
        ${recent}${wsSection}<div class="notice" id="picker-error" hidden></div><aside class="open-tip" id="open-tip" hidden><span>Tip: You can also drag a folder here</span><button type="button" id="tip-close" aria-label="Dismiss tip">×</button></aside></div>`);
      const go = () => { const path = $('repo-path').value.trim(); if (!path) { fail('Type or paste the project folder, or use Browse Files.'); return; } openCompare(path); };
      $('open-form').addEventListener('submit', ev => { ev.preventDefault(); go(); });
      const zone = $('open-form');
      zone.addEventListener('dragover', ev => { ev.preventDefault(); zone.classList.add('is-over'); });
      zone.addEventListener('dragleave', () => zone.classList.remove('is-over'));
      zone.addEventListener('drop', ev => {
        ev.preventDefault(); zone.classList.remove('is-over');
        const file = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
        const dropped = file && file.path;
        if (dropped) { $('repo-path').value = dropped; go(); return; }
        fail('This browser did not share the folder path. Use Browse Files, or paste the path.');
      });
      const browse = $('browse');
      if (browse) browse.addEventListener('click', async () => {
        try { const picked = await api('/api/browse', {}); if (picked.path) { $('repo-path').value = picked.path; go(); } }
        catch (e) { fail(e.message); }
      });
      const more = $('see-all');
      if (more) more.addEventListener('click', () => {
        const open = more.getAttribute('aria-expanded') === 'true';
        more.setAttribute('aria-expanded', open ? 'false' : 'true');
        more.textContent = open ? 'See all' : 'Show less';
        document.querySelectorAll('.recent-card.is-extra').forEach(card => { card.hidden = open; });
      });
      const tip = $('open-tip');
      if (tip && localStorage.getItem('repotrace-open-tip') !== 'off') tip.hidden = false;
      const closeTip = $('tip-close');
      if (closeTip) closeTip.addEventListener('click', () => { tip.hidden = true; try { localStorage.setItem('repotrace-open-tip', 'off'); } catch (e) { /* the tip can stay dismissed for this view */ } });
      document.querySelectorAll('[data-panel]').forEach(button => button.addEventListener('click', () => show(button.dataset.panel)));
      document.querySelectorAll('[data-path]').forEach(button => button.addEventListener('click', () => openCompare(button.dataset.path)));
      document.querySelectorAll('[data-ws-mini]').forEach(btn => btn.addEventListener('click', () => openWorkspace(btn.dataset.wsMini)));
    }

    try { info = await api('/api/state'); } catch (e) { /* the menu still opens without the recent list */ }
    if (epoch !== githubEpoch) return;
    try { gh = await api('/api/github/status'); githubSeen = gh; }
    catch (e) { gh = {configured: false, signed_in: false, state: 'error', error: e.message}; }
    if (epoch !== githubEpoch) return;
    show('menu');
  }

  function stepWorkspace(boot, ws) {
    openHome(false);
    const versions = ws.versions || [];
    const vLabel = v => `${v.short || v.commit?.slice(0, 8)} · ${v.subject || '(no message)'}${v.author ? ' · ' + v.author : ''}`;
    const versionRows = versions.map((v, i) => `<article class="ws-version">
      <span class="ws-ver-num">${String(i + 1).padStart(2, '0')}</span>
      <div class="ws-ver-info">
        <strong>${h(v.short || v.commit?.slice(0, 8))}</strong>
        <small>${h(v.subject || '(no message)')}</small>
        <small class="ws-sub">${v.author ? h(v.author) : ''} ${v.branch ? '· ' + h(v.branch) : ''}</small>
      </div>
      <time>${ago(v.added)}</time>
    </article>`).join('');
    const hasEnough = versions.length >= 2;
    const baseOpts = versions.map((v, i) => `<option value="${i}"${i === versions.length - 2 ? ' selected' : ''}>${h(vLabel(v))}</option>`).join('');
    const headOpts = versions.map((v, i) => `<option value="${i}"${i === versions.length - 1 ? ' selected' : ''}>${h(vLabel(v))}</option>`).join('');

    page(`<div class="page-header"><span class="eyebrow">WORKSPACE</span><h1>${ico('workspace')} ${h(ws.name)}</h1><p>${ws.description ? h(ws.description) + ' · ' : ''}${h(ws.repo_name || ws.repo)} · ${versions.length} version${versions.length !== 1 ? 's' : ''} tracked</p></div>
      ${hasEnough ? `<section class="card" aria-labelledby="ws-cmp-title"><div class="card-head"><h2 id="ws-cmp-title">Compare Versions</h2></div>
        <p class="help-text">Pick any two versions from this workspace and see the full change impact graph, recommendations, and more.</p>
        <form id="ws-compare-form" class="go-form">
          <div class="pair" id="ws-pair">
            <label class="slot slot-base"><span class="slot-label"><span>Older version</span><em class="role">Start</em></span><select id="ws-base">${baseOpts}</select></label>
            <button type="button" class="swap" id="ws-swap" aria-label="Swap versions">${ico('swap')}</button>
            <label class="slot slot-head"><span class="slot-label"><span>Newer version</span><em class="role">End</em></span><select id="ws-head">${headOpts}</select></label>
          </div>
          <div class="action-bar"><button class="primary" type="submit">Analyse ${ico('arrow')}</button></div>
        </form>
      </section>` : '<div class="notice neutral"><strong>Need at least 2 versions to compare.</strong><p>Push another commit or add a version to start comparing.</p></div>'}
      <section class="card" aria-labelledby="ws-versions-title"><div class="card-head"><h2 id="ws-versions-title">Version History</h2><button type="button" class="small-button" id="ws-refresh">${ico('download')} Refresh</button></div>
        ${versionRows || '<p class="help-text">No versions recorded yet. Refresh to capture the latest commits.</p>'}
      </section>
      <section class="card"><div class="card-head"><h2>Explore Working Folder</h2></div>
        <p class="help-text">Map the current state of the project without comparing versions.</p>
        <div class="action-row"><button class="secondary" id="ws-explore">Explore the map ${ico('arrow')}</button></div>
      </section>
      <div class="notice" id="picker-error" hidden></div>
      <div class="action-row"><button class="secondary" id="ws-back">← All Workspaces</button><button class="text-button" id="ws-rename">Rename</button><button class="text-button ws-delete" id="ws-delete">Delete workspace</button></div>`);

    // Bindings
    const goBack = () => { stepOne(boot); };
    $('ws-back').addEventListener('click', goBack);

    if (hasEnough) {
      $('ws-swap')?.addEventListener('click', () => {
        const b = $('ws-base'), hd = $('ws-head');
        const tmp = b.value; b.value = hd.value; hd.value = tmp;
      });
      $('ws-compare-form').addEventListener('submit', async ev => {
        ev.preventDefault();
        const baseIdx = parseInt($('ws-base').value, 10);
        const headIdx = parseInt($('ws-head').value, 10);
        if (baseIdx === headIdx) { fail('Choose two different versions.'); return; }
        try {
          const result = await api('/api/workspace/compare', { id: ws.id, base_index: baseIdx, head_index: headIdx });
          waiting(result.job, { compare: true, reverse: false, back: () => stepWorkspace(boot, ws) });
        } catch (e) { fail(e.message); }
      });
    }

    $('ws-refresh')?.addEventListener('click', async () => {
      try {
        const refreshed = await api('/api/workspace/refresh', { id: ws.id });
        stepWorkspace(boot, refreshed);
      } catch (e) { fail(e.message); }
    });

    $('ws-explore')?.addEventListener('click', async () => {
      try {
        const started = await api('/api/lab', { repo: ws.repo });
        waiting(started.job, { compare: false, reverse: false, back: () => stepWorkspace(boot, ws) });
      } catch (e) { fail(e.message); }
    });

    $('ws-rename')?.addEventListener('click', async () => {
      const name = prompt('New workspace name:', ws.name);
      if (!name || !name.trim()) return;
      try {
        const updated = await api('/api/workspace/rename', { id: ws.id, name: name.trim() });
        stepWorkspace(boot, updated);
      } catch (e) { fail(e.message); }
    });

    $('ws-delete')?.addEventListener('click', async () => {
      if (!confirm(`Delete workspace "${ws.name}"? This only removes the workspace metadata, not the project itself.`)) return;
      try {
        await api('/api/workspace/delete', { id: ws.id });
        try { info = await api('/api/state'); } catch (e) { /* continue */ }
        stepOne(boot);
      } catch (e) { fail(e.message); }
    });
  }

  function stepTwo(boot, info) {
    openHome(false);
    const commits = info.commits || [];
    const label = c => `${c.short} · ${c.subject || '(no message)'} · ${c.date}`;
    const options = selected => commits.map((c, i) => `<option value="${h(c.commit)}" ${i === selected ? 'selected' : ''}>${h(label(c))}</option>`).join('');
    const can = commits.length >= 2;
    page(`<div class="page-header"><span class="eyebrow">${h(info.name)} · ${h(info.current_branch)}</span><h1>Choose what to compare</h1><p>${commits.length} commit${commits.length === 1 ? '' : 's'} found. ${info.dirty ? 'You have unsaved changes: the map shows your working folder; the comparison uses saved commits only. ' : ''}${h((info.source_roots || {}).reason || '')}</p></div>
      <form id="go-form" class="go-form">
      ${can ? `<section class="card" aria-labelledby="cmp-title"><div class="card-head"><h2 id="cmp-title">Check a change</h2><label class="check"><input type="checkbox" id="skip"><span>Only explore the map</span></label></div>
        <div class="pair" id="pair">
          <label class="slot slot-base"><span class="slot-label"><span>Older version</span><em class="role">Start</em></span><select id="base">${options(1)}</select></label>
          <button type="button" class="swap" id="swap" aria-label="Reverse the direction" title="Reverse the direction">${ico('swap')}</button>
          <label class="slot slot-head"><span class="slot-label"><span>Newer version</span><em class="role">End</em></span><select id="head">${options(0)}</select></label>
        </div>
        <fieldset class="reverse-choice"><legend>Reverse this change?</legend><div class="seg"><label><input type="radio" name="reverse" value="no" checked><span>No</span></label><label><input type="radio" name="reverse" value="yes"><span>Yes</span></label></div><p class="help-text" id="direction" aria-live="polite"></p></fieldset></section>`
        : '<div class="notice neutral"><strong>Only one commit</strong><p>There is nothing to compare yet. You can still explore the project.</p></div>'}
      <div class="notice neutral"><strong>Explore the code</strong><p>Always included: the map of every file, class and function in your working folder, with search.</p></div>
      <div class="notice" id="picker-error" hidden></div>
      <div class="action-bar"><button class="primary" type="submit">${can ? 'Analyse' : 'Explore'} ${ico('arrow')}</button><button class="secondary" type="button" id="back-to-open">Choose another project</button></div></form>`);
    const form = $('go-form'), pair = $('pair');
    const asked = () => document.querySelector('input[name="reverse"]:checked')?.value === 'yes';
    const describe = () => {
      if (!can) return;
      const reverse = asked();
      pair.classList.toggle('reversed', reverse);
      pair.querySelector('.slot-base .role').textContent = reverse ? 'End' : 'Start';
      pair.querySelector('.slot-head .role').textContent = reverse ? 'Start' : 'End';
      $('direction').textContent = reverse
        ? 'Yes. The same two versions, run backwards: from the newer one to the older one. Git is not modified.'
        : 'No. From the older version to the newer one, the way the change happened.';
    };
    // Moving the two versions is animated from where each one was, so the swap reads as a swap and not a jump.
    const flip = mutate => {
      if (!can) return;
      const parts = [...pair.children], from = parts.map(el => el.getBoundingClientRect());
      mutate();
      if (calm() || !pair.animate) return;
      parts.forEach((el, i) => { const to = el.getBoundingClientRect(), dx = from[i].left - to.left, dy = from[i].top - to.top; if (dx || dy) el.animate([{transform: `translate(${dx}px, ${dy}px)`}, {transform: 'none'}], {duration: 200, easing: 'cubic-bezier(.2,.7,.2,1)'}); });
    };
    const explore = () => { const off = !!$('skip')?.checked; pair.classList.toggle('off', off); pair.querySelectorAll('select,button').forEach(el => { el.disabled = off; }); document.querySelectorAll('input[name="reverse"]').forEach(el => { el.disabled = off; }); };
    if (can) {
      describe();
      form.addEventListener('change', ev => { if (ev.target.name === 'reverse') flip(describe); else if (ev.target.id === 'skip') explore(); });
      $('swap').addEventListener('click', () => { document.querySelector(`input[name="reverse"][value="${asked() ? 'no' : 'yes'}"]`).checked = true; flip(describe); });
    }
    $('back-to-open').addEventListener('click', () => stepOne(boot));
    form.addEventListener('submit', async ev => {
      ev.preventDefault();
      const compare = can && !$('skip').checked;
      const reverse = compare && asked();
      const body = {repo: info.repo, ...(compare ? {base: $('base').value, head: $('head').value, reverse} : {})};
      if (compare && body.base === body.head) { fail('Choose two different versions, or tick "Only explore the map".'); return; }
      try { const {job} = await api('/api/lab', body); waiting(job, {compare, reverse, back: () => stepTwo(boot, info)}); } catch (e) { fail(e.message); }
    });
  }

  // The steps are drawn once. Each poll only moves the highlight, the clock and the notes, so the page never jumps and the motion is real.
  function waiting(job, {compare, reverse, back}) {
    openHome(false);
    const order = compare ? FLOW.compare : FLOW.explore;
    const name = s => (reverse && REVERSED[s]) || STEPS[s] || s;
    busy(true);
    page(`<section class="run"><div class="run-head"><div><span class="eyebrow">IN PROGRESS</span><h1>${reverse ? 'Reading the project, backwards' : 'Reading the project'}</h1><p>${reverse ? 'The same two versions in the opposite direction. ' : ''}Everything stays on this computer. The highlighted step is the one running now.</p></div><div class="elapsed" role="timer" aria-label="Time so far"><b data-elapsed>0:00</b><span>elapsed</span></div></div>
      <div class="progress-track" aria-hidden="true"><span class="progress-fill" id="progress-fill"></span></div>
      <ol class="steps" id="progress-list" aria-live="polite">${order.map(s => `<li data-stage="${h(s)}"><span class="mark" aria-hidden="true"></span><span class="copy"><b>${h(name(s))}</b><small></small></span><span class="time"></span></li>`).join('')}</ol>
      <div class="action-row"><button type="button" class="secondary" id="cancel-run">Cancel</button><span class="help-text">Cancel stops at the end of the step that is running. Nothing is changed.</span></div></section>`);
    const t0 = performance.now(); let skew = 0, stopped = false, widest = 0, marks = {};
    const now = () => (performance.now() - t0) / 1000 + skew;
    const paint = (seen, stage, detail) => {
      const at = Math.max(0, order.indexOf(stage));
      widest = Math.max(widest, (at + 0.45) / order.length);                         // the bar only ever moves forward
      const fill = $('progress-fill'); if (fill) fill.style.transform = `scaleX(${widest})`;
      order.forEach((id, i) => {
        const item = document.querySelector(`#progress-list li[data-stage="${id}"]`); if (!item) return;
        const current = id === stage, finished = i < at;          // anything before the running step is finished, even a step the engine had nothing to do for
        item.classList.toggle('now', current);
        item.classList.toggle('done', finished);
        item.querySelector('small').textContent = current ? note(detail) : '';      // the line is always there, so nothing below it moves
        const next = marks[order[i + 1]];
        item.querySelector('.time').textContent = finished && marks[id] != null && next != null ? took(Math.max(0, next - marks[id])) : '';
      });
    };
    const tickClock = () => {
      const clockEl = document.querySelector('[data-elapsed]'); if (clockEl) clockEl.textContent = clock(now());
      const live = document.querySelector('#progress-list li.now .time'), item = live && live.parentElement;
      if (live && item && marks[item.dataset.stage] != null) live.textContent = took(Math.max(0, now() - marks[item.dataset.stage]));
    };
    const timer = setInterval(() => { if (stopped) clearInterval(timer); else tickClock(); }, 250);
    const leave = () => { stopped = true; clearInterval(timer); busy(false); };
    $('cancel-run').addEventListener('click', async () => {
      $('cancel-run').disabled = true; leave();
      try { await api('/api/cancel', {job}); } catch (e) { /* the job simply finishes unseen */ }
      back();
    });
    paint(['check'], 'check', '');
    const tick = async () => {
      if (stopped) return;
      try {
        const state = await api('/api/job?id=' + encodeURIComponent(job));
        if (stopped) return;
        if (state.state === 'done') { if (root.RTSettings) root.RTSettings.notify('Analysis finished. The comparison is on screen.'); leave(); root.PROTO = state.view.data; root.RTLab(root.PROTO); return; }
        if (state.state === 'cancelled') { leave(); back(); return; }
        if (state.state === 'error') { const message = state.error && state.error.message || 'The analysis failed.'; if (root.RTSettings) root.RTSettings.notify(message, {error: true}); leave(); failPage(message, 'Choose a project again', () => stepOne(root.RTLab)); return; }
        marks = state.marks || {}; skew = Math.max(0, state.seconds - (performance.now() - t0) / 1000);
        paint(state.seen || [], state.stage, state.detail);
        tickClock();
        setTimeout(tick, 500);
      } catch (e) { leave(); failPage(e.message, 'Try again', () => stepOne(root.RTLab)); }
    };
    setTimeout(tick, 300);
  }

  // From a finished review: run the same request again, with the direction turned around. The old review stays on screen until the new one is ready or the run is cancelled.
  function run(body) {
    const previous = root.PROTO;
    (async () => {
      try {
        const {job} = await api('/api/lab', body);
        waiting(job, {compare: !!(body.base && body.head), reverse: !!body.reverse, back: () => (previous ? root.RTLab(previous) : stepOne(root.RTLab))});
      } catch (e) { fail(e.message); }
    })();
  }
  root.RTPicker = {start, run};
})(typeof globalThis !== 'undefined' ? globalThis : this);
