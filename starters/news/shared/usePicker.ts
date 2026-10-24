// The inline edition picker's state: open or closed, the month shown and the chosen day. No dialog, no native date
// input (they broke on the phone); each design draws it in-flow under its edition bar.
import { useEffect, useState } from 'react'
import { calendar, type Newsroom } from './useNewsroom'

export function usePicker(nr: Newsroom) {
  const [open, setOpen] = useState(false)
  const [month, setMonth] = useState('')
  const [day, setDay] = useState('')
  useEffect(() => {
    if (nr.current) { setMonth(nr.current.date.slice(0, 7)); setDay(nr.current.date) }
  }, [nr.current?.id, open])
  useEffect(() => {
    if (!open) return
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    addEventListener('keydown', esc)
    return () => removeEventListener('keydown', esc)
  }, [open])
  const cal = month ? calendar(nr.index, month) : undefined
  return {
    open, toggle: () => setOpen((o) => !o), close: () => setOpen(false),
    cal, day, setDay, setMonth,
    times: cal?.days.get(day) ?? [],
    choose: (id: string) => { setOpen(false); nr.open(id) },
  }
}
