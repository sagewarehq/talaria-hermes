// The workspace's dev server: every app in apps/ live on one loopback port, with no build step. Talaria's plugin
// starts it (appserver.py) and Desktop, the phone and the preview load apps from it. Owned by the plugin, which
// replaces this folder on every build.
//
//   /<app>/               the app: a page that mounts apps/<app>/App.tsx (apps.mjs), reloading as its code changes
//   /<app>/api/…          apps/<app>/server.ts's default export, called with a Request, answering a Response;
//                         ctx.db() is the app's SQLite database (db.py migrates it, node:sqlite opens it)
//   POST /<app>/__action/<name>   one of the app's actions (actions.py, as on the phone)
//   /<app>/<file>         a file from the app's data folder, ~/.hermes/talaria/apps/<app>/, where routines write
//   /<app>/__page/…       the page channel: what a page shared with Hermes shows, read on the plugin's ask
//   /__talaria/ping       "talaria-apps <stamp>", so the plugin knows this copy is current
//   POST /__talaria/snapshot   the plugin's ask for the shared page (app_snapshot)
//
// Env: TALARIA_PORT, TALARIA_HOME (~/.hermes/talaria), TALARIA_PYTHON and TALARIA_PLUGIN (to run actions),
// TALARIA_STAMP, TALARIA_HOSTS (extra host names to answer to, comma-separated), TALARIA_ADMIN (the plugin's secret
// for /__talaria/gate).
import { spawn } from 'node:child_process'
import { randomBytes, timingSafeEqual } from 'node:crypto'
import net from 'node:net'
import { createReadStream, existsSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'
import { Readable } from 'node:stream'
import { createServer } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { aliases, appDir, entryPlugin, isApp, page, workspace } from './apps.mjs'

const env = process.env
const home = env.TALARIA_HOME || path.join(env.HOME, '.hermes', 'talaria')
const dataRoot = path.join(home, 'apps')
const MAX_BODY = 4 * 1024 * 1024

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.json': 'application/json', '.js': 'text/javascript', '.css': 'text/css',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.webp': 'image/webp', '.avif': 'image/avif', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8', '.md': 'text/markdown; charset=utf-8', '.pdf': 'application/pdf',
  '.woff2': 'font/woff2', '.mp3': 'audio/mpeg', '.mp4': 'video/mp4',
}

function send(res, status, body, type = 'text/plain; charset=utf-8') {
  res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store' })
  res.end(body)
}

/** A request that changes something must come from a page on this same host: another site's page open in the
 *  browser could otherwise post to a server on the machine's loopback. */
function sameOrigin(req) {
  const origin = req.headers.origin
  if (!origin) return true
  try { return new URL(origin).host === req.headers.host } catch { return false }
}

function body(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    let size = 0
    req.on('data', (c) => {
      size += c.length
      if (size > MAX_BODY) { reject(new Error('too large')); req.destroy() } else chunks.push(c)
    })
    req.on('end', () => resolve(Buffer.concat(chunks)))
    req.on('error', reject)
  })
}

function python(args, input = '') {
  return new Promise((resolve) => {
    const child = spawn(env.TALARIA_PYTHON || 'python3', args, { stdio: ['pipe', 'pipe', 'pipe'], env: { ...env, TALARIA_HOME: home } })
    const out = [], err = []
    child.stdout.on('data', (c) => out.push(c))
    child.stderr.on('data', (c) => err.push(c))
    child.on('error', (e) => resolve({ code: 1, out: '', err: String(e) }))
    child.on('close', (code) => resolve({ code, out: Buffer.concat(out).toString(), err: Buffer.concat(err).toString().trim() }))
    child.stdin.end(input)
  })
}

/** Node's own SQLite (22.13+), else better-sqlite3 from the workspace: the same exec/prepare/get/all/run. Neither:
 *  db.py --check says how to add one. */
async function sqlite() {
  try {
    const { DatabaseSync } = await import('node:sqlite')
    return (file) => new DatabaseSync(file)
  } catch {}
  try {
    const { default: Database } = await import('better-sqlite3')
    return (file) => new Database(file)
  } catch {}
  throw new Error(`Node ${process.version} has no SQLite: run python3 ${path.join(env.TALARIA_PLUGIN || '~/.hermes/plugins/talaria', 'db.py')} --check`)
}

/** The app's SQLite database for its server.ts, opened once and kept. The plugin owns its schema: db.py applies the
 *  app's migrations first, again whenever a migration is added. */
const databases = new Map()
function database(app) {
  const folder = path.join(dataRoot, app, 'migrations')
  const steps = existsSync(folder) ? readdirSync(folder).filter((f) => f.endsWith('.sql')).sort().join('/') : ''
  const open = databases.get(app)
  if (open?.steps === steps) return open.db
  const db = (async () => {
    open?.db.then((d) => d.close(), () => {})
    if (steps) {
      const { code, err } = await python([path.join(env.TALARIA_PLUGIN || '', 'db.py'), app])
      if (code) throw new Error(`${app}'s database: ${err || 'migrations failed'}`)
    }
    const d = (await sqlite())(path.join(dataRoot, app, 'app.db'))
    d.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON')
    return d
  })()
  databases.set(app, { steps, db })
  db.catch(() => databases.get(app)?.db === db && databases.delete(app))  // a failed migration is tried again next call
  return db
}

/** apps/<app>/server.ts answers /<app>/api/…: its default export gets a Request (with the full URL) and the app's
 *  name, data folder and database, and returns a Response. Loaded through Vite, so editing it takes effect on the next call. */
async function api(server, app, req, res) {
  const file = ['server.ts', 'server.js'].map((f) => path.join(appDir(app), f)).find((f) => existsSync(f))
  if (!file) return send(res, 404, `${app} has no server.ts`)
  if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method) && !sameOrigin(req)) return send(res, 403, 'Not from this app’s page.')
  const mod = await server.ssrLoadModule(file)
  if (typeof mod.default !== 'function') return send(res, 500, `${app}/server.ts has no default export`)
  const hasBody = !['GET', 'HEAD'].includes(req.method)
  const request = new Request(`http://${req.headers.host}${req.url}`, {
    method: req.method, headers: req.headers, body: hasBody ? await body(req) : undefined,
  })
  const answer = await mod.default(request, { app, dir: path.join(dataRoot, app), db: () => database(app) })
  if (!(answer instanceof Response)) return send(res, 500, `${app}/server.ts didn't answer with a Response`)
  res.writeHead(answer.status, Object.fromEntries(answer.headers))
  if (answer.body) Readable.fromWeb(answer.body).pipe(res)
  else res.end()
}

/** POST /<app>/__action/<name>: actions.py runs it, exactly as for the phone and the per-app ports. The SDK's
 *  header forces a CORS preflight, which nothing here answers, so only the app's own page can send it. */
async function action(app, name, req, res) {
  if (req.headers['x-talaria-action'] !== '1' || !sameOrigin(req)) {
    return send(res, 403, JSON.stringify({ ok: false, error: 'Not from this app’s page.' }), 'application/json')
  }
  const request = await body(req)
  const code = 'import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; import actions; '
    + 'sys.stdout.write(actions.run(Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.stdin.buffer.read()))'
  const { out, err } = await python(['-c', code, env.TALARIA_PLUGIN || '', dataRoot, app, name], request)
  send(res, 200, out || JSON.stringify({ ok: false, error: err.split('\n').pop() || `${name} failed` }), 'application/json')
}

/** A file from the app's data folder. Not its actions, nor dotfiles, nor an older build's page. */
function dataFile(app, rest, res) {
  const parts = rest.split('/')
  if (parts[0] === 'actions' || parts.some((p) => p.startsWith('.') || p === '__pycache__') || /\.py$/.test(rest)) return false
  const folder = path.join(dataRoot, app)
  const file = path.resolve(folder, rest)
  if (!file.startsWith(folder + path.sep)) return false
  let stat
  try { stat = statSync(file) } catch { return false }
  if (!stat.isFile()) return false
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream',
    'Content-Length': stat.size, 'Cache-Control': 'no-store' })
  createReadStream(file).pipe(res)
  return true
}

function apps() {
  return {
    name: 'talaria-apps',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        try {
          const url = new URL(req.url, 'http://x')
          const segs = url.pathname.split('/')
          if (url.pathname === '/__talaria/ping') return send(res, 200, `talaria-apps ${env.TALARIA_STAMP || ''} ${process.pid}`)
          // An app's server code runs here; it's never handed to a page.
          if (segs[1] === 'apps' && (/^server\.[a-z]+$/.test(segs[3] || '') || (segs[3] === 'server' && segs.length > 4))) return send(res, 404, 'Not found')
          const app = decodeURIComponent(segs[1] || '')
          if (!isApp(app)) return next()
          if (segs.length === 2) { res.writeHead(302, { Location: `/${app}/${url.search}` }); return res.end() }
          const rest = decodeURIComponent(segs.slice(2).join('/'))
          if (rest === 'api' || rest.startsWith('api/')) return await api(server, app, req, res)
          if (rest.startsWith('__action/') && req.method === 'POST') return await action(app, rest.slice('__action/'.length), req, res)
          if (rest === '__page/watch') return watch(app, req, res)
          if (rest === '__page/answer' && req.method === 'POST') return await answer(req, res)
          if (rest && rest !== 'index.html' && dataFile(app, rest, res)) return
          if (rest && path.extname(rest)) return send(res, 404, 'Not found')
          // The app's page, also for its routes (/<app>/trips/42), never a stale built index.html.
          send(res, 200, await server.transformIndexHtml(`/${app}/`, page(app)), 'text/html; charset=utf-8')
        } catch (e) {
          server.config.logger.error(String(e?.stack || e))
          if (!res.headersSent) send(res, 500, String(e?.message || e))
        }
      })
    },
  }
}

// MARK: The page channel
// While you share an app's page with Hermes (Desktop's toggle beside the app), its runtime keeps GET
// /<app>/__page/watch open: server-sent events, under the app's path so the gate lets it through. The plugin's
// app_snapshot asks over POST /__talaria/snapshot; the newest watching page gets an id, reads itself, and posts what
// it shows to /<app>/__page/answer with that id. Only a page that read the stream knows the id, and the answer's
// header forces a CORS preflight that nothing answers, so another site's page can neither answer nor make one up.
// Nothing is read unless the plugin asks, and no page watches unless you shared it.

const SNAPSHOT_WAIT = 8000
const MAX_SNAPSHOT = 512 * 1024
const watchers = [] // { app, res }, oldest first
const asked = new Map() // id -> { app, resolve }

function watch(app, req, res) {
  if (!sameOrigin(req)) return send(res, 403, 'Not from this app’s page.')
  res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive' })
  res.write(': watching\n\n')
  const watcher = { app, res }
  watchers.push(watcher)
  const alive = setInterval(() => res.write(': still\n\n'), 25000) // proxies close a stream that goes quiet
  req.on('close', () => {
    clearInterval(alive)
    watchers.splice(watchers.indexOf(watcher), 1)
  })
}

async function answer(req, res) {
  if (req.headers['x-talaria-page'] !== '1' || !sameOrigin(req)) return send(res, 403, 'Not from this app’s page.')
  const raw = await body(req)
  if (raw.length > MAX_SNAPSHOT) return send(res, 413, 'Too large.')
  let reply
  try { reply = JSON.parse(raw.toString()) } catch { return send(res, 400, 'Not JSON.') }
  const ask = asked.get(reply?.id)
  if (!ask) return send(res, 404, 'Nothing asked that.')
  asked.delete(reply.id)
  ask.resolve({ ...reply.snapshot, app: ask.app }) // the app is the one whose path it watched, whatever the page says
  send(res, 204, '')
}

/** The newest watching page (of ``app``, when given) reads itself; null when none watches or it doesn't answer. */
function snapshot(app, wait = SNAPSHOT_WAIT) {
  const watcher = watchers.findLast((w) => !app || w.app === app)
  if (!watcher) return Promise.resolve(null)
  const id = randomBytes(18).toString('base64url')
  return new Promise((resolve) => {
    const timer = setTimeout(() => { asked.delete(id); resolve({ error: 'The page didn’t answer.' }) }, wait)
    asked.set(id, { app: watcher.app, resolve: (s) => { clearTimeout(timer); resolve(s) } })
    watcher.res.write(`event: snapshot\ndata: ${JSON.stringify({ id })}\n\n`)
  })
}

function pageApi() {
  return {
    name: 'talaria-page',
    configureServer(s) {
      s.middlewares.use('/__talaria/snapshot', async (req, res) => {
        if (!fromPlugin(req) || req.method !== 'POST') return send(res, 403, 'Only for Talaria’s plugin.')
        try {
          const { app, wait } = JSON.parse((await body(req)).toString() || '{}')
          const ms = Math.min(Math.max(Number(wait) || SNAPSHOT_WAIT, 500), SNAPSHOT_WAIT)
          const shot = await snapshot(typeof app === 'string' && app ? app : null, ms)
          send(res, shot ? 200 : 404, JSON.stringify(shot ?? { error: 'No app page is shared with Hermes.' }), 'application/json')
        } catch (e) {
          send(res, 400, JSON.stringify({ error: String(e?.message || e) }), 'application/json')
        }
      })
    },
  }
}

// MARK: The gate
// Desktop on a direct connection (http:// or https:// to the gateway, no SSH) can't reach this loopback port. The
// plugin then opens a gate on the address the gateway listens on, same port number: a TCP pipe to this server for
// devices that showed a ticket. /talaria open mints the ticket over Desktop's authenticated connection; the frame
// loads /<app>/?talaria-ticket=…, which unlocks that device's address for a while and redirects to the clean URL.
// Everything after, hot reload's websocket included, is piped through untouched. Everyone else gets a 403.

const TICKET_TTL = 2 * 60 * 1000
const UNLOCK_TTL = 12 * 60 * 60 * 1000 // since that device's last connection
const tickets = new Map() // ticket -> expiry
const unlocked = new Map() // address -> expiry
const gates = new Map() // host -> port

const peer = (sock) => (sock.remoteAddress || '').replace(/^::ffff:/, '')
/** The plugin's own call: it started this server and gave it a secret no page has. */
function fromPlugin(req) {
  const given = Buffer.from(String(req.headers['x-talaria-admin'] || ''))
  const want = Buffer.from(env.TALARIA_ADMIN || '')
  return want.length > 0 && given.length === want.length && timingSafeEqual(given, want)
}

function refuse(sock, status, text) {
  sock.end(`HTTP/1.1 ${status}\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: ${Buffer.byteLength(text)}\r\n`
    + `Cache-Control: no-store\r\nConnection: close\r\n\r\n${text}`)
}

function admit(sock, port) {
  const chunks = []
  let size = 0
  const onData = (chunk) => {
    chunks.push(chunk)
    size += chunk.length
    const head = Buffer.concat(chunks)
    const end = head.indexOf('\r\n')
    if (end < 0 && size < 8192) return
    sock.off('data', onData)
    sock.pause()
    const [, target] = /^[A-Z]+ (\S+) HTTP\/\d/.exec(head.toString('latin1', 0, end < 0 ? 8192 : end)) || []
    if (!target) return refuse(sock, '400 Bad Request', 'Not HTTP.')
    const url = new URL(target, 'http://gate')
    const ip = peer(sock)
    const ticket = url.searchParams.get('talaria-ticket')
    if (ticket && (tickets.get(ticket) ?? 0) > Date.now()) {
      tickets.delete(ticket)
      unlocked.set(ip, Date.now() + UNLOCK_TTL)
      url.searchParams.delete('talaria-ticket')
      return sock.end(`HTTP/1.1 302 Found\r\nLocation: ${url.pathname}${url.search}\r\nCache-Control: no-store\r\n`
        + `Content-Length: 0\r\nConnection: close\r\n\r\n`)
    }
    if ((unlocked.get(ip) ?? 0) < Date.now()) return refuse(sock, '403 Forbidden', 'Open this app from Talaria.')
    if (url.pathname.startsWith('/__talaria/')) return refuse(sock, '404 Not Found', 'Not found')
    unlocked.set(ip, Date.now() + UNLOCK_TTL)
    const up = net.connect(port, '127.0.0.1', () => {
      up.write(head)
      sock.pipe(up).pipe(sock)
      sock.resume()
    })
    up.on('error', () => sock.destroy())
    sock.on('error', () => up.destroy())
  }
  sock.on('data', onData)
  sock.on('error', () => {})
}

/** Open the gate on ``host`` (an address of this machine; never a wildcard), at this server's port number when it's
 *  free there. Its port. */
function openGate(host, port) {
  if (gates.has(host)) return Promise.resolve(gates.get(host))
  if (!host || ['0.0.0.0', '::', '*'].includes(host)) return Promise.reject(new Error('The gate needs one address, not all of them.'))
  const listen = (p) => new Promise((resolve, reject) => {
    const gate = net.createServer((sock) => admit(sock, port))
    gate.once('error', reject)
    gate.listen(p, host, () => resolve(gate.address().port))
  })
  return listen(port).catch((e) => (e.code === 'EADDRINUSE' ? listen(0) : Promise.reject(e))).then((p) => {
    gates.set(host, p)
    server.config.logger.info(`talaria-apps gate on ${host}:${p}`)
    return p
  })
}

function gateApi() {
  return {
    name: 'talaria-gate',
    configureServer(s) {
      s.middlewares.use('/__talaria/gate', async (req, res) => {
        if (!fromPlugin(req) || req.method !== 'POST') return send(res, 403, 'Only for Talaria’s plugin.')
        try {
          const { host } = JSON.parse((await body(req)).toString() || '{}')
          const gatePort = await openGate(host, s.config.server.port)
          const ticket = randomBytes(24).toString('base64url')
          tickets.set(ticket, Date.now() + TICKET_TTL)
          // A host name (not an address) has to be one Vite answers to.
          if (!net.isIP(host) && Array.isArray(s.config.server.allowedHosts) && !s.config.server.allowedHosts.includes(host)) {
            s.config.server.allowedHosts.push(host)
          }
          send(res, 200, JSON.stringify({ port: gatePort, ticket }), 'application/json')
        } catch (e) {
          send(res, 400, JSON.stringify({ error: String(e?.message || e) }), 'application/json')
        }
      })
    },
  }
}

const server = await createServer({
  root: workspace,
  configFile: false,
  // Its own dependency cache: the phone's builds share node_modules, and their settings would otherwise have it
  // re-bundle every dependency on each start.
  cacheDir: 'node_modules/.vite-apps',
  appType: 'custom',
  logLevel: 'info',
  clearScreen: false,
  plugins: [react(), tailwindcss(), entryPlugin(), gateApi(), pageApi(), apps()],
  resolve: { alias: aliases },
  // Crawl every app up front, so the first visit doesn't stop to reload for a newly found dependency.
  optimizeDeps: { entries: ['apps/*/App.{tsx,jsx}'] },
  server: {
    host: '127.0.0.1',
    port: Number(env.TALARIA_PORT || 8798),
    strictPort: true,
    allowedHosts: (env.TALARIA_HOSTS || '').split(',').filter(Boolean),
    fs: { deny: ['.env', '.env.*', '**/apps/*/server.*', '**/apps/*/server/**'] },
    // A build writes its output into .out/ and a migration copies old code into legacy/: neither is an app's code,
    // and watching them sent every open app a reload on each build.
    watch: { ignored: ['**/.out/**', '**/legacy/**', '**/.lock'] },
    // Compile every app's code when the server starts, so the first open after a restart doesn't wait for it.
    warmup: { clientFiles: ['./apps/*/App.{tsx,jsx}', './talaria/runtime.tsx', './talaria/sdk.ts'] },
  },
})
await server.listen()
server.config.logger.info(`talaria-apps on ${server.resolvedUrls?.local?.[0] ?? ''}`)
