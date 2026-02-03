// src/components/Dashboard/MiniChart.tsx
import { useEffect, useRef, useState, useCallback } from 'react'
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickSeries,
  AreaSeries,
  HistogramSeries,
  Time,
  LineType,
  CrosshairMode,
  ColorType
} from 'lightweight-charts'
import { TrendingUp, TrendingDown } from 'lucide-react'

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

interface AreaData {
  time: Time
  value: number
}

interface MiniChartProps {
  symbol: string
  variant?: 'full' | 'minimal'
  height?: number
  onChartClick?: () => void
}

export const MiniChart = ({
  symbol,
  variant = 'minimal',
  height = 250,
  onChartClick
}: MiniChartProps): React.ReactElement => {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const areaSeriesRef = useRef<ISeriesApi<'Area'> | null>(null)

  const [candlestickData, setCandlestickData] = useState<CandlestickData[]>([])
  const [, setVolumeData] = useState<VolumeData[]>([])
  const [areaData, setAreaData] = useState<AreaData[]>([])
  const [currentPrice, setCurrentPrice] = useState<number>(0)
  const [priceChange, setPriceChange] = useState<number>(0)
  const [priceChangePercent, setPriceChangePercent] = useState<number>(0)
  const [timeframe, setTimeframe] = useState<string>('1h')
  const [chartType, setChartType] = useState<'candlestick' | 'area'>('candlestick')
  const [isChartReady, setIsChartReady] = useState(false)

  // Generate comprehensive sample data (same as main chart)
  const generateSampleData = useCallback(() => {
    const candlesticks: CandlestickData[] = []
    const volumes: VolumeData[] = []
    const areas: AreaData[] = []

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

    // Chart configuration for minimal variant
    const baseChartOptions = {
      layout: {
        textColor: 'transparent',
        background: {
          type: ColorType.Solid,
          color: 'transparent'
        }
      },
      grid: {
        vertLines: {
          color: 'transparent',
          visible: false
        },
        horzLines: {
          color: 'transparent',
          visible: false
        }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: 'transparent',
          visible: false
        },
        horzLine: {
          color: 'transparent',
          visible: false
        }
      },
      rightPriceScale: {
        borderColor: 'transparent',
        textColor: 'transparent',
        visible: false
      },
      leftPriceScale: {
        borderColor: 'transparent',
        textColor: 'transparent',
        visible: false
      },
      timeScale: {
        borderColor: 'transparent',
        textColor: 'transparent',
        visible: false,
        timeVisible: false,
        secondsVisible: false,
        borderVisible: false
      },
      handleScroll: true,
      handleScale: true,
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
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

    // Add minimal volume series
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
      const { width, height: newHeight } = entries[0].contentRect
      chart.applyOptions({ width, height: newHeight })
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

  const timeframes = ['1m', '5m', '30m', '1h', '2h', '15m']
  const isUp = priceChange >= 0

  return (
    <div
      className="relative w-full bg-[#1a1d1f] border border-gray-800 rounded-lg overflow-hidden flex flex-col"
      style={{ height: `${height}px` }}
    >
      {/* Symbol Name - Outside Chart Container */}
      <div className="relative z-10 p-3 flex justify-between items-center shrink-0 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <h3 className="text-white font-semibold text-sm">{symbol}</h3>
          <span className="text-xs text-gray-400">PERP</span>
        </div>

        {/* Chart Type Toggle */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setChartType('candlestick')}
            className={`px-2 py-1 text-xs rounded transition-colors ${
              chartType === 'candlestick'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
            }`}
          >
            Candle
          </button>
        </div>
      </div>

      {/* Price and Time Frame Section */}
      <div className="relative z-10 p-3 flex flex-col shrink-0">
        {/* Price Section */}
        <div className="mb-3">
          <div className="flex items-baseline gap-2">
            <span className="text-white text-xl font-semibold">
              {currentPrice.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
              })}
            </span>
            <div
              className={`flex items-center gap-1 text-sm ${
                isUp ? 'text-green-500' : 'text-red-500'
              }`}
            >
              {isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
              <span className="font-medium">
                {isUp ? '+' : ''}
                {priceChangePercent.toFixed(2)}%
              </span>
            </div>
          </div>
          <div className="flex items-center gap-4 mt-1 text-xs text-gray-400">
            <span>Vol: 1.2B</span>
            <span>24h: ${Math.abs(priceChange).toFixed(2)}</span>
          </div>
        </div>

        {/* Time Frame Selector */}
        <div className="flex gap-1 mb-3">
          {timeframes.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                timeframe === tf
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Chart Container - Clickable for navigation */}
      <div
        ref={chartContainerRef}
        className="flex-1 w-full min-h-0 cursor-pointer hover:opacity-90 transition-opacity"
        onClick={onChartClick}
      />
    </div>
  )
}
