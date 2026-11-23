"""Recommendations are rules over a review dict. No model score, no generic advice, no user state."""
import json
import unittest

from repotrace.changes.change_impact import analyze_change_impact
from repotrace.report import lab_data
from repotrace.report.dashboard import build_view
from repotrace.report.recommendations import FIELDS, answer_followup, build_recommendations, tests_to_run_first
from tests.test_change_impact import RepoCase


def fixture():
    return {
        'history_window': 60,
        'changed': [
            {'node': 3, 'name': 'calculate_total', 'file': 'pricing.py', 'change': 'modified'},
            {'node': 4, 'name': 'format_receipt', 'file': 'receipt.py', 'change': 'modified'},
            {'node': 5, 'name': 'unused_helper', 'file': 'helpers.py', 'change': 'modified'},
        ],
        'concerns': [
            {'type': 'signature', 'title': 'place_order → calculate_total() no longer fits',
             'node': 8, 'file': 'orders.py', 'line': 12,
             'what': 'The call fits the old parameters but not the new ones: missing tax argument.',
             'why': 'This call would raise an error when it runs.',
             'check': 'Open place_order and update the call to calculate_total.'},
            {'type': 'leftover', 'title': 'report may still use the removed old_discount',
             'node': 9, 'file': 'legacy.py', 'line': 4,
             'what': 'report used old_discount, which no longer exists in the new version.',
             'why': 'If it still calls the old name it will fail when it runs.',
             'check': 'Open report and update or confirm its use of old_discount.'},
        ],
        'tests': [
            {'name': 'test_total', 'file': 'tests/test_pricing.py', 'line': 10,
             'run': 'python3 -m pytest tests/test_pricing.py::test_total',
             'tier': 0, 'seen_in': ['before'],
             'reasons': [{'change': 0, 'for': 'calculate_total', 'tier': 0, 'chain': ['test_total', 'calculate_total']}]},
            {'name': 'test_receipt', 'file': 'tests/test_receipt.py', 'line': 4,
             'run': 'python3 -m pytest tests/test_receipt.py::test_receipt',
             'tier': 1, 'seen_in': ['before', 'after'],
             'reasons': [{'change': 1, 'for': 'format_receipt', 'tier': 1}]},
        ],
        'removed_tests': [
            {'name': 'test_old_discount', 'file': 'tests/test_legacy.py', 'for': 'old_discount',
             'chain': ['test_old_discount', 'old_discount']},
        ],
        'history': [
            {'file': 'pricing.py', 'changed_in': 4, 'with': [{'file': 'orders.py', 'together': 3, 'of': 4}]},
            {'file': 'receipt.py', 'changed_in': 2, 'with': [{'file': 'formatters.py', 'together': 1, 'of': 2}]},
        ],
        'test_plan': {'omitted': 2, 'selected': 2, 'total_candidates': 4, 'limit': 20},
        'gaps': [
            '2 calls inside the changed functions could not be traced.',
            'No findings does not mean safe.',
        ],
        'unresolved': [{'name': 'calculate_total', 'file': 'pricing.py', 'count': 2, 'node': 3}],
    }


class RecommendationTests(unittest.TestCase):
    def test_every_item_is_specific_complete_and_free_of_a_fake_score(self):
        review = fixture()
        review['concerns'][0]['dismissed'] = True
        review['predicted_failure'] = 0.87
        items = build_recommendations(review)
        again = build_recommendations(fixture())
        self.assertEqual([item['id'] for item in items], [item['id'] for item in again])
        self.assertTrue(items)
        self.assertEqual(sum(item['level'] == 4 for item in items), 1)
        self.assertFalse(any(item['level'] == 3 for item in items))
        blob = json.dumps(items)
        self.assertNotIn('0.87', blob)
        self.assertNotIn('improve performance', blob.lower())
        self.assertNotIn('check your data', blob.lower())
        self.assertNotRegex(blob, r'\d+(\.\d+)?%')
        known = ('calculate_total', 'format_receipt', 'unused_helper', 'place_order', 'old_discount',
                 'report', 'test_total', 'test_old_discount', 'orders.py', 'pricing.py', 'formatters.py')
        for item in items:
            self.assertTrue(set(FIELDS) <= set(item), sorted(item))
            self.assertTrue(set(item) <= set(FIELDS) | {'id', 'level'})
            self.assertNotIn('dismissed', item)
            self.assertNotIn('completed', item)
            self.assertNotIn('saved', item)
            self.assertNotIn('hypothesis', item['evidence'])
            self.assertTrue(any(name in item['recommendation'] for name in known), item['recommendation'])
            self.assertTrue(item['reasoning'] and item['expected_impact'] and item['implementation'])
            self.assertTrue(item['dependencies'] and item['risks'])
            self.assertIn('Static analysis, not runtime proof', ' '.join(item['risks']))
            self.assertEqual(set(item['confidence']), {'level', 'basis'})
            self.assertEqual(set(item['next_action']), {'kind', 'target'})
            self.assertIn(item['next_action']['kind'], ('review-tab', 'node', 'copy-test'))
            self.assertEqual(item['confidence']['level'], _level_from_basis(item['confidence']['basis']))
            kind = item['evidence']['kind']
            if kind in ('concern', 'lost-path', 'removed-test', 'no-test'):
                self.assertEqual(item['level'], 1)
                self.assertEqual(item['priority'], 'now')
            elif kind == 'history':
                self.assertEqual(item['level'], 2)
                self.assertEqual(item['confidence']['level'], 'low')
                self.assertIn('correlation', item['recommendation'].lower())
                self.assertIn('Correlation is not a call', ' '.join(item['risks']))
                together = item['evidence']['counts']['together']
                self.assertEqual(item['priority'], 'soon' if together >= 2 else 'later')
            elif kind == 'strategy':
                self.assertEqual(item['level'], 4)
                self.assertEqual(item['priority'], 'soon')
                self.assertEqual(item['evidence']['counts']['omitted'], 2)
                self.assertNotIn('safe', json.dumps(item).lower())
            else:
                self.fail(kind)
            if item['confidence']['level'] == 'high':
                self.assertEqual(item['evidence']['certainty'], 'sure')
            if item['evidence']['certainty'] == 'correlation':
                self.assertEqual(item['confidence']['level'], 'low')
            if item['evidence']['certainty'] in ('maybe', 'assumption'):
                self.assertEqual(item['confidence']['level'], 'medium')

        lost = next(item for item in items if 'test_total' in item['recommendation'])
        self.assertEqual((lost['level'], lost['priority'], lost['confidence']['level']), (1, 'now', 'high'))
        self.assertEqual(lost['next_action']['kind'], 'copy-test')
        self.assertIn('pytest', lost['next_action']['target'])
        traced = [fact for item in items for fact in item['evidence']['facts'] if 'could not be traced' in fact]
        self.assertTrue(traced, items)

        leftover = next(item for item in items if 'old_discount' in item['recommendation'] and item['evidence']['kind'] == 'concern')
        self.assertEqual(leftover['confidence']['level'], 'medium')
        self.assertEqual(leftover['priority'], 'now')

        missing = next(item for item in items if 'unused_helper' in item['recommendation'])
        self.assertEqual((missing['level'], missing['priority'], missing['confidence']['level']), (1, 'now', 'medium'))

        soon = next(item for item in items if item['level'] == 2 and 'orders.py' in item['recommendation'])
        self.assertEqual(soon['priority'], 'soon')
        later = next(item for item in items if item['level'] == 2 and 'formatters.py' in item['recommendation'])
        self.assertEqual(later['priority'], 'later')
        strategy = next(item for item in items if item['level'] == 4)
        self.assertIn('Measured:', strategy['evidence']['facts'][0])
        self.assertIn('Choice, not a measurement', strategy['evidence']['facts'][1])

    def test_a_gap_alone_is_not_advice_and_overflow_names_are_kept(self):
        self.assertEqual(build_recommendations({'changed': [], 'concerns': [], 'tests': [], 'history': [], 'gaps': ['be careful']}), [])
        tests = [{
            'name': 'test_%02d' % i, 'file': 'tests/test_app.py', 'run': 'python3 -m pytest tests/test_app.py::test_%02d' % i,
            'tier': 0, 'seen_in': ['before'], 'reasons': [{'change': 0, 'for': 'alpha', 'tier': 0}],
        } for i in range(9)]
        items = build_recommendations({'changed': [{'name': 'alpha', 'file': 'a.py', 'node': 1}], 'tests': tests, 'history': []})
        lost = [item for item in items if item['evidence']['kind'] == 'lost-path']
        self.assertEqual(len(lost), 8)
        noted = [item for item in lost if item['evidence']['counts'].get('more') == 1]
        self.assertEqual(len(noted), 1)
        self.assertIn('test_08', json.dumps(noted[0]['evidence']))

    def test_follow_up_searches_the_fields_and_does_not_invent_an_answer(self):
        items = build_recommendations(fixture())
        hit = answer_followup(items, 'where is test_total')
        self.assertTrue(hit['matched'])
        self.assertIn('not an AI answer', hit['note'])
        self.assertTrue(any('test_total' in (row['recommendation'] + row['evidence']) for row in hit['hits']))
        none = answer_followup(items, 'quantum blockchain')
        self.assertFalse(none['matched'])
        self.assertIn('Nothing in this review', none['note'])
        empty = answer_followup(items, 'the')
        self.assertFalse(empty['matched'])
        self.assertIn('not an AI answer', empty['note'])
        self.assertEqual(empty['hits'], [])

    def test_tests_to_run_first_uses_only_recorded_evidence(self):
        review = fixture()
        review['tests_outside'] = [{
            'name': 'test_later', 'file': 'tests/test_later.py', 'line': 8,
            'run': 'python3 -m pytest tests/test_later.py::test_later',
            'tier': 0, 'seen_in': ['before', 'after'],
            'via': {'kind': 'setup', 'name': 'PricingTests.setUp'},
            'chain': ['test_later', 'PricingTests.setUp', 'format_receipt'],
            'reasons': [{'change': 1, 'for': 'format_receipt', 'tier': 0,
                         'via': {'kind': 'setup', 'name': 'PricingTests.setUp'},
                         'chain': ['test_later', 'PricingTests.setUp', 'format_receipt']}],
        }]
        items = build_recommendations(review)
        review['recommendations'] = items
        pack = tests_to_run_first(review)
        blob = json.dumps(pack)
        self.assertNotIn('safe', blob.lower())
        self.assertNotRegex(blob, r'\d+(\.\d+)?%')
        self.assertNotRegex(blob, r'\b0\.\d+')
        self.assertNotIn('probability', blob.lower())
        by_name = {row['name']: row for row in pack['tests']}
        lost = next(item for item in items if item['evidence']['kind'] == 'lost-path' and 'test_total' in item['recommendation'])
        self.assertEqual(by_name['test_total']['priority'], lost['priority'])
        self.assertEqual(by_name['test_total']['confidence'], lost['confidence'])
        self.assertEqual(by_name['test_total']['priority'], 'now')
        self.assertEqual(by_name['test_total']['confidence']['level'], 'high')
        self.assertIn('Lost path', by_name['test_total']['why'])
        self.assertEqual(by_name['test_total']['command'], 'python3 -m pytest tests/test_pricing.py::test_total')
        self.assertIn('not coverage', by_name['test_total']['does_not_prove'])
        self.assertIn('not proof the code is untested', by_name['test_total']['does_not_prove'])
        self.assertEqual(by_name['test_receipt']['priority'], 'soon')
        self.assertEqual(by_name['test_receipt']['confidence']['level'], 'medium')
        self.assertIn('Connected call', by_name['test_receipt']['why'])
        self.assertEqual(by_name['test_later']['priority'], 'later')
        self.assertEqual(by_name['test_later']['confidence']['level'], 'high')
        self.assertIn('setUp', by_name['test_later']['why'])
        self.assertIn('PricingTests.setUp', by_name['test_later']['why'])
        self.assertTrue(any('unused_helper' in note for note in pack['missing']))
        self.assertNotIn('unused_helper', by_name)

        alone = {
            'changed': [{'name': 'alpha', 'file': 'a.py', 'node': 1}],
            'tests': [],
            'tests_outside': [{
                'name': 'test_alpha', 'file': 'tests/test_a.py', 'line': 2,
                'run': 'python3 -m pytest tests/test_a.py::test_alpha',
                'tier': 0, 'seen_in': ['before', 'after'],
                'reasons': [{'change': 0, 'for': 'alpha', 'tier': 0, 'chain': ['test_alpha', 'alpha']}],
            }],
            'test_plan': {'omitted': 1, 'selected': 0},
        }
        advised = build_recommendations(alone)
        self.assertFalse(any(item['evidence']['kind'] == 'no-test' for item in advised))
        alone['recommendations'] = advised
        only = tests_to_run_first(alone)['tests'][0]
        self.assertEqual(only['priority'], 'now')
        self.assertEqual(only['confidence']['level'], 'high')
        self.assertIn('only connected test', only['priority_reason'])
        self.assertIn('Connected call', only['why'])


class WiredReviewTests(RepoCase):
    def test_build_review_attaches_recommendations_from_the_comparison(self):
        base = self.commit({
            'app.py': 'def total(price):\n    return price\n',
            'tests/test_app.py': 'from app import total\n\n\ndef test_total():\n    assert total(1) == 1\n',
        })
        head = self.commit({'app.py': 'def total(price, tax):\n    return price + tax\n'})
        keep = {}
        report = analyze_change_impact(self.repo, base, head, include_possible=True, keep=keep)
        view = build_view(report, str(self.repo))
        review, _graph = lab_data.build_review(report, view, keep['reports'], str(self.repo), 'proj')
        items = review['recommendations']
        json.dumps(review)
        self.assertTrue(items)
        self.assertFalse(any(item['level'] in (3, 5) or 'dismissed' in item or 'completed' in item for item in items))
        blob = json.dumps(items).lower()
        self.assertTrue('total' in blob or 'app.py' in blob)
        self.assertNotIn('improve performance', blob)
        self.assertTrue(all(set(FIELDS) <= set(item) for item in items))
        self.assertTrue(any(item['priority'] == 'now' for item in items))


def _level_from_basis(basis):
    if 'history correlation' in basis:
        return 'low'
    if basis.startswith('Link certainty is sure'):
        return 'high'
    if 'maybe or an assumption' in basis:
        return 'medium'
    raise AssertionError(basis)


if __name__ == '__main__':
    unittest.main()
