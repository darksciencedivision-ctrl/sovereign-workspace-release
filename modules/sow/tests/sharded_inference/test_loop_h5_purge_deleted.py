"""Deleted chat purge is explicit, age limited, dry by default and hash chained."""
import json
import sqlite3

import pytest

from test_si_retention_h6 import _setup, clean_env, SA
from sovereign_product import store as store_module


def prepare(tmp_path, monkeypatch):
    root, paths, store, live = _setup(tmp_path)
    monkeypatch.setattr(store_module, 'utc_now', lambda: '2000-01-01T00:00:00Z')
    old = store.create_session()['session_id']
    store.append_message(old, 'user', 'synthetic old message')
    store.delete_session(old)
    monkeypatch.setattr(store_module, 'utc_now', lambda: '2099-01-01T00:00:00Z')
    recent = store.create_session()['session_id']
    store.delete_session(recent)
    return root, paths, store, live, old, recent


def test_dry_run_changes_no_rows_or_events(clean_env, tmp_path, monkeypatch):
    root, paths, store, live, old, recent = prepare(tmp_path, monkeypatch)
    before = paths.db_path.read_bytes()
    report = SA.purge_deleted(root, older_than_days=30)
    assert report['applied'] is False and report['would_purge_sessions'] == [old]
    assert paths.db_path.read_bytes() == before
    assert len(store.list_sessions(include_deleted=True)) == 3


def test_apply_removes_only_old_deleted_chat_and_preserves_chain(clean_env, tmp_path, monkeypatch):
    root, paths, store, live, old, recent = prepare(tmp_path, monkeypatch)
    report = SA.purge_deleted(root, older_than_days=30, apply=True)
    assert report['purged'] == {'sessions': 1, 'jobs': 0}
    assert {s['session_id'] for s in store.list_sessions(include_deleted=True)} == {live, recent}
    with sqlite3.connect(paths.db_path) as db:
        assert db.execute('SELECT count(*) FROM messages WHERE session_id=?', (old,)).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM event_log WHERE action='retention_purge' AND entity_id=?", (old,)).fetchone()[0] == 1
    assert store.verify_event_chain()['ok']


def test_cli_defaults_to_dry_run(clean_env, tmp_path, monkeypatch, capsys):
    root, paths, store, live, old, recent = prepare(tmp_path, monkeypatch)
    assert SA.main(['--root', str(root), 'purge-deleted', '--older-than-days', '30']) == 0
    assert json.loads(capsys.readouterr().out)['applied'] is False
    assert len(store.list_sessions(include_deleted=True)) == 3


def test_negative_age_refused(clean_env, tmp_path):
    with pytest.raises(SA.StateAdminError, match='negative'):
        SA.purge_deleted(tmp_path, older_than_days=-1)
