// What a Talaria app imports as 'talaria'. Owned by the plugin, which replaces this folder on every build.

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
    const res = await fetch(`/__action/${encodeURIComponent(name)}`, {
      method: 'POST', body: JSON.stringify(request), headers: { 'Content-Type': 'application/json', 'X-Talaria-Action': '1' },
    })
    envelope = await res.json().catch(() => ({ ok: false, error: `${name}: ${res.status}` }))
  }
  if (!envelope?.ok) throw new Error(envelope?.error || `${name} failed`)
  return envelope.result as T
}
