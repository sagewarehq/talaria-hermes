---
name: app
description: "Use when the user asks for an app, or for a dashboard, tracker, planner, report, tool or any page or small app to look at in Talaria (their iPhone app). Covers the Vite + React workspace apps are built in, the packages it has, how to design one, and how to hand it back so it opens in the app."
version: 2.2.0
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
      apps/<name>/index.html, main.tsx, …   one app's source
      talaria/                              Talaria's own (the build config, viz); replaced on every build, don't edit
    ~/.hermes/talaria/apps/<name>/          the built app, which the phone opens, plus its data files

- `<name>` is short kebab-case (`spending`, `hiring-pipeline`, `cebu-trip`).
- Write source only in `workspace/apps/<name>/` and `workspace/shared/`. The built folder is the build's output,
  except for data files (below).
- `ls ~/.hermes/talaria/workspace/apps` lists the apps; `ls ~/.hermes/talaria/apps` lists what Talaria shows. To
  delete an app, remove both folders.

## Build it

    python3 ~/.hermes/plugins/talaria/build.py --new <name>    start an app from the template, and build it
    python3 ~/.hermes/plugins/talaria/build.py <name>          build it after every change to its source
    python3 ~/.hermes/plugins/talaria/build.py --all           build every app, after a change to shared/
    python3 ~/.hermes/plugins/talaria/build.py add <pkg>…      add npm packages to the workspace
    python3 ~/.hermes/plugins/talaria/build.py migrate <name>  move an older app in (below)

- **Build after every change to source**, then look at it (below). Talaria shows the last good build: a failed
  build changes nothing there and prints the error with its file and line. Fix it and build again.
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

Tailwind v4 is set up: a CSS file with `@import "tailwindcss";` and `@source "../../shared";` (so classes in
shared components count), imported from `main.tsx`. Anything else: `build.py add <pkg>`, then import it. Packages
are bundled into the app, so it doesn't depend on a CDN.

`shared/` starts with:
- `Screen` (`@shared/Screen`): a page laid out under Talaria's top bar, with the right safe-area padding.
- `useJSON(path)` (`@shared/useJSON`): fetches one of the app's data files, never cached.

Add to it whatever a second app would otherwise copy: a theme, a card, a data hook. After changing it, build with
`--all`, since every app that imports it has the old copy until it's rebuilt.

`--new` starts an app with this skeleton, in `workspace/apps/<name>/`. `index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <title>Spending</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="./main.tsx"></script>
  </body>
</html>
```

`main.tsx` renders `<App />` into `#app` and imports `./style.css`; `App.tsx` is the app. The page's `<title>` is
the app's name in Talaria; keep it short.

## Pages and state

An app can have as many pages as it needs. Talaria is its browser: links between its pages open in place, and
Talaria's Back button (and the edge swipe) walks back through them before it leaves the app.

- **Pages are HTML files.** `trip.html` beside `index.html` (with its own `<script type="module"
  src="./trip.tsx">`), or a folder with its own `index.html`. Every `.html` in the app's source is built as a page.
  Link them with relative hrefs: `<a href="./trip.html#tokyo">`, `<a href="./cebu/">` (keep the trailing slash).
- **`/` is the app's root** on every page, so any page fetches data as `fetch('/data.json')`.
- **One-page apps work too.** Route with the hash (`#/settings`, `#/trip/tokyo`); each route counts as a page for
  Back. The History API works as well: a reload of a route that isn't a file serves the root `index.html`.
- **Each app keeps its own state.** `localStorage` and IndexedDB persist on the phone between launches, shared
  by every page of that app and private to it. Use them for what the user does on the phone: checked items,
  filters, drafts, the last tab. That state stays on the phone; data that Hermes or a routine writes belongs in the
  app's JSON files.
- Give each page its own `<title>`, and lay out every page under the top bar like the first (below).

## Data

Data that Hermes or a routine writes lives in the **built** folder, `~/.hermes/talaria/apps/<name>/data.json`
(any names, any number of files), and the app fetches it at runtime. A build never touches those files. Never
import data into source or put it in `public/`: the first freezes it into the build, the second copies an old file
over the live one on every build.

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
- The preview runs actions too, so try them there before handing the app back.

## Hand it back

Once you've looked at it (see "Look at it before you hand it back" below), end your reply with the app's page on a
line of its own, so Talaria shows a card that opens it:

    MEDIA:/root/.hermes/talaria/apps/<name>/index.html

Use the absolute path of the **built** page. When the change is on one page, hand back that page instead
(`MEDIA:/root/.hermes/talaria/apps/<name>/trip.html`) and the card opens straight to it. Before the card, say
in a sentence or two what you built or changed.

## Apps from before the workspace

Older apps are plain folders in `~/.hermes/talaria/apps/<name>/` (an `index.html` with `app.js`, htm, or `.jsx`
files Talaria compiles as it serves them) with no source in the workspace. They keep working. For a small fix,
edit them in place. For a real change, migrate it into the workspace:

    python3 ~/.hermes/plugins/talaria/build.py migrate <name>

1. It sets up the rewrite without touching the live app: a source folder from the template under the app's old
   title, and a copy of the old code (its `.html`, `.js`, `.jsx`, `.tsx`, `.ts` and `.css`) in
   `~/.hermes/talaria/workspace/legacy/<name>/` to work from. (`--new` refuses an older app, since it would
   replace it.)
2. Rewrite the app in React in `workspace/apps/<name>/`, reading the old code for what it did, reusing `shared/`.
   Point it at the same data files (`fetch('/data.json')`).
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
- **Make it feel alive.**
  - Animate things in with Motion.
  - Give tap feedback.
  - Use real interactions (tabs, filters, sheets, drag) over static text.
- **Data:**
  - Put real data in JSON files in the app's built folder (`~/.hermes/talaria/apps/<name>/data.json`), and have
    the page fetch them (`useJSON('/data.json')` from `@shared/useJSON`). Never import data or put it in
    `public/`: a build would freeze it, or copy an old file over the live one.
  - When it should stay current, offer to set up a routine (a cron job) that refreshes the JSON, so the app
    stays live without being rebuilt.

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
   - Does it look intentional and finished, or like a rough draft?
   Scroll and look again when the page is longer than one screen.
4. **Check for errors.** Open the `alone:` address and read `browser_console`. Fix every error and failed
   request.
5. **Go through every page you built or changed.** Frame a subpage with `/__phone/<page>` (for example
   `http://<name>.localhost:8797/__phone/trip.html`), and click the main interactions (tabs, filters, sheets)
   with the browser tools.
6. **Fix what you find, build, then look again.** Repeat until there is nothing left to fix. Only then hand it back.

In your reply, say briefly what you checked and anything you fixed after looking. If the build, the preview or the
browser fails, say so plainly; don't claim it looked fine.
