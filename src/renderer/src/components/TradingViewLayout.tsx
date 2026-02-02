import { useEffect } from 'react'
import TopBar from './TopBar'
import WatchlistPanel from './WatchlistPanel'
import CandlestickChart from './CandlestickChart'
import TradingPanel from './TradingPanel'
import BottomPanel from './BottomPanel'
import { useTradingStore } from '../store/useTradingStore'

export default function TradingViewLayout() {
  const { connectWebSocket, disconnectWebSocket } = useTradingStore()

  useEffect(() => {
    connectWebSocket()

    return () => {
      disconnectWebSocket()
    }
  }, [])

  return (
    <div className="h-screen w-full flex flex-col bg-[#131722] overflow-hidden">
      {/* Top Bar */}
      <TopBar />

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Watchlist */}
        <WatchlistPanel />

        {/* Center: Chart Area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Chart */}
          <div className="flex-1 overflow-hidden">
            <CandlestickChart />
          </div>

          {/* Bottom Panel */}
          <BottomPanel />
        </div>

        {/* Right: Trading Panel */}
        <TradingPanel />
      </div>
    </div>
  )
}
