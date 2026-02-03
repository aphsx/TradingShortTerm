import { useEffect, useRef, useState, useCallback } from 'react'
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickSeries,
  AreaSeries,
  HistogramSeries,
  Time,
  ColorType,
  CrosshairMode,
  LineType
} from 'lightweight-charts'
import { TrendingUp, TrendingDown, BarChart3, Settings } from 'lucide-react'

interface CandlestickData {
  time: Time
  open: number
  high: number
  low: number
  close: number
}

interface VolumeData {
  time: Time
  value: number
  color: string
}

interface TradingViewChartProps {
  symbol: string
  variant?: 'full' | 'minimal'
  height?: number
}

const TradingViewChart = ({
  symbol,
  variant = 'full',
  height = 500
}: TradingViewChartProps): React.ReactElement => {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const areaSeriesRef = useRef<ISeriesApi<'Area'> | null>(null)

  const [candlestickData, setCandlestickData] = useState<CandlestickData[]>([])
  const [, setVolumeData] = useState<VolumeData[]>([])
  const [areaData, setAreaData] = useState<{ time: Time; value: number }[]>([])
  const [currentPrice, setCurrentPrice] = useState<number>(0)
  const [priceChange, setPriceChange] = useState<number>(0)
  const [priceChangePercent, setPriceChangePercent] = useState<number>(0)
  const [timeframe, setTimeframe] = useState<string>('1h')
  const [chartType, setChartType] = useState<'candlestick' | 'area'>('candlestick')
  const [isChartReady, setIsChartReady] = useState(false)

  // Generate comprehensive sample data
  const generateSampleData = useCallback(() => {
    const candlesticks: CandlestickData[] = []
    const volumes: VolumeData[] = []
    const areas: { time: Time; value: number }[] = []

    const basePrice = 50000
    const now = Math.floor(Date.now() / 1000)
    let previousClose = basePrice

    for (let i = 200; i >= 0; i--) {
      const time = (now - i * 3600) as Time // 1-hour intervals
      const volatility = previousClose * 0.015

      const open = previousClose + (Math.random() - 0.5) * volatility * 0.3
      const close = open + (Math.random() - 0.5) * volatility
      const high = Math.max(open, close) + Math.random() * volatility * 0.5
      const low = Math.min(open, close) - Math.random() * volatility * 0.5

      const volume = Math.random() * 10000000 + 500000
      const color = close >= open ? '#26a69a' : '#ef5350'

      candlesticks.push({
        time,
        open: Number(open.toFixed(2)),
        high: Number(high.toFixed(2)),
        low: Number(low.toFixed(2)),
        close: Number(close.toFixed(2))
      })

      volumes.push({
        time,
        value: volume,
        color
      })

      areas.push({
        time,
        value: close
      })

      previousClose = close
    }

    return { candlesticks, volumes, areas }
  }, [])

  useEffect(() => {
    if (!chartContainerRef.current) return

    const { candlesticks, volumes, areas } = generateSampleData()
    setCandlestickData(candlesticks)
    setVolumeData(volumes)
    setAreaData(areas)

    // Set current price and change
    const lastCandle = candlesticks[candlesticks.length - 1]
    const firstCandle = candlesticks[0]
    setCurrentPrice(lastCandle.close)
    setPriceChange(lastCandle.close - firstCandle.open)
    setPriceChangePercent(((lastCandle.close - firstCandle.open) / firstCandle.open) * 100)

    // Chart configuration based on variant
    const baseChartOptions = {
      layout: {
        textColor: variant === 'full' ? '#d1d5db' : 'transparent',
        background: {
          type: ColorType.Solid,
          color: variant === 'full' ? '#1f2937' : 'transparent'
        }
      },
      grid: {
        vertLines: {
          color: variant === 'full' ? '#374151' : 'transparent',
          visible: variant === 'full'
        },
        horzLines: {
          color: variant === 'full' ? '#374151' : 'transparent',
          visible: variant === 'full'
        }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: variant === 'full' ? '#6b7280' : 'transparent',
          visible: variant === 'full'
        },
        horzLine: {
          color: variant === 'full' ? '#6b7280' : 'transparent',
          visible: variant === 'full'
        }
      },
      rightPriceScale: {
        borderColor: variant === 'full' ? '#374151' : 'transparent',
        textColor: variant === 'full' ? '#d1d5db' : 'transparent',
        visible: variant === 'full'
      },
      leftPriceScale: {
        borderColor: variant === 'full' ? '#374151' : 'transparent',
        textColor: variant === 'full' ? '#d1d5db' : 'transparent',
        visible: false
      },
      timeScale: {
        borderColor: variant === 'full' ? '#374151' : 'transparent',
        textColor: variant === 'full' ? '#d1d5db' : 'transparent',
        visible: variant === 'full',
        timeVisible: variant === 'full',
        secondsVisible: false,
        borderVisible: variant === 'full'
      },
      handleScroll: variant === 'full',
      handleScale: variant === 'full',
      width: chartContainerRef.current.clientWidth,
      height: variant === 'minimal' ? height : chartContainerRef.current.clientHeight,
      overlayPriceScales: {
        ticksVisible: false,
        borderVisible: false
      }
    }

    const chart = createChart(chartContainerRef.current, baseChartOptions)
    chartRef.current = chart

    // Add main series based on chart type
    if (chartType === 'candlestick') {
      const candlestickSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        priceScaleId: 'right'
      })
      candlestickSeriesRef.current = candlestickSeries
      candlestickSeries.setData(candlesticks)
    } else {
      const areaSeries = chart.addSeries(AreaSeries, {
        lineColor: '#2962FF',
        topColor: 'rgba(41, 98, 255, 0.28)',
        bottomColor: 'rgba(41, 98, 255, 0.01)',
        lineWidth: 2,
        lineType: LineType.Curved,
        priceScaleId: 'right',
        crosshairMarkerVisible: false
      })
      areaSeriesRef.current = areaSeries
      areaSeries.setData(areas)
    }

    // Add volume series for full variant
    if (variant === 'full') {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        color: '#6b7280',
        priceFormat: {
          type: 'volume'
        },
        priceScaleId: 'volume'
      })
      volumeSeriesRef.current = volumeSeries
      volumeSeries.setData(volumes)
    }

    chart.timeScale().fitContent()
    setIsChartReady(true)

    // Handle resize with ResizeObserver
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || !entries[0].target || !chart) return
      const { width, height } = entries[0].contentRect
      chart.applyOptions({
        width,
        height: variant === 'minimal' ? height : height
      })
      chart.timeScale().fitContent()
    })

    resizeObserver.observe(chartContainerRef.current)

    return () => {
      resizeObserver.disconnect()
      if (chart) {
        chart.remove()
      }
    }
  }, [variant, chartType, height, generateSampleData])

  // Update chart when symbol changes
  useEffect(() => {
    if (!isChartReady) return

    const { candlesticks, volumes, areas } = generateSampleData()
    setCandlestickData(candlesticks)
    setVolumeData(volumes)
    setAreaData(areas)

    if (candlestickSeriesRef.current) {
      candlestickSeriesRef.current.setData(candlesticks)
    }
    if (volumeSeriesRef.current) {
      volumeSeriesRef.current.setData(volumes)
    }
    if (areaSeriesRef.current) {
      areaSeriesRef.current.setData(areas)
    }

    const lastCandle = candlesticks[candlesticks.length - 1]
    const firstCandle = candlesticks[0]
    setCurrentPrice(lastCandle.close)
    setPriceChange(lastCandle.close - firstCandle.open)
    setPriceChangePercent(((lastCandle.close - firstCandle.open) / firstCandle.open) * 100)
  }, [symbol, isChartReady, generateSampleData])

  // Update chart type
  useEffect(() => {
    if (!isChartReady || !chartRef.current) return

    // Remove existing series and add new one
    if (chartType === 'candlestick' && areaSeriesRef.current) {
      chartRef.current.removeSeries(areaSeriesRef.current)
      areaSeriesRef.current = null

      const candlestickSeries = chartRef.current.addSeries(CandlestickSeries, {
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        priceScaleId: 'right'
      })
      candlestickSeriesRef.current = candlestickSeries
      candlestickSeries.setData(candlestickData)
    } else if (chartType === 'area' && candlestickSeriesRef.current) {
      chartRef.current.removeSeries(candlestickSeriesRef.current)
      candlestickSeriesRef.current = null

      const areaSeries = chartRef.current.addSeries(AreaSeries, {
        lineColor: '#2962FF',
        topColor: 'rgba(41, 98, 255, 0.28)',
        bottomColor: 'rgba(41, 98, 255, 0.01)',
        lineWidth: 2,
        lineType: LineType.Curved,
        priceScaleId: 'right',
        crosshairMarkerVisible: false
      })
      areaSeriesRef.current = areaSeries
      areaSeries.setData(areaData)
    }
  }, [chartType, isChartReady, candlestickData, areaData])

  const timeframes = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
  const isUp = priceChange >= 0

  if (variant === 'minimal') {
    return (
      <div className="relative w-full bg-transparent">
        {/* Minimal header */}
        <div className="flex justify-between items-center mb-2">
          <div className="flex items-center gap-3">
            <span className="text-white font-bold text-lg">{symbol}</span>
            <div
              className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${
                isUp ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'
              }`}
            >
              {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              <span>
                {isUp ? '+' : ''}
                {priceChangePercent.toFixed(2)}%
              </span>
            </div>
          </div>

          {/* Time frame selector */}
          <div className="flex gap-1">
            {timeframes.slice(0, 4).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  timeframe === tf
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* Chart container */}
        <div ref={chartContainerRef} className="w-full" style={{ height: `${height}px` }} />
      </div>
    )
  }

  return (
    <div className="w-full h-full bg-gray-900 relative">
      {/* Full TradingView-style header */}
      <div className="absolute top-0 left-0 right-0 z-10 bg-gray-800 border-b border-gray-700">
        <div className="flex justify-between items-center p-4">
          {/* Left side - Symbol and price */}
          <div className="flex items-center gap-4">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-white font-bold text-xl">{symbol}</h1>
                <span className="text-xs bg-gray-700 text-gray-300 px-2 py-1 rounded">PERP</span>
              </div>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-white font-mono text-lg">
                  $
                  {currentPrice.toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                  })}
                </span>
                <div
                  className={`flex items-center gap-1 text-sm font-medium ${
                    isUp ? 'text-green-500' : 'text-red-500'
                  }`}
                >
                  {isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                  <span>
                    {isUp ? '+' : ''}
                    {priceChange.toFixed(2)} ({isUp ? '+' : ''}
                    {priceChangePercent.toFixed(2)}%)
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Center - Time frames */}
          <div className="flex gap-1">
            {timeframes.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-3 py-1 text-sm rounded transition-colors ${
                  timeframe === tf
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Right side - Chart type and actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setChartType(chartType === 'candlestick' ? 'area' : 'candlestick')}
              className={`p-2 rounded transition-colors ${
                chartType === 'candlestick'
                  ? 'bg-gray-700 text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
              title="Chart Type"
            >
              <BarChart3 className="w-4 h-4" />
            </button>
            <button
              className="p-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
              title="Settings"
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Chart container */}
      <div ref={chartContainerRef} className="w-full h-full pt-16" />

      {/* TradingView attribution */}
      <div className="absolute bottom-4 right-4 text-xs text-gray-500">
        Powered by TradingView Lightweight Charts
      </div>
    </div>
  )
}

export default TradingViewChart
