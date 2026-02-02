import { useEffect } from 'react'
import { TradingChart } from './components/TradingChart'
import { BalanceDisplay } from './components/BalanceDisplay'
import { OrderPanel } from './components/OrderPanel'
import { wsService } from './services/websocket'
import { useTradingStore } from './store/trading'
import { Badge } from './components/ui/badge'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import './assets/main.css'

function App(): React.JSX.Element {
  const isConnected = useTradingStore((state) => state.isConnected)
  const currentPrice = useTradingStore((state) => state.currentPrice)

  useEffect(() => {
    const timer = setTimeout(() => {
      console.log('Connecting to backend WebSocket...')
      wsService.connect()
    }, 2000)

    return () => {
      clearTimeout(timer)
      wsService.disconnect()
    }
  }, [])

  return (
    <div className="w-screen h-screen flex flex-col bg-slate-950 text-slate-100 overflow-hidden">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-amber-900/30 bg-gradient-to-r from-slate-900 to-slate-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white">
              ⚡ 24HrT Trading Bot
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Real-time Binance Trading Dashboard
            </p>
          </div>
          
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="flex items-center gap-2 mb-2">
                {isConnected ? (
                  <>
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                    <Badge className="bg-green-500/20 text-green-300 border-green-500/30">
                      Connected
                    </Badge>
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-5 w-5 text-red-500" />
                    <Badge className="bg-red-500/20 text-red-300 border-red-500/30">
                      Disconnected
                    </Badge>
                  </>
                )}
              </div>
              
              {currentPrice && (
                <div className="text-sm text-slate-400">
                  {currentPrice.symbol}: {' '}
                  <span className="font-mono text-lg font-bold text-amber-400">
                    ${parseFloat(currentPrice.price).toFixed(2)}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>
      
      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden gap-4 p-4">
        {/* Left Panel - Chart */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <TradingChart />
        </div>

        {/* Right Panel - Controls */}
        <div className="w-96 flex flex-col gap-4 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-900">
          <BalanceDisplay />
          <OrderPanel />
        </div>
      </main>
    </div>
  )
}

export default App
