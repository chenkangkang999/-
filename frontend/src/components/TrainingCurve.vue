<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from "vue";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);
const props = defineProps<{ series: Array<{ name: string; points: Array<[number, number]> }> }>();
const element = ref<HTMLElement>();
let chart: echarts.ECharts | undefined;
let observer: ResizeObserver | undefined;
function draw() {
  chart?.setOption({ color: ["#6e9d8e", "#c3a368"], tooltip: { trigger: "axis" }, legend: { top: 0 },
    grid: { left: 58, right: 20, top: 38, bottom: 35 },
    xAxis: { type: "value", name: "步数", minInterval: 1, axisLine: { lineStyle: { color: "#b5c7bc" } } },
    yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: "#e8eee6", type: "dashed" } } },
    series: props.series.map(item => ({ name: item.name, type: "line", data: item.points, smooth: false, connectNulls: false, showSymbol: item.points.length < 20 })),
  }, true);
}
onMounted(() => { if (element.value) { chart = echarts.init(element.value); draw(); observer = new ResizeObserver(() => chart?.resize()); observer.observe(element.value); } });
watch(() => props.series, draw, { deep: true });
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); });
</script>
<template><div ref="element" class="training-curve" role="img" :aria-label="series.map(item => `${item.name}：${item.points.length} 个真实记录点`).join('；')"></div></template>
