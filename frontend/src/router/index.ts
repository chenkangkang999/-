import { createRouter, createWebHistory } from "vue-router";
import { useSessionStore } from "@/stores/session";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { public: true },
    },
    {
      path: "/",
      name: "home",
      component: () => import("@/views/HomeView.vue"),
      meta: { title: "工作台概览", caption: "每一次协作，都有迹可循" },
    },
    {
      path: "/consultation/:id?",
      name: "consultation",
      component: () => import("@/views/ConsultationView.vue"),
      meta: { title: "协作问诊", caption: "从症状描述到证据与就医指引" },
    },
    {
      path: "/agents/:name?",
      name: "agents",
      component: () => import("@/views/AgentsView.vue"),
      meta: { title: "智能体中心", caption: "查看能力、运行记录与独立测试" },
    },
    {
      path: "/monitoring",
      name: "monitoring",
      component: () => import("@/views/MonitoringView.vue"),
      meta: { title: "运行监控", caption: "用真实数据理解系统的每一步" },
    },
    {
      path: "/billing",
      name: "billing",
      component: () => import("@/views/BillingView.vue"),
      meta: { title: "用量与账单", caption: "让模型调用与成本清晰可见" },
    },
    { path: "/training", name: "training", component: () => import("@/views/TrainingView.vue"), meta: { title: "训练与数据" } },
    { path: "/flywheel", name: "flywheel", component: () => import("@/views/FlywheelView.vue"), meta: { title: "数据飞轮" } },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
router.beforeEach(async (to) => {
  const session = useSessionStore();
  if (to.meta.public) return;
  try {
    await session.load();
  } catch {
    return {
      name: "login",
      query: { redirect: to.fullPath, connection: "failed" },
    };
  }
  if (!session.user) return { name: "login", query: { redirect: to.fullPath } };
});
export default router;
