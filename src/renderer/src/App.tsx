import { AdvancedTradingChart } from './components/AdvancedTradingChart'
import { BalanceDisplay } from './components/BalanceDisplay'
import { OrderPanel } from './components/OrderPanel'
import './assets/main.css'

function App(): React.JSX.Element {

  return (
    <div className="w-screen h-screen flex bg-[#131722] text-slate-100 overflow-hidden">
      {/* Main Content - Full Width Chart */}
      <main className="flex-1 flex overflow-hidden">
        {/* Chart Area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <AdvancedTradingChart />
        </div>

        {/* Right Panel - Trading Controls */}
        <div className="w-96 flex flex-col gap-4 bg-[#1e222d] border-l border-[#2b2b43] p-4 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-900">
          <BalanceDisplay />
          <OrderPanel />
        </div>
      </main>
    </div>
  )
}

export default App
