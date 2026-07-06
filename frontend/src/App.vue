<template>
  <div class="min-h-screen text-text-primary font-sans relative">
    <AuroraBackground :reduce-motion="false" />

    <LandingView
      v-if="showLanding"
      @enter="onEnterApp"
    />

    <template v-else>
      <div
        v-if="bootMode === 'loading'"
        class="relative z-10 flex h-screen items-center justify-center animate-fadeIn"
      >
        <div class="text-center animate-fadeIn">
          <div class="relative mx-auto mb-6 h-20 w-20">
            <div class="absolute inset-0 rounded-full border-2 border-primary/15 animate-spin-slow" />
            <div class="absolute inset-1 rounded-full border-2 border-t-secondary border-r-transparent border-b-transparent border-l-transparent animate-spin" style="animation-duration: 1.1s;" />
            <div class="absolute inset-2 rounded-full border-2 border-b-tertiary border-t-transparent border-r-transparent border-l-transparent animate-spin" style="animation-duration: 1.6s; animation-direction: reverse;" />
            <div class="absolute inset-0 flex items-center justify-center">
              <span class="text-xl font-black gradient-text">EA</span>
            </div>
          </div>
          <p class="text-sm font-medium tracking-wide text-text-secondary">正在初始化学习工作台...</p>
          <p class="mt-2 text-xs text-text-muted">多智能体协作编排中</p>
        </div>
      </div>

      <AuthView
        v-else-if="bootMode === 'login'"
        @login="onLogin"
        @register="onRegister"
        @go-home="goHome"
      />

      <CourseSelectionView
        v-else-if="bootMode === 'course_selection'"
        :courses="availableCourses"
        :enrolled="enrolledCourses"
        :loading="isBusy"
        @select="onCourseSelect"
        @go-home="goHome"
      />

      <PremiumWorkspace
        v-else-if="bootMode === 'probe' || bootMode === 'ready'"
        :boot-mode="bootMode"
        :user="currentUser"
        :current-node="currentNode"
        :cards="currentCards"
        :path-nodes="currentPathNodes"
        :node-title="currentNodeTitle"
        :messages="messages"
        :agent-feedback="agentFeedback"
        :capability-radar="capabilityRadar"
        :overall-progress="overallProgress"
        :mastered-count="masteredCount"
        :statuses="agentStatuses"
        :info-message="infoMessage"
        :is-busy="isBusy"
        :is-loading-node="isLoadingNode"
        :is-submitting-probe="isSubmittingProbe"
        :probe="probe"
        :probe-collected="probeCollected"
        :probe-total="probeTotal"
        :last-diagnostic="lastDiagnostic"
        :get-card-label="getCardLabel"
        :get-agent-label="getAgentLabel"
        :parse-quiz="parseQuiz"
        :active-course="activeCourse"
        :enrolled-courses="enrolledCourses"
        @select-node="loadNode"
        @submit-quiz="submitQuiz"
        @send-tutor="onSendTutorMessage"
        @submit-probe="submitProbe"
        @logout="handleLogout"
        @go-home="goHome"
        @switch-course="onSwitchCourse"
        @refresh-resources="() => refreshNodeResources(currentNode, true)"
        @generate-card="onGenerateCard"
      />
    </template>
  </div>
</template>

<script setup>
import { defineAsyncComponent, onMounted, ref } from "vue";
import AuroraBackground from "./components/AuroraBackground.vue";
import { useEduAgent } from "./composables/useEduAgent";
import { useTheme } from "./composables/useTheme.js";

const LandingView = defineAsyncComponent(() => import("./components/LandingView.vue"));
const AuthView = defineAsyncComponent(() => import("./components/AuthView.vue"));
const CourseSelectionView = defineAsyncComponent(() => import("./components/CourseSelectionView.vue"));
const PremiumWorkspace = defineAsyncComponent(() => import("./components/PremiumWorkspace.vue"));

useTheme();

const showLanding = ref(true);

const {
  bootMode,
  isSubmittingProbe,
  isBusy,
  isLoadingNode,
  currentNode,
  currentUser,
  capabilityRadar,
  currentCards,
  currentNodeTitle,
  currentPathNodes,
  messages,
  agentFeedback,
  infoMessage,
  agentStatuses,
  probe,
  probeCollected,
  probeTotal,
  lastDiagnostic,
  overallProgress,
  masteredCount,
  activeCourse,
  availableCourses,
  enrolledCourses,
  handleLogin,
  handleRegister,
  handleLogout,
  bootstrap,
  submitProbe,
  loadNode,
  refreshNodeResources,
  submitQuiz,
  sendTutorMessage,
  getCardLabel,
  getAgentLabel,
  parseQuiz,
  handleEnrollCourse,
  handleSwitchCourse,
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

function onCourseSelect(courseId) {
  handleEnrollCourse(courseId);
}

async function onSendTutorMessage(payload) {
  if (typeof payload === "string") {
    await sendTutorMessage(payload);
  } else {
    await sendTutorMessage(payload.text, payload.contextType, payload.codeSnippet, payload.errorMessage);
  }
}

function onSwitchCourse(courseId) {
  handleSwitchCourse(courseId);
}

/**
 * 用户点击资源卡片区域的"生成"或"重新生成"时触发。
 * force=true 表示强制重新生成（即使已有资源）。
 */
async function onGenerateCard({ nodeId, force = false } = {}) {
  const targetNode = nodeId || currentNode.value;
  if (!targetNode) return;
  await refreshNodeResources(targetNode, force);
}

onMounted(() => {
  if (window.location.hash === "#app") {
    showLanding.value = false;
    bootstrap();
  }
});
</script>
