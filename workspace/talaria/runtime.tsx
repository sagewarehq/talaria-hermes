// Mounts an app: its App.tsx's default export into the page's root, with its `meta` (title, icon, theme colours)
// applied to the page. Owned by the plugin, which replaces this folder on every build.
import type { ComponentType } from 'react'
import { createRoot } from 'react-dom/client'

export interface Meta {
  /** The page's title, and the app's name in lists. */
  title?: string
  /** Its icon in Talaria's lists and sidebars, from a fixed set (appprefs.py's ICONS); the user can pick another. */
  glyph?: string
  /** An image in the app's folder, as a path relative to it: './favicon.svg'. */
  icon?: string
  /** The browser chrome's colour in light and dark mode. */
  theme?: { light?: string; dark?: string } | string
}

declare global {
  interface Window { __TALARIA__?: { app: string } }
}

/** Chromium's Navigation API (Desktop is Electron): the part used here, which not every TypeScript's DOM types have. */
const navigation = (window as unknown as { navigation?: {
  canGoBack: boolean
  canGoForward: boolean
  back(): { finished: Promise<unknown> }
  forward(): { finished: Promise<unknown> }
  addEventListener(type: 'currententrychange', listener: () => void): void
} }).navigation

function head(tag: string, attrs: Record<string, string>) {
  const el = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v)
  document.head.appendChild(el)
}

/** In Hermes Desktop the app is a sandboxed frame: it can't open a window or write the clipboard. Desktop's Talaria
 *  plugin says hello once the frame loads; from then on, links that leave the app (external ones, target="_blank"),
 *  window.open and clipboard writes go to it instead. Without that hello (the phone, the preview) nothing changes. */
function desktopHost() {
  if (window.parent === window) return
  let host: { source: MessageEventSource; origin: string } | null = null
  let next = 0
  const waiting = new Map<number, (ok: boolean) => void>()
  const ask = (talaria: string, fields: Record<string, string>) => new Promise<boolean>((resolve) => {
    if (!host) return resolve(false)
    const id = ++next
    waiting.set(id, resolve)
    ;(host.source as Window).postMessage({ talaria, id, ...fields }, host.origin)
  })
  addEventListener('message', (e) => {
    if (e.source !== window.parent || typeof e.data?.talaria !== 'string') return
    if (e.data.talaria === 'host' && !host) {
      // Desktop's page is a file, whose origin is opaque ("null") and can't be named as a target: answer the parent
      // (and only it, by source) with "*" then. What goes up is a link or text the app chose to hand over; what the
      // page shows goes to Hermes only while you share it (share, below), and through the dev server, not this.
      host = { source: e.source, origin: e.origin === 'null' ? '*' : e.origin }
      install(ask)
      pages(host)
    } else if (e.data.talaria === 'share' && host) {
      share(Boolean(e.data.on))
    } else if (e.data.talaria === 'back' || e.data.talaria === 'forward') {
      void navigation?.[e.data.talaria as 'back' | 'forward']().finished.catch(() => {})
    } else if (e.data.talaria === 'answer') {
      waiting.get(e.data.id)?.(Boolean(e.data.ok))
      waiting.delete(e.data.id)
    }
  })
}

/** Desktop's Back and Forward walk the app's own pages. The frame shares its history with Desktop's window, so
 *  history.back() on the app's first page would leave Desktop's page: the Navigation API counts only this frame's
 *  entries. Where the app is (its page, past /<app>/) goes up too, for "Ask Hermes to change it". */
function pages(host: { source: MessageEventSource; origin: string }) {
  const nav = navigation
  if (!nav) return
  const tell = () => {
    const at = location.pathname.split('/').slice(2).join('/')
    const page = at === 'index.html' ? '' : at
    ;(host.source as Window).postMessage({ talaria: 'nav', back: nav.canGoBack, forward: nav.canGoForward, page }, host.origin)
  }
  nav.addEventListener('currententrychange', tell)
  tell()
}

/** While you share this page with Hermes (Desktop's toggle), it keeps the dev server's page channel open
 *  (serve.mjs) and, each time Hermes asks, answers with what it shows: app_snapshot. Nothing goes up otherwise. */
let watching: EventSource | null = null
function share(on: boolean) {
  const app = window.__TALARIA__?.app
  if (!on || !app) {
    watching?.close()
    watching = null
    return
  }
  if (watching) return
  watching = new EventSource(`/${app}/__page/watch`)
  watching.addEventListener('snapshot', (e) => {
    const { id } = JSON.parse((e as MessageEvent).data)
    void fetch(`/${app}/__page/answer`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Talaria-Page': '1' },
      body: JSON.stringify({ id, snapshot: snapshot() }),
    }).catch(() => {})
  })
}

const MAX_TEXT = 60_000
const MAX_VISIBLE = 8_000

/** What the page shows: its title and page, the part in view, all of its readable text, and any selection. */
function snapshot() {
  const tidy = (text: string) => text.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim()
  const at = location.pathname.split('/').slice(2).join('/')
  const all = tidy(document.body.innerText)
  const scrolled = document.scrollingElement
  return {
    title: document.title,
    page: at === 'index.html' ? '' : at,
    query: location.search,
    visible: tidy(inView()).slice(0, MAX_VISIBLE),
    text: all.slice(0, MAX_TEXT),
    truncated: all.length > MAX_TEXT,
    selection: String(getSelection() ?? '').trim().slice(0, MAX_VISIBLE) || undefined,
    scroll: scrolled && scrolled.scrollHeight > innerHeight
      ? Math.round(scrolled.scrollTop / (scrolled.scrollHeight - innerHeight) * 100) : undefined,
  }
}

/** The text in the window right now, block by block: what you'd read if you looked up. */
function inView() {
  const blocks: string[] = []
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  let last: Element | null = null
  for (let node = walk.nextNode(); node; node = walk.nextNode()) {
    const el = node.parentElement
    if (!el || !node.textContent?.trim() || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName)) continue
    const box = el.getBoundingClientRect()
    if (box.bottom <= 0 || box.top >= innerHeight || box.right <= 0 || box.left >= innerWidth || el.checkVisibility?.() === false) continue
    const block = el.closest('p,li,h1,h2,h3,h4,h5,h6,td,th,figcaption,blockquote,pre,button,label,div') ?? el
    blocks.push((block === last ? ' ' : '\n') + node.textContent.replace(/\s+/g, ' ').trim())
    last = block
  }
  return blocks.join('')
}

function install(ask:(talaria: string, fields: Record<string, string>) => Promise<boolean>) {
  const leaves = (url: URL) => url.origin !== location.origin || /^(mailto|tel):/.test(url.protocol)
  document.addEventListener('click', (e) => {
    const a = (e.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null
    if (!a || e.defaultPrevented || e.button !== 0) return
    const url = new URL(a.href, location.href)
    if (a.target === '_blank' || leaves(url)) {
      e.preventDefault()
      void ask('open', { url: url.href })
    }
  })
  window.open = (target?: string | URL) => {
    if (target) void ask('open', { url: new URL(String(target), location.href).href })
    return null
  }
  // The share sheet can't open from the frame (it would fail as if cancelled), so apps fall back to copying.
  Object.defineProperty(navigator, 'share', { configurable: true, value: undefined })
  const clipboard = navigator.clipboard
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: Object.assign(Object.create(clipboard ?? null), {
      writeText: (text: string) => ask('copy', { text: String(text) }).then((ok) => {
        if (!ok) throw new DOMException('Desktop couldn’t copy that.', 'NotAllowedError')
      }),
    }),
  })
}

export function boot(mod: { default: ComponentType; meta?: Meta }, app: string) {
  window.__TALARIA__ = { app }
  desktopHost()
  const meta = mod.meta ?? {}
  if (meta.title) document.title = meta.title
  if (meta.icon) head('link', { rel: 'icon', href: meta.icon })
  const theme = typeof meta.theme === 'string' ? { light: meta.theme, dark: meta.theme } : meta.theme
  if (theme?.light) head('meta', { name: 'theme-color', content: theme.light, media: '(prefers-color-scheme: light)' })
  if (theme?.dark) head('meta', { name: 'theme-color', content: theme.dark, media: '(prefers-color-scheme: dark)' })
  const App = mod.default
  createRoot(document.getElementById('app')!).render(<App />)
}
