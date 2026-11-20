from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pippa_agentapp_sdk import LocalRunner
import app

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)

@pytest.fixture
def services(monkeypatch):
    monkeypatch.setattr(app, '_place', lambda name: {'name': name, 'lat': 51.5, 'lon': -0.1})
    monkeypatch.setattr(app, '_sights', lambda *args: [{'name': 'Garden', 'lat': 51.5, 'lon': -0.1}, {'name': 'Museum', 'lat': 51.5, 'lon': -0.1}])
    def route(points):
        if len(points) == 2: return (20, 1.5)
        return (27, 2.0) if points[1]['name'] == 'Garden' else (35, 2.5)
    monkeypatch.setattr(app, '_route', route)


def call(**inputs):
    return LocalRunner(app.App()).call('walk.plan', inputs, granted_secrets={}, now=NOW, request_id='test').result.data


def test_feasible_detour_and_calories(services):
    result = call(start_place='A', destination='B', available_minutes=40, weight_kg=60)
    assert result['scenic_name'] == 'Garden'
    assert result['extra_minutes'] == 7
    assert result['estimated_active_calories_kcal'] == 68
    assert result['calories_estimated']


def test_buffer_prevents_detour(services):
    result = call(start_place='A', destination='B', available_minutes=35)
    assert result['fits_schedule'] and not result['scenic_found']
    assert not result['calories_estimated']


def test_direct_route_does_not_fit(services):
    result = call(start_place='A', destination='B', available_minutes=25)
    assert not result['fits_schedule']
    assert not result['scenic_found']


def test_scenic_service_failure_keeps_direct_route(services, monkeypatch):
    def fail(*args): raise TimeoutError()
    monkeypatch.setattr(app, '_sights', fail)
    result = call(start_place='A', destination='B', available_minutes=40)
    assert result['fits_schedule'] and not result['scenic_found']
    assert 'could not be checked' in result['note']


def test_route_service_failure_reports_error(services, monkeypatch):
    def fail(*args): raise TimeoutError()
    monkeypatch.setattr(app, '_route', fail)
    with pytest.raises(app.LookupUnavailable):
        call(start_place='A', destination='B', available_minutes=40)


def test_invalid_values_are_rejected(services):
    with pytest.raises(app.MissingDetails):
        call(start_place='A', destination='B', available_minutes=40, weight_kg=-5)
