"""Replay observed false-positive and good specs without a model or GPU."""
import json
from pathlib import Path

import pytest

from test_si_exact_counting import EC, SPEC, OBJECTIVE, _counter, _notes

FIXTURES = Path(__file__).with_name('fixtures')
BAD_OBJECTIVE = 'How many components does the design describe, and which one is the most important?'


def load(name):
    return json.loads((FIXTURES / (name + '.json')).read_text())


def test_recorded_false_positive_is_not_replayed(tmp_path):
    bad = load('job_0804302e4575494aa212affefb0dc569')
    (tmp_path / EC.STATE_FILE).write_bytes(json.dumps(bad).encode())
    outcome = _counter(None, tmp_path).run(BAD_OBJECTIVE, None)
    assert outcome.answer is None, 'cached wrong confident answer must be invalidated'
    assert 'not covered' in outcome.note


@pytest.mark.parametrize('name,count', [
    ('job_9ac3fc1f33fe47e4ae8c580e993a2787', 63),
    ('job_4f51f0a52a5844ef96531f808e8617d9', 124),
])
def test_recorded_good_specs_cover_objective(name, count):
    saved = load(name)
    assert EC.objective_fit_issues(OBJECTIVE, saved['spec']) == []
    assert next(a['result'] for a in saved['results']['aggregates']
                if a['op'] == 'count_where') == count


@pytest.mark.parametrize('objective', [
    'How many notes report 16 warnings and what is the total of revenue?',
    'Which customer has the most warnings?',
    'How many notes report 16 warnings and which is the most important?',
    'How many notes report 15 warnings?',
    'What is the minimum warnings?',
])
def test_each_requested_quantity_needs_a_matching_aggregate(objective):
    assert EC.objective_fit_issues(objective, SPEC)


def test_ranked_record_count_must_be_captured():
    spec = {**SPEC, 'fields': {k: v for k, v in SPEC['fields'].items() if k != 'records'}}
    assert EC.objective_fit_issues(OBJECTIVE, spec)


class Model:
    def __init__(self, uncovered):
        self.uncovered = uncovered
        self.coverage_calls = 0

    def generate(self, *, prompt, **kwargs):
        if 'List every part of the objective NOT covered' in prompt:
            self.coverage_calls += 1
            return json.dumps({'uncovered': self.uncovered})
        if 'Does this extract the records' in prompt:
            return '{"ok": true}'
        if 'Exact results computed' in prompt:
            return 'The computed results follow.'
        return json.dumps(SPEC)


@pytest.mark.parametrize('uncovered', [['causal explanation'], None, 'none'])
def test_nonempty_or_invalid_model_coverage_falls_back(tmp_path, uncovered):
    model = Model(uncovered)
    text, _ = _notes(30)
    outcome = _counter(model, tmp_path).run(OBJECTIVE, text)
    assert outcome.answer is None
    assert model.coverage_calls == 1


def test_empty_coverage_preserves_exact_answer(tmp_path):
    model = Model([])
    text, _ = _notes(30)
    outcome = _counter(model, tmp_path).run(OBJECTIVE, text)
    assert 'Computed by the product' in outcome.answer
    assert model.coverage_calls == 1
