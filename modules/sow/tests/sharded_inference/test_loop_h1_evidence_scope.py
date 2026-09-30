"""Only inert evidence/research artifacts are downloadable from the evidence API."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product.paths import ProductPaths
from sovereign_product.server import create_app


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / 'install'
    state = tmp_path / 'state'
    root.mkdir(); state.mkdir()
    paths = ProductPaths(root, state, state / 'sovereign.db', state / 'evidence')
    return paths, create_app(service=SimpleNamespace(paths=paths)).test_client()


@pytest.mark.parametrize('relative', ['sovereign.db', 'config.json', 'llamacpp_supervisor/api_key',
                                     'freetoken_supervisor/api_key', 'evidence/payload.html',
                                     'evidence/program.exe'])
def test_non_evidence_or_active_file_is_refused(setup, relative):
    paths, client = setup
    target = paths.state_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'private')
    response = client.get('/v1/evidence', query_string={'pointer': 'sovereign-state://' + relative})
    assert response.status_code in (400, 404)
    assert b'private' not in response.data


@pytest.mark.parametrize('relative', ['evidence/run/result.json', 'research/run/report.md',
                                     'evidence/log.txt', 'evidence/table.csv'])
@pytest.mark.parametrize('prefix', ['sovereign-state://', 'sovereign://runtime/'])
def test_ui_pointer_shapes_serve_inert_artifacts_with_sandbox(setup, relative, prefix):
    paths, client = setup
    target = paths.state_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'evidence body')
    response = client.get('/v1/evidence', query_string={'pointer': prefix + relative})
    assert response.status_code == 200
    assert response.data == b'evidence body'
    assert response.headers['Content-Security-Policy'] == "sandbox; default-src 'none'"
    assert response.headers['X-Content-Type-Options'] == 'nosniff'


def test_install_file_is_not_evidence(setup):
    paths, client = setup
    (paths.root / 'internal.json').write_bytes(b'private')
    response = client.get('/v1/evidence', query_string={'pointer': 'sovereign://internal.json'})
    assert response.status_code == 404


def test_unknown_mime_of_allowed_text_extension_is_attachment(setup, monkeypatch):
    paths, client = setup
    (paths.evidence_dir).mkdir()
    (paths.evidence_dir / 'notes.log').write_bytes(b'plain log')
    monkeypatch.setattr('sovereign_product.server.mimetypes.guess_type', lambda name: (None, None))
    response = client.get('/v1/evidence', query_string={'pointer': 'sovereign-state://evidence/notes.log'})
    assert response.status_code == 200
    assert response.headers['Content-Disposition'].startswith('attachment;')
