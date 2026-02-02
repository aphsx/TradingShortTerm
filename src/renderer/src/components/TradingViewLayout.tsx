import { useEffect } from 'react'
import TopBar from './TopBar'
import SymbolSelector from './SymbolSelector'
import ChartToolbar from './ChartToolbar'
import CandlestickChart from './CandlestickChart'
import TradingPanel from './TradingPanel'
import { useTradingStore } from '../store/useTradingStore'

export default function TradingViewLayout() {
  const { loadHistoricalData, connectWebSocket, disconnectWebSocket } = useTradingStore()

  useEffect(() => {
    // Load initial data and connect
    loadHistoricalData()
    connectWebSocket()

    // Cleanup on unmount
    return () => {
      disconnectWebSocket()
    }
  }, [])

  return (
    <div className="h-screen w-full flex flex-col bg-[#131722]">
      {/* Top Bar */}
      <TopBar />

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Symbol Selector */}
        <SymbolSelector />

        {/* Center: Chart Area */}
        <div className="flex-1 flex flex-col">
          <ChartToolbar />
          <div className="flex-1">
            <CandlestickChart />
          </div>
        </div>

        {/* Right: Trading Panel */}
        <TradingPanel />
      </div>
    </div>
  )
}
