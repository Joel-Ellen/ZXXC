<template>
  <div class="min-h-screen text-text-primary font-sans relative">
    <AuroraBackground :reduce-motion="false" />

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
      :submit-login="onLogin"
      :submit-register="onRegister"
      @go-home="goHome"
    />

    <CourseSelectionView
      v-else-if="bootMode === 'course_selection'"
      :courses="availableCourses"
      :enrolled="enrolledCourses"
      :loading="isBusy"
      :return-to-workspace="courseSelectionReturnMode !== null"
      @select="onCourseSelect"
      @back="returnToWorkspace"
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
      @browse-courses="openCourseSelection"
      @switch-course="onSwitchCourse"
      @refresh-resources="() => refreshNodeResources(currentNode, true)"
      @generate-card="onGenerateCard"
    />
  </div>
</template>

<script setup>
import { defineAsyncComponent, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import AuroraBackground from "../components/AuroraBackground.vue";
import { useEduAgent } from "../composables/useEduAgent";

const AuthView = defineAsyncComponent(() => import("../components/AuthView.vue"));
const CourseSelectionView = defineAsyncComponent(() => import("../components/CourseSelectionView.vue"));
const PremiumWorkspace = defineAsyncComponent(() => import("../components/PremiumWorkspace.vue"));

const router = useRouter();
const courseSelectionReturnMode = ref(null);

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

onMounted(() => {
  bootstrap();
});

async function onLogin(userId, password, captchaToken, captchaAnswer) {
  await handleLogin(userId, password, captchaToken, captchaAnswer);
  await bootstrap();
}

async function onRegister(userId, email, password, captchaToken, captchaAnswer) {
  await handleRegister(userId, email, password, captchaToken, captchaAnswer);
  await bootstrap();
}

function goHome() {
  courseSelectionReturnMode.value = null;
  router.push("/");
}

function openCourseSelection() {
  courseSelectionReturnMode.value = bootMode.value;
  bootMode.value = "course_selection";
}

function returnToWorkspace() {
  const returnMode = courseSelectionReturnMode.value;
  courseSelectionReturnMode.value = null;
  bootMode.value = returnMode === "probe" ? "probe" : "ready";
}

async function onCourseSelect(courseId) {
  const isEnrolled = enrolledCourses.value.some((course) => course.course_id === courseId);

  if (isEnrolled) {
    if (activeCourse.value?.course_id === courseId) {
      returnToWorkspace();
      return;
    }
    await handleSwitchCourse(courseId);
  } else {
    await handleEnrollCourse(courseId);
  }

  if (bootMode.value !== "course_selection") {
    courseSelectionReturnMode.value = null;
  }
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

async function onGenerateCard({ nodeId, cardType = "", force = false } = {}) {
  const targetNode = nodeId || currentNode.value;
  if (!targetNode) return;
  await refreshNodeResources(targetNode, { force, cardType });
}
</script>
