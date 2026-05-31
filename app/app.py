"""
Astral Audio — Flask app
Routes: / → form, /start → session setup, /loading → loading page,
        /progress → SSE pipeline stream, /result → serve cached result,
        /rescore → adjust playlist, /api/timezone → lat/lng → tz
"""
import json
import logging
import os
import queue
import shutil
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, Response, stream_with_context, send_file

# load local.env when running locally
load_dotenv('local.env')

# add src/ to path so pipeline modules resolve correctly
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_PATH, '..', 'src'))

from aspects import (PLANET_LIST,
                     get_planet_list, get_transit_aspects,
                     PLANET_DESCRIPTIONS, NATAL_MEANINGS, TRANSIT_MEANINGS)
from horoscope import get_horoscope, get_select_aspects
from library import load_music_library, merge_into_library
from score import build_target_vector, score_tracks, rescore as rescore_tracks, aspect_audio_profile
from model import train_model, predict_target_vector, blend_target_vectors

# optional Spotipy for album art — graceful fallback if not installed / no creds
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    _SPOTIPY_AVAILABLE = True
except ImportError:
    _SPOTIPY_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-please-change')

# ---------------------------------------------------------------------------
# In-memory result cache
# Keyed by a per-session cache_id (uuid stored in the Flask session cookie).
# Stores library_df and target_vector so /rescore never reruns the pipeline.
# ---------------------------------------------------------------------------
_RESULT_CACHE: dict = {}
_MAX_CACHE_ENTRIES = 10


def _cache_set(cache_id: str, data: dict):
    if len(_RESULT_CACHE) >= _MAX_CACHE_ENTRIES:
        oldest = next(iter(_RESULT_CACHE))
        del _RESULT_CACHE[oldest]
    _RESULT_CACHE[cache_id] = data

# Resolve the local library path. Priority:
#   1. LIBRARY_PATH env var — set this in Render to your persistent disk path,
#      e.g. /var/data/music_library.csv  (mount the disk at /var/data in Render settings)
#   2. music_library.csv in the repo root — ephemeral fallback (changes lost on restart)
_BASE_LIBRARY = os.path.join(BASE_PATH, '..', 'music_library.csv')

def _resolve_library_path() -> str:
    def _needs_copy(dest):
        return not os.path.exists(dest) or os.path.getsize(dest) == 0

    env_path = os.environ.get('LIBRARY_PATH')
    if env_path:
        os.makedirs(os.path.dirname(os.path.abspath(env_path)), exist_ok=True)
        if _needs_copy(env_path) and os.path.exists(_BASE_LIBRARY):
            shutil.copy2(_BASE_LIBRARY, env_path)
        return env_path
    if os.path.isdir('/data'):
        vol = '/data/music_library.csv'
        if _needs_copy(vol) and os.path.exists(_BASE_LIBRARY):
            shutil.copy2(_BASE_LIBRARY, vol)
        return vol
    logging.warning('No persistent disk configured — library changes will be lost on restart.')
    return _BASE_LIBRARY

LOCAL_LIBRARY_PATH = _resolve_library_path()

UPLOAD_DIR = os.path.join('/tmp', 'astral_audio_uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# usage log — written to persistent disk if available, otherwise skipped
_USAGE_LOG = os.path.join(os.path.dirname(LOCAL_LIBRARY_PATH), 'usage_log.jsonl')

def _log_run(entry: dict):
    """Append a JSON line to the usage log. Fails silently."""
    try:
        entry['ts'] = datetime.now().isoformat()
        with open(_USAGE_LOG, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Spotify / Deezer helpers
# ---------------------------------------------------------------------------

def get_spotify_client():
    if not _SPOTIPY_AVAILABLE:
        return None
    cid     = os.environ.get('SPOTIFY_CLIENT_ID')
    csecret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    if not cid or not csecret:
        return None
    try:
        auth = SpotifyClientCredentials(client_id=cid, client_secret=csecret)
        return spotipy.Spotify(auth_manager=auth)
    except Exception:
        return None


def fetch_track_meta(sp, track_ids):
    """Batch fetch album art from Spotify (max 50 per request)."""
    art = {}
    for i in range(0, len(track_ids), 50):
        batch = track_ids[i:i + 50]
        results = sp.tracks(batch)
        for t in results['tracks']:
            if not t:
                continue
            if t.get('album', {}).get('images'):
                art[t['id']] = t['album']['images'][1]['url']  # 300 px
    return art


def fetch_deezer_previews(tracks):
    """Fetch 30s preview URLs from Deezer public API (no auth required).
    tracks: list of dicts with 'name' and 'artist' keys.
    Returns dict keyed by spotify_id → preview_url."""
    previews = {}
    for t in tracks:
        sid = t.get('spotify_id')
        if not sid:
            continue
        query = urllib.parse.urlencode({'q': f'track:"{t["name"]}" artist:"{t["artist"]}"', 'limit': 1})
        url = f'https://api.deezer.com/search?{query}'
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                data = json.loads(resp.read())
            items = data.get('data', [])
            if items and items[0].get('preview'):
                previews[sid] = items[0]['preview']
        except Exception:
            pass
        time.sleep(0.05)  # stay well under Deezer rate limits
    return previews


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def _pool_count():
    """Return number of tracks in local library (header excluded), or None on error."""
    try:
        with open(LOCAL_LIBRARY_PATH) as f:
            return sum(1 for _ in f) - 1
    except Exception:
        return None


@app.route('/')
def index():
    error = request.args.get('error')
    google_maps_key = os.environ.get('GOOGLE_MAPS_API_KEY', '')
    return render_template('index.html', error=error, maps_key=google_maps_key,
                           pool_count=_pool_count())


@app.route('/start', methods=['POST'])
def start():
    """Validate form, save data to session, redirect to loading page."""
    required = ['birth_date', 'birth_time', 'birth_lat', 'birth_lng', 'birth_tz',
                'current_lat', 'current_lng', 'current_tz']
    for field in required:
        if not request.form.get(field):
            return redirect(f'/?error=missing_{field}')

    try:
        session['birth_data'] = {
            'name': request.form.get('name', 'You').strip() or 'You',
            'date': request.form['birth_date'],
            'time': request.form['birth_time'],
            'lat':  float(request.form['birth_lat']),
            'lng':  float(request.form['birth_lng']),
            'tz':   request.form['birth_tz'],
        }
        session['current_location'] = {
            'lat': float(request.form['current_lat']),
            'lng': float(request.form['current_lng']),
            'tz':  request.form['current_tz'],
        }
    except (ValueError, KeyError):
        return redirect('/?error=invalid_form_data')

    # library choice + filters
    session['library_choice']  = request.form.get('library_choice', 'upload')
    session['genre_filters']   = request.form.getlist('genre_filter')
    session['decade_filters']  = request.form.getlist('decade_filter')

    # handle optional Exportify CSV upload
    csv_file = request.files.get('liked_songs_csv')
    if csv_file and csv_file.filename:
        upload_id = session.get('upload_id') or uuid.uuid4().hex
        session['upload_id'] = upload_id
        csv_path = os.path.join(UPLOAD_DIR, f'{upload_id}.csv')
        try:
            csv_file.save(csv_path)
            session['csv_path'] = csv_path
            # merge into local music library
            try:
                added = merge_into_library(csv_path, LOCAL_LIBRARY_PATH)
                app.logger.info(f'Library merge: +{added} new tracks (pool now {_pool_count()})')
            except Exception as merge_err:
                app.logger.warning(f'Library merge failed: {merge_err}')
        except Exception:
            session.pop('csv_path', None)

    return redirect('/loading')


@app.route('/loading')
def loading_page():
    """Show the animated loading page; JS connects to /progress SSE stream."""
    if 'birth_data' not in session:
        return redirect('/')
    return render_template('loading.html')


@app.route('/progress')
def progress():
    """SSE stream: runs the pipeline, emits phase events, stores result in cache."""
    if 'birth_data' not in session:
        return Response('data: {"event":"error","message":"Session expired"}\n\n',
                        mimetype='text/event-stream')

    birth_data       = session['birth_data']
    current_location = session['current_location']
    uploaded_csv     = session.get('csv_path')
    library_choice   = session.get('library_choice', 'upload')
    genre_filters    = session.get('genre_filters') or []
    decade_filters   = session.get('decade_filters') or []

    # Snapshot session values — can't write to session inside a streaming response
    cache_id = session.get('cache_id') or uuid.uuid4().hex

    def run_pipeline():
        def event(name, message=None):
            data = {'event': name}
            if message:
                data['message'] = message
            return f'data: {json.dumps(data)}\n\n'

        try:
            # Phase 1 — chart + horoscope (slow: Gemini API)
            yield event('phase', 'reading the cosmos')

            daily_aspects, natal_subj, transit_subj = get_transit_aspects(
                birth_data, transit_loc=current_location
            )
            horoscope = get_horoscope(daily_aspects)

            # Phase 2 — scoring + model (fast: local, or slower with model training)
            yield event('phase', 'finding your frequency')

            # always score against the full local library for maximum discovery
            # user upload is used for model training only
            library_df = load_music_library(
                local_library_path=LOCAL_LIBRARY_PATH,
                genre_filters=genre_filters,
                decade_filters=decade_filters,
            )
            library_source = 'pool'

            select_aspects  = get_select_aspects(daily_aspects, horoscope)
            baseline_vector = build_target_vector(select_aspects)

            # attempt to train personal Lasso model if upload has added_at dates
            model_bundle = None
            if uploaded_csv and Path(uploaded_csv).exists():
                try:
                    raw_df = pd.read_csv(uploaded_csv)
                    raw_df.columns = [c.lower().replace(' ', '_').replace('(s)', 's')
                                      for c in raw_df.columns]
                    if 'added_at' in raw_df.columns:
                        n_songs = len(raw_df.dropna(subset=['added_at']))
                        yield event('phase', f'finding your frequency · 0 / {n_songs} songs')

                        progress_q = queue.Queue()
                        result_box = [None]
                        err_box    = [None]

                        def _progress_cb(current, total):
                            progress_q.put((current, total))

                        def _do_train():
                            try:
                                result_box[0] = train_model(raw_df, birth_data, progress_cb=_progress_cb)
                            except Exception as e:
                                err_box[0] = e
                            finally:
                                progress_q.put(None)  # sentinel

                        t = threading.Thread(target=_do_train, daemon=True)
                        t.start()

                        while True:
                            msg = progress_q.get()
                            if msg is None:
                                break
                            cur, tot = msg
                            yield event('phase', f'finding your frequency · {cur} / {tot} songs')

                        t.join()
                        if err_box[0]:
                            raise err_box[0]
                        model_bundle = result_box[0]
                except Exception as model_err:
                    app.logger.warning(f'Model training skipped: {model_err}')

            if model_bundle is not None:
                model_vector  = predict_target_vector(daily_aspects, model_bundle)
                target_vector = blend_target_vectors(model_vector, baseline_vector, model_weight=0.3)
            else:
                target_vector = baseline_vector

            matched_df = score_tracks(library_df, target_vector, top_n=20)
            matched_df = matched_df.rename(columns={
                'track_name':   'name',
                'artist_names': 'artist',
            })
            top_tracks = matched_df.to_dict('records')

            sp = get_spotify_client()
            if sp:
                track_ids = [t['spotify_id'] for t in top_tracks if t.get('spotify_id')]
                art_map   = fetch_track_meta(sp, track_ids)
                for t in top_tracks:
                    t['album_art_url'] = art_map.get(t.get('spotify_id'), None)
            else:
                for t in top_tracks:
                    t['album_art_url'] = None

            # Phase 3 — song previews
            yield event('phase', 'scoring your stars')

            preview_map = fetch_deezer_previews(top_tracks)
            for t in top_tracks:
                t['preview_url'] = preview_map.get(t.get('spotify_id'), None)

            horoscope_meanings = {
                a['aspect'].split(' (orb:')[0].strip(): a.get('meaning', '')
                for a in horoscope.get('aspects', [])
            }
            template_aspects = []
            for a in select_aspects[:3]:
                key = f'Natal {a.p1_name} in {a.aspect} with transiting {a.p2_name}'
                prof = aspect_audio_profile(a)
                template_aspects.append({
                    'planet1':     a.p1_name,
                    'planet2':     a.p2_name,
                    'aspect_type': a.aspect,
                    'meaning':     horoscope_meanings.get(key, ''),
                    'profile': {f: round(float(prof[f]), 2)
                                for f in ['valence', 'energy', 'danceability', 'acousticness']},
                })

            natal_planets   = get_planet_list(natal_subj,   PLANET_LIST)
            transit_planets = get_planet_list(transit_subj, PLANET_LIST)
            natal_rising    = natal_subj.first_house.sign

            user_tz   = ZoneInfo(current_location.get('tz', 'UTC'))
            now_local = datetime.now(tz=user_tz)
            today_str = now_local.strftime('%A, %B %-d · %Y')
            day_name  = now_local.strftime('%A')

            # Store rendered HTML in cache so /result can serve it
            html = render_template(
                'result.html',
                horoscope=horoscope,
                tracks=top_tracks,
                aspects=template_aspects,
                natal_planets=natal_planets,
                transit_planets=transit_planets,
                natal_rising=natal_rising,
                day_name=day_name,
                today=today_str,
                birth_data=birth_data,
                library_source=library_source,
                library_total=len(library_df),
                matched_count=len(top_tracks),
                target_vector=target_vector,
                planet_descriptions=PLANET_DESCRIPTIONS,
                natal_meanings=NATAL_MEANINGS,
                transit_meanings=TRANSIT_MEANINGS,
            )
            _cache_set(cache_id, {
                'target_vector': target_vector,
                'html':          html,
            })

            _log_run({
                'library':  library_source,
                'tracks':   len(library_df),
                'model':    'blended' if model_bundle else 'handcoded',
                'uploaded': bool(uploaded_csv),
            })

            yield event('done', cache_id)

        except Exception as e:
            app.logger.exception('Pipeline error')
            _log_run({'error': str(e)})
            yield event('error', str(e))

    resp = Response(stream_with_context(run_pipeline()), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    # Write cache_id to session before streaming starts
    session['cache_id'] = cache_id
    return resp


@app.route('/result')
def result():
    """Serve the pre-rendered result HTML from cache."""
    cache_id = session.get('cache_id')
    cached   = _RESULT_CACHE.get(cache_id) if cache_id else None
    if not cached or 'html' not in cached:
        return redirect('/')
    return cached['html']


# ---------------------------------------------------------------------------
# Rescore endpoint
# ---------------------------------------------------------------------------

@app.route('/rescore', methods=['POST'])
def rescore_endpoint():
    """Adjust playlist from slider values + liked/disliked track URIs."""
    data = request.get_json(force=True) or {}

    cache_id = session.get('cache_id')
    cached   = _RESULT_CACHE.get(cache_id) if cache_id else None

    # Get target_vector from cache or fall back to session cookie
    if cached is not None:
        base_target = cached['target_vector']
    else:
        base_target = session.get('target_vector')
        if not base_target:
            return jsonify({'error': 'Session expired — please regenerate your playlist.'}), 400
        app.logger.info('Rescore: using target_vector from session cookie after cache miss')

    # always reload from full local library — fast CSV read, avoids holding DataFrames in memory
    try:
        library_df = load_music_library(
            local_library_path=LOCAL_LIBRARY_PATH,
            genre_filters=session.get('genre_filters') or [],
            decade_filters=session.get('decade_filters') or [],
        )
    except Exception as e:
        app.logger.warning(f'Rescore library load failed: {e}')
        return jsonify({'error': 'Session expired — please regenerate your playlist.'}), 400

    slider_values  = data.get('sliders', {})
    liked_uris     = data.get('liked', [])
    disliked_uris  = data.get('disliked', [])

    new_df, adjusted = rescore_tracks(
        library_df, base_target, slider_values,
        liked_uris=liked_uris, disliked_uris=disliked_uris,
    )
    new_df = new_df.rename(columns={'track_name': 'name', 'artist_names': 'artist'})

    tracks = []
    for t in new_df.to_dict('records'):
        tracks.append({
            'name':          t.get('name', ''),
            'artist':        t.get('artist', ''),
            'track_uri':     t.get('track_uri', ''),
            'spotify_id':    t.get('spotify_id', ''),
            'spotify_url':   t.get('spotify_url', ''),
            'album_art_url': None,
            'preview_url':   None,
        })

    sp = get_spotify_client()
    if sp:
        ids     = [t['spotify_id'] for t in tracks if t.get('spotify_id')]
        art_map = fetch_track_meta(sp, ids)
        for t in tracks:
            t['album_art_url'] = art_map.get(t.get('spotify_id'))

    preview_map = fetch_deezer_previews(tracks)
    for t in tracks:
        t['preview_url'] = preview_map.get(t.get('spotify_id'), None)

    return jsonify({
        'tracks': tracks,
        'target': {k: adjusted[k] for k in ['valence', 'energy', 'danceability', 'acousticness']},
    })


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

try:
    from timezonefinder import TimezoneFinder as _TF
    _timezone_finder = _TF()
except Exception:
    _timezone_finder = None


@app.route('/api/timezone')
def api_timezone():
    """Resolve lat/lng to timezone string using timezonefinder."""
    try:
        lat = float(request.args['lat'])
        lng = float(request.args['lng'])
    except (KeyError, ValueError):
        return jsonify({'error': 'lat and lng required'}), 400

    try:
        if _timezone_finder is None:
            raise RuntimeError('timezonefinder not available')
        tz = _timezone_finder.timezone_at(lat=lat, lng=lng) or 'UTC'
        return jsonify({'timezone': tz})
    except Exception:
        return jsonify({'timezone': 'UTC'})


@app.route('/admin/download-library')
def download_library():
    return send_file(LOCAL_LIBRARY_PATH, as_attachment=True, download_name='music_library.csv')


@app.route('/health')
def health():
    upload_files = list(Path(UPLOAD_DIR).glob('*.csv')) if Path(UPLOAD_DIR).exists() else []
    uploads = [
        {'file': f.name, 'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat()}
        for f in sorted(upload_files, key=lambda f: f.stat().st_mtime, reverse=True)
    ]

    runs = []
    try:
        with open(_USAGE_LOG) as f:
            runs = [json.loads(l) for l in f if l.strip()]
    except Exception:
        pass

    return jsonify({
        'ok':            True,
        'pool':          Path(LOCAL_LIBRARY_PATH).exists(),
        'pool_count':    _pool_count(),
        'uploads_count': len(uploads),
        'uploads':       uploads,
        'runs_total':    len(runs),
        'runs_recent':   runs[-20:][::-1],  # last 20, newest first
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
