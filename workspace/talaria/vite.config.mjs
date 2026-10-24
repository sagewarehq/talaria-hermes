// The build of one sub-app. Talaria's build.py runs `vite build --config talaria/vite.config.mjs` from the workspace
// with TALARIA_APP (its folder in apps/) and TALARIA_OUT (where to put it) set. Owned by the plugin, which replaces
// this folder on every build.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { readdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const workspace = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const root = path.join(workspace, 'apps', process.env.TALARIA_APP)

// Every page of the app is an entry, so pages stay pages: index.html, trip.html, cebu/index.html.
function pages(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const file = path.join(dir, e.name)
    if (e.isDirectory()) return e.name === 'public' || e.name === 'node_modules' || e.name.startsWith('.') ? [] : pages(file)
    return e.name.endsWith('.html') ? [file] : []
  })
}

export default defineConfig({
  root,
  base: '/', // each app is its own origin on the phone, in the preview and in Desktop
  publicDir: path.join(root, 'public'),
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      { find: /^@shared\//, replacement: path.join(workspace, 'shared') + '/' },
      { find: /^viz$/, replacement: path.join(workspace, 'talaria', 'viz', 'entry.ts') },
      { find: /^talaria$/, replacement: path.join(workspace, 'talaria', 'sdk.ts') },
    ],
  },
  build: {
    outDir: process.env.TALARIA_OUT,
    emptyOutDir: true, // outside root, so Vite only empties it when told
    target: 'safari17', // the phone's WKWebView
    rollupOptions: { input: Object.fromEntries(pages(root).map((f) => [path.relative(root, f).replace(/\.html$/, ''), f])) },
  },
})
