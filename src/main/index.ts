import { app, shell, BrowserWindow, ipcMain } from 'electron'
import { join } from 'path'
import { readFileSync, existsSync } from 'fs'
import crypto from 'crypto'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'

type BinanceAccountBalance = {
  asset: string
  free: string
  locked: string
}

type BinanceAccountResponse = {
  accountType?: string
  canTrade?: boolean
  canWithdraw?: boolean
  canDeposit?: boolean
  updateTime?: number
  balances?: BinanceAccountBalance[]
}

let binanceTimeOffsetMs = 0
let binanceTimeOffsetUpdatedAt = 0

async function getBinanceServerTimeMs(baseUrl: string): Promise<number> {
  const url = new URL(baseUrl)
  url.pathname = '/api/v3/time'
  const res = await fetch(url.toString(), { method: 'GET' })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Binance time error ${res.status}: ${text || res.statusText}`)
  }
  const data = (await res.json()) as { serverTime?: number }
  if (!data?.serverTime || typeof data.serverTime !== 'number') {
    throw new Error('Binance time response invalid')
  }
  return data.serverTime
}

async function ensureBinanceTimeOffset(baseUrl: string): Promise<void> {
  const now = Date.now()
  if (binanceTimeOffsetUpdatedAt && now - binanceTimeOffsetUpdatedAt < 60_000) return
  const serverTime = await getBinanceServerTimeMs(baseUrl)
  binanceTimeOffsetMs = serverTime - now
  binanceTimeOffsetUpdatedAt = now
}

function loadEnvFile(filePath: string, overrideExisting = false): void {
  try {
    if (!existsSync(filePath)) return
    const content = readFileSync(filePath, 'utf8')
    for (const rawLine of content.split(/\r?\n/)) {
      const line = rawLine.trim()
      if (!line || line.startsWith('#')) continue
      const eq = line.indexOf('=')
      if (eq === -1) continue
      const key = line.slice(0, eq).trim()
      let value = line.slice(eq + 1).trim()
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1)
      }
      if (overrideExisting || process.env[key] === undefined || process.env[key] === '') {
        process.env[key] = value
      }
    }
  } catch (e) {
    console.error('Failed to load env file:', filePath, e)
  }
}

async function binanceSignedGet(
  pathname: string,
  params: Record<string, string | number> = {}
): Promise<unknown> {
  const apiKey = (process.env.BINANCE_API_KEY || '').trim().replace(/\r|\n/g, '')
  const apiSecret = (process.env.BINANCE_API_SECRET || '').trim().replace(/\r|\n/g, '')
  const baseUrl = (process.env.BINANCE_BASE_URL || 'https://testnet.binance.vision').trim()

  if (!apiKey || !apiSecret) {
    throw new Error('Missing BINANCE_API_KEY or BINANCE_API_SECRET')
  }

  if (apiKey.includes(' ') || apiSecret.includes(' ')) {
    throw new Error(
      'BINANCE_API_KEY/BINANCE_API_SECRET contains spaces. Ensure the values are pasted as a single token with no prefix like "secret ".'
    )
  }

  if (apiSecret.toLowerCase().startsWith('secret')) {
    throw new Error(
      'BINANCE_API_SECRET looks like it includes a prefix (e.g. "secret ..."). Please set only the secret value in .env.local.'
    )
  }

  const url = new URL(baseUrl)
  url.pathname = pathname

  await ensureBinanceTimeOffset(baseUrl)

  const query = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) query.set(k, String(v))
  const timestamp = Date.now() + binanceTimeOffsetMs
  const recvWindow = process.env.BINANCE_RECV_WINDOW || '10000'
  query.set('timestamp', String(timestamp))
  query.set('recvWindow', recvWindow)

  const signature = crypto.createHmac('sha256', apiSecret).update(query.toString()).digest('hex')
  query.set('signature', signature)
  url.search = query.toString()

  const res = await fetch(url.toString(), {
    method: 'GET',
    headers: {
      'X-MBX-APIKEY': apiKey
    }
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    const safeDiagnostics = {
      baseUrl,
      pathname,
      apiKeyLength: apiKey.length,
      apiSecretLength: apiSecret.length,
      timestamp,
      recvWindow,
      query: query.toString()
    }
    throw new Error(
      `Binance error ${res.status}: ${text || res.statusText}\nDiagnostics: ${JSON.stringify(
        safeDiagnostics
      )}`
    )
  }

  return res.json()
}

function createWindow(): void {
  // Create the browser window.
  const mainWindow = new BrowserWindow({
    width: 900,
    height: 670,
    show: false,
    autoHideMenuBar: true,
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // HMR for renderer base on electron-vite cli.
  // Load the remote URL for development or the local html file for production.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.whenReady().then(() => {
  loadEnvFile(join(process.cwd(), '.env'))
  loadEnvFile(join(process.cwd(), '.env.local'), true)

  // Set app user model id for windows
  electronApp.setAppUserModelId('com.electron')

  // Default open or close DevTools by F12 in development
  // and ignore CommandOrControl + R in production.
  // see https://github.com/alex8088/electron-toolkit/tree/master/packages/utils
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // IPC test
  ipcMain.on('ping', () => console.log('pong'))

  ipcMain.handle('binance:getAccount', async () => {
    const data = (await binanceSignedGet('/api/v3/account')) as BinanceAccountResponse
    const rawBalances = Array.isArray(data?.balances) ? data.balances : []
    const balances = rawBalances
      .map((b) => ({
        asset: b.asset,
        free: Number(b.free),
        locked: Number(b.locked)
      }))
      .filter(
        (b) =>
          Number.isFinite(b.free) &&
          Number.isFinite(b.locked) &&
          (b.free !== 0 || b.locked !== 0)
      )

    return {
      accountType: data?.accountType,
      canTrade: data?.canTrade,
      canWithdraw: data?.canWithdraw,
      canDeposit: data?.canDeposit,
      updateTime: data?.updateTime,
      balances
    }
  })

  createWindow()

  app.on('activate', function () {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
