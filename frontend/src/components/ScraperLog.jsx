import { useState, useEffect, useRef } from 'react'
import { FiTerminal, FiX, FiPlay, FiActivity } from 'react-icons/fi'

const STATUS_URL = '/api/scrape-status'
const LOG_POLL_MS = 2500
const STATUS_POLL_MS = 2000
const MAX_LINES = 300

function lineClass(line) {
  if (/\bOK\s/.test(line)) return 'text-emerald-300'
  if (/\bWARN\b/.test(line)) return 'text-amber-300'
  if (/\bERR\b/.test(line)) return 'text-rose-300'
  if (/^={3,}/.test(line.trim()) || /^-{3,}/.test(line.trim())) return 'text-slate-600'
  if (/Cycle #/.test(line)) return 'text-cyan-200 font-semibold'
  if (/\[trigger\s*\]/.test(line)) return 'text-violet-300'
  return 'text-slate-200'
}

function statusPill(status) {
  if (status.running) return 'bg-emerald-950 text-emerald-300 border border-emerald-800'
  if (status.last_exit_code && status.last_exit_code !== 0) return 'bg-rose-950 text-rose-300 border border-rose-800'
  return 'bg-slate-800 text-slate-300 border border-slate-700'
}

function statusText(status) {
  if (status.running) return `Running${status.pid ? ` (pid ${status.pid})` : ''}`
  if (status.last_exit_code && status.last_exit_code !== 0) return 'Crashed (Exited with Error)'
  return 'Idle'
}

export default function ScraperLog({ onRunScrape }) {
  const [open, setOpen] = useState(false)
  const [lines, setLines] = useState([])
  const [lastFetch, setLastFetch] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const [status, setStatus] = useState({ running: false, pid: null, last_exit_code: null })
  const [actionMessage, setActionMessage] = useState('')
  const [runBusy, setRunBusy] = useState(false)

  const termRef = useRef(null)
  const atBottom = useRef(true)

  useEffect(() => {
    let alive = true

    const fetchStatus = async () => {
      try {
        const baseUrl = import.meta.env.VITE_API_BASE || ''
        const url = baseUrl ? `${baseUrl}${STATUS_URL}?v=${Date.now()}` : `${STATUS_URL}?v=${Date.now()}`
        
        const res = await fetch(url, { cache: 'no-store' })
        if (!res.ok) return
        const payload = await res.json()
        if (!alive) return
        setStatus(payload)
      } catch {
        // dev endpoint may not exist in non-dev contexts
      }
    }

    void fetchStatus()
    const id = setInterval(() => {
      void fetchStatus()
    }, STATUS_POLL_MS)

    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  useEffect(() => {
    if (!open) return undefined

    let alive = true

    const fetchLog = async () => {
      try {
        const baseUrl = import.meta.env.VITE_API_BASE || ''
        const logUrl = baseUrl ? `${baseUrl}/scraper.log?v=${Date.now()}` : `/scraper.log?v=${Date.now()}`

        const res = await fetch(logUrl, { cache: 'no-store' })
        if (!res.ok) throw new Error(res.status === 404 ? 'not-started' : `HTTP ${res.status}`)

        const text = await res.text()
        if (!alive) return

        setLines(text.split('\n').filter(Boolean).slice(-MAX_LINES))
        setLastFetch(new Date())
        setFetchError(null)
      } catch (err) {
        if (!alive) return
        setFetchError(err.message)
      }
    }

    void fetchLog()
    const id = setInterval(() => {
      void fetchLog()
    }, LOG_POLL_MS)

    return () => {
      alive = false
      clearInterval(id)
    }
  }, [open])

  useEffect(() => {
    const el = termRef.current
    if (el && atBottom.current) el.scrollTop = el.scrollHeight
  }, [lines])

  const handleScroll = () => {
    const el = termRef.current
    if (!el) return
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  const scrollToBottom = () => {
    const el = termRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
    atBottom.current = true
  }

  const triggerRun = async () => {
    if (runBusy || status.running) return
    setRunBusy(true)
    setActionMessage('Requesting scrape cycle...')

    try {
      if (onRunScrape) {
        const result = await onRunScrape()
        if (result?.ok) {
          setActionMessage('Scrape request sent')
        } else if (result?.reason === 'already-running') {
          setActionMessage('Scrape already running')
        } else if (result?.reason === 'cooldown') {
          setActionMessage('Scroll trigger cooldown active; try again shortly')
        } else if (result?.reason === 'not-available') {
          setActionMessage('Scraper endpoint unavailable')
        } else {
          setActionMessage('Could not request scrape cycle')
        }
      } else {
        const baseUrl = import.meta.env.VITE_API_BASE || ''
        const url = baseUrl ? `${baseUrl}/api/scrape-cycle` : '/api/scrape-cycle'
        const res = await fetch(url, { method: 'POST' })
        
        if (res.status === 409) {
          setActionMessage('Scrape already running')
        } else if (!res.ok) {
          setActionMessage(`Trigger failed (HTTP ${res.status})`)
        } else {
          setActionMessage('Scrape request sent')
        }
      }
    } catch {
      setActionMessage('Could not request scrape cycle')
    } finally {
      setRunBusy(false)
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-6 left-6 z-50 flex items-center gap-2
                   bg-slate-950 border border-slate-600 text-emerald-200
                   px-5 py-3.5 rounded-xl shadow-2xl font-mono text-[13px]
                   hover:bg-slate-800 transition-colors"
        aria-label="Toggle scraper logs"
      >
        <FiTerminal size={17} />
        <span>Scraper Terminal</span>
        <span className={`text-[11px] px-2.5 py-1 rounded-md ${statusPill(status)}`}>
          {status.running ? 'Running' : (status.last_exit_code && status.last_exit_code !== 0 ? 'Crashed' : 'Idle')}
        </span>
      </button>

      {open && (
        <div
          className="fixed bottom-0 left-0 right-0 z-50 flex flex-col
                     bg-[#0b1220] border-t border-slate-700 shadow-2xl"
          style={{ height: '46vh', minHeight: '320px' }}
        >
          <div className="flex items-center gap-3 px-4 py-3 bg-[#131c2e] border-b border-slate-700 flex-shrink-0">
            <FiActivity className="text-cyan-300" size={16} />
            <span className="font-mono text-sm text-slate-200">scraper.log</span>
            <span className={`text-xs px-2 py-0.5 rounded-md ${statusPill(status)}`}>
              {statusText(status)}
            </span>
            <span className="ml-auto text-xs text-slate-400">
              {lastFetch ? `Updated ${lastFetch.toLocaleTimeString()}` : 'Waiting for logs'}
            </span>
          </div>

          <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800 bg-[#0f1729]">
            <button
              onClick={triggerRun}
              disabled={runBusy || status.running}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-bold border transition-all
                         ${status.last_exit_code && status.last_exit_code !== 0
                           ? 'bg-rose-600 hover:bg-rose-700 text-white border-rose-500 shadow-lg shadow-rose-900/20'
                           : 'bg-maroon-700 hover:bg-maroon-800 text-white border-maroon-600'}
                         disabled:opacity-45 disabled:cursor-not-allowed`}
            >
              <FiPlay size={13} />
              {status.last_exit_code && status.last_exit_code !== 0 ? 'Restart Scraper' : 'Run One Scrape'}
            </button>
            <button
              onClick={scrollToBottom}
              className="px-4 py-2 rounded-md text-sm bg-slate-700 text-slate-100 border border-slate-600 hover:bg-slate-600"
            >
              Jump To Latest
            </button>
            <button
              onClick={() => setOpen(false)}
              className="ml-auto px-4 py-2 rounded-md text-sm bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700"
            >
              <span className="inline-flex items-center gap-1"><FiX size={13} /> Close</span>
            </button>
          </div>

          {(actionMessage || fetchError) && (
            <div className="px-4 py-2 text-xs border-b border-slate-800 bg-[#0e1627]">
              {actionMessage && <span className="text-cyan-300 mr-4">{actionMessage}</span>}
              {fetchError === 'not-started' && (
                <span className="text-amber-300">Scraper not started. Use Run One Scrape.</span>
              )}
              {fetchError && fetchError !== 'not-started' && (
                <span className="text-rose-300">{fetchError}</span>
              )}
            </div>
          )}

          <div
            ref={termRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto px-4 py-3 font-mono text-[14px] leading-7"
          >
            {lines.length === 0 && !fetchError && (
              <p className="text-slate-500 italic">Waiting for scraper output...</p>
            )}
            {lines.map((line, i) => (
              <div key={`${i}-${line.slice(0, 16)}`} className={`whitespace-pre-wrap break-all ${lineClass(line)}`}>
                {line}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}
