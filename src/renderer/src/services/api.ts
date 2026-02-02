const BASE_URL = 'http://localhost:8080/api'

export interface Balance {
  asset: string
  free: string
  locked: string
}

export interface OrderRequest {
  symbol: string
  side: 'BUY' | 'SELL'
  quantity: string
  type?: 'MARKET' | 'LIMIT'
  price?: string
}

export interface OrderResponse {
  orderId?: number
  symbol: string
  side: string
  status: string
  message?: string
}

class ApiService {
  async getBalance(): Promise<Balance[]> {
    try {
      const response = await fetch(`${BASE_URL}/balance`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      return data.balances || []
    } catch (error) {
      console.error('Failed to fetch balance:', error)
      throw error
    }
  }

  async placeOrder(order: OrderRequest): Promise<OrderResponse> {
    try {
      console.log('Placing order:', order)
      const response = await fetch(`${BASE_URL}/order`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(order)
      })

      const data = await response.json()
      
      if (!response.ok) {
        const errorMsg = data?.error || data?.message || `HTTP error! status: ${response.status}`
        throw new Error(errorMsg)
      }

      console.log('Order placed successfully:', data)
      return data
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      console.error('Failed to place order:', errorMessage)
      throw error
    }
  }

  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${BASE_URL}/health`)
      return response.ok
    } catch (error) {
      return false
    }
  }

  async getKlines(symbol: string = 'BTCUSDT', interval: string = '1m', limit: number = 500): Promise<KlineData[]> {
    try {
      const response = await fetch(`${BASE_URL}/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      return await response.json()
    } catch (error) {
      console.error('Failed to fetch klines:', error)
      throw error
    }
  }
}

export interface KlineData {
  openTime: number
  open: string
  high: string
  low: string
  close: string
  volume: string
  closeTime: number
  quoteAssetVolume: string
  numberOfTrades: number
  takerBuyBaseAssetVolume: string
  takerBuyQuoteAssetVolume: string
}

export const apiService = new ApiService()
