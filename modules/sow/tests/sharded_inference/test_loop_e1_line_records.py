"""Recorded log/table exact objectives need line-shape hints and compound counts."""
import json
from pathlib import Path
import sys

SOV_ROOT = Path(__file__).resolve().parents[4] / 'modules' / 'sovereign'
sys.path.insert(0, str(SOV_ROOT))
from sovereign_product.exact_counting import ExactCounter, make_sample, _spec_prompt, objective_fit_issues
from sovereign_product.exact_worker import execute, parse_spec, SpecError

import pytest

# The recorded 5000-line log and 3000-row table live in the operator's workbench, next to the
# worktree, not in the repository: a checkout without them (the release worktree, a clean room)
# must still collect and pass. test_run10_e1_self_contained.py repeats the checks on generated data.
BENCH = Path(__file__).resolve().parents[5]
INPUTS = BENCH / 'harness' / 'state' / 'sovereign' / 'long_inputs'
HAVE_RECORDED = ((INPUTS / 'h4-service-log.txt').is_file() and (INPUTS / 'h4-orders.csv').is_file()
                 and (BENCH / 'harness' / 'h4-truth.json').is_file())
TRUTH = (json.loads((BENCH / 'harness' / 'h4-truth.json').read_text(encoding='utf-8'))
         if HAVE_RECORDED else {})
recorded = pytest.mark.skipif(not HAVE_RECORDED, reason='recorded h4 inputs live in the workbench')
LOG_OBJECTIVE = ('How many ERROR lines are there in total, and how many of them come '
                 'from the db component?')
TABLE_OBJECTIVE = ('Using only the orders, how many orders have status returned, what '
                   'is the total of all amounts, and what is the largest amount and '
                   'how many orders reach it?')
LOG_SPEC = {'applicable': True,
            'pattern': (r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} '
                        r'(?P<level>[A-Z]+) (?P<component>[a-z]+): '
                        r'request handled in (?P<ms>\d+) ms$'),
            'flags': 'm', 'fields': {'level': 'str', 'component': 'str', 'ms': 'int'},
            'aggregates': [
                {'op': 'count_where', 'field': 'level', 'cmp': '==', 'value': 'ERROR'},
                {'op': 'count_where_all', 'where': [
                    {'field': 'level', 'cmp': '==', 'value': 'ERROR'},
                    {'field': 'component', 'cmp': '==', 'value': 'db'}]}]}
TABLE_SPEC = {'applicable': True,
              'pattern': r'^(?P<order_id>\d+),(?P<status>[a-z]+),(?P<amount>\d+)$',
              'flags': 'm', 'fields': {'order_id': 'int', 'status': 'str', 'amount': 'int'},
              'aggregates': [
                  {'op': 'count_where', 'field': 'status', 'cmp': '==', 'value': 'returned'},
                  {'op': 'sum', 'field': 'amount'}, {'op': 'max', 'field': 'amount'}]}


@recorded
def test_recorded_log_objective_computes_both_counts():
    text = (INPUTS / 'h4-service-log.txt').read_text(encoding='utf-8')
    assert objective_fit_issues(LOG_OBJECTIVE, LOG_SPEC) == []
    result = execute(text, parse_spec(LOG_SPEC))
    assert result['matched'] == 5000
    assert result['unmatched_anchor_mentions'] == 0
    assert [a['result'] for a in result['aggregates']] == [
        TRUTH['log']['errors'], TRUTH['log']['errors_db']]


@recorded
def test_recorded_table_objective_computes_counts_total_and_ties():
    text = (INPUTS / 'h4-orders.csv').read_text(encoding='utf-8')
    assert objective_fit_issues(TABLE_OBJECTIVE, TABLE_SPEC) == []
    result = execute(text, parse_spec(TABLE_SPEC))
    assert result['matched'] == 3000
    assert result['unmatched_anchor_mentions'] == 1
    count, total, maximum = result['aggregates']
    assert count['result'] == TRUTH['table']['returned']
    assert total['result'] == TRUTH['table']['total_amount']
    assert maximum['result'] == TRUTH['table']['max_amount']
    assert maximum['attained_by'] == TRUTH['table']['max_ties']


@recorded
def test_prompt_describes_timestamp_or_csv_line_records():
    log = (INPUTS / 'h4-service-log.txt').read_text(encoding='utf-8')
    table = (INPUTS / 'h4-orders.csv').read_text(encoding='utf-8')
    log_prompt = _spec_prompt(LOG_OBJECTIVE, make_sample(log), len(log))
    table_prompt = _spec_prompt(TABLE_OBJECTIVE, make_sample(table), len(table))
    assert 'leading timestamp' in log_prompt and 'flags": "m"' in log_prompt
    assert 'comma-separated' in table_prompt and 'flags": "m"' in table_prompt
    assert 'count_where_all' in log_prompt


def test_compound_count_refuses_empty_or_invalid_conditions():
    for where in ([], [{'field': 'missing', 'cmp': '==', 'value': 'db'}],
                  [{'field': 'level', 'cmp': '<', 'value': 'ERROR'}]):
        bad = {**LOG_SPEC, 'aggregates': [{'op': 'count_where_all', 'where': where}]}
        try:
            parse_spec(bad)
        except SpecError:
            continue
        raise AssertionError(f'unsafe compound filter accepted: {where}')


class RecordedSpecPort:
    def __init__(self, spec):
        self.spec = spec
        self.prompts = []

    def generate(self, *, system, prompt, max_tokens, should_stop):
        self.prompts.append(prompt)
        if 'Write the extraction spec' in prompt:
            return json.dumps(self.spec)
        if 'Does this extract the records' in prompt:
            return '{"ok": true}'
        if 'List every part of the objective NOT covered' in prompt:
            return '{"uncovered": []}'
        return 'The computed results follow.'


@recorded
def test_full_offline_route_uses_recorded_log_and_table_specs(tmp_path):
    for name, objective, spec, numbers in (
        ('h4-service-log.txt', LOG_OBJECTIVE, LOG_SPEC,
         (TRUTH['log']['errors'], TRUTH['log']['errors_db'])),
        ('h4-orders.csv', TABLE_OBJECTIVE, TABLE_SPEC,
         (TRUTH['table']['returned'], TRUTH['table']['total_amount'],
          TRUTH['table']['max_amount'], TRUTH['table']['max_ties'])),
    ):
        port = RecordedSpecPort(spec)
        material = (INPUTS / name).read_text(encoding='utf-8')
        result = ExactCounter(port, tmp_path / name, max_output_tokens=2048).run(objective, material)
        assert result.answer is not None, result.note
        assert 'Computed by the product' in result.answer
        assert all(str(number) in result.answer for number in numbers)
        assert len(port.prompts) == 4
        assert 'Observed line shape' in port.prompts[0]
