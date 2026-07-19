<template>
  <div class="app-workspace-view text-text-primary font-sans relative">
    <AuroraBackground v-if="bootMode !== 'ready' && bootMode !== 'course_selection'" :reduce-motion="false" />

    <div
      v-if="bootMode === 'loading'"
      class="app-workspace-loading relative z-10 flex items-center justify-center animate-fadeIn"
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
      @login-success="onLoginSuccess"
      @go-home="goHome"
    />

    <CourseSelectionView
      v-else-if="bootMode === 'course_selection'"
      :courses="availableCourses"
      :enrolled="enrolledCourses"
      :active-course="activeCourse"
      :loading="isBusy"
      @select="onCourseSelect"
      @back="returnToWorkspace"
      @go-home="goHome"
    />

    <ColdStartAssessmentView
      v-else-if="bootMode === 'probe'"
      :user="currentUser"
      :active-course="activeCourse"
      :probe="probe"
      :collected="probeCollected"
      :total="probeTotal"
      :submitting="isSubmittingProbe"
      @submit="submitProbe"
    />

    <PremiumWorkspace
      v-else-if="bootMode === 'ready'"
      :boot-mode="bootMode"
      :user="currentUser"
      :current-node="currentNode"
      :cards="currentCards"
      :resource-card-states="currentResourceCardStates"
      :path-nodes="currentPathNodes"
      :node-title="currentNodeTitle"
      :messages="messages"
      :agent-feedback="agentFeedback"
      :capability-radar="capabilityRadar"
      :overall-progress="overallProgress"
      :mastered-count="masteredCount"
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
      :session-id="sessionId"
      :enrolled-courses="enrolledCourses"
      @select-node="loadNode"
      @submit-quiz="submitWorkspaceQuiz"
      @send-tutor="onSendTutorMessage"
      @submit-probe="submitProbe"
      @logout="handleLogout"
      @go-home="goHome"
      @switch-course="onSwitchCourse"
      @browse-courses="openCourseSelection"
      @refresh-resources="() => refreshNodeResources(currentNode, { force: true })"
      @generate-card="onGenerateCard"
      @code-run="onCodeRun"
      @code-submitted="onCodeSubmitted"
      @restart-probe="restartProbe"
    />
  </div>
</template>

<script setup>
import { defineAsyncComponent, onMounted } from "vue";
import { useRouter } from "vue-router";
import AuroraBackground from "../components/AuroraBackground.vue";
import { useEduAgent } from "../composables/useEduAgent";

const AuthView = defineAsyncComponent(() => import("../components/AuthView.vue"));
const ColdStartAssessmentView = defineAsyncComponent(() => import("../components/ColdStartAssessmentView.vue"));
const CourseSelectionView = defineAsyncComponent(() => import("../components/CourseSelectionView.vue"));
const PremiumWorkspace = defineAsyncComponent(() => import("../components/PremiumWorkspace.vue"));

const router = useRouter();

const {
  isLoggedIn,
  bootMode,
  isSubmittingProbe,
  isBusy,
  isLoadingNode,
  currentNode,
  currentUser,
  capabilityRadar,
  currentCards,
  currentResourceCardStates,
  currentNodeTitle,
  currentPathNodes,
  messages,
  agentFeedback,
  infoMessage,
  probe,
  probeCollected,
  probeTotal,
  lastDiagnostic,
  overallProgress,
  masteredCount,
  activeCourse,
  sessionId,
  availableCourses,
  enrolledCourses,
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
  restartProbe,
  recordCodeRun,
  recordCodeSubmission,
} = useEduAgent();

onMounted(() => {
  bootstrap();
});

async function onLoginSuccess(result) {
  currentUser.value = result.user;
  isLoggedIn.value = true;
  await bootstrap();
}

function goHome() {
  router.push("/");
}

async function onCourseSelect(courseId) {
  if (courseId === activeCourse.value?.course_id) {
    bootMode.value = "ready";
    return;
  }

  const isEnrolled = enrolledCourses.value.some((course) => course.course_id === courseId);
  if (isEnrolled) {
    await handleSwitchCourse(courseId);
    return;
  }

  await handleEnrollCourse(courseId);
}

function openCourseSelection() {
  bootMode.value = "course_selection";
}

function returnToWorkspace() {
  bootMode.value = activeCourse.value ? "ready" : "course_selection";
}

async function onSendTutorMessage(payload) {
  if (typeof payload === "string") {
    await sendTutorMessage(payload);
  } else {
    await sendTutorMessage(payload.text, payload.contextType, payload.codeSnippet, payload.errorMessage);
  }
}

async function submitWorkspaceQuiz(submission) {
  let result;
  try {
    result = await submitQuiz(submission);
  } catch (error) {
    try {
      submission?.onFailure?.(error);
    } catch (callbackError) {
      console.error("quiz onFailure callback failed:", callbackError);
    }
    return null;
  }
  try {
    submission?.onRecorded?.(result);
  } catch (callbackError) {
    console.error("quiz onRecorded callback failed:", callbackError);
  }
  return result;
}

function onSwitchCourse(courseId) {
  handleSwitchCourse(courseId);
}

async function onGenerateCard({ nodeId, force = false, cardType = "" } = {}) {
  const targetNode = nodeId || currentNode.value;
  if (!targetNode) return;
  await refreshNodeResources(targetNode, { force, cardType });
}

function onCodeRun(payload) {
  void recordCodeRun(payload).catch((error) => {
    console.error("Unable to record code run:", error);
  });
}

function onCodeSubmitted(payload) {
  void recordCodeSubmission(payload).catch((error) => {
    console.error("Unable to record code submission:", error);
  });
}
</script>

<style scoped>
.app-workspace-view,
.app-workspace-loading {
  min-height: 100vh;
  min-height: 100dvh;
}

.app-workspace-loading {
  padding:
    env(safe-area-inset-top, 0px)
    env(safe-area-inset-right, 0px)
    env(safe-area-inset-bottom, 0px)
    env(safe-area-inset-left, 0px);
}
</style>
