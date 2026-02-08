import { createClient } from '@supabase/supabase-js'

const supabaseUrl = 'https://nqspzwlavfcuqecuqmrx.supabase.co'
const supabaseAnonKey = 'sb_publishable_lSyQqU5RF2gLvZLPKqmPaA_lbhJA7jE'

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

export interface TradeOrder {
  id: string
  analysis_id?: string
  symbol: string
  side: string
  status: string
  entry_price?: number
  exit_price?: number
  leverage: number
  margin?: number
  size?: number
  tp_price?: number
  sl_price?: number
  entry_time: string
  exit_time?: string
  pnl_amount?: number
  exit_reason?: string
  created_at: string
  notes?: string
  entry_fee: number
  exit_fee: number
  funding_fees: number
  net_pnl?: number
}

export interface DailyPerformance {
  date: string
  fills: number
  symbols: string[]
  pnl: number
  isWin: boolean
}
