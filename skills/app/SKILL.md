---
name: app
description: "Use when the user asks for an app, or for a dashboard, tracker, planner, report, tool or any page or small app to look at in Talaria (their iPhone app). Covers the Vite + React workspace apps are built in, the packages it has, how to design one, and how to hand it back so it opens in the app."
version: 2.6.0
author: Sageware Solutions Inc.
metadata:
  hermes:
    tags: [talaria, app, web, dashboard, ui, charts, react, vite]
---

# Talaria apps

An app is a small web app the user opens full screen in Talaria, their iPhone app for Hermes. It's yours to
build and rebuild freely, and it can be anything a web page can be: a live dashboard, a tracker, a planner, a
report, a game, a control panel. Be ambitious. An app is a whole app, not a widget.

## Where it lives

Every app is a sub-app of one Vite + React + TypeScript project on this machine, the **workspace**, and is built
into a folder of its own that Talaria loads:

    ~/.hermes/talaria/workspace/            the Vite project: package.json, node_modules, tsconfig.json
      shared/                               components, hooks and styles more than one app uses
      apps/<name>/App.tsx, server.ts, …     one app's source
      talaria/                              Talaria's own (the build config, viz); replaced on every build, don't edit
    ~/.hermes/talaria/apps/<name>/          the built app, which the phone opens, plus its data files

- `<name>` is short kebab-case (`spending`, `hiring-pipeline`, `cebu-trip`).
- Write source only in `workspace/apps/<name>/` and `workspace/shared/`. The built folder is the build's output,
  except for data files (below).
- `ls ~/.hermes/talaria/workspace/apps` lists the apps; `ls ~/.hermes/talaria/apps` lists what Talaria shows. To
  delete an app, remove both folders.
- The workspace also runs **live**, with no build step, on one dev server (one port for every app, each at
  `/<name>/`), which Hermes Desktop opens apps from and which reloads them as you edit. The phone opens the build.

## Build it

    python3 ~/.hermes/plugins/talaria/build.py --new <name>    start an app from the template, and build it
    python3 ~/.hermes/plugins/talaria/build.py <name>          build it after every change to its source
    python3 ~/.hermes/plugins/talaria/build.py --all           build every app, after a change to shared/
    python3 ~/.hermes/plugins/talaria/build.py add <pkg>…      add npm packages to the workspace
    python3 ~/.hermes/plugins/talaria/build.py migrate <name>  move an older app in (below)

- **Build after every change to source**, then look at it (below). The phone shows the last good build: a failed
  build changes nothing there and prints the error with its file and line. Fix it and build again. Desktop shows
  your edits as you save them, from the dev server, but the phone only sees what you build.
- Changing a data file needs no build.
- The first build installs the packages and takes about half a minute; after that a build takes a few seconds.
- It's ordinary Vite: imports without extensions, `import './style.css'`, npm packages, images and fonts imported
  from source, `import.meta.env`. Files in `apps/<name>/public/` are copied as they are.
- Types are stripped, not checked. To check them, run `npx tsc --noEmit` in the workspace.
- If the build says it needs Node.js, there's none on this machine: write a plain HTML app straight into
  `~/.hermes/talaria/apps/<name>/index.html` instead, with no build. Its module scripts can still import
  `react`, `react-dom/client`, `viz`, `motion/react`, `lucide-react` and `d3` by name (Talaria serves its own
  copies), and `html` (htm bound to React) for markup without JSX.

## What's in it

| import | what |
|---|---|
| `react`, `react-dom/client` | React 19 |
| `viz` | Datagen's charts (below) |
| `motion/react` | Motion: animation, gestures, layout transitions, `AnimatePresence` |
| `lucide-react` | Lucide icons as components (`<Wallet size={16} />`) |
| `d3` | d3 v7, for anything custom (scales, shapes, maps, force layouts) |
| `@shared/…` | the workspace's `shared/` folder |
| `talaria` | Talaria's own: `useQuery` and `db` (the app's database), `action` (its scripts) |

Tailwind v4 is set up: the app's `style.css`, with `@import "tailwindcss";` and `@source "../../shared";` (so
classes in shared components count), loaded before the app. Anything else: `build.py add <pkg>`, then import it. Packages
are bundled into the app, so it doesn't depend on a CDN.

`shared/` starts with:
- `Screen` (`@shared/Screen`): a page laid out under Talaria's top bar, with the right safe-area padding.
- `useJSON(path)` (`@shared/useJSON`): fetches one of the app's data files, never cached.

Add to it whatever a second app would otherwise copy: a theme, a card, a data hook. After changing it, build with
`--all`, since every app that imports it has the old copy until it's rebuilt.

`--new` starts an app in `workspace/apps/<name>/`: an `App.tsx` and a `style.css`. There's no `index.html` or
`main.tsx`: Talaria gives every app its page, loads `style.css`, and mounts `App.tsx`'s default export.

```tsx
export const meta = { title: 'Spending', icon: './icon.svg', theme: { light: '#ffffff', dark: '#111317' } }

export default function App() { … }
```

`meta.title` is the app's name in Talaria; keep it short. `icon` is an image in the app's data folder, and `theme`
the browser chrome's colour; both are optional.

## Pages and state

An app can have as many pages as it needs. Talaria is its browser: links between its pages open in place, and
Talaria's Back button (and the edge swipe) walks back through them before it leaves the app.

- **Route with the hash** (`#/settings`, `#/trip/tokyo`); each route counts as a page for Back.
- **Fetch with relative paths**: `fetch('data.json')`, `fetch('articles/42.json')`, `<img src="./images/a.jpg">`.
  Never a leading `/`: on the dev server the app lives at `/<name>/`, and `/data.json` would miss it.
- **Keep state in `localStorage` or IndexedDB** for what the user does on the device: checked items, filters,
  drafts, the last tab. Prefix every key with the app's name (`spending:filters`): on the dev server every app
  shares one origin. That state stays on the device; data that Hermes or a routine writes belongs in the app's
  JSON files, or its database once it's records (below).
- Lay out every screen under the top bar (below).
- An older app with its own `index.html` keeps its pages as HTML files and `/` as its root, and opens in Desktop only
  over SSH; write new apps as an `App.tsx`.

## Data

Data that Hermes or a routine writes lives in the **built** folder, `~/.hermes/talaria/apps/<name>/`, which a build
never touches. Never import data into source or put it in `public/`: the first freezes it into the build, the second
copies an old file over the live one on every build. It takes one of two shapes; choose per kind of data, and an app
can have both:

| | JSON files (`data.json`, any names) | The app's database (`app.db`, below) |
|---|---|---|
| For | a document written whole: settings, a snapshot a routine replaces, a report, an edition | **records**: rows the page lists, searches, filters, pages through, adds, edits or deletes |
| Read | `useJSON('data.json')`: the whole file, every time | `useQuery('SELECT …')`: only the rows a screen needs |
| Written by | Hermes or a routine, replacing the file | the page (`db`), actions, routines and `server.ts`, at once, safely |
| Grows to | tens of KB; a file over ~200 KB is a sign it's records | hundreds of thousands of rows |

Reach for the database when any of these is true: the page changes the data; more than one writer touches it
(the phone and Desktop, a routine and the page); it's a list that grows (a ledger, a log, a history, a reading
list); or the page would otherwise download far more than it shows. Keeping history (each day's balances, not
only today's) is a reason too.

## Actions: changing things from the page

A page can't write files itself. When it needs to change something on this machine (save settings, edit a list,
start a routine, record what the user did), give the app an **action**: a Python script in its built folder,

    ~/.hermes/talaria/apps/<name>/actions/<action>.py

and call it from the page:

```tsx
import { action } from 'talaria'
const saved = await action('settings', { op: 'save', topics })
```

- The script gets the request as JSON on stdin, runs in the app's folder, and prints one JSON value (64 KB at most)
  as the answer. Exit non-zero (`sys.exit("message")`) to fail; `action()` throws with that message.
- Standard library only, and quick: it has two minutes, and the phone waits.
- Put actions in the built folder, not the source: a build never touches them, and only you can add one.
- Anything fetched from a URL the user typed must be public https only (resolve it and refuse private addresses,
  on redirects too); never fetch the machine itself.
- `action()` throws `ActionsUnavailable` on a Talaria that can't run actions yet; show "Update Talaria" for it.
- The preview and the dev server run actions too, so try them there before handing the app back.

## A database: records the page queries and changes

When the app keeps **records** (trips, expenses, notes, a log, anything the page lists, filters, adds to or edits,
or that more than one writer touches), give it its own SQLite database rather than a JSON file. Settings and
what a routine publishes whole can stay JSON.

1. **Check first**, once per machine: `python3 ~/.hermes/plugins/talaria/db.py --check`. It prints JSON with
   `ok`, what this machine is (`system`), and under `fix`, the steps for anything missing. If `ok` is false, work
   through `fix`: try each `try` in order until `--check` passes, choosing what suits `system`. Ask the user before
   anything that needs sudo or installs system-wide. Python's SQLite is required; Node's matters only for `server.ts`.
2. **Write the schema as migrations** in the built folder, beside `actions/`:

       ~/.hermes/talaria/apps/<name>/migrations/001-trips.sql
       ~/.hermes/talaria/apps/<name>/migrations/002-trip-notes.sql

   Numbered from 1 with no gaps, plain SQL, no `BEGIN`/`COMMIT` (each run is one transaction). Never edit or
   renumber one that has run: add the next. The plugin applies them after a build and before the page or an action
   uses the database (`db.py <name>` applies them now).
3. **Use it from the page:**

```tsx
import { db, useQuery } from 'talaria'
const { rows: trips, error, refresh } = useQuery<Trip>('SELECT * FROM trips WHERE year = ? ORDER BY start DESC LIMIT 50', [year])

async function add(name: string) {
  await db.run('INSERT INTO trips (name, start) VALUES (?, ?)', [name, today])
  refresh()
}
```

`useQuery` reads on mount and again when its SQL or params change, or on `refresh()`; it keeps the last rows while
the next ones load. The rest of `db`:

```tsx
const trip = await db.get<Trip>('SELECT * FROM trips WHERE id = ?', [id])
const { lastId } = await db.run('INSERT INTO trips (name, start, meta) VALUES (?, ?, ?)', [name, start, { tags }])
await db.batch([['UPDATE trips SET done = 1 WHERE id = ?', [id]], ['DELETE FROM drafts WHERE trip = ?', [id]]])
```

- **Make writes feel instant**: update what the screen shows first, then write, then `refresh()`; if the write
  throws, put it back and say so. Disable a button only while its own write is in flight.
- Show loading (keep the last rows, or a skeleton the size of the list), empty ("No trips yet" and the way to add
  one) and error states; `error.message` is readable.
- One statement per call; `batch` for several that must land together. Always parameters (`?` or `:name`), never
  values pasted into SQL. Objects and arrays in params are stored as JSON text (`json_extract` reads them).
- Answers are capped at 64 KB: `LIMIT` and page lists. Each call is a round trip to this machine, so read what
  a screen needs in one or two queries.
- The page can't `ATTACH`, set a `PRAGMA` or reach another app's database; it throws like a failed action.
- **Load bulk data with a script, not a migration.** Migrations are the schema (and a few fixed rows). Importing
  a ledger or an API's records is a Python script (or a routine) that opens `app.db` and inserts in one
  transaction with `executemany`, upserting (`INSERT … ON CONFLICT(id) DO UPDATE`) so running it again is safe.
- **Design the schema for the screens**: a primary key on every table, an index on what the page filters and sorts
  by, dates as ISO text (`'2026-10-25'`, so `substr`, `strftime` and sorting work), money as integer minor units
  or REAL consistently, JSON in a TEXT column for loose detail. Let SQL do the work: `GROUP BY` for totals,
  `LIMIT`/`OFFSET` for pages, `LIKE` or FTS5 for search, views for derived numbers the page and a routine share.
- Actions and routines open the same file with Python's `sqlite3`: `os.environ["TALARIA_DB"]` in an action,
  `~/.hermes/talaria/apps/<name>/app.db` in a routine. Use `timeout=5` and keep transactions short.
- Look at it yourself with `python3 ~/.hermes/plugins/talaria/db.py <name> "SELECT …"`, and use it to check what the
  page wrote after you try it in the preview.
- **Moving an app from JSON**: add the migration, load the file's records with a script, switch the page to
  `useQuery`, build, check the counts match, and only then remove the JSON (or keep it if a routine still writes it,
  and have the routine write the database instead).

## A server of its own

For more than an action (an API the page calls often, data computed on request), give the app a `server.ts` beside
`App.tsx`. The dev server answers `/<name>/api/…` with its default export, which gets a `Request` and answers a
`Response`; it runs on this machine with Node, and editing it takes effect on the next call:

```ts
export default async function (req: Request, ctx: { app: string; dir: string }) {
  const url = new URL(req.url)  // /<name>/api/…
  return Response.json({ ok: true })
}
```

The page calls it as `fetch('api/totals')`. `ctx.dir` is the app's data folder, and `await ctx.db()` its database
(migrated, kept open; `prepare(sql).all(...)`, `.get`, `.run`, `exec`). A request that changes something
must come from the app's own page (the server refuses another site's). The server is never sent to the page. It runs
only on the dev server, so the phone, which opens the build, can't call it yet: use actions for what the phone needs.

## Hand it back

Once you've looked at it (see "Look at it before you hand it back" below), end your reply with the app's page on a
line of its own, so Talaria shows a card that opens it:

    MEDIA:/root/.hermes/talaria/apps/<name>/index.html

Use the absolute path of the **built** page, so build first. (An older app with pages of its own: when the change
is on one page, hand back that page, `MEDIA:/root/.hermes/talaria/apps/<name>/trip.html`.) Before the card, say in a
sentence or two what you built or changed. In Hermes Desktop the app is in Talaria's Apps page, live.

## Apps from before the workspace

Older apps are plain folders in `~/.hermes/talaria/apps/<name>/` (an `index.html` with `app.js`, htm, or `.jsx`
files Talaria compiles as it serves them) with no source in the workspace. They keep working. For a small fix,
edit them in place. For a real change, migrate it into the workspace:

    python3 ~/.hermes/plugins/talaria/build.py migrate <name>

1. It sets up the rewrite without touching the live app: a source folder from the template under the app's old
   title, and a copy of the old code (its `.html`, `.js`, `.jsx`, `.tsx`, `.ts` and `.css`) in
   `~/.hermes/talaria/workspace/legacy/<name>/` to work from. (`--new` refuses an older app, since it would
   replace it.)
2. Rewrite the app in React as `workspace/apps/<name>/App.tsx`, reading the old code for what it did, reusing
   `shared/`. Point it at the same data files, by relative paths (`fetch('data.json')`).
3. Build it when the rewrite is ready. The first build replaces the old code in the built folder with the new
   build. Its data, images and any routine's scripts stay where they are, so a routine that writes them keeps
   working.

## Charts: use `viz`, not Chart.js

`viz` is Datagen's chart kit. It's hand-drawn SVG: quiet gridlines, rounded bar ends, hover tooltips, a
colour-blind-safe palette, and light and dark modes. It looks far better than library defaults.

- **`<Grid>`** lays panels out on 12 columns. On a phone, half and third widths take the full width.
- **`<Panel title description width chart rows formats height>`** is a card with a chart.
  - `width` is `full`, `half`, `third` or `quarter`.
  - `rows` is an array of objects.
  - `chart` is one of:
    - `{ type: 'line' | 'area', x, y, series }`. `y` is a column or a list of columns. `series` splits one `y` by
      another column. An area chart can also take `stacked: true`.
    - `{ type: 'bar', x, y, series, stacked, horizontal }`. Use `horizontal` when labels are long.
    - `{ type: 'scatter', x, y, series, label }`
    - `{ type: 'number', value, compare, caption, good: 'up' | 'down' }`
  - A Panel can also hold any children instead of a chart.
- **`<Stat title value compare good format width>`** is a headline number with its change. Use `good="down"`
  when a fall is good news.
- **`<Chart chart rows formats height>`** is a chart without the card.
- **`formats`** maps a column to how its values read:
  - `'number'`, `'integer'`, `'compact'` (1.2K)
  - `'currency'` or `{ currency: 'PHP' }`
  - `'percent'` (0.125 reads as 12.5%)
  - `'date'`, `'month'`, `'text'`
- **Colours:** `setChartTheme(name)` picks a set: `datagen` (the default), `ocean`, `nordic`, `forest`, `earth`,
  `sunset`, `berry`, `candy`, `pastel`, `retro`, `neon`, `vivid`, `ink` or `classic`. For colours of your own,
  pass `setChartTheme(defineChartTheme({ label, description, light: { series: [8 colours] }, dark: { series: [...] } }))`.
- **Matching your design:** the charts read CSS variables, so an app restyles them by setting these:
  - `--surface`, `--border`, `--text`, `--text-muted` and `--bg`
  - `--series-1` … `--series-8`, `--chart-grid` and `--chart-axis`
- Reach for d3 when you need something `viz` doesn't draw: maps, networks, calendars, radial charts.

## Design

- **Give each app its own identity** to fit what it's for. Choose the layout, type, colour, imagery and motion
  yourself; it does not have to look like Talaria.
  - A dark theme, a display face from Google Fonts, gradients and texture are all fine when they serve the content.
- **It's a phone.**
  - Design for about 400pt wide, one column.
  - Make thumb-sized targets (44pt or more).
  - Never scroll sideways. The template's CSS clips the page and wraps long strings; keep both if you replace it,
    and give any scroller of its own (a swipe row, a reader) `overflow-x: hidden` or `overflow-wrap: anywhere`.
- **Keep it compact.** Phones reward density; air is for separating groups, not filling the screen.
  - Gaps of 8–12px between items and 16–20px between sections; card padding 12–14px; 16px side margins.
  - Body text 15–16px, labels 12–13px. A headline over 28px only when it's the point of the page.
  - Show the useful content in the first screenful: no tall hero or banner unless the request calls for one,
    and then keep it under about a third of the screen.
- **It runs edge to edge under Talaria's floating top bar.**
  - Keep `viewport-fit=cover`.
  - Start the content right under the top bar: pad the top by `env(safe-area-inset-top)` (the status bar) plus
    48px (the bar's buttons), no more, and give the first heading no top margin; pad the bottom by
    `env(safe-area-inset-bottom)` plus 16px.
  - A background, though, should run to the edges.
- **Support light and dark** with `prefers-color-scheme`, unless the design is deliberately one or the other.
- **It also opens in Hermes Desktop**, in a pane about 800px wide or more, with no Talaria top bar over it. Keep the
  phone layout for narrow widths, and from about 760px use the room: move bottom tabs into a top bar, drop the
  top padding the phone's buttons need, put lists in columns or a grid, and add a side rail when there's 1100px
  or more. Give titles and cards hover states.
- **Make it feel alive.**
  - Animate things in with Motion.
  - Give tap feedback.
  - Use real interactions (tabs, filters, sheets, drag) over static text.
- **Data:**
  - Put real data in the app's built folder, never in source: JSON files for documents, the app's database for
    records ("Data", above).
  - When it should stay current, offer to set up a routine (a cron job) that refreshes it (rewrites the JSON, or
    upserts into the database), so the app stays live without being rebuilt.
  - With a database, use it: search, filters, sorting and paging done by queries, and a tap that opens the rows
    behind a total, instead of a page that only shows what a file precomputed.

## Look at it before you hand it back

Don't stop when it builds. An app isn't done until you've seen it on a phone-sized screen and it looks right.
Every time you build or change one:

1. **Build it** (`build.py <name>`), and fix any error it prints.
2. **Start the preview.** It serves the built app the way Talaria does:

       python3 ~/.hermes/plugins/talaria/preview.py <name>

   It prints two addresses: `phone:` frames the app at iPhone size, between a drawn status bar and home
   indicator, under Talaria's floating Back and ⋯ buttons; `alone:` is the app by itself. The server keeps
   running, so later calls return at once, and it always serves the latest build.
3. **Look at it.** Open the `phone:` address with `browser_navigate`, then use `browser_vision` and ask about it
   critically, as the user would see it:
   - Does anything overflow, get cut off, overlap, or scroll sideways?
   - Does the content start right under the floating buttons, with nothing hidden behind them?
   - Is the text legible, and are the targets thumb-sized?
   - Do the charts and data show real values, with no blank panels, `NaN` or `undefined`?
   - With a database: add, edit and delete something, reload, and check it stayed (`db.py <name> "SELECT …"`).
   - Does it look intentional and finished, or like a rough draft?
   Scroll and look again when the page is longer than one screen.
4. **Check for errors.** Open the `alone:` address and read `browser_console`. Fix every error and failed
   request.
5. **Look at it as Desktop shows it**, live from the dev server:

       python3 ~/.hermes/plugins/talaria/appserver.py <name>

   prints its address (starting the server if it isn't running). Open it at about 1200px and 800px wide, and call
   the app's `server.ts`, if it has one, from the page.
6. **Go through every page you built or changed.** Frame a subpage with `/__phone/<page>` (for example
   `http://<name>.localhost:8797/__phone/trip.html`), and click the main interactions (tabs, filters, sheets)
   with the browser tools.
7. **Fix what you find, build, then look again.** Repeat until there is nothing left to fix. Only then hand it back.

In your reply, say briefly what you checked and anything you fixed after looking. If the build, the preview or the
browser fails, say so plainly; don't claim it looked fine.
