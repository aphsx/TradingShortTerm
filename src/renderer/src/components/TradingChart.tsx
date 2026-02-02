import { useEffect, useRef, useState, useCallback } from 'react'
import { 
  createChart, 
  IChartApi, 
  CandlestickData,
  ColorType,
  ISeriesApi,
  UTCTimestamp,
  HistogramData,
  CandlestickSeries,
  HistogramSeries
} from 'lightweight-charts'
import { useTradingStore } from '../store/trading'
import { apiService, KlineData } from '../services/api'
import { wsService } from '../services/websocket'
import { Card } from './ui/card'
import { Button } from './ui/button'
import { AlertCircle, TrendingUp, Activity } from 'lucide-react'

const TIMEFRAMES = [
  { label: '1m', value: '1m', minutes: 1 },
  { label: '3m', value: '3m', minutes: 3 },
  { label: '5m', value: '5m', minutes: 5 },
  { label: '15m', value: '15m', minutes: 15 },
  { label: '30m', value: '30m', minutes: 30 },
  { label: '1H', value: '1h', minutes: 60 },
  { label: '2H', value: '2h', minutes: 120 },
  { label: '4H', value: '4h', minutes: 240 },
  { label: '1D', value: '1d', minutes: 1440 },
]

const POPULAR_SYMBOLS = [
  { symbol: 'BTCUSDT', name: 'BTC/USDT' },
  { symbol: 'ETHUSDT', name: 'ETH/USDT' },
  { symbol: 'BNBUSDT', name: 'BNB/USDT' },
  { symbol: 'SOLUSDT', name: 'SOL/USDT' },
  { symbol: 'ADAUSDT', name: 'ADA/USDT' },
  { symbol: 'XRPUSDT', name: 'XRP/USDT' },
]

export function TradingChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const lastUpdateRef = useRef<{ time: number; price: number } | null>(null)
  
  const [selectedSymbol, setSelectedSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState('15m')
  const [isLoading, setIsLoading] = useState(true)
  const [priceChange, setPriceChange] = useState<{ value: number; percent: number }>({ value: 0, percent: 0 })
  const [high24h, setHigh24h] = useState<number>(0)
  const [low24h, setLow24h] = useState<number>(0)
  const [volume24h, setVolume24h] = useState<string>('0')
  
  const isConnected = useTradingStore((state) => state.isConnected)
  const currentPrice = useTradingStore((state) => state.currentPrice)

  // Initialize chart with TradingView-like styling
  useEffect(() => {
    if (!chartContainerRef.current) return

    const container = chartContainerRef.current
    const width = container.clientWidth
    const height = container.clientHeight || 600

    // Clear existing chart
    if (chartRef.current) {
      chartRef.current.remove()
      chartRef.current = null
      candlestickSeriesRef.current = null
      volumeSeriesRef.current = null
    }

    console.log('📊 Creating TradingView-style chart...')

    // Create chart with professional TradingView styling
    const chart = createChart(container, {
      width: width,
      height: height,
      layout: {
        background: { type: ColorType.Solid, color: '#131722' },
        textColor: '#d1d4dc',
        fontSize: 12,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
      },
      grid: {
        vertLines: { 
          color: '#1e222d',
          style: 1,
          visible: true 
        },
        horzLines: { 
          color: '#1e222d',
          style: 1,
          visible: true 
        }
      },
      crosshair: {
        mode: 1,
        vertLine: {
          width: 1,
          color: '#758696',
          style: 3,
          labelBackgroundColor: '#2962FF'
        },
        horzLine: {
          width: 1,
          color: '#758696',
          style: 3,
          labelBackgroundColor: '#2962FF'
        }
      },
      rightPriceScale: {
        borderColor: '#2b2b43',
        visible: true,
        scaleMargins: {
          top: 0.1,
          bottom: 0.2
        }
      },
      timeScale: {
        borderColor: '#2b2b43',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12,
        barSpacing: 6,
        minBarSpacing: 3
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true
      }
    })

    // Add candlestick series with TradingView colors
    const candlestickSeriesInstance = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      priceFormat: {
        type: 'price',
        precision: 2,
        minMove: 0.01
      }
    })

    // Add volume histogram series
    const volumeSeriesInstance = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: {
        type: 'volume'
      },
      priceScaleId: ''
    })

    // Configure volume series scale margins
    volumeSeriesInstance.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0
      }
    })

    chartRef.current = chart
    candlestickSeriesRef.current = candlestickSeriesInstance
    volumeSeriesRef.current = volumeSeriesInstance

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth
        })
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
      }
    }
  }, [])

  // Load klines data when symbol or timeframe changes
  const loadKlines = useCallback(async () => {
    if (!candlestickSeriesRef.current || !volumeSeriesRef.current) {
      console.log('Series not ready')
      return
    }

    try {
      setIsLoading(true)
      console.log(`📊 Loading ${selectedSymbol} ${timeframe} klines...`)
      
      const klines = await apiService.getKlines(selectedSymbol, timeframe, 500)
      
      if (!klines || klines.length === 0) {
        console.warn('No klines data received')
        setIsLoading(false)
        return
      }

      // Process candlestick data
      const candlestickData: CandlestickData[] = []
      const volumeData: HistogramData[] = []
      let high = 0
      let low = Infinity
      let totalVolume = 0
      
      klines.forEach((k: KlineData) => {
        const time = Math.floor(k.openTime / 1000) as UTCTimestamp
        const open = parseFloat(k.open)
        const high_price = parseFloat(k.high)
        const low_price = parseFloat(k.low)
        const close = parseFloat(k.close)
        const volume = parseFloat(k.volume)

        candlestickData.push({
          time,
          open,
          high: high_price,
          low: low_price,
          close
        })

        volumeData.push({
          time,
          value: volume,
          color: close >= open ? '#26a69a80' : '#ef535080'
        })

        // Track 24h stats
        if (high_price > high) high = high_price
        if (low_price < low) low = low_price
        totalVolume += volume
      })

      // Calculate price change
      if (candlestickData.length >= 2) {
        const firstPrice = candlestickData[0].close
        const lastPrice = candlestickData[candlestickData.length - 1].close
        const change = lastPrice - firstPrice
        const changePercent = (change / firstPrice) * 100
        setPriceChange({ value: change, percent: changePercent })
      }

      setHigh24h(high)
      setLow24h(low)
      setVolume24h(totalVolume.toFixed(2))

      // Update chart
      candlestickSeriesRef.current.setData(candlestickData)
      volumeSeriesRef.current.setData(volumeData)
      
      // Auto-fit content
      chartRef.current?.timeScale().fitContent()

      console.log(`✅ Loaded ${candlestickData.length} candles`)
      setIsLoading(false)
    } catch (error) {
      console.error('Failed to load klines:', error)
      setIsLoading(false)
    }
  }, [selectedSymbol, timeframe])

  useEffect(() => {
    if (candlestickSeriesRef.current && volumeSeriesRef.current) {
      loadKlines()
    }
  }, [loadKlines])

  // Connect WebSocket when symbol changes
  useEffect(() => {
    console.log('Connecting WebSocket for symbol:', selectedSymbol)
    wsService.connect(selectedSymbol)

    return () => {
      // Don't disconnect on cleanup - let it reconnect on symbol change
    }
  }, [selectedSymbol])

  // Update with real-time price from WebSocket
  useEffect(() => {
    if (!candlestickSeriesRef.current || !currentPrice || isLoading) {
      return
    }

    // Only update if price is for the selected symbol
    if (currentPrice.symbol !== selectedSymbol) {
      return
    }

    try {
      const currentTime = Math.floor(currentPrice.timestamp / 1000)
      const price = parseFloat(currentPrice.price)

      if (!isFinite(price)) {
        console.warn('Invalid price value:', currentPrice.price)
        return
      }

      // Get timeframe in seconds
      const timeframeMinutes = TIMEFRAMES.find(tf => tf.value === timeframe)?.minutes || 1
      const timeframeSeconds = timeframeMinutes * 60

      // Round time to current candle period
      const candleTime = Math.floor(currentTime / timeframeSeconds) * timeframeSeconds as UTCTimestamp

      // Check if we should update existing candle or create new one
      if (lastUpdateRef.current && lastUpdateRef.current.time === candleTime) {
        // Update existing candle
        const lastPrice = lastUpdateRef.current.price
        candlestickSeriesRef.current.update({
          time: candleTime,
          open: lastPrice,
          high: Math.max(lastPrice, price),
          low: Math.min(lastPrice, price),
          close: price
        })
      } else {
        // New candle
        candlestickSeriesRef.current.update({
          time: candleTime,
          open: price,
          high: price,
          low: price,
          close: price
        })
      }

      lastUpdateRef.current = { time: candleTime, price }
    } catch (error) {
      console.error('Error updating chart:', error)
    }
  }, [currentPrice, selectedSymbol, timeframe, isLoading])

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
                {POPULAR_SYMBOLS.map(s => (
                  <option key={s.symbol} value={s.symbol} className="bg-[#1e222d]">
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Current Price and Change */}
            {currentPrice && currentPrice.symbol === selectedSymbol && (
              <div className="flex items-center gap-4">
                <div>
                  <div className="text-2xl font-bold text-white tabular-nums">
                    {parseFloat(currentPrice.price).toFixed(2)}
                  </div>
                  <div className={`text-sm font-medium ${priceChange.value >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'}`}>
                    {priceChange.value >= 0 ? '+' : ''}{priceChange.value.toFixed(2)} 
                    ({priceChange.percent >= 0 ? '+' : ''}{priceChange.percent.toFixed(2)}%)
                  </div>
                </div>

                {/* 24h Stats */}
                <div className="flex items-center gap-4 text-xs">
                  <div>
                    <div className="text-[#758696]">24h High</div>
                    <div className="text-white font-medium tabular-nums">{high24h.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-[#758696]">24h Low</div>
                    <div className="text-white font-medium tabular-nums">{low24h.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-[#758696]">24h Volume</div>
                    <div className="text-white font-medium tabular-nums">{parseFloat(volume24h).toLocaleString()}</div>
                  </div>
                </div>
              </div>
            )}

            {/* Connection Status */}
            <div className="flex items-center gap-2 ml-4">
              {isConnected ? (
                <>
                  <Activity className="h-4 w-4 text-[#26a69a] animate-pulse" />
                  <span className="text-xs text-[#758696]">Live</span>
                </>
              ) : (
                <>
                  <AlertCircle className="h-4 w-4 text-[#ef5350]" />
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
      <div ref={chartContainerRef} className="flex-1 w-full overflow-hidden relative bg-[#131722]">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#131722]/90 z-10">
            <div className="flex flex-col items-center gap-3">
              <div className="relative">
                <div className="w-12 h-12 border-4 border-[#2962FF]/20 border-t-[#2962FF] rounded-full animate-spin"></div>
              </div>
              <span className="text-[#758696] text-sm font-medium">Loading chart data...</span>
            </div>
          </div>
        )}
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
