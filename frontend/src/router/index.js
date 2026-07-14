import { createRouter, createWebHistory } from "vue-router";
import { ensureAuthenticated } from "./auth";

const LandingView = () => import("../components/LandingView.vue");
const HomeView = () => import("../views/HomeView.vue");
const CoursesView = () => import("../views/CoursesView.vue");
const CourseDetailView = () => import("../views/CourseDetailView.vue");
const LearnView = () => import("../views/LearnView.vue");
const ReviewView = () => import("../views/ReviewView.vue");
const ProgressView = () => import("../views/ProgressView.vue");
const AccountView = () => import("../views/AccountView.vue");
const SettingsView = () => import("../views/SettingsView.vue");
const LoginView = () => import("../views/LoginView.vue");

const protectedRoute = {
  requiresAuth: true,
};

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "landing",
      component: LandingView,
    },
    {
      path: "/app",
      name: "app-workspace",
      component: HomeView,
      meta: protectedRoute,
    },
    {
      path: "/courses",
      name: "courses",
      component: CoursesView,
      meta: protectedRoute,
    },
    {
      path: "/courses/:courseId",
      name: "course-detail",
      component: CourseDetailView,
      props: true,
      meta: protectedRoute,
    },
    {
      path: "/learn/:courseId/:nodeId",
      name: "learn",
      component: LearnView,
      props: true,
      meta: protectedRoute,
    },
    {
      path: "/review",
      name: "review",
      component: ReviewView,
      meta: protectedRoute,
    },
    {
      path: "/progress",
      name: "progress",
      component: ProgressView,
      meta: protectedRoute,
    },
    {
      path: "/account",
      name: "account",
      component: AccountView,
      meta: protectedRoute,
    },
    {
      path: "/settings",
      name: "settings",
      component: SettingsView,
      meta: protectedRoute,
    },
    {
      path: "/login",
      name: "login",
      component: LoginView,
      meta: { authMode: "login" },
    },
    {
      path: "/forgot-password",
      name: "password-forgot",
      component: LoginView,
      meta: { authMode: "forgot" },
    },
    {
      path: "/reset-password",
      name: "password-reset",
      component: LoginView,
      meta: { authMode: "reset" },
    },
    {
      path: "/verify-email",
      name: "email-verify",
      component: LoginView,
      meta: { authMode: "verify" },
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/",
    },
  ],
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition;
    }

    if (to.hash) {
      return { el: to.hash, behavior: "smooth" };
    }

    return { top: 0 };
  },
});

router.beforeEach(async (to) => {
  if (!to.matched.some((record) => record.meta.requiresAuth)) {
    return true;
  }

  const user = await ensureAuthenticated();
  if (user) {
    return true;
  }

  return {
    name: "login",
    query: { redirect: to.fullPath },
  };
});

export default router;
