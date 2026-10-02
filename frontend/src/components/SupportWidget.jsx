import { useEffect } from 'react'
import { useUser } from '../lib/auth'
import { chatIdentity, getSupportConfig, getSupportContext, onSupportContext } from '../lib/support'

const THEME = { primary: '#8B1A1A', onPrimary: '#ffffff', radius: 16, position: 'right' }
const STRINGS = {
  launcher: 'Chat with us',
  title: 'Ethnic Threads support',
  intro: 'Ask about an order, a product or the site. Sign in and we can look up your orders for you.',
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
 * The support desk's chat widget, in the shop's colours. It is told what the
 * visitor is looking at (a product, an order), and a signed-in shopper is
 * vouched for by a token the shop's server signs, so support knows whose
 * orders it may talk about. Renders nothing itself; with no support desk
 * configured it does nothing.
 */
export default function SupportWidget() {
  const user = useUser()
  // Signing in or out starts the chat again as that person.
  const who = user ? `${user.role}:${user.id}` : 'guest'

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
      if (user) identityToken = (await chatIdentity().catch(() => ({}))).token || undefined
      if (cancelled) return

      chat = window.TMSChat.init({
        server: config.widget.server,
        integration: config.widget.integration,
        theme: THEME,
        strings: STRINGS,
        visitor: user ? { name: user.name, email: user.email || undefined } : undefined,
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [who])

  return null
}
