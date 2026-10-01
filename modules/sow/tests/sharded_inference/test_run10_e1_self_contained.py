"""The E-1 line-record checks on generated data, so they run in any checkout.

test_loop_e1_line_records.py checks the operator's recorded 5000-line log and 3000-row table, which
live outside the repository. These tests build inputs of the same shape and compare the engine with
counts taken directly from the generated rows.
"""
import random

from test_loop_e1_line_records import (  # noqa: F401
    LOG_OBJECTIVE, LOG_SPEC, TABLE_OBJECTIVE, TABLE_SPEC, RecordedSpecPort, ExactCounter,
    execute, make_sample, objective_fit_issues, parse_spec, _spec_prompt)

LEVELS = ('INFO', 'WARN', 'ERROR', 'INFO', 'WARN')
COMPONENTS = ('db', 'api', 'auth', 'queue', 'cache')
STATUSES = ('pending', 'shipped', 'returned', 'cancelled', 'paid')


def make_log(lines=5000, seed=3):
    rng = random.Random(seed)
    rows = [(rng.choice(LEVELS), rng.choice(COMPONENTS), rng.randint(1, 999)) for _ in range(lines)]
    text = ''.join(
        f'{2019 + i % 7}-{1 + i % 12:02d}-{1 + i % 28:02d} {i % 24:02d}:{i % 60:02d}:{(i * 7) % 60:02d} '
        f'{level} {component}: request handled in {ms} ms\n'
        for i, (level, component, ms) in enumerate(rows))
    return text, rows


def make_table(rows=3000, seed=5):
    rng = random.Random(seed)
    data = [(1000 + i, rng.choice(STATUSES), rng.choice([50, 120, 399, 500, 500, 250])) for i in range(rows)]
    return 'order_id,status,amount\n' + ''.join(f'{o},{s},{a}\n' for o, s, a in data), data


def test_generated_log_objective_computes_both_counts():
    text, rows = make_log()
    assert objective_fit_issues(LOG_OBJECTIVE, LOG_SPEC) == []
    result = execute(text, parse_spec(LOG_SPEC))
    assert result['matched'] == len(rows) and result['unmatched_anchor_mentions'] == 0
    errors = sum(1 for level, _c, _ms in rows if level == 'ERROR')
    errors_db = sum(1 for level, component, _ms in rows if level == 'ERROR' and component == 'db')
    assert errors_db and errors > errors_db
    assert [a['result'] for a in result['aggregates']] == [errors, errors_db]


def test_generated_table_objective_computes_counts_total_and_ties():
    text, data = make_table()
    assert objective_fit_issues(TABLE_OBJECTIVE, TABLE_SPEC) == []
    result = execute(text, parse_spec(TABLE_SPEC))
    assert result['matched'] == len(data) and result['unmatched_anchor_mentions'] == 1  # the header
    count, total, maximum = result['aggregates']
    assert count['result'] == sum(1 for _o, status, _a in data if status == 'returned')
    assert total['result'] == sum(amount for _o, _s, amount in data)
    assert maximum['result'] == max(amount for _o, _s, amount in data)
    assert maximum['attained_by'] == sum(1 for _o, _s, amount in data if amount == maximum['result'])


def test_generated_inputs_get_the_line_shape_hint():
    log, _ = make_log()
    table, _ = make_table()
    log_prompt = _spec_prompt(LOG_OBJECTIVE, make_sample(log), len(log))
    table_prompt = _spec_prompt(TABLE_OBJECTIVE, make_sample(table), len(table))
    assert 'leading timestamp' in log_prompt and 'flags": "m"' in log_prompt
    assert 'comma-separated' in table_prompt and 'flags": "m"' in table_prompt
    assert 'count_where_all' in log_prompt


def test_full_offline_route_on_generated_log_and_table(tmp_path):
    log, log_rows = make_log()
    table, table_rows = make_table()
    errors = sum(1 for level, _c, _ms in log_rows if level == 'ERROR')
    errors_db = sum(1 for level, c, _ms in log_rows if level == 'ERROR' and c == 'db')
    returned = sum(1 for _o, status, _a in table_rows if status == 'returned')
    total = sum(amount for _o, _s, amount in table_rows)
    for name, material, objective, spec, numbers in (
            ('log', log, LOG_OBJECTIVE, LOG_SPEC, (errors, errors_db)),
            ('table', table, TABLE_OBJECTIVE, TABLE_SPEC, (returned, total, 500))):
        port = RecordedSpecPort(spec)
        result = ExactCounter(port, tmp_path / name, max_output_tokens=2048).run(objective, material)
        assert result.answer is not None, result.note
        assert 'Computed by the product' in result.answer
        assert all(str(number) in result.answer for number in numbers)
        assert len(port.prompts) == 4 and 'Observed line shape' in port.prompts[0]
