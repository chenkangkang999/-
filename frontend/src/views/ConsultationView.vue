<script setup lang="ts">
import { ref } from 'vue'

import { http } from '@/api/client'

interface Message {
  id: number
  role: string
  content: string
  agent_name: string
  citations: Array<{ title: string; snippet: string; source: string }>
}

const consultationId = ref<number | null>(null)
const input = ref('')
const messages = ref<Message[]>([])
const steps = ref<Array<{ agent: string; latency_ms: number }>>([])
const busy = ref(false)
const error = ref('')

async function ensureConsultation(): Promise<number> {
  if (consultationId.value) return consultationId.value
  const { data } = await http.post('/consultations/', { title: input.value.slice(0, 40) })
  consultationId.value = data.id
  return data.id
}

async function send() {
  if (!input.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const id = await ensureConsultation()
    const content = input.value
    input.value = ''
    const { data } = await http.post(`/consultations/${id}/messages/`, { content })
    messages.value.push(data.message, data.reply)
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section>
    <h1>问诊</h1>
    <p class="muted">输入症状与持续时间；系统会展示每条回答引用的证据。</p>

    <div class="card" style="margin: 16px 0">
      <el-input
        v-model="input"
        type="textarea"
        :rows="3"
        placeholder="例如：咳嗽三天，夜间加重，无发热"
      />
      <div style="margin-top: 12px; display: flex; gap: 12px; align-items: center">
        <el-button type="primary" :loading="busy" @click="send">发送</el-button>
        <span class="muted">会话 ID：{{ consultationId ?? '未创建' }}</span>
      </div>
      <el-alert v-if="error" :title="error" type="error" style="margin-top: 12px" />
    </div>

    <article v-for="message in messages" :key="message.id" class="card" style="margin-bottom: 12px">
      <div class="muted">
        {{ message.role === 'user' ? '你' : message.agent_name || '助手' }}
      </div>
      <pre style="white-space: pre-wrap; font-family: inherit">{{ message.content }}</pre>
      <div v-if="message.citations.length" class="muted">
        引用：{{ message.citations.map((item) => item.title).join('；') }}
      </div>
    </article>

    <div v-if="steps.length" class="card">
      <h2>Agent 步骤</h2>
      <div v-for="step in steps" :key="step.agent" class="muted">
        {{ step.agent }} · {{ step.latency_ms }}ms
      </div>
    </div>
  </section>
</template>