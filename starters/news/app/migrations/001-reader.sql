-- The reader's state, shared by every device: the reading list and each device's votes (reader.py).

-- Read later: each story's snapshot (JSON, as the app shows it) and when it was saved.
CREATE TABLE saved (id TEXT PRIMARY KEY, article TEXT NOT NULL, saved_at TEXT NOT NULL);
CREATE INDEX saved_by_time ON saved (saved_at);
-- Stories taken off the list, and when: a device that still has one from before doesn't bring it back.
CREATE TABLE removed (id TEXT PRIMARY KEY, removed_at TEXT NOT NULL);

-- Each device sends all its votes at once; it keeps its own set, so one device's sync never wipes another's.
CREATE TABLE devices (device TEXT PRIMARY KEY, synced_at TEXT NOT NULL);
CREATE TABLE votes (
  device TEXT NOT NULL REFERENCES devices ON DELETE CASCADE,
  id TEXT NOT NULL,             -- the story
  value INTEGER NOT NULL,       -- 1 more like this, -1 less
  at TEXT NOT NULL DEFAULT '',
  vote TEXT NOT NULL,           -- the whole vote as JSON: title, publisher, topics, tags, reason, note
  PRIMARY KEY (device, id)
);
-- One vote per story: the latest any device cast. What the editor goes by.
CREATE VIEW latest_votes AS
  SELECT device, id, value, at, vote FROM (
    SELECT *, row_number() OVER (PARTITION BY id ORDER BY at DESC, device) AS n FROM votes
  ) WHERE n = 1;

CREATE TABLE meta (key TEXT PRIMARY KEY, value);
