import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// The app is an installable PWA: the app shell is cached by a service worker, and the
// last timetable data is kept by src/api/client.ts, so it opens with no connection.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'Department Timetables',
        short_name: 'Timetables',
        description: 'Clash-free timetables, live absences and extra sessions.',
        theme_color: '#001858',
        background_color: '#f8f9fc',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        // API on the same domain under /api (downloads are page navigations): never answer
        // those with the app page.
        navigateFallbackDenylist: [/^\/api\//, /^\/docs/],
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
      },
    }),
  ],
})
