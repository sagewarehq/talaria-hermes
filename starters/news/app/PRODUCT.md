# Newsroom
## Platform
web (Talaria app)
## Users
The reader who set it up, reading on their phone in Talaria.
## Product Purpose
An edited news app: on the reader's schedule (every 6 or 12 hours, or daily) Hermes reviews the reader's sources and publishes an edition of up to 30 stories
picked for their topics and interests, with a reason for each, an in-app reader, and votes that tune the ranking.
## Stack
React + TypeScript in the Talaria Vite workspace: an App.tsx app in `~/.hermes/talaria/workspace/apps/news/`, shared
core in `workspace/shared/newsroom/`. Hermes Desktop runs it live from the workspace's dev server at `/news/`; the
phone opens the build `build.py news` writes into this folder (never edit the built `index.html` or `assets/`).
Fetch with relative paths (`editions.json`, `articles/<id>.json`), which work on both. Settings in `newsroom.json`. Python collector (`refresh.py`), publisher (`publish_edition.py`), article
extraction (`extract.py`, in `~/.hermes/talaria/venvs/newsroom` when present) and app actions in `actions/`.
## Editions
`editorial.json` (latest), `editions/<id>.json` (immutable archive), `editions.json` (index), `articles/<id>.json`
(extracted text).
## Shared by the reader's devices
The reading list, every device's votes and the stories read live in `app.db` (`migrations/`, `reader.py`), changed
by `actions/saved.py`, `actions/feedback.py` and `actions/read.py` in one transaction each, so two devices at once
never lose a change. Each transaction rewrites the files the page and the editor read: `read-later.json` (Read later:
story snapshots and when they were saved, removals remembered), `reader-feedback.json` (each device's votes, a 👎's
reason and note, a vote taken back as 0; and one vote per story for the editor) and `read.json`. Every device adopts
all three, the latest vote on a story winning, so a 👎 hides a story, a 👍 ranks it up and a story shows Read
everywhere. The routine is "Newsroom editor", installed from the app's first run.
