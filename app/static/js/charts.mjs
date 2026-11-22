const COLORS = [
  "#2563eb",
  "#16a34a",
  "#d97706",
  "#7c3aed",
  "#0891b2",
  "#db2777",
  "#4f46e5",
  "#65a30d",
];

function shortLabel(value) {
  const text = String(value ?? "");
  return text.length > 12 ? `${text.slice(0, 12)}…` : text;
}

export function buildBarLineOption(spec, type) {
  const isLine = type === "line";
  const manyCategories = (spec.x_data || []).length > 6;
  const option = {
    color: COLORS,
    grid: { left: 12, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      trigger: isLine ? "axis" : "axis",
      confine: true,
    },
    legend: {
      show: (spec.series || []).length > 1,
      top: 0,
      type: "scroll",
    },
    xAxis: {
      type: "category",
      data: (spec.x_data || []).map((value) => shortLabel(value)),
      axisLabel: {
        rotate: manyCategories ? 30 : 0,
        hideOverlap: true,
      },
    },
    yAxis: {
      type: "value",
    },
    series: (spec.series || []).map((series) => ({
      name: series.name,
      type: isLine ? "line" : "bar",
      data: series.data,
      smooth: isLine,
      emphasis: { focus: "series" },
    })),
  };
  return option;
}

export function buildPieOption(spec) {
  return {
    color: COLORS,
    tooltip: { trigger: "item", confine: true },
    legend: {
      top: 0,
      type: "scroll",
    },
    series: [
      {
        name: spec.title,
        type: "pie",
        radius: ["42%", "70%"],
        center: ["50%", "56%"],
        data: (spec.data || []).map((item) => ({
          name: String(item.name),
          value: item.value,
        })),
        label: { formatter: "{b}: {d}%" },
        emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: "rgba(0,0,0,0.3)" } },
      },
    ],
  };
}

export function buildChartOption(spec) {
  if (!spec) return null;
  if (spec.type === "pie") return buildPieOption(spec);
  if (spec.type === "bar") return buildBarLineOption(spec, "bar");
  if (spec.type === "line") return buildBarLineOption(spec, "line");
  return null;
}

export function initChart(container, spec) {
  const echarts = globalThis.echarts;
  if (!echarts || !container) return null;
  const option = buildChartOption(spec);
  if (!option) return null;
  const chart = echarts.init(container);
  chart.setOption(option);
  return chart;
}

export function disposeChart(chart) {
  if (chart && typeof chart.dispose === "function") chart.dispose();
}
