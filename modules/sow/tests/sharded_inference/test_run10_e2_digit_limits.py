"""Exact route: a degenerate run of digits must not crash the integer parsing (limit: 4300 digits)."""
import copy

from test_si_exact_counting import EC, SPEC, OBJECTIVE, Script, _counter, _notes

HUGE = '9' * 5000


def test_prose_with_a_huge_digit_run_is_rejected_not_raised():
    assert EC.prose_numbers_ok('There are ' + HUGE + ' records', {'matched': 3}, 'count') is False


def test_an_objective_with_a_huge_digit_run_does_not_raise():
    assert EC.prose_numbers_ok('3 records', {'matched': 3}, 'count the ' + HUGE) is True


def test_fit_check_refuses_a_huge_count_target_without_raising():
    spec = {'pattern': 'Log', 'fields': {'level': 'int'},
            'aggregates': [{'op': 'count_where', 'field': 'level', 'cmp': '==', 'value': 3}]}
    issues = EC.objective_fit_issues('How many level ' + HUGE + ' lines?', spec)
    assert any('no matching filtered count' in issue for issue in issues)


def test_a_looping_model_answer_falls_back_to_the_table(tmp_path):
    text, _ = _notes(40)
    loop = 'The count is ' + HUGE + '.'
    port = Script(copy.deepcopy(SPEC), {'ok': True}, loop, loop, loop)
    outcome = _counter(port, tmp_path).run(OBJECTIVE, text)
    assert outcome.answer is not None and HUGE not in outcome.answer
    assert outcome.telemetry['prose_from_model'] is False
    assert 'Computed by the product over' in outcome.answer
