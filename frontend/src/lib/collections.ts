import type { ProductSummary } from '../types'

// Curated groupings built from real catalogue names and tags (no hardcoded product lists).
export interface Collection {
  key: string
  title: string
  blurb: string
  matches: (p: ProductSummary) => boolean
}

const text = (p: ProductSummary) => `${p.name} ${p.search_tags.join(' ')}`.toLowerCase()

export const COLLECTIONS: Collection[] = [
  {
    key: 'sports',
    title: 'Game Day',
    blurb: 'Team-inspired gear for the stands, the Bowl, and the tailgate.',
    matches: (p) => text(p).includes('sports'),
  },
  {
    key: 'schools',
    title: 'Graduate & Professional Schools',
    blurb: 'Rep your program, from Architecture to Public Health.',
    matches: (p) => p.name.toLowerCase().includes('school of'),
  },
  {
    key: 'family',
    title: 'Yale Family',
    blurb: 'For the moms, dads, grandparents, aunts, and uncles cheering from afar.',
    matches: (p) => /\b(mom|dad|aunt|uncle|brother|grandma|grandpa)\b/i.test(p.name),
  },
  {
    key: 'vintage',
    title: 'Vintage Bulldog',
    blurb: 'Throwback marks and heritage graphics with a lived-in feel.',
    matches: (p) => text(p).includes('vintage'),
  },
]

export function findCollection(key: string | null): Collection | undefined {
  return COLLECTIONS.find((c) => c.key === key)
}
