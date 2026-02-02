import { useEffect, useRef, useState } from 'react'
import { createChart, ColorType, SeriesType } from 'lightweight-charts'
import { useTradingStore } from '../store/useTradingStore'

export default function CandlestickChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<any>(null)
  const candleSeriesRef = useRef<any>(null)
  const volumeSeriesRef = useRef<any>(null)

  const { candles, isLoadingHistory, getCandleArray } = useTradingStore()
  const [isChartReady, setIsChartReady] = useState(false)

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) {
      console.error('❌ Chart container ref is null')
      return
    }

    const container = chartContainerRef.current
    const width = container.clientWidth
    const height = container.clientHeight

    console.log('📊 Initializing chart with dimensions:', { width, height })

    if (width === 0 || height === 0) {
      console.warn('⚠️ Container has zero dimensions, setting defaults')
    }

    try {
      const chart = createChart(container, {
        layout: {
          background: { type: ColorType.Solid, color: '#131722' },
          textColor: '#d1d4dc'
        },
        grid: {
          vertLines: { color: '#1e222d' },
          horzLines: { color: '#1e222d' }
        },
        width: width || 800,
        height: height || 600,
        rightPriceScale: {
          borderColor: '#2b2b43'
        },
        timeScale: {
          borderColor: '#2b2b43',
          timeVisible: true,
          secondsVisible: false
        },
        crosshair: {
          mode: 1 as any
        }
      })

      console.log('✅ Chart instance created')

      // Candlestick series - use specific method
      const candleSeries = chart.addCandlestickSeries({
        upColor: '#089981',
        downColor: '#f23645',
        borderUpColor: '#089981',
        borderDownColor: '#f23645',
        wickUpColor: '#089981',
        wickDownColor: '#f23645'
      })

      // Volume series - use specific method
      const volumeSeries = chart.addHistogramSeries({
        color: '#26a69a',
        priceScaleId: ''
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

      console.log('✅ Series created and chart ready')

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
        console.log('🧹 Cleaning up chart')
        resizeObserver.disconnect()
        if (chartRef.current) {
          chartRef.current.remove()
          chartRef.current = null
        }
      }
    } catch (error) {
      console.error('❌ Error creating chart:', error)
    }
  }, [])

  // Update chart data
  useEffect(() => {
    if (!isChartReady || !candleSeriesRef.current || !volumeSeriesRef.current) {
      console.log('⏳ Chart not ready yet', { isChartReady, hasCandleSeries: !!candleSeriesRef.current, hasVolumeSeries: !!volumeSeriesRef.current })
      return
    }

    const candleArray = getCandleArray()
    console.log('📊 Got candle array with', candleArray.length, 'candles')
    
    if (candleArray.length === 0) {
      console.warn('⚠️ No candle data available')
      return
    }

    try {
      const candleData = candleArray.map((c: any) => ({
        time: c.time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close
      }))

      const volumeData = candleArray.map((c: any) => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open ? '#08998180' : '#f2364580'
      }))

      console.log('📈 Setting candle data:', candleData.length, 'candles')
      candleSeriesRef.current.setData(candleData)
      
      console.log('📊 Setting volume data:', volumeData.length, 'volumes')
      volumeSeriesRef.current.setData(volumeData)

      // Fit content
      if (chartRef.current) {
        chartRef.current.timeScale().fitContent()
        console.log('✅ Chart updated successfully')
      }
    } catch (error) {
      console.error('❌ Error updating chart:', error)
    }
  }, [candles, isChartReady, getCandleArray])

  return (
    <div className="relative w-full h-full min-h-[400px] bg-[#131722]">
      {isLoadingHistory && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#131722] z-10">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
            <p className="text-gray-400">Loading chart data...</p>
          </div>
        </div>
      )}
      <div ref={chartContainerRef} className="w-full h-full min-h-[400px]" />
    </div>
  )
}
