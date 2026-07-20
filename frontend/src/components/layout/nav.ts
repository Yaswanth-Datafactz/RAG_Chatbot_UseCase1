import { LayoutDashboard, MessageSquare } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  /** Custom active-match predicate, for items whose page covers more than
   * one route (Chat covers both "/" and "/c/:id"). Falls back to an exact
   * pathname match when omitted -- sufficient for a simple item like
   * Admin. */
  isActive?: (pathname: string) => boolean
}

export const NAV_ITEMS: NavItem[] = [
  {
    label: 'Chat',
    to: '/',
    icon: MessageSquare,
    isActive: (pathname) => pathname === '/' || pathname.startsWith('/c/'),
  },
  {
    label: 'Admin',
    to: '/admin',
    icon: LayoutDashboard,
  },
]
