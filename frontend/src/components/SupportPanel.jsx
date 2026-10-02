import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FiActivity, FiAlertTriangle, FiCheckCircle, FiInbox } from 'react-icons/fi'
import { adminOverview, formatWhen, requestLink } from '../lib/support'

const REFRESH_MS = 10000

const EVENT_LABELS = {
  'ticket.created': 'New request',
  'ticket.updated': 'Request updated',
  'ticket.status_changed': 'Status changed',
  'ticket.assigned': 'Assigned',
  'message.created': 'Message',
  'incident.opened': 'Incident opened',
  'incident.updated': 'Incident still happening',
  'incident.resolved': 'Incident resolved',
  'approval.requested': 'Waiting for approval',
  'approval.decided': 'Approval decided',
  'csat.submitted': 'Rated',
  ping: 'Test delivery',
}

function describe(event) {
  if (event.incident) {
    const times = event.incident.occurrences > 1 ? ` (${event.incident.occurrences} times)` : ''
    return `${event.incident.title}${times}`
  }
  if (event.message) {
    const who = event.message.from === 'customer' ? 'Customer' : event.message.name || 'Support'
    return `${who}: ${event.message.preview}`
  }
  if (event.approval) return `${event.approval.action}: ${event.approval.status}`
  if (event.rating != null) return `${event.rating} out of 5`
  if (event.type === 'ticket.status_changed' && event.status) return `Now: ${event.status}`
  return event.subject || ''
}

/**
 * The admin's view of the support desk: what the scraper has reported, what
 * shoppers have asked, and what the desk has told us (its webhooks).
 */
export default function SupportPanel() {
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const found = await adminOverview()
        if (!active) return
        setOverview(found)
        setError('')
      } catch (err) {
        if (!active) return
        setError(err.status === 401 ? 'Sign in again to see the support desk.' : err.message)
      }
    }
    void load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  if (error) {
    return (
      <section className="p-6 rounded-2xl bg-white border border-gray-200 shadow-sm" aria-label="Support desk">
        <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-2">
          <FiInbox className="text-maroon-700" /> Support Desk
        </h2>
        <p className="text-sm text-gray-600">{error}</p>
      </section>
    )
  }
  if (!overview) return null
  const { configured } = overview
  if (!configured.tickets && !configured.incidents) return null

  const incidents = overview.incidents || []
  const tickets = overview.tickets || []
  const events = overview.events || []

  return (
    <section className="p-6 rounded-2xl bg-white border border-gray-200 shadow-sm space-y-6" aria-label="Support desk">
      <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
        <FiInbox className="text-maroon-700" /> Support Desk
      </h2>

      {configured.incidents && (
        <div aria-label="Open incidents">
          {incidents.length === 0 ? (
            <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 flex items-center gap-2">
              <FiCheckCircle /> No open incidents.
            </p>
          ) : (
            <ul className="space-y-2">
              {incidents.map((incident) => (
                <li
                  key={incident.id || incident.fingerprint}
                  className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-start gap-3"
                >
                  <FiAlertTriangle className="text-amber-600 mt-0.5 shrink-0" size={18} />
                  <div className="min-w-0 text-sm">
                    <p className="font-semibold text-amber-900 break-words">{incident.title}</p>
                    <p className="text-xs text-amber-800">
                      {incident.occurrences > 1 ? `Reported ${incident.occurrences} times` : 'Reported once'}
                      {' · since '}
                      {formatWhen(incident.firstSeenAt)}
                      {incident.ticket ? ` · ${incident.ticket}` : ''}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {overview.incidentsError && <p className="text-xs text-gray-500 mt-2">{overview.incidentsError}</p>}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        <div aria-label="Latest requests">
          <h3 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3">Latest requests</h3>
          {tickets.length === 0 ? (
            <p className="text-sm text-gray-500">{overview.ticketsError || 'No requests yet.'}</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {tickets.map((ticket) => (
                <li key={ticket.reference} className="py-2.5 flex items-center justify-between gap-3">
                  <Link to={requestLink(ticket.reference, ticket.token)} className="min-w-0 hover:text-maroon-700">
                    <span className="block text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                      {ticket.reference}
                    </span>
                    <span className="block text-sm font-semibold text-gray-900 truncate">{ticket.subject}</span>
                  </Link>
                  <span className="text-xs font-bold text-gray-600 bg-gray-100 rounded-full px-2.5 py-1 shrink-0">
                    {ticket.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div aria-label="Support desk activity">
          <h3 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-1.5">
            <FiActivity size={12} className="text-maroon-700" /> Activity from the support desk
          </h3>
          {!configured.webhooks ? (
            <p className="text-sm text-gray-500">Webhooks are not set up.</p>
          ) : events.length === 0 ? (
            <p className="text-sm text-gray-500">Nothing yet.</p>
          ) : (
            <ul className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {events.map((event) => (
                <li key={event.id} className="text-sm">
                  <span className="font-semibold text-gray-900">{EVENT_LABELS[event.type] || event.type}</span>
                  {event.reference && <span className="text-gray-500"> · {event.reference}</span>}
                  <span className="text-xs text-gray-400"> · {formatWhen(event.at || event.received_at)}</span>
                  <span className="block text-gray-600 break-words">{describe(event)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  )
}
