import React, { useState } from 'react'
import { useTradeOrders } from '../hooks/useTradeOrders'
import { DayDetailModal } from './DayDetailModal'

const DailyPerformanceCalendar: React.FC = () => {
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const { getDailyPerformances, getTradeStats, getTradesForDay, getDayStats, loading, error } = useTradeOrders()
  
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

  const dailyPerformances = getDailyPerformances(30)
  const stats = getTradeStats()

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

  const handleDayClick = (date: string) => {
    setSelectedDate(date)
    setIsModalOpen(true)
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
    setSelectedDate(null)
  }

  return (
    <>
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
          <div className="flex items-center gap-2 text-gray-500">
            <span className="text-xs">Click on any day to see detailed analysis</span>
          </div>
        </div>

        {/* Calendar Grid */}
        <div className="grid grid-cols-7 gap-2">
          {dailyPerformances.map((performance) => (
            <div
              key={performance.date}
              onClick={() => handleDayClick(performance.date)}
              className={`border rounded-lg p-2 min-h-[80px] cursor-pointer transition-all hover:shadow-md hover:scale-105 ${getBgColor(performance.pnl, performance.fills)}`}
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

      {/* Day Detail Modal */}
      {selectedDate && (
        <DayDetailModal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          date={selectedDate}
          trades={getTradesForDay(selectedDate)}
          dayStats={getDayStats(selectedDate)}
        />
      )}
    </>
  )
}

export default DailyPerformanceCalendar
