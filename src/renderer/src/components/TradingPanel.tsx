import { useState } from 'react'
import { useTradingStore } from '../store/useTradingStore'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'
import { cn } from '../lib/utils'

type OrderSide = 'BUY' | 'SELL'
type OrderType = 'MARKET' | 'LIMIT'

export default function TradingPanel() {
  const { symbol, ticker } = useTradingStore()
  const [side, setSide] = useState<OrderSide>('BUY')
  const [orderType, setOrderType] = useState<OrderType>('LIMIT')
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')

  const handlePlaceOrder = async () => {
    const order = {
      symbol,
      side,
      type: orderType,
      quantity: parseFloat(quantity),
      price: orderType === 'LIMIT' ? parseFloat(price) : undefined
    }

    try {
      const response = await fetch('http://localhost:8080/api/order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(order)
      })

      if (!response.ok) {
        throw new Error('Failed to place order')
      }

      const result = await response.json()
      console.log('✅ Order placed:', result)
      alert('Order placed successfully!')

      // Reset form
      setQuantity('')
      if (orderType === 'LIMIT') setPrice('')
    } catch (error) {
      console.error('❌ Order failed:', error)
      alert('Failed to place order: ' + (error as Error).message)
    }
  }

  const isBuy = side === 'BUY'
  const currentPrice = ticker?.price || 0

  return (
    <div className="w-80 bg-[#1e222d] border-l border-[#2b2b43] flex flex-col">
      <Card className="m-4 bg-[#131722] border-[#2b2b43]">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Place Order</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Buy/Sell Toggle */}
          <div className="flex space-x-2">
            <Button
              variant={isBuy ? 'success' : 'outline'}
              className={cn('flex-1', isBuy && 'bg-green-600 hover:bg-green-700')}
              onClick={() => setSide('BUY')}
            >
              Buy
            </Button>
            <Button
              variant={!isBuy ? 'destructive' : 'outline'}
              className="flex-1"
              onClick={() => setSide('SELL')}
            >
              Sell
            </Button>
          </div>

          {/* Order Type */}
          <div className="flex space-x-2">
            <Button
              variant={orderType === 'LIMIT' ? 'default' : 'outline'}
              className="flex-1"
              size="sm"
              onClick={() => setOrderType('LIMIT')}
            >
              Limit
            </Button>
            <Button
              variant={orderType === 'MARKET' ? 'default' : 'outline'}
              className="flex-1"
              size="sm"
              onClick={() => setOrderType('MARKET')}
            >
              Market
            </Button>
          </div>

          {/* Price Input (only for LIMIT) */}
          {orderType === 'LIMIT' && (
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Price</label>
              <Input
                type="number"
                placeholder={currentPrice.toString()}
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </div>
          )}

          {/* Quantity Input */}
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Quantity</label>
            <Input
              type="number"
              placeholder="0.00"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </div>

          {/* Market Price Info */}
          {orderType === 'MARKET' && currentPrice > 0 && (
            <div className="text-xs text-gray-400">
              Market Price: <span className="text-white">{currentPrice.toFixed(2)}</span>
            </div>
          )}

          {/* Total */}
          {quantity && (orderType === 'MARKET' || price) && (
            <div className="text-sm">
              <span className="text-gray-400">Total: </span>
              <span className="text-white font-semibold">
                {(
                  parseFloat(quantity) *
                  (orderType === 'MARKET' ? currentPrice : parseFloat(price) || 0)
                ).toFixed(2)}{' '}
                USDT
              </span>
            </div>
          )}

          {/* Place Order Button */}
          <Button
            className={cn('w-full', isBuy ? 'bg-green-600 hover:bg-green-700' : '')}
            variant={isBuy ? 'success' : 'destructive'}
            onClick={handlePlaceOrder}
            disabled={!quantity || (orderType === 'LIMIT' && !price)}
          >
            {side} {symbol}
          </Button>

          {/* Balance Info (Mock) */}
          <div className="pt-4 border-t border-[#2b2b43] text-xs space-y-1">
            <div className="flex justify-between text-gray-400">
              <span>Available:</span>
              <span className="text-white">0.00 USDT</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
