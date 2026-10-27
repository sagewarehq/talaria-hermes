import { useEffect, useState } from 'react'
import { onDataChange } from 'talaria'

/** A JSON file from the app's data folder, by a relative path (`'data.json'`), which Hermes or a routine writes.
 *  Never import data: a build would freeze it. */
export function useJSON<T>(path: string): { data: T | undefined; error: Error | undefined } {
  const [data, setData] = useState<T>()
  const [error, setError] = useState<Error>()
  // The phone answers the first read from what it kept, and says when the box had newer: read again.
  const [tick, setTick] = useState(0)
  useEffect(() => onDataChange(() => setTick((t) => t + 1)), [])
  useEffect(() => {
    fetch(path, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${path}: ${r.status}`))))
      .then(setData, setError)
  }, [path, tick])
  return { data, error }
}
