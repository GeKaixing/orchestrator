import { contextBridge } from 'electron'

const api = {
  getInfo: (): { port: number; backendUrl: string } => ({
    port: 8765,
    backendUrl: 'http://127.0.0.1:8765'
  })
}

contextBridge.exposeInMainWorld('api', api)
