"""Recommendations drawn only from a finished review dict.

Each item has the ten fields the screen reads, plus a stable ``id`` and a ``level``.
Dismissed, saved and completed are choices the person makes in the browser.
They are not produced here.

Levels, and only these:

* 1 Immediate — a concern, a test whose recorded path exists only in the older
  version, a test that no longer exists, or a changed definition with no
  connected test.
* 2 Analytical — a history "edited together" count. Correlation, not a cause
  and not a call.
* 3 Predictive — not emitted. RepoTrace has no probability model, so a forecast
  would be invented. A hypothesis is allowed only when its evidence keeps the
  measured facts separate and the confidence basis says it is a hypothesis.
  Nothing in this module has that kind of evidence, so level 3 is omitted.
* 4 Strategic — at most one item, choosing between two actions the review
  already lists. No invented costs.
* 5 is not an item. The screen answers follow-up questions by searching these
  fields (see ``answer_followup``). There is no model call.

Priority:

* now — a concern, a lost or removed test path, or a changed definition with
  no connected test. A concern that also has a lost test path is now.
* soon — two files edited together at least twice, or the one strategic choice.
* later — two files edited together once.

Confidence:

* high — the underlying link is recorded as written in source (sure).
* medium — the link is maybe, or the conclusion is an assumption.
* low — history correlation only. Never a numeric model score.
"""
import hashlib
import re

FIELDS = (
    'recommendation', 'reasoning', 'evidence', 'expected_impact', 'priority',
    'confidence', 'implementation', 'dependencies', 'risks', 'next_action',
)

STATIC_RISK = (
    'Static analysis, not runtime proof. A recorded link is not proof the code runs, '
    'and a missing link is not proof it is absent.'
)
CORRELATION_RISK = 'Correlation is not a call. Files edited in the same commits are not a dependency.'

_MAX = {'concern': 14, 'lost-path': 8, 'removed-test': 6, 'no-test': 8, 'history': 6}
_LABEL = {'sure': 'Measured', 'maybe': 'Assumption', 'assumption': 'Assumption', 'correlation': 'Correlation'}
_STOP = set(
    'the a an of to in and or for is are be this that it with as on by from at '
    'what which how do does did was were not'.split()
)


def priority_for(kind, together=0):
    """The priority rule. ``together`` is used only for history counts."""
    if kind in ('concern', 'lost-path', 'removed-test', 'no-test'):
        return 'now'
    if kind == 'history':
        return 'soon' if together >= 2 else 'later'
    if kind == 'strategy':
        return 'soon'
    raise ValueError('unknown recommendation kind: ' + str(kind))


def confidence_for(certainty):
    """The confidence rule. ``certainty`` is sure, maybe, assumption or correlation."""
    if certainty == 'sure':
        return {'level': 'high', 'basis': 'Link certainty is sure: written in source.'}
    if certainty == 'correlation':
        return {'level': 'low', 'basis': 'Link certainty is history correlation, not a call.'}
    return {'level': 'medium', 'basis': 'Link certainty is maybe or an assumption.'}


def answer_followup(recommendations, question):
    """Search the structured fields of this review. Not a model and not a measurement.

    Returns ``{matched, note, hits}``. ``hits`` quotes the recommendation and the
    evidence summary that contained the words. An empty question, or words that
    occur nowhere in the items, do not get an invented answer.
    """
    tokens = [w for w in re.findall(r'[a-z0-9_]+', (question or '').lower()) if len(w) > 2 and w not in _STOP]
    if not tokens:
        return {
            'matched': False,
            'note': 'Type a word from a file, a test, or a recommendation. This searches this review; it is not an AI answer.',
            'hits': [],
        }
    hits = []
    for item in recommendations or []:
        blob = _blob(item)
        found = [token for token in tokens if token in blob]
        if not found:
            continue
        evidence = item.get('evidence') or {}
        hits.append({
            'id': item.get('id'),
            'recommendation': item.get('recommendation') or '',
            'evidence': evidence.get('summary') or '',
            'matched': found,
        })
    hits.sort(key=lambda hit: (-len(hit['matched']), hit['id'] or ''))
    if not hits:
        return {'matched': False, 'note': 'Nothing in this review matches those words.', 'hits': []}
    return {
        'matched': True,
        'note': 'Matched by searching this review’s recommendations. This is not an AI answer.',
        'hits': hits[:3],
    }


def build_recommendations(review):
    """Build the recommendation list from one review. Does not mutate ``review``."""
    review = review or {}
    changed = _rows(review, 'changed')
    concerns = _rows(review, 'concerns')
    tests = _rows(review, 'tests')
    removed = _rows(review, 'removed_tests')
    history = _rows(review, 'history')
    unresolved = _rows(review, 'unresolved')
    covered_indexes, covered_names = _covered(tests + _rows(review, 'tests_outside'), removed)
    items = []

    concern_rows, concern_rest = _cap(concerns, _MAX['concern'])
    for concern in concern_rows:
        items.append(_concern_item(concern))
    _note_more(items, concern_rest, lambda c: _concern_name(c) + ' in ' + str(c.get('file') or ''))

    lost = [test for test in tests if _lost(test)]
    lost_rows, lost_rest = _cap(lost, _MAX['lost-path'])
    for test in lost_rows:
        items.append(_lost_item(test))
    _note_more(items, lost_rest, lambda t: str(t.get('name') or '') + ' in ' + str(t.get('file') or ''))

    removed_rows, removed_rest = _cap(removed, _MAX['removed-test'])
    for test in removed_rows:
        items.append(_removed_item(test))
    _note_more(items, removed_rest, lambda t: str(t.get('name') or '') + ' in ' + str(t.get('file') or ''))

    missing = []
    for index, change in enumerate(changed):
        name = change.get('name') or ''
        if index in covered_indexes or name in covered_names:
            continue
        missing.append(change)
    missing_rows, missing_rest = _cap(missing, _MAX['no-test'])
    for change in missing_rows:
        items.append(_missing_item(change))
    _note_more(items, missing_rest, lambda c: str(c.get('name') or '') + ' in ' + str(c.get('file') or ''))

    _attach_unresolved(items, unresolved)

    history_rows = []
    for hint in history:
        partner = _strongest(hint)
        if partner and int(partner.get('together') or 0) >= 1:
            history_rows.append((hint, partner))
    history_kept, history_rest = _cap(history_rows, _MAX['history'])
    window = int(review.get('history_window') or 0)
    for hint, partner in history_kept:
        items.append(_history_item(hint, partner, window))
    _note_more(items, history_rest, lambda pair: str(pair[0].get('file') or '') + ' with ' + str(pair[1].get('file') or ''))

    strategic = _strategy(review, items, concerns, tests, unresolved)
    if strategic:
        items.append(strategic)

    items.sort(key=lambda item: ({'now': 0, 'soon': 1, 'later': 2}[item['priority']], {1: 0, 4: 1, 2: 2}[item['level']], item['id']))
    return items


def _concern_item(concern):
    names = _concern_names(concern)
    name = names[0] if names else 'the definition'
    file = concern.get('file') or ''
    line = concern.get('line') or 0
    certainty = 'sure' if concern.get('type') == 'signature' else 'maybe'
    where = _where(file, line)
    check = (concern.get('check') or '').strip()
    others = [extra for extra in names[1:] if extra and extra != name]
    mention = ' It names {extra}.'.format(extra=', '.join(others)) if others else ''
    recommendation = 'Open {name} in {where} and inspect this {kind} concern.{mention}'.format(
        name=name, where=where, kind=concern.get('type') or 'recorded', mention=mention)
    facts = [
        concern.get('what') or recommendation,
        'Recorded at {where}.'.format(where=where),
        'Certainty: sure, the call is written in source.' if certainty == 'sure' else 'Certainty: maybe. The review does not record a sure call.',
    ]
    if concern.get('why'):
        facts.append(concern['why'])
    return _item(
        kind='concern', level=1, recommendation=recommendation,
        reasoning=' '.join(part for part in (concern.get('what'), concern.get('why')) if part),
        evidence=_evidence(certainty, ' '.join(facts[:2]), facts, names, [file] if file else [], {'line': int(line or 0)}),
        expected_impact='You would learn whether {name} in {file} still matches the changed code, or rule that line out.'.format(
            name=name, file=file or 'this file'),
        implementation=check or recommendation,
        dependencies=['The line is {where} in this review.'.format(where=where), 'Opening the definition does not edit the repository.'],
        risks=[STATIC_RISK, 'The concern is a place to inspect. It is not proof the call fails when the program runs.'],
        action=_node_or_tab(concern.get('node'), 'overview'),
        extra=(concern.get('type'), file, name, line),
    )


def _lost_item(test):
    name = test.get('name') or 'the test'
    file = test.get('file') or ''
    target = _reason_target(test) or 'the changed definition'
    certainty = 'sure' if _sure(test.get('tier')) else 'maybe'
    command = (test.get('run') or '').strip()
    chain = test.get('chain') or []
    recommendation = 'Copy the command for {name} in {file}. It reached {target} before this change and the new version has no recorded path.'.format(
        name=name, file=file or 'its file', target=target)
    facts = [
        'Measured: seen only before the change.' if certainty == 'sure' else 'The path was recorded only before the change.',
        'Certainty: {word}.'.format(word='sure, written in source' if certainty == 'sure' else 'maybe, one step depends on an assumption'),
        'Path: {chain}.'.format(chain=' → '.join(str(part) for part in chain) if chain else 'not stored'),
    ]
    if command:
        facts.append('Command stored in the review: ' + command)
    return _item(
        kind='lost-path', level=1, recommendation=recommendation,
        reasoning='{name} is still in {file}, but RepoTrace could follow it to {target} only in the older version.'.format(
            name=name, file=file or 'the test file', target=target),
        evidence=_evidence(certainty, facts[0] + ' Target: ' + target + '.', facts, [name, target], [file] if file else [],
                           {'tier': 0 if certainty == 'sure' else 1}),
        expected_impact='Copying the command lets you run {name} yourself and see whether the lost path still matters. RepoTrace does not run it.'.format(name=name),
        implementation=('Copy this command and run it in the project’s own environment: ' + command) if command else 'Open Related tests. No command was stored for ' + name + '.',
        dependencies=['The command is the one already stored for {name}.'.format(name=name), 'RepoTrace does not execute it.'],
        risks=[STATIC_RISK, 'A path recorded only before the change is not proof the test fails.'],
        action={'kind': 'copy-test', 'target': command} if command else {'kind': 'review-tab', 'target': 'tests'},
        extra=(file, name),
    )


def _removed_item(test):
    name = test.get('name') or 'the test'
    file = test.get('file') or ''
    target = test.get('for') or 'a changed definition'
    certainty = 'sure' if _sure(test.get('tier')) else 'assumption'
    chain = test.get('chain') or []
    recommendation = 'Open the tests list and confirm {name} in {file} is gone. It was connected to {target}, and there is nothing left to run.'.format(
        name=name, file=file or 'its file', target=target)
    facts = [
        '{name} was connected to {target} and is absent from the new version.'.format(name=name, target=target),
        'Path: {chain}.'.format(chain=' → '.join(str(part) for part in chain) if chain else 'not stored'),
    ]
    return _item(
        kind='removed-test', level=1, recommendation=recommendation,
        reasoning='The test existed on the path to {target} before this change and is not in the new version, so the review has no command to copy.'.format(target=target),
        evidence=_evidence(certainty, facts[0], facts, [name, target], [file] if file else [], {'removed': 1}),
        expected_impact='You would confirm that {name} was removed with the change, and rule out running a test that is no longer there.'.format(name=name),
        implementation='Open Related tests and read the removed-test note for {name}. Do not invent a command.'.format(name=name),
        dependencies=['The removed test is already listed on this review.', 'There is no command to copy.'],
        risks=[STATIC_RISK, 'A removed test is not proof the behavior it checked is gone.'],
        action={'kind': 'review-tab', 'target': 'tests'},
        extra=(file, name, target),
    )


def _missing_item(change):
    name = change.get('name') or 'the definition'
    file = change.get('file') or ''
    recommendation = 'Open {name} in {file}. No connected test was recorded for it in this comparison.'.format(
        name=name, file=file or 'its file')
    facts = [
        'Measured: 0 connected tests and 0 removed tests name {name}.'.format(name=name),
        'Certainty: an assumption. Absence of a path is a hole in the map, not proof the definition is untested.',
    ]
    return _item(
        kind='no-test', level=1, recommendation=recommendation,
        reasoning='None of the tests in this review, including tests that no longer exist, record a path to {name}.'.format(name=name),
        evidence=_evidence('assumption', facts[0], facts, [name], [file] if file else [], {'connected_tests': 0}),
        expected_impact='You would look for a test that reaches {name}, or rule out that this review already listed one.'.format(name=name),
        implementation='Open {name} from the changed-code list and compare it with the project’s tests. RepoTrace does not run them.'.format(name=name),
        dependencies=['The changed-definition entry for {name} is already in this review.'.format(name=name)],
        risks=[STATIC_RISK, 'No recorded test path is not proof that {name} is untested.'.format(name=name)],
        action=_node_or_tab(change.get('node'), 'changes'),
        extra=(file, name),
    )


def _history_item(hint, partner, window):
    file = hint.get('file') or ''
    other = partner.get('file') or ''
    together = int(partner.get('together') or 0)
    of = int(partner.get('of') or 0)
    changed_in = int(hint.get('changed_in') or 0)
    recommendation = 'Read {other} next to {file}. They were edited together {together} of {of} times. Treat that as correlation, not a call.'.format(
        other=other, file=file, together=together, of=of)
    facts = [
        'Measured correlation: {file} appears in {changed_in} commits in the {window} commits looked at.'.format(
            file=file, changed_in=changed_in, window=window),
        '{other} was in {together} of those {of}.'.format(other=other, together=together, of=of),
        'This is correlation, not causation, and not a recorded call.',
    ]
    return _item(
        kind='history', level=2, recommendation=recommendation,
        reasoning='In the saved history window, {file} and {other} show up in the same commits {together} times. That does not mean one calls the other.'.format(
            file=file, other=other, together=together),
        evidence=_evidence('correlation', facts[1], facts, [file, other], [file, other],
                           {'together': together, 'of': of, 'changed_in': changed_in, 'window': window}),
        expected_impact='You would learn whether {other} changed for the same reason as {file}, or rule the co-edit out as coincidence.'.format(
            other=other, file=file),
        implementation='Open Limits and history and read the co-edit counts for {file}. Do not treat them as a call graph.'.format(file=file),
        dependencies=['The counts come from the {window} commits already summarized on this review.'.format(window=window)],
        risks=[STATIC_RISK, CORRELATION_RISK],
        action={'kind': 'review-tab', 'target': 'limits'},
        extra=(file, other, together),
        together=together,
    )


def _strategy(review, items, concerns, tests, unresolved):
    runnable = [test for test in tests if (test.get('run') or '').strip()]
    omitted = int((review.get('test_plan') or {}).get('omitted') or 0)
    unresolved_calls = sum(int(row.get('count') or 0) for row in unresolved)
    no_test = [item for item in items if item['evidence']['kind'] == 'no-test']

    left, left_action = None, None
    if concerns:
        concern = concerns[0]
        names = _concern_names(concern)
        name = names[0] if names else 'the concern'
        left = 'open {name} in {file} ({kind} concern)'.format(
            name=name, file=concern.get('file') or 'its file', kind=concern.get('type') or 'recorded')
        left_action = _node_or_tab(concern.get('node'), 'overview')
    elif no_test:
        left = no_test[0]['recommendation']
        left_action = dict(no_test[0]['next_action'])
    elif unresolved:
        row = unresolved[0]
        left = 'open {name} in {file} and read the {count} calls that could not be traced'.format(
            name=row.get('name') or 'the definition', file=row.get('file') or 'its file', count=int(row.get('count') or 0))
        left_action = _node_or_tab(row.get('node'), 'changes')

    right = None
    if runnable:
        test = runnable[0]
        right = 'copy the command for {name} ({command})'.format(name=test.get('name') or 'the test', command=test['run'].strip())
    elif omitted:
        right = 'open Related tests and account for the {omitted} connected tests left outside the shortlist'.format(omitted=omitted)
    if not left or not right or left == right:
        return None

    gaps = _gap_risks(review)
    facts = [
        'Measured: {concerns} concern(s), {tests} listed test(s), {omitted} omitted from the shortlist, {calls} untraced call(s) inside changed definitions.'.format(
            concerns=len(concerns), tests=len(tests), omitted=omitted, calls=unresolved_calls),
        'Choice, not a measurement: {left} — or — {right}.'.format(left=left, right=right),
    ]
    risks = [STATIC_RISK, 'Picking one action first is not a measurement of which one matters more.']
    if omitted:
        risks.append('The shortlist leaves {omitted} connected tests outside the list. That is a budget, not a claim the rest can be skipped.'.format(omitted=omitted))
    risks.extend(gaps)
    return _item(
        kind='strategy', level=4,
        recommendation='Choose one first step already in this review: {left} — or — {right}.'.format(left=left, right=right),
        reasoning='Both actions are already visible in this comparison. The review does not rank them with a score.',
        evidence=_evidence('assumption', 'The counts are measured. Which action to take first is an assumption, not a measurement.', facts,
                           [], [], {'concerns': len(concerns), 'tests': len(tests), 'omitted': omitted, 'unresolved_calls': unresolved_calls}),
        expected_impact='You would learn which of the two listed actions you can finish with what is already on screen, and which limit in the review still blocks a conclusion.',
        implementation='First: {left}. Or first: {right}. Then use the other if the first does not answer the question.'.format(left=left, right=right),
        dependencies=['Both steps are already in this review.', 'Neither step edits the repository or runs a test by itself.'],
        risks=risks,
        action=left_action,
        extra=('strategy', left[:80], right[:80]),
    )


def _item(kind, level, recommendation, reasoning, evidence, expected_impact, implementation, dependencies, risks, action, extra, together=0):
    evidence = dict(evidence)
    evidence['kind'] = kind
    return {
        'id': _item_id(kind, extra),
        'level': level,
        'recommendation': recommendation,
        'reasoning': reasoning or recommendation,
        'evidence': evidence,
        'expected_impact': expected_impact,
        'priority': priority_for(kind, together),
        'confidence': confidence_for(evidence['certainty']),
        'implementation': implementation,
        'dependencies': [step for step in dependencies if step],
        'risks': [step for step in risks if step],
        'next_action': {'kind': action['kind'], 'target': action['target']},
    }


def _evidence(certainty, summary, facts, names, files, counts):
    clean_names = [str(name) for name in names if name]
    clean_files = [str(name) for name in files if name]
    return {
        'label': _LABEL[certainty],
        'summary': summary,
        'facts': [str(fact) for fact in facts if fact],
        'certainty': certainty,
        'names': clean_names,
        'files': clean_files,
        'counts': {key: int(value) for key, value in counts.items()},
    }


def _attach_unresolved(items, unresolved):
    for row in unresolved:
        name = row.get('name') or ''
        count = int(row.get('count') or 0)
        if not name or count < 1:
            continue
        fact = 'Measured: {count} calls inside {name} could not be traced.'.format(count=count, name=name)
        for item in items:
            names = item['evidence'].get('names') or []
            if name not in names:
                continue
            if fact not in item['evidence']['facts']:
                item['evidence']['facts'].append(fact)
            item['evidence']['counts']['unresolved'] = count
            break


def _covered(tests, removed):
    indexes, names = set(), set()
    for test in tests:
        for reason in test.get('reasons') or []:
            if not isinstance(reason, dict):
                continue
            if 'change' in reason:
                indexes.add(reason['change'])
            if reason.get('for'):
                names.add(reason['for'])
    for test in removed:
        if test.get('for'):
            names.add(test['for'])
    return indexes, names


def _lost(test):
    seen = test.get('seen_in') or []
    return list(seen) == ['before']


def _sure(tier):
    return tier in (0, 'supported', 'sure')


def _reason_target(test):
    reasons = [reason for reason in (test.get('reasons') or []) if isinstance(reason, dict) and reason.get('for')]
    if not reasons:
        return ''
    reasons.sort(key=lambda reason: (0 if _sure(reason.get('tier')) else 1, reason.get('distance') or 0, reason.get('for')))
    return reasons[0]['for']


def _concern_name(concern):
    title = concern.get('title') or ''
    name = title.split(' may ')[0].split(' → ')[0]
    if name.startswith('Decorator '):
        name = name[len('Decorator '):]
    name = name.split(' changed')[0].strip()
    return name or (concern.get('file') or '')


def _concern_names(concern):
    names = []
    primary = _concern_name(concern)
    if primary:
        names.append(primary)
    title = concern.get('title') or ''
    for pattern in (r'removed ([A-Za-z_][\w.]*)', r'→\s*([A-Za-z_][\w.]*)'):
        found = re.search(pattern, title)
        if found and found.group(1) not in names:
            names.append(found.group(1))
    return names


def _strongest(hint):
    partners = [row for row in (hint.get('with') or []) if isinstance(row, dict) and row.get('file')]
    partners.sort(key=lambda row: (-int(row.get('together') or 0), row.get('file')))
    return partners[0] if partners else None


def _gap_risks(review):
    out = []
    for gap in _rows(review, 'gaps'):
        if not isinstance(gap, str) or not gap.strip() or 'safe' in gap.lower():
            continue
        out.append(gap.strip())
        if len(out) == 2:
            break
    return out


def _node_or_tab(node, tab):
    if isinstance(node, int) and not isinstance(node, bool) and node >= 0:
        return {'kind': 'node', 'target': node}
    return {'kind': 'review-tab', 'target': tab}


def _where(file, line):
    if file and line:
        return '{file} at line {line}'.format(file=file, line=int(line))
    return file or 'the file in this review'


def _rows(review, key):
    value = review.get(key) or []
    return list(value) if isinstance(value, list) else []


def _cap(rows, limit):
    return list(rows[:limit]), list(rows[limit:])


def _note_more(items, rest, describe):
    if not rest or not items:
        return
    names = [describe(row) for row in rest]
    last = items[-1]
    last['evidence']['facts'].append('Also in this review: {names} ({count} more).'.format(names=', '.join(names), count=len(rest)))
    last['evidence']['counts']['more'] = len(rest)


def _item_id(kind, extra):
    raw = kind + '|' + '|'.join('' if part is None else str(part) for part in extra)
    return kind + '-' + hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]


DOES_NOT_PROVE = (
    'A listed test is not coverage. A missing test is not proof the code is untested.'
)


def tests_to_run_first(review):
    """Tests to run first, from the review's own tests, shortlist, and lost paths.

    Priority is now when the recorded path exists only in the older version, or
    when this is the only connected test of a changed definition. Soon means the
    test is in the shortlist. Later means it is still connected and was left
    outside that shortlist. Confidence is high only for a sure link and medium
    for a maybe link. There is no numeric score. Lost-path items already emitted
    by ``build_recommendations`` keep that item's priority and confidence.
    """
    review = review or {}
    shortlist = _rows(review, 'tests')
    outside = _rows(review, 'tests_outside')
    recommendations = _rows(review, 'recommendations')
    counts = _connection_counts(shortlist + outside)
    suggestions = []
    for test in shortlist:
        suggestions.append(_test_suggestion(test, True, counts, recommendations))
    for test in outside:
        suggestions.append(_test_suggestion(test, False, counts, recommendations))
    suggestions.sort(key=lambda row: ({'now': 0, 'soon': 1, 'later': 2}[row['priority']], row['file'], row['name']))
    missing = []
    for item in recommendations:
        evidence = item.get('evidence') or {}
        if evidence.get('kind') == 'no-test' and item.get('recommendation'):
            missing.append(item['recommendation'])
    return {'tests': suggestions, 'does_not_prove': DOES_NOT_PROVE, 'missing': missing}


def _test_suggestion(test, in_shortlist, counts, recommendations):
    lost = _lost(test)
    only = _only_connected(test, counts)
    reused = _matching_lost_recommendation(test, recommendations) if lost else None
    certainty = 'sure' if _sure(test.get('tier')) else 'maybe'
    confidence = confidence_for(certainty)
    if lost or only:
        priority = 'now'
    elif in_shortlist:
        priority = 'soon'
    else:
        priority = 'later'
    if reused and reused.get('priority') in ('now', 'soon', 'later'):
        priority = reused['priority']
    reused_confidence = (reused or {}).get('confidence') or {}
    if reused_confidence.get('level') in ('high', 'medium'):
        confidence = {'level': reused_confidence['level'], 'basis': reused_confidence.get('basis') or confidence['basis']}
    node = test.get('node')
    if isinstance(node, bool) or not isinstance(node, int) or node < 0:
        node = None
    return {
        'name': test.get('name') or '',
        'file': test.get('file') or '',
        'line': test.get('line'),
        'why': _why_listed(test),
        'priority': priority,
        'priority_reason': _priority_reason(priority, lost, only),
        'confidence': confidence,
        'command': (test.get('run') or '').strip(),
        'does_not_prove': DOES_NOT_PROVE,
        'lost': lost,
        'in_shortlist': bool(in_shortlist),
        'node': node,
    }


def _connection_counts(tests):
    counts = {}
    for test in tests:
        seen = set()
        for reason in test.get('reasons') or []:
            if not isinstance(reason, dict):
                continue
            key = reason.get('for')
            if not key:
                key = reason.get('change')
            if key is None or key in seen:
                continue
            seen.add(key)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _only_connected(test, counts):
    reasons = [reason for reason in (test.get('reasons') or []) if isinstance(reason, dict)]
    if not reasons:
        return False
    for reason in reasons:
        key = reason.get('for') or reason.get('change')
        if key is not None and counts.get(key) == 1:
            return True
    return False


def _matching_lost_recommendation(test, recommendations):
    name = test.get('name') or ''
    file = test.get('file') or ''
    if not name:
        return None
    for item in recommendations:
        evidence = item.get('evidence') or {}
        if evidence.get('kind') != 'lost-path':
            continue
        names = evidence.get('names') or []
        files = evidence.get('files') or []
        if name in names and (not file or not files or file in files):
            return item
    return None


def _why_listed(test):
    parts = []
    if _lost(test):
        parts.append('Lost path: the recorded connection is only in the older version.')
    described = False
    seen = set()
    vias = []
    top = test.get('via')
    if isinstance(top, dict):
        vias.append(top)
    for reason in test.get('reasons') or []:
        via = reason.get('via') if isinstance(reason, dict) else None
        if isinstance(via, dict):
            vias.append(via)
    for via in vias:
        mark = (via.get('kind'), via.get('name'))
        if mark in seen:
            continue
        seen.add(mark)
        name = via.get('name') or ''
        if via.get('kind') == 'setup':
            parts.append('Reached through {name}, a setUp hook the test runner calls.'.format(name=name or 'setUp'))
            described = True
        elif via.get('kind') == 'fixture':
            auto = ' It is marked autouse.' if via.get('autouse') else ''
            parts.append('Reached through the fixture {name}.{auto}'.format(name=name or 'a fixture', auto=auto))
            described = True
    if not described:
        parts.append('Connected call: a recorded path reaches the changed code.')
    targets = []
    for reason in test.get('reasons') or []:
        if isinstance(reason, dict) and reason.get('for') and reason['for'] not in targets:
            targets.append(reason['for'])
    if targets:
        parts.append('Recorded for {names}.'.format(names=', '.join(str(name) for name in targets)))
    chain = test.get('chain') or []
    if chain:
        parts.append('Path: {chain}.'.format(chain=' → '.join(str(part) for part in chain)))
    return ' '.join(parts)


def _priority_reason(priority, lost, only):
    if priority == 'now' and lost and only:
        return 'Now. The path was lost, and this is the only connected test of a changed definition.'
    if priority == 'now' and lost:
        return 'Now. The path was lost.'
    if priority == 'now' and only:
        return 'Now. This is the only connected test of a changed definition.'
    if priority == 'soon':
        return 'Soon. It is in the shortlist.'
    return 'Later. It is outside the shortlist and still connected.'


def _blob(item):
    evidence = item.get('evidence') or {}
    parts = [
        item.get('recommendation'), item.get('reasoning'), item.get('implementation'), item.get('expected_impact'),
        evidence.get('summary'), ' '.join(evidence.get('facts') or []), ' '.join(evidence.get('names') or []),
        ' '.join(evidence.get('files') or []), ' '.join(item.get('risks') or []), ' '.join(item.get('dependencies') or []),
    ]
    return ' '.join(part for part in parts if part).lower()
