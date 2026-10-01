"""Completed messages remain visible when their jobs exceed the newest-job window."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product.server import ProductService
from sovereign_product.store import NotFound
from sovereign_product.store import SovereignStore


class FakeStore:
    def __init__(self, jobs, messages):
        self.jobs = jobs
        self.messages = messages
        self.looked_up = []

    def list_jobs(self, *, session_id, limit):
        assert session_id == 'session_test'
        return list(reversed(self.jobs))[:limit]

    def list_messages(self, session_id):
        assert session_id == 'session_test'
        return self.messages

    def get_job(self, job_id):
        self.looked_up.append(job_id)
        for job in self.jobs:
            if job['job_id'] == job_id:
                return job
        raise NotFound(job_id)


class Service:
    public_session = ProductService.public_session

    def __init__(self, store):
        self.store = store

    def public_message(self, message, **kwargs):
        return {'id': message['message_id']}

    def public_job(self, job):
        return {'job_id': job['job_id']}


SESSION = {'session_id': 'session_test', 'title': 'Synthetic',
           'created_at': 't0', 'updated_at': 't1',
           'active_model_profile': 'default', 'orchestration_mode': 'default'}


def completed_job(index, session_id='session_test'):
    return {'job_id': f'job_{index:04}', 'session_id': session_id,
            'status': 'completed', 'output_message_id': f'message_{index:04}'}


def completed_message(index):
    return {'message_id': f'message_{index:04}', 'session_id': 'session_test',
            'job_id': f'job_{index:04}', 'role': 'sovereign'}


def test_oldest_completed_answer_is_not_hidden_after_five_hundred_jobs():
    jobs = [completed_job(i) for i in range(501)]
    messages = [completed_message(i) for i in range(501)]
    store = FakeStore(jobs, messages)
    result = Service(store).public_session(SESSION)
    assert len(result['messages']) == 501
    assert result['messages'][0]['id'] == 'message_0000'
    assert store.looked_up == ['job_0000']


def test_missing_window_job_from_other_session_does_not_attach():
    jobs = [completed_job(i) for i in range(1, 501)]
    jobs.insert(0, completed_job(0, session_id='other_session'))
    store = FakeStore(jobs, [completed_message(0)])
    result = Service(store).public_session(SESSION)
    assert result['messages'] == []


def test_message_window_keeps_newest_messages_in_chronological_order(tmp_path):
    store = SovereignStore(tmp_path / 'state.db')
    session = store.create_session()
    for index in range(2001):
        store.append_message(session['session_id'], 'user', f'turn {index}')
    messages = store.list_messages(session['session_id'])
    assert len(messages) == 2000
    assert messages[0]['content'] == 'turn 1'
    assert messages[-1]['content'] == 'turn 2000'
