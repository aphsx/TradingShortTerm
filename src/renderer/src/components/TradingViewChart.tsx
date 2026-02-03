// src/components/TradingViewChart.tsx
const TradingViewChart = ({ symbol }: { symbol: string }) => {
  return (
    <div className="w-full h-full bg-[#161A1E] flex items-center justify-center text-[#848E9C]">
      <div className="text-center">
        <h3 className="text-xl font-bold mb-2">TradingView Chart</h3>
        <p>Symbol: {symbol}</p>
        <p className="text-sm mt-2">Chart placeholder component</p>
      </div>
    </div>
  );
};

export default TradingViewChart;
