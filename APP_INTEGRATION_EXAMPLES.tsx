// Example: How to integrate the new charting module into your App.tsx

// Option 1: Use the simple chart component directly
import { CandlestickChart } from './components/CandlestickChart'

export function App() {
  return (
    <div className="w-full h-screen bg-[#131722] flex flex-col">
      <CandlestickChart 
        symbol="BTCUSDT" 
        interval="1m" 
        className="flex-1"
      />
    </div>
  )
}

// Option 2: Use the advanced chart with controls (RECOMMENDED)
import { AdvancedTradingChart } from './components/AdvancedTradingChart'

export function App() {
  return (
    <div className="w-full h-screen bg-[#131722]">
      <AdvancedTradingChart />
    </div>
  )
}

// Option 3: Side-by-side with order panel
import { AdvancedTradingChart } from './components/AdvancedTradingChart'
import { OrderPanel } from './components/OrderPanel'
import { BalanceDisplay } from './components/BalanceDisplay'

export function App() {
  return (
    <div className="w-full h-screen bg-[#131722] flex">
      {/* Left: Chart (70%) */}
      <div className="flex-1 min-w-0">
        <AdvancedTradingChart />
      </div>
      
      {/* Right: Trading Panel (30%) */}
      <div className="w-96 bg-[#1e222d] border-l border-[#2b2b43] flex flex-col gap-4 p-4">
        <BalanceDisplay />
        <OrderPanel />
      </div>
    </div>
  )
}

// Option 4: Full dashboard layout
import { AdvancedTradingChart } from './components/AdvancedTradingChart'
import { OrderPanel } from './components/OrderPanel'
import { BalanceDisplay } from './components/BalanceDisplay'

export function App() {
  return (
    <div className="w-full h-screen bg-[#131722] flex flex-col">
      {/* Header */}
      <div className="h-16 bg-[#1e222d] border-b border-[#2b2b43] flex items-center px-6">
        <h1 className="text-white text-xl font-bold">24HrT Trading Terminal</h1>
        <div className="ml-auto">
          <BalanceDisplay />
        </div>
      </div>
      
      {/* Main Content */}
      <div className="flex-1 flex min-h-0">
        {/* Chart Area */}
        <div className="flex-1 min-w-0">
          <AdvancedTradingChart />
        </div>
        
        {/* Right Sidebar */}
        <div className="w-96 bg-[#1e222d] border-l border-[#2b2b43] overflow-y-auto">
          <OrderPanel />
        </div>
      </div>
    </div>
  )
}
