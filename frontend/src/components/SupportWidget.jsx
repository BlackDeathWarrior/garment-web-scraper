import { useEffect } from 'react'
import {
  adminSession,
  chatIdentity,
  currentVisitor,
  getSupportConfig,
  getSupportContext,
  onSupportContext,
} from '../lib/support'

const THEME = { primary: '#8B1A1A', onPrimary: '#ffffff', radius: 16, position: 'right' }
const STRINGS = {
  launcher: 'Chat with us',
  title: 'Ethnic Threads support',
  intro: 'Ask about a listing, a price or the site. We usually reply in a few minutes.',
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (window.TMSChat) return resolve()
    const existing = document.querySelector(`script[src="${src}"]`)
    const script = existing || document.createElement('script')
    script.addEventListener('load', () => resolve())
    script.addEventListener('error', () => reject(new Error('The chat could not be loaded')))
    if (!existing) {
      script.src = src
      script.async = true
      document.body.appendChild(script)
    }
  })
}

/**
 * The support desk's chat widget, in the storefront's colours. It is told
 * which listing the visitor has open, and the signed-in admin is vouched for
 * by a token the worker signs. Renders nothing itself; with no support desk
 * configured it does nothing.
 */
export default function SupportWidget() {
  useEffect(() => {
    let chat = null
    let stopListening = () => {}
    let cancelled = false

    const start = async () => {
      const config = await getSupportConfig()
      if (cancelled || !config.widget) return
      try {
        await loadScript(config.widget.script)
      } catch {
        return
      }
      if (cancelled || !window.TMSChat) return

      let identityToken
      if (adminSession()) {
        identityToken = (await chatIdentity().catch(() => ({}))).token || undefined
      }
      if (cancelled) return

      const visitor = currentVisitor()
      chat = window.TMSChat.init({
        server: config.widget.server,
        integration: config.widget.integration,
        theme: THEME,
        strings: STRINGS,
        visitor: visitor.name || visitor.email ? visitor : undefined,
        context: getSupportContext(),
        identityToken,
      })
      stopListening = onSupportContext((context) => chat?.setContext(context))
    }
    void start()

    return () => {
      cancelled = true
      stopListening()
      chat?.destroy()
    }
  }, [])

  return null
}
