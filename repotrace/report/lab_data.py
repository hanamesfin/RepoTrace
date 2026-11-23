"""The data the guided ("Lab") screens read, built from engine reports.

The screens know nothing about the engine. They read one plain structure:

    {'project': {...}, 'graphs': {key: graph}, 'reviews': [review], 'questions': [str]}

    graph   nodes (folder / file / class / function, each with its exact symbol `id`), links `[from, to, strength, calls, ver]`
    review  one comparison: what changed, what to check, the test shortlist, what could not be checked

Two ideas are kept apart on purpose, because mixing them made the prototype say too much:
  strength  how sure a link is: 0 sure (written in the code), 1 maybe (one step depends on an assumption)
  ver       which version shows it: 0 the version on screen, 1 only the older version (a removed function's old callers)

Joins inside one version use the exact symbol id. Symbol ids contain line numbers, so they are not stable across two
versions; a function is matched across versions by (file, qualified name, kind) and nothing looser. A test that is
connected to several changed functions appears once, with one reason per change. Nothing here reads files from disk:
all code shown comes from the analysed reports, so it is the code that was analysed.
"""
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from repotrace.changes.git_snapshot import GitError, run_git
from repotrace.changes.test_selection import build_test_plan
from repotrace.graph.graph_explore import Explorer, is_test_file
from repotrace.graph.graph_index import GraphIndex
from repotrace.graph.structure import build_structure
from repotrace.report.overview import build_overview
from repotrace.report.recommendations import build_recommendations, tests_to_run_first

CODE_LINES, CODE_CHARS = 30, 1600
SNIPPET_CONTEXT = 2
DIFF_CHARS = 2400


# ------------------------------------------------------------------ one version of a project

STOP = set('the a an of to in and or for is are be this that it with as on by from at self none true false return if else not def class init main conftest usually'.split())


def words(text):
    """Split identifiers and prose into lowercase words: `retryPolicy` and `retry_policy` both give retry, policy."""
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text or '')
    return [w for w in re.findall(r'[a-z][a-z0-9]+', text.lower().replace('_', ' ')) if w not in STOP and len(w) > 2]



def _words(name):
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name or '')
    return [w for w in re.findall(r'[A-Za-z][a-z0-9]*', name.replace('_', ' ')) if w]


# ---- topic grouping (experimental), copied from the prototype
def concepts(nodes, links):
    """Group files into topics by who calls whom, then name each group by its most distinctive words.

    This is an interpretation, not a fact; the screen says so."""
    files = [n for n in nodes if n['k'] == 'file' and not n['test']]
    fid = {n['i']: n['i'] for n in files}

    def file_of(i):
        while nodes[i]['k'] != 'file':
            i = nodes[i]['p']
        return i
    weight = defaultdict(lambda: defaultdict(float))
    for a, b, strength, n, ver in links:
        fa, fb = file_of(a), file_of(b)
        if ver != 1 and fa != fb and fa in fid and fb in fid:
            weight[fa][fb] += n * (1 if strength == 0 else 0.5)
            weight[fb][fa] += n * (1 if strength == 0 else 0.5)
    label = {i: i for i in fid}
    for _ in range(12):
        changed = False
        for i in sorted(fid):
            votes = Counter()
            for j, w in weight[i].items():
                votes[label[j]] += w
            if votes:
                best = max(votes.items(), key=lambda kv: (kv[1], -kv[0]))[0]
                if best != label[i]:
                    label[i], changed = best, True
        if not changed:
            break
    groups = defaultdict(list)
    for i, lab in label.items():
        groups[lab].append(i)
    # Fold small groups into the group they belong with: first by who they call, then by the folder they sit in.
    folder_of = lambda i: nodes[nodes[i]['p']]['q']

    def regroup(min_size, max_groups):
        while True:
            groups = defaultdict(list)
            for i, lab in label.items():
                groups[lab].append(i)
            small = sorted((l for l, m in groups.items() if len(m) < min_size), key=lambda l: (len(groups[l]), l))
            if not small and len(groups) <= max_groups:
                return
            lab = small[0] if small else min(groups, key=lambda l: (len(groups[l]), l))
            if len(groups) <= 1:
                return
            votes = Counter()
            for m in groups[lab]:
                for j, w in weight[m].items():
                    if label[j] != lab:
                        votes[label[j]] += w
                for j in fid:                           # same folder counts too, so files with no links still land somewhere sensible
                    if label[j] != lab and folder_of(j) == folder_of(m):
                        votes[label[j]] += 0.5
            target = max(votes.items(), key=lambda kv: (kv[1], -kv[0]))[0] if votes else max((l for l in groups if l != lab), key=lambda l: len(groups[l]))
            for m in groups[lab]:
                label[m] = target
    regroup(3, 12)
    groups = defaultdict(list)
    for i, lab in label.items():
        groups[lab].append(i)
    tokens = {lab: Counter() for lab in groups}
    for lab, members in groups.items():
        for n in nodes:
            top = n
            while top['k'] != 'file' and top['p'] is not None:
                top = nodes[top['p']]
            if top['i'] in members:
                tokens[lab].update(words(n['n'] + ' ' + (n.get('doc') or '')))
    df = Counter(w for c in tokens.values() for w in c)
    names, ordered = [], sorted(groups, key=lambda l: (-len(groups[l]), l))
    where = {}
    for k, lab in enumerate(ordered):
        score = {w: c * (1 / df[w]) for w, c in tokens[lab].items()}
        top = [w for w, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
        names.append(' · '.join(top) or 'misc')
        for m in groups[lab]:
            where[m] = k
    mapping = {}
    for n in nodes:
        top = n
        while top['k'] != 'file' and top['p'] is not None:
            top = nodes[top['p']]
        if top['k'] == 'file':
            mapping[n['i']] = where.get(top['i'], -1)
    for n in nodes:
        if n['k'] == 'dir':
            kids = Counter(mapping.get(c['i'], -1) for c in nodes if c['p'] == n['i'])
            mapping[n['i']] = kids.most_common(1)[0][0] if kids else -1
    # tests belong to the topic they mostly exercise
    for n in nodes:
        if n['k'] == 'file' and n['test']:
            votes = Counter(mapping.get(b, -1) for a, b, *_ in links if file_of_safe(nodes, a) == n['i'])
            mapping[n['i']] = votes.most_common(1)[0][0] if votes else -1
    for n in nodes:
        if n['k'] in ('class', 'fn') and n['test']:
            top = n
            while top['k'] != 'file':
                top = nodes[top['p']]
            mapping[n['i']] = mapping.get(top['i'], -1)
    return names, [mapping.get(n['i'], -1) for n in nodes]


def file_of_safe(nodes, i):
    while nodes[i]['k'] != 'file':
        i = nodes[i]['p']
    return i


def build_graph(report, version, name):
    """Nodes and links for one analysed version. Returns (graph, {symbol id: node index})."""
    files = sorted((f for f in report['files'] if f['status'] == 'ok'), key=lambda f: f['file'])
    symbols = {s['id']: s for f in files for s in f['symbols']}
    index = GraphIndex(report, include_possible=True)
    overview = build_overview(index, Explorer(index), name)
    nodes, by_id = [], {}

    def add(kind, short, qualified, parent, file, line, sid=None, **extra):
        node = {'i': len(nodes), 'k': kind, 'n': short, 'q': qualified, 'p': parent, 'file': file, 'line': line,
                'test': is_test_file(file) if file else False, **extra}
        if sid is not None:
            node['id'] = sid
            by_id[sid] = node['i']
        nodes.append(node)
        return node['i']

    def folder_of(path):
        folder = str(Path(path).parent)
        return '(top)' if folder == '.' else folder

    dirs, file_idx = {}, {}
    for f in files:
        folder = folder_of(f['file'])
        if folder not in dirs:
            dirs[folder] = add('dir', folder, folder, None, '' if folder == '(top)' else folder, 0)
            nodes[dirs[folder]]['test'] = all(is_test_file(x['file']) for x in files if folder_of(x['file']) == folder)
    for f in files:
        file_idx[f['file']] = add('file', Path(f['file']).name, f['file'], dirs[folder_of(f['file'])], f['file'], 1, lines=f.get('line_count', 0))

    def detail(s):
        doc = (s.get('docstring') or '').strip().split('\n')[0][:160]
        code = '\n'.join((s.get('source') or '').split('\n')[:CODE_LINES])[:CODE_CHARS]
        return doc, code

    ordered = sorted(symbols.values(), key=lambda s: (s['file'], s['span']['line']))
    class_idx = {}
    for s in ordered:
        top = s['parent_id'].endswith('::module')
        doc, code = detail(s)
        if s['kind'] == 'CLASS' and top:
            class_idx[s['id']] = add('class', s['name'], s['qualified_name'], file_idx[s['file']], s['file'], s['span']['line'], s['id'], doc=doc, code=code)
        elif s['kind'] == 'FUNCTION' and top:
            add('fn', s['name'], s['qualified_name'], file_idx[s['file']], s['file'], s['span']['line'], s['id'], doc=doc, code=code,
                unres=index.unresolved_by_source.get(s['id'], 0))
    for s in ordered:
        if s['kind'] == 'METHOD' and s['parent_id'] in class_idx:
            doc, code = detail(s)
            add('fn', s['name'], s['qualified_name'], class_idx[s['parent_id']], s['file'], s['span']['line'], s['id'], doc=doc, code=code,
                unres=index.unresolved_by_source.get(s['id'], 0))

    def owner(sid):                         # a nested function or class counts for the definition that contains it
        s = symbols.get(sid)
        while s is not None:
            if s['id'] in by_id:
                return by_id[s['id']]
            s = symbols.get(s['parent_id'])
        return None

    calls = Counter()
    for pairs in index.reverse.values():
        for pair in pairs:
            a, b = owner(pair['source']), owner(pair['target'])
            if a is not None and b is not None and a != b:
                calls[(a, b, 1 if pair['evidence']['resolution'] == 'POSSIBLE' else 0)] += pair['call_site_count']
    links = [[a, b, strength, n, 0] for (a, b, strength), n in sorted(calls.items())]
    rel = []                                              # class relations: 0 is a kind of, 1 creates one
    for e in build_structure(report)['edges']:
        x, y = by_id.get(e['source']), by_id.get(e['target'])
        if x is not None and y is not None and e['kind'] in ('inherits', 'holds'):
            rel.append([x, y, 0 if e['kind'] == 'inherits' else 1])
    names, concept_of = concepts(nodes, links)            # EXPERIMENTAL: topics guessed from who calls whom and common words
    graph = {'version': version, 'nodes': nodes, 'links': links, 'rel': rel, 'concepts': names, 'concept_of': concept_of, 'calls': overview['calls'],
             'files': overview['files'], 'functions': overview['functions']}
    for sid in [sid for sid in symbols if sid not in by_id]:    # a changed nested function is shown as the definition that contains it
        found = owner(sid)
        if found is not None:
            by_id[sid] = found
    return graph, by_id


def add_removed(graph, base_graph, base_by_id, report):
    """Code a change deleted is drawn from the older version: a node marked `gone`, with its old links marked ver 1.

    Returns {older symbol id: node index in `graph`}."""
    nodes = graph['nodes']
    key = lambda n: (n['file'], n['q'], n['k'])
    now = {key(n): n['i'] for n in nodes if n['k'] in ('fn', 'class')}
    removed = {}

    def place(file):
        """The file node for `file`, adding a `gone` folder and file when the whole file is gone."""
        file_node = next((n['i'] for n in nodes if n['k'] == 'file' and n['file'] == file), None)
        if file_node is not None:
            return file_node
        folder = str(Path(file).parent)
        folder = '(top)' if folder == '.' else folder
        folder_node = next((n['i'] for n in nodes if n['k'] == 'dir' and n['q'] == folder), None)
        if folder_node is None:
            folder_node = len(nodes)
            nodes.append({'i': folder_node, 'k': 'dir', 'n': folder, 'q': folder, 'p': None, 'file': '' if folder == '(top)' else folder, 'line': 0,
                          'test': is_test_file(file), 'gone': True})
        file_node = len(nodes)
        nodes.append({'i': file_node, 'k': 'file', 'n': Path(file).name, 'q': file, 'p': folder_node, 'file': file, 'line': 1, 'test': is_test_file(file), 'gone': True})
        return file_node

    for change in report['changes']:
        before = change.get('before')
        if change['change'] != 'deleted' or not before or before['id'] not in base_by_id:
            continue
        old = base_graph['nodes'][base_by_id[before['id']]]
        if key(old) in now:
            continue
        parent = None
        if old['p'] is not None and base_graph['nodes'][old['p']]['k'] == 'class':
            parent_key = key(base_graph['nodes'][old['p']])
            parent = now.get(parent_key)
        node = {**old, 'i': len(nodes), 'p': parent if parent is not None else place(old['file']), 'gone': True}
        nodes.append(node)
        now[key(old)] = node['i']
        removed[before['id']] = node['i']
    old_to_now = {i: now.get(key(n)) for i, n in enumerate(base_graph['nodes']) if n['k'] in ('fn', 'class')}
    gone = set(removed.values())
    for a, b, strength, n, _ in base_graph['links']:
        x, y = old_to_now.get(a), old_to_now.get(b)
        if x is not None and y is not None and x != y and (x in gone or y in gone):
            graph['links'].append([x, y, strength, n, 1])          # an old call, kept with its own strength, marked as old-version only
    return removed


# ------------------------------------------------------------------ code shown from the analysed text

def _sources(report):
    return {f['file']: (f.get('source') or '') for f in report['files'] if f['status'] == 'ok'}


def _lines(text):
    return text.split('\n')


def signature(text, line):
    """The `def` line(s) of a function as written in that version, decorators skipped."""
    rows, out = _lines(text), []
    for row in rows[max(line, 1) - 1:max(line, 1) + 25]:
        if not out and row.strip().startswith('@'):
            continue
        out.append(row.strip() if not out else '    ' + row.strip())
        if row.rstrip().endswith(':'):
            break
    return '\n'.join(out) or None


def snippet(text, line, around=SNIPPET_CONTEXT):
    rows = _lines(text)
    return [[k + 1, rows[k]] for k in range(max(0, line - 1 - around), min(len(rows), line + around))]


def _call_line(text, from_line, name):
    """First line inside the function that starts at `from_line` that calls `name` (a short name)."""
    rows, short = _lines(text), name.split('.')[-1]
    if not rows or not from_line or from_line > len(rows):
        return None
    indent = len(rows[from_line - 1]) - len(rows[from_line - 1].lstrip())
    for k in range(from_line, min(len(rows), from_line + 80)):
        row = rows[k]
        if row.strip() and (len(row) - len(row.lstrip())) <= indent and not row.lstrip().startswith(('#', '@', ')')):
            break
        if re.search(r'\b' + re.escape(short) + r'\s*\(', row):
            return k + 1
    return None


def history_hints(repo, files, window=60, bulk=20):
    """Files edited in the same past commits as `files`: hints, never call links. Returns (hints, commits looked at)."""
    try:
        raw = run_git(repo, 'log', f'-n{window}', '--name-only', '--format=@@%H').decode('utf-8', 'replace')
    except (GitError, TypeError, OSError):
        return [], 0
    commits = []
    for block in raw.split('@@')[1:]:
        names = [l for l in block.strip().split('\n')[1:] if l.endswith('.py')]
        if names and len(names) <= bulk:
            commits.append(set(names))
    count, pair = Counter(), defaultdict(Counter)
    for names in commits:
        for a in names:
            count[a] += 1
            for b in names:
                if a != b:
                    pair[a][b] += 1
    hints = [{'file': f, 'changed_in': count[f], 'with': [{'file': b, 'together': n, 'of': count[f]} for b, n in pair[f].most_common(3)]}
             for f in sorted(set(files)) if count.get(f)]
    return hints, len(commits)


# ------------------------------------------------------------------ one comparison

def _readable(ref, commit):
    """A tag or branch name as given; a bare commit id (what the picker sends) as its 7-character short form."""
    return commit[:7] if not ref or re.fullmatch(r'[0-9a-fA-F]{7,40}', ref) else ref


def build_review(report, view, reports, repo=None, name='project'):
    """Everything the screens need for one comparison. Returns (review, graph of the newer version with removed code added)."""
    base_ref, head_ref = report['base']['commit'][:8], report['head']['commit'][:8]
    version_name = lambda side: _readable(report[side].get('ref'), report[side]['commit'])
    after_graph, after_by_id = build_graph(reports['after'], f'{head_ref} (after the change)', name)
    base_graph, base_by_id = build_graph(reports['before'], f'{base_ref} (before the change)', name)
    removed = add_removed(after_graph, base_graph, base_by_id, report)
    nodes = after_graph['nodes']
    concept_of = after_graph['concept_of']                  # removed code joins the topic of the file it sat in
    while len(concept_of) < len(nodes):
        parent = nodes[len(concept_of)]['p']
        concept_of.append(concept_of[parent] if parent is not None and parent < len(concept_of) else -1)
    src = {'before': _sources(reports['before']), 'after': _sources(reports['after'])}
    by_file_name = {(n['file'], n['q']): n['i'] for n in nodes if n['k'] in ('fn', 'class')}

    changed, node_of_change = [], {}
    for idx, (change, shown) in enumerate(zip(report['changes'], view['changes'])):
        after, before = change.get('after'), change.get('before')
        node = after_by_id.get(after['id']) if after else removed.get(before['id']) if before else None
        node_of_change[idx] = node
        text = lambda side, sym: signature(src[side].get(change['file'], ''), sym['span']['line']) if sym else None
        changed.append({'node': node, 'name': change['qualified_name'], 'file': change['file'], 'change': change['change'], 'pair': shown.get('pair'),
                        'diff': (shown.get('diff') or '')[:DIFF_CHARS], 'before_sig': text('before', before), 'after_sig': text('after', after),
                        'line': shown.get('line') or 1})

    concerns = []
    for idx, (change, shown) in enumerate(zip(report['changes'], view['changes'])):
        target = node_of_change[idx]
        sites = {(s['file'], s['caller']): s for s in (shown.get('name_matches') or {}).get('sites', [])}
        for cand in change.get('review_candidates', []):
            if not (cand.get('still_references_removed_name') or cand.get('may_still_call_removed')):
                continue
            # After the rename the forgotten caller no longer resolves to the removed function, so it often has no 'after' link at all:
            # find it in the newer version by (file, name).
            side = cand['sides'].get('after') or next(iter(cand['sides'].values()))
            node = after_by_id.get(cand['sides']['after']['symbol_id']) if 'after' in cand['sides'] else by_file_name.get((cand['file'], cand['qualified_name']))
            site = sites.get((cand['file'], cand['qualified_name']))
            line = site['line'] if site else side['span']['line']
            concerns.append({'type': 'leftover', 'title': f"{cand['qualified_name']} may still use the removed {change['qualified_name']}",
                             'node': node, 'target': target, 'changed': idx, 'file': cand['file'], 'line': line,
                             'what': f"{cand['qualified_name']} used {change['qualified_name']}, which no longer exists in the new version.",
                             'why': 'If it still calls the old name it will fail when it runs.',
                             'snippet': snippet(src['after'].get(cand['file'], ''), line),
                             'check': f"Open {cand['qualified_name']} and update or confirm its use of {change['qualified_name']}."})
        if shown.get('decorator_effect'):
            wrapped = shown['decorator_effect']['wrapped']
            concerns.append({'type': 'decorator', 'title': f"Decorator {change['qualified_name']} changed: it wraps {len(wrapped)} functions",
                             'node': target, 'target': target, 'changed': idx, 'file': change['file'], 'line': shown.get('line') or 1,
                             'what': f"{change['qualified_name']} wraps {', '.join(wrapped[:5])}.",
                             'why': 'Every call to a wrapped function now runs the changed code first.',
                             'snippet': snippet(src['after'].get(change['file'], ''), shown.get('line') or 1),
                             'check': 'Run the tests for the wrapped functions and their callers.'})
    for idx, change in enumerate(report['changes']):
        for f in (change.get('signature_review') or {}).get('findings', []):
            concerns.append({'type': 'signature', 'title': f"{f['caller']} → {f['called_expression']}() no longer fits",
                             'node': after_by_id.get(f.get('caller_id')), 'target': node_of_change[idx], 'changed': idx,
                             'file': f['file'], 'line': f['span']['line'],
                             'what': f"The call fits the old parameters but not the new ones: {f['reason']}.",
                             'why': 'This call would raise an error when it runs.',
                             'snippet': snippet(src['after'].get(f['file'], ''), f['span']['line']), 'check': f['action']})

    # Related code that uses what changed (tests are listed separately, below).
    candidates, seen = [], set()
    for idx, change in enumerate(report['changes']):
        for cand in change.get('review_candidates', []):
            if is_test_file(cand['file']) or (cand['file'], cand['qualified_name']) in seen:
                continue
            seen.add((cand['file'], cand['qualified_name']))
            side = cand['sides'].get('after') or cand['sides'].get('before')
            node = after_by_id.get(cand['sides']['after']['symbol_id']) if 'after' in cand['sides'] else by_file_name.get((cand['file'], cand['qualified_name']))
            best = min(cand['sides'].values(), key=lambda s: s['distance'])
            strength = 1 if any(s['path_has_possible_link'] for s in cand['sides'].values()) else 0
            candidates.append({'node': node, 'name': cand['qualified_name'], 'file': cand['file'], 'line': side['span']['line'], 'dist': best['distance'],
                               'strength': strength, 'tier': strength, 'for_node': node_of_change[idx]})
    candidates.sort(key=lambda c: (c['dist'], c['strength'], c['file'], c['name']))
    # Everything the change could reach, tests included: what the graph rings as "may be affected".
    reach = {}
    for idx, change in enumerate(report['changes']):
        for cand in change.get('review_candidates', []):
            best = min(cand['sides'].values(), key=lambda s: s['distance'])
            node = after_by_id.get(cand['sides']['after']['symbol_id']) if 'after' in cand['sides'] else by_file_name.get((cand['file'], cand['qualified_name']))
            if node is None or (node in reach and reach[node]['dist'] <= best['distance']):
                continue
            strength = 1 if any(s['path_has_possible_link'] for s in cand['sides'].values()) else 0
            reach[node] = {'node': node, 'name': cand['qualified_name'], 'file': cand['file'], 'line': best['span']['line'], 'dist': best['distance'], 'tier': strength,
                           'test': is_test_file(cand['file']), 'for_node': node_of_change[idx]}
    affected = sorted(reach.values(), key=lambda a: (a['dist'], a['tier'], a['file'], a['name']))

    all_connected, removed_tests = _merge_tests(report, nodes, after_by_id, node_of_change, by_file_name, src['after'])
    plan = report.get('test_plan') or build_test_plan(report['changes'])
    by_test = {(t['file'], t['name']): t for t in all_connected}
    tests = [by_test[(t['file'], t['name'])] for t in plan['tests']]
    selected = {(t['file'], t['name']) for t in tests}
    tests_outside = [t for t in all_connected if (t['file'], t['name']) not in selected]

    unreadable = [f['file'] for r in reports.values() for f in r['files'] if f['status'] != 'ok']
    in_tests = sum(n.get('unres') or 0 for n in nodes if n['k'] == 'fn' and n['test'] and not n.get('gone'))
    in_changed = sum(nodes[c['node']].get('unres') or 0 for c in changed if c['node'] is not None and not nodes[c['node']].get('gone'))
    gaps = [g['message'] for g in report['gaps']][:4] + report['warnings'][:3]
    if unreadable:
        gaps.append(f"{len(set(unreadable))} file(s) could not be read, so their functions are missing: {', '.join(sorted(set(unreadable))[:3])}.")
    if in_changed:
        gaps.append(f"{in_changed} calls inside the changed functions could not be traced.")
    if in_tests:
        gaps.append(f"{in_tests} calls inside tests could not be followed (for example objects handed over by parametrized fixtures, built by a factory or "
                    'a dependency container, or unpacked from a tuple), so tests that reach the change that way are missing from the list.')
    gaps.append('Signature checks cover explicit calls to plain functions. Methods, decorated targets, constructors and calls using *args/**kwargs are not checked. '
                'No findings does not mean safe.')
    hints, window = history_hints(repo, [c['file'] for c in changed]) if repo else ([], 0)
    subject = (view['head'].get('subject') or '').strip()
    review = {'id': f'{base_ref}..{head_ref}', 'graph': f'{base_ref}..{head_ref}', 'example': False,
              'label': subject or f"{len(changed)} changed definition{'s' if len(changed) != 1 else ''}",
              'base': version_name('base'), 'head': version_name('head'),
              'base_commit': report['base']['commit'], 'head_commit': report['head']['commit'], 'story': view.get('story'), 'changed': changed,
              'concerns': concerns[:14], 'candidates': candidates[:10], 'affected': affected, 'tests': tests,
              'tests_outside': tests_outside, 'removed_tests': removed_tests, 'history': hints,
              'test_plan': {k: v for k, v in plan.items() if k != 'tests'},
              'history_window': window, 'gaps': [g for g in gaps if g]}
    review['unresolved'] = _unresolved_calls(nodes, changed)
    review['recommendations'] = build_recommendations(review)
    review['test_recommendations'] = tests_to_run_first(review)
    return review, after_graph


def _unresolved_calls(nodes, changed):
    """Calls the analyzer could not trace inside changed definitions that still exist."""
    out = []
    for change in changed:
        node = change.get('node')
        if not isinstance(node, int) or isinstance(node, bool) or node < 0 or node >= len(nodes):
            continue
        info = nodes[node]
        if info.get('gone'):
            continue
        count = info.get('unres') or 0
        if count:
            out.append({'name': change['name'], 'file': change['file'], 'count': int(count), 'node': node})
    return out


def _merge_tests(report, nodes, after_by_id, node_of_change, by_file_name, after_src):
    """One entry per test, with one reason per changed function it connects to. Nothing is discarded."""
    merged, removed, removed_seen = {}, [], set()
    for idx, change in enumerate(report['changes']):
        selection = change.get('test_selection') or {}
        for t in selection.get('tests', []):
            key = (t['file'], t['name'])
            entry = merged.setdefault(key, {'name': t['name'], 'file': t['file'], 'line': t['line'], 'run': t['run'], 'reasons': [],
                                            'node': after_by_id.get((t.get('ids') or {}).get('after'), by_file_name.get(key))})
            entry['reasons'].append({'change': idx, 'target': node_of_change[idx], 'for': change['qualified_name'], 'chain': t['chain'], 'via': t.get('via'),
                                     'tier': 0 if t['tier'] == 'supported' else 1, 'seen_in': t['seen_in'], 'distance': t['distance']})
        for t in selection.get('removed_tests', []):
            if (t['file'], t['name']) not in removed_seen:
                removed_seen.add((t['file'], t['name']))
                removed.append({'name': t['name'], 'file': t['file'], 'chain': t['chain'], 'for': change['qualified_name']})
    out = []
    for entry in merged.values():
        entry['reasons'].sort(key=lambda r: (r['tier'], r['distance'], r['for']))
        best = entry['reasons'][0]
        seen_in = [side for side in ('before', 'after') if any(side in r['seen_in'] for r in entry['reasons'])]
        entry.update({'tier': best['tier'], 'seen_in': seen_in, 'chain': best['chain'], 'via': best['via'], 'for_node': best['target'], 'dist': best['distance']})
        # Where the path begins: in the test body, or in the setUp hook it runs through. A fixture's evidence is in the fixture, not shown here.
        via, chain = best['via'] or {}, best['chain']
        start, nxt = entry['line'], (chain[1] if len(chain) > 1 else '')
        if via.get('kind') == 'setup':
            hook = by_file_name.get((entry['file'], via['name']))
            start, nxt = (nodes[hook]['line'] if hook is not None else None), (chain[2] if len(chain) > 2 else '')
        elif via.get('kind') == 'fixture':
            start = None
        line = _call_line(after_src.get(entry['file'], ''), start, nxt) if start and nxt else None
        entry['call_line'] = line
        entry['snippet'] = snippet(after_src.get(entry['file'], ''), line) if line else None
        out.append(entry)
    out.sort(key=lambda e: (e['tier'], e['dist'], e['file'], e['name']))
    return out, removed


# ------------------------------------------------------------------ the whole payload

def questions_for(graph, limit=4):
    """Sample questions drawn from the project itself: its most-used definitions, in plain words."""
    nodes = graph['nodes']
    used = Counter(b for a, b, *_ in graph['links'] if not nodes[a]['test'])
    plumbing = re.compile(r'^(__.*__|main|(print|show|ask|log|debug|echo|display|render|format|get|set|to|from)_.*|.*_(str|repr))$')   # helpers everything calls: a poor starting point
    ranked = sorted((n for n in nodes if n['k'] in ('fn', 'class') and not n['test'] and not n.get('gone') and not plumbing.match(n['n'])),
                    key=lambda n: (-used[n['i']], n['q']))
    out = []
    for n in ranked:
        words = ' '.join(w.lower() for w in _words(n['n']))
        if not words:
            continue
        out.append(f'where is {words} used?' if n['k'] == 'fn' else f'what is {words}?')
        if len(out) == limit:
            break
    return out


def payload(name, main_graph, reviews, review_graphs):
    return {'project': {'name': name, 'made_at': time.strftime('%Y-%m-%d %H:%M')},
            'graphs': {'main': main_graph, **review_graphs}, 'reviews': reviews, 'questions': questions_for(main_graph)}
