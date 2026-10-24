import { Bookmark, ThumbsDown, ThumbsUp, type LucideIcon } from 'lucide-react'
import { motion } from 'motion/react'
import type { Article, Newsroom } from './useNewsroom'

/** An icon that fills when on (a light fill of its own colour, so its inner lines still show), with a small pop. */
export function Glyph({ Icon, on, size = 17 }: { Icon: LucideIcon; on: boolean; size?: number }) {
  return (
    <motion.span key={String(on)} initial={on ? { scale: 0.6 } : false} animate={{ scale: 1 }} transition={{ type: 'spring', bounce: 0.6, duration: 0.4 }} className="grid">
      <Icon size={size} strokeWidth={on ? 2.1 : 1.8} fill={on ? 'currentColor' : 'none'} fillOpacity={on ? 0.28 : 0} />
    </motion.span>
  )
}

/** More like this, Less like this and Save: 44px targets, filled when chosen, for every story. */
export function Actions({ a, nr, className = '', button = '' }: { a: Article; nr: Newsroom; className?: string; button?: string }) {
  const v = nr.vote[a.id]?.value
  const saved = Boolean(nr.saved[a.id])
  return (
    <div className={`flex items-center ${className}`} aria-label="Feedback and save">
      <button className={button} aria-pressed={v === 1} aria-label={`More like this: ${a.title}`} onClick={() => nr.rate(a, 1)}><Glyph Icon={ThumbsUp} on={v === 1} /></button>
      <button className={button} aria-pressed={v === -1} aria-label={`Less like this: ${a.title}`} onClick={() => nr.rate(a, -1)}><Glyph Icon={ThumbsDown} on={v === -1} /></button>
      <button className={button} aria-pressed={saved} aria-label={`${saved ? 'Unsave' : 'Save'}: ${a.title}`} onClick={() => nr.toggleSave(a)}><Glyph Icon={Bookmark} on={saved} /></button>
    </div>
  )
}
