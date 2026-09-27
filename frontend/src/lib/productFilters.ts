import { categoryOf } from './format'
import type { CategoryKey } from './format'
import type { ProductSummary } from '../types'

// ---------- Sorting ----------

export const SORT_OPTIONS = [
  { key: 'name', label: 'Name (A–Z)' },
  { key: 'price-asc', label: 'Price: low to high' },
  { key: 'price-desc', label: 'Price: high to low' },
  { key: 'stock', label: 'Most in stock' },
] as const
export type SortKey = (typeof SORT_OPTIONS)[number]['key'] | 'relevance'

export function sortProducts(list: ProductSummary[], sort: SortKey): ProductSummary[] {
  const byName = (a: ProductSummary, b: ProductSummary) => a.name.localeCompare(b.name)
  const sorted = [...list]
  if (sort === 'name') sorted.sort(byName)
  if (sort === 'price-asc') sorted.sort((a, b) => a.price - b.price || byName(a, b))
  if (sort === 'price-desc') sorted.sort((a, b) => b.price - a.price || byName(a, b))
  if (sort === 'stock') sorted.sort((a, b) => b.total_stock - a.total_stock || byName(a, b))
  return sorted // 'relevance' keeps the incoming order (e.g. the agent's search ranking)
}

// ---------- Price bands (catalogue prices run $32–$98) ----------

export const PRICE_BANDS = [
  { key: 'under-40', label: 'Under $40', test: (p: number) => p < 40 },
  { key: '40-70', label: '$40 – $70', test: (p: number) => p >= 40 && p <= 70 },
  { key: 'over-70', label: 'Over $70', test: (p: number) => p > 70 },
] as const
export type PriceBand = (typeof PRICE_BANDS)[number]['key']

// ---------- Colors: many spellings ("navy blue", "heather gray") grouped into families ----------

const COLOR_FAMILIES: [string, RegExp][] = [
  ['Navy', /navy/],
  ['Blue', /blue/],
  ['Gray', /gr[ae]y|charcoal|heather|silver/],
  ['White', /white|cream|ivory|natural/],
  ['Black', /black/],
  ['Red', /red|maroon|crimson/],
  ['Green', /green/],
  ['Gold', /gold|yellow/],
  ['Coral', /coral|pink/],
  ['Multicolor', /multi/],
]

export function colorFamilies(colors: string[]): string[] {
  const families = new Set<string>()
  for (const c of colors) {
    const lower = c.toLowerCase()
    const match = COLOR_FAMILIES.find(([, re]) => re.test(lower))
    families.add(match ? match[0] : 'Other')
  }
  return [...families]
}

export const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL'] as const

// ---------- Filter state (kept in the URL so it survives refresh / sharing / Back) ----------

export interface Filters {
  query: string
  category: CategoryKey
  price: PriceBand | ''
  color: string
  size: string
}

export function readFilters(params: URLSearchParams): Filters {
  return {
    query: params.get('q') ?? '',
    category: (params.get('category') ?? 'all') as CategoryKey,
    price: (params.get('price') ?? '') as PriceBand | '',
    color: params.get('color') ?? '',
    size: params.get('size') ?? '',
  }
}

type FilterKey = keyof Filters

export function matchesFilters(p: ProductSummary, f: Filters, skip?: FilterKey): boolean {
  if (skip !== 'category' && f.category !== 'all' && categoryOf(p.garment_type) !== f.category) return false
  if (skip !== 'price' && f.price) {
    const band = PRICE_BANDS.find((b) => b.key === f.price)
    if (band && !band.test(p.price)) return false
  }
  if (skip !== 'color' && f.color && !colorFamilies(p.colors).includes(f.color)) return false
  if (skip !== 'size' && f.size && !p.in_stock_sizes.includes(f.size)) return false
  if (skip !== 'query' && f.query.trim()) {
    const q = f.query.trim().toLowerCase()
    const haystack = [p.name, p.garment_type, p.description, ...p.colors, ...p.search_tags].join(' ').toLowerCase()
    if (!haystack.includes(q)) return false
  }
  return true
}

/** How many products each option would show, given the *other* active filters (for chip counts). */
export function countBy<T extends string>(
  products: ProductSummary[],
  filters: Filters,
  skip: FilterKey,
  keysOf: (p: ProductSummary) => T[],
): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const p of products) {
    if (!matchesFilters(p, filters, skip)) continue
    for (const k of keysOf(p)) counts[k] = (counts[k] ?? 0) + 1
  }
  return counts
}

export function activeFilterCount(f: Filters): number {
  return [f.query.trim(), f.category !== 'all', f.price, f.color, f.size].filter(Boolean).length
}
