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
      const response = await fetch(`${BASE_URL}/order`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(order)
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      return data
    } catch (error) {
      console.error('Failed to place order:', error)
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
}

export const apiService = new ApiService()
