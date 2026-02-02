import { useEffect, useState } from 'react'
import { useTradingStore } from '../store/useTradingStore'

export default function CountdownTimer() {
  const { candleCloseTime, interval, updateCandleCloseTime } = useTradingStore()
  const [timeRemaining, setTimeRemaining] = useState<string>('00:00')

  useEffect(() => {
    if (!candleCloseTime) return
    
    const timer = setInterval(() => {
      const now = Date.now()
      const remaining = Math.max(0, candleCloseTime - now)
      
      if (remaining === 0) {
        setTimeRemaining('00:00')
        clearInterval(timer)
        return
      }

      const seconds = Math.floor(remaining / 1000)
      const minutes = Math.floor(seconds / 60)
      const secs = seconds % 60
      
      setTimeRemaining(
        `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
      )
    }, 1000)

    return () => clearInterval(timer)
  }, [candleCloseTime, interval])

  const getIntervalMs = (interval: string): number => {
    const intervals: Record<string, number> = {
      '1m': 60 * 1000,
      '3m': 3 * 60 * 1000,
      '5m': 5 * 60 * 1000,
      '15m': 15 * 60 * 1000,
      '30m': 30 * 60 * 1000,
      '1h': 60 * 60 * 1000,
      '2h': 2 * 60 * 60 * 1000,
      '4h': 4 * 60 * 60 * 1000,
      '6h': 6 * 60 * 60 * 1000,
      '8h': 8 * 60 * 60 * 1000,
      '12h': 12 * 60 * 60 * 1000,
      '1d': 24 * 60 * 60 * 1000,
      '3d': 3 * 24 * 60 * 60 * 1000,
      '1w': 7 * 24 * 60 * 60 * 1000,
      '1M': 30 * 24 * 60 * 60 * 1000,
    }
    return intervals[interval] || 60 * 1000
  }

  // Calculate candle close time based on interval
  useEffect(() => {
    const intervalMs = getIntervalMs(interval)
    const now = Date.now()
    const nextCloseTime = Math.ceil(now / intervalMs) * intervalMs
    updateCandleCloseTime(nextCloseTime)
  }, [interval, updateCandleCloseTime])

  if (!candleCloseTime) return null

  return (
    <div className="flex items-center gap-1 px-2 py-1 bg-[#1E222D] rounded border border-[#2B2B43]">
      <div className="w-2 h-2 bg-[#2962FF] rounded-full animate-pulse" />
      <span className="text-xs text-[#2962FF] font-medium">
        {timeRemaining}
      </span>
    </div>
  )
}
