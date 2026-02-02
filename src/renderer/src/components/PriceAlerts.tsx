import { useState } from 'react'
import { useTradingStore } from '../store/useTradingStore'
import { Bell, Plus, X, TrendingUp, TrendingDown } from 'lucide-react'

interface PriceAlert {
  id: string
  symbol: string
  targetPrice: number
  direction: 'above' | 'below'
  enabled: boolean
}

export default function PriceAlerts() {
  const { symbol, currentPrice } = useTradingStore()
  const [alerts, setAlerts] = useState<PriceAlert[]>([])
  const [showAlertModal, setShowAlertModal] = useState(false)
  const [newAlert, setNewAlert] = useState({
    targetPrice: '',
    direction: 'above' as 'above' | 'below'
  })

  const addAlert = () => {
    if (!newAlert.targetPrice) return

    const alert: PriceAlert = {
      id: Date.now().toString(),
      symbol,
      targetPrice: parseFloat(newAlert.targetPrice),
      direction: newAlert.direction,
      enabled: true
    }

    setAlerts([...alerts, alert])
    setNewAlert({ targetPrice: '', direction: 'above' })
    setShowAlertModal(false)
  }

  const removeAlert = (id: string) => {
    setAlerts(alerts.filter(alert => alert.id !== id))
  }

  const toggleAlert = (id: string) => {
    setAlerts(alerts.map(alert => 
      alert.id === id ? { ...alert, enabled: !alert.enabled } : alert
    ))
  }

  // Check alerts (in real app, this would be handled by backend)
  const checkAlerts = () => {
    alerts.forEach(alert => {
      if (!alert.enabled) return
      
      const triggered = alert.direction === 'above' 
        ? currentPrice >= alert.targetPrice
        : currentPrice <= alert.targetPrice
      
      if (triggered) {
        // Show notification
        console.log(`🔔 Price Alert: ${symbol} is ${alert.direction} ${alert.targetPrice}`)
        // In real app, show browser notification
      }
    })
  }

  return (
    <div className="relative">
      <button
        onClick={() => setShowAlertModal(!showAlertModal)}
        className="p-2 hover:bg-[#2B2B43] rounded transition-colors relative"
        title="Price Alerts"
      >
        <Bell className="w-4 h-4 text-gray-400" />
        {alerts.length > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-[#2962FF] text-white text-xs rounded-full flex items-center justify-center">
            {alerts.length}
          </span>
        )}
      </button>

      {showAlertModal && (
        <div className="absolute top-full right-0 mt-2 w-80 bg-[#1E222D] border border-[#2B2B43] rounded-lg shadow-xl z-50">
          <div className="p-4 border-b border-[#2B2B43]">
            <div className="flex items-center justify-between">
              <h3 className="text-white font-semibold">Price Alerts</h3>
              <button
                onClick={() => setShowAlertModal(false)}
                className="text-gray-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="p-4">
            {/* Add New Alert */}
            <div className="mb-4">
              <div className="flex gap-2 mb-2">
                <input
                  type="number"
                  value={newAlert.targetPrice}
                  onChange={(e) => setNewAlert({ ...newAlert, targetPrice: e.target.value })}
                  placeholder="Target Price"
                  className="flex-1 bg-[#131722] text-white text-sm px-3 py-2 rounded border border-[#2B2B43] focus:outline-none focus:border-[#2962FF]"
                />
                <select
                  value={newAlert.direction}
                  onChange={(e) => setNewAlert({ ...newAlert, direction: e.target.value as 'above' | 'below' })}
                  className="bg-[#131722] text-white text-sm px-3 py-2 rounded border border-[#2B2B43] focus:outline-none focus:border-[#2962FF]"
                >
                  <option value="above">Above</option>
                  <option value="below">Below</option>
                </select>
                <button
                  onClick={addAlert}
                  className="p-2 bg-[#2962FF] text-white rounded hover:bg-[#1E4BC6] transition-colors"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Existing Alerts */}
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {alerts.length === 0 ? (
                <p className="text-gray-400 text-sm text-center py-4">
                  No price alerts set
                </p>
              ) : (
                alerts.map(alert => (
                  <div
                    key={alert.id}
                    className={`flex items-center justify-between p-2 rounded border ${
                      alert.enabled 
                        ? 'border-[#2B2B43] bg-[#131722]' 
                        : 'border-gray-700 bg-gray-800 opacity-50'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleAlert(alert.id)}
                        className={`w-4 h-4 rounded-full border-2 ${
                          alert.enabled 
                            ? 'bg-[#2962FF] border-[#2962FF]' 
                            : 'border-gray-600'
                        }`}
                      />
                      <div className="flex items-center gap-1">
                        {alert.direction === 'above' ? (
                          <TrendingUp className="w-3 h-3 text-[#26a69a]" />
                        ) : (
                          <TrendingDown className="w-3 h-3 text-[#ef5350]" />
                        )}
                        <span className="text-white text-sm">
                          ${alert.targetPrice.toFixed(2)}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => removeAlert(alert.id)}
                      className="text-gray-400 hover:text-red-400 transition-colors"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
