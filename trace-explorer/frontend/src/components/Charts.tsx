import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatShortTime } from "../format";

export const PALETTE = [
  "#5b8def",
  "#ef8354",
  "#a78bfa",
  "#3ddc97",
  "#f25c54",
  "#ffd369",
  "#4cc9f0",
  "#f72585",
];

const GRID_STROKE = "#232936";
const AXIS_COLOR = "#8b93a7";
const TOOLTIP_STYLE = {
  background: "#171c28",
  border: "1px solid #232936",
  fontSize: 12,
  borderRadius: 4,
};

function tooltipFormatter(valueFormatter: (v: number) => string) {
  return (value: unknown) => valueFormatter(Number(value));
}

function toSeriesData(bucketStarts: number[], series: Record<string, number[]>) {
  return bucketStarts.map((time, i) => {
    const row: Record<string, number> = { time };
    for (const [key, values] of Object.entries(series)) row[key] = values[i] ?? 0;
    return row;
  });
}

interface TimeSeriesChartProps {
  bucketStarts: number[];
  series: Record<string, number[]>;
  valueFormatter: (v: number) => string;
  height?: number;
}

export function StackedAreaChart({ bucketStarts, series, valueFormatter, height = 220 }: TimeSeriesChartProps) {
  const keys = Object.keys(series);
  if (keys.length === 0) return <EmptyChart height={height} />;

  const data = toSeriesData(bucketStarts, series);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data}>
        <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="time"
          tickFormatter={formatShortTime}
          stroke={AXIS_COLOR}
          fontSize={11}
          tickLine={false}
          axisLine={{ stroke: GRID_STROKE }}
          minTickGap={50}
        />
        <YAxis
          stroke={AXIS_COLOR}
          fontSize={11}
          tickFormatter={valueFormatter}
          tickLine={false}
          axisLine={false}
          width={56}
        />
        <Tooltip
          labelFormatter={(v) => formatShortTime(Number(v))}
          formatter={tooltipFormatter(valueFormatter)}
          contentStyle={TOOLTIP_STYLE}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {keys.map((key, i) => (
          <Area
            key={key}
            type="monotone"
            dataKey={key}
            name={key}
            stackId="1"
            stroke={PALETTE[i % PALETTE.length]}
            fill={PALETTE[i % PALETTE.length]}
            fillOpacity={0.3}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function StackedBarChart({ bucketStarts, series, valueFormatter, height = 220 }: TimeSeriesChartProps) {
  const keys = Object.keys(series);
  if (keys.length === 0) return <EmptyChart height={height} />;

  const data = toSeriesData(bucketStarts, series);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data}>
        <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="time"
          tickFormatter={formatShortTime}
          stroke={AXIS_COLOR}
          fontSize={11}
          tickLine={false}
          axisLine={{ stroke: GRID_STROKE }}
          minTickGap={50}
        />
        <YAxis
          stroke={AXIS_COLOR}
          fontSize={11}
          tickFormatter={valueFormatter}
          tickLine={false}
          axisLine={false}
          width={40}
          allowDecimals={false}
        />
        <Tooltip
          labelFormatter={(v) => formatShortTime(Number(v))}
          formatter={tooltipFormatter(valueFormatter)}
          contentStyle={TOOLTIP_STYLE}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {keys.map((key, i) => (
          <Bar key={key} dataKey={key} name={key} stackId="1" fill={PALETTE[i % PALETTE.length]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

interface HorizontalBarChartProps {
  data: { label: string; value: number }[];
  valueFormatter: (v: number) => string;
  height?: number;
  colorFn?: (value: number) => string;
}

export function HorizontalBarChart({ data, valueFormatter, height, colorFn }: HorizontalBarChartProps) {
  if (data.length === 0) return <EmptyChart height={height ?? 160} />;

  const chartHeight = height ?? Math.max(120, data.length * 32);
  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" horizontal={false} />
        <XAxis
          type="number"
          tickFormatter={valueFormatter}
          stroke={AXIS_COLOR}
          fontSize={11}
          tickLine={false}
          axisLine={{ stroke: GRID_STROKE }}
        />
        <YAxis
          type="category"
          dataKey="label"
          stroke={AXIS_COLOR}
          fontSize={11}
          width={110}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip formatter={tooltipFormatter(valueFormatter)} contentStyle={TOOLTIP_STYLE} />
        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
          {data.map((d, i) => (
            <Cell key={d.label} fill={colorFn ? colorFn(d.value) : PALETTE[i % PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function EmptyChart({ height }: { height: number }) {
  return (
    <div style={{ height }} className="flex items-center justify-center text-xs text-text-muted">
      No data
    </div>
  );
}
