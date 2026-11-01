<script setup lang="ts">
import { onBeforeUnmount,onMounted,ref } from "vue";
import { http,errorText } from "@/api/client";
import { numberText,learningStatus } from "@/api/learning";
type State={mode:string;status:string;degraded_reason:string;base_model_present:boolean;active_adapter_consumed:boolean;reranker:string;clinical_data:Record<string,{status:string;rows?:number}>;index?:{id:number;status:string;processed_rows:number;total_rows:number|null;documents:number;chunks:number;deduplicated:number;full_corpus:boolean;limited:boolean;error_code:string}|null};
const state=ref<State|null>(null);const error=ref("");const loading=ref(false);let timer:ReturnType<typeof setTimeout>|undefined;let disposed=false;
async function load(){clearTimeout(timer);loading.value=true;try{const{data}=await http.get<State>("/rag/status/");if(!disposed){state.value=data;error.value="";}}catch(err){if(!disposed)error.value=errorText(err);}finally{loading.value=false;if(!disposed&&state.value?.index?.status==="running")timer=setTimeout(load,Number(import.meta.env.VITE_TRAINING_POLL_MS||5000));}}
const labels:Record<string,string>={ddi:"药物相互作用",guidelines:"已审校指南与药品说明书",drug_names:"中文/英文药名映射","nmpa-domestic":"NMPA国产药品","nmpa-import":"NMPA进口药品",news2:"NEWS2评分规则",framingham:"Framingham研究公式"};
const dataStatus:Record<string,string>={connected:"已核验",not_connected:"未接入",stale_requires_sync:"资料或配置已变更，待同步",unverified_model:"模型尚未核验",insufficient_data:"信息不足"};
onMounted(load);onBeforeUnmount(()=>{disposed=true;clearTimeout(timer);});
</script>
<template>
  <section class="card rag-status"><div class="section-title"><div><h2>知识检索与临床数据接入</h2><p class="muted">实际模式、全量索引和已接入数据分别核验。</p></div><el-button size="small" :loading="loading" @click="load">刷新检索状态</el-button></div><el-alert v-if="error" :title="error" type="error" show-icon />
    <template v-if="state"><div class="rag-state-summary"><strong>{{state.mode==='bm25'?'真实 BM25 稀疏检索':state.mode==='milvus'?'BGE + Milvus 混合检索':'检索模式待核验'}}</strong><span class="pill neutral">{{state.status==='connected'?'已有可用索引':'尚未接通'}}</span></div><p class="learning-note">{{state.degraded_reason||'向量模型和索引版本必须匹配；未匹配时阻止使用旧索引。'}}</p>
      <div v-if="state.index" class="rag-index-progress"><h3>索引任务 #{{state.index.id}} · {{learningStatus(state.index.status==='succeeded'?'completed':state.index.status)}}</h3><p>已处理 {{numberText(state.index.processed_rows)}} / {{numberText(state.index.total_rows)}} 行 · {{state.index.full_corpus?'配置语料已全量处理':state.index.limited?'限量运行，不能称全库完成':'以实际任务状态为准'}}</p><el-progress v-if="state.index.total_rows" :percentage="Math.min(100,state.index.processed_rows/state.index.total_rows*100)" :show-text="false" /><div class="rag-index-counts"><span>索引文档 <strong>{{numberText(state.index.documents)}}</strong></span><span>索引切片 <strong>{{numberText(state.index.chunks)}}</strong></span><span>去重跳过 <strong>{{numberText(state.index.deduplicated)}}</strong></span></div><p v-if="state.index.error_code" class="error-text">{{state.index.error_code}}</p></div><p v-else class="learning-note">尚未运行知识索引；不会把训练集行数当作已入库知识数量。</p>
      <p class="learning-note">基座文件：{{state.base_model_present?'已找到，实际加载另行验证':'尚未提供完整基座'}} · 活动 adapter：{{state.active_adapter_consumed?'已由当前向量索引模式消费':'尚未被当前检索模式使用'}} · 重排：{{state.reranker==='none'?'未启用':state.reranker}}</p><div class="clinical-data-grid"><div v-for="(data,key) in state.clinical_data" :key="key"><span>{{labels[key]||key}}</span><strong>{{dataStatus[data.status]||'状态待核对'}}</strong><small v-if="data.status==='connected'&&data.rows!=null">{{numberText(data.rows)}} 条来源记录</small></div></div><p class="learning-note">社区问答不是个体用药推荐的临床指南；药物表未接入不等于“没有相互作用”。</p>
    </template>
  </section>
</template>
