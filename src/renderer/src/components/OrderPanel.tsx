import { useState } from 'react'
import { apiService, OrderRequest } from '../services/api'
import { useTradingStore } from '../store/trading'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'
import { Alert, AlertDescription } from './ui/alert'
import { Badge } from './ui/badge'
import { ArrowUpRight, ArrowDownLeft, AlertCircle, CheckCircle, AlertTriangle } from 'lucide-react'

export function OrderPanel() {
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY')
  const [quantity, setQuantity] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const currentPrice = useTradingStore((state) => state.currentPrice)

  const handlePlaceOrder = async (): Promise<void> => {
    if (!quantity || parseFloat(quantity) <= 0) {
      setMessage({ type: 'error', text: 'Please enter a valid quantity' })
      return
    }

    if (!currentPrice) {
      setMessage({ type: 'error', text: 'Waiting for price data...' })
      return
    }

    setLoading(true)
    setMessage(null)

    try {
      const order: OrderRequest = {
        symbol: currentPrice.symbol,
        side,
        quantity,
        type: 'MARKET'
      }

      const response = await apiService.placeOrder(order)
      setMessage({
        type: 'success',
        text: `Order placed successfully! Order ID: ${response.orderId || 'N/A'}`
      })
      setQuantity('')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error'
      setMessage({
        type: 'error',
        text: `Failed to place order: ${errorMsg}`
      })
    } finally {
      setLoading(false)
    }
  }

  const total = quantity && currentPrice 
    ? (parseFloat(quantity) * parseFloat(currentPrice.price)).toFixed(2)
    : '0.00'

  return (
    <Card className="w-full border-amber-900/30 bg-gradient-to-b from-slate-900 to-slate-950">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg text-white">Place Order</CardTitle>
            <CardDescription className="text-slate-400">
              {currentPrice?.symbol || 'BTCUSDT'} Market Order
            </CardDescription>
          </div>
          <Badge variant="outline" className="bg-amber-500/10 text-amber-400 border-amber-500/20">
            Testnet
          </Badge>
        </div>
      </CardHeader>
      
      <CardContent className="space-y-5">
        {/* Buy/Sell Toggle */}
        <div className="space-y-2">
          <Label className="text-xs text-slate-400">Order Type</Label>
          <div className="grid grid-cols-2 gap-3">
            <Button
              onClick={() => setSide('BUY')}
              disabled={loading}
              variant={side === 'BUY' ? 'default' : 'outline'}
              className={`h-12 font-semibold transition-all ${
                side === 'BUY'
                  ? 'bg-green-600 hover:bg-green-700 text-white border-green-500'
                  : 'border-slate-700 text-slate-300 hover:bg-slate-800'
              }`}
            >
              <ArrowUpRight className="mr-2 h-4 w-4" />
              BUY
            </Button>
            <Button
              onClick={() => setSide('SELL')}
              disabled={loading}
              variant={side === 'SELL' ? 'default' : 'outline'}
              className={`h-12 font-semibold transition-all ${
                side === 'SELL'
                  ? 'bg-red-600 hover:bg-red-700 text-white border-red-500'
                  : 'border-slate-700 text-slate-300 hover:bg-slate-800'
              }`}
            >
              <ArrowDownLeft className="mr-2 h-4 w-4" />
              SELL
            </Button>
          </div>
        </div>

        {/* Quantity Input */}
        <div className="space-y-2">
          <Label htmlFor="quantity" className="text-xs text-slate-400">
            Quantity ({currentPrice?.symbol.replace('USDT', '') || 'BTC'})
          </Label>
          <Input
            id="quantity"
            type="number"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="0.001"
            step="0.001"
            min="0"
            disabled={loading}
            className="bg-slate-900 border-slate-700 text-white placeholder:text-slate-600 focus:border-amber-500 focus:ring-amber-500/20"
          />
        </div>

        {/* Current Price & Total */}
        {currentPrice && (
          <div className="space-y-3 rounded-lg bg-slate-900/50 p-4 border border-slate-800">
            <div className="flex justify-between text-sm">
              <span className="text-slate-400">Current Price</span>
              <span className="font-mono text-amber-400 font-semibold">
                ${parseFloat(currentPrice.price).toFixed(2)}
              </span>
            </div>
            {quantity && parseFloat(quantity) > 0 && (
              <div className="flex justify-between text-sm border-t border-slate-700 pt-3">
                <span className="text-slate-400">Total Order Value</span>
                <span className="font-mono text-white font-semibold">
                  ${total} USDT
                </span>
              </div>
            )}
          </div>
        )}

        {/* Place Order Button */}
        <Button
          onClick={handlePlaceOrder}
          disabled={loading || !currentPrice}
          className={`w-full h-12 font-semibold text-base transition-all ${
            side === 'BUY'
              ? 'bg-green-600 hover:bg-green-700 disabled:bg-green-900/50'
              : 'bg-red-600 hover:bg-red-700 disabled:bg-red-900/50'
          }`}
        >
          {loading ? (
            <>
              <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full mr-2" />
              Placing Order...
            </>
          ) : (
            <>
              {side === 'BUY' ? <ArrowUpRight className="mr-2 h-5 w-5" /> : <ArrowDownLeft className="mr-2 h-5 w-5" />}
              {side === 'BUY' ? 'Buy' : 'Sell'} {currentPrice?.symbol || 'BTCUSDT'}
            </>
          )}
        </Button>

        {/* Messages */}
        {message && (
          <Alert className={`border-l-4 ${
            message.type === 'success'
              ? 'border-l-green-500 bg-green-950/30 border border-green-900/50'
              : 'border-l-red-500 bg-red-950/30 border border-red-900/50'
          }`}>
            {message.type === 'success' ? (
              <CheckCircle className="h-4 w-4 text-green-400 mr-2" />
            ) : (
              <AlertCircle className="h-4 w-4 text-red-400 mr-2" />
            )}
            <AlertDescription className={message.type === 'success' ? 'text-green-300' : 'text-red-300'}>
              {message.text}
            </AlertDescription>
          </Alert>
        )}

        <Alert className="border-amber-500/30 bg-amber-500/10">
          <AlertTriangle className="h-4 w-4 text-amber-400" />
          <AlertDescription className="text-amber-300 text-xs">
            <strong>⚠️ Testnet Mode</strong> - Using test funds only. Ensure backend is running with valid Binance API credentials.
          </AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  )
}
