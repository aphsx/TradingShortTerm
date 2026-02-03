// src/App.tsx
import { useState } from 'react';
import { DashboardPage } from './pages/DashboardPage';
import TradingViewChart from './components/TradingViewChart';
import { ChevronLeft, BarChart2, Settings } from 'lucide-react';

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT');

  const handleNavigate = (page: string, symbol: string | null = null) => {
    if (symbol) setSelectedSymbol(symbol);
    setCurrentPage(page);
  };

  return (
    <div className="bg-[#0B0E11] min-h-screen text-[#EAECEF] font-sans selection:bg-[#FCD535] selection:text-black">
      
      {/* --- PRO HEADER --- */}
      <header className="h-12 bg-[#161A1E] border-b border-[#2B3139] flex items-center justify-between px-4 sticky top-0 z-50">
        <div className="flex items-center gap-6">
          {/* Logo */}
          <div className="flex items-center gap-2 text-[#FCD535] font-bold tracking-wider cursor-pointer" onClick={() => setCurrentPage('dashboard')}>
            <BarChart2 className="w-5 h-5" /> SNIPER<span className="text-white">BOT</span>
          </div>
          
          {/* Nav Links */}
          <nav className="hidden md:flex items-center gap-4 text-xs font-bold text-[#848E9C]">
            <button 
              onClick={() => setCurrentPage('dashboard')}
              className={`hover:text-[#FCD535] transition ${currentPage === 'dashboard' ? 'text-[#FCD535]' : ''}`}
            >
              DASHBOARD
            </button>
            <button 
              onClick={() => setCurrentPage('market')}
              className={`hover:text-[#FCD535] transition ${currentPage === 'market' ? 'text-[#FCD535]' : ''}`}
            >
              MARKETS
            </button>
            <button className="hover:text-[#FCD535] transition">WALLET</button>
          </nav>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-4">
           {/* Connection Status Indicator */}
           <div className="flex items-center gap-1.5 bg-[#2B3139] px-2 py-1 rounded text-[10px] text-[#0ECB81] border border-[#0ECB81]/20">
             <div className="w-1.5 h-1.5 rounded-full bg-[#0ECB81] animate-pulse"></div>
             Testnet Connected
           </div>
           <Settings className="w-4 h-4 text-[#848E9C] hover:text-white cursor-pointer" />
           <div className="w-7 h-7 bg-[#2B3139] rounded-full flex items-center justify-center text-[#FCD535] font-bold text-xs border border-[#2B3139]">
             U
           </div>
        </div>
      </header>

      {/* --- CONTENT AREA --- */}
      <div className="relative">
        {currentPage === 'trade' && (
          <div className="h-[calc(100vh-48px)] flex flex-col">
            {/* Sub-header for Trade Page */}
            <div className="h-10 border-b border-[#2B3139] flex items-center px-4 bg-[#161A1E] gap-4">
              <button onClick={() => setCurrentPage('dashboard')} className="text-[#848E9C] hover:text-white">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="font-bold text-[#EAECEF]">{selectedSymbol}</span>
              <span className="text-[#0ECB81] text-xs font-mono">32,450.00</span>
              <span className="px-1.5 py-0.5 bg-[#2B3139] text-[10px] text-[#FCD535] rounded">PERP</span>
            </div>

            <div className="flex-1 overflow-hidden flex">
              <main className="flex-1 relative border-r border-[#2B3139]">
                 <TradingViewChart symbol={selectedSymbol} />
              </main>
              <aside className="w-[320px] bg-[#161A1E] border-l border-[#2B3139]">
                 {/* Order Form Placeholder */}
                 <div className="p-4">
                    <h2 className="text-sm font-bold text-[#EAECEF] mb-4">Place Order</h2>
                    {/* Form Controls would go here with #2B3139 backgrounds */}
                 </div>
              </aside>
            </div>
          </div>
        )}

        {currentPage === 'dashboard' && <DashboardPage onNavigate={handleNavigate} />}
        
        {currentPage === 'market' && <div className="p-10 text-center text-[#848E9C]">Market Page Placeholder</div>}
      </div>
    </div>
  );
}

export default App;