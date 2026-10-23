---
name: app
description: "Use when the user asks for an app, or for a dashboard, tracker, planner, report, tool or any page or small app to look at in Talaria (their iPhone app). Covers where apps live, the libraries Talaria has built in, how to design one, and how to hand it back so it opens in the app."
version: 1.1.0
author: Sageware Solutions Inc.
metadata:
  hermes:
    tags: [talaria, app, web, dashboard, ui, charts]
---

# Talaria apps

An app is a small web app the user opens full screen in Talaria, their iPhone app for Hermes. It's yours to
build and rebuild freely, and it can be anything a web page can be: a live dashboard, a tracker, a planner, a
report, a game, a control panel. Be ambitious. An app is a whole app, not a widget.

## Where it lives

Each app is a folder on this machine:

    ~/.hermes/talaria/apps/<name>/index.html

- `<name>` is short kebab-case (`spending`, `hiring-pipeline`, `cebu-trip`). Create the folders if they're missing.
- `index.html` is the entry. Put anything else beside it: more pages, ES modules, components, CSS, images, and
  JSON data. Everything loads by path within the folder (`./app.js`, `fetch('/data.json')`).
- The page's `<title>` is the app's name in Talaria. Keep it short.
- To change an app, edit its folder in place; `ls ~/.hermes/talaria/apps` lists them all. To delete one,
  remove its folder.

## Pages and state

An app can have as many pages as it needs. Talaria is its browser: links between its pages open in place, and
Talaria's Back button (and the edge swipe) walks back through them before it leaves the app.

- **Pages are files.** `trip.html` beside `index.html`, or a folder with its own `index.html`. Link them with
  relative hrefs: `<a href="./trip.html#tokyo">`, `<a href="./cebu/">` (keep the trailing slash on a folder).
- **`/` is the app's root** on every page, so a nested page reaches shared files as `fetch('/data.json')`,
  `import '/app.js'` and `<link href="/style.css">`. Use these root paths for anything more than one page shares.
- **One-page apps work too.** Route with the hash (`#/settings`, `#/trip/tokyo`); each route counts as a page for
  Back. The History API works as well: a reload of a route that isn't a file serves the root `index.html`, so
  load its scripts and styles by root paths.
- **Each app keeps its own state.** `localStorage` and IndexedDB persist on the phone between launches, shared
  by every page of that app and private to it. Use them for what the user does on the phone: checked items,
  filters, drafts, the last tab. That state stays on the phone; data that Hermes or a routine writes belongs in the
  app's JSON files.
- Give each page its own `<title>`, and lay out every page under the top bar like the first (below).

## Hand it back

End your reply with the app's page on a line of its own, so Talaria shows a card that opens it:

    MEDIA:/root/.hermes/talaria/apps/<name>/index.html

Use the absolute path. When the change is on one page, hand back that page instead
(`MEDIA:/root/.hermes/talaria/apps/<name>/trip.html`) and the card opens straight to it. Before the card, say
in a sentence or two what you built or changed.

## What's built in

Talaria serves these from itself, offline, with no build step. It adds an import map to every app page,
so `<script type="module">` can import them by name:

| import | what |
|---|---|
| `react`, `react-dom/client` | React 19 |
| `html` | htm bound to React: JSX-like markup with no compiler, ``html`<${Card} title=${t}>…</${Card}>` `` |
| `viz` | Datagen's charts (below) |
| `motion/react` | Motion: animation, gestures, layout transitions, `AnimatePresence` |
| `lucide-react` | Lucide icons as components (`<${Wallet} size=${16} />`) |
| `d3` | d3 v7, for anything custom (scales, shapes, maps, force layouts) |

Classic scripts and styles at `/lib/`:
- `/lib/tailwind.js`: the Tailwind v4 browser build, for utility classes in markup.
- `/lib/alpine.js`: Alpine.js. Load it with `defer`.
- `/lib/viz.css`: the styles the `viz` charts need.
- `/lib/talaria.css`: Talaria's own look, but only if you want it.

Anything from an https CDN works too, but the built-ins work offline and load instantly; prefer them.

A skeleton:

```html
<!doctype html>
<html><head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Spending</title>
  <link rel="stylesheet" href="/lib/viz.css">
  <style>
    body { margin: 0; font: 15px/1.45 -apple-system, system-ui, sans-serif;
           padding: calc(env(safe-area-inset-top) + 48px) 16px calc(env(safe-area-inset-bottom) + 16px); }
  </style>
</head><body>
  <div id="app"></div>
  <script type="module">
    import { createRoot } from 'react-dom/client'
    import { useState } from 'react'
    import html from 'html'
    import { Grid, Panel, Stat } from 'viz'
    import { motion } from 'motion/react'

    const rows = await fetch('./data.json').then(r => r.json())
    function App() {
      return html`<${Grid}>
        <${Stat} title="This month" value=${618000} compare=${561000} format=${{ currency: 'PHP' }} />
        <${Panel} title="Revenue" chart=${{ type: 'area', x: 'month', y: 'revenue' }} rows=${rows} />
      <//>`
    }
    createRoot(document.getElementById('app')).render(html`<${App} />`)
  </script>
</body></html>
```

## Charts: use `viz`, not Chart.js

`viz` is Datagen's chart kit. It's hand-drawn SVG: quiet gridlines, rounded bar ends, hover tooltips, a
colour-blind-safe palette, and light and dark modes. It looks far better than library defaults.

- **`<${Grid}>`** lays panels out on 12 columns. On a phone, half and third widths take the full width.
- **`<${Panel} title description width chart rows formats height>`** is a card with a chart.
  - `width` is `full`, `half`, `third` or `quarter`.
  - `rows` is an array of objects.
  - `chart` is one of:
    - `{ type: 'line' | 'area', x, y, series }`. `y` is a column or a list of columns. `series` splits one `y` by
      another column. An area chart can also take `stacked: true`.
    - `{ type: 'bar', x, y, series, stacked, horizontal }`. Use `horizontal` when labels are long.
    - `{ type: 'scatter', x, y, series, label }`
    - `{ type: 'number', value, compare, caption, good: 'up' | 'down' }`
  - A Panel can also hold any children instead of a chart.
- **`<${Stat} title value compare good format width>`** is a headline number with its change. Use `good="down"`
  when a fall is good news.
- **`<${Chart} chart rows formats height>`** is a chart without the card.
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
  - Never scroll sideways.
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
  - Put real data in JSON files beside the page, and have the page read them.
  - When it should stay current, offer to set up a routine (a cron job) that refreshes the JSON, so the app
    stays live without being rebuilt.
- **Check your work** before handing it back:
  - Every file you reference exists.
  - The HTML is complete.
  - Module scripts parse: `node --check` on any `.js` you wrote.
