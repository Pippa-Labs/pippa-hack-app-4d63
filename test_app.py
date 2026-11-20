from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

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
    assert result['route_verified']
    direct = parse_qs(urlparse(result['direct_map_url']).query)
    scenic = parse_qs(urlparse(result['scenic_map_url']).query)
    assert direct['travelmode'] == ['walking']
    assert scenic['waypoints'] == ['51.5,-0.1']


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
    result = call(start_place='A & Co', destination='B', available_minutes=40)
    assert not result['route_verified'] and not result['scenic_found']
    assert not result['calories_estimated']
    assert 'lookup failed' in result['note']
    query = parse_qs(urlparse(result['direct_map_url']).query)
    assert query['origin'] == ['A & Co'] and query['destination'] == ['B']
    assert query['travelmode'] == ['walking']


def test_invalid_values_are_rejected(services):
    with pytest.raises(app.MissingDetails):
        call(start_place='A', destination='B', available_minutes=40, weight_kg=-5)


def test_sights_fallback_only_uses_nearby_mapped_museums(monkeypatch):
    def fake_fetch(url, params, timeout=2):
        if 'overpass' in url:
            raise TimeoutError()
        assert params['osm_tag'] == 'tourism:museum'
        return {'features': [
            {'properties': {'name': 'Museum Tavern', 'osm_key': 'amenity', 'osm_value': 'pub'},
             'geometry': {'coordinates': [-0.1, 51.5]}},
            {'properties': {'name': 'Far Museum', 'osm_key': 'tourism', 'osm_value': 'museum'},
             'geometry': {'coordinates': [-0.5, 51.5]}},
            {'properties': {'name': 'Nearby Museum', 'osm_key': 'tourism', 'osm_value': 'museum'},
             'geometry': {'coordinates': [-0.101, 51.5]}},
        ]}
    monkeypatch.setattr(app, '_fetch', fake_fetch)
    place = {'lat': 51.5, 'lon': -0.1}
    assert [s['name'] for s in app._sights(place, place)] == ['Nearby Museum']


def test_sights_propagates_outage_when_all_sources_fail(monkeypatch):
    def fail(*args, **kwargs): raise TimeoutError()
    monkeypatch.setattr(app, '_fetch', fail)
    with pytest.raises(TimeoutError):
        app._sights({'lat': 51.5, 'lon': -0.1}, {'lat': 51.5, 'lon': -0.1})


@pytest.mark.parametrize('outcome, expected_kind', [
    ('places.restaurants', 'restaurant'), ('places.gyms', 'gym'),
])
def test_venue_outcomes_include_only_supplied_results(monkeypatch, outcome, expected_kind):
    def fake_find(location, kind, geocode, fetch):
        assert location == 'Museum' and kind == expected_kind
        return {'location': 'Museum, London', 'status': 'found',
                'places': [{'name': 'Example Venue', 'distance_km': 0.2,
                            'cuisine': '', 'map_url': 'https://www.google.com/maps/search/?api=1'}],
                'map_url': 'https://www.google.com/maps/search/?api=1',
                'note': 'Distance is straight-line; check details.'}
    monkeypatch.setattr(app.places, 'find_places', fake_find)
    result = LocalRunner(app.App()).call(outcome, {'location': 'Museum'}, granted_secrets={}, now=NOW, request_id='test').result.data
    assert result['status'] == 'found' and 'Example Venue' in result['venues']
    assert '0.20 km straight-line' in result['venues'] and result['map_url'].startswith('https://www.google.com/maps/')


def test_venue_service_failure_does_not_invent_results(monkeypatch):
    monkeypatch.setattr(app.places, 'find_places', lambda *args: {
        'location': 'London', 'status': 'unavailable', 'places': [],
        'map_url': 'https://www.google.com/maps/search/?api=1', 'note': 'Could not check venues.'})
    result = LocalRunner(app.App()).call('places.restaurants', {'location': 'London'}, granted_secrets={}, now=NOW, request_id='test').result.data
    assert result['status'] == 'unavailable' and result['venues'] == ''


def test_venue_requires_location():
    with pytest.raises(app.MissingLocation):
        LocalRunner(app.App()).call('places.gyms', {}, granted_secrets={}, now=NOW, request_id='test')


def test_bmi_outcome_calculates_from_user_measurements():
    result = LocalRunner(app.App()).call('body.bmi', {'height_cm': 170, 'weight_kg': 60}, granted_secrets={}, now=NOW, request_id='test').result.data
    assert result['bmi'] == 20.8
    assert 'not a diagnosis' in result['note'] and 'not saved' in result['note']


def test_bmi_outcome_rejects_missing_measurements():
    with pytest.raises(app.InvalidMeasurements):
        LocalRunner(app.App()).call('body.bmi', {'height_cm': 170}, granted_secrets={}, now=NOW, request_id='test')
