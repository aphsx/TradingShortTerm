import { useEffect } from 'react'
import { TradingChart } from './components/TradingChart'
import { wsService } from './services/websocket'
import './assets/main.css'

function App(): React.JSX.Element {
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
      padding: 0
    }}>
      <header style={{
        padding: '15px 20px',
        background: '#252525',
        borderBottom: '2px solid #2962FF'
      }}>
        <h1 style={{ margin: 0, fontSize: '24px' }}>
          ⚡ 24HrT Trading Bot
        </h1>
        <p style={{ margin: '5px 0 0 0', color: '#888', fontSize: '14px' }}>
          Real-time Binance Trading Dashboard
        </p>
      </header>
      
      <main style={{ flex: 1, overflow: 'hidden' }}>
        <TradingChart />
      </main>
    </div>
  )
}

export default App
