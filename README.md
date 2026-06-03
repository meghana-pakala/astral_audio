# Astral Audio

Music recommendation today is a backwards-looking system. Streaming services know your listening history and optimize for your past self, which makes them bad at the one thing you actually want from music: meeting you where you are right now. The missing variable is a predictive measure of emotional state. The question this project tries to answer: is there a structured proxy for current mood that can actually drive a recommendation system?

*Musica Universalis* — Harmony of the Spheres — is the ancient idea that planetary motion has a frequency. Harmonic ratios - the acoustic basis of music theory - define the natural frequencies produced between any vibrating objects. Connecting the two becomes a data challenge: if planetary configurations correlate with mood and energy, and audio features describe the emotional character of a song, then the sky should tell you something about what music you'll connect with on any given day. 

Astral Audio maps your personal astrological transits to audio feature targets and finds the songs that match your stars. Astrology may be a pseudo-science, but it makes a credible case as the original data science: both attempt to find signal in the noise of human experience - the difference is just the geometry of outer space versus a feature space.

**[Find your astral frequency →](https://astral-audio.onrender.com)**

---

## How It Works

1. **Natal & Transit Aspects** — [`src/aspects.py`](src/aspects.py)
   - Computes natal and current planetary positions using [kerykeion](https://github.com/g-battaglia/kerykeion)
   - Filters to active aspects within moiety orb limits
2. **LLM Aspect Selection** — [`src/horoscope.py`](src/horoscope.py)
   - Calls Gemini to select the most emotionally coherent aspects for the day
   - Returns a daily horoscope, mood keywords, and aspect interpretations
3. **Baseline Audio Vector** — [`src/score.py`](src/score.py)
   - Computes the audio profile for each selected aspect from predefined planetary profiles
   - Blends aspect profiles into a single target vector, weighted by signal strength
4. **Personal Lasso Model** (optional) — [`src/model.py`](src/model.py)
   - Given a user playlist upload, trains a Lasso regression model to learn personal taste
   - Model prediction is blended 30/70 with the baseline vector (model 30%, baseline 70%)
5. **Score & Rank** — [`src/score.py`](src/score.py)
   - Scores tracks by weighted Euclidean distance from the target vector
   - Returns the top 20 tracks as the playlist
6. **Tune & Rescore** (in-app)
   - Adjust the target vector directly with audio feature sliders
   - Like/dislike individual tracks to shift the vector toward/away from that song's profile

Run the full pipeline via [`astral_audio.ipynb`](astral_audio.ipynb)

---

## The Astro-Logic

A natal chart is a snapshot of the sky at the moment you were born. A transit chart is a map of the sky right now. An **aspect** is a meaningful geometric angle formed when a planet in today's sky aligns with a planet in your natal chart - describing which parts of your chart are being activated.

### Aspects & Harmony

Johannes Kepler argued in *Harmonices Mundi* (1619) that the same ratios governing musical consonance also define the geometric relationships between planetary positions. The five key aspect types are defined by the same divisions that produce the natural harmonic series:

| Planetary Aspect | Harmonic Ratio | Character |
|---|---|---|
| Conjunction (0°) | 1:1 - unison | Perfect fusion, amplified energy |
| Opposition (180°) | 2:1 - octave | Polarity, unresolved tension |
| Trine (120°) | 3:2 - perfect fifth | Flow, ease, consonance |
| Square (90°) | 4:3 - perfect fourth | Friction, activation, drive |
| Sextile (60°) | 6:5 - minor third | Warm, cooperative, understated |

When a square is active, the system isn't simply mapping "tension → darker music" — it's recognizing that the 4:3 geometric relationship corresponds to the same ratio that music theory identifies as the boundary between consonance and dissonance.  This gives the audio feature mapping a principled basis to translate planetary geometry into sonic targets rather than relying on purely symbolic associations. 

### Orbs & Signal Strength

Planets are rarely at exactly the canonical aspect angle. An **orb** is the allowable margin of deviation for a planet; **moiety** is each aspect's effective orb limit, calculated as the average of both planets' individual orbs.

Orb limits are assigned per planet based on angular velocity and astrological significance — faster-moving planets get wider orbs because their aspects drive genuine day-to-day variation; slower outer planets get tighter orbs because their influence only becomes meaningful when nearly exact.

Once an aspect is identified, its moiety determines how strongly it influences the audio target. Both physics and astrology treat proximity as a nonlinear influence, so to calculate aspect signal strength we apply inverse square law (double the distance, quarter the influence) - the same relationship used for gravitational and electromagnetic force: `signal_strength = 1 / (orb² + 1)`

A Venus trine Saturn at 0.06° carries near-full weight. The same aspect at 3° carries about 10%. Influence fades continuously rather than cutting off at a hard threshold.

## Mapping Stars to Sonics

Each planet is encoded as a profile across five continuous audio features plus mode:

| Feature | Description | Scoring Weight |
|---------|-------------|---------------|
| Valence | Musical Positivity (dark/tense to bright/euphoric) | 2.0× |
| Energy | Intensity & Activity (ambient to driving) | 1.5× |
| Danceability | Rhythmic Regularity & Groove | 1.5× |
| Acousticness | Production Character (electronic to acoustic) | 1.0× |
| Tempo | BPM offset from a neutral 120 BPM | target only |
| Mode | Minor vs. Major | soft 0.3 penalty |

Valence maps to harmonic consonance: soft aspects (conjunction, trine, sextile) pull valence up; hard aspects (square, opposition) pull it down. Energy maps to amplification of planetary expression: hard aspects drive energy up, soft aspects let it settle.

Each aspect's profile is the average of the two planet profiles, reflecting that an aspect is a conversation between energies rather than the expression of either alone.The selected aspect profiles are then blended into a single target vector, weighted by signal strength.

**Excluded Features:** speechiness, instrumentalness, liveness, loudness, and key are dropped - speechiness and instrumentalness lack consistent distribution across library tracks; loudness and liveness are unreliably measured; key is categorical in a way that doesn't translate cleanly to a continuous target.

### Personal Model

The baseline vector captures universal astrological logic but knows nothing about individual taste. Uploading an [Exportify](https://exportify.net) CSV of Liked Songs trains a personal Lasso regression model on top of it.

**Training Signal:** Each Liked Song has an `added_at` timestamp - the day the user saved it, treated as a weak proxy for mood. The assumption is that a song saved on a given day reflects what the user wanted to hear that day.

**Feature Engineering:** For each save date, active transit aspects are computed and encoded as a sparse vector - one slot per possible natal/aspect/transit planet combination (10 planets × 5 aspect types × 10 planets = 500 features), valued by signal strength. Most slots are 0 on any given day.

**Target:** The deviation of each song's audio features from the user's personal mean. Training on deltas anchors the model to the user's baseline taste range - it only needs to explain mood shifts, not reconstruct absolute preferences from scratch.

**Model:** One `LassoCV` per audio feature. Lasso suits this problem well: the feature space is sparse, the dataset is small (typically a few hundred to few thousand tracks), and the L1 penalty automatically zeroes out aspect combinations that aren't predictive for that user.

**Blend:** The model prediction is combined with the baseline vector at 30% model / 70% baseline. This is intentionally conservative - save date is a noisy signal, and the blend lets the model nudge results toward personal taste without overriding the astrological logic.

### Scoring & Tuning

Tracks are ranked by weighted Euclidean distance from the target vector across the continuous audio features, with a soft mode penalty applied afterward - lower score = closer match. The top 20 tracks are returned as the playlist.

The app displays the target vector as a radar chart and allows the user to refine their results. Feature sliders adjust the audio target, and like/dislike buttons shift the vector 50% toward or away from that track's audio profile before rescoring. This creates a lightweight human-in-the-loop correction layer on top of the astrological output.

---

## Limitations & Future Directions

**Planet-to-Audio Mappings:** The planetary profiles are hand-coded from astrological interpretation, not learned from data. The most impactful next step would be replacing them with data-driven weights. The user feedback loop is already built to collect the necessary signal — with account creation and enough sessions, aggregated ratings could be used to fit the planet-to-audio-feature weights directly. If ratings cluster around specific aspect configurations, the heuristic profiles get replaced by learned ones, turning the system from interpretive to empirical.

**Semantic Embeddings:** Audio features capture sonic mechanics, not emotional resonance. "Here Comes the Sun" and a Vivaldi concerto might score similarly on valence, energy, and acousticness but feel completely different. Semantic embeddings would address this directly — encoding emotional similarity so that songs cluster by mood and cultural association rather than BPM and acousticness. Rather than targeting a feature vector, the system would map aspect descriptions into an embedding space and retrieve songs by emotional proximity - asking what songs *feel* like a Venus-Neptune trine rather than what tracks *measure* like one.

**Model Training Signals:** Save date is a noisy signal - people save songs for many reasons unrelated to their mood that day, which is why the personal model blend is intentionally conservative at 30%. Spotify's Extended Listening History (available on request) would provide far stronger behavioral signals: play counts, skips, and listening streaks across the same transit period are significantly more informative than when a song was first saved.

**Two-User Playlists:** Separate library uploads, both natal charts computed, target vectors blended, playlist drawn from the shared pool - the most natural extension of the current architecture.

**Spotify API Restrictions:** The Exportify CSV approach adds friction but is a deliberate workaround. Spotify's developer API limits third-party access to 50 recently played tracks and rough top-track aggregates — not enough behavioral signal to meaningfully inform the model. The API also restricts playlist creation, with no feasible method to push the app's output as a daily playlist.

---

## Project Structure

```
astral_audio/
├── app/
│   ├── templates/
│   │   ├── about.html        # app philosophy
│   │   ├── index.html        # user input + playlist upload
│   │   ├── loading.html      # pipeline progress screen
│   │   ├── result.html       # playlist + radar chart + sliders
│   │   └── error.html
│   ├── app.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── Procfile
├── src/
│   ├── aspects.py            # aspect computation, orb filtering
│   ├── horoscope.py          # LLM call, aspect selection
│   ├── library.py            # library loading, genre/decade filtering
│   ├── model.py              # Lasso model training, prediction
│   ├── score.py              # target vector construction, track scoring
│   └── backfill_genres.py    # utility: genre metadata enrichment
├── pipeline.ipynb
├── music_library.csv
└── README.md
```

---

## Background

This project grew out of [AnaLyrics](https://github.com/meghana-pakala/capstone), a genre classification model built on song lyrics - part of a broader goal to build a playlist generator that takes mood as an input and returns songs that match (a concept Spotify launched with their AI playlist feature a few months later). That project laid the data source foundation - Spotify, MusicBrainz, and Genius APIs - to understand what signals were actually available. 

The NLP pipeline proved that genre boundaries based on language are difficult to define, and audio features don't map cleanly to a labeling approach. The question I kept coming back to was how I could use lyrics and sonics as a target rather than a model variable. The missing factor was a proxy for measuring mood beyond genre categories - astrology was a natural fit. It is an ancient system with genuine underlying mathematical structure, and a framework for mapping external condtions to internal emotions.

Astral Audio is a way to bring those threads together. Audio features are continuous, emotionally interpretable, and well-suited to distance-based matching. Genre classification from lyrics is essentially asking what a song means culturally, which is closer to semantic embedding than audio feature matching. Audio features capture the shape of a song - lyrical embeddings capture its meaning. The next version of this system doesn't target a feature vector, it maps aspect descriptions into emotional space and retrieves songs by what they feel like rather than what they measure like. AnaLyrics set the course and Astral Audio launched the mission - the next step? Ad Astra.
