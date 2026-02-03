// src/App.tsx
import { useState } from 'react';
import { DashboardPage } from './pages/DashboardPage';
import TradingViewChart from './components/TradingViewChart';
import { 
  LayoutDashboard, 
  LineChart, 
  Wallet, 
  History, 
  Settings, 
  LogOut, 
  Bell, 
  Zap,
  Search,
  ChevronRight,
  ChevronLeft
} from 'lucide-react';

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT');

  const handleNavigate = (page: string, symbol: string | null = null) => {
    if (symbol) setSelectedSymbol(symbol);
    setCurrentPage(page);
  };

  const SidebarItem = ({ id, icon: Icon, label }: { id: string; icon: any; label: string }) => (
    <button
      onClick={() => setCurrentPage(id)}
      className={`w-10 h-10 mb-2 rounded-lg flex items-center justify-center transition-all duration-200 group relative
        ${currentPage === id 
          ? 'bg-[#2B3139] text-[#FCD535] shadow-[0_0_10px_rgba(252,213,53,0.15)]' 
          : 'text-[#848E9C] hover:bg-[#2B3139]/50 hover:text-[#EAECEF]'
        }`}
    >
      <Icon className="w-5 h-5" />
      {/* Tooltip */}
      <div className="absolute left-14 bg-[#2B3139] text-[#EAECEF] text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap border border-[#363C45] z-50 pointer-events-none">
        {label}
      </div>
    </button>
  );

  return (
    <div className="flex h-screen bg-[#0B0E11] text-[#EAECEF] font-sans selection:bg-[#FCD535] selection:text-black overflow-hidden">
      
      {/* --- LEFT SIDEBAR --- */}
      <aside className="w-16 bg-[#161A1E] border-r border-[#2B3139] flex flex-col items-center py-4 z-50">
        {/* Logo */}
        <div className="mb-8 text-[#FCD535] p-2 bg-[#2B3139]/30 rounded-lg cursor-pointer" onClick={() => setCurrentPage('dashboard')}>
          <Zap className="w-6 h-6 fill-current" />
        </div>

        {/* Navigation */}
        <nav className="flex-1 flex flex-col items-center w-full px-2">
          <SidebarItem id="dashboard" icon={LayoutDashboard} label="Dashboard" />
          <SidebarItem id="trade" icon={LineChart} label="Trade" />
          <SidebarItem id="market" icon={Search} label="Markets" />
          <SidebarItem id="wallet" icon={Wallet} label="Wallet" />
          <SidebarItem id="history" icon={History} label="History" />
        </nav>

        {/* Bottom Actions */}
        <div className="flex flex-col items-center gap-2 pb-2 w-full px-2">
          <button className="w-10 h-10 rounded-lg flex items-center justify-center text-[#848E9C] hover:text-[#EAECEF] hover:bg-[#2B3139]/50 transition-colors">
            <Settings className="w-5 h-5" />
          </button>
          <button className="w-10 h-10 rounded-lg flex items-center justify-center text-[#F6465D] hover:bg-[#F6465D]/10 transition-colors">
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </aside>

      {/* --- MAIN CONTENT WRAPPER --- */}
      <div className="flex-1 flex flex-col min-w-0">
        
        {/* --- TOP HEADER --- */}
        <header className="h-12 bg-[#161A1E] border-b border-[#2B3139] flex items-center justify-between px-6 z-40 shadow-sm">
          {/* Left: Breadcrumb / Ticker Tape */}
          <div className="flex items-center gap-6 overflow-hidden">
             <div className="flex items-center gap-2 text-sm font-medium text-[#848E9C]">
                <span className="uppercase tracking-wider">{currentPage}</span>
                {currentPage === 'trade' && (
                  <>
                    <ChevronRight className="w-4 h-4" />
                    <span className="text-[#EAECEF] font-bold">{selectedSymbol}</span>
                  </>
                )}
             </div>

             {/* Mini Ticker Tape (Desktop only) */}
             <div className="hidden lg:flex items-center gap-6 pl-6 border-l border-[#2B3139] opacity-80">
                <div className="flex items-center gap-2 text-xs font-mono">
                  <span className="text-[#EAECEF] font-bold">BTC</span>
                  <span className="text-[#0ECB81]">43,250.00</span>
                </div>
                <div className="flex items-center gap-2 text-xs font-mono">
                  <span className="text-[#EAECEF] font-bold">ETH</span>
                  <span className="text-[#F6465D]">2,250.00</span>
                </div>
                <div className="flex items-center gap-2 text-xs font-mono">
                  <span className="text-[#EAECEF] font-bold">SOL</span>
                  <span className="text-[#0ECB81]">112.50</span>
                </div>
             </div>
          </div>

          {/* Right: Actions */}
          <div className="flex items-center gap-4">
            <div className="relative cursor-pointer group">
              <Bell className="w-4 h-4 text-[#848E9C] group-hover:text-white transition-colors" />
              <span className="absolute -top-1 -right-1 w-2 h-2 bg-[#F6465D] rounded-full border border-[#161A1E]"></span>
            </div>
            
            <div className="h-4 w-px bg-[#2B3139]"></div>

            <div className="flex items-center gap-2 px-3 py-1.5 bg-[#2B3139]/50 rounded-full border border-[#2B3139]">
              <div className="w-2 h-2 rounded-full bg-[#0ECB81] shadow-[0_0_8px_#0ECB81]"></div>
              <span className="text-[10px] font-bold text-[#0ECB81] uppercase tracking-wide">Testnet</span>
            </div>

            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-[#FCD535] to-[#F7931A] p-[1px] cursor-pointer">
               <div className="w-full h-full rounded-full bg-[#1E2329] flex items-center justify-center text-[#FCD535] font-bold text-xs">
                 U
               </div>
            </div>
          </div>
        </header>

        {/* --- PAGE CONTENT --- */}
        <main className="flex-1 overflow-y-auto overflow-x-hidden relative bg-[#0B0E11] scrollbar-hide">
          {currentPage === 'trade' && (
            <div className="h-full flex flex-col">
              {/* Specialized Trade Header */}
              <div className="h-12 border-b border-[#2B3139] flex items-center px-4 bg-[#161A1E] gap-4 shrink-0">
                <button onClick={() => setCurrentPage('dashboard')} className="p-1 hover:bg-[#2B3139] rounded text-[#848E9C] hover:text-white transition">
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <div>
                   <div className="flex items-baseline gap-2">
                      <h2 className="text-lg font-bold text-[#EAECEF] leading-none">{selectedSymbol}</h2>
                      <span className="text-xs text-[#0ECB81] bg-[#0ECB81]/10 px-1 rounded">+2.45%</span>
                   </div>
                   <p className="text-[10px] text-[#848E9C] font-mono leading-none mt-1">Perpetual Contract</p>
                </div>
                
                <div className="ml-auto flex gap-4 text-sm font-mono">
                   <div>
                      <p className="text-[10px] text-[#848E9C] uppercase">Mark Price</p>
                      <p className="text-[#0ECB81]">32,450.00</p>
                   </div>
                   <div>
                      <p className="text-[10px] text-[#848E9C] uppercase">Index Price</p>
                      <p className="text-[#EAECEF]">32,445.00</p>
                   </div>
                   <div>
                      <p className="text-[10px] text-[#848E9C] uppercase">24h Vol</p>
                      <p className="text-[#EAECEF]">1.2B</p>
                   </div>
                </div>
              </div>

              <div className="flex-1 overflow-hidden flex">
                <main className="flex-1 relative border-r border-[#2B3139]">
                   <TradingViewChart symbol={selectedSymbol} />
                </main>
                <aside className="w-[320px] bg-[#161A1E] border-l border-[#2B3139] flex flex-col">
                   {/* Order Form Placeholder */}
                   <div className="p-4 flex-1">
                      <div className="flex bg-[#0B0E11] p-1 rounded mb-4">
                         <button className="flex-1 py-1.5 text-xs font-bold bg-[#2B3139] text-white rounded shadow-sm">Open</button>
                         <button className="flex-1 py-1.5 text-xs font-bold text-[#848E9C] hover:text-white">Close</button>
                      </div>
                      <h2 className="text-sm font-bold text-[#EAECEF] mb-4">Place Order</h2>
                      {/* Form Controls would go here with #2B3139 backgrounds */}
                      <div className="space-y-3">
                         <div className="bg-[#0B0E11] border border-[#2B3139] rounded p-2 flex justify-between text-xs">
                            <span className="text-[#848E9C]">Price</span>
                            <span className="text-white font-mono">32,450.00</span>
                         </div>
                         <div className="bg-[#0B0E11] border border-[#2B3139] rounded p-2 flex justify-between text-xs">
                            <span className="text-[#848E9C]">Amount (USDT)</span>
                            <span className="text-white font-mono">0.00</span>
                         </div>
                         <button className="w-full py-3 bg-[#0ECB81] hover:bg-[#0ECB81]/90 text-black font-bold text-sm rounded transition mt-4">
                            Buy / Long
                         </button>
                      </div>
                   </div>
                </aside>
              </div>
            </div>
          )}

          {currentPage === 'dashboard' && <DashboardPage onNavigate={handleNavigate} />}
          
          {currentPage === 'market' && (
            <div className="flex flex-col items-center justify-center h-full text-[#848E9C]">
              <Search className="w-12 h-12 mb-4 opacity-20" />
              <p className="text-lg font-medium">Market Explorer</p>
              <p className="text-sm opacity-60">Advanced screening tools coming soon.</p>
            </div>
          )}

          {currentPage === 'wallet' && (
            <div className="flex flex-col items-center justify-center h-full text-[#848E9C]">
              <Wallet className="w-12 h-12 mb-4 opacity-20" />
              <p className="text-lg font-medium">Assets Overview</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;