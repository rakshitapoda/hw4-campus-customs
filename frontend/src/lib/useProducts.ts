import { useCallback, useEffect, useState } from 'react'
import { fetchProducts } from '../api/client'
import type { ProductSummary } from '../types'

interface State {
  products: ProductSummary[]
  loading: boolean
  /** The ApiError (or other error) from the last attempt, for <ErrorState>. */
  error: unknown
}

export function useProducts(): State & { retry: () => void } {
  const [state, setState] = useState<State>({ products: [], loading: true, error: null })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchProducts(controller.signal)
      .then((products) => setState({ products, loading: false, error: null }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setState({ products: [], loading: false, error: err })
      })
    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }))
    setAttempt((a) => a + 1)
  }, [])

  return { ...state, retry }
}
