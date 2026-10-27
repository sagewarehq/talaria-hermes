// What a Talaria app imports as 'talaria'. Owned by the plugin, which replaces this folder on every build.
import { useCallback, useEffect, useRef, useState } from 'react'

/** Thrown when this copy of Talaria can't run actions yet (a build from before them): update Talaria. */
export class ActionsUnavailable extends Error {
  constructor() { super('This version of Talaria can’t run app actions. Update Talaria to use this.') }
}

type Bridge = { postMessage(message: unknown): Promise<unknown> }
const bridge = () => (window as unknown as { webkit?: { messageHandlers?: { talaria?: Bridge } } }).webkit?.messageHandlers?.talaria

/** Run one of this app's actions (a script in its folder's actions/) with `request`, and get its JSON answer. */
export async function action<T = unknown>(name: string, request: unknown = null): Promise<T> {
  let envelope: { ok: boolean; result?: T; error?: string }
  const b = bridge()
  if (b) {
    const reply = await b.postMessage({ action: name, request })
    envelope = typeof reply === 'string' ? JSON.parse(reply) : (reply as typeof envelope)
  } else if (location.protocol === 'talaria-canvas:') {
    throw new ActionsUnavailable()
  } else {
    // On the workspace dev server every app lives under /<app>/; on an origin of its own (the preview, a per-app
    // port) at /. The page's own path says which.
    const app = (window as unknown as { __TALARIA__?: { app: string } }).__TALARIA__?.app
    const base = app && location.pathname.startsWith(`/${app}/`) ? `/${app}/` : '/'
    const res = await fetch(`${base}__action/${encodeURIComponent(name)}`, {
      method: 'POST', body: JSON.stringify(request), headers: { 'Content-Type': 'application/json', 'X-Talaria-Action': '1' },
    })
    envelope = await res.json().catch(() => ({ ok: false, error: `${name}: ${res.status}` }))
  }
  if (!envelope?.ok) throw new Error(envelope?.error || `${name} failed`)
  return envelope.result as T
}

export type Row = Record<string, unknown>
export type Params = unknown[] | Record<string, unknown>
type Ran = { rows: Row[]; changes: number; lastId: number | null }

/** This app's SQLite database: app.db in its folder, its tables from the migrations/ Hermes writes there. Rides on
 *  the reserved action `talaria-db`, so it works wherever actions do. Objects and arrays in `params` are stored as
 *  JSON text; blobs come back as base64. */
export const db = {
  /** The rows a statement returns. */
  async query<T = Row>(sql: string, params?: Params): Promise<T[]> {
    return (await action<Ran>('talaria-db', { sql, params })).rows as T[]
  },
  /** The first row, or undefined. */
  async get<T = Row>(sql: string, params?: Params): Promise<T | undefined> {
    return (await db.query<T>(sql, params))[0]
  },
  /** A statement that changes something: how many rows it changed, and the last inserted row's id. */
  async run(sql: string, params?: Params): Promise<{ changes: number; lastId: number | null }> {
    const { changes, lastId } = await action<Ran>('talaria-db', { sql, params })
    return { changes, lastId }
  },
  /** Several statements in one transaction: all of them, or none if one fails. */
  batch(statements: [sql: string, params?: Params][]): Promise<Ran[]> {
    return action<Ran[]>('talaria-db', { batch: statements.map(([sql, params]) => ({ sql, params })) })
  },
}

/** Calls `changed` when the phone finds this app's data changed on the box after answering a read from its kept copy:
 *  read again. Returns the unsubscribe. Without a listener (or a `useQuery`), the phone reloads the page instead. */
export function onDataChange(changed: () => void): () => void {
  const listener = (e: Event) => { e.preventDefault(); changed() }
  window.addEventListener('talaria:data', listener)
  return () => window.removeEventListener('talaria:data', listener)
}

/** A query's rows, read when the component mounts and again when `sql` or `params` change or `refresh()` is called
 *  (after a write), or when the phone finds the data changed. `rows` stays the last answer while a new one loads, so
 *  lists don't flash empty. */
export function useQuery<T = Row>(sql: string | null, params?: Params) {
  const [rows, setRows] = useState<T[]>()
  const [error, setError] = useState<Error>()
  const [loading, setLoading] = useState(sql !== null)
  const [tick, setTick] = useState(0)
  const key = JSON.stringify(params ?? null)
  const latest = useRef(0)
  useEffect(() => {
    if (sql === null) return
    const n = ++latest.current
    setLoading(true)
    db.query<T>(sql, params).then(
      (r) => { if (n === latest.current) { setRows(r); setError(undefined); setLoading(false) } },
      (e) => { if (n === latest.current) { setError(e instanceof Error ? e : new Error(String(e))); setLoading(false) } },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sql, key, tick])
  const refresh = useCallback(() => setTick((t) => t + 1), [])
  useEffect(() => onDataChange(refresh), [refresh])
  return { rows, error, loading, refresh }
}
