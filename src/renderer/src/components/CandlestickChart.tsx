import { useEffect, useRef } from 'react'
import { 
  createChart, 
  IChartApi, 
  ISeriesApi,
  ColorType,
  LineStyle,
  CrosshairMode
} from 'lightweight-charts'
import { useMarketStore } from '../store/useMarketStore'

interface CandlestickChartProps {
  symbol: string
  interval: string
  className?: string
}

export function CandlestickChart({ symbol, interval, className = '' }: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const resizeObserverRef = useRef<ResizeObserver | null>(null)

  const { 
    candleData, 
    isLoadingHistory, 
    loadHistoricalData, 
    connectWebSocket,
    getCandleArray,
    setSymbol,
    setInterval: setStoreInterval
  } = useMarketStore()

  // Initialize chart with TradingView styling
  useEffect(() => {
    if (!chartContainerRef.current) return

    const container = chartContainerRef.current
    const width = container.clientWidth
    const height = container.clientHeight || 600

    console.log('📊 Initializing TradingView chart...')

    // Create chart with exact TradingView Dark Theme
    const chart = createChart(container, {
      width,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#131722' },
        textColor: '#d1d4dc',
        fontSize: 12,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif'
      },
      grid: {
        vertLines: { 
          color: '#1f2937', // Dark grey
          style: LineStyle.Solid,
          visible: true 
        },
        horzLines: { 
          color: '#1f2937', // Dark grey
          style: LineStyle.Solid,
          visible: true 
        }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          width: 1,
          color: '#758696',
          style: LineStyle.Dashed,
          labelBackgroundColor: '#2962FF'
        },
        horzLine: {
          width: 1,
          color: '#758696',
          style: LineStyle.Dashed,
          labelBackgroundColor: '#2962FF'
        }
      },
      rightPriceScale: {
        borderVisible: false,
        visible: true,
        scaleMargins: {
          top: 0.1,
          bottom: 0.1
        }
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12, // Space on the right (TradingView style)
        barSpacing: 8,
        minBarSpacing: 4,
        fixLeftEdge: false,
        fixRightEdge: false
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
      },
      kineticScroll: {
        touch: true,
        mouse: false
      }
    })

    // Add candlestick series with exact TradingView colors
    const candlestickSeries = chart.addSeries({
      type: 'Candlestick',
      upColor: '#089981', // TradingView green (teal)
      downColor: '#f23645', // TradingView red
      borderUpColor: '#089981',
      borderDownColor: '#f23645',
      wickUpColor: '#089981',
      wickDownColor: '#f23645'
    })

    chartRef.current = chart
    candlestickSeriesRef.current = candlestickSeries

    // Setup ResizeObserver for responsive chart
    resizeObserverRef.current = new ResizeObserver((entries) => {
      if (!chartRef.current) return
      
      const { width: newWidth, height: newHeight } = entries[0].contentRect
      chartRef.current.applyOptions({
        width: newWidth,
        height: newHeight
      })
    })

    resizeObserverRef.current.observe(container)

    return () => {
      // Cleanup
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect()
      }
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
      }
    }
  }, [])

  // Load historical data and connect WebSocket on mount or symbol/interval change
  useEffect(() => {
    console.log(`📈 Loading data for ${symbol} ${interval}`)
    
    // Update store with new symbol/interval
    setSymbol(symbol)
    setStoreInterval(interval)
    
    // Load historical data first
    loadHistoricalData().then(() => {
      // Then connect WebSocket for real-time updates
      connectWebSocket()
    })

  }, [symbol, interval])

  // Update chart when candle data changes
  useEffect(() => {
    if (!candlestickSeriesRef.current || candleData.size === 0) return

    const candles = getCandleArray()
    
    if (candles.length === 0) return

    console.log(`📊 Updating chart with ${candles.length} candles`)
    
    // Set all data at once (more efficient than updating one by one)
    candlestickSeriesRef.current.setData(candles)
    
    // Auto-fit content on first load
    if (chartRef.current && !isLoadingHistory) {
      chartRef.current.timeScale().fitContent()
    }

  }, [candleData, getCandleArray, isLoadingHistory])

  return (
    <div className={`relative ${className}`}>
      {/* Chart container */}
      <div 
        ref={chartContainerRef} 
        className="w-full h-full bg-[#131722]"
        style={{ minHeight: '400px' }}
      />
      
      {/* Loading overlay */}
      {isLoadingHistory && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#131722]/90 z-10">
          <div className="flex flex-col items-center gap-3">
            <div className="relative">
              <div className="w-12 h-12 border-4 border-[#2962FF]/20 border-t-[#2962FF] rounded-full animate-spin" />
            </div>
            <span className="text-[#758696] text-sm font-medium">
              Loading chart data...
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
