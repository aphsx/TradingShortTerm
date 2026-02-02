import { useTradingStore } from '../store/useTradingStore'
import { formatPrice, formatPercent } from '../lib/utils'

export default function TopBar() {
  const { symbol, ticker } = useTradingStore()

  return (
    <div className="h-14 bg-[#1e222d] border-b border-[#2b2b43] flex items-center px-4 space-x-6">
      {/* Symbol */}
      <div className="flex items-center space-x-2">
        <h1 className="text-xl font-bold text-white">{symbol}</h1>
        <span className="text-xs text-gray-400">Binance</span>
      </div>

      {/* Price Info */}
      {ticker && (
        <>
          <div className="flex flex-col">
            <span className="text-xs text-gray-400">Last Price</span>
            <span className="text-lg font-semibold text-white">
              {formatPrice(ticker.price)}
            </span>
          </div>

          <div className="flex flex-col">
            <span className="text-xs text-gray-400">24h Change</span>
            <span
              className={`text-sm font-medium ${
                ticker.priceChangePercent >= 0 ? 'text-green-500' : 'text-red-500'
              }`}
            >
              {formatPercent(ticker.priceChangePercent)}
            </span>
          </div>

          <div className="flex flex-col">
            <span className="text-xs text-gray-400">24h High</span>
            <span className="text-sm text-white">{formatPrice(ticker.high24h)}</span>
          </div>

          <div className="flex flex-col">
            <span className="text-xs text-gray-400">24h Low</span>
            <span className="text-sm text-white">{formatPrice(ticker.low24h)}</span>
          </div>

          <div className="flex flex-col">
            <span className="text-xs text-gray-400">24h Volume</span>
            <span className="text-sm text-white">
              {ticker.volume24h.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          </div>
        </>
      )}
    </div>
  )
}
