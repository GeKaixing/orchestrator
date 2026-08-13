/// <reference types="vite/client" />

interface Window {
  api: {
    getInfo(): { port: number; backendUrl: string }
  }
}
