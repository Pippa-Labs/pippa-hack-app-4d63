from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pippa_agentapp_sdk import AgentAppError, Manifest, Result, load_manifest_file, validate_manifest
import places
import dayflow_profile

MANIFEST_PATH = Path(__file__).with_name('manifest.yaml')

class MissingDetails(AgentAppError):
    user_message = 'Please provide a starting place, a destination, and the minutes available between your plans.'
    retryable = False

class MissingLocation(AgentAppError):
    user_message = 'Please provide the place or address near which you want to search.'
    retryable = False

class InvalidMeasurements(AgentAppError):
    user_message = 'Please provide a valid height in cm and weight in kg.'
    retryable = False

class LookupUnavailable(AgentAppError):
    user_message = 'I could not find a walking route right now. Please check the place names and try again later.'
    retryable = True


def _fetch(url, params, timeout=2):
    request = Request(url + '?' + urlencode(params), headers={'User-Agent': 'DayFlow-hackathon/0.1 (walking route demo)', 'Accept': 'application/json'})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _place(query):
    data = _fetch('https://photon.komoot.io/api/', {'q': query, 'limit': 1})
    features = data.get('features', [])
    if not features:
        raise LookupUnavailable('place not found')
    feature = features[0]
    lon, lat = feature['geometry']['coordinates']
    props = feature['properties']
    label = ', '.join(str(props[k]) for k in ('name', 'housenumber', 'street', 'city', 'state', 'country') if props.get(k))
    return {'lat': lat, 'lon': lon, 'name': label or query}


def _route(points):
    payload = {'locations': [{'lat': p['lat'], 'lon': p['lon']} for p in points], 'costing': 'pedestrian', 'units': 'kilometers'}
    data = _fetch('https://valhalla1.openstreetmap.de/route', {'json': json.dumps(payload, separators=(',', ':'))})
    summary = data['trip']['summary']
    return float(summary['time']) / 60, float(summary['length'])


def _map_link(start, destination, waypoint=None):
    """Google Maps directions use geocoded coordinates where available."""
    def point(value):
        if isinstance(value, dict):
            return f"{value['lat']},{value['lon']}"
        return value
    params = {'api': '1', 'origin': point(start), 'destination': point(destination), 'travelmode': 'walking'}
    if waypoint is not None:
        params['waypoints'] = point(waypoint)
    return 'https://www.google.com/maps/dir/?' + urlencode(params)


def _distance_km(lat1, lon1, lat2, lon2):
    """Straight-line distance, used to keep Photon fallback results local."""
    radians = math.pi / 180
    delta_lat = (lat2 - lat1) * radians
    delta_lon = (lon2 - lon1) * radians
    h = (math.sin(delta_lat / 2) ** 2 + math.cos(lat1 * radians) *
         math.cos(lat2 * radians) * math.sin(delta_lon / 2) ** 2)
    return 12742 * math.asin(min(1, math.sqrt(h)))


def _sights(start, destination):
    lat = (start['lat'] + destination['lat']) / 2
    lon = (start['lon'] + destination['lon']) / 2
    # Search OpenStreetMap near the midpoint; each candidate is routed before
    # being recommended.  The fallback is deliberately bounded and only
    # accepts explicitly mapped museums, not unrelated search results.
    query = f'[out:json][timeout:3];(nwr["tourism"~"^(attraction|viewpoint|museum)$"]["name"](around:1500,{lat},{lon}););out center 12;'
    result = []
    try:
        data = _fetch('https://overpass-api.de/api/interpreter', {'data': query}, timeout=2)
        for item in data.get('elements', []):
            coords = item if 'lat' in item else item.get('center', {})
            name = item.get('tags', {}).get('name')
            if name and 'lat' in coords and 'lon' in coords:
                result.append({'name': name, 'lat': coords['lat'], 'lon': coords['lon']})
    except Exception:
        pass
    if not result:
        data = _fetch('https://photon.komoot.io/api/', {
            'q': 'museum', 'lat': lat, 'lon': lon, 'limit': 20,
            'osm_tag': 'tourism:museum',
        }, timeout=2)
        for feature in data.get('features', []):
            props = feature.get('properties', {})
            coords = feature.get('geometry', {}).get('coordinates', [])
            if (props.get('osm_key') != 'tourism' or props.get('osm_value') != 'museum'
                    or not props.get('name') or len(coords) < 2):
                continue
            try:
                sight_lon, sight_lat = float(coords[0]), float(coords[1])
                if _distance_km(lat, lon, sight_lat, sight_lon) <= 1.5:
                    result.append({'name': props['name'], 'lat': sight_lat, 'lon': sight_lon})
            except (ValueError, TypeError):
                continue
    return sorted(result, key=lambda sight: _distance_km(lat, lon, sight['lat'], sight['lon']))


class App:
    def __init__(self):
        self._manifest = validate_manifest(load_manifest_file(MANIFEST_PATH))

    @property
    def manifest(self) -> Manifest:
        return self._manifest

    def handle(self, call):
        if call.outcome_id == 'body.bmi':
            try:
                result = dayflow_profile.calculate_bmi(call.inputs.get('height_cm'), call.inputs.get('weight_kg'))
            except ValueError as exc:
                raise InvalidMeasurements('invalid measurements') from exc
            return Result(data=result, narrative=f"BMI: {result['bmi']}. {result['note']}")
        if call.outcome_id in ('places.restaurants', 'places.gyms'):
            location = (call.inputs.get('location') or '').strip()
            if not location:
                raise MissingLocation('missing location')
            kind = 'restaurant' if call.outcome_id == 'places.restaurants' else 'gym'
            found = places.find_places(location, kind, _place, _fetch)
            venue_lines = []
            for venue in found['places']:
                cuisine = f", cuisine: {venue['cuisine']}" if venue['cuisine'] else ''
                venue_lines.append(f"{venue['name']} ({venue['distance_km']:.2f} km straight-line{cuisine}): {venue['map_url']}")
            venue_text = '\n'.join(venue_lines)
            subject = 'restaurants' if kind == 'restaurant' else 'gyms'
            narrative = (f"Nearby {subject} around {found['location']}: {venue_text or 'No verified venues to list.'} "
                         f"Map search: {found['map_url']}. {found['note']}")
            return Result(data={
                'location': found['location'], 'status': found['status'],
                'venues': venue_text, 'map_url': found['map_url'], 'note': found['note'],
            }, narrative=narrative)
        if call.outcome_id != 'walk.plan':
            raise AgentAppError('Unknown outcome')
        inputs = call.inputs
        start_text = (inputs.get('start_place') or '').strip()
        end_text = (inputs.get('destination') or '').strip()
        try:
            available = float(inputs['available_minutes'])
            buffer = float(inputs.get('buffer_minutes') if inputs.get('buffer_minutes') is not None else 10)
            extra_limit = float(inputs.get('max_extra_minutes') if inputs.get('max_extra_minutes') is not None else 10)
            weight = float(inputs['weight_kg']) if inputs.get('weight_kg') is not None else None
            if not all(math.isfinite(x) for x in (available, buffer, extra_limit)) or available <= 0 or buffer < 0 or extra_limit < 0 or (weight is not None and (not math.isfinite(weight) or not 20 <= weight <= 300)):
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise MissingDetails('invalid time or weight')
        if not start_text or not end_text:
            raise MissingDetails('missing place')
        walking_time = max(0, available - buffer)
        try:
            start, destination = _place(start_text), _place(end_text)
            direct_min, direct_km = _route([start, destination])
        except Exception as exc:
            # A useful navigation link remains available even if our provider
            # is down; none of its route figures have been verified by DayFlow.
            link = _map_link(start_text, end_text)
            note = ('The route lookup failed, so no route time, distance, scenic stop or calories could be verified. '
                    'Open the walking directions link and check the suggested places yourself. '
                    'Google Maps may resolve names differently and calculates its own route. '
                    'Locations are sent to public mapping services.')
            return Result(data={
                'start_resolved': start_text, 'destination_resolved': end_text,
                'route_verified': False, 'direct_map_url': link, 'scenic_map_url': '',
                'direct_minutes': 0, 'direct_distance_km': 0,
                'available_walking_minutes': round(walking_time, 1), 'fits_schedule': False,
                'scenic_found': False, 'scenic_name': '', 'scenic_minutes': 0,
                'scenic_distance_km': 0, 'extra_minutes': 0,
                'estimated_active_calories_kcal': 0, 'calories_estimated': False, 'note': note,
            }, narrative=f'{note} Walking directions: {link}')
        fits = direct_min <= walking_time
        selected = None
        sight_problem = False
        if fits and extra_limit > 0:
            try:
                sights = _sights(start, destination)
                # Limit external requests and choose the shortest feasible detour.
                for sight in sights[:3]:
                    try:
                        minutes, km = _route([start, sight, destination])
                    except Exception:
                        sight_problem = True
                        continue
                    extra = max(0, minutes - direct_min)
                    if minutes <= walking_time and extra <= extra_limit and (selected is None or minutes < selected[1]):
                        selected = (sight, minutes, km, extra)
            except Exception:
                sight_problem = True
        chosen_minutes = selected[1] if selected else direct_min
        # 3.5 MET is a rough moderate-walking estimate; subtract resting energy.
        calories = round(2.5 * weight * chosen_minutes / 60) if weight is not None else 0
        if not fits:
            note = 'The direct walk does not fit after the buffer; consider another mode of transport.'
        elif selected:
            note = 'This detour fits the stated time and buffer. Check opening times, route safety and accessibility before setting off.'
        elif sight_problem:
            note = 'The direct route fits, but scenic places could not be checked reliably. Check route safety and accessibility before setting off.'
        else:
            note = 'The direct route fits; no checked scenic detour met the time limits. Check route safety and accessibility before setting off.'
        if weight is not None:
            note += ' Active calories estimate the proposed walk, not calories already burned.'
        note += ' Locations are sent to public mapping services. Map data © OpenStreetMap contributors.'
        direct_link = _map_link(start, destination)
        scenic_link = _map_link(start, destination, selected[0]) if selected else ''
        summary = (f"Direct walking route from {start['name']} to {destination['name']}: "
                   f"{direct_km:.2f} km, about {direct_min:.1f} minutes; "
                   f"{walking_time:.1f} minutes available after the {buffer:g}-minute buffer. "
                   f"Direct walking directions: {direct_link}. ")
        if selected:
            summary += (f"Checked scenic stop: {selected[0]['name']}; via this stop "
                        f"{selected[2]:.2f} km, {selected[1]:.1f} minutes, "
                        f"{selected[3]:.1f} extra minutes. Scenic walking directions: {scenic_link}. ")
        else:
            summary += 'No scenic stop was verified; do not suggest or invent one. '
        if weight is not None:
            summary += f'Estimated active calories for the proposed walk: {calories} kcal, not calories already burned. '
        else:
            summary += 'Calories were not estimated because no weight was supplied. '
        note += ' Google Maps calculates its own route, which may differ from the estimate above.'
        return Result(data={
            'start_resolved': start['name'], 'destination_resolved': destination['name'],
            'route_verified': True, 'direct_map_url': direct_link, 'scenic_map_url': scenic_link,
            'direct_minutes': round(direct_min, 1), 'direct_distance_km': round(direct_km, 2),
            'available_walking_minutes': round(walking_time, 1), 'fits_schedule': fits,
            'scenic_found': selected is not None, 'scenic_name': selected[0]['name'] if selected else '',
            'scenic_minutes': round(selected[1], 1) if selected else 0,
            'scenic_distance_km': round(selected[2], 2) if selected else 0,
            'extra_minutes': round(selected[3], 1) if selected else 0,
            'estimated_active_calories_kcal': calories, 'calories_estimated': weight is not None,
            'note': note,
        }, narrative=summary + note)
