from urllib.parse import parse_qs, urlparse

import places


def geocode(_):
    return {'name': 'Museum, London', 'lat': 51.5, 'lon': -0.1}


def test_nearby_restaurants_sorted_and_limited():
    def fetch(url, params, timeout):
        assert '["amenity"="restaurant"]' in params['data']
        return {'elements': [
            {'lat': 51.502, 'lon': -0.1, 'tags': {'name': 'Second', 'cuisine': 'japanese'}},
            {'center': {'lat': 51.501, 'lon': -0.1}, 'tags': {'name': 'First'}},
            {'lat': 52.0, 'lon': -0.1, 'tags': {'name': 'Too Far'}},
            {'lat': 51.5, 'lon': -0.1, 'tags': {}},
        ]}
    result = places.find_places('Museum', 'restaurant', geocode, fetch)
    assert result['status'] == 'found'
    assert [p['name'] for p in result['places']] == ['First', 'Second']
    assert result['places'][1]['cuisine'] == 'japanese'
    assert 'straight-line' in result['note'] and 'not verified' in result['note']
    assert urlparse(result['places'][0]['map_url']).netloc == 'www.google.com'


def test_gym_empty_is_not_a_failure():
    def fetch(url, params, timeout):
        assert '["leisure"="fitness_centre"]' in params['data']
        return {'elements': []}
    result = places.find_places('A & B', 'gym', geocode, fetch)
    assert result['status'] == 'empty' and not result['places']
    assert parse_qs(urlparse(result['map_url']).query)['query'] == ['gyms near A & B']


def test_service_failure_offers_search_without_fabricating_venues():
    def fail(*args, **kwargs):
        raise TimeoutError()
    result = places.find_places('London', 'restaurant', geocode, fail)
    assert result['status'] == 'unavailable' and result['places'] == []
    assert result['map_url'].startswith('https://www.google.com/maps/search/')
    assert 'could not be checked' in result['note']
