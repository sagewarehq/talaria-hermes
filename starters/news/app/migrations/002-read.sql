-- Stories the reader opened, on any device, and when first: the Read mark on every device (actions/read.py).
CREATE TABLE read_stories (id TEXT PRIMARY KEY, at TEXT NOT NULL);
CREATE INDEX read_by_time ON read_stories (at);
