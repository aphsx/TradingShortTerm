import { useState } from 'react'
import { CandlestickChart } from './CandlestickChart'
import { useMarketStore } from '../store/useMarketStore'
import { Card } from './ui/card'
import { Button } from './ui/button'
import { Activity, AlertCircle, TrendingUp } from 'lucide-react'

const TIMEFRAMES = [
  { label: '1m', value: '1m' },
  { label: '3m', value: '3m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '30m', value: '30m' },
  { label: '1H', value: '1h' },
  { label: '2H', value: '2h' },
  { label: '4H', value: '4h' },
  { label: '1D', value: '1d' }
]

const POPULAR_SYMBOLS = [
  { symbol: 'BTCUSDT', name: 'BTC/USDT' },
  { symbol: 'ETHUSDT', name: 'ETH/USDT' },
  { symbol: 'BNBUSDT', name: 'BNB/USDT' },
  { symbol: 'SOLUSDT', name: 'SOL/USDT' },
  { symbol: 'ADAUSDT', name: 'ADA/USDT' },
  { symbol: 'XRPUSDT', name: 'XRP/USDT' }
]

export function AdvancedTradingChart() {
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState('1m')

  const { isConnected, latestCandle } = useMarketStore()

  // Calculate 24h stats from latest candle
  const currentPrice = latestCandle?.close ?? 0
  const priceChange = 0 // You can calculate this from historical data
  const priceChangePercent = 0

  return (
    <Card className="w-full h-full flex flex-col border-slate-800 bg-[#131722] overflow-hidden shadow-2xl">
      {/* Top Bar - TradingView Style */}
      <div className="flex-shrink-0 border-b border-[#2b2b43] bg-[#1e222d] px-4 py-2">
        <div className="flex items-center justify-between gap-4">
          {/* Left side - Symbol and Stats */}
          <div className="flex items-center gap-6">
            {/* Symbol Selector */}
            <div className="flex items-center gap-2">
              <select
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                className="bg-transparent text-white font-bold text-lg border-none outline-none cursor-pointer hover:bg-[#2a2e39] px-2 py-1 rounded"
              >
                {POPULAR_SYMBOLS.map((s) => (
                  <option key={s.symbol} value={s.symbol} className="bg-[#1e222d]">
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Current Price and Change */}
            {latestCandle && latestCandle.symbol === selectedSymbol && (
              <div className="flex items-center gap-4">
                <div>
                  <div className="text-2xl font-bold text-white tabular-nums">
                    {currentPrice.toFixed(2)}
                  </div>
                  <div
                    className={`text-sm font-medium ${
                      priceChange >= 0 ? 'text-[#089981]' : 'text-[#f23645]'
                    }`}
                  >
                    {priceChange >= 0 ? '+' : ''}
                    {priceChange.toFixed(2)} ({priceChangePercent >= 0 ? '+' : ''}
                    {priceChangePercent.toFixed(2)}%)
                  </div>
                </div>

                {/* 24h Stats */}
                <div className="flex items-center gap-4 text-xs">
                  <div>
                    <div className="text-[#758696]">24h High</div>
                    <div className="text-white font-medium tabular-nums">
                      {latestCandle.high.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[#758696]">24h Low</div>
                    <div className="text-white font-medium tabular-nums">
                      {latestCandle.low.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[#758696]">24h Volume</div>
                    <div className="text-white font-medium tabular-nums">
                      {latestCandle.volume.toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Connection Status */}
            <div className="flex items-center gap-2 ml-4">
              {isConnected ? (
                <>
                  <Activity className="h-4 w-4 text-[#089981] animate-pulse" />
                  <span className="text-xs text-[#758696]">Live</span>
                </>
              ) : (
                <>
                  <AlertCircle className="h-4 w-4 text-[#f23645]" />
                  <span className="text-xs text-[#758696]">Disconnected</span>
                </>
              )}
            </div>
          </div>

          {/* Right side - Timeframe Selector */}
          <div className="flex items-center gap-1">
            {TIMEFRAMES.map((tf) => (
              <Button
                key={tf.value}
                size="sm"
                variant="ghost"
                onClick={() => setTimeframe(tf.value)}
                className={`h-7 px-3 text-xs font-medium transition-colors ${
                  timeframe === tf.value
                    ? 'bg-[#2962FF] text-white hover:bg-[#1E53E5]'
                    : 'text-[#758696] hover:bg-[#2a2e39] hover:text-white'
                }`}
              >
                {tf.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart Container */}
      <div className="flex-1 w-full overflow-hidden relative">
        <CandlestickChart 
          symbol={selectedSymbol} 
          interval={timeframe} 
          className="w-full h-full"
        />
      </div>

      {/* Bottom Info Bar - TradingView Style */}
      <div className="flex-shrink-0 border-t border-[#2b2b43] bg-[#1e222d] px-4 py-2">
        <div className="flex items-center justify-between text-xs text-[#758696]">
          <div className="flex items-center gap-4">
            <span>Powered by Binance Market Data</span>
            <span>•</span>
            <span>Lightweight Charts by TradingView</span>
          </div>
          <div className="flex items-center gap-2">
            <TrendingUp className="h-3 w-3" />
            <span>Real-time updates</span>
          </div>
        </div>
      </div>
    </Card>
  )
}
