import { useEffect, useState } from 'react'
import { apiService, Balance } from '../services/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'
import { Button } from './ui/button'
import { Badge } from './ui/badge'
import { RefreshCw } from 'lucide-react'

export function BalanceDisplay() {
  const [balances, setBalances] = useState<Balance[]>([])
  const [loading, setLoading] = useState(false)

  const fetchBalances = async (): Promise<void> => {
    setLoading(true)
    try {
      const data = await apiService.getBalance()
      const relevantBalances = data.filter(
        (b) => ['USDT', 'BTC', 'ETH', 'BNB'].includes(b.asset)
      )
      setBalances(relevantBalances)
    } catch (error) {
      console.error('Error fetching balances:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchBalances()
    const interval = setInterval(fetchBalances, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <Card className="w-full border-amber-900/30 bg-gradient-to-b from-slate-900 to-slate-950">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg text-white">Account Balance</CardTitle>
            <CardDescription className="text-slate-400">
              {balances.length} assets available
            </CardDescription>
          </div>
          <Button
            onClick={fetchBalances}
            disabled={loading}
            size="sm"
            variant="outline"
            className="border-slate-700 text-slate-300 hover:bg-slate-800"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {balances.length === 0 ? (
          <div className="text-center py-6">
            <p className="text-slate-400 text-sm">
              {loading ? 'Loading balances...' : 'No balances available'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {balances.map((balance) => (
              <div
                key={balance.asset}
                className="flex items-center justify-between p-4 rounded-lg bg-slate-900/50 border border-slate-800 hover:border-slate-700 transition-colors"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <Badge variant="secondary" className="bg-amber-500/10 text-amber-400 border-amber-500/20 w-fit">
                      {balance.asset}
                    </Badge>
                    {parseFloat(balance.locked) > 0 && (
                      <span className="text-xs text-orange-400 bg-orange-500/10 px-2 py-1 rounded border border-orange-500/20">
                        Locked: {parseFloat(balance.locked).toFixed(4)}
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-white font-semibold font-mono">
                    {parseFloat(balance.free).toFixed(4)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
