/** Candlestick chart (TradingView lightweight-charts v5) with EMA/Bollinger
 * overlays, volume histogram, and entry/stop/target price lines. */
import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";

import type { Candle, ScannerRow } from "../api/types";

const INK = {
  text: "#93a5b8",
  grid: "rgba(42, 54, 68, 0.5)",
  up: "#38e07d",
  down: "#f4564e",
  ema20: "#3dc9f5",
  ema50: "#f5b83d",
  ema200: "#9d7bf5",
  bb: "rgba(147, 165, 184, 0.35)",
};

function toTime(ts: string): UTCTimestamp {
  return Math.floor(new Date(ts).getTime() / 1000) as UTCTimestamp;
}

export default function ChartPanel({
  candles, row, height = 420, compact = false,
}: {
  candles: Candle[]; row: ScannerRow | null; height?: number; compact?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || candles.length === 0) return;

    const chart = createChart(el, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: INK.text,
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: INK.grid },
        horzLines: { color: INK.grid },
      },
      rightPriceScale: { borderColor: "rgba(42,54,68,0.8)" },
      timeScale: { borderColor: "rgba(42,54,68,0.8)", timeVisible: false },
      crosshair: {
        horzLine: { labelBackgroundColor: "#1c2530" },
        vertLine: { labelBackgroundColor: "#1c2530" },
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: INK.up,
      downColor: INK.down,
      wickUpColor: INK.up,
      wickDownColor: INK.down,
      borderVisible: false,
    });
    candleSeries.setData(
      candles.map((c) => ({
        time: toTime(c.ts), open: c.open, high: c.high, low: c.low, close: c.close,
      })),
    );

    if (!compact) {
      const volume = chart.addSeries(HistogramSeries, {
        priceScaleId: "vol",
        priceFormat: { type: "volume" },
        color: "rgba(70, 86, 106, 0.6)",
      });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      volume.setData(
        candles.map((c) => ({
          time: toTime(c.ts),
          value: c.volume,
          color: c.close >= c.open ? "rgba(56,224,125,0.35)" : "rgba(244,86,78,0.35)",
        })),
      );
    }

    const addLine = (key: "ema20" | "ema50" | "ema200", color: string, width: 1 | 2) => {
      const data = candles
        .filter((c) => c[key] !== null)
        .map((c) => ({ time: toTime(c.ts), value: c[key] as number }));
      if (!data.length) return;
      chart
        .addSeries(LineSeries, {
          color, lineWidth: width, priceLineVisible: false, lastValueVisible: false,
          crosshairMarkerVisible: false,
        })
        .setData(data);
    };
    addLine("ema20", INK.ema20, 1);
    addLine("ema50", INK.ema50, 1);
    addLine("ema200", INK.ema200, 2);

    for (const key of ["bb_upper", "bb_lower"] as const) {
      const data = candles
        .filter((c) => c[key] !== null)
        .map((c) => ({ time: toTime(c.ts), value: c[key] as number }));
      if (data.length) {
        chart
          .addSeries(LineSeries, {
            color: INK.bb, lineWidth: 1, lineStyle: LineStyle.Dotted,
            priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
          })
          .setData(data);
      }
    }

    const priceLine = (price: number | null, color: string, title: string) => {
      if (price === null) return;
      candleSeries.createPriceLine({
        price, color, lineWidth: 1, lineStyle: LineStyle.Dashed, title,
        axisLabelVisible: true,
      });
    };
    if (!compact) {
      priceLine(row?.entry ?? null, INK.ema20, "ENTRY");
      priceLine(row?.stop ?? null, INK.down, "STOP");
      priceLine(row?.target ?? null, INK.up, "TARGET");
    }

    chart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, candles.length - 130), to: candles.length + 3,
    });

    const observer = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, [candles, row, height, compact]);

  return (
    <div>
      <div ref={ref} className="w-full" />
      {!compact && (
        <div className="mt-2 flex flex-wrap gap-4 px-1 text-[11px] text-[var(--color-ink-300)]">
          <span><span style={{ color: INK.ema20 }}>—</span> EMA 20</span>
          <span><span style={{ color: INK.ema50 }}>—</span> EMA 50</span>
          <span><span style={{ color: INK.ema200 }}>—</span> EMA 200</span>
          <span><span style={{ color: INK.bb }}>┄</span> Bollinger 20,2</span>
        </div>
      )}
    </div>
  );
}
