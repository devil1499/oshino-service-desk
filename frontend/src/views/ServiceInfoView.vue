<script setup lang="ts">
import { watch, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { serviceProducts } from '../api/service'
const route = useRoute()
const auth = useAuthStore()
const products = ref<{ id: number; name: string }[]>([])
const error = ref('')
watch(
  () => route.path,
  async () => {
    error.value = ''
    try {
      if (route.path.endsWith('products'))
        products.value = await serviceProducts(auth.token)
    } catch (e) {
      error.value = e instanceof Error ? e.message : '读取失败'
    }
  },
  { immediate: true },
)
</script>
<template>
  <section class="service-info">
    <RouterLink to="/service">← 返回服务工作台</RouterLink>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <template v-if="route.path.endsWith('products')"
      ><h1>支持的售后产品</h1>
      <p>以下为毕业设计中的虚构产品，可在服务咨询中选择。</p>
      <article v-for="p in products" :key="p.id">
        <h2>{{ p.name }}</h2>
        <p>蓝牙连接、声音异常、使用方法及售后咨询。</p>
        <RouterLink to="/service">开始咨询 →</RouterLink>
      </article></template
    >
    <template v-else
      ><h1>服务守则</h1>
      <p>本项目演示规则 · 适用于虚构 Oshino 数码产品。</p>
      <article>
        <h2>用户守则</h2>
        <ol>
          <li>如实说明产品型号、故障现象和已尝试步骤。</li>
          <li>同一问题在原会话中继续沟通，不重复创建工单。</li>
          <li>可以转人工、说明原因申请更换客服，并确认处理结果。</li>
          <li>不提交密码、验证码等敏感信息。</li>
        </ol>
      </article>
      <article>
        <h2>客服守则</h2>
        <ol>
          <li>接单前阅读历史对话和已尝试步骤，避免重复询问。</li>
          <li>L1 处理日常咨询；技术难题转 L2；投诉争议交 L3 协调。</li>
          <li>转交写明原因，保留原工单和完整处理记录。</li>
          <li>如实记录结果，不索取密码，不擅自承诺退款或虚构已完成操作。</li>
        </ol>
      </article>
      <article>
        <h2>工单排序</h2>
        <p>
          P1 严重风险或大范围故障 → P2 核心功能无法使用 → P3 部分功能异常 → P4
          普通咨询。
        </p>
        <p>
          相同优先级按最强王者、王者、铂金、青铜排序；等级相同时等待更久的先处理。客户初报严重程度，由接单客服核实。
        </p>
      </article></template
    >
  </section>
</template>
<style scoped>
.service-info {
  max-width: 1200px;
}
.service-info h1 {
  font-size: 32px;
  margin: 28px 0;
}
.service-info > p {
  color: #6b7e96;
}
.service-info article {
  background: white;
  border: 1px solid #dce5f0;
  border-radius: 14px;
  padding: 28px;
  margin: 24px 0;
}
.service-info h2 {
  font-size: 21px;
}
.service-info li {
  line-height: 2.5;
}
</style>
