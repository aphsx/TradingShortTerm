import { useEffect } from 'react'
import TopBar from './TopBar'
import SymbolSelector from './SymbolSelector'
import ChartToolbar from './ChartToolbar'
import TradingChart from './TradingChart'
import TradingPanel from './TradingPanel'
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
            <TradingChart />
          </div>
        </div>

        {/* Right: Trading Panel */}
        <TradingPanel />
      </div>
    </div>
  )
}
