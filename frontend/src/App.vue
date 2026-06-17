<template>
  <div class="min-h-screen text-text-primary font-sans relative">
    <!-- Dynamic aurora background -->
    <AuroraBackground :reduce-motion="false" />

    <!-- Landing page -->
    <LandingView
      v-if="showLanding"
      @enter="onEnterApp"
    />

    <!-- App states -->
    <template v-else>
      <!-- 加载中 -->
      <div
        v-if="bootMode === 'loading'"
        class="relative z-10 flex items-center justify-center h-screen animate-fadeIn"
      >
        <div class="text-center animate-fadeIn">
          <div class="relative w-20 h-20 mx-auto mb-6">
            <div class="absolute inset-0 rounded-full border-2 border-primary/15 animate-spin-slow" />
            <div class="absolute inset-1 rounded-full border-2 border-t-secondary border-r-transparent border-b-transparent border-l-transparent animate-spin" style="animation-duration: 1.1s;" />
            <div class="absolute inset-2 rounded-full border-2 border-b-tertiary border-t-transparent border-r-transparent border-l-transparent animate-spin" style="animation-duration: 1.6s; animation-direction: reverse;" />
            <div class="absolute inset-0 flex items-center justify-center">
              <span class="text-xl font-black gradient-text">EA</span>
            </div>
          </div>
          <p class="text-sm font-medium text-text-secondary tracking-wide">正在初始化学习工作台...</p>
          <p class="mt-2 text-xs text-text-muted">多智能体协作编排中</p>
        </div>
      </div>

      <!-- 登录 / 注册 -->
      <AuthView
        v-else-if="bootMode === 'login'"
        @login="onLogin"
        @register="onRegister"
        @go-home="goHome"
      />

      <!-- 主工作台 (探针 + 就绪) -->
      <PremiumWorkspace
        v-else-if="bootMode === 'probe' || bootMode === 'ready'"
        :boot-mode="bootMode"
        :user="currentUser"
        :current-node="currentNode"
        :cards="currentCards"
        :path-nodes="currentPathNodes"
        :node-title="currentNodeTitle"
        :messages="messages"
        :capability-radar="capabilityRadar"
        :statuses="agentStatuses"
        :is-busy="isBusy"
        :is-loading-node="isLoadingNode"
        :is-submitting-probe="isSubmittingProbe"
        :probe="probe"
        :probe-collected="probeCollected"
        :probe-total="probeTotal"
        :get-card-label="getCardLabel"
        :get-agent-label="getAgentLabel"
        :parse-quiz="parseQuiz"
        @select-node="loadNode"
        @submit-quiz="submitQuiz"
        @send-tutor="sendTutorMessage"
        @submit-probe="submitProbe"
        @logout="handleLogout"
        @go-home="goHome"
      />
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import AuroraBackground from "./components/AuroraBackground.vue";
import AuthView from "./components/AuthView.vue";
import LandingView from "./components/LandingView.vue";
import PremiumWorkspace from "./components/PremiumWorkspace.vue";
import { useEduAgent } from "./composables/useEduAgent";
import { useTheme } from "./composables/useTheme.js";

// Initialize theme system
useTheme();

const showLanding = ref(true);

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

function onEnterApp() {
  showLanding.value = false;
  bootstrap();
}

function goHome() {
  showLanding.value = true;
}

onMounted(() => {
  // Check URL hash for direct app access
  if (window.location.hash === "#app") {
    showLanding.value = false;
    bootstrap();
  }
});
</script>
