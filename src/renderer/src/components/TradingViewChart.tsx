import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickSeries,
  AreaSeries,
  HistogramSeries,
  LineSeries,
  BarSeries,
  Time,
  ColorType,
  CrosshairMode,
  LineType,
  PriceScaleMode,
  UTCTimestamp,
  BusinessDay
} from 'lightweight-charts'
import { TrendingUp, TrendingDown, BarChart3, Settings, Maximize2, Minimize2, RefreshCw } from 'lucide-react'

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
  variant?: 'full' | 'minimal' | 'advanced'
  height?: number
  theme?: 'light' | 'dark'
  autosize?: boolean
  data?: CandlestickData[]
  showVolume?: boolean
  showToolbar?: boolean
}

const TradingViewChart = ({
  symbol,
  variant = 'full',
  height = 500,
  theme = 'dark',
  autosize = true,
  data,
  showVolume = true,
  showToolbar = true
}: TradingViewChartProps): React.ReactElement => {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const areaSeriesRef = useRef<ISeriesApi<'Area'> | null>(null)
  const lineSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const barSeriesRef = useRef<ISeriesApi<'Bar'> | null>(null)

  const [candlestickData, setCandlestickData] = useState<CandlestickData[]>([])
  const [volumeData, setVolumeData] = useState<VolumeData[]>([])
  const [areaData, setAreaData] = useState<{ time: Time; value: number }[]>([])
  const [currentPrice, setCurrentPrice] = useState<number>(0)
  const [priceChange, setPriceChange] = useState<number>(0)
  const [priceChangePercent, setPriceChangePercent] = useState<number>(0)
  const [timeframe, setTimeframe] = useState<string>('1h')
  const [chartType, setChartType] = useState<'candlestick' | 'area' | 'line' | 'bar'>('candlestick')
  const [isChartReady, setIsChartReady] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())

  // TradingView theme configuration
  const chartTheme = useMemo(() => {
    if (theme === 'light') {
      return {
        background: '#ffffff',
        textColor: '#333333',
        gridColor: '#e1e1e1',
        borderColor: '#d1d5db',
        upColor: '#26a69a',
        downColor: '#ef5350',
        volumeUpColor: 'rgba(38, 166, 154, 0.5)',
        volumeDownColor: 'rgba(239, 83, 80, 0.5)'
      }
    }
    return {
      background: '#1e1e1e',
      textColor: '#d1d5db',
      gridColor: '#374151',
      borderColor: '#4b5563',
      upColor: '#26a69a',
      downColor: '#ef5350',
      volumeUpColor: 'rgba(38, 166, 154, 0.5)',
      volumeDownColor: 'rgba(239, 83, 80, 0.5)'
    }
  }, [theme])

  // Generate comprehensive sample data with more realistic patterns
  const generateSampleData = useCallback(() => {
    const candlesticks: CandlestickData[] = []
    const volumes: VolumeData[] = []
    const areas: { time: Time; value: number }[] = []
    const lines: { time: Time; value: number }[] = []
    const bars: { time: Time; open: number; high: number; low: number; close: number }[] = []

    const basePrice = 50000
    const now = Math.floor(Date.now() / 1000)
    let previousClose = basePrice
    let trend = Math.random() > 0.5 ? 1 : -1
    let trendStrength = Math.random() * 0.5 + 0.5

    for (let i = 500; i >= 0; i--) {
      const time = (now - i * 3600) as Time // 1-hour intervals
      
      // Add trend and mean reversion
      if (Math.random() < 0.1) {
        trend *= -1
        trendStrength = Math.random() * 0.5 + 0.5
      }
      
      const volatility = previousClose * (0.01 + trendStrength * 0.02)
      const trendMove = trend * volatility * 0.3
      const randomMove = (Math.random() - 0.5) * volatility

      const open = previousClose + trendMove + randomMove * 0.3
      const close = open + trendMove + randomMove
      const high = Math.max(open, close) + Math.random() * volatility * 0.5
      const low = Math.min(open, close) - Math.random() * volatility * 0.5

      // Ensure realistic price movements
      const finalOpen = Math.max(open, low)
      const finalClose = Math.max(Math.min(close, high), low)
      const finalHigh = Math.max(high, finalOpen, finalClose)
      const finalLow = Math.min(low, finalOpen, finalClose)

      const volume = Math.random() * 15000000 + 500000
      const color = finalClose >= finalOpen ? '#26a69a' : '#ef5350'

      candlesticks.push({
        time,
        open: Number(finalOpen.toFixed(2)),
        high: Number(finalHigh.toFixed(2)),
        low: Number(finalLow.toFixed(2)),
        close: Number(finalClose.toFixed(2))
      })

      volumes.push({
        time,
        value: volume,
        color
      })

      areas.push({
        time,
        value: finalClose
      })
      
      lines.push({
        time,
        value: finalClose
      })
      
      bars.push({
        time,
        open: Number(finalOpen.toFixed(2)),
        high: Number(finalHigh.toFixed(2)),
        low: Number(finalLow.toFixed(2)),
        close: Number(finalClose.toFixed(2))
      })

      previousClose = finalClose
    }

    return { candlesticks, volumes, areas, lines, bars }
  }, [])

  useEffect(() => {
    if (!chartContainerRef.current) return

    setIsLoading(true)
    const { candlesticks, volumes, areas, lines, bars } = generateSampleData()
    
    // Use provided data or generated data
    const finalCandlesticks = data || candlesticks
    const finalVolumes = volumes
    const finalAreas = areas
    const finalLines = lines
    const finalBars = bars
    
    setCandlestickData(finalCandlesticks)
    setVolumeData(finalVolumes)
    setAreaData(finalAreas)

    // Set current price and change
    const lastCandle = finalCandlesticks[finalCandlesticks.length - 1]
    const firstCandle = finalCandlesticks[0]
    setCurrentPrice(lastCandle.close)
    setPriceChange(lastCandle.close - firstCandle.open)
    setPriceChangePercent(((lastCandle.close - firstCandle.open) / firstCandle.open) * 100)
    setLastUpdate(new Date())

    // Enhanced TradingView-style chart configuration
    const baseChartOptions = {
      layout: {
        textColor: variant === 'full' ? chartTheme.textColor : 'transparent',
        background: {
          type: ColorType.Solid,
          color: variant === 'full' ? chartTheme.background : 'transparent'
        },
        fontSize: 12,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
      },
      grid: {
        vertLines: {
          color: variant === 'full' ? chartTheme.gridColor : 'transparent',
          visible: variant === 'full'
        },
        horzLines: {
          color: variant === 'full' ? chartTheme.gridColor : 'transparent',
          visible: variant === 'full'
        }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: variant === 'full' ? '#758696' : 'transparent',
          visible: variant === 'full'
        },
        horzLine: {
          color: variant === 'full' ? '#758696' : 'transparent',
          visible: variant === 'full'
        }
      },
      rightPriceScale: {
        borderColor: variant === 'full' ? chartTheme.borderColor : 'transparent',
        textColor: variant === 'full' ? chartTheme.textColor : 'transparent',
        visible: variant === 'full',
        scaleMargins: {
          top: 0.1,
          bottom: showVolume ? 0.25 : 0.2
        },
        mode: PriceScaleMode.Normal,
        // Enhanced price scale options from TradingView docs
        entireTextOnly: false,
        minimumWidth: 60,
        alignLabels: true,
        autoScale: true,
        invertScale: false,
        lockVisibleTimeRangeOnResize: true
      },
      leftPriceScale: {
        borderColor: variant === 'full' ? chartTheme.borderColor : 'transparent',
        textColor: variant === 'full' ? chartTheme.textColor : 'transparent',
        visible: false,
        mode: PriceScaleMode.Normal,
        entireTextOnly: false,
        minimumWidth: 60,
        alignLabels: true,
        autoScale: true,
        invertScale: false
      },
      timeScale: {
        borderColor: variant === 'full' ? chartTheme.borderColor : 'transparent',
        textColor: variant === 'full' ? chartTheme.textColor : 'transparent',
        visible: variant === 'full',
        timeVisible: variant === 'full',
        secondsVisible: false,
        borderVisible: variant === 'full',
        fixLeftEdge: true,
        fixRightEdge: false,
        lockVisibleTimeRangeOnResize: true,
        shiftVisibleRangeOnNewBar: true,
        // Enhanced time scale options from TradingView docs
        minBarSpacing: 0.5,
        rightOffset: 0,
        barSpacing: 6,
        rightBarStaysOnScroll: true,
        tickMarkFormatter: (time: UTCTimestamp, tickMarkType: number, locale: string) => {
          const date = new Date(time * 1000)
          switch (tickMarkType) {
            case 0: // Year
              return date.getFullYear().toString()
            case 1: // Month
              return date.toLocaleDateString(locale, { month: 'short' })
            case 2: // Day of month
              return date.getDate().toString()
            case 3: // Time without seconds
              return date.toLocaleTimeString(locale, { 
                hour: '2-digit', 
                minute: '2-digit',
                hour12: false 
              })
            default:
              return date.toLocaleTimeString(locale, { 
                hour: '2-digit', 
                minute: '2-digit',
                hour12: false 
              })
          }
        }
      },
      handleScroll: variant === 'full',
      handleScale: variant === 'full' && {
        axisPressedMouseMove: {
          time: true,
          price: true
        },
        axisDoubleClickReset: true,
        mouseWheel: true,
        pinch: true
      },
      width: chartContainerRef.current.clientWidth,
      height: variant === 'minimal' ? height : chartContainerRef.current.clientHeight,
      overlayPriceScales: {
        ticksVisible: false,
        borderVisible: false,
        // Enhanced overlay price scales from TradingView docs
        scaleMargins: {
          top: 0.8,
          bottom: 0
        }
      },
      localization: {
        priceFormatter: (price: number) => {
          return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: price < 1 ? 4 : 2
          }).format(price)
        },
        timeFormatter: (time: UTCTimestamp) => {
          const date = new Date(time * 1000)
          return date.toLocaleString()
        }
      }
    }

    const chart = createChart(chartContainerRef.current, baseChartOptions)
    chartRef.current = chart

    // Add main series based on chart type with enhanced styling
    let candlestickSeries, areaSeries, lineSeries, barSeries
    
    switch (chartType) {
      case 'candlestick':
        candlestickSeries = chart.addSeries(CandlestickSeries, {
          upColor: chartTheme.upColor,
          downColor: chartTheme.downColor,
          borderVisible: true,
          borderUpColor: chartTheme.upColor,
          borderDownColor: chartTheme.downColor,
          wickUpColor: chartTheme.upColor,
          wickDownColor: chartTheme.downColor,
          priceScaleId: 'right'
        })
        candlestickSeriesRef.current = candlestickSeries
        candlestickSeries.setData(finalCandlesticks)
        break
        
      case 'area':
        areaSeries = chart.addSeries(AreaSeries, {
          lineColor: '#2962FF',
          topColor: 'rgba(41, 98, 255, 0.28)',
          bottomColor: 'rgba(41, 98, 255, 0.01)',
          lineWidth: 2,
          lineType: LineType.Curved,
          priceScaleId: 'right',
          crosshairMarkerVisible: false,
          crosshairMarkerRadius: 3,
          crosshairMarkerBorderColor: '#2962FF',
          crosshairMarkerBackgroundColor: '#ffffff'
        })
        areaSeriesRef.current = areaSeries
        areaSeries.setData(finalAreas)
        break
        
      case 'line':
        lineSeries = chart.addSeries(LineSeries, {
          color: '#FF6B6B',
          lineWidth: 2,
          lineType: LineType.Curved,
          priceScaleId: 'right',
          crosshairMarkerVisible: true,
          crosshairMarkerRadius: 4,
          crosshairMarkerBorderColor: '#FF6B6B',
          crosshairMarkerBackgroundColor: '#ffffff'
        })
        lineSeriesRef.current = lineSeries
        lineSeries.setData(finalLines)
        break
        
      case 'bar':
        barSeries = chart.addSeries(BarSeries, {
          upColor: chartTheme.upColor,
          downColor: chartTheme.downColor,
          priceScaleId: 'right'
        })
        barSeriesRef.current = barSeries
        barSeries.setData(finalBars)
        break
    }

    // Add volume series for full variant with enhanced styling
    if (variant === 'full' && showVolume) {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        color: '#6b7280',
        priceFormat: {
          type: 'volume'
        },
        priceScaleId: 'volume'
      })
      volumeSeriesRef.current = volumeSeries
      
      // Set volume data with proper colors
      const coloredVolumeData = finalVolumes.map((item) => ({
        time: item.time,
        value: item.value,
        color: item.color
      }))
      volumeSeries.setData(coloredVolumeData)
    }

    chart.timeScale().fitContent()
    setIsChartReady(true)
    setIsLoading(false)

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
  }, [variant, chartType, height, generateSampleData, data, chartTheme, showVolume])

  // Update chart when symbol changes
  useEffect(() => {
    if (!isChartReady) return

    setIsLoading(true)
    const { candlesticks, volumes, areas, lines, bars } = generateSampleData()
    
    const finalCandlesticks = data || candlesticks
    const finalVolumes = volumes
    const finalAreas = areas
    const finalLines = lines
    const finalBars = bars
    
    setCandlestickData(finalCandlesticks)
    setVolumeData(finalVolumes)
    setAreaData(finalAreas)
    setLastUpdate(new Date())

    // Update series based on current chart type
    if (candlestickSeriesRef.current) {
      candlestickSeriesRef.current.setData(finalCandlesticks)
    }
    if (volumeSeriesRef.current) {
      const coloredVolumeData = finalVolumes.map((item) => ({
        time: item.time,
        value: item.value,
        color: item.color
      }))
      volumeSeriesRef.current.setData(coloredVolumeData)
    }
    if (areaSeriesRef.current) {
      areaSeriesRef.current.setData(finalAreas)
    }
    if (lineSeriesRef.current) {
      lineSeriesRef.current.setData(finalLines)
    }
    if (barSeriesRef.current) {
      barSeriesRef.current.setData(finalBars)
    }

    const lastCandle = finalCandlesticks[finalCandlesticks.length - 1]
    const firstCandle = finalCandlesticks[0]
    setCurrentPrice(lastCandle.close)
    setPriceChange(lastCandle.close - firstCandle.open)
    setPriceChangePercent(((lastCandle.close - firstCandle.open) / firstCandle.open) * 100)
    setIsLoading(false)
  }, [symbol, isChartReady, generateSampleData, data])

  // Update chart type with enhanced series management
  useEffect(() => {
    if (!isChartReady || !chartRef.current) return

    // Remove all existing series
    const allSeries = [
      candlestickSeriesRef.current,
      areaSeriesRef.current,
      lineSeriesRef.current,
      barSeriesRef.current
    ]
    
    allSeries.forEach((series) => {
      if (series) {
        chartRef.current!.removeSeries(series)
      }
    })

    // Reset refs
    candlestickSeriesRef.current = null
    areaSeriesRef.current = null
    lineSeriesRef.current = null
    barSeriesRef.current = null

    // Add new series based on chart type
    let candlestickSeries, areaSeries, lineSeries, barSeries
    
    switch (chartType) {
      case 'candlestick':
        candlestickSeries = chartRef.current.addSeries(CandlestickSeries, {
          upColor: chartTheme.upColor,
          downColor: chartTheme.downColor,
          borderVisible: true,
          borderUpColor: chartTheme.upColor,
          borderDownColor: chartTheme.downColor,
          wickUpColor: chartTheme.upColor,
          wickDownColor: chartTheme.downColor,
          priceScaleId: 'right'
        })
        candlestickSeriesRef.current = candlestickSeries
        candlestickSeries.setData(candlestickData)
        break
        
      case 'area':
        areaSeries = chartRef.current.addSeries(AreaSeries, {
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
        break
        
      case 'line':
        lineSeries = chartRef.current.addSeries(LineSeries, {
          color: '#FF6B6B',
          lineWidth: 2,
          lineType: LineType.Curved,
          priceScaleId: 'right',
          crosshairMarkerVisible: true
        })
        lineSeriesRef.current = lineSeries
        lineSeries.setData(areaData.map((item) => ({ time: item.time, value: item.value })))
        break
        
      case 'bar':
        barSeries = chartRef.current.addSeries(BarSeries, {
          upColor: chartTheme.upColor,
          downColor: chartTheme.downColor,
          priceScaleId: 'right'
        })
        barSeriesRef.current = barSeries
        barSeries.setData(candlestickData)
        break
    }
  }, [chartType, isChartReady, candlestickData, areaData, chartTheme])

  const timeframes = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M']
  const chartTypes = [
    { value: 'candlestick', label: 'Candles', icon: '📊' },
    { value: 'area', label: 'Area', icon: '📈' },
    { value: 'line', label: 'Line', icon: '📉' },
    { value: 'bar', label: 'Bars', icon: '📊' }
  ] as const
  const isUp = priceChange >= 0

  // Enhanced Time Scale API methods
  const getTimeScaleApi = useCallback(() => {
    return chartRef.current?.timeScale()
  }, [])

  const resetTimeScale = useCallback(() => {
    const timeScale = getTimeScaleApi()
    if (timeScale) {
      timeScale.resetTimeScale()
    }
  }, [getTimeScaleApi])

  const setVisibleRange = useCallback((from: Time, to: Time) => {
    const timeScale = getTimeScaleApi()
    if (timeScale) {
      timeScale.setVisibleLogicalRange({ from, to })
    }
  }, [getTimeScaleApi])

  const fitContent = useCallback(() => {
    const timeScale = getTimeScaleApi()
    if (timeScale) {
      timeScale.fitContent()
    }
  }, [getTimeScaleApi])

  // Enhanced Price Scale API methods
  const getPriceScaleApi = useCallback((scaleId: string) => {
    return chartRef.current?.priceScale(scaleId)
  }, [])

  // Refresh data function
  const handleRefresh = useCallback(() => {
    if (!isChartReady) return
    
    setIsLoading(true)
    const { candlesticks, volumes, areas, lines, bars } = generateSampleData()
    
    const finalCandlesticks = data || candlesticks
    const finalVolumes = volumes
    const finalAreas = areas
    const finalLines = lines
    const finalBars = bars
    
    setCandlestickData(finalCandlesticks)
    setVolumeData(finalVolumes)
    setAreaData(finalAreas)
    setLastUpdate(new Date())

    // Update all active series
    if (candlestickSeriesRef.current) {
      candlestickSeriesRef.current.setData(finalCandlesticks)
    }
    if (volumeSeriesRef.current) {
      const coloredVolumeData = finalVolumes.map((item) => ({
        time: item.time,
        value: item.value,
        color: item.color
      }))
      volumeSeriesRef.current.setData(coloredVolumeData)
    }
    if (areaSeriesRef.current) {
      areaSeriesRef.current.setData(finalAreas)
    }
    if (lineSeriesRef.current) {
      lineSeriesRef.current.setData(finalLines)
    }
    if (barSeriesRef.current) {
      barSeriesRef.current.setData(finalBars)
    }

    const lastCandle = finalCandlesticks[finalCandlesticks.length - 1]
    const firstCandle = finalCandlesticks[0]
    setCurrentPrice(lastCandle.close)
    setPriceChange(lastCandle.close - firstCandle.open)
    setPriceChangePercent(((lastCandle.close - firstCandle.open) / firstCandle.open) * 100)
    
    // Auto-fit content after refresh
    fitContent()
    setIsLoading(false)
  }, [isChartReady, generateSampleData, data, fitContent])

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
            {/* Chart type selector */}
            <select
              value={chartType}
              onChange={(e) => setChartType(e.target.value as any)}
              className="px-3 py-1 bg-gray-700 text-gray-300 rounded text-sm hover:bg-gray-600 transition-colors"
            >
              {chartTypes.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.icon} {type.label}
                </option>
              ))}
            </select>
            
            {/* Refresh button */}
            <button
              onClick={handleRefresh}
              disabled={isLoading}
              className={`p-2 rounded transition-colors ${
                isLoading
                  ? 'bg-gray-600 text-gray-400 cursor-not-allowed'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
            
            {/* Fit content button */}
            <button
              onClick={fitContent}
              className="p-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
              title="Fit Content"
            >
              <Maximize2 className="w-4 h-4" />
            </button>
            
            {/* Reset time scale button */}
            <button
              onClick={resetTimeScale}
              className="p-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
              title="Reset Time Scale"
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-20">
          <div className="bg-gray-800 rounded-lg p-4 flex items-center gap-3">
            <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
            <span className="text-white text-sm">Loading chart data...</span>
          </div>
        </div>
      )}

      {/* Chart container */}
      <div 
        ref={chartContainerRef} 
        className={`w-full ${
          variant === 'full' ? 'h-full pt-16 pb-10' : 'h-full'
        }`} 
      />

      {/* Enhanced status bar */}
      {variant === 'full' && (
        <div className="absolute bottom-0 left-0 right-0 bg-gray-800 border-t border-gray-700 px-4 py-2">
          <div className="flex justify-between items-center text-xs text-gray-400">
            <div className="flex items-center gap-4">
              <span>Symbol: {symbol}</span>
              <span>Timeframe: {timeframe}</span>
              <span>Type: {chartType}</span>
              <span>Candles: {candlestickData.length}</span>
              {lastUpdate && (
                <span>Last Update: {lastUpdate.toLocaleTimeString()}</span>
              )}
            </div>
            <div className="flex items-center gap-4">
              <span>O: {candlestickData[0]?.open.toFixed(2) || '0.00'}</span>
              <span>H: {Math.max(...candlestickData.map(d => d.high)).toFixed(2)}</span>
              <span>L: {Math.min(...candlestickData.map(d => d.low)).toFixed(2)}</span>
              <span>C: {currentPrice.toFixed(2)}</span>
            </div>
            <div className="text-xs text-gray-500">
              Powered by TradingView Lightweight Charts
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default TradingViewChart
