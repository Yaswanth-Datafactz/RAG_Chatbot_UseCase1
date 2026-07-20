import { BrowserRouter, Outlet, Route, Routes, useParams } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { NAV_ITEMS } from './components/layout/nav'
import { ConversationList } from './components/chat/ConversationList'
import { useConversations } from './components/chat/useConversations'
import { ChatPage } from './pages/Chat'
import { AdminPage } from './pages/Admin'

export interface ChatOutletContext {
  addConversation: ReturnType<typeof useConversations>['addConversation']
  refreshConversationTitle: ReturnType<typeof useConversations>['refreshConversationTitle']
}

/** The one place a use case wires its own nav/branding into the shared
 * AppShell -- Admin (Phase 6) reuses it via a sibling <Route> below rather
 * than a second shell, per docs/phase-5.md's documented extension point.
 *
 * useConversations() lives here (not inside ConversationList) so ChatPage
 * -- a route sibling, not a child, of ConversationList -- can share the
 * same conversation list state via <Outlet context>: starting a chat
 * directly on "/" (no prior "New conversation" click) needs to add that
 * conversation to the sidebar's own state, and a first message needs to
 * refresh that same conversation's auto-assigned title once it lands. */
function Layout() {
  const { conversationId } = useParams<{ conversationId?: string }>()
  const { conversations, status, errorMessage, refresh, addConversation, removeConversation, refreshConversationTitle } =
    useConversations()

  return (
    <AppShell
      navItems={NAV_ITEMS}
      productName="Knowledge Assistant"
      pageTitle="Contoso Corp Knowledge Assistant"
      sidebarExtra={
        <ConversationList
          activeConversationId={conversationId}
          conversations={conversations}
          status={status}
          errorMessage={errorMessage}
          refresh={refresh}
          addConversation={addConversation}
          removeConversation={removeConversation}
        />
      }
    >
      <Outlet context={{ addConversation, refreshConversationTitle } satisfies ChatOutletContext} />
    </AppShell>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<ChatPage />} />
          <Route path="/c/:conversationId" element={<ChatPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
