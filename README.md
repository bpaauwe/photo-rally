# Photo Road Rally

Flask + SQLite app for running a photo road rally. Organizers write a turn-by-turn
instruction sheet and capture GPS positions where they photographed each photo spot.
Participants stop at each photo spot, press Mark, and are scored by the distance between
their mark and the organizer's (lower is better).

## Local development

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    export RALLY_INSECURE_COOKIES=1        # local http only
    flask --app rally init-db
    flask --app rally create-user admin
    flask --app rally run --debug

Open /auth/login (organizer) or / (participant join).
Note: phone GPS and camera require HTTPS, so test those on the deployed host.
The photo spot map loads Leaflet and OpenStreetMap tiles from the internet.

## Shared host (Passenger / cPanel "Setup Python App")

- Startup file: `passenger_wsgi.py`, entry point: `application`
- `pip install -r requirements.txt` in the app's virtualenv
- Run `flask --app rally init-db` and `create-user` once from the app's shell
- Forgot a password? `flask --app rally set-password USERNAME` resets it. Signed in, use the Account page to change your username or password.
- Config via env vars (optional): `RALLY_SECRET_KEY`, `RALLY_DB`, `RALLY_PHOTOS`, `RALLY_DB_WAL=1`,
  `RALLY_PUBLIC_URL` (the https address printed in QR codes, e.g. `https://example.com/rally`)
- `instance/` holds the database, photos and generated secret key. Back it up and keep it out of git.

## Tests

    python -m unittest discover tests      # QR decoding checks run only if OpenCV is installed
    node tests/sw_test.js          # service worker logic (needs Node)

## Layout

    schema.sql             tables (re-runnable)
    rally/auth.py          organizer login, create-user command
    rally/admin.py         rallies, scoring rules, teams
    rally/sheets.py        instruction editor, .txt/.csv import, .txt export, print view
    rally/objects.py       photo spot editor: photo upload, GPS capture, adjusted pin, photo serving
    rally/static/js/sw.js  service worker: offline pages, photos and static files
    rally/cards.py         printable team cards with QR codes (and the event QR)
    rally/services/qr.py   pure-Python QR code generator (SVG output)
    rally/results.py       standings, per-team/photo-spot detail, pin (bias) check, CSV export
    rally/play.py          participant join (each team sees the photo spots in its own stable random order), instructions, photo spot pages, mark API
    rally/services/geo.py  haversine, reference point
    rally/services/instructions.py  sheet text format: parse, display model, CSV
    rally/services/scoring.py  pure scoring, ranking and bias functions

## Offline use (participants)

The participant pages install a service worker (served from `/play/sw.js`, so it needs HTTPS).
On the first visit with signal, the phone saves the instruction page, every photo spot page, the photos
and the app files. After that the pages open without signal, and marks queue on the phone and send later.
Pages refresh from the server when there is signal; saved copies are used when the network is slow or gone.
To force a fresh save for everyone after changing the service worker, bump `VERSION` in `sw.js`.
