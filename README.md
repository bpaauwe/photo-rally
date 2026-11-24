# Photo Road Rally

Flask + SQLite app for running a photo road rally. Organizers write a turn-by-turn
instruction sheet and capture GPS positions where they photographed each object.
Participants stop at each object, press Mark, and are scored by the distance between
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

## Shared host (Passenger / cPanel "Setup Python App")

- Startup file: `passenger_wsgi.py`, entry point: `application`
- `pip install -r requirements.txt` in the app's virtualenv
- Run `flask --app rally init-db` and `create-user` once from the app's shell
- Config via env vars (optional): `RALLY_SECRET_KEY`, `RALLY_DB`, `RALLY_PHOTOS`, `RALLY_DB_WAL=1`
- `instance/` holds the database, photos and generated secret key. Back it up and keep it out of git.

## Tests

    python -m unittest discover tests

## Layout

    schema.sql             tables (re-runnable)
    rally/auth.py          organizer login, create-user command
    rally/admin.py         rallies, scoring rules, teams
    rally/sheets.py        instruction editor, .txt/.csv import, .txt export, print view
    rally/play.py          participant join (marking flow is next)
    rally/services/geo.py  haversine, reference point
    rally/services/instructions.py  sheet text format: parse, display model, CSV
    rally/services/scoring.py  pure scoring functions
