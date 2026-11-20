"""Find nearby venues from OpenStreetMap, with a map-search fallback."""
from math import asin, cos, radians, sin, sqrt
from urllib.parse import urlencode


def _distance_km(a, b):
    lat1, lat2 = radians(a['lat']), radians(b['lat'])
    delta_lat = lat2 - lat1
    delta_lon = radians(b['lon'] - a['lon'])
    h = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 6371.0 * 2 * asin(min(1, sqrt(h)))


def _map_search(text):
    return 'https://www.google.com/maps/search/?' + urlencode({'api': '1', 'query': text})


def find_places(location, kind, geocode, fetch):
    """Return named OSM venues, or a truthful fallback search link.

    geocode(text) returns a dict containing lat, lon and name; fetch(url,
    params, timeout=...) returns decoded JSON. Distance is straight-line.
    """
    if kind not in ('restaurant', 'gym'):
        raise ValueError('kind must be restaurant or gym')
    location = str(location or '').strip()
    if not location:
        raise ValueError('location is required')
    subject = 'restaurants' if kind == 'restaurant' else 'gyms'
    map_url = _map_search(f'{subject} near {location}')
    try:
        centre = geocode(location)
        lat, lon = float(centre['lat']), float(centre['lon'])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('invalid coordinates')
    except Exception:
        return {'status': 'unavailable', 'location': location, 'places': [], 'map_url': map_url,
                'note': 'Location lookup failed; use the map search and check its results yourself.'}

    tag = 'amenity' if kind == 'restaurant' else 'leisure'
    value = 'restaurant' if kind == 'restaurant' else 'fitness_centre'
    query = f'[out:json][timeout:5];nwr["{tag}"="{value}"]["name"](around:1500,{lat},{lon});out center 40;'
    try:
        data = fetch('https://overpass-api.de/api/interpreter', {'data': query}, timeout=6)
        elements = data['elements']
        if not isinstance(elements, list):
            raise ValueError('invalid response')
    except Exception:
        return {'status': 'unavailable', 'location': centre.get('name', location), 'places': [], 'map_url': map_url,
                'note': 'Nearby venue data could not be checked; use the map search and check its results yourself.'}

    results, seen = [], set()
    for item in elements:
        tags = item.get('tags', {})
        name = str(tags.get('name') or '').strip()
        coord = item if 'lat' in item and 'lon' in item else item.get('center', {})
        try:
            point = {'lat': float(coord['lat']), 'lon': float(coord['lon'])}
            distance = _distance_km({'lat': lat, 'lon': lon}, point)
        except (KeyError, TypeError, ValueError):
            continue
        if not name or not distance <= 1.5:
            continue
        key = (name.casefold(), round(point['lat'], 4), round(point['lon'], 4))
        if key in seen:
            continue
        seen.add(key)
        results.append({'name': name, 'distance_km': round(distance, 2),
                        'map_url': _map_search(f"{name} {point['lat']},{point['lon']}"),
                        'cuisine': str(tags.get('cuisine') or '').replace(';', ', ')})
    results.sort(key=lambda item: item['distance_km'])
    note = ('Distances are approximate straight-line distances, not walking routes. '
            'Open the map and check current opening hours and details. '
            'OpenStreetMap data may be incomplete or outdated. Locations are sent to public mapping services. '
            'Map data © OpenStreetMap contributors.')
    if kind == 'restaurant':
        note += ' Nutrition, menu, dietary suitability and healthiness were not verified.'
    return {'status': 'found' if results else 'empty', 'location': centre.get('name', location),
            'places': results[:3], 'map_url': map_url, 'note': note}
