import { useSyncExternalStore } from 'react'

function subscribe(onChange: () => void) {
  window.addEventListener('online', onChange)
  window.addEventListener('offline', onChange)
  return () => {
    window.removeEventListener('online', onChange)
    window.removeEventListener('offline', onChange)
  }
}

/** Site-wide banner shown while the browser is offline, so failed loads aren't a mystery. */
export default function NetworkStatus() {
  const online = useSyncExternalStore(subscribe, () => navigator.onLine, () => true)
  if (online) return null
  return (
    <div className="network-banner" role="status">
      You’re offline. Products and the assistant will work again once you reconnect.
    </div>
  )
}
