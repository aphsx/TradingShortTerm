import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      binance: {
        getAccount: () => Promise<{
          accountType?: string
          canTrade?: boolean
          canWithdraw?: boolean
          canDeposit?: boolean
          updateTime?: number
          balances: Array<{ asset: string; free: number; locked: number }>
        }>
      }
    }
  }
}
