import { useEffect, useRef } from 'react'
import { createChart, IChartApi, Time } from 'lightweight-charts'
import { useTradingStore } from '../store/trading'
import { Card } from './ui/card'
import { Badge } from './ui/badge'
import { CheckCircle2, AlertCircle } from 'lucide-react'

export function TradingChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<any>(null)
  const hasSeriesCreated = useRef(false)
  
  const isConnected = useTradingStore((state) => state.isConnected)
  const currentPrice = useTradingStore((state) => state.currentPrice)

  useEffect(() => {
    if (!chartContainerRef.current) {
      console.warn('Chart container not ready')
      return
    }

    // If chart already exists, don't recreate it
    if (chartRef.current && hasSeriesCreated.current) {
      return
    }

    try {
      const container = chartContainerRef.current
      
      // Clear any existing chart
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
        seriesRef.current = null
        hasSeriesCreated.current = false
      }

      const width = container.clientWidth
      const height = container.clientHeight || 500

      console.log('Creating chart with dimensions:', { width, height })

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

      const lineSeries = chart.addSeries({
        color: '#fbbf24',
        lineWidth: 2,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 4,
        lastValueVisible: true,
        priceLineVisible: true
      } as any)

      chartRef.current = chart
      seriesRef.current = lineSeries
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

  useEffect(() => {
    if (!seriesRef.current || !currentPrice) return

    try {
      const dataPoint = {
        time: Math.floor(currentPrice.timestamp / 1000) as Time,
        value: parseFloat(currentPrice.price)
      }

      // Ensure the value is a valid number
      if (!isFinite(dataPoint.value)) {
        console.warn('Invalid price value:', currentPrice.price)
        return
      }

      seriesRef.current.update(dataPoint)
    } catch (error) {
      console.error('Error updating chart data:', error)
    }
  }, [currentPrice])

  return (
    <Card className="w-full h-full flex flex-col border-amber-900/30 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-950 overflow-hidden">
      <div className="flex-shrink-0 border-b border-slate-800 bg-slate-900/50 px-4 py-3">
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
                <div className="font-semibold text-white">{currentPrice.symbol}</div>
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
      </div>
      
      <div ref={chartContainerRef} className="flex-1 w-full overflow-hidden" />
    </Card>
  )
}
