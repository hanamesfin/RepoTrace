/* Settings that change this page and stay on this computer.
   A control is here only when it changes the interface or a choice the page already makes.
   Analysis limits, Git hosts, and resource caps that this app does not apply are described, not switched on. */
(function () {
  'use strict';
  var KEY = 'repotrace-settings';
  var DEFAULTS = {
    colorMode: 'theme',
    lightTheme: 'github-light',
    darkTheme: 'github-dark',
    accent: '',
    density: 'comfortable',
    motion: 'system',
    railSide: 'left',
    railMode: 'labels',
    uiFont: 'system',
    codeFont: 'system',
    uiSize: 14,
    codeSize: 13,
    leading: 1.55,
    tracking: 0,
    weight: 500,
    ligatures: false,
    contrast: 'default',
    focus: 'default',
    cues: 'color',
    scale: 100,
    showPossible: true,
    landing: 'review',
    quietStart: '',
    quietEnd: '',
    notifyAnalysis: false,
    soundAnalysis: false,
    section: 'appearance'
  };
  var UI_FONTS = {
    system: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    inter: 'Inter, "Inter var", sans-serif',
    geist: 'Geist, Inter, sans-serif',
    plex: '"IBM Plex Sans", Inter, sans-serif'
  };
  var CODE_FONTS = {
    system: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    jetbrains: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
    fira: '"Fira Code", ui-monospace, SFMono-Regular, Menlo, monospace',
    plex: '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace'
  };
  var ACCENTS = [
    {id: '', name: 'Theme'},
    {id: '#58a6ff', name: 'Blue'},
    {id: '#2a9d8f', name: 'Teal'},
    {id: '#8b5cf6', name: 'Violet'},
    {id: '#d4a017', name: 'Amber'},
    {id: '#e85d75', name: 'Rose'}
  ];

  function load() {
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (error) { saved = {}; }
    var next = {};
    Object.keys(DEFAULTS).forEach(function (key) {
      next[key] = saved[key] == null ? DEFAULTS[key] : saved[key];
    });
    return next;
  }

  function coerce(key, value) {
    var sample = DEFAULTS[key];
    if (typeof sample === 'number') {
      var number = Number(value);
      return number === number ? number : sample;
    }
    if (typeof sample === 'boolean') return value === true || value === 'true';
    return value;
  }

  function save(settings) {
    var next = {};
    Object.keys(DEFAULTS).forEach(function (key) {
      next[key] = settings[key] == null ? DEFAULTS[key] : coerce(key, settings[key]);
    });
    try { localStorage.setItem(KEY, JSON.stringify(next)); } catch (error) {}
    return next;
  }

  function channel(hex, index) {
    var value = parseInt(hex.slice(index + 1, index + 3), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
  }

  function ink(hex) {
    if (!hex || hex.length < 7) return '#0b0d10';
    var level = 0.2126 * channel(hex, 0) + 0.7152 * channel(hex, 2) + 0.0722 * channel(hex, 4);
    return (1.05 / (level + 0.05)) >= ((level + 0.05) / 0.05) ? '#ffffff' : '#0b0d10';
  }

  function overlay() {
    var settings = load();
    var root = document.documentElement;
    root.setAttribute('data-settings', 'on');
    root.setAttribute('data-density', settings.density);
    root.setAttribute('data-motion', settings.motion);
    root.setAttribute('data-rail-side', settings.railSide);
    root.setAttribute('data-rail-mode', settings.railMode);
    root.setAttribute('data-contrast', settings.contrast);
    root.setAttribute('data-focus', settings.focus);
    root.setAttribute('data-cues', settings.cues);
    root.setAttribute('data-ligatures', settings.ligatures ? 'on' : 'off');
    root.style.setProperty('--sans', UI_FONTS[settings.uiFont] || UI_FONTS.system);
    root.style.setProperty('--mono', CODE_FONTS[settings.codeFont] || CODE_FONTS.system);
    root.style.setProperty('--ui-size', settings.uiSize + 'px');
    root.style.setProperty('--code-size', settings.codeSize + 'px');
    root.style.setProperty('--ui-leading', String(settings.leading));
    root.style.setProperty('--ui-tracking', settings.tracking + 'em');
    root.style.setProperty('--ui-weight', String(settings.weight));
    root.style.setProperty('--ui-ligatures', settings.ligatures ? 'common-ligatures' : 'none');
    var page = (Number(settings.scale) || 100) / 100;
    var zoom = page;
    /* The map lives in a frame inside this page, so the frame inherits this zoom. It must not zoom again. */
    root.style.zoom = window.parent !== window || Math.abs(zoom - 1) < 0.01 ? '' : String(zoom);
    if (settings.accent) {
      root.style.setProperty('--accent', settings.accent);
      root.style.setProperty('--mint', settings.accent);
      root.style.setProperty('--blue', settings.accent);
      root.style.setProperty('--accent-ink', ink(settings.accent));
    }
    tellFrames();
  }

  function tellFrames() {
    var frame = document.getElementById('xp');
    if (!frame || !frame.contentWindow) return;
    var target = location.protocol === 'file:' ? '*' : location.origin;
    try { frame.contentWindow.postMessage({rt: 'settings'}, target); } catch (error) {}
  }

  function wantedTheme(settings) {
    if (settings.colorMode === 'light') return settings.lightTheme || 'github-light';
    if (settings.colorMode === 'dark') return settings.darkTheme || 'github-dark';
    if (settings.colorMode === 'system') {
      var light = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
      return light ? (settings.lightTheme || 'github-light') : (settings.darkTheme || 'github-dark');
    }
    return '';
  }

  function syncTheme() {
    if (!window.RTTheme) { overlay(); return; }
    var want = wantedTheme(load());
    if (want && RTTheme.current() !== want) RTTheme.preview(want);
    overlay();
  }

  function noteTheme(theme) {
    if (!theme) return;
    var settings = load();
    if (theme.kind === 'light') settings.lightTheme = theme.id;
    else settings.darkTheme = theme.id;
    settings.colorMode = 'theme';
    save(settings);
    overlay();
  }

  function quietNow() {
    var settings = load();
    if (!settings.quietStart || !settings.quietEnd) return false;
    var parts = function (value) {
      var bits = String(value).split(':');
      return (Number(bits[0]) || 0) * 60 + (Number(bits[1]) || 0);
    };
    var now = new Date();
    var minutes = now.getHours() * 60 + now.getMinutes();
    var start = parts(settings.quietStart);
    var end = parts(settings.quietEnd);
    if (start === end) return false;
    if (start < end) return minutes >= start && minutes < end;
    return minutes >= start || minutes < end;
  }

  function beep() {
    try {
      var context = new (window.AudioContext || window.webkitAudioContext)();
      var tone = context.createOscillator();
      var gain = context.createGain();
      tone.frequency.value = 660;
      gain.gain.value = 0.03;
      tone.connect(gain);
      gain.connect(context.destination);
      tone.start();
      gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.18);
      tone.stop(context.currentTime + 0.2);
    } catch (error) {}
  }

  function notify(message, options) {
    var settings = load();
    var opts = options || {};
    if (quietNow() && !opts.error) return;
    var play = opts.testSound || (settings.soundAnalysis && !opts.test);
    var popup = opts.testNotice || (settings.notifyAnalysis && !opts.testSound);
    if (play) beep();
    if (!popup || !('Notification' in window)) return;
    var show = function () { try { new Notification('RepoTrace', {body: message}); } catch (error) {} };
    if (Notification.permission === 'granted') show();
    else if (Notification.permission !== 'denied') Notification.requestPermission().then(function (permission) { if (permission === 'granted') show(); });
  }

  function storageBytes() {
    var total = 0;
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var key = localStorage.key(i) || '';
        total += key.length + (localStorage.getItem(key) || '').length;
      }
    } catch (error) {}
    return total;
  }

  function escape(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char];
    });
  }

  function option(value, label, current) {
    return '<option value="' + escape(value) + '"' + (String(current) === String(value) ? ' selected' : '') + '>' + escape(label) + '</option>';
  }

  function field(key, label, control, note) {
    return '<label class="setting" data-setting="' + escape(label + ' ' + (note || '')) + '"><span>' + escape(label) + '</span>' + control + (note ? '<small>' + escape(note) + '</small>' : '') + '</label>';
  }

  function select(key, current, pairs) {
    return '<select data-key="' + key + '">' + pairs.map(function (pair) { return option(pair[0], pair[1], current); }).join('') + '</select>';
  }

  function range(key, current, min, max, step) {
    return '<span class="range-line"><input data-key="' + key + '" type="range" min="' + min + '" max="' + max + '" step="' + step + '" value="' + escape(current) + '"><b data-for="' + key + '">' + escape(current) + '</b></span>';
  }

  function check(key, current) {
    return '<input data-key="' + key + '" type="checkbox"' + (current ? ' checked' : '') + '>';
  }

  function render(parts) {
    var settings = load();
    var theme = window.RTTheme ? RTTheme.get(RTTheme.current()) : {name: 'Theme'};
    var bytes = storageBytes();
    var nav = [
      ['Personalization', [['appearance', 'Appearance and themes'], ['type', 'Typography and editor'], ['access', 'Accessibility']]],
      ['Development', [['git', 'Git and repositories'], ['analysis', 'Analysis and intelligence'], ['workspace', 'Workspace and navigation']]],
      ['System', [['privacy', 'Privacy and security'], ['notices', 'Notifications'], ['storage', 'Storage and backup'], ['performance', 'Performance']]]
    ];
    var current = settings.section && document ? settings.section : 'appearance';
    var links = nav.map(function (group) {
      return '<p class="settings-group">' + escape(group[0]) + '</p>' + group[1].map(function (item) {
        var on = item[0] === current;
        return '<button type="button" class="settings-link' + (on ? ' is-current' : '') + '" data-section="' + item[0] + '" aria-current="' + (on ? 'page' : 'false') + '">' + escape(item[1]) + '</button>';
      }).join('');
    }).join('') + '<button type="button" class="settings-reset" id="settings-reset-nav">Reset all settings</button>';
    var accents = ACCENTS.map(function (item) {
      var on = (settings.accent || '') === item.id;
      var chip = item.id ? ' style="background:' + item.id + '"' : '';
      return '<button type="button" class="accent-swatch' + (on ? ' is-on' : '') + (item.id ? '' : ' is-neutral') + '" data-accent="' + escape(item.id) + '" aria-pressed="' + (on ? 'true' : 'false') + '"><i' + chip + '></i><span>' + escape(item.name) + '</span></button>';
    }).join('');
    var modes = [['theme', 'Use the theme'], ['dark', 'Dark'], ['light', 'Light'], ['system', 'Match the system']];
    var modeButtons = modes.map(function (item) {
      var on = settings.colorMode === item[0];
      return '<button type="button" class="mode-choice' + (on ? ' is-on' : '') + '" data-mode="' + item[0] + '" aria-pressed="' + (on ? 'true' : 'false') + '">' + escape(item[1]) + '</button>';
    }).join('');
    var shown = function (id) { return id === current ? '' : ' hidden'; };
    return '<div class="settings-shell"><nav class="settings-nav" aria-label="Settings sections"><input id="settings-q" type="search" placeholder="Search settings" aria-label="Search settings">' + links + '</nav><div class="settings-main"><header class="settings-head"><span class="eyebrow">SETTINGS</span><p id="settings-status">Saved on this computer. Nothing is uploaded.</p></header>'
      + '<section class="settings-block" id="set-appearance"' + shown('appearance') + '><h2>Appearance</h2><div class="preview-window" id="settings-preview"><div class="preview-top"><span></span><span></span><span></span><b>' + escape(theme.name) + '</b></div><p>Find what a change left behind.</p><div class="preview-chips"><span class="chip accent">Accent</span><span class="chip ok">Success</span><span class="chip warn">Warning</span><span class="chip bad">Error</span></div><pre class="settings-code">def changed(x):\n    return x</pre></div>'
      + '<div class="setting" data-setting="color mode dark light system"><span>Color mode</span><div class="mode-row">' + modeButtons + '</div><small>Dark and Light use the last theme you chose of that kind. Match the system follows this computer’s appearance. Choosing a theme below returns to that theme.</small></div>'
      + '<div class="setting" data-setting="accent color"><span>Accent</span><div class="accent-row">' + accents + '</div><small>Theme uses the accent from the selected theme. Another accent replaces it on buttons and focus.</small></div>'
      + field('density', 'Density', select('density', settings.density, [['compact', 'Compact'], ['comfortable', 'Comfortable'], ['spacious', 'Spacious']]), 'Changes the padding of the workspace.')
      + field('motion', 'Motion', select('motion', settings.motion, [['system', 'Follow the system'], ['full', 'Motion on'], ['reduced', 'Reduced motion']]), 'Reduced motion turns off transitions on this page.')
      + field('railSide', 'Sidebar side', select('railSide', settings.railSide, [['left', 'Left'], ['right', 'Right']]), 'Moves the project navigation to the other side.')
      + field('railMode', 'Sidebar labels', select('railMode', settings.railMode, [['labels', 'Icons and labels'], ['icons', 'Icons only']]), 'Icons only keeps the same navigation in a narrow rail.')
      + '<h3 id="theme-caption">' + escape(theme.name) + ' · saved</h3><div class="theme-grid" role="list">' + (parts.themeCards || '') + '</div></section>'
      + '<section class="settings-block" id="set-type"' + shown('type') + '><h2>Typography</h2><p class="help-text">A named font is used when it is installed on this computer. Otherwise the system font is used. RepoTrace does not download fonts.</p>'
      + field('uiFont', 'Interface font', select('uiFont', settings.uiFont, [['system', 'System'], ['inter', 'Inter'], ['geist', 'Geist'], ['plex', 'IBM Plex Sans']]), 'Applies to the interface, not to code blocks.')
      + field('codeFont', 'Code font', select('codeFont', settings.codeFont, [['system', 'System mono'], ['jetbrains', 'JetBrains Mono'], ['fira', 'Fira Code'], ['plex', 'IBM Plex Mono']]), 'Applies to source, diffs, and commands.')
      + field('uiSize', 'Interface size', range('uiSize', settings.uiSize, 8, 20, 1), '8 to 20 pixels.')
      + field('codeSize', 'Code size', range('codeSize', settings.codeSize, 11, 18, 1), '11 to 18 pixels.')
      + field('leading', 'Line height', range('leading', settings.leading, 1.3, 1.8, 0.05), 'Applies to the interface text.')
      + field('tracking', 'Letter spacing', range('tracking', settings.tracking, -0.02, 0.06, 0.01), 'A small change, in ems.')
      + field('weight', 'Interface weight', select('weight', settings.weight, [[450, 'Regular'], [500, 'Medium'], [600, 'Semibold']]), 'Applies to the interface text.')
      + field('ligatures', 'Code ligatures', check('ligatures', settings.ligatures), 'On asks the code font for ligatures. A font without them draws the characters separately.')
      + '</section>'
      + '<section class="settings-block" id="set-access"' + shown('access') + '><h2>Accessibility</h2>'
      + field('contrast', 'Contrast', select('contrast', settings.contrast, [['default', 'Theme contrast'], ['high', 'Higher contrast']]), 'Higher contrast uses the text color for secondary text and a stronger border.')
      + field('focus', 'Focus ring', select('focus', settings.focus, [['default', 'Default'], ['strong', 'Strong']]), 'The keyboard focus ring is always drawn. Strong makes it thicker.')
      + field('cues', 'Status marks', select('cues', settings.cues, [['color', 'Color'], ['shape', 'Color and shape']]), 'Shape adds a dashed, solid, or dotted border so sure, maybe, and older-version marks are not color alone.')
      + field('scale', 'Page scale', select('scale', settings.scale, [[90, '90%'], [100, '100%'], [110, '110%'], [125, '125%']]), 'Scales this page. 100% is the normal size.')
      + '<p class="help-text">Keyboard navigation is always available. A system screen reader reads the buttons, labels, and status text. There is no separate screen-reader mode to switch on.</p></section>'
      + '<section class="settings-block" id="set-git"' + shown('git') + '><h2>Git and repositories</h2>' + (parts.gitHtml || '') + '<p class="help-text">GitLab and Azure DevOps are not connected. There is no OAuth client for them, and this page will not pretend a sign-in succeeded. SSH keys are not managed here.</p></section>'
      + '<section class="settings-block" id="set-analysis"' + shown('analysis') + '><h2>Analysis</h2><p class="help-text">RepoTrace reads Python without running it. It does not score a change, and it does not offer a depth slider, a language pack, or a timeout control. Those limits belong to the analyzer, not to a switch on this page.</p>'
      + field('showPossible', 'Show possible links when a project opens', check('showPossible', settings.showPossible), 'Possible means one step is an assumption. This applies the next time a project is opened.')
      + '</section>'
      + '<section class="settings-block" id="set-workspace"' + shown('workspace') + '><h2>Workspace</h2>'
      + field('landing', 'Open a finished analysis on', select('landing', settings.landing, [['review', 'The review'], ['map', 'The map'], ['files', 'The file list'], ['home', 'Start']]), 'Used the next time a project is opened. If that view does not exist yet, RepoTrace opens Start.')
      + '<div class="setting" data-setting="keyboard shortcuts command k back"><span>Keyboard shortcuts</span><ul class="shortcut-list"><li><kbd>⌘</kbd> <kbd>K</kbd> Find code</li><li><kbd>Alt</kbd> <kbd>←</kbd> Back</li><li><kbd>Esc</kbd> Leave a text field, then go back</li></ul><small>These shortcuts are fixed. This page does not rebind them.</small></div></section>'
      + '<section class="settings-block" id="set-privacy"' + shown('privacy') + '><h2>Privacy</h2><p class="help-text">Analysis stays on this computer. The report is built in this browser. Nothing in Settings is uploaded. There is no data-sharing switch because there is no sharing channel, and there is no secret scanner on this page.</p><div class="setting" data-setting="clear recommendations dismissed saved"><span>Recommendation memory</span><button type="button" class="secondary" id="settings-clear-recs">Clear dismissed, saved, and completed</button><small>Removes those marks from this browser. It does not change the review.</small></div></section>'
      + '<section class="settings-block" id="set-notices"' + shown('notices') + '><h2>Notifications</h2>'
      + field('notifyAnalysis', 'Desktop notice when analysis finishes', check('notifyAnalysis', settings.notifyAnalysis), 'The browser asks permission the first time. A denied permission cannot be overridden here.')
      + field('soundAnalysis', 'Short sound when analysis finishes', check('soundAnalysis', settings.soundAnalysis), 'A quiet tone from this page. It does not use a sound file.')
      + field('quietStart', 'Quiet hours start', '<input data-key="quietStart" type="time" value="' + escape(settings.quietStart) + '">', 'Leave both times empty to keep notices available all day.')
      + field('quietEnd', 'Quiet hours end', '<input data-key="quietEnd" type="time" value="' + escape(settings.quietEnd) + '">', 'Overnight ranges are supported. Quiet hours suppress the finish notice and the sound, not an error.')
      + '<div class="action-row"><button type="button" class="secondary" id="settings-test-notice">Try a desktop notice</button><button type="button" class="secondary" id="settings-test-sound">Play the sound</button></div></section>'
      + '<section class="settings-block" id="set-storage"' + shown('storage') + '><h2>Storage</h2><p class="help-text" id="settings-bytes">This browser is storing about ' + bytes + ' characters for RepoTrace settings, recommendations, and the open-project tip. Repository mirrors on disk are not measured here, and this page does not compress or delete them.</p><div class="action-row"><button type="button" class="secondary" id="settings-export">Export settings</button><label class="secondary settings-import">Import settings<input id="settings-import" type="file" accept="application/json,.json" hidden></label><button type="button" class="secondary settings-reset">Reset settings</button></div><p class="help-text">Export is a JSON file of these choices. It does not contain a GitHub token. Reset returns these choices to their defaults and does not sign you out.</p></section>'
      + '<section class="settings-block" id="set-performance"' + shown('performance') + '><h2>Performance</h2><p class="help-text">Analysis is one process on this computer, started when you open a comparison. Cancel stops that process. There is no background worker, so these controls are not switches.</p><ul class="limit-list"><li>No CPU cap, memory cap, battery mode, or hardware-acceleration switch.</li><li>No Git executable path, default branch editor, or SSH key manager.</li><li>No GitLab or Azure DevOps sign-in.</li><li>No cache compression, cleanup schedule, or backup of the repository mirror.</li><li>No numeric score for test recommendations. The test plan categories are rules over the review, not a sensitivity dial.</li></ul></section></div></div>';
  }

  function setStatus(text) {
    var node = document.getElementById('settings-status');
    if (node) node.textContent = text;
  }

  function bind(root) {
    if (!root) return;
    var refreshBytes = function () {
      var node = document.getElementById('settings-bytes');
      if (node) node.textContent = 'This browser is storing about ' + storageBytes() + ' characters for RepoTrace settings, recommendations, and the open-project tip. Repository mirrors on disk are not measured here, and this page does not compress or delete them.';
    };
    var writeControl = function (control) {
      var settings = load();
      var value = control.type === 'checkbox' ? control.checked : control.value;
      settings[control.getAttribute('data-key')] = value;
      save(settings);
      if (control.getAttribute('data-key') === 'colorMode') syncTheme();
      else overlay();
      var readout = root.querySelector('[data-for="' + control.getAttribute('data-key') + '"]');
      if (readout) readout.textContent = control.value;
      setStatus('Saved on this computer.');
    };
    var showSection = function (id, persist) {
      var known = false;
      root.querySelectorAll('.settings-block').forEach(function (block) {
        if (block.id === 'set-' + id) known = true;
      });
      if (!known) id = 'appearance';
      root.querySelectorAll('.settings-block').forEach(function (block) {
        block.hidden = block.id !== 'set-' + id;
      });
      root.querySelectorAll('.settings-link').forEach(function (link) {
        var on = link.getAttribute('data-section') === id;
        link.classList.toggle('is-current', on);
        link.setAttribute('aria-current', on ? 'page' : 'false');
      });
      if (persist) {
        var settings = load();
        settings.section = id;
        save(settings);
      }
    };
    root.querySelectorAll('[data-key]').forEach(function (control) {
      control.addEventListener('change', function () { writeControl(control); });
      if (control.type === 'range') control.addEventListener('input', function () { writeControl(control); });
    });
    root.querySelectorAll('[data-mode]').forEach(function (button) {
      button.addEventListener('click', function () {
        var settings = load();
        settings.colorMode = button.getAttribute('data-mode');
        save(settings);
        syncTheme();
        setStatus('Saved on this computer.');
        root.querySelectorAll('[data-mode]').forEach(function (other) {
          var on = other === button;
          other.classList.toggle('is-on', on);
          other.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
      });
    });
    root.querySelectorAll('[data-accent]').forEach(function (button) {
      button.addEventListener('click', function () {
        var settings = load();
        settings.accent = button.getAttribute('data-accent') || '';
        save(settings);
        if (window.RTTheme) RTTheme.restore();
        overlay();
        setStatus('Saved on this computer.');
        root.querySelectorAll('[data-accent]').forEach(function (other) {
          var on = other === button;
          other.classList.toggle('is-on', on);
          other.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
      });
    });
    root.querySelectorAll('.settings-link').forEach(function (link) {
      link.addEventListener('click', function () {
        var box = document.getElementById('settings-q');
        if (box) box.value = '';
        showSection(link.getAttribute('data-section'), true);
      });
    });
    var search = document.getElementById('settings-q');
    if (search) search.addEventListener('input', function () {
      var query = search.value.trim().toLowerCase();
      if (!query) {
        showSection(load().section || 'appearance', false);
        root.querySelectorAll('.settings-link').forEach(function (link) { link.hidden = false; });
        return;
      }
      root.querySelectorAll('.settings-block').forEach(function (block) {
        block.hidden = (block.innerText || '').toLowerCase().indexOf(query) < 0;
      });
      root.querySelectorAll('.settings-link').forEach(function (link) {
        var block = document.getElementById('set-' + link.getAttribute('data-section'));
        link.hidden = !!(block && block.hidden);
      });
    });
    var clearRecs = document.getElementById('settings-clear-recs');
    if (clearRecs) clearRecs.addEventListener('click', function () {
      try {
        Object.keys(localStorage).forEach(function (key) {
          if (key.indexOf('repotrace-recs:') === 0) localStorage.removeItem(key);
        });
      } catch (error) {}
      refreshBytes();
      setStatus('Recommendation marks were cleared on this computer.');
    });
    var exporter = document.getElementById('settings-export');
    if (exporter) exporter.addEventListener('click', function () {
      var blob = new Blob([JSON.stringify(load(), null, 2)], {type: 'application/json'});
      var url = URL.createObjectURL(blob);
      var link = document.createElement('a');
      link.href = url;
      link.download = 'repotrace-settings.json';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      setStatus('Settings file downloaded. It has no token.');
    });
    var importer = document.getElementById('settings-import');
    if (importer) importer.addEventListener('change', function () {
      var file = importer.files && importer.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function () {
        var parsed;
        try { parsed = JSON.parse(String(reader.result || '')); } catch (error) { setStatus('That file is not settings JSON.'); return; }
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) { setStatus('That file is not settings JSON.'); return; }
        var settings = load();
        Object.keys(DEFAULTS).forEach(function (key) {
          if (parsed[key] != null && typeof parsed[key] === typeof DEFAULTS[key]) settings[key] = parsed[key];
        });
        save(settings);
        syncTheme();
        document.dispatchEvent(new CustomEvent('repotrace-settings-refresh'));
        setStatus('Settings imported.');
      };
      reader.readAsText(file);
    });
    root.querySelectorAll('.settings-reset').forEach(function (reset) {
      reset.addEventListener('click', function () {
        save(Object.assign({}, DEFAULTS));
        if (window.RTTheme) RTTheme.apply('github-dark');
        syncTheme();
        document.dispatchEvent(new CustomEvent('repotrace-settings-refresh'));
        setStatus('Settings were reset. The GitHub token was not removed.');
      });
    });
    var testNotice = document.getElementById('settings-test-notice');
    if (testNotice) testNotice.addEventListener('click', function () { notify('This is a test notice from Settings.', {testNotice: true, error: true}); setStatus('If the browser allows notices, one was sent.'); });
    var testSound = document.getElementById('settings-test-sound');
    if (testSound) testSound.addEventListener('click', function () { beep(); setStatus('The sound played.'); });
    showSection(load().section || 'appearance', false);
  }

  function wrapTheme() {
    if (!window.RTTheme || RTTheme._settingsWrapped) return;
    ['apply', 'preview', 'restore'].forEach(function (name) {
      var original = RTTheme[name];
      RTTheme[name] = function (id) {
        var theme = original(id);
        overlay();
        return theme;
      };
    });
    RTTheme._settingsWrapped = true;
  }

  wrapTheme();
  syncTheme();
  if (window.matchMedia) {
    var media = window.matchMedia('(prefers-color-scheme: light)');
    var onScheme = function () { if (load().colorMode === 'system') syncTheme(); };
    if (media.addEventListener) media.addEventListener('change', onScheme);
    else if (media.addListener) media.addListener(onScheme);
  }
  function themeCards() {
    if (!window.RTTheme) return '';
    var current = RTTheme.current();
    return RTTheme.themes.map(function (theme) {
      var on = theme.id === current;
      return '<button type="button" class="theme-card' + (on ? ' is-saved' : '') + '" data-theme-id="' + escape(theme.id) + '" aria-pressed="' + (on ? 'true' : 'false') + '" aria-label="' + escape(theme.name) + ', ' + escape(theme.kind) + ' theme"><span class="theme-swatch" style="background:' + theme.bg + ';color:' + theme.text + ';border-color:' + theme.border + '"><span class="theme-dots" aria-hidden="true"><i style="background:' + theme.accent + '"></i><i style="background:' + theme.success + '"></i><i style="background:' + theme.warning + '"></i><i style="background:' + theme.error + '"></i></span><strong>Aa</strong><small style="color:' + theme.muted + '">' + escape(theme.name) + '</small></span></button>';
    }).join('');
  }

  function showBeforeProject() {
    var content = document.getElementById('content');
    if (!content) return;
    content.innerHTML = render({
      themeCards: themeCards(),
      gitHtml: '<p class="help-text">Open a project to connect GitHub and to read the local Git status. GitLab and Azure DevOps stay disconnected.</p>'
    });
    bind(content);
  }

  document.addEventListener('click', function (event) {
    if (window.RTLab && RTLab.current) return;
    var target = event.target && event.target.closest ? event.target : null;
    if (!target) return;
    if (target.closest('[data-action="settings"]')) {
      showBeforeProject();
      return;
    }
    var card = target.closest('[data-theme-id]');
    if (card && document.getElementById('content') && document.getElementById('content').querySelector('.settings-shell')) {
      var chosen = RTTheme.apply(card.getAttribute('data-theme-id'));
      noteTheme(chosen);
      showBeforeProject();
    }
  });

  window.RTSettings = {
    get: load,
    noteTheme: noteTheme,
    overlay: overlay,
    notify: notify,
    quietNow: quietNow,
    render: render,
    bind: bind,
    apply: syncTheme
  };
})();
