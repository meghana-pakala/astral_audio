FROM python:3.13-slim

# Install build tools + libsqlite3 — required to compile pyswisseph
RUN apt-get update && apt-get install -y \
    gcc build-essential libsqlite3-0 libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /service

# install dependencies first for better layer caching
COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

# copy repo contents — src/ and music_library.csv land at /service/
COPY . .

# run from /service so ../src and ../music_library.csv resolve correctly
CMD gunicorn --chdir app app:app --bind 0.0.0.0:$PORT --workers 1 --worker-class gthread --threads 4
