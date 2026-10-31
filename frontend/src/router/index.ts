import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('@/views/HomeView.vue') },
    {
      path: '/consultation',
      name: 'consultation',
      component: () => import('@/views/ConsultationView.vue'),
    },
    { path: '/agents', name: 'agents', component: () => import('@/views/AgentsView.vue') },
    {
      path: '/monitoring',
      name: 'monitoring',
      component: () => import('@/views/MonitoringView.vue'),
    },
    { path: '/billing', name: 'billing', component: () => import('@/views/BillingView.vue') },
  ],
})

export default router