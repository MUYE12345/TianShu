export function createSSE(url, handlers) {
  const eventSource = new EventSource(url)
  const cleanup = {}

  for (const [event, handler] of Object.entries(handlers)) {
    eventSource.addEventListener(event, (e) => {
      try {
        handler(JSON.parse(e.data))
      } catch { handler(e.data) }
    })
  }

  eventSource.onerror = () => {
    eventSource.close()
  }

  return () => eventSource.close()
}
