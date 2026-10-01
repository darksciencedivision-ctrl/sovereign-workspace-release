"""Exact route: group-count rankings ("which status is the most common") and CRLF line records."""
import pytest

from test_si_exact_counting import EC, EW, Script, _counter

TICKET_SPEC = {
    'applicable': True, 'pattern': r'^Ticket (?P<status>[a-z]+) (?P<owner>[a-z]+)$', 'flags': 'm',
    'fields': {'status': 'str', 'owner': 'str'},
    'aggregates': [{'op': 'group_count', 'field': 'status'}]}


def _fit(objective, spec=TICKET_SPEC):
    return EC.objective_fit_issues(objective, spec)


@pytest.mark.parametrize('objective', [
    'Which status is the most common?',
    'What is the most common status?',
    'Which status has the most records?',
    'Which status appears most often in the log?',
    'Which status is the most common, and how many records have it?',
])
def test_group_count_ranking_of_a_grouped_field_is_eligible(objective):
    assert _fit(objective) == []


@pytest.mark.parametrize('objective', [
    'Which status is the least common?',
    'Which owner has the most records?',                    # owner is not grouped
    'Which owner is the most common?',
    'Which status is the most common among closed tickets?',  # a filtered group is not computed
    'Which status logs the most errors?',                   # "errors" needs a filter
    'Which status is the most common for owner bob?',
])
def test_group_count_ranking_that_the_table_cannot_answer_is_refused(objective):
    assert _fit(objective) != []


def test_group_count_ranking_needs_a_group_count_aggregate():
    spec = dict(TICKET_SPEC, aggregates=[{'op': 'count'}])
    assert _fit('Which status is the most common?', spec) != []


def test_the_spec_prompt_names_the_group_count_ranking():
    assert 'most common' in EC.SPEC_FORMAT and 'group_count' in EC.SPEC_FORMAT.split('most common')[1][:200]


def test_a_group_ranking_runs_the_whole_exact_route(tmp_path):
    rows = ['Ticket open ann'] * 5 + ['Ticket closed bob'] * 9 + ['Ticket hold cy'] * 2
    text = '\n'.join(rows) + '\n'
    port = Script(TICKET_SPEC, {'ok': True}, 'The most common status is closed with 9 records.')
    outcome = _counter(port, tmp_path).run('Which status is the most common?', text)
    assert outcome.answer.startswith('The most common status is closed with 9 records.')
    assert 'closed: 9, open: 5, hold: 2' in outcome.answer


def test_crlf_line_records_are_counted():
    spec = EW.parse_spec(TICKET_SPEC)
    rows = ['Ticket open ann', 'Ticket closed bob', 'Ticket closed cy']
    for newline in ('\n', '\r\n'):
        result = EW.execute(newline.join(rows) + newline, spec)
        assert result['matched'] == 3 and result['unmatched_anchor_mentions'] == 0
        assert result['aggregates'][0]['top'][0] == {'value': 'closed', 'count': 2}


def test_crlf_records_that_start_with_a_varying_value_are_counted():
    spec = EW.parse_spec({
        'applicable': True, 'pattern': r'^(?P<level>[A-Z]+) (?P<ms>\d+)$', 'flags': 'm',
        'fields': {'level': 'str', 'ms': 'int'},
        'aggregates': [{'op': 'count'}, {'op': 'sum', 'field': 'ms'}]})
    for newline in ('\n', '\r\n'):
        result = EW.execute(newline.join(['ERROR 5', 'INFO 7', '', 'ERROR 9']) + newline, spec)
        assert [a['result'] for a in result['aggregates']] == [3, 21]
        assert result['unmatched_anchor_mentions'] == 0

