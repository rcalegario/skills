export type Due = number | null

declare module 'claude-code' {
  interface PluginState {
    'retro-report': { due: Due; isHidden: boolean }
  }
}
