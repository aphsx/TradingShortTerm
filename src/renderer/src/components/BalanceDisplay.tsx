import { useEffect, useState } from 'react'
import { apiService, Balance } from '../services/api'

export function BalanceDisplay(): JSX.Element {
  const [balances, setBalances] = useState<Balance[]>([])
  const [loading, setLoading] = useState(false)

  const fetchBalances = async (): Promise<void> => {
    setLoading(true)
    try {
      const data = await apiService.getBalance()
      // Filter to show only relevant balances
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
    // Refresh every 10 seconds
    const interval = setInterval(fetchBalances, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div
      style={{
        padding: '15px',
        background: '#252525',
        borderRadius: '8px',
        marginBottom: '15px'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <h3 style={{ margin: 0, fontSize: '16px', color: '#fff' }}>💰 Account Balance</h3>
        <button
          onClick={fetchBalances}
          disabled={loading}
          style={{
            padding: '5px 12px',
            background: '#2962FF',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
            cursor: loading ? 'not-allowed' : 'pointer',
            fontSize: '12px'
          }}
        >
          {loading ? '↻ Loading...' : '🔄 Refresh'}
        </button>
      </div>

      {balances.length === 0 ? (
        <p style={{ color: '#888', fontSize: '14px', margin: '10px 0' }}>
          {loading ? 'Loading balances...' : 'No balances available'}
        </p>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '10px' }}>
          {balances.map((balance) => (
            <div
              key={balance.asset}
              style={{
                padding: '10px',
                background: '#1e1e1e',
                borderRadius: '6px',
                border: '1px solid #2b2b2b'
              }}
            >
              <div style={{ fontSize: '12px', color: '#888', marginBottom: '4px' }}>{balance.asset}</div>
              <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#fff' }}>
                {parseFloat(balance.free).toFixed(4)}
              </div>
              {parseFloat(balance.locked) > 0 && (
                <div style={{ fontSize: '11px', color: '#f57c00', marginTop: '2px' }}>
                  Locked: {parseFloat(balance.locked).toFixed(4)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
