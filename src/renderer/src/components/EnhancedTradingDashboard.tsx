import { useEffect, useState } from 'react'
import MultiAssetTradingPanel from './MultiAssetTradingPanel'
import { priceService } from '../services/priceService'
import { useMultiAssetStore } from '../store/useMultiAssetStore'

export default function EnhancedTradingDashboard() {
  const [isMultiAssetMode, setIsMultiAssetMode] = useState(false)
  const { setBalances } = useMultiAssetStore()

  useEffect(() => {
    if (isMultiAssetMode) {
      // Start price updates when switching to multi-asset mode
      priceService.startPriceUpdates()
      
      // Fetch initial balance
      fetchBalance()
    } else {
      // Stop price updates when switching back to single asset mode
      priceService.stopPriceUpdates()
    }

    // Cleanup on unmount
    return () => {
      priceService.stopPriceUpdates()
    }
  }, [isMultiAssetMode])

  const fetchBalance = async () => {
    try {
      const response = await fetch('http://localhost:8080/api/balance')
      if (response.ok) {
        const data = await response.json()
        setBalances(data.balances || [])
      }
    } catch (error) {
      console.error('Failed to fetch balance:', error)
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Mode Toggle */}
      <div className="bg-[#1E222D] border-b border-[#2B2B43] px-4 py-2">
        <div className="flex items-center justify-between">
          <h2 className="text-white text-sm font-semibold">Trading Dashboard</h2>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">Mode:</span>
            <button
              onClick={() => setIsMultiAssetMode(!isMultiAssetMode)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                isMultiAssetMode
                  ? 'bg-[#2962FF] text-white'
                  : 'bg-[#131722] text-gray-400 hover:text-white'
              }`}
            >
              {isMultiAssetMode ? 'Multi-Asset' : 'Single Asset'}
            </button>
          </div>
        </div>
      </div>

      {/* Trading Panel */}
      <div className="flex-1">
        {isMultiAssetMode ? (
          <MultiAssetTradingPanel />
        ) : (
          <div className="h-full flex items-center justify-center text-gray-500">
            <div className="text-center">
              <p className="text-sm mb-2">Single Asset Mode</p>
              <p className="text-xs">Switch to Multi-Asset mode for enhanced trading</p>
            </div>
          </div>
        )}
      </div>

      {/* Footer Info */}
      <div className="bg-[#1E222D] border-t border-[#2B2B43] px-4 py-2">
        <div className="flex items-center justify-between text-xs text-gray-400">
          <span>
            {isMultiAssetMode 
              ? `✅ Multi-Asset Trading: 10+ cryptocurrencies + Gold` 
              : '📊 Single Asset Trading'
            }
          </span>
          <span>Binance Testnet</span>
        </div>
      </div>
    </div>
  )
}
