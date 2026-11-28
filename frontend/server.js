// Serve the web app on a hosting panel (e.g. a Pterodactyl Node.js server). No dependencies.
//
//   node frontend/server.js
//
// On start: installs the packages and builds the app (skip with SKIP_BUILD=1), then serves
// frontend/dist/ and forwards /api/... to the API (API_TARGET), so one address serves both.
// Settings are read from frontend/.env (KEY=VALUE lines) or the environment:
//   API_TARGET   address of the API server, e.g. http://203.0.113.10:25566 (required)
//   VITE_API_URL /api (the web app calls the API through this server)
//   TLS_CERT, TLS_KEY  certificate and key files (relative to frontend/) (e.g. a Cloudflare origin certificate):
//                when both exist the server speaks HTTPS, otherwise plain HTTP
//   SERVER_PORT  port to listen on (set by the panel), or PORT, or 8080
import { spawnSync } from 'node:child_process'
import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs'
import http from 'node:http'
import https from 'node:https'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const DIST = path.join(HERE, 'dist')

const envFile = path.join(HERE, '.env')
if (existsSync(envFile)) {
  for (const line of readFileSync(envFile, 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$/)
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^['"]|['"]$/g, '')
  }
}
const env = process.env
const PORT = Number(env.SERVER_PORT || env.PORT || 8080)
if (!env.API_TARGET) {
  console.error('API_TARGET is missing (frontend/.env), e.g. API_TARGET=http://203.0.113.10:25566')
  process.exit(1)
}
const API = new URL(env.API_TARGET)

if (env.SKIP_BUILD !== '1') {
  const run = (args) => {
    console.log(`> npm ${args.join(' ')}`)
    const r = spawnSync('npm', args, { cwd: HERE, stdio: 'inherit', env: { ...env, VITE_API_URL: env.VITE_API_URL || '/api' } })
    if (r.status !== 0) process.exit(r.status ?? 1)
  }
  run(['install', '--no-audit', '--no-fund'])
  run(['run', 'build'])
}
if (!existsSync(path.join(DIST, 'index.html'))) {
  console.error('frontend/dist/index.html not found: the build did not run')
  process.exit(1)
}

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.ico': 'image/x-icon', '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json', '.txt': 'text/plain; charset=utf-8',
}

function sendFile(res, file) {
  const name = path.basename(file)
  // Built assets have a hash in their name: cache them for long. The page, the service worker
  // and the manifest must always be fresh, or a new version never reaches the phones.
  const cache = file.includes(`${path.sep}assets${path.sep}`)
    ? 'public, max-age=31536000, immutable'
    : name === 'index.html' || name === 'sw.js' || name.endsWith('.webmanifest') || name.startsWith('workbox-')
      ? 'no-cache'
      : 'public, max-age=3600'
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream', 'Cache-Control': cache })
  createReadStream(file).pipe(res)
}

// ------------------------------------------------------------------ link previews
// Apps that show link previews (WhatsApp, Telegram, Facebook...) read the page's <meta> tags
// without running JavaScript. So the page is served with its own title, and full addresses.
const INDEX = path.join(DIST, 'index.html')
let groupNames = { at: 0, byId: new Map() }

function fetchJson(pathname) {
  return new Promise((resolve, reject) => {
    const r = (API.protocol === 'https:' ? https : http).get(
      { hostname: API.hostname, port: API.port || (API.protocol === 'https:' ? 443 : 80), path: pathname, timeout: 3000 },
      (up) => {
        let body = ''
        up.on('data', (c) => (body += c))
        up.on('end', () => {
          try {
            resolve(JSON.parse(body))
          } catch (e) {
            reject(e)
          }
        })
      },
    )
    r.on('timeout', () => r.destroy(new Error('timeout')))
    r.on('error', reject)
  })
}

/** Group id -> name, refreshed at most once a minute. */
async function groupName(id) {
  if (Date.now() - groupNames.at > 60_000) {
    const byId = new Map()
    const walk = (n) => (byId.set(String(n.id), n.name), n.children.forEach(walk))
    try {
      for (const lv of await fetchJson('/public/groups')) lv.sections.forEach(walk)
      groupNames = { at: Date.now(), byId }
    } catch {
      /* API unreachable: keep the generic preview */
    }
  }
  return groupNames.byId.get(String(id))
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const setMeta = (html, attr, key, value) =>
  html.replace(new RegExp(`(<meta ${attr}="${key}" content=")[^"]*(")`), `$1${esc(value)}$2`)

async function sendIndex(req, res, url) {
  const origin = `${req.headers['x-forwarded-proto'] || (tls ? 'https' : 'http')}://${req.headers.host}`
  let html = readFileSync(INDEX, 'utf8')
  const m = url.match(/^\/g\/(\d+)/)
  const name = m && (await groupName(m[1]))
  if (name) {
    const title = `${name} · Timetable`
    const text = `This week's classes for ${name}, always up to date: cancelled classes and extra sessions shown live. Works offline.`
    html = html.replace(/<title>[^<]*<\/title>/, `<title>${esc(title)}</title>`)
    html = setMeta(html, 'property', 'og:title', title)
    html = setMeta(html, 'property', 'og:description', text)
    html = setMeta(html, 'name', 'description', text)
  }
  html = setMeta(html, 'property', 'og:url', origin + url)
  html = setMeta(html, 'property', 'og:image', origin + '/og-image.png')
  res.writeHead(200, { 'Content-Type': TYPES['.html'], 'Cache-Control': 'no-cache' })
  res.end(html)
}

function serveStatic(req, res) {
  let url
  try {
    url = decodeURIComponent((req.url || '/').split('?')[0])
  } catch {
    url = '/'
  }
  const file = path.normalize(path.join(DIST, url))
  if (file !== INDEX && file.startsWith(DIST + path.sep) && existsSync(file) && statSync(file).isFile()) return sendFile(res, file)
  sendIndex(req, res, url).catch(() => sendFile(res, INDEX)) // app routes like /g/12 (QR codes)
}

function proxy(req, res) {
  const upstream = (API.protocol === 'https:' ? https : http).request(
    {
      hostname: API.hostname,
      port: API.port || (API.protocol === 'https:' ? 443 : 80),
      method: req.method,
      path: req.url.replace(/^\/api/, '') || '/',
      headers: { ...req.headers, host: API.host, 'x-forwarded-proto': 'https', 'x-forwarded-for': req.socket.remoteAddress },
      timeout: 120_000, // generating a timetable takes about 10 s
    },
    (up) => {
      res.writeHead(up.statusCode || 502, up.headers)
      up.pipe(res)
    },
  )
  upstream.on('timeout', () => upstream.destroy(new Error('timeout')))
  upstream.on('error', (e) => {
    console.error('API unreachable:', e.message)
    if (!res.headersSent) res.writeHead(502, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ detail: 'The API server is not reachable' }))
  })
  req.pipe(upstream)
}

const handler = (req, res) => ((req.url || '').startsWith('/api/') ? proxy(req, res) : serveStatic(req, res))
// Certificate paths may be relative to this folder, e.g. TLS_CERT=certs/origin.pem
const cert = env.TLS_CERT && path.resolve(HERE, env.TLS_CERT)
const key = env.TLS_KEY && path.resolve(HERE, env.TLS_KEY)
const tls = cert && key && existsSync(cert) && existsSync(key)
if (!cert || !key) console.warn('No TLS_CERT / TLS_KEY in frontend/.env: serving plain HTTP')
else if (!tls) console.warn(`Certificate not found (${existsSync(cert) ? '' : cert + ' '}${existsSync(key) ? '' : key}): serving plain HTTP`)
const server = tls
  ? https.createServer({ cert: readFileSync(cert), key: readFileSync(key) }, handler)
  : http.createServer(handler)
server.listen(PORT, '0.0.0.0', () =>
  console.log(`Web app on ${tls ? 'https' : 'http'}://0.0.0.0:${PORT}, API at ${API.origin}`),
)
