import { useEffect, useRef } from 'react'
import { createChart, IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import { useTradingStore } from '../store/trading'

export function TradingChart(): JSX.Element {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  
  // Use selectors to prevent unnecessary re-renders
  const isConnected = useTradingStore((state) => state.isConnected)
  const currentPrice = useTradingStore((state) => state.currentPrice)

  // Initialize chart once
  useEffect(() => {
    if (!chartContainerRef.current) {
      console.warn('Chart container not ready')
      return
    }

    try {
      const container = chartContainerRef.current
      const width = container.clientWidth
      const height = container.clientHeight || 500

      console.log('Creating chart with dimensions:', { width, height })

      const chart = createChart(container, {
        width: width,
        height: height,
        layout: {
          background: { color: '#1e1e1e' },
          textColor: '#d1d4dc'
        },
        grid: {
          vertLines: { color: '#2b2b2b' },
          horzLines: { color: '#2b2b2b' }
        },
        crosshair: {
          mode: 1
        },
        rightPriceScale: {
          borderColor: '#2b2b2b'
        },
        timeScale: {
          borderColor: '#2b2b2b',
          timeVisible: true,
          secondsVisible: false
        }
      })

      if (!chart) {
        console.error('Failed to create chart')
        return
      }

      const lineSeries = chart.addLineSeries({
        color: '#2962FF',
        lineWidth: 2,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 4,
        lastValueVisible: true,
        priceLineVisible: true
      })

      chartRef.current = chart
      seriesRef.current = lineSeries

      // Handle window resize
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
        chart.remove()
      }
    } catch (error) {
      console.error('Error initializing chart:', error)
    }
  }, [])

  // Update chart with new price data - NO RE-RENDER on every tick
  useEffect(() => {
    if (!seriesRef.current || !currentPrice) return

    const dataPoint = {
      time: Math.floor(currentPrice.timestamp / 1000) as Time,
      value: parseFloat(currentPrice.price)
    }

    // Direct update to chart, no React re-render
    seriesRef.current.update(dataPoint)
  }, [currentPrice])

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <div style={{ 
        padding: '10px', 
        background: '#1e1e1e', 
        color: '#fff',
        borderBottom: '1px solid #2b2b2b'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <div>
            <span style={{ color: '#888' }}>Status: </span>
            <span style={{ color: isConnected ? '#4caf50' : '#f44336' }}>
              {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
            </span>
          </div>
          {currentPrice && (
            <>
              <div>
                <span style={{ color: '#888' }}>Symbol: </span>
                <span style={{ fontWeight: 'bold' }}>{currentPrice.symbol}</span>
              </div>
              <div>
                <span style={{ color: '#888' }}>Price: </span>
                <span style={{ fontSize: '20px', fontWeight: 'bold', color: '#2962FF' }}>
                  ${parseFloat(currentPrice.price).toFixed(2)}
                </span>
              </div>
            </>
          )}
        </div>
      </div>
      <div ref={chartContainerRef} style={{ width: '100%', height: 'calc(100% - 60px)' }} />
    </div>
  )
}
