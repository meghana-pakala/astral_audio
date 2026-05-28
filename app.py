"""
Astral Audio — Flask app
Routes: / → form, /generate → run pipeline, /api/timezone → lat/lng → tz
"""
import logging
import os
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session

# load local.env when running locally
load_dotenv('local.env')

# add src/ to path so pipeline modules resolve correctly
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_PATH, 'src'))

from aspects import (NATAL_PLANETS_LIST, TRANSIT_PLANETS_LIST,
                     get_planet_list, get_transit_aspects)
from horoscope import get_horoscope, get_select_aspects
from library import load_music_library, merge_into_library
from score import build_target_vector, score_tracks

# optional Spotipy for album art — graceful fallback if not installed / no creds
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    _SPOTIPY_AVAILABLE = True
except ImportError:
    _SPOTIPY_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-please-change')

# Resolve the local library path. Priority:
#   1. LIBRARY_PATH env var — set this in Render to your persistent disk path,
#      e.g. /var/data/local_library.csv  (mount the disk at /var/data in Render settings)
#   2. /data/local_library.csv — Railway persistent volume (legacy)
#   3. local_library.csv in the repo root — ephemeral fallback (changes lost on restart)
_BASE_LIBRARY = os.path.join(BASE_PATH, 'local_library.csv')

def _resolve_library_path() -> str:
    env_path = os.environ.get('LIBRARY_PATH')
    if env_path:
        os.makedirs(os.path.dirname(os.path.abspath(env_path)), exist_ok=True)
        if not os.path.exists(env_path) and os.path.exists(_BASE_LIBRARY):
            shutil.copy2(_BASE_LIBRARY, env_path)
        return env_path
    if os.path.isdir('/data'):
        vol = '/data/local_library.csv'
        if not os.path.exists(vol) and os.path.exists(_BASE_LIBRARY):
            shutil.copy2(_BASE_LIBRARY, vol)
        return vol
    logging.warning('No persistent disk configured — library changes will be lost on restart.')
    return _BASE_LIBRARY

LOCAL_LIBRARY_PATH = _resolve_library_path()

UPLOAD_DIR = os.path.join('/tmp', 'astral_audio_uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Spotify helpers
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


def fetch_album_art(sp, track_ids):
    """Batch fetch album art from Spotify (max 50 per request)."""
    art = {}
    for i in range(0, len(track_ids), 50):
        batch = track_ids[i:i + 50]
        results = sp.tracks(batch)
        for t in results['tracks']:
            if t and t.get('album', {}).get('images'):
                art[t['id']] = t['album']['images'][1]['url']  # 300 px
    return art


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
            # Merge into the shared pool so local-pool users benefit from this upload.
            # The uploader's own session still uses their raw CSV directly (see /generate).
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
    """Show the animated loading page; JS will navigate to /generate."""
    if 'birth_data' not in session:
        return redirect('/')
    return render_template('loading.html')


@app.route('/generate')
def generate():
    """Run the astrological pipeline using birth data stored in session."""
    if 'birth_data' not in session:
        return redirect('/')

    birth_data       = session['birth_data']
    current_location = session['current_location']
    uploaded_csv     = session.get('csv_path')

    try:
        # 1. Astrological aspects (natal vs today's transits) + subject objects
        daily_aspects, natal_subj, transit_subj = get_transit_aspects(
            birth_data, transit_loc=current_location
        )

        # 2. Horoscope from Gemini (reads GEMINI_API_KEY from env)
        horoscope = get_horoscope(daily_aspects)

        # 3. Music library
        library_choice = session.get('library_choice', 'upload')
        use_upload = (library_choice == 'upload')
        user_csv   = uploaded_csv if use_upload else None
        library_df = load_music_library(
            user_playlist_path=user_csv,
            local_library_path=LOCAL_LIBRARY_PATH,
            genre_filters=session.get('genre_filters') or [],
            decade_filters=session.get('decade_filters') or [],
        )
        library_source = (
            'uploaded' if (use_upload and user_csv and Path(user_csv).exists())
            else 'pool'
        )

        # 4. Select aspects → target audio vector
        select_aspects = get_select_aspects(daily_aspects, horoscope)
        target_vector  = build_target_vector(select_aspects)

        # 5. Score and rank tracks
        matched_df = score_tracks(library_df, target_vector, top_n=20)
        matched_df = matched_df.rename(columns={
            'track_name':   'name',
            'artist_names': 'artist',
        })
        top_tracks = matched_df.to_dict('records')

        # 6. Batch-fetch album art via Spotify (300 px images)
        sp = get_spotify_client()
        if sp:
            track_ids = [t['spotify_id'] for t in top_tracks if t.get('spotify_id')]
            art_map   = fetch_album_art(sp, track_ids)
            for t in top_tracks:
                t['album_art_url'] = art_map.get(t.get('spotify_id'), None)
        else:
            for t in top_tracks:
                t['album_art_url'] = None

        # 7. Build template-ready aspects list (planet1/planet2/aspect_type/meaning)
        horoscope_meanings = {
            a['aspect'].split(' (orb:')[0].strip(): a.get('meaning', '')
            for a in horoscope.get('aspects', [])
        }
        template_aspects = []
        for a in select_aspects[:3]:
            key = f'Natal {a.p1_name} in {a.aspect} with transiting {a.p2_name}'
            template_aspects.append({
                'planet1':     a.p1_name,
                'planet2':     a.p2_name,
                'aspect_type': a.aspect,
                'meaning':     horoscope_meanings.get(key, ''),
            })

        # 8. Planet positions for transit wheel
        natal_planets   = get_planet_list(natal_subj,   NATAL_PLANETS_LIST)
        transit_planets = get_planet_list(transit_subj, TRANSIT_PLANETS_LIST)

        today_str = datetime.now().strftime('%A, %B %-d · %Y')
        day_name  = datetime.now().strftime('%A')

        return render_template(
            'result.html',
            horoscope=horoscope,
            tracks=top_tracks,
            aspects=template_aspects,
            natal_planets=natal_planets,
            transit_planets=transit_planets,
            day_name=day_name,
            today=today_str,
            birth_data=birth_data,
            library_source=library_source,
            library_total=len(library_df),
            matched_count=len(top_tracks),
            target_vector=target_vector,
        )

    except Exception as e:
        app.logger.exception('Pipeline error')
        return render_template('error.html', error=str(e))


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

@app.route('/api/timezone')
def api_timezone():
    """Resolve lat/lng to timezone string using timezonefinder."""
    try:
        lat = float(request.args['lat'])
        lng = float(request.args['lng'])
    except (KeyError, ValueError):
        return jsonify({'error': 'lat and lng required'}), 400

    try:
        from timezonefinder import TimezoneFinder
        tf = TimezoneFinder()
        tz = tf.timezone_at(lat=lat, lng=lng) or 'UTC'
        return jsonify({'timezone': tz})
    except Exception:
        return jsonify({'timezone': 'UTC'})


@app.route('/health')
def health():
    return jsonify({
        'ok':         True,
        'pool':       Path(LOCAL_LIBRARY_PATH).exists(),
        'pool_count': _pool_count(),
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
