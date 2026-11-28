import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { PublicLayout, Shell } from './components/Layout'
import { ConfigProvider, ToastProvider, useAuth } from './lib/hooks'
import { Dashboard, Timetable } from './pages/admin/timetable'
import { Levels, Modules, Professors, Rooms } from './pages/admin/data'
import { Import } from './pages/admin/import'
import { Activity, Settings } from './pages/admin/settings'
import { ProfAvailability, ProfBookings, ProfExtra, ProfWeek } from './pages/prof'
import { FreeRooms, GroupWeek, Home, Login } from './pages/public'

const ADMIN_NAV = [
  {
    label: 'Overview',
    items: [
      { to: '/admin', label: 'Dashboard', icon: 'grid', end: true },
      { to: '/admin/timetable', label: 'Timetable', icon: 'calendar' },
    ],
  },
  {
    label: 'Department',
    items: [
      { to: '/admin/import', label: 'Import files', icon: 'upload' },
      { to: '/admin/levels', label: 'Levels', icon: 'layers' },
      { to: '/admin/modules', label: 'Modules', icon: 'book' },
      { to: '/admin/professors', label: 'Professors', icon: 'users' },
      { to: '/admin/rooms', label: 'Rooms', icon: 'door' },
    ],
  },
  {
    label: 'Monitoring',
    items: [
      { to: '/admin/settings', label: 'Settings', icon: 'settings' },
      { to: '/admin/activity', label: 'Activity', icon: 'history' },
    ],
  },
]

const PROF_NAV = [
  {
    label: 'My space',
    items: [
      { to: '/prof', label: 'My week', icon: 'calendar', end: true },
      { to: '/prof/extra', label: 'Extra session', icon: 'plus' },
      { to: '/prof/bookings', label: 'Absences & bookings', icon: 'history' },
      { to: '/prof/availability', label: 'My availability', icon: 'clock' },
    ],
  },
  { label: 'Students', items: [{ to: '/', label: 'Group timetables', icon: 'users', end: true }] },
]

function RequireRole({ role, children }: { role: 'admin' | 'prof'; children: ReactNode }) {
  const auth = useAuth()
  if (!auth) return <Navigate to="/login" replace />
  if (auth.role !== role) return <Navigate to={auth.role === 'admin' ? '/admin' : '/prof'} replace />
  return children
}

export default function App() {
  return (
    <ConfigProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<PublicLayout />}>
              <Route index element={<Home />} />
              <Route path="g/:id" element={<GroupWeek />} />
              <Route path="free-rooms" element={<FreeRooms />} />
              <Route path="login" element={<Login />} />
            </Route>
            <Route
              path="admin"
              element={
                <RequireRole role="admin">
                  <Shell sections={ADMIN_NAV} />
                </RequireRole>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="timetable" element={<Timetable />} />
              <Route path="import" element={<Import />} />
              <Route path="levels" element={<Levels />} />
              <Route path="modules" element={<Modules />} />
              <Route path="professors" element={<Professors />} />
              <Route path="rooms" element={<Rooms />} />
              <Route path="settings" element={<Settings />} />
              <Route path="activity" element={<Activity />} />
            </Route>
            <Route
              path="prof"
              element={
                <RequireRole role="prof">
                  <Shell sections={PROF_NAV} />
                </RequireRole>
              }
            >
              <Route index element={<ProfWeek />} />
              <Route path="extra" element={<ProfExtra />} />
              <Route path="bookings" element={<ProfBookings />} />
              <Route path="availability" element={<ProfAvailability />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </ConfigProvider>
  )
}
