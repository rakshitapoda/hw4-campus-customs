import { useState } from 'react'

interface Props {
  src: string
  alt: string
  loading?: 'lazy' | 'eager'
  className?: string
}

/** Product photo with a labelled placeholder if the image fails to load (instead of a broken icon). */
export default function ProductImage({ src, alt, loading, className }: Props) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  if (failedSrc === src) {
    return (
      <div className={`image-fallback ${className ?? ''}`} role="img" aria-label={`${alt} (image unavailable)`}>
        <span aria-hidden="true">CC</span>
        <small>Image unavailable</small>
      </div>
    )
  }
  return <img src={src} alt={alt} loading={loading} className={className} onError={() => setFailedSrc(src)} />
}
