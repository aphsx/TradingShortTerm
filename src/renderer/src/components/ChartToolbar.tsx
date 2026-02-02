import { useTradingStore } from '../store/useTradingStore'
import { cn } from '../lib/utils'

const INTERVALS = [
  { label: '1m', value: '1m' },
  { label: '3m', value: '3m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '30m', value: '30m' },
  { label: '1h', value: '1h' },
  { label: '2h', value: '2h' },
  { label: '4h', value: '4h' },
  { label: '1d', value: '1d' }
]

export default function ChartToolbar() {
  const { interval, setInterval } = useTradingStore()

  return (
    <div className="h-12 bg-[#1e222d] border-b border-[#2b2b43] flex items-center px-4 space-x-2">
      <span className="text-sm text-gray-400 mr-2">Timeframe:</span>
      {INTERVALS.map((item) => (
        <button
          key={item.value}
          onClick={() => setInterval(item.value)}
          className={cn(
            'px-3 py-1.5 text-sm rounded transition-colors',
            interval === item.value
              ? 'bg-blue-600 text-white'
              : 'text-gray-400 hover:bg-gray-700 hover:text-white'
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
