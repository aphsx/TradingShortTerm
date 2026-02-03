// src/pages/DashboardPage.tsx
import { MiniChart } from '../components/Dashboard/MiniChart'
import { TrendingUp, Wallet, Activity } from 'lucide-react'

interface DashboardPageProps {
  onNavigate: (page: string, symbol?: string) => void
}

export const DashboardPage = ({ onNavigate }: DashboardPageProps): React.ReactElement => {
  return (
    <div className="p-4 space-y-4 bg-[#0B0E11] min-h-screen text-[#EAECEF]">
      {/* --- SECTION 1: COMPACT STATUS BAR --- */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Total Balance */}
        <div className="bg-[#1E2329] p-5 rounded-sm border-l-4 border-[#FCD535]">
          {' '}
          {/* สีเหลือง Binance */}
          <div className="flex justify-between items-start mb-2">
            <p className="text-[#848E9C] text-xs font-medium uppercase tracking-wider">
              Total Equity (USDT)
            </p>
            <Wallet className="w-4 h-4 text-[#848E9C]" />
          </div>
          <h3 className="text-2xl font-mono font-bold text-[#EAECEF]">
            10,450<span className="text-[#848E9C] text-lg">.23</span>
          </h3>
          <p className="text-[#0ECB81] text-xs font-mono mt-1 flex items-center gap-1">
            ▲ $450.00 (Today)
          </p>
        </div>

        {/* PnL Analysis */}
        <div className="bg-[#1E2329] p-5 rounded-sm">
          <p className="text-[#848E9C] text-xs font-medium uppercase tracking-wider mb-2">
            Unrealized PnL
          </p>
          <h3 className="text-2xl font-mono font-bold text-[#0ECB81]">
            +1,204<span className="text-sm">.00</span>
          </h3>
          <p className="text-[#848E9C] text-xs mt-1">
            ROE: <span className="text-[#0ECB81]">12.5%</span>
          </p>
        </div>

        {/* Margin Usage */}
        <div className="bg-[#1E2329] p-5 rounded-sm">
          <p className="text-[#848E9C] text-xs font-medium uppercase tracking-wider mb-2">
            Margin Ratio
          </p>
          <div className="flex items-end gap-2">
            <h3 className="text-2xl font-mono font-bold text-[#FCD535]">
              12.4<span className="text-sm">%</span>
            </h3>
            <span className="text-xs text-[#848E9C] mb-1">Low Risk</span>
          </div>
          {/* Progress Bar */}
          <div className="w-full bg-[#2B3139] h-1.5 mt-3 rounded-full overflow-hidden">
            <div className="bg-[#FCD535] h-full w-[12%]"></div>
          </div>
        </div>

        {/* Active Position Count */}
        <div className="bg-[#1E2329] p-5 rounded-sm flex flex-col justify-between">
          <p className="text-[#848E9C] text-xs font-medium uppercase tracking-wider">
            Open Positions
          </p>
          <div className="flex justify-between items-end">
            <h3 className="text-3xl font-mono font-bold text-[#EAECEF]">4</h3>
            <button className="text-xs text-[#3B82F6] hover:text-white transition">View All</button>
          </div>
        </div>
      </div>

      {/* --- SECTION 2: MARKET MONITOR (MINI CHARTS) --- */}
      <div>
        <div className="flex justify-between items-center mb-2 px-1">
          <h2 className="text-sm font-bold text-[#EAECEF] flex items-center gap-2 uppercase tracking-wide">
            <Activity className="w-4 h-4 text-[#FCD535]" /> Hot Futures
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <MiniChart symbol="BTCUSDT" onChartClick={() => onNavigate('trade', 'BTCUSDT')} />
          </div>
          <div>
            <MiniChart symbol="ETHUSDT" onChartClick={() => onNavigate('trade', 'ETHUSDT')} />
          </div>
          <div>
            <MiniChart symbol="SOLUSDT" onChartClick={() => onNavigate('trade', 'SOLUSDT')} />
          </div>
        </div>
      </div>

      {/* --- SECTION 3: MARKET LIST (TABLE STYLE) --- */}
      <div className="bg-[#1E2329] rounded-sm overflow-hidden">
        <div className="p-4 border-b border-[#2B3139] flex justify-between items-center">
          <h2 className="text-sm font-bold text-[#EAECEF] flex items-center gap-2 uppercase">
            <TrendingUp className="w-4 h-4 text-[#0ECB81]" /> Market Overview
          </h2>
          <input
            type="text"
            placeholder="Search Coin..."
            className="bg-[#0B0E11] text-xs text-white px-3 py-1.5 rounded-sm border border-[#2B3139] focus:border-[#FCD535] outline-none"
          />
        </div>

        <table className="w-full text-left text-sm">
          <thead className="text-[#848E9C] text-xs bg-[#161A1E]">
            <tr>
              <th className="px-4 py-3 font-medium">Pair</th>
              <th className="px-4 py-3 font-medium text-right">Price</th>
              <th className="px-4 py-3 font-medium text-right">24h Change</th>
              <th className="px-4 py-3 font-medium text-right">24h Volume</th>
              <th className="px-4 py-3 text-center">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2B3139]">
            {/* Row Item */}
            <tr
              className="hover:bg-[#2B3139] transition cursor-pointer group"
              onClick={() => onNavigate('trade', 'BNBUSDT')}
            >
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-[#EAECEF]">BNBUSDT</span>
                  <span className="text-[10px] bg-[#2B3139] text-[#FCD535] px-1 rounded">10x</span>
                </div>
              </td>
              <td className="px-4 py-3 text-right font-mono text-[#EAECEF] group-hover:text-white">
                320.50
              </td>
              <td className="px-4 py-3 text-right font-mono text-[#0ECB81]">+5.20%</td>
              <td className="px-4 py-3 text-right font-mono text-[#848E9C]">1.2B</td>
              <td className="px-4 py-3 text-center">
                <button className="text-[#FCD535] text-xs hover:underline">Trade</button>
              </td>
            </tr>

            {/* Row Item (Negative) */}
            <tr
              className="hover:bg-[#2B3139] transition cursor-pointer group"
              onClick={() => onNavigate('trade', 'DOGEUSDT')}
            >
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-[#EAECEF]">DOGEUSDT</span>
                  <span className="text-[10px] bg-[#2B3139] text-[#FCD535] px-1 rounded">20x</span>
                </div>
              </td>
              <td className="px-4 py-3 text-right font-mono text-[#EAECEF] group-hover:text-white">
                0.08500
              </td>
              <td className="px-4 py-3 text-right font-mono text-[#F6465D]">-2.10%</td>
              <td className="px-4 py-3 text-right font-mono text-[#848E9C]">800M</td>
              <td className="px-4 py-3 text-center">
                <button className="text-[#FCD535] text-xs hover:underline">Trade</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
