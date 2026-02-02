import { useEffect, useState } from 'react'
import TopBar from './TopBar'
import WatchlistPanel from './WatchlistPanel'
import CandlestickChart from './CandlestickChart'
import TradingPanel from './TradingPanel'
import BottomPanel from './BottomPanel'
import MarketOverview from './MarketOverview'
import { useTradingStore } from '../store/useTradingStore'
import { BarChart3, TrendingUp } from 'lucide-react'

export default function TradingViewLayout() {
  const { connectWebSocket, connectPriceWebSocket, disconnectWebSocket } = useTradingStore()
  const [currentView, setCurrentView] = useState<'trading' | 'market'>('trading')

  useEffect(() => {
    if (currentView === 'trading') {
      connectWebSocket()
      connectPriceWebSocket()
    }

    return () => {
      disconnectWebSocket()
    }
  }, [currentView])

  return (
    <div className="h-screen w-full flex flex-col bg-[#131722] overflow-hidden">
      {/* Navigation Bar */}
      <div className="bg-[#1E222D] border-b border-[#2B2B43] px-4 py-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCurrentView('trading')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
              currentView === 'trading'
                ? 'bg-[#2962FF] text-white'
                : 'text-gray-400 hover:text-white hover:bg-[#2B2B43]'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span className="text-sm font-medium">Trading</span>
          </button>
          <button
            onClick={() => setCurrentView('market')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
              currentView === 'market'
                ? 'bg-[#2962FF] text-white'
                : 'text-gray-400 hover:text-white hover:bg-[#2B2B43]'
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            <span className="text-sm font-medium">Market Overview</span>
          </button>
        </div>
      </div>

      {/* Content */}
      {currentView === 'trading' ? (
        <>
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
        </>
      ) : (
        <MarketOverview />
      )}
    </div>
  )
}
