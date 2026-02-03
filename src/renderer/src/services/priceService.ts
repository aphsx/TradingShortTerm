import { useMultiAssetStore } from '../store/useMultiAssetStore'

// Popular trading symbols for multi-asset trading
const POPULAR_SYMBOLS = [
  'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT',
  'XRPUSDT', 'DOTUSDT', 'DOGEUSDT', 'MATICUSDT', 'PAXGUSDT',
  'BTCETH', 'ETHBNB', 'BTCBUSD', 'ETHBUSD', 'USDCUSDT'
]

export class PriceService {
  private static instance: PriceService
  private updateInterval: NodeJS.Timeout | null = null
  private readonly UPDATE_INTERVAL = 5000 // 5 seconds

  static getInstance(): PriceService {
    if (!PriceService.instance) {
      PriceService.instance = new PriceService()
    }
    return PriceService.instance
  }

  startPriceUpdates() {
    if (this.updateInterval) {
      return
    }

    console.log('🔄 Starting multi-asset price updates...')
    
    // Initial fetch
    this.fetchAllPrices()
    
    // Set up periodic updates
    this.updateInterval = setInterval(() => {
      this.fetchAllPrices()
    }, this.UPDATE_INTERVAL)
  }

  stopPriceUpdates() {
    if (this.updateInterval) {
      clearInterval(this.updateInterval)
      this.updateInterval = null
      console.log('⏹️ Stopped price updates')
    }
  }

  private async fetchAllPrices() {
    try {
      // Fetch all symbol prices
      const pricesResponse = await fetch('http://localhost:8080/api/prices')
      if (!pricesResponse.ok) {
        throw new Error('Failed to fetch prices')
      }
      
      const pricesData = await pricesResponse.json()
      const prices = pricesData.prices || []

      // Fetch 24hr ticker data
      const tickerResponse = await fetch('http://localhost:8080/api/ticker/24hr')
      let tickerData: any[] = []
      
      if (tickerResponse.ok) {
        const tickerResult = await tickerResponse.json()
        tickerData = tickerResult.tickers || []
      }

      // Update store with price data
      const { setPrices } = useMultiAssetStore.getState()
      const updatedPrices: Record<string, any> = {}

      // Process all prices
      prices.forEach((price: any) => {
        const ticker = tickerData.find((t: any) => t.symbol === price.symbol)
        
        updatedPrices[price.symbol] = {
          symbol: price.symbol,
          price: parseFloat(price.price),
          change24h: ticker?.change24h || 0,
          high24h: parseFloat(ticker?.high24h || price.price),
          low24h: parseFloat(ticker?.low24h || price.price),
          volume24h: parseFloat(ticker?.volume24h || '0'),
          lastUpdate: Date.now()
        }
      })

      setPrices(updatedPrices)
      
      console.log(`📊 Updated ${Object.keys(updatedPrices).length} prices`)
    } catch (error) {
      console.error('❌ Failed to fetch prices:', error)
    }
  }

  async fetchSinglePrice(symbol: string) {
    try {
      const response = await fetch(`http://localhost:8080/api/ticker/24hr?symbols=${symbol}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch price for ${symbol}`)
      }
      
      const data = await response.json()
      const ticker = data.tickers?.[0]
      
      if (ticker) {
        const { updatePrice } = useMultiAssetStore.getState()
        updatePrice(symbol, {
          price: parseFloat(ticker.price),
          change24h: ticker.change24h || 0,
          high24h: parseFloat(ticker.high24h || ticker.price),
          low24h: parseFloat(ticker.low24h || ticker.price),
          volume24h: parseFloat(ticker.volume24h || '0')
        })
        
        return ticker
      }
    } catch (error) {
      console.error(`❌ Failed to fetch price for ${symbol}:`, error)
    }
    
    return null
  }

  getPopularSymbols(): string[] {
    return POPULAR_SYMBOLS
  }

  isSymbolSupported(symbol: string): boolean {
    return POPULAR_SYMBOLS.includes(symbol)
  }
}

// Export singleton instance
export const priceService = PriceService.getInstance()
