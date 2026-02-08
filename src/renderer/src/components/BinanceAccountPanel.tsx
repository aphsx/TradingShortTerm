import React, { useEffect, useState } from 'react'

type BinanceBalance = { asset: string; free: number; locked: number }

type BinanceAccount = {
  accountType?: string
  canTrade?: boolean
  canWithdraw?: boolean
  canDeposit?: boolean
  updateTime?: number
  balances: BinanceBalance[]
}

export default function BinanceAccountPanel(): React.ReactElement {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [account, setAccount] = useState<BinanceAccount | null>(null)

  const fetchAccount = async (): Promise<void> => {
    try {
      setLoading(true)
      setError(null)
      const data = await window.api.binance.getAccount()
      setAccount(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load Binance account')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAccount()
  }, [])

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Binance Account</h2>
          <p className="text-gray-600 text-sm">Balances from Binance (via Electron main process)</p>
        </div>
        <button
          onClick={fetchAccount}
          className="px-3 py-2 rounded bg-gray-900 text-white text-sm hover:bg-gray-800 disabled:opacity-60"
          disabled={loading}
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {error && <div className="mt-4 text-red-600 text-sm">{error}</div>}

      {!error && loading && (
        <div className="mt-4 text-gray-500 text-sm">Loading Binance account...</div>
      )}

      {!error && !loading && account && (
        <>
          <div className="mt-6 overflow-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="py-2 pr-4">Asset</th>
                  <th className="py-2 pr-4">Free</th>
                  <th className="py-2 pr-4">Locked</th>
                  <th className="py-2 pr-4">Total</th>
                </tr>
              </thead>
              <tbody>
                {account.balances
                  .slice()
                  .sort((a, b) => b.free + b.locked - (a.free + a.locked))
                  .map((b) => (
                    <tr key={b.asset} className="border-b last:border-b-0">
                      <td className="py-2 pr-4 font-medium text-gray-800">{b.asset}</td>
                      <td className="py-2 pr-4 text-gray-700">{b.free.toFixed(8)}</td>
                      <td className="py-2 pr-4 text-gray-700">{b.locked.toFixed(8)}</td>
                      <td className="py-2 pr-4 text-gray-900">{(b.free + b.locked).toFixed(8)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!error && !loading && !account && <div className="mt-4 text-gray-500 text-sm">No data.</div>}
    </div>
  )
}
