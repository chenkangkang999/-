<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);
const props = defineProps<{
  labels: string[];
  values: number[];
  unit?: string;
}>();
const element = ref<HTMLElement>();
let chart: echarts.ECharts | undefined;
let observer: ResizeObserver | undefined;
function draw() {
  const styles = element.value ? getComputedStyle(element.value) : undefined;
  const theme = (name: string) => styles?.getPropertyValue(name).trim() || undefined;
  const barColor = theme("--chart-bar");
  chart?.setOption({
    color: barColor ? [barColor] : undefined,
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: unknown) => `${value}${props.unit || ""}`,
    },
    grid: { top: 20, bottom: 35, left: 48, right: 15 },
    xAxis: {
      type: "category",
      data: props.labels,
      axisLine: { lineStyle: { color: theme("--chart-axis") } },
      axisLabel: { color: theme("--chart-label"), fontSize: 12 },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      splitLine: { lineStyle: { color: theme("--chart-grid"), type: "dashed" } },
      axisLabel: { color: theme("--chart-label"), fontSize: 12 },
    },
    series: [
      {
        type: "bar",
        data: props.values,
        barMaxWidth: 35,
        itemStyle: { borderRadius: [5, 5, 0, 0] },
      },
    ],
  });
}
onMounted(() => {
  if (element.value) {
    chart = echarts.init(element.value);
    draw();
    observer = new ResizeObserver(() => chart?.resize());
    observer.observe(element.value);
  }
});
watch(() => [props.labels, props.values], draw, { deep: true });
onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>
<template>
  <div
    ref="element"
    class="metric-chart"
    role="img"
    :aria-label="
      labels
        .map((name, index) => `${name}: ${values[index]}${unit || ''}`)
        .join('，')
    "
  ></div>
</template>
