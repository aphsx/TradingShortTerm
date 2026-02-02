import { useEffect } from 'react'
import { TradingChart } from './components/TradingChart'
import { BalanceDisplay } from './components/BalanceDisplay'
import { OrderPanel } from './components/OrderPanel'
import { wsService } from './services/websocket'
import { useTradingStore } from './store/trading'
import './assets/main.css'

function App(): React.JSX.Element {
  const isConnected = useTradingStore((state) => state.isConnected)
  const currentPrice = useTradingStore((state) => state.currentPrice)

  useEffect(() => {
    // Connect to WebSocket when component mounts
    // Wait a bit for backend to start
    const timer = setTimeout(() => {
      console.log('Connecting to backend WebSocket...')
      wsService.connect()
    }, 2000)

    // Cleanup: disconnect when component unmounts
    return () => {
      clearTimeout(timer)
      wsService.disconnect()
    }
  }, [])

  return (
    <div style={{ 
      width: '100vw', 
      height: '100vh', 
      display: 'flex', 
      flexDirection: 'column',
      background: '#1e1e1e',
      color: '#fff',
      margin: 0,
      padding: 0,
      overflow: 'hidden'
    }}>
      {/* Header */}
      <header style={{
        padding: '15px 20px',
        background: '#252525',
        borderBottom: '2px solid #2962FF',
        flexShrink: 0
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '24px' }}>
              ⚡ 24HrT Trading Bot
            </h1>
            <p style={{ margin: '5px 0 0 0', color: '#888', fontSize: '14px' }}>
              Real-time Binance Trading Dashboard
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ 
              display: 'inline-block',
              padding: '8px 16px',
              background: isConnected ? '#1b5e20' : '#b71c1c',
              borderRadius: '20px',
              fontSize: '12px',
              fontWeight: 'bold'
            }}>
              {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
            </div>
            {currentPrice && (
              <div style={{ marginTop: '8px', fontSize: '12px', color: '#888' }}>
                {currentPrice.symbol}: <span style={{ color: '#2962FF', fontWeight: 'bold', fontSize: '16px' }}>
                  ${parseFloat(currentPrice.price).toFixed(2)}
                </span>
              </div>
            )}
          </div>
        </div>
      </header>
      
      {/* Main Content */}
      <main style={{ 
        flex: 1, 
        display: 'flex',
        overflow: 'hidden'
      }}>
        {/* Left Panel - Chart */}
        <div style={{ 
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          padding: '15px',
          overflow: 'auto'
        }}>
          <TradingChart />
        </div>

        {/* Right Panel - Controls */}
        <div style={{
          width: '350px',
          padding: '15px',
          background: '#1a1a1a',
          borderLeft: '1px solid #2b2b2b',
          display: 'flex',
          flexDirection: 'column',
          gap: '15px',
          overflowY: 'auto',
          flexShrink: 0
        }}>
          <BalanceDisplay />
          <OrderPanel />
        </div>
      </main>
    </div>
  )
}

export default App
