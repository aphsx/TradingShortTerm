import React, { useState, useEffect } from 'react'

interface DailyPerformance {
  date: string
  fills: number
  symbols: string[]
  pnl: number
}

interface TradeStats {
  netRealizedPnl: number
  grossPnl: number
  totalFills: number
  totalFees: number
  dayWinRate: number
  winningDays: number
  losingDays: number
}

const DailyPerformanceCalendar: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Mock data matching the image exactly
  const mockDailyPerformances: DailyPerformance[] = [
    { date: '2023-12-21', fills: 0, symbols: [], pnl: 0 },
    { date: '2023-12-22', fills: 0, symbols: [], pnl: 0 },
    { date: '2023-12-23', fills: 0, symbols: [], pnl: 0 },
    { date: '2023-12-24', fills: 0, symbols: [], pnl: 0 },
    { date: '2023-12-25', fills: 0, symbols: [], pnl: 0 },
    { date: '2023-12-26', fills: 0, symbols: [], pnl: 0 },
    { date: '2023-12-27', fills: 0, symbols: [], pnl: 0 },
    { date: '2023-12-28', fills: 0, symbols: [], pnl: 0 },
    { date: '2023-12-29', fills: 0, symbols: [], pnl: 0 },
    { date: '2023-12-30', fills: 0, symbols: [], pnl: 0 },
    { date: '2023-12-31', fills: 0, symbols: [], pnl: 0 },
    { date: '2024-01-01', fills: 0, symbols: [], pnl: 0 },
    { date: '2024-01-02', fills: 82, symbols: ['ADA', 'LTC', 'HYPE'], pnl: 3.2976 },
    { date: '2024-01-03', fills: 53, symbols: ['HYPE', 'LTC', 'ADA'], pnl: 2.8885 },
    { date: '2024-01-04', fills: 62, symbols: ['ADA', 'LTC', 'HYPE'], pnl: 3.3636 },
    { date: '2024-01-05', fills: 148, symbols: ['HYPE', 'LTC', 'ADA'], pnl: 8.5594 },
    { date: '2024-01-06', fills: 118, symbols: ['HYPE', 'ADA', 'LTC'], pnl: 7.7886 },
    { date: '2024-01-07', fills: 151, symbols: ['HYPE', 'ADA', 'LTC'], pnl: 6.5661 },
    { date: '2024-01-08', fills: 139, symbols: ['HYPE', 'ADA', 'LTC'], pnl: 5.9737 },
    { date: '2024-01-09', fills: 141, symbols: ['HYPE', 'LTC', 'ADA'], pnl: 6.2059 },
    { date: '2024-01-10', fills: 42, symbols: ['HYPE', 'ADA', 'LTC'], pnl: 1.9184 },
    { date: '2024-01-11', fills: 83, symbols: ['HYPE', 'ADA', 'LTC'], pnl: 3.5409 },
    { date: '2024-01-12', fills: 85, symbols: ['LTC', 'ADA', 'HYPE'], pnl: -5.8453 },
    { date: '2024-01-13', fills: 149, symbols: ['LTC', 'ADA', 'HYPE'], pnl: 7.4851 },
    { date: '2024-01-14', fills: 178, symbols: ['LTC', 'HYPE', 'ADA'], pnl: 8.0537 },
    { date: '2024-01-15', fills: 31, symbols: ['ADA', 'LTC', 'HYPE'], pnl: 1.6022 },
    { date: '2024-01-16', fills: 158, symbols: ['HYPE', 'LTC', 'ADA'], pnl: 5.9679 },
    { date: '2024-01-17', fills: 64, symbols: ['ADA', 'LTC', 'HYPE'], pnl: 2.4083 },
    { date: '2024-01-18', fills: 106, symbols: ['HYPE', 'LTC', 'ADA'], pnl: 4.8868 },
    { date: '2024-01-19', fills: 12, symbols: ['HYPE', 'LTC'], pnl: 21.0910 }
  ]

  const mockStats: TradeStats = {
    netRealizedPnl: 74.8849,
    grossPnl: 95.7523,
    totalFills: 1802,
    totalFees: 20.8674,
    dayWinRate: 94.4,
    winningDays: 17,
    losingDays: 1
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-1/4 mb-4"></div>
          <div className="grid grid-cols-7 gap-2">
            {[...Array(35)].map((_, i) => (
              <div key={i} className="h-20 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="text-red-500">Error loading data: {error}</div>
      </div>
    )
  }

  const dailyPerformances = mockDailyPerformances
  const stats = mockStats

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', { 
      month: 'short', 
      day: 'numeric' 
    })
  }

  const getProfitColor = (pnl: number) => {
    if (pnl > 0) return 'text-green-600'
    if (pnl < 0) return 'text-red-600'
    return 'text-gray-400'
  }

  const getBgColor = (pnl: number, fills: number) => {
    if (fills === 0) return 'bg-gray-50 border-gray-200'
    if (pnl > 0) return 'bg-green-50 border-green-200'
    if (pnl < 0) return 'bg-red-50 border-red-200'
    return 'bg-gray-50 border-gray-200'
  }

  const getDotColor = (pnl: number, fills: number) => {
    if (fills === 0) return 'bg-gray-400'
    if (pnl > 0) return 'bg-green-500'
    if (pnl < 0) return 'bg-red-500'
    return 'bg-gray-400'
  }

  return (
    <div className="p-6 bg-white rounded-lg shadow-lg">
      {/* Header with Stats */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-800 mb-4">Daily Performance Calendar</h2>
        
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <div className="bg-gray-50 p-3 rounded">
            <div className="text-xs text-gray-500 mb-1">Net Realized PnL</div>
            <div className={`text-lg font-semibold ${getProfitColor(stats.netRealizedPnl)}`}>
              {stats.netRealizedPnl >= 0 ? '+' : ''}{stats.netRealizedPnl.toFixed(4)} USDC
            </div>
            <div className="text-xs text-gray-400">
              (Gross: {stats.grossPnl.toFixed(4)})
            </div>
          </div>
          
          <div className="bg-gray-50 p-3 rounded">
            <div className="text-xs text-gray-500 mb-1">Total Fills</div>
            <div className="text-lg font-semibold text-gray-800">
              {stats.totalFills}
            </div>
          </div>
          
          <div className="bg-gray-50 p-3 rounded">
            <div className="text-xs text-gray-500 mb-1">Total Fees</div>
            <div className="text-lg font-semibold text-orange-600">
              {stats.totalFees >= 0 ? '-' : ''}{Math.abs(stats.totalFees).toFixed(4)} USDC
            </div>
          </div>
          
          <div className="bg-gray-50 p-3 rounded">
            <div className="text-xs text-gray-500 mb-1">Day Win Rate</div>
            <div className="text-lg font-semibold text-gray-800">
              {stats.dayWinRate.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-400">
              ({stats.winningDays}W/{stats.losingDays}L)
            </div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mb-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-green-500 rounded-full"></div>
          <span className="text-gray-600">Profit</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-red-500 rounded-full"></div>
          <span className="text-gray-600">Loss</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-gray-400 rounded-full"></div>
          <span className="text-gray-600">No trades</span>
        </div>
      </div>

      {/* Calendar Grid */}
      <div className="grid grid-cols-7 gap-2">
        {dailyPerformances.map((performance) => (
          <div
            key={performance.date}
            className={`border rounded-lg p-2 min-h-[80px] ${getBgColor(performance.pnl, performance.fills)}`}
          >
            <div className="flex items-start justify-between mb-1">
              <div className="text-xs text-gray-600">
                {formatDate(performance.date)}
              </div>
              <div className={`w-2 h-2 rounded-full ${getDotColor(performance.pnl, performance.fills)}`}></div>
            </div>
            
            {performance.fills > 0 ? (
              <>
                <div className="text-xs text-gray-500 mb-1">
                  {performance.fills} fills
                </div>
                {performance.symbols.length > 0 && (
                  <div className="text-xs text-gray-600 mb-1">
                    {performance.symbols.slice(0, 2).join(', ')}
                    {performance.symbols.length > 2 && '...'}
                  </div>
                )}
                <div className={`text-xs font-semibold ${getProfitColor(performance.pnl)}`}>
                  {performance.pnl >= 0 ? '+' : ''}{performance.pnl.toFixed(4)} USDC
                </div>
              </>
            ) : (
              <div className="text-xs text-gray-400">
                0.00 USDC
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default DailyPerformanceCalendar
