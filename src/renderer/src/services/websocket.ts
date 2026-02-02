import { useTradingStore } from '../store/trading'

class WebSocketService {
  private ws: WebSocket | null = null
  private reconnectTimeout: NodeJS.Timeout | null = null
  private readonly baseUrl = 'ws://localhost:8080/api/price'
  private readonly reconnectDelay = 3000
  private currentSymbol: string = 'BTCUSDT'

  connect(symbol: string = 'BTCUSDT'): void {
    // If switching symbols, close existing connection
    if (this.ws?.readyState === WebSocket.OPEN && this.currentSymbol !== symbol) {
      console.log(`Switching from ${this.currentSymbol} to ${symbol}`)
      this.disconnect()
    }

    if (this.ws?.readyState === WebSocket.OPEN && this.currentSymbol === symbol) {
      console.log('WebSocket already connected to', symbol)
      return
    }

    this.currentSymbol = symbol
    const url = `${this.baseUrl}?symbol=${symbol}`
    console.log('Connecting to WebSocket:', url)
    
    try {
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        console.log('✅ WebSocket connected to', symbol)
        useTradingStore.getState().setConnected(true)
        
        // Clear any pending reconnect
        if (this.reconnectTimeout) {
          clearTimeout(this.reconnectTimeout)
          this.reconnectTimeout = null
        }
      }

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          // Update store with new price
          useTradingStore.getState().setPrice(data)
          useTradingStore.getState().addPriceToHistory(data)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      this.ws.onclose = () => {
        console.log('WebSocket disconnected')
        useTradingStore.getState().setConnected(false)
        this.ws = null
        
        // Attempt to reconnect
        this.scheduleReconnect()
      }
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
      this.scheduleReconnect()
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimeout) {
      return // Already scheduled
    }

    console.log(`Reconnecting in ${this.reconnectDelay}ms...`)
    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null
      this.connect(this.currentSymbol)
    }, this.reconnectDelay)
  }

  disconnect(): void {
    console.log('Disconnecting WebSocket...')
    
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  getCurrentSymbol(): string {
    return this.currentSymbol
  }
}

export const wsService = new WebSocketService()
