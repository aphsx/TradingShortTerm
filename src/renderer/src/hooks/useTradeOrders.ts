import { useState, useEffect } from 'react'
import { supabase, TradeOrder, MarketAnalysisLog, DailyPerformance } from '../lib/supabase'

export const useTradeOrders = () => {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tradeOrders, setTradeOrders] = useState<TradeOrder[]>([])
  const [marketAnalysis, setMarketAnalysis] = useState<MarketAnalysisLog[]>([])

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      // Fetch trade orders
      const { data: tradesData, error: tradesError } = await supabase
        .from('trade_orders')
        .select('*')
        .order('entry_time', { ascending: false })

      if (tradesError) {
        throw tradesError
      }

      // Fetch market analysis logs
      const { data: analysisData, error: analysisError } = await supabase
        .from('market_analysis_logs')
        .select('*')
        .order('created_at', { ascending: false })

      if (analysisError) {
        throw analysisError
      }

      setTradeOrders(tradesData || [])
      setMarketAnalysis(analysisData || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data')
      console.error('Error fetching data:', err)
    } finally {
      setLoading(false)
    }
  }

  const getDailyPerformances = (days: number = 30): DailyPerformance[] => {
    const performances: DailyPerformance[] = []
    const today = new Date()
    
    // Generate date range for the last N days
    for (let i = days - 1; i >= 0; i--) {
      const date = new Date(today)
      date.setDate(date.getDate() - i)
      const dateStr = date.toISOString().split('T')[0]
      
      performances.push({
        date: dateStr,
        fills: 0,
        symbols: [],
        pnl: 0,
        isWin: false
      })
    }

    // Group trades by date and calculate performance
    const tradesByDate = tradeOrders.reduce((acc, trade) => {
      if (trade.exit_time && trade.net_pnl !== null && trade.net_pnl !== undefined) {
        const exitDate = new Date(trade.exit_time).toISOString().split('T')[0]
        
        if (!acc[exitDate]) {
          acc[exitDate] = {
            trades: [],
            totalPnl: 0,
            symbols: new Set()
          }
        }
        
        acc[exitDate].trades.push(trade)
        acc[exitDate].totalPnl += trade.net_pnl
        acc[exitDate].symbols.add(trade.symbol.replace('/', ''))
      }
      return acc
    }, {} as Record<string, { trades: TradeOrder[], totalPnl: number, symbols: Set<string> }>)

    // Update performances with actual trade data
    performances.forEach((performance) => {
      const dayData = tradesByDate[performance.date]
      if (dayData) {
        performance.fills = dayData.trades.length
        performance.symbols = Array.from(dayData.symbols)
        performance.pnl = dayData.totalPnl
        performance.isWin = dayData.totalPnl > 0
      }
    })

    return performances
  }

  const getTradeStats = () => {
    const completedTrades = tradeOrders.filter(trade => 
      trade.status === 'closed' && trade.exit_time && trade.net_pnl !== null && trade.net_pnl !== undefined
    )

    const totalFills = completedTrades.length
    const grossPnl = completedTrades.reduce((sum, trade) => sum + (trade.pnl_amount || 0), 0)
    const totalFees = completedTrades.reduce((sum, trade) => 
      sum + (trade.entry_fee || 0) + (trade.exit_fee || 0) + (trade.funding_fees || 0), 0
    )
    const netRealizedPnl = completedTrades.reduce((sum, trade) => sum + (trade.net_pnl || 0), 0)

    // Calculate daily performance for win rate
    const dailyPerformances = getDailyPerformances(30)
    const daysWithTrades = dailyPerformances.filter(day => day.fills > 0)
    const winningDays = daysWithTrades.filter(day => day.pnl > 0).length
    const losingDays = daysWithTrades.filter(day => day.pnl < 0).length
    const dayWinRate = daysWithTrades.length > 0 ? (winningDays / daysWithTrades.length) * 100 : 0

    return {
      netRealizedPnl,
      grossPnl,
      totalFills,
      totalFees,
      dayWinRate,
      winningDays,
      losingDays
    }
  }

  const getTradesForDay = (date: string) => {
    return tradeOrders.filter(trade => {
      if (!trade.exit_time) return false
      const exitDate = new Date(trade.exit_time).toISOString().split('T')[0]
      return exitDate === date
    })
  }

  const getDayStats = (date: string) => {
    const dayTrades = getTradesForDay(date)
    
    if (dayTrades.length === 0) {
      return {
        totalPnl: 0,
        grossPnl: 0,
        totalFees: 0,
        winRate: 0,
        totalTrades: 0,
        winningTrades: 0,
        losingTrades: 0
      }
    }

    const totalPnl = dayTrades.reduce((sum, trade) => sum + (trade.net_pnl || 0), 0)
    const grossPnl = dayTrades.reduce((sum, trade) => sum + (trade.pnl_amount || 0), 0)
    const totalFees = dayTrades.reduce((sum, trade) => 
      sum + (trade.entry_fee || 0) + (trade.exit_fee || 0) + (trade.funding_fees || 0), 0
    )
    
    const winningTrades = dayTrades.filter(trade => (trade.net_pnl || 0) > 0).length
    const losingTrades = dayTrades.filter(trade => (trade.net_pnl || 0) < 0).length
    const winRate = dayTrades.length > 0 ? (winningTrades / dayTrades.length) * 100 : 0

    return {
      totalPnl,
      grossPnl,
      totalFees,
      winRate,
      totalTrades: dayTrades.length,
      winningTrades,
      losingTrades
    }
  }

  const getAnalysisForDay = (date: string) => {
    return marketAnalysis.filter(analysis => {
      const analysisDate = new Date(analysis.created_at).toISOString().split('T')[0]
      return analysisDate === date
    })
  }

  return {
    tradeOrders,
    marketAnalysis,
    loading,
    error,
    getDailyPerformances,
    getTradeStats,
    getTradesForDay,
    getDayStats,
    getAnalysisForDay,
    refetch: fetchData
  }
}
