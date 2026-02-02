import { useEffect, useRef } from 'react'
import { createChart, ColorType, SeriesType, CrosshairMode } from 'lightweight-charts'
import { useTradingStore } from '../store/useTradingStore'

export default function TradingChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<any>(null)
  const candleSeriesRef = useRef<any>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const { symbol, interval } = useTradingStore()

  useEffect(() => {
    if (!chartContainerRef.current) return

    try {
      // สร้าง Chart Instance พร้อม Theme เหมือน TradingView
      const chart = createChart(chartContainerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: '#131722' },
          textColor: '#d1d4dc'
        },
        grid: {
          vertLines: { color: '#2B2B43' },
          horzLines: { color: '#2B2B43' }
        },
        width: chartContainerRef.current.clientWidth,
        height: chartContainerRef.current.clientHeight,
        crosshair: {
          mode: CrosshairMode.Normal
        },
        priceScale: {
          borderColor: '#2B2B43'
        },
        timeScale: {
          borderColor: '#2B2B43',
          timeVisible: true,
          secondsVisible: false
        }
      })

      // สร้าง Candlestick Series ด้วย v5 API
      const candleSeries = chart.addSeries({
        type: SeriesType.Candlestick,
        upColor: '#089981',
        downColor: '#f23645',
        borderDownColor: '#f23645',
        borderUpColor: '#089981',
        wickDownColor: '#f23645',
        wickUpColor: '#089981'
      } as any)

      chartRef.current = chart
      candleSeriesRef.current = candleSeries

      console.log('✅ Chart created successfully for', symbol, interval)

      // โหลดข้อมูลย้อนหลัง 500 แท่ง
      const loadHistoricalData = async () => {
        try {
          console.log('📥 Loading historical data from backend...')
          const response = await fetch(
            `http://localhost:8080/api/kline?symbol=${symbol}&interval=${interval}&limit=500`
          )
          
          if (!response.ok) throw new Error('Failed to fetch')
          
          const data = await response.json()
          
          // แปลงข้อมูล Binance ให้เป็น format ของ lightweight-charts
          const candleData = data.map((item: any) => ({
            time: Math.floor(item.openTime / 1000),
            open: parseFloat(item.open),
            high: parseFloat(item.high),
            low: parseFloat(item.low),
            close: parseFloat(item.close)
          }))

          // ใส่ข้อมูลลงกราฟ
          if (candleData.length > 0) {
            candleSeries.setData(candleData)
            chart.timeScale().fitContent()
            console.log('✅ Loaded', candleData.length, 'candles')
          }
        } catch (error) {
          console.error('❌ Error loading historical data:', error)
        }
      }

      loadHistoricalData()

      // เชื่อมต่อ WebSocket สำหรับ real-time updates
      const connectWebSocket = () => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return

        const wsUrl = `ws://localhost:8080/api/kline?symbol=${symbol}&interval=${interval}`
        console.log('🔌 Connecting WebSocket:', wsUrl)

        const ws = new WebSocket(wsUrl)

        ws.onopen = () => {
          console.log('✅ WebSocket connected')
        }

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            const tick = {
              time: Math.floor(data.time / 1000),
              open: data.open,
              high: data.high,
              low: data.low,
              close: data.close
            }
            // อัปเดตแท่งเทียนล่าสุด (real-time)
            candleSeries.update(tick)
            console.log(`📊 ${symbol} ${interval} - Close: ${tick.close}`)
          } catch (error) {
            console.error('❌ WebSocket message error:', error)
          }
        }

        ws.onerror = (error) => {
          console.error('❌ WebSocket error:', error)
        }

        ws.onclose = () => {
          console.log('🔌 WebSocket disconnected')
          // Reconnect after 5 seconds
          setTimeout(connectWebSocket, 5000)
        }

        wsRef.current = ws
      }

      connectWebSocket()

      // Responsive resize
      const handleResize = () => {
        if (chartContainerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: chartContainerRef.current.clientWidth,
            height: chartContainerRef.current.clientHeight
          })
        }
      }

      window.addEventListener('resize', handleResize)

      // Cleanup
      return () => {
        window.removeEventListener('resize', handleResize)
        if (wsRef.current) wsRef.current.close()
        if (chartRef.current) chartRef.current.remove()
      }
    } catch (error) {
      console.error('❌ Error creating chart:', error)
    }
  }, [symbol, interval])

  return (
    <div className="relative w-full h-full bg-[#131722]">
      <div ref={chartContainerRef} className="w-full h-full" />
    </div>
  )
}
