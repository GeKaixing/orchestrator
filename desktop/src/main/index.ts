import { app, BrowserWindow, dialog } from 'electron'
import { spawn, type ChildProcess } from 'child_process'
import { join, resolve } from 'path'
import http from 'http'

const BACKEND_PORT = 8765
// desktop/out/main -> ../../.. = orchestrator 根目录
const ORCH_DIR = resolve(__dirname, '../../..')

let backendProc: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null

function isDev(): boolean {
  return !app.isPackaged
}

function waitForBackend(timeoutMs: number, port: number): Promise<void> {
  const start = Date.now()
  return new Promise((resolvePromise, reject) => {
    const retry = (): void => {
      if (Date.now() - start > timeoutMs) {
        reject(new Error('后端 90s 内未就绪'))
        return
      }
      setTimeout(tryOnce, 1000)
    }
    const tryOnce = (): void => {
      const req = http.get(
        { host: '127.0.0.1', port, path: '/api/health', timeout: 2000 },
        (res) => {
          res.resume()
          if (res.statusCode === 200) resolvePromise()
          else retry()
        }
      )
      req.on('error', retry)
      req.on('timeout', () => {
        req.destroy()
        retry()
      })
    }
    tryOnce()
  })
}

function startBackend(): ChildProcess {
  const proc = spawn('uv', ['run', 'python', '-m', 'backend'], {
    cwd: ORCH_DIR,
    env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe']
  })
  proc.stdout?.on('data', (d) => console.log('[backend]', String(d).trim()))
  proc.stderr?.on('data', (d) => console.error('[backend]', String(d).trim()))
  proc.on('exit', (code) => console.log('[backend] exited', code))
  return proc
}

function stopBackend(): void {
  if (!backendProc || backendProc.pid === undefined) return
  if (process.platform === 'win32') {
    spawn('taskkill', ['/T', '/F', '/PID', String(backendProc.pid)], { windowsHide: true })
  } else {
    backendProc.kill()
  }
  backendProc = null
}

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 1000,
    minHeight: 640,
    title: '达人招商编排客户端',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  })
  if (isDev() && process.env['ELECTRON_RENDERER_URL']) {
    await mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    await mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(async () => {
  backendProc = startBackend()
  try {
    await waitForBackend(120000, BACKEND_PORT)
  } catch (err) {
    dialog.showErrorBox(
      '后端启动失败',
      `无法连接本地后端 (127.0.0.1:${BACKEND_PORT})。\n\n请确认已安装 uv 并在 orchestrator 根目录执行过 uv sync。\n\n${String(err)}`
    )
    app.quit()
    return
  }
  await createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) void createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('will-quit', () => {
  stopBackend()
})
