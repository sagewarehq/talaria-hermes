// What the workspace dev server (serve.mjs) and the phone's build (vite.config.mjs) agree on: which folders are
// apps, the page every app gets, and the entry that mounts its App.tsx. Owned by the plugin, which replaces this
// folder on every build.
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const workspace = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
export const NAME = /^[a-z0-9][a-z0-9_-]*$/
// Paths the dev server itself answers, so no app can be named after one.
export const RESERVED = new Set(['apps', 'shared', 'talaria', 'node_modules', 'lib', 'legacy', 'assets'])
export const ENTRY = '/@talaria/entry/'

export const appDir = (app) => path.join(workspace, 'apps', app)
/** An app the dev server runs: a folder in apps/ with an App.tsx (or .jsx) that exports the app as its default. */
export const appFile = (app) => ['App.tsx', 'App.jsx'].map((f) => path.join(appDir(app), f)).find((f) => existsSync(f))
export const isApp = (app) => NAME.test(app) && !RESERVED.has(app) && Boolean(appFile(app))

export const aliases = [
  { find: /^@shared\//, replacement: path.join(workspace, 'shared') + '/' },
  { find: /^viz$/, replacement: path.join(workspace, 'talaria', 'viz', 'entry.ts') },
  { find: /^talaria$/, replacement: path.join(workspace, 'talaria', 'sdk.ts') },
]

/** The title in the app's `export const meta = { title: '…' }`, read without running it. */
export function title(app) {
  const m = /export\s+const\s+meta\s*(?::[^=]+)?=\s*\{[^}]*?\btitle\s*:\s*(['"`])(.*?)\1/s.exec(readFileSync(appFile(app), 'utf8'))
  return m ? m[2] : app
}

const escape = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const COLOR = /^(#[0-9a-f]{3,8}|[a-z]+|(rgb|hsl|oklch)a?\([0-9.,%\s/-]+\))$/i

/** The background the page paints before any of the app's code or CSS arrives, and between reloads: the app's
 *  `meta.theme` colours when it has them, else the browser's own canvas, light or dark with the system. Without it a
 *  dark app flashes white while it loads. */
export function backdrop(app) {
  const text = readFileSync(appFile(app), 'utf8')
  const pick = (key) => {
    const m = new RegExp(`\\b${key}\\s*:\\s*(['"\`])([^'"\`]+)\\1`).exec(/\btheme\s*:\s*\{[^}]*\}/s.exec(text)?.[0] ?? '')
    return m && COLOR.test(m[2].trim()) ? m[2].trim() : null
  }
  const one = /\btheme\s*:\s*(['"`])([^'"`]+)\1/.exec(text)?.[2]?.trim()
  const light = pick('light') ?? (one && COLOR.test(one) ? one : null)
  const dark = pick('dark') ?? (one && COLOR.test(one) ? one : null)
  return [
    ':root{color-scheme:light dark}html{background:Canvas}',
    light ? `@media (prefers-color-scheme:light){html{background:${light}}}` : '',
    dark ? `@media (prefers-color-scheme:dark){html{background:${dark}}}` : '',
  ].join('')
}

/** The page every app gets: a root to mount into, and the entry. Its title, icon and theme colours come from the
 *  app's `meta` export, set as it loads (runtime.tsx). */
export function page(app) {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <meta name="color-scheme" content="light dark" />
    <style>${backdrop(app)}</style>
    <title>${escape(title(app))}</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="${ENTRY}${app}"></script>
  </body>
</html>
`
}

/** The module behind the page's script: the app, then its style.css when it has one (after the app's own imports,
 *  so its rules win over a library's, viz's chart colours say, as they did in a main.tsx), mounted by the runtime. */
export function entry(app) {
  const css = path.join(appDir(app), 'style.css')
  return [
    `import { boot } from ${JSON.stringify(path.join(workspace, 'talaria', 'runtime.tsx'))}`,
    `import * as app from ${JSON.stringify(appFile(app))}`,
    existsSync(css) ? `import ${JSON.stringify(css)}` : '',
    `boot(app, ${JSON.stringify(app)})`,
  ].filter(Boolean).join('\n')
}

/** Resolves and loads the entry, for the dev server and the build alike. */
export function entryPlugin() {
  return {
    name: 'talaria-entry',
    resolveId(id) {
      if (id.startsWith(ENTRY)) return '\0talaria-entry:' + id.slice(ENTRY.length)
    },
    load(id) {
      if (!id.startsWith('\0talaria-entry:')) return
      const app = id.slice('\0talaria-entry:'.length)
      if (!isApp(app)) throw new Error(`No app named ${app}: apps/${app}/App.tsx is missing.`)
      return entry(app)
    },
  }
}
