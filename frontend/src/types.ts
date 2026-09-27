// Shapes returned by the FastAPI backend (see backend/main.py response models).

export interface SizeStock {
  size: string
  quantity: number
}

export interface ProductSummary {
  product_id: string
  name: string
  garment_type: string
  description: string
  colors: string[]
  search_tags: string[]
  image_file_path: string
  image_url: string
  price: number
  total_stock: number
  /** Sizes with stock > 0 (used by the size filter). */
  in_stock_sizes: string[]
}

export interface ProductDetail extends ProductSummary {
  inventory: SizeStock[]
}

// A product recommended by the chat agent; built by the backend from the database (models.ProductCard).
export interface ProductCard {
  product_id: string
  name: string
  garment_type: string
  price: number
  image_url: string
  colors: string[]
  total_stock: number
  in_stock_sizes: string[]
}

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

// A catalogue search run by the chat agent (models.ChatSearchResults). Products use the same
// ProductSummary shape as GET /api/products, so they render with the normal ProductCard.
export interface ChatSearchResults {
  query: string
  shopper_message: string
  filters: Record<string, string | number>
  match_mode: 'all_terms' | 'partial' | 'filters_only'
  total_matches: number
  /** Typo fixes the search applied, e.g. { hoddies: 'hoodies' }. */
  corrections: Record<string, string>
  products: ProductSummary[]
}

export interface ChatResponse {
  reply: string
  products: ProductCard[]
  search_results: ChatSearchResults | null
  model: string
  tool_calls: number
  /** True when the exchange was stored in the shopper's saved history (logged-in only). */
  saved: boolean
}

// Where the shopper is when they send a message (models.PageContextIn).
export interface PageContext {
  path: string
  product_id: string | null
}

export interface ChatHistoryMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  products: ProductCard[]
  created_at: string
}

export interface ChatHistoryResponse {
  messages: ChatHistoryMessage[]
  total_saved: number
}

// Never includes the password hash (see PublicUser in backend/auth.py).
export interface PublicUser {
  id: number
  first_name: string | null
  last_name: string | null
  name: string
  email: string
}

export interface AuthResponse {
  message: string
  token: string
  user: PublicUser
}
