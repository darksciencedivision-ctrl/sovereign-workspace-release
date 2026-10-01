"""Exercise refusal boundaries missed by the exact-route line trace."""
import copy

import pytest

from test_si_exact_counting import EC, EW, SPEC, OBJECTIVE, Script, _counter, _notes


@pytest.mark.parametrize('change', [
    {'fields': []},
    {'aggregates': [None]},
    {'aggregates': [{'op': 'count_where_all', 'where': [], 'extra': True}]},
    {'aggregates': [{'op': 'count_where_all', 'where': [{}, {}]}]},
])
def test_malformed_spec_boundaries_are_refused(change):
    spec = copy.deepcopy(SPEC)
    spec.update(change)
    with pytest.raises(EW.SpecError):
        EW.parse_spec(spec)


@pytest.mark.parametrize('first', [{'applicable': False}, {'applicable': True}])
def test_non_json_correction_falls_back_without_exact_claim(tmp_path, first):
    text, _ = _notes(20)
    outcome = _counter(Script(first, 'not JSON'), tmp_path).run(OBJECTIVE, text)
    assert outcome.answer is None
    assert outcome.note == 'the model did not correct its spec'


def test_model_confirmation_cannot_override_missing_objective_fields(tmp_path):
    text, _ = _notes(20)
    incomplete = copy.deepcopy(SPEC)
    incomplete['aggregates'] = [{'op': 'count'}]
    outcome = _counter(Script(incomplete, {'ok': True}), tmp_path).run(OBJECTIVE, text)
    assert outcome.answer is None
    assert 'not covered by the computed table' in outcome.note


def test_compound_count_alone_is_an_eligible_count():
    spec = {'pattern': 'Log', 'fields': {'level': 'str', 'component': 'str'},
            'aggregates': [{'op': 'count_where_all', 'where': [
                {'field': 'level', 'cmp': '==', 'value': 'ERROR'},
                {'field': 'component', 'cmp': '==', 'value': 'db'}]}]}
    assert EC.objective_fit_issues('How many ERROR lines from db?', spec) == []
