# Newsroom
## Platform
web (Talaria app)
## Users
The reader who set it up, reading on their phone in Talaria.
## Product Purpose
An edited news app: on the reader's schedule (every 6 or 12 hours, or daily) Hermes reviews the reader's sources and publishes an edition of up to 30 stories
picked for their topics and interests, with a reason for each, an in-app reader, and votes that tune the ranking.
## Stack
React + TypeScript in the Talaria Vite workspace: source in `~/.hermes/talaria/workspace/apps/news/`, shared core in
`workspace/shared/newsroom/`, built into this folder by `build.py news` (never edit the built `index.html` or
`assets/`). Settings in `newsroom.json`. Python collector (`refresh.py`), publisher (`publish_edition.py`), article
extraction (`extract.py`, in `~/.hermes/talaria/venvs/newsroom` when present) and app actions in `actions/`.
## Editions
`editorial.json` (latest), `editions/<id>.json` (immutable archive), `editions.json` (index), `articles/<id>.json`
(extracted text). The routine is "Newsroom editor", installed from the app's first run.
