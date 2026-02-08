import React from 'react'
import { X, TrendingUp, TrendingDown, Clock, DollarSign, Target, Activity } from 'lucide-react'
import { TradeOrder } from '../lib/supabase'

interface DayDetailModalProps {
  isOpen: boolean
  onClose: () => void
  date: string
  trades: TradeOrder[]
  dayStats: {
    totalPnl: number
    grossPnl: number
    totalFees: number
    winRate: number
    totalTrades: number
    winningTrades: number
    losingTrades: number
  }
}

const DayDetailModal: React.FC<DayDetailModalProps> = ({
  isOpen,
  onClose,
  date,
  trades,
  dayStats
}) => {
  if (!isOpen) return null

  const formatTime = (timeString: string) => {
    return new Date(timeString).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  }

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 4
    }).format(price)
  }

  const getProfitColor = (pnl: number) => {
    if (pnl > 0) return 'text-green-600'
    if (pnl < 0) return 'text-red-600'
    return 'text-gray-400'
  }

  const getSideColor = (side: string) => {
    return side === 'buy' ? 'text-green-600 bg-green-50' : 'text-red-600 bg-red-50'
  }

  const getAnalysisInsights = (trades: TradeOrder[]) => {
    const insights: string[] = []
    
    // Win rate analysis
    if (dayStats.winRate >= 80) {
      insights.push("Excellent win rate today! Very consistent trading.")
    } else if (dayStats.winRate >= 60) {
      insights.push("Good win rate. Consider reviewing losing trades for patterns.")
    } else {
      insights.push("Low win rate today. Review your strategy and market conditions.")
    }

    // Fee analysis
    const feeRatio = dayStats.totalFees / Math.abs(dayStats.grossPnl) * 100
    if (feeRatio > 10) {
      insights.push("High fee ratio detected. Consider reducing trade frequency or using limit orders.")
    }

    // PnL consistency
    const pnlVariance = trades.reduce((acc, trade) => {
      if (trade.net_pnl) {
        acc.push(trade.net_pnl)
      }
      return acc
    }, [] as number[])

    if (pnlVariance.length > 0) {
      const variance = pnlVariance.reduce((sum, pnl) => sum + Math.pow(pnl - (dayStats.totalPnl / pnlVariance.length), 2), 0) / pnlVariance.length
      if (variance > 100) {
        insights.push("High PnL variance detected. Focus on consistency over big wins.")
      }
    }

    // Time analysis
    const entryHours = trades.map(trade => new Date(trade.entry_time).getHours())
    const peakHour = entryHours.reduce((acc, hour) => {
      acc[hour] = (acc[hour] || 0) + 1
      return acc
    }, {} as Record<number, number>)

    const mostActiveHour = Object.entries(peakHour).reduce((a, b) => (a[1] > b[1] ? a : b))[0]
    insights.push(`Most active trading hour: ${mostActiveHour}:00-${parseInt(mostActiveHour) + 1}:00`)

    return insights
  }

  const analysisInsights = getAnalysisInsights(trades)

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-6xl w-full max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="border-b border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-2xl font-bold text-gray-800">
                {formatDate(date)}
              </h2>
              <p className="text-gray-600">Detailed Trading Analysis</p>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-gray-500" />
            </button>
          </div>

          {/* Day Stats Summary */}
          <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
            <div className="bg-gray-50 p-3 rounded-lg">
              <div className="text-xs text-gray-500 mb-1">Net PnL</div>
              <div className={`text-lg font-semibold ${getProfitColor(dayStats.totalPnl)}`}>
                {dayStats.totalPnl >= 0 ? '+' : ''}{formatPrice(dayStats.totalPnl)}
              </div>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <div className="text-xs text-gray-500 mb-1">Gross PnL</div>
              <div className={`text-lg font-semibold ${getProfitColor(dayStats.grossPnl)}`}>
                {dayStats.grossPnl >= 0 ? '+' : ''}{formatPrice(dayStats.grossPnl)}
              </div>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <div className="text-xs text-gray-500 mb-1">Total Fees</div>
              <div className="text-lg font-semibold text-orange-600">
                {formatPrice(dayStats.totalFees)}
              </div>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <div className="text-xs text-gray-500 mb-1">Win Rate</div>
              <div className="text-lg font-semibold text-gray-800">
                {dayStats.winRate.toFixed(1)}%
              </div>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <div className="text-xs text-gray-500 mb-1">Total Trades</div>
              <div className="text-lg font-semibold text-gray-800">
                {dayStats.totalTrades}
              </div>
            </div>
            <div className="bg-gray-50 p-3 rounded-lg">
              <div className="text-xs text-gray-500 mb-1">W/L Ratio</div>
              <div className="text-lg font-semibold text-gray-800">
                {dayStats.winningTrades}W/{dayStats.losingTrades}L
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Trade List */}
            <div className="lg:col-span-2">
              <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5" />
                Trade History ({trades.length} trades)
              </h3>
              
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {trades.map((trade) => (
                  <div key={trade.id} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${getSideColor(trade.side)}`}>
                          {trade.side.toUpperCase()}
                        </span>
                        <span className="font-semibold text-gray-800">{trade.symbol}</span>
                        <span className="text-sm text-gray-500">{formatTime(trade.entry_time)}</span>
                      </div>
                      {trade.net_pnl && (
                        <div className={`font-semibold ${getProfitColor(trade.net_pnl)}`}>
                          {trade.net_pnl >= 0 ? '+' : ''}{formatPrice(trade.net_pnl)}
                        </div>
                      )}
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-gray-500">Entry:</span>
                        <span className="ml-2 text-gray-800">{formatPrice(trade.entry_price || 0)}</span>
                      </div>
                      {trade.exit_price && (
                        <div>
                          <span className="text-gray-500">Exit:</span>
                          <span className="ml-2 text-gray-800">{formatPrice(trade.exit_price)}</span>
                        </div>
                      )}
                      <div>
                        <span className="text-gray-500">Size:</span>
                        <span className="ml-2 text-gray-800">{trade.size || 0}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Leverage:</span>
                        <span className="ml-2 text-gray-800">{trade.leverage}x</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Fees:</span>
                        <span className="ml-2 text-gray-800">{formatPrice(trade.entry_fee + trade.exit_fee + trade.funding_fees)}</span>
                      </div>
                      {trade.exit_reason && (
                        <div>
                          <span className="text-gray-500">Reason:</span>
                          <span className="ml-2 text-gray-800">{trade.exit_reason}</span>
                        </div>
                      )}
                    </div>
                    
                    {trade.notes && (
                      <div className="mt-2 pt-2 border-t border-gray-100">
                        <span className="text-gray-500 text-sm">Notes:</span>
                        <p className="text-gray-700 text-sm mt-1">{trade.notes}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Analysis Panel */}
            <div>
              <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
                <Target className="w-5 h-5" />
                AI Analysis & Insights
              </h3>
              
              <div className="space-y-4">
                {/* Performance Analysis */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <h4 className="font-semibold text-blue-800 mb-2 flex items-center gap-2">
                    <TrendingUp className="w-4 h-4" />
                    Performance Analysis
                  </h4>
                  <ul className="space-y-2 text-sm text-blue-700">
                    {analysisInsights.map((insight, index) => (
                      <li key={index} className="flex items-start gap-2">
                        <span className="text-blue-500 mt-1">•</span>
                        <span>{insight}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Recommendations */}
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                  <h4 className="font-semibold text-green-800 mb-2 flex items-center gap-2">
                    <DollarSign className="w-4 h-4" />
                    Recommendations
                  </h4>
                  <ul className="space-y-2 text-sm text-green-700">
                    {dayStats.winRate < 60 && (
                      <li className="flex items-start gap-2">
                        <span className="text-green-500 mt-1">•</span>
                        <span>Consider reducing position size until win rate improves</span>
                      </li>
                    )}
                    {dayStats.totalFees > dayStats.grossPnl * 0.1 && (
                      <li className="flex items-start gap-2">
                        <span className="text-green-500 mt-1">•</span>
                        <span>High fees detected. Consider using limit orders to reduce costs</span>
                      </li>
                    )}
                    {dayStats.totalTrades > 50 && (
                      <li className="flex items-start gap-2">
                        <span className="text-green-500 mt-1">•</span>
                        <span>High trading frequency. Focus on quality over quantity</span>
                      </li>
                    )}
                    <li className="flex items-start gap-2">
                      <span className="text-green-500 mt-1">•</span>
                      <span>Review losing trades to identify common patterns</span>
                    </li>
                  </ul>
                </div>

                {/* Risk Analysis */}
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                  <h4 className="font-semibold text-orange-800 mb-2 flex items-center gap-2">
                    <Activity className="w-4 h-4" />
                    Risk Analysis
                  </h4>
                  <div className="space-y-2 text-sm text-orange-700">
                    <div className="flex justify-between">
                      <span>Avg Leverage Used:</span>
                      <span className="font-medium">
                        {(trades.reduce((sum, t) => sum + t.leverage, 0) / trades.length).toFixed(1)}x
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Risk/Reward Ratio:</span>
                      <span className="font-medium">
                        {dayStats.grossPnl > 0 ? (dayStats.grossPnl / Math.abs(dayStats.totalFees)).toFixed(2) : 'N/A'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Trading Span:</span>
                      <span className="font-medium">
                        {trades.length > 0 ? 
                          `${Math.max(...trades.map(t => new Date(t.entry_time).getHours())) - 
                           Math.min(...trades.map(t => new Date(t.entry_time).getHours()))} hours` : 
                          'N/A'
                        }
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export { DayDetailModal }
