/**
 * Whether this person may change what applies to the whole instance: Settings
 * > System's instance cards, the Files, Notifications and Backup tabs, the
 * integrations, the default units, search providers.
 *
 * ★ `isAdmin || authMode === 'none'`, NEVER `isAdmin` ALONE. With sign-in off
 * the server allows instance administration and returns no user
 * (`app/services/auth.py`), so `AuthContext` reports `isAdmin === false` for
 * the one person using the app. An `isAdmin` gate hides these settings from
 * exactly that person.
 *
 * Its own module rather than a field on `AuthContext`: tests mock that module
 * with a partial `useAuth`, which a new export or field would be missing from.
 */

import { useAuth } from '@/contexts/AuthContext'

export function useCanManageInstance(): boolean {
  const { isAdmin, authMode } = useAuth()
  return isAdmin || authMode === 'none'
}
