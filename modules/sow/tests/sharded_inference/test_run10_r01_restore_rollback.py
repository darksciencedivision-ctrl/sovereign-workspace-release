"""A failed restore must leave the prior state home available."""
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product import state_admin


def test_restore_rename_failure_recovers_previous_state(tmp_path, monkeypatch):
    root = tmp_path / 'install'
    root.mkdir()
    (root / 'STATE_LAYOUT.json').write_text('{"state":"external"}', encoding='utf-8')
    home = tmp_path / 'state' / 'sovereign'
    home.mkdir(parents=True)
    (home / 'prior.txt').write_text('operator state', encoding='utf-8')
    archive = tmp_path / 'backup.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('state/new.txt', 'replacement')
    monkeypatch.setattr(state_admin, 'resolve_state_home', lambda _root: home)
    # Use the actual archive digest; the failure under test is the second rename.
    import hashlib
    digest = hashlib.sha256(b'replacement').hexdigest()
    monkeypatch.setattr(state_admin, 'verify', lambda _archive: {
        'files': [{'path': 'new.txt', 'sha256': digest}]
    })
    real_replace = state_admin.os.replace
    calls = []

    def fail_install(source, destination):
        calls.append((Path(source), Path(destination)))
        if len(calls) == 2:
            raise OSError('simulated second rename failure')
        return real_replace(source, destination)

    monkeypatch.setattr(state_admin.os, 'replace', fail_install)
    with pytest.raises(OSError, match='simulated second rename failure'):
        state_admin.restore(root, archive)
    assert (home / 'prior.txt').read_text(encoding='utf-8') == 'operator state'
