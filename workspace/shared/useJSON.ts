import { useEffect, useState } from 'react'

/** A JSON file from the app's built folder (`/data.json`), which Hermes or a routine writes. Never import data:
 *  a build would freeze it. */
export function useJSON<T>(path: string): { data: T | undefined; error: Error | undefined } {
  const [data, setData] = useState<T>()
  const [error, setError] = useState<Error>()
  useEffect(() => {
    fetch(path, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${path}: ${r.status}`))))
      .then(setData, setError)
  }, [path])
  return { data, error }
}
