// Today's worth sessions no retro names, and the first of them; null draws no band.
export type Due = { count: number; session: string } | null

declare module 'claude-code' {
  interface PluginState {
    'retro-report': { due: Due; isHidden: boolean }
  }
}
