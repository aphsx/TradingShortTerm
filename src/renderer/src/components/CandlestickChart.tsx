import { useEffect, useRef, useState } from 'react'
import { 
  createChart, 
  ColorType, 
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  CandlestickData as LWCCandlestickData,
  Time,
  CandlestickSeries,
  HistogramSeries
} from 'lightweight-charts'
import { useTradingStore } from '../store/useTradingStore'
import { 
  TrendingUp, 
  TrendingDown, 
  Minus,
  ChevronLeft,
  ChevronRight,
  Plus,
  ZoomIn,
  ZoomOut
} from 'lucide-react'

export default function CandlestickChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  const { candles, isLoadingHistory, getCandleArray, symbol, interval } = useTradingStore()
  const [isChartReady, setIsChartReady] = useState(false)
  const [chartType, setChartType] = useState<'candlestick' | 'line' | 'area'>('candlestick')
  const [lastPrice, setLastPrice] = useState<number>(0)
  const [priceChange, setPriceChange] = useState<number>(0)
  const [priceChangePercent, setPriceChangePercent] = useState<number>(0)

  // Initialize chart with TradingView styling
  useEffect(() => {
    if (!chartContainerRef.current) return

    const container = chartContainerRef.current
    const width = container.clientWidth
    const height = container.clientHeight

    if (width === 0 || height === 0) return

    try {
      const chart = createChart(container, {
        layout: {
          background: { type: ColorType.Solid, color: '#131722' },
          textColor: '#787B86',
          fontSize: 12,
          fontFamily: '-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif'
        },
        grid: {
          vertLines: { 
            color: '#1E222D',
            style: 0,
            visible: true 
          },
          horzLines: { 
            color: '#1E222D',
            style: 0,
            visible: true 
          }
        },
        width: width,
        height: height,
        rightPriceScale: {
          borderColor: '#2B2B43',
          scaleMargins: {
            top: 0.1,
            bottom: 0.2
          }
        },
        timeScale: {
          borderColor: '#2B2B43',
          timeVisible: true,
          secondsVisible: false,
          rightOffset: 12,
          barSpacing: 6,
          minBarSpacing: 0.5,
          fixLeftEdge: true,
          fixRightEdge: true
        },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: {
            color: '#758696',
            width: 1,
            style: 3,
            labelBackgroundColor: '#131722'
          },
          horzLine: {
            color: '#758696',
            width: 1,
            style: 3,
            labelBackgroundColor: '#131722'
          }
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

      // Candlestick series
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350'
      })

      // Volume series
      const volumeSeries = chart.addSeries(HistogramSeries, {
        color: '#26a69a',
        priceFormat: {
          type: 'volume'
        },
        priceScaleId: '',
        lastValueVisible: false,
        priceLineVisible: false
      })
      
      volumeSeries.priceScale().applyOptions({
        scaleMargins: {
          top: 0.8,
          bottom: 0
        }
      })

      chartRef.current = chart
      candleSeriesRef.current = candleSeries
      volumeSeriesRef.current = volumeSeries
      setIsChartReady(true)

      // Handle resize
      const handleResize = () => {
        if (chartContainerRef.current && chartRef.current) {
          const newWidth = chartContainerRef.current.clientWidth
          const newHeight = chartContainerRef.current.clientHeight
          if (newWidth > 0 && newHeight > 0) {
            chartRef.current.applyOptions({
              width: newWidth,
              height: newHeight
            })
          }
        }
      }

      const resizeObserver = new ResizeObserver(handleResize)
      resizeObserver.observe(chartContainerRef.current)

      return () => {
        resizeObserver.disconnect()
        if (chartRef.current) {
          chartRef.current.remove()
          chartRef.current = null
        }
      }
    } catch (error) {
      console.error('Error creating chart:', error)
    }
  }, [])

  // Update chart data
  useEffect(() => {
    if (!isChartReady || !candleSeriesRef.current || !volumeSeriesRef.current) return

    const candleArray = getCandleArray()
    if (candleArray.length === 0) return

    try {
      const candleData: LWCCandlestickData[] = candleArray.map((c) => ({
        time: c.time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close
      }))

      const volumeData = candleArray.map((c) => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open ? '#26a69a80' : '#ef535080'
      }))

      candleSeriesRef.current.setData(candleData)
      volumeSeriesRef.current.setData(volumeData)

      // Update price info
      if (candleData.length > 0) {
        const lastCandle = candleData[candleData.length - 1]
        const firstCandle = candleData[0]
        setLastPrice(lastCandle.close)
        const change = lastCandle.close - firstCandle.open
        const changePercent = ((change / firstCandle.open) * 100)
        setPriceChange(change)
        setPriceChangePercent(changePercent)
      }

      if (chartRef.current) {
        chartRef.current.timeScale().fitContent()
      }
    } catch (error) {
      console.error('Error updating chart:', error)
    }
  }, [candles, isChartReady, getCandleArray])

  const handleZoomIn = () => {
    if (chartRef.current) {
      const timeScale = chartRef.current.timeScale()
      const scrollPosition = timeScale.scrollPosition()
      timeScale.applyOptions({
        barSpacing: Math.min(timeScale.options().barSpacing * 1.2, 50)
      })
    }
  }

  const handleZoomOut = () => {
    if (chartRef.current) {
      const timeScale = chartRef.current.timeScale()
      timeScale.applyOptions({
        barSpacing: Math.max(timeScale.options().barSpacing * 0.8, 1)
      })
    }
  }

  const handleScrollLeft = () => {
    if (chartRef.current) {
      const timeScale = chartRef.current.timeScale()
      const position = timeScale.scrollPosition()
      timeScale.scrollToPosition(position - 10, false)
    }
  }

  const handleScrollRight = () => {
    if (chartRef.current) {
      const timeScale = chartRef.current.timeScale()
      const position = timeScale.scrollPosition()
      timeScale.scrollToPosition(position + 10, false)
    }
  }

  const handleFitContent = () => {
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent()
    }
  }

  const getTrendIcon = () => {
    if (priceChange > 0) return <TrendingUp className="w-4 h-4" />
    if (priceChange < 0) return <TrendingDown className="w-4 h-4" />
    return <Minus className="w-4 h-4" />
  }

  const getTrendColor = () => {
    if (priceChange > 0) return 'text-[#26a69a]'
    if (priceChange < 0) return 'text-[#ef5350]'
    return 'text-gray-400'
  }

  return (
    <div className="relative w-full h-full bg-[#131722] flex flex-col">
      {/* Chart Header - TradingView Style */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#2B2B43]">
        <div className="flex items-center gap-6">
          {/* Symbol Info */}
          <div className="flex items-center gap-2">
            <span className="text-white font-semibold text-lg">{symbol}</span>
            <span className="text-gray-500 text-sm">{interval}</span>
          </div>

          {/* Price Info */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className={`text-xl font-bold ${getTrendColor()}`}>
                ${lastPrice.toFixed(2)}
              </span>
              {getTrendIcon()}
            </div>
            <div className={`flex items-center gap-1 ${getTrendColor()}`}>
              <span className="text-sm font-semibold">
                {priceChange > 0 ? '+' : ''}{priceChange.toFixed(2)}
              </span>
              <span className="text-sm">
                ({priceChangePercent > 0 ? '+' : ''}{priceChangePercent.toFixed(2)}%)
              </span>
            </div>
          </div>
        </div>

        {/* Chart Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleScrollLeft}
            className="p-1.5 hover:bg-[#2B2B43] rounded transition-colors"
            title="Scroll Left"
          >
            <ChevronLeft className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={handleScrollRight}
            className="p-1.5 hover:bg-[#2B2B43] rounded transition-colors"
            title="Scroll Right"
          >
            <ChevronRight className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={handleZoomOut}
            className="p-1.5 hover:bg-[#2B2B43] rounded transition-colors"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={handleZoomIn}
            className="p-1.5 hover:bg-[#2B2B43] rounded transition-colors"
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={handleFitContent}
            className="px-3 py-1.5 text-sm hover:bg-[#2B2B43] rounded transition-colors text-gray-400"
            title="Fit Content"
          >
            Fit
          </button>
        </div>
      </div>

      {/* Chart Container */}
      <div className="flex-1 relative">
        {isLoadingHistory && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#131722] bg-opacity-90 z-10">
            <div className="text-center">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#2962FF] mx-auto mb-3"></div>
              <p className="text-gray-400 text-sm">Loading chart data...</p>
            </div>
          </div>
        )}
        <div ref={chartContainerRef} className="w-full h-full" />
      </div>

      {/* TradingView Attribution */}
      <div className="absolute bottom-2 left-2 text-[10px] text-gray-600 z-10">
        <a 
          href="https://www.tradingview.com" 
          target="_blank" 
          rel="noopener noreferrer"
          className="hover:text-gray-400 transition-colors"
        >
          Chart by TradingView
        </a>
      </div>
    </div>
  )
}
