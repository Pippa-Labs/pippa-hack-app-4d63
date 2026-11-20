from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pippa_agentapp_sdk import AgentAppError, Manifest, Result, load_manifest_file, validate_manifest

MANIFEST_PATH = Path(__file__).with_name('manifest.yaml')

class MissingDetails(AgentAppError):
    user_message = 'Please provide a starting place, a destination, and the minutes available between your plans.'
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


def _sights(start, destination):
    lat = (start['lat'] + destination['lat']) / 2
    lon = (start['lon'] + destination['lon']) / 2
    # A small, bounded search near the midpoint; routing below decides feasibility.
    query = f'[out:json][timeout:4];(nwr["tourism"~"^(attraction|viewpoint|museum)$"]["name"](around:1500,{lat},{lon}););out center 12;'
    data = _fetch('https://overpass-api.de/api/interpreter', {'data': query}, timeout=3)
    result = []
    for item in data.get('elements', []):
        coords = item if 'lat' in item else item.get('center', {})
        name = item.get('tags', {}).get('name')
        if name and 'lat' in coords and 'lon' in coords:
            result.append({'name': name, 'lat': coords['lat'], 'lon': coords['lon']})
    return result


class App:
    def __init__(self):
        self._manifest = validate_manifest(load_manifest_file(MANIFEST_PATH))

    @property
    def manifest(self) -> Manifest:
        return self._manifest

    def handle(self, call):
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
        try:
            start, destination = _place(start_text), _place(end_text)
            direct_min, direct_km = _route([start, destination])
        except Exception as exc:
            if isinstance(exc, AgentAppError):
                raise
            raise LookupUnavailable('place or route lookup failed') from exc
        walking_time = max(0, available - buffer)
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
        return Result(data={
            'start_resolved': start['name'], 'destination_resolved': destination['name'],
            'direct_minutes': round(direct_min, 1), 'direct_distance_km': round(direct_km, 2),
            'available_walking_minutes': round(walking_time, 1), 'fits_schedule': fits,
            'scenic_found': selected is not None, 'scenic_name': selected[0]['name'] if selected else '',
            'scenic_minutes': round(selected[1], 1) if selected else 0,
            'scenic_distance_km': round(selected[2], 2) if selected else 0,
            'extra_minutes': round(selected[3], 1) if selected else 0,
            'estimated_active_calories_kcal': calories, 'calories_estimated': weight is not None,
            'note': note,
        }, narrative=note)
