"""The icons and colors an app may wear in Talaria's lists and sidebars. Icons are Hermes Desktop's codicons (it
loads the whole font, @vscode/codicons 0.0.45), picked for apps: no debug, layout or brand glyphs. Colors are
Desktop's project swatches by name: ``hsl(i*30 68% 58%)`` for the i-th. On its own, with no imports, so build.py (run
as a script) can check one too. Keep in step with desktop/src/icons.ts and Talaria/Projects/AppIcons.swift.
"""

ICONS = (  # in the app skill's groups, so pickers show like with like
    "person", "account", "organization", "mention", "comment-discussion", "mail", "inbox", "call-outgoing",
    "megaphone", "bell", "rss", "broadcast", "radio-tower", "calendar", "clock", "history", "milestone",
    "checklist", "tasklist", "target", "flag", "note", "notebook", "pencil", "book", "folder-library", "file-text",
    "files", "archive", "bookmark", "tag", "repo", "package", "briefcase", "credit-card", "percentage", "dashboard",
    "graph", "graph-line", "pie-chart", "pulse", "table", "database", "home", "globe", "map", "location", "compass",
    "telescope", "coffee", "game", "jersey", "smiley", "thumbsup", "heart", "gift", "mortar-board", "music",
    "piano", "mic", "play-circle", "device-camera", "device-camera-video", "file-media", "symbol-color", "paintcan",
    "sparkle", "wand", "lightbulb", "thinking", "beaker", "microscope", "rocket", "flame", "star-full", "zap",
    "code", "terminal", "git-branch", "extensions", "tools", "gear", "layers", "server", "chip", "cloud", "plug",
    "keyboard", "device-desktop", "device-mobile", "link", "sync", "search", "eye", "bug", "shield", "lock", "key",
    "verified",
)

COLORS = ("red", "orange", "yellow", "lime", "green", "mint", "teal", "sky", "blue", "purple", "magenta", "pink")
