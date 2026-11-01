<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { http, errorText } from "@/api/client";
type Field = { id:string;label:string;group:string;type:string;min?:number;max?:number;options?:Array<{value:string;label:string}> };
const props = defineProps<{modelValue:Record<string,unknown>}>();
const emit = defineEmits<{"update:modelValue":[value:Record<string,unknown>]}>();
const fields = ref<Field[]>([]); const note=ref(""); const error=ref("");
const groups = computed(() => [...new Set(fields.value.map(item=>item.group))]);
function update(field:Field,event:Event) { const raw=(event.target as HTMLInputElement).value; const next={...props.modelValue}; if(raw==="") delete next[field.id]; else next[field.id]=field.type==="boolean"?raw==="true":field.type==="number"?Number(raw):raw; emit("update:modelValue",next); }
onMounted(async()=>{try {const {data}=await http.get("/clinical/schema/");fields.value=Array.isArray(data.fields)?data.fields:[];note.value=data.note||"";} catch(err){error.value=errorText(err);}});
</script>
<template>
  <details class="clinical-inputs"><summary>补充已知生命体征、检查与特殊情况（选填）</summary><p class="muted small">{{note || '未测量或不清楚请留空，不会默认填成正常、否或无。'}}</p><p v-if="error" class="error-text">{{error}}</p>
    <fieldset v-for="group in groups" :key="group"><legend>{{group}}</legend><div class="clinical-input-grid"><label v-for="field in fields.filter(item=>item.group===group)" :key="field.id" :for="`clinical-${field.id}`">{{field.label}}
      <input v-if="field.type==='number'" :id="`clinical-${field.id}`" type="number" step="any" :min="field.min" :max="field.max" :value="modelValue[field.id] ?? ''" placeholder="未提供" @input="update(field,$event)" />
      <select v-else :id="`clinical-${field.id}`" :value="modelValue[field.id]==null?'':String(modelValue[field.id])" @change="update(field,$event)"><option value="">未提供 / 不清楚</option><template v-if="field.type==='boolean'"><option value="true">是</option><option value="false">否</option></template><template v-else><option v-for="option in field.options" :key="option.value" :value="option.value">{{option.label}}</option></template></select>
    </label></div></fieldset>
  </details>
</template>
