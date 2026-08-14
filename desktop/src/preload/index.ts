import { contextBridge, shell } from 'electron'

const api = {
  getInfo: (): { port: number; backendUrl: string } => ({
    port: 8765,
    backendUrl: 'http://127.0.0.1:8765'
  }),
  openExternal: (url: string): Promise<void> => shell.openExternal(url)
}

contextBridge.exposeInMainWorld('api', api)
