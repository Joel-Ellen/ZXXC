<template>
  <div class="min-h-screen bg-gray-950 text-gray-100 font-sans">
    <!-- 加载中 -->
    <div v-if="bootMode === 'loading'" class="flex items-center justify-center h-screen">
      <div class="text-center">
        <div class="w-12 h-12 mx-auto mb-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin"></div>
        <p class="text-gray-400">正在初始化 EduAgent...</p>
      </div>
    </div>

    <!-- 登录 / 注册 -->
    <AuthView
      v-else-if="bootMode === 'login'"
      @login="onLogin"
      @register="onRegister"
    />

    <!-- 冷启动探针 -->
    <ProbeView
      v-else-if="bootMode === 'probe'"
      :probe="probe"
      :collected="probeCollected"
      :total="probeTotal"
      :busy="isSubmittingProbe"
      @submit="submitProbe"
    />

    <!-- 主工作台 -->
    <WorkspaceView
      v-else-if="bootMode === 'ready'"
      :user="currentUser"
      :current-node="currentNode"
      :node-title="currentNodeTitle"
      :cards="currentCards"
      :path-nodes="currentPathNodes"
      :messages="messages"
      :radar="capabilityRadar"
      :report="diagnosticReport"
      :progress="overallProgress"
      :mastered="masteredCount"
      :total-path="currentPathNodes.length"
      :statuses="agentStatuses"
      :busy="isBusy"
      :loading-node="isLoadingNode"
      :card-label="getCardLabel"
      :agent-label="getAgentLabel"
      :parse-quiz="parseQuiz"
      @select-node="loadNode"
      @submit-quiz="submitQuiz"
      @send-tutor="sendTutorMessage"
      @logout="handleLogout"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import AuthView from "./components/AuthView.vue";
import ProbeView from "./components/ProbeView.vue";
import WorkspaceView from "./components/WorkspaceView.vue";
import { useEduAgent } from "./composables/useEduAgent";

const {
  bootMode, isSubmittingProbe, isBusy, isLoadingNode,
  currentNode, currentUser, capabilityRadar, diagnosticReport,
  currentCards, currentNodeTitle, currentPathNodes,
  messages, agentStatuses, probe, probeCollected, probeTotal,
  overallProgress, masteredCount,
  handleLogin, handleRegister, handleLogout,
  bootstrap, submitProbe, loadNode, submitQuiz, sendTutorMessage,
  getCardLabel, getAgentLabel, parseQuiz,
} = useEduAgent();

async function onLogin(userId, password, captchaToken, captchaAnswer) {
  await handleLogin(userId, password, captchaToken, captchaAnswer);
  await bootstrap();
}

async function onRegister(userId, email, password, captchaToken, captchaAnswer) {
  await handleRegister(userId, email, password, captchaToken, captchaAnswer);
  await bootstrap();
}

onMounted(bootstrap);
</script>
