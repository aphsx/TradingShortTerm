// src/App.tsx
import React from 'react'
import BinanceAccountPanel from './components/BinanceAccountPanel'
import DailyPerformanceCalendar from './components/DailyPerformanceCalendar'

function App(): React.ReactElement {
  return (
    <div className="min-h-screen bg-[#0B0E11] text-[#EAECEF] font-sans">
      <div className="container mx-auto p-6">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-[#EAECEF] mb-2">Trading Dashboard</h1>
          <p className="text-[#848E9C]">Your daily performance overview and trading analytics</p>
        </div>
        <BinanceAccountPanel />
        <DailyPerformanceCalendar />
      </div>
    </div>
  )
}

export default App
