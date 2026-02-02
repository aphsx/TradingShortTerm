import { useEffect, useRef, useState } from 'react'
import { createChart, IChartApi, Time, CandlestickData, ISeriesApi } from 'lightweight-charts'
import { useTradingStore } from '../store/trading'
import { apiService, KlineData } from '../services/api'
import { Card } from './ui/card'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { CheckCircle2, AlertCircle, TrendingUp } from 'lucide-react'

const TIMEFRAMES = [
  { label: '1m', value: '1m', display: '1 นาที' },
  { label: '5m', value: '5m', display: '5 นาที' },
  { label: '15m', value: '15m', display: '15 นาที' },
  { label: '1h', value: '1h', display: '1 ชั่วโมง' },
  { label: '4h', value: '4h', display: '4 ชั่วโมง' },
  { label: '1d', value: '1d', display: '1 วัน' }
]

export function TradingChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<any>(null)
  const hasSeriesCreated = useRef(false)
  
  const [timeframe, setTimeframe] = useState('1m')
  const [isLoading, setIsLoading] = useState(true)
  
  const isConnected = useTradingStore((state) => state.isConnected)
  const currentPrice = useTradingStore((state) => state.currentPrice)

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) {
      console.warn('Chart container not ready')
      return
    }

    // If chart already exists, don't recreate it
    if (chartRef.current && hasSeriesCreated.current) {
      console.log('Chart already created, skipping...')
      return
    }

    try {
      const container = chartContainerRef.current
      
      // Clear any existing chart
      if (chartRef.current) {
        console.log('Removing existing chart...')
        chartRef.current.remove()
        chartRef.current = null
        seriesRef.current = null
        hasSeriesCreated.current = false
      }

      const width = container.clientWidth
      const height = container.clientHeight || 500

      console.log('🚀 Creating chart with dimensions:', { width, height })

      const chart = createChart(container, {
        width: width,
        height: height,
        layout: {
          background: { color: 'rgba(15, 23, 42, 0)' },
          textColor: '#cbd5e1'
        },
        grid: {
          vertLines: { color: '#334155' },
          horzLines: { color: '#334155' }
        },
        crosshair: {
          mode: 1
        },
        rightPriceScale: {
          borderColor: '#334155'
        },
        timeScale: {
          borderColor: '#334155',
          timeVisible: true,
          secondsVisible: false
        }
      })

      if (!chart) {
        console.error('Failed to create chart')
        return
      }

      const candlestickSeries = chart.addSeries('candlestick', {
        upColor: '#16a34a',
        downColor: '#dc2626',
        borderVisible: false,
        wickUpColor: '#16a34a',
        wickDownColor: '#dc2626'
      })

      console.log('✅ Chart and candlestick series created successfully')

      chartRef.current = chart
      seriesRef.current = candlestickSeries
      hasSeriesCreated.current = true

      const handleResize = (): void => {
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
          seriesRef.current = null
          hasSeriesCreated.current = false
        }
      }
    } catch (error) {
      console.error('Error initializing chart:', error)
      return
    }
  }, [])

  // Load klines data when timeframe changes
  useEffect(() => {
    if (!seriesRef.current || !hasSeriesCreated.current) {
      console.log('⏸️ Series not ready yet')
      return
    }

    const loadKlines = async () => {
      try {
        setIsLoading(true)
        console.log(`📊 Loading ${timeframe} klines...`)
        
        const klines = await apiService.getKlines('BTCUSDT', timeframe, 500)
        console.log(`✅ Received ${klines.length} klines from API`)
        
        const candlestickData: CandlestickData[] = klines.map((k: KlineData) => ({
          time: Math.floor(k.openTime / 1000) as Time,
          open: parseFloat(k.open),
          high: parseFloat(k.high),
          low: parseFloat(k.low),
          close: parseFloat(k.close)
        }))

        if (candlestickData.length > 0) {
          seriesRef.current.setData(candlestickData)
          console.log(`✅ Loaded ${candlestickData.length} candlesticks to chart`)
        } else {
          console.warn('⚠️ No candlestick data received')
        }
      } catch (error) {
        console.error('❌ Failed to load klines:', error)
      } finally {
        setIsLoading(false)
        console.log('✅ Loading complete, isLoading set to false')
      }
    }

    loadKlines()
  }, [timeframe])

  // Update with real-time price (convert to candlestick format)
  useEffect(() => {
    if (!seriesRef.current || !currentPrice || isLoading) {
      return
    }

    try {
      const time = Math.floor(currentPrice.timestamp / 1000) as Time
      const price = parseFloat(currentPrice.price)

      if (!isFinite(price)) {
        console.warn('Invalid price value:', currentPrice.price)
        return
      }

      // Update the last candle with new price
      seriesRef.current.update({
        time: time,
        open: price,
        high: price,
        low: price,
        close: price
      })
    } catch (error) {
      console.error('❌ Error updating chart:', error)
    }
  }, [currentPrice, isLoading])

  return (
    <Card className="w-full h-full flex flex-col border-amber-900/30 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-950 overflow-hidden">
      <div className="flex-shrink-0 border-b border-slate-800 bg-slate-900/50 px-4 py-3">
        <div className="flex items-center justify-between gap-6">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              {isConnected ? (
                <>
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                  <Badge className="bg-green-500/20 text-green-300 border-green-500/30">Connected</Badge>
                </>
              ) : (
                <>
                  <AlertCircle className="h-5 w-5 text-red-500" />
                  <Badge className="bg-red-500/20 text-red-300 border-red-500/30">Disconnected</Badge>
                </>
              )}
            </div>
            
            {currentPrice && (
              <>
                <div>
                  <span className="text-xs text-slate-400">Symbol</span>
                  <div className="font-semibold text-white flex items-center gap-1">
                    <TrendingUp className="h-4 w-4 text-amber-400" />
                    {currentPrice.symbol}
                  </div>
                </div>
                <div>
                  <span className="text-xs text-slate-400">Current Price</span>
                  <div className="text-2xl font-bold text-amber-400 font-mono">
                    ${parseFloat(currentPrice.price).toFixed(2)}
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 mr-2">ช่วงเวลา:</span>
            {TIMEFRAMES.map((tf) => (
              <Button
                key={tf.value}
                size="sm"
                variant={timeframe === tf.value ? 'default' : 'outline'}
                onClick={() => setTimeframe(tf.value)}
                className={`h-7 px-3 ${
                  timeframe === tf.value
                    ? 'bg-amber-500 text-slate-900 hover:bg-amber-600'
                    : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                }`}
              >
                {tf.label}
              </Button>
            ))}
          </div>
        </div>
      </div>
      
      <div ref={chartContainerRef} className="flex-1 w-full overflow-hidden relative">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-950/50 z-10">
            <div className="text-amber-400 flex items-center gap-2">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-amber-400"></div>
              <span>กำลังโหลดข้อมูล...</span>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}
