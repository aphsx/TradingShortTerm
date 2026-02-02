import { useEffect, useRef, useState, useCallback } from 'react'
import { 
  createChart, 
  ColorType, 
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  CandlestickData as LWCCandlestickData,
  Time,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  AreaSeries,
  MouseEventParams
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
  ZoomOut,
  BarChart3,
  LineChart as LineChartIcon,
  AreaChart as AreaChartIcon,
  HelpCircle
} from 'lucide-react'
import CountdownTimer from './CountdownTimer'

export default function CandlestickChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  const { candles, isLoadingHistory, getCandleArray, symbol, interval, currentPrice } = useTradingStore()
  const [isChartReady, setIsChartReady] = useState(false)
  const [chartType, setChartType] = useState<'candlestick' | 'line' | 'area'>('candlestick')
  const [lastPrice, setLastPrice] = useState<number>(0)
  const [priceChange, setPriceChange] = useState<number>(0)
  const [priceChangePercent, setPriceChangePercent] = useState<number>(0)
  const [selectedRange, setSelectedRange] = useState<'1D' | '1W' | '1M' | '1Y' | 'ALL'>('ALL')
  const [tooltip, setTooltip] = useState<{ x: number; y: number; content: string } | null>(null)
  const [mainSeries, setMainSeries] = useState<ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> | ISeriesApi<'Area'> | null>(null)
  const [userInteracted, setUserInteracted] = useState(false) // Track if user manually zoomed/panned

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

      // Create main series based on chart type
      let mainSeries: ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> | ISeriesApi<'Area'>
      
      switch (chartType) {
        case 'line':
          mainSeries = chart.addSeries(LineSeries, {
            color: '#2196F3',
            lineWidth: 2,
            title: symbol
          })
          break
        case 'area':
          mainSeries = chart.addSeries(AreaSeries, {
            topColor: 'rgba(33, 150, 243, 0.56)',
            bottomColor: 'rgba(33, 150, 243, 0.04)',
            lineColor: '#2196F3',
            lineWidth: 2,
            title: symbol
          })
          break
        default:
          mainSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
            title: symbol
          })
          candleSeriesRef.current = mainSeries as ISeriesApi<'Candlestick'>
      }
      
      setMainSeries(mainSeries)

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
      candleSeriesRef.current = mainSeries as ISeriesApi<'Candlestick'>
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

  // Filter data based on selected time range
  const filterDataByRange = useCallback((data: any[]) => {
    if (!data.length) return data
    
    const now = Date.now()
    const oneDay = 24 * 60 * 60 * 1000
    const oneWeek = 7 * oneDay
    const oneMonth = 30 * oneDay
    const oneYear = 365 * oneDay
    
    let cutoffTime = 0
    
    switch (selectedRange) {
      case '1D':
        cutoffTime = now - oneDay
        break
      case '1W':
        cutoffTime = now - oneWeek
        break
      case '1M':
        cutoffTime = now - oneMonth
        break
      case '1Y':
        cutoffTime = now - oneYear
        break
      default:
        return data // ALL
    }
    
    return data.filter(item => {
      const itemTime = typeof item.time === 'number' ? item.time * 1000 : new Date(item.time).getTime()
      return itemTime >= cutoffTime
    })
  }, [selectedRange])

  // Handle crosshair move for tooltip
  const handleCrosshairMove = useCallback((param: MouseEventParams<Time>) => {
    if (!param.point || !mainSeries || !param.time) {
      setTooltip(null)
      return
    }
    
    const data = param.seriesData.get(mainSeries)
    if (!data) {
      setTooltip(null)
      return
    }
    
    let content = ''
    const time = new Date(typeof param.time === 'number' ? param.time * 1000 : param.time as string)
    const timeStr = time.toLocaleString()
    
    if ('open' in data && 'high' in data && 'low' in data && 'close' in data) {
      // Candlestick data
      const candleData = data as LWCCandlestickData
      content = `
        <div class="bg-[#1e222d] border border-[#2b2b43] rounded p-2 text-xs">
          <div class="text-gray-400 mb-1">${timeStr}</div>
          <div class="grid grid-cols-2 gap-2">
            <div><span class="text-gray-500">O:</span> <span class="text-white">${candleData.open.toFixed(2)}</span></div>
            <div><span class="text-gray-500">H:</span> <span class="text-white">${candleData.high.toFixed(2)}</span></div>
            <div><span class="text-gray-500">L:</span> <span class="text-white">${candleData.low.toFixed(2)}</span></div>
            <div><span class="text-gray-500">C:</span> <span class="text-white">${candleData.close.toFixed(2)}</span></div>
          </div>
        </div>
      `
    } else if ('value' in data) {
      // Line/Area data
      const valueData = data as { value: number }
      content = `
        <div class="bg-[#1e222d] border border-[#2b2b43] rounded p-2 text-xs">
          <div class="text-gray-400 mb-1">${timeStr}</div>
          <div><span class="text-gray-500">Price:</span> <span class="text-white">${valueData.value.toFixed(2)}</span></div>
        </div>
      `
    }
    
    setTooltip({
      x: param.point.x,
      y: param.point.y,
      content
    })
  }, [mainSeries])

      // Subscribe to crosshair events
      useEffect(() => {
        if (!chartRef.current || !isChartReady) return
        
        const chart = chartRef.current
        chart.subscribeCrosshairMove(handleCrosshairMove)
        
        // Track when user manually scrolls or zooms
        const handleTimeScaleChange = () => {
          setUserInteracted(true)
        }
        
        // These events indicate user interaction
        chart.subscribeClick(handleTimeScaleChange)
        
        return () => {
          chart.unsubscribeCrosshairMove(handleCrosshairMove)
          // Note: There's no direct unsubscribe for click in Lightweight Charts
        }
      }, [chartRef, isChartReady, handleCrosshairMove])
  useEffect(() => {
    if (currentPrice > 0) {
      setLastPrice(currentPrice)
      
      const candleArray = getCandleArray()
      if (candleArray.length > 0) {
        const firstCandle = candleArray[0]
        const change = currentPrice - firstCandle.open
        const changePercent = ((change / firstCandle.open) * 100)
        setPriceChange(change)
        setPriceChangePercent(changePercent)
      }
    }
  }, [currentPrice, getCandleArray])

  // Update chart data
  useEffect(() => {
    if (!isChartReady || !mainSeries || !volumeSeriesRef.current) return

    const candleArray = getCandleArray()
    if (candleArray.length === 0) return

    try {
      // Filter data based on selected range
      const filteredData = filterDataByRange(candleArray)
      
      // Prepare data based on chart type
      let chartData: any[] = []
      
      switch (chartType) {
        case 'line':
          chartData = filteredData.map((c) => ({
            time: c.time,
            value: c.close
          }))
          break
        case 'area':
          chartData = filteredData.map((c) => ({
            time: c.time,
            value: c.close
          }))
          break
        default:
          chartData = filteredData.map((c) => ({
            time: c.time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close
          }))
      }

      const volumeData = filteredData.map((c) => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open ? '#26a69a80' : '#ef535080'
      }))

      mainSeries.setData(chartData)
      volumeSeriesRef.current.setData(volumeData)

      // Update price info
      if (chartData.length > 0) {
        const lastItem = chartData[chartData.length - 1]
        const firstItem = chartData[0]
        const lastPrice = 'close' in lastItem ? lastItem.close : lastItem.value
        const firstPrice = 'open' in firstItem ? firstItem.open : firstItem.value
        
        setLastPrice(lastPrice)
        const change = lastPrice - firstPrice
        const changePercent = ((change / firstPrice) * 100)
        setPriceChange(change)
        setPriceChangePercent(changePercent)
      }

      if (chartRef.current) {
        // Only fit content if user hasn't manually interacted (zoomed/panned)
        if (!userInteracted) {
          chartRef.current.timeScale().fitContent()
        }
      }
    } catch (error) {
      console.error('Error updating chart:', error)
    }
  }, [candles, isChartReady, getCandleArray, chartType, filterDataByRange, mainSeries])

  const handleZoomIn = () => {
    if (chartRef.current) {
      setUserInteracted(true) // Mark that user interacted
      const timeScale = chartRef.current.timeScale()
      const scrollPosition = timeScale.scrollPosition()
      timeScale.applyOptions({
        barSpacing: Math.min(timeScale.options().barSpacing * 1.2, 50)
      })
    }
  }

  const handleZoomOut = () => {
    if (chartRef.current) {
      setUserInteracted(true) // Mark that user interacted
      const timeScale = chartRef.current.timeScale()
      timeScale.applyOptions({
        barSpacing: Math.max(timeScale.options().barSpacing * 0.8, 1)
      })
    }
  }

  const handleScrollLeft = () => {
    if (chartRef.current) {
      setUserInteracted(true) // Mark that user interacted
      const timeScale = chartRef.current.timeScale()
      const position = timeScale.scrollPosition()
      timeScale.scrollToPosition(position - 10, false)
    }
  }

  const handleScrollRight = () => {
    if (chartRef.current) {
      setUserInteracted(true) // Mark that user interacted
      const timeScale = chartRef.current.timeScale()
      const position = timeScale.scrollPosition()
      timeScale.scrollToPosition(position + 10, false)
    }
  }

  const handleFitContent = () => {
    if (chartRef.current) {
      setUserInteracted(false) // Reset user interaction when fitting content
      chartRef.current.timeScale().fitContent()
    }
  }

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!chartRef.current) return
      
      switch (e.key) {
        case 'ArrowLeft':
          handleScrollLeft()
          break
        case 'ArrowRight':
          handleScrollRight()
          break
        case '+':
        case '=':
          handleZoomIn()
          break
        case '-':
        case '_':
          handleZoomOut()
          break
        case 'r':
        case 'R':
          handleFitContent()
          break
        case '1':
          setSelectedRange('1D')
          break
        case '2':
          setSelectedRange('1W')
          break
        case '3':
          setSelectedRange('1M')
          break
        case '4':
          setSelectedRange('1Y')
          break
        case '0':
          setSelectedRange('ALL')
          break
      }
    }
    
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Handle chart type change
  const handleChartTypeChange = (type: 'candlestick' | 'line' | 'area') => {
    setUserInteracted(false) // Reset when changing chart type
    setChartType(type)
  }

  // Handle range change
  const handleRangeChange = (range: '1D' | '1W' | '1M' | '1Y' | 'ALL') => {
    setUserInteracted(false) // Reset when changing range
    setSelectedRange(range)
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
            <CountdownTimer />
            <div className={`flex items-center gap-1 ${getTrendColor()}`}>
              <span className="text-sm font-semibold">
                {priceChange > 0 ? '+' : ''}{priceChange.toFixed(2)}
              </span>
              <span className="text-sm">
                ({priceChangePercent > 0 ? '+' : ''}{priceChangePercent.toFixed(2)}%)
              </span>
            </div>
          </div>

          {/* Time Range Selector */}
          <div className="flex items-center gap-1 bg-[#1E222D] rounded p-1">
            {(['1D', '1W', '1M', '1Y', 'ALL'] as const).map((range) => (
              <button
                key={range}
                onClick={() => handleRangeChange(range)}
                className={`px-3 py-1 text-sm rounded transition-colors ${
                  selectedRange === range
                    ? 'bg-[#2962FF] text-white'
                    : 'text-gray-400 hover:text-white hover:bg-[#2B2B43]'
                }`}
                title={`Show ${range === 'ALL' ? 'all data' : range}`}
              >
                {range}
              </button>
            ))}
          </div>

          {/* Chart Type Selector */}
          <div className="flex items-center gap-1 bg-[#1E222D] rounded p-1">
            <button
              onClick={() => handleChartTypeChange('candlestick')}
              className={`p-1.5 rounded transition-colors ${
                chartType === 'candlestick'
                  ? 'bg-[#2962FF] text-white'
                  : 'text-gray-400 hover:text-white hover:bg-[#2B2B43]'
              }`}
              title="Candlestick Chart"
            >
              <BarChart3 className="w-4 h-4" />
            </button>
            <button
              onClick={() => handleChartTypeChange('line')}
              className={`p-1.5 rounded transition-colors ${
                chartType === 'line'
                  ? 'bg-[#2962FF] text-white'
                  : 'text-gray-400 hover:text-white hover:bg-[#2B2B43]'
              }`}
              title="Line Chart"
            >
              <LineChartIcon className="w-4 h-4" />
            </button>
            <button
              onClick={() => handleChartTypeChange('area')}
              className={`p-1.5 rounded transition-colors ${
                chartType === 'area'
                  ? 'bg-[#2962FF] text-white'
                  : 'text-gray-400 hover:text-white hover:bg-[#2B2B43]'
              }`}
              title="Area Chart"
            >
              <AreaChartIcon className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Chart Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleScrollLeft}
            className="p-1.5 hover:bg-[#2B2B43] rounded transition-colors"
            title="Scroll Left (←)"
          >
            <ChevronLeft className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={handleScrollRight}
            className="p-1.5 hover:bg-[#2B2B43] rounded transition-colors"
            title="Scroll Right (→)"
          >
            <ChevronRight className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={handleZoomOut}
            className="p-1.5 hover:bg-[#2B2B43] rounded transition-colors"
            title="Zoom Out (-)"
          >
            <ZoomOut className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={handleZoomIn}
            className="p-1.5 hover:bg-[#2B2B43] rounded transition-colors"
            title="Zoom In (+)"
          >
            <ZoomIn className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={handleFitContent}
            className="px-3 py-1.5 text-sm hover:bg-[#2B2B43] rounded transition-colors text-gray-400"
            title="Fit Content (R)"
          >
            Fit
          </button>
          <div className="relative group">
            <button
              className="p-1.5 hover:bg-[#2B2B43] rounded transition-colors text-gray-400"
              title="Keyboard Shortcuts"
            >
              <HelpCircle className="w-4 h-4" />
            </button>
            <div className="absolute right-0 top-full mt-2 w-64 bg-[#1E222D] border border-[#2B2B43] rounded p-3 text-xs opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-30">
              <div className="text-gray-400 mb-2 font-semibold">Keyboard Shortcuts:</div>
              <div className="space-y-1 text-gray-300">
                <div className="flex justify-between">
                  <span>Scroll Left</span>
                  <kbd className="px-1 py-0.5 bg-[#2B2B43] rounded text-[10px]">←</kbd>
                </div>
                <div className="flex justify-between">
                  <span>Scroll Right</span>
                  <kbd className="px-1 py-0.5 bg-[#2B2B43] rounded text-[10px]">→</kbd>
                </div>
                <div className="flex justify-between">
                  <span>Zoom In</span>
                  <kbd className="px-1 py-0.5 bg-[#2B2B43] rounded text-[10px]">+</kbd>
                </div>
                <div className="flex justify-between">
                  <span>Zoom Out</span>
                  <kbd className="px-1 py-0.5 bg-[#2B2B43] rounded text-[10px]">-</kbd>
                </div>
                <div className="flex justify-between">
                  <span>Fit Content</span>
                  <kbd className="px-1 py-0.5 bg-[#2B2B43] rounded text-[10px]">R</kbd>
                </div>
                <div className="border-t border-[#2B2B43] pt-1 mt-1">
                  <div className="flex justify-between">
                    <span>1 Day</span>
                    <kbd className="px-1 py-0.5 bg-[#2B2B43] rounded text-[10px]">1</kbd>
                  </div>
                  <div className="flex justify-between">
                    <span>1 Week</span>
                    <kbd className="px-1 py-0.5 bg-[#2B2B43] rounded text-[10px]">2</kbd>
                  </div>
                  <div className="flex justify-between">
                    <span>1 Month</span>
                    <kbd className="px-1 py-0.5 bg-[#2B2B43] rounded text-[10px]">3</kbd>
                  </div>
                  <div className="flex justify-between">
                    <span>1 Year</span>
                    <kbd className="px-1 py-0.5 bg-[#2B2B43] rounded text-[10px]">4</kbd>
                  </div>
                  <div className="flex justify-between">
                    <span>All Time</span>
                    <kbd className="px-1 py-0.5 bg-[#2B2B43] rounded text-[10px]">0</kbd>
                  </div>
                </div>
              </div>
            </div>
          </div>
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
        
        {/* Tooltip */}
        {tooltip && (
          <div
            className="absolute z-20 pointer-events-none"
            style={{
              left: tooltip.x + 10,
              top: tooltip.y - 40,
              transform: 'translate(0, -100%)'
            }}
            dangerouslySetInnerHTML={{ __html: tooltip.content }}
          />
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
