// An article's extracted text (articles/<id>.json, written on the box when the edition is published), for the in-app
// reader. Blocks are plain text; nothing is rendered as HTML. A block with inline code has it in `parts`: text, code,
// text, and so on. Media blocks are addresses: a photo on the publisher's
// site, or an embed from a known player (YouTube, Vimeo, Flourish, Datawrapper), rebuilt from its id by extract.py.
import { useEffect, useState } from 'react'

export type Block =
  | { t: 'p' | 'h' | 'li' | 'q' | 'code'; text: string; parts?: string[] }
  | { t: 'img'; src: string; alt?: string }
  | { t: 'embed'; kind: 'video' | 'chart'; src: string; ratio?: number }
export type Extracted = { ok: boolean; words?: number; byline?: string | null; site?: string | null; blocks?: Block[]; reason?: string }

const cache = new Map<string, Extracted | null>()

export function useArticle(id?: string) {
  const [state, setState] = useState<{ id?: string; article?: Extracted | null }>({})
  useEffect(() => {
    if (!id) return
    if (cache.has(id)) { setState({ id, article: cache.get(id) }); return }
    setState({ id })
    let live = true
    fetch(`articles/${id}.json`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null)).catch(() => null)
      .then((a: Extracted | null) => { cache.set(id, a); if (live) setState({ id, article: a }) })
    return () => { live = false }
  }, [id])
  return { loading: Boolean(id) && state.id === id && state.article === undefined, article: state.id === id ? state.article : undefined }
}

/** Fetch the next few articles ahead of time, so Next opens instantly. */
export function prefetch(ids: string[]) {
  for (const id of ids) if (!cache.has(id)) fetch(`articles/${id}.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null).then((a) => cache.set(id, a))
}
