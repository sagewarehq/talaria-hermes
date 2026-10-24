// The three helpers data.ts takes from Datagen's @studio/sql/lib/db.ts, as they are there.
export interface QueryResult { columns: { name: string; type: string }[]; rows: unknown[][] }
const bare = (type: string) => type.toLowerCase().replace(/^(nullable|lowcardinality)\((.*)\)$/, '$2').trim()
const NUMERIC = /^(smallint|integer|int|bigint|tinyint|numeric|decimal|real|float|double|money|u?int\d+|float\d+|decimal\d*)\b/
const TEMPORAL = /^(date|timestamp|time|datetime|datetime64|date32)\b/
export const isNumericType = (type: string) => NUMERIC.test(bare(type))
export const isTemporalType = (type: string) => TEMPORAL.test(bare(type))
export function headerText(name: string): string {
  const words = name.replace(/_/g, ' ').replace(/\s+/g, ' ').trim()
  return name === name.toLowerCase() ? words.charAt(0).toUpperCase() + words.slice(1) : words
}
