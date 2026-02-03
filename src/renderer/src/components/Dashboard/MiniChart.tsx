// src/components/Dashboard/MiniChart.tsx
import { useEffect, useRef } from 'react';
import { createChart, ColorType, AreaSeries, Time } from 'lightweight-charts';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

interface ChartData {
  time: string | Time;
  value: number;
}

interface MiniChartProps {
  symbol: string;
  data: ChartData[];
  isUp: boolean;
}

export const MiniChart = ({ symbol, data, isUp }: MiniChartProps) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const color = isUp ? '#0ECB81' : '#F6465D';

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: 'transparent' },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      width: chartContainerRef.current.clientWidth,
      height: 90,
      rightPriceScale: { visible: false },
      timeScale: { visible: false, borderVisible: false },
      handleScroll: false,
      handleScale: false,
      crosshair: { vertLine: { visible: false }, horzLine: { visible: false } },
    });

    const series = chart.addSeries(AreaSeries, {
      lineColor: color,
      topColor: isUp ? 'rgba(14, 203, 129, 0.15)' : 'rgba(246, 70, 93, 0.15)',
      bottomColor: 'rgba(0, 0, 0, 0)',
      lineWidth: 2,
      crosshairMarkerVisible: false,
      lineType: 2, // Curved line
    });

    series.setData(data);
    chart.timeScale().fitContent();

    const handleResize = () => chart.applyOptions({ width: chartContainerRef.current?.clientWidth });
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data, isUp]);

  return (
    <div className="relative w-full h-[140px] bg-[#161A1E] border border-[#2B3139] hover:border-[#474D57] rounded-lg overflow-hidden transition-all duration-300 group shadow-lg hover:shadow-[0_0_15px_rgba(0,0,0,0.3)]">
      {/* Glow Effect on Hover */}
      <div className={`absolute top-0 left-0 w-full h-1 bg-gradient-to-r ${isUp ? 'from-transparent via-[#0ECB81] to-transparent' : 'from-transparent via-[#F6465D] to-transparent'} opacity-0 group-hover:opacity-100 transition-opacity duration-500`} />

      <div className="relative z-10 p-4 flex flex-col justify-between h-full">
        {/* Header: Symbol & Badge */}
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-2">
            <h3 className="text-[#EAECEF] font-bold text-lg tracking-wide">{symbol}</h3>
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#2B3139] text-[#848E9C] border border-[#363C45]">PERP</span>
          </div>
          {/* Change Pill */}
          <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${isUp ? 'bg-[#0ECB81]/10 text-[#0ECB81]' : 'bg-[#F6465D]/10 text-[#F6465D]'}`}>
            {isUp ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
            <span>{isUp ? '2.45%' : '1.20%'}</span>
          </div>
        </div>

        {/* Price Section */}
        <div className="mt-1">
           <p className={`text-2xl font-mono font-medium tracking-tight ${isUp ? 'text-[#EAECEF]' : 'text-[#EAECEF]'} group-hover:text-white transition-colors`}>
             {isUp ? '32,450.00' : '1,200.50'}
           </p>
           <p className="text-[#848E9C] text-[10px] font-mono mt-0.5">Vol: 1.2B</p>
        </div>
      </div>
      
      {/* Chart Background */}
      <div ref={chartContainerRef} className="absolute bottom-0 left-0 right-0 h-[90px] w-full opacity-60 group-hover:opacity-90 transition-opacity duration-300 pointer-events-none mix-blend-lighten" />
    </div>
  );
};
