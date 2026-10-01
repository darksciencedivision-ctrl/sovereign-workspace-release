"""Health caches only successful integrity checks, using a monotonic clock."""
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product.server import create_app


def service(check):
    return SimpleNamespace(
        store=SimpleNamespace(quick_check=check), _manifest=lambda: {},
        root=Path('.'), deep_executor=lambda: None, workers_ready=lambda: True,
        _self_state=lambda: {}, research_executor=object(), research_unavailable_reason=None,
        qualification=lambda: {'verdict': 'accepted', 'reasons': []}, _workers=[],
        long_route_ready=lambda: True,
        long_models=lambda: {'models': [{'status': 'ready'}]},
        long_active_job=lambda: None,
        role_models=lambda: {'models': [], 'status': 'ready', 'detail': None})


def test_success_checked_once_per_sixty_seconds():
    clock = [0.0]
    calls = []
    client = create_app(service=service(lambda: calls.append(1)), health_clock=lambda: clock[0]).test_client()
    assert client.get('/v1/health').get_json()['durable_store']
    clock[0] = 59.99
    assert client.get('/v1/health').get_json()['durable_store']
    assert len(calls) == 1
    clock[0] = 60.0
    assert client.get('/v1/health').get_json()['durable_store']
    assert len(calls) == 2


def test_failure_flips_health_and_is_not_cached_as_healthy():
    clock = [0.0]
    calls = []
    def check():
        calls.append(1)
        if len(calls) in (2, 3):
            raise RuntimeError('injected corrupt store')
    client = create_app(service=service(check), health_clock=lambda: clock[0]).test_client()
    assert client.get('/v1/health').get_json()['durable_store']
    clock[0] = 60.0
    assert client.get('/v1/health').get_json()['durable_store'] is False
    assert client.get('/v1/health').get_json()['durable_store'] is False
    assert client.get('/v1/health').get_json()['durable_store'] is True
    assert len(calls) == 4


def test_cache_is_per_application_not_shared_between_databases():
    first = create_app(service=service(lambda: None)).test_client()
    second = create_app(service=service(lambda: (_ for _ in ()).throw(RuntimeError('bad')))).test_client()
    assert first.get('/v1/health').get_json()['durable_store']
    assert second.get('/v1/health').get_json()['durable_store'] is False
