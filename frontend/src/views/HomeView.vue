<script setup lang="ts">
const stages = [
  { name: '问诊', desc: '结构化主诉、红旗征识别' },
  { name: '检索', desc: '混合检索 + 引用溯源' },
  { name: '风险 / 用药', desc: '并行评估，互不阻塞' },
  { name: '辩论', desc: '分歧收敛（LangGraph）' },
  { name: '白话解释', desc: 'SOAP + 通俗说明' },
  { name: '安全护栏', desc: '合规拦截与免责声明' },
]
</script>

<template>
  <section>
    <h1>从「会答」到「敢答、可查、可审」</h1>
    <p class="muted">
      协调器按固定顺序调度 7 个专职 Agent；检索只提供证据，最终以安全侧结论为准。
    </p>

    <div class="grid grid-3" style="margin-top: 24px">
      <article v-for="(stage, index) in stages" :key="stage.name" class="card">
        <div class="muted">STEP {{ String(index + 1).padStart(2, '0') }}</div>
        <h2>{{ stage.name }}</h2>
        <p class="muted">{{ stage.desc }}</p>
      </article>
    </div>

    <div class="card" style="margin-top: 24px">
      <h2>开始体验</h2>
      <p class="muted">进入问诊页输入症状，可看到每个 Agent 的中间步骤与引用证据。</p>
      <RouterLink to="/consultation"><el-button type="primary">去问诊</el-button></RouterLink>
    </div>
  </section>
</template>