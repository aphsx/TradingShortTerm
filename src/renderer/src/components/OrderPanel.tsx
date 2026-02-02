import { useState } from 'react'
import { apiService, OrderRequest } from '../services/api'
import { useTradingStore } from '../store/trading'

export function OrderPanel(): JSX.Element {
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY')
  const [quantity, setQuantity] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const currentPrice = useTradingStore((state) => state.currentPrice)

  const handlePlaceOrder = async (): Promise<void> => {
    if (!quantity || parseFloat(quantity) <= 0) {
      setMessage({ type: 'error', text: 'Please enter a valid quantity' })
      return
    }

    if (!currentPrice) {
      setMessage({ type: 'error', text: 'Waiting for price data...' })
      return
    }

    setLoading(true)
    setMessage(null)

    try {
      const order: OrderRequest = {
        symbol: currentPrice.symbol,
        side,
        quantity,
        type: 'MARKET'
      }

      const response = await apiService.placeOrder(order)
      setMessage({
        type: 'success',
        text: `Order placed successfully! ${response.message || ''}`
      })
      setQuantity('')
    } catch (error) {
      setMessage({
        type: 'error',
        text: `Failed to place order: ${error instanceof Error ? error.message : 'Unknown error'}`
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        padding: '15px',
        background: '#252525',
        borderRadius: '8px'
      }}
    >
      <h3 style={{ margin: '0 0 15px 0', fontSize: '16px', color: '#fff' }}>📊 Place Order</h3>

      {/* Side selector */}
      <div style={{ marginBottom: '15px' }}>
        <label style={{ display: 'block', fontSize: '12px', color: '#888', marginBottom: '8px' }}>
          Order Type
        </label>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={() => setSide('BUY')}
            disabled={loading}
            style={{
              flex: 1,
              padding: '10px',
              background: side === 'BUY' ? '#4caf50' : '#2b2b2b',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontWeight: 'bold',
              transition: 'all 0.2s'
            }}
          >
            🟢 BUY
          </button>
          <button
            onClick={() => setSide('SELL')}
            disabled={loading}
            style={{
              flex: 1,
              padding: '10px',
              background: side === 'SELL' ? '#f44336' : '#2b2b2b',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontWeight: 'bold',
              transition: 'all 0.2s'
            }}
          >
            🔴 SELL
          </button>
        </div>
      </div>

      {/* Quantity input */}
      <div style={{ marginBottom: '15px' }}>
        <label
          htmlFor="quantity"
          style={{ display: 'block', fontSize: '12px', color: '#888', marginBottom: '8px' }}
        >
          Quantity ({currentPrice?.symbol.replace('USDT', '') || 'BTC'})
        </label>
        <input
          id="quantity"
          type="number"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          placeholder="0.001"
          step="0.001"
          min="0"
          disabled={loading}
          style={{
            width: '100%',
            padding: '10px',
            background: '#1e1e1e',
            border: '1px solid #2b2b2b',
            borderRadius: '6px',
            color: '#fff',
            fontSize: '14px',
            boxSizing: 'border-box'
          }}
        />
      </div>

      {/* Current price info */}
      {currentPrice && (
        <div
          style={{
            padding: '10px',
            background: '#1e1e1e',
            borderRadius: '6px',
            marginBottom: '15px',
            fontSize: '12px',
            color: '#888'
          }}
        >
          <div>
            Current Price: <span style={{ color: '#2962FF', fontWeight: 'bold' }}>
              ${parseFloat(currentPrice.price).toFixed(2)}
            </span>
          </div>
          {quantity && parseFloat(quantity) > 0 && (
            <div style={{ marginTop: '5px' }}>
              Total: <span style={{ color: '#fff', fontWeight: 'bold' }}>
                ${(parseFloat(quantity) * parseFloat(currentPrice.price)).toFixed(2)} USDT
              </span>
            </div>
          )}
        </div>
      )}

      {/* Place order button */}
      <button
        onClick={handlePlaceOrder}
        disabled={loading || !currentPrice}
        style={{
          width: '100%',
          padding: '12px',
          background: side === 'BUY' ? '#4caf50' : '#f44336',
          color: '#fff',
          border: 'none',
          borderRadius: '6px',
          cursor: loading || !currentPrice ? 'not-allowed' : 'pointer',
          fontSize: '14px',
          fontWeight: 'bold',
          opacity: loading || !currentPrice ? 0.6 : 1,
          transition: 'all 0.2s'
        }}
      >
        {loading ? '⏳ Placing Order...' : `${side === 'BUY' ? '🟢 BUY' : '🔴 SELL'} ${currentPrice?.symbol || 'BTCUSDT'}`}
      </button>

      {/* Status message */}
      {message && (
        <div
          style={{
            marginTop: '15px',
            padding: '10px',
            background: message.type === 'success' ? '#1b5e20' : '#b71c1c',
            borderRadius: '6px',
            fontSize: '12px',
            color: '#fff'
          }}
        >
          {message.text}
        </div>
      )}

      <div
        style={{
          marginTop: '15px',
          padding: '10px',
          background: '#1e1e1e',
          borderRadius: '6px',
          fontSize: '11px',
          color: '#888'
        }}
      >
        ⚠️ <strong>Testnet Mode</strong> - Using test funds only
      </div>
    </div>
  )
}
