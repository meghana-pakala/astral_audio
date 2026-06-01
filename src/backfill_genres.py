"""
backfill missing genres in music_library.csv via MusicBrainz API
run in shell: python3 src/backfill_mb_genres.py --batch-size 100 --start 0
"""

import argparse
import time
import requests
import pandas as pd
from pathlib import Path
from library import _categorize_genres

LIBRARY_PATH = Path(__file__).parent.parent / 'music_library.csv'
MB_HEADERS   = {'User-Agent': 'AstralAudio/1.0 (megpakala13@gmail.com)'}

# fetch tags + genres for artists from MusicBrainz API
def fetch_mb_genres(artist_name: str):
    try:
        search_url = f'https://musicbrainz.org/ws/2/artist/?query=artist:{requests.utils.quote(artist_name)}&fmt=json'
        r = requests.get(search_url, headers=MB_HEADERS, timeout=10)
        if r.status_code != 200 or not r.json().get('artists'):
            return []

        artist_id = r.json()['artists'][0]['id']
        time.sleep(1.1)  # MB rate limit

        tags_url = f'https://musicbrainz.org/ws/2/artist/{artist_id}?inc=tags+genres&fmt=json'
        r2 = requests.get(tags_url, headers=MB_HEADERS, timeout=10)
        if r2.status_code != 200:
            return []

        data   = r2.json()
        tags   = [t['name'] for t in data.get('tags',   []) if t.get('count', 0) > 0]
        genres = [g['name'] for g in data.get('genres', []) if g.get('count', 0) > 0]
        return list(set(tags + genres))

    except Exception as e:
        print(f'  Error fetching {artist_name}: {e}')
        return []

# normalize raw tags and rename genre variants
def normalize_mb_genres(raw: list):
    s = ','.join(raw).lower()
    # character cleanup
    s = s.replace('-', ' ').replace("'", '').replace('/', ' ')
    # genre variant normalization
    replacements = [
        ('alt ',          'alternative '),
        ('alternativt',   'alternative'),
        ('aternative',    'alternative'),
        ('afro ',         'afro'),
        ('avantgarde',    'avant garde'),
        (' music',        ''),
        (' musicians',    ''),
        ('pop/rock',      'pop rock'),
        ('popular',       'pop'),
        ('rnb',           'r&b'),
        ('r b',           'r&b'),
        ('r & b',         'r&b'),
        ('rhythm & blues','r&b'),
        ('rhythm and blues', 'r&b'),
        ('rock & roll',   'rock and roll'),
        ('rockn roll',    'rock and roll'),
    ]
    for old, new in replacements:
        s = s.replace(old, new)

    # deduplicate
    seen, result = set(), []
    for g in [g.strip() for g in s.split(',') if g.strip()]:
        if g not in seen:
            seen.add(g)
            result.append(g)
    return ','.join(result)

# run API call on new artists only, categorize genre, batch save
def backfill(batch_size: int = 100, start: int = 0):
    df = pd.read_csv(LIBRARY_PATH, low_memory=False)

    # find unique artists missing mb_genres
    missing_mask    = df['mb_genres'].isna() | (df['mb_genres'].astype(str).str.strip() == '')
    missing_artists = df[missing_mask]['artist_names'].unique()
    # skip artists with 'none' (previously attempted, no result found)
    attempted = set(df[df['mb_genres'].astype(str).str.strip() == 'none']['artist_names'])
    missing_artists = [a for a in missing_artists if a not in attempted]
    total = len(missing_artists)

    print(f'Library: {len(df)} tracks, {df["artist_names"].nunique()} unique artists')
    print(f'Artists missing MB genres: {total}')

    if total == 0:
        print('Nothing to backfill.')
        return

    batch = missing_artists[start:start + batch_size]
    print(f'\nProcessing batch: {start} → {start + len(batch)} of {total}\n')

    updated = 0
    for i, artist in enumerate(batch):
        print(f'[{start + i + 1}/{total}] {artist}')
        raw = fetch_mb_genres(artist)
        print(f'  Tags: {raw[:5]}{"..." if len(raw) > 5 else ""}')

        if raw:
            normalized = normalize_mb_genres(raw)
            df.loc[df['artist_names'] == artist, 'mb_genres'] = normalized
            updated += 1
        else:
            df.loc[df['artist_names'] == artist, 'mb_genres'] = 'none'

        time.sleep(1.1)

    # run genre categorization on all updated rows
    df['genre_categories'] = df.apply(
        lambda r: _categorize_genres(r.get('genres', ''), r.get('mb_genres', '')) or '',
        axis=1
    )

    df.to_csv(LIBRARY_PATH, index=False)

    categorized = (df['genre_categories'].fillna('') != '').sum()
    print(f'\nBatch complete. Updated {updated} artists.')
    print(f'Genre coverage: {categorized}/{len(df)} ({categorized/len(df)*100:.1f}%)')
    print(f'Next run: --start {start + batch_size}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--start',      type=int, default=0)
    args = parser.parse_args()
    backfill(batch_size=args.batch_size, start=args.start)
