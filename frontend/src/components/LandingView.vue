<template>
  <div class="landing-root relative min-h-screen overflow-x-hidden bg-space-bg text-text-primary">
    <!-- Scroll progress bar -->
    <div class="fixed inset-x-0 top-0 z-[60] h-[2px] bg-transparent">
      <div class="h-full bg-gradient-to-r from-primary via-secondary to-tertiary" :style="{ width: `${scrollProgress}%` }" />
    </div>

    <!-- Fixed minimal nav -->
    <nav
      class="fixed inset-x-0 top-0 z-50 transition-all duration-500"
      :class="navScrolled ? 'bg-space-panel/85 backdrop-blur-xl border-b border-subtle' : 'bg-transparent'"
    >
      <div class="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        <a href="#" class="flex items-center gap-2" @click.prevent="scrollToTop">
          <div class="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-primary to-secondary text-[10px] font-black text-primary-text">
            EA
          </div>
          <span class="text-sm font-semibold tracking-tight">EduAgent</span>
        </a>

        <div class="hidden items-center gap-6 text-xs font-medium text-text-secondary md:flex">
          <a href="#curriculum" class="transition-colors hover:text-text-primary">知识体系</a>
          <a href="#why" class="transition-colors hover:text-text-primary">为何选择</a>
          <a href="#features" class="transition-colors hover:text-text-primary">功能</a>
          <a href="#comparison" class="transition-colors hover:text-text-primary">对比</a>
          <a href="#workflow" class="transition-colors hover:text-text-primary">流程</a>
          <a href="#demo" class="transition-colors hover:text-text-primary">演示</a>
          <a href="#architecture" class="transition-colors hover:text-text-primary">架构</a>
          <a href="#faq" class="transition-colors hover:text-text-primary">FAQ</a>
        </div>

        <div class="flex items-center gap-3">
          <button
            type="button"
            class="focus-ring hidden rounded-full border border-subtle bg-card px-4 py-1.5 text-xs font-semibold text-text-secondary transition-all duration-200 hover:border-primary/30 hover:text-primary hover:bg-card-hover md:inline-flex"
            @click="enterApp"
          >
            登录
          </button>
          <button
            type="button"
            class="focus-ring rounded-full bg-text-primary px-4 py-1.5 text-xs font-semibold text-space-bg transition-transform duration-200 hover:scale-105 active:scale-95"
            @click="enterApp"
          >
            进入工作台
          </button>
          <button
            type="button"
            class="focus-ring flex h-8 w-8 items-center justify-center rounded-full border border-subtle text-text-secondary md:hidden"
            aria-label="打开菜单"
            @click="mobileMenuOpen = true"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      </div>
    </nav>

    <!-- Mobile menu -->
    <transition name="fade">
      <div v-if="mobileMenuOpen" class="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm md:hidden" @click="mobileMenuOpen = false">
        <div class="absolute right-4 top-4 w-64 rounded-[24px] border border-subtle bg-space-panel p-5 shadow-2xl" @click.stop>
          <div class="mb-4 flex items-center justify-between">
            <span class="text-sm font-bold">菜单</span>
            <button type="button" class="rounded-full p-1 text-text-muted hover:text-text-primary" @click="mobileMenuOpen = false">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="space-y-1">
            <a v-for="item in menuItems" :key="item.href" :href="item.href" class="block rounded-xl px-4 py-3 text-sm font-medium text-text-secondary transition-colors hover:bg-card hover:text-text-primary" @click="mobileMenuOpen = false">
              {{ item.label }}
            </a>
          </div>
          <button type="button" class="focus-ring mt-4 w-full rounded-full bg-text-primary py-2.5 text-sm font-semibold text-space-bg" @click="enterApp">
            进入工作台
          </button>
        </div>
      </div>
    </transition>

    <!-- Hero -->
    <section class="relative flex min-h-screen flex-col items-center justify-center px-6 pt-14 pb-24">
      <!-- Background ambient -->
      <div class="pointer-events-none absolute inset-0 overflow-hidden">
        <div class="absolute -top-[20vh] left-1/2 h-[80vh] w-[80vh] -translate-x-1/2 rounded-full bg-primary/10 blur-[120px]" />
        <div class="absolute top-[30vh] right-[-10vw] h-[60vh] w-[60vh] rounded-full bg-secondary/10 blur-[100px]" />
        <div class="absolute bottom-[10vh] left-[-10vw] h-[50vh] w-[50vh] rounded-full bg-tertiary/8 blur-[90px]" />
        <div class="absolute top-[60vh] left-[20vw] h-[30vh] w-[30vh] rounded-full bg-info/8 blur-[80px]" />
      </div>

      <div class="relative z-10 mx-auto max-w-5xl text-center">
        <div
          ref="heroEyebrow"
          class="reveal mb-6 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary-soft px-4 py-1.5 text-xs font-bold uppercase tracking-[0.18em] text-primary"
        >
          <span class="h-1.5 w-1.5 rounded-full bg-primary animate-breathe" />
          多智能体学习系统
        </div>
        <h1
          ref="heroHeadline"
          class="reveal text-5xl font-black leading-[1.05] tracking-tight sm:text-6xl md:text-7xl lg:text-8xl"
        >
          <span class="block">让 AI</span>
          <span class="gradient-text">成为你的私教。</span>
        </h1>
        <p
          ref="heroSubhead"
          class="reveal mx-auto mt-6 max-w-2xl text-lg font-light leading-relaxed text-text-secondary sm:text-xl"
        >
          EduAgent 将冷启动测评、知识路径、苏格拉底式对话辅导与五维能力雷达融为一体，为每一位学习者打造自适应的数据结构与算法学习体验。
        </p>
        <div
          ref="heroCtas"
          class="reveal mt-10 flex flex-wrap items-center justify-center gap-4"
        >
          <button
            type="button"
            class="focus-ring btn-capsule px-8 py-3.5 text-sm"
            @click="enterApp"
          >
            立即体验
          </button>
          <a
            href="#demo"
            class="focus-ring rounded-full border border-subtle bg-card px-6 py-3 text-sm font-medium text-text-secondary transition-all duration-200 hover:border-primary/30 hover:text-primary hover:bg-card-hover"
          >
            观看演示
          </a>
        </div>

        <!-- Hero pills -->
        <div ref="heroPills" class="reveal mt-10 flex flex-wrap items-center justify-center gap-3">
          <span class="rounded-full border border-subtle bg-card/80 px-3 py-1.5 text-xs text-text-secondary backdrop-blur-sm">冷启动测评</span>
          <span class="rounded-full border border-subtle bg-card/80 px-3 py-1.5 text-xs text-text-secondary backdrop-blur-sm">知识图谱</span>
          <span class="rounded-full border border-subtle bg-card/80 px-3 py-1.5 text-xs text-text-secondary backdrop-blur-sm">对话辅导</span>
          <span class="rounded-full border border-subtle bg-card/80 px-3 py-1.5 text-xs text-text-secondary backdrop-blur-sm">能力雷达</span>
        </div>
      </div>

      <!-- Hero visual: floating app preview -->
      <div
        ref="heroVisual"
        class="reveal relative z-10 mx-auto mt-16 w-full max-w-5xl"
      >
        <div class="relative mx-auto aspect-[16/10] w-full overflow-hidden rounded-[36px] border border-subtle bg-space-panel/60 shadow-2xl backdrop-blur-xl">
          <!-- App mockup header -->
          <div class="flex h-12 items-center gap-3 border-b border-subtle px-5">
            <div class="flex items-center gap-2">
              <div class="h-3 w-3 rounded-full bg-error" />
              <div class="h-3 w-3 rounded-full bg-warning" />
              <div class="h-3 w-3 rounded-full bg-success" />
            </div>
            <div class="ml-4 flex h-6 flex-1 items-center gap-2 rounded-full bg-card px-3">
              <div class="h-2 w-2 rounded-full bg-primary" />
              <div class="h-2 w-20 rounded-full bg-text-muted/20" />
            </div>
          </div>
          <!-- Mockup body -->
          <div class="grid h-[calc(100%-48px)] grid-cols-12 gap-px bg-subtle">
            <div class="col-span-3 bg-space-surface/50 p-4">
              <div class="mb-4 flex h-10 items-center gap-2 rounded-xl bg-card px-3">
                <div class="h-2 w-2 rounded-full bg-primary" />
                <div class="h-2 w-12 rounded bg-text-muted/20" />
              </div>
              <div class="space-y-3">
                <div v-for="i in 5" :key="i" class="h-8 rounded-lg bg-card" :style="{ opacity: 1 - i * 0.12 }" />
              </div>
            </div>
            <div class="col-span-4 bg-space-surface/30 p-4">
              <div class="mb-4 h-6 rounded-lg bg-card" />
              <div class="space-y-4">
                <div class="rounded-2xl border border-primary/20 bg-primary-soft p-4">
                  <div class="flex items-center gap-2">
                    <div class="h-2 w-2 rounded-full bg-primary" />
                    <div class="h-3 w-1/3 rounded bg-primary/30" />
                  </div>
                  <div class="mt-3 space-y-2">
                    <div class="h-2 w-full rounded bg-card" />
                    <div class="h-2 w-5/6 rounded bg-card" />
                    <div class="h-2 w-4/6 rounded bg-card" />
                  </div>
                </div>
                <div class="rounded-2xl border border-subtle bg-card p-4">
                  <div class="h-3 w-1/2 rounded bg-text-muted/20" />
                  <div class="mt-3 h-20 rounded-xl bg-space-surface/50" />
                </div>
              </div>
            </div>
            <div class="col-span-5 bg-space-bg/50 p-4">
              <div class="mb-4 flex items-center justify-between">
                <div class="h-6 w-1/3 rounded-lg bg-card" />
                <div class="h-6 w-16 rounded-full bg-card" />
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div class="col-span-2 h-32 rounded-2xl border border-secondary/20 bg-secondary-soft p-4">
                  <div class="flex h-full w-full items-center justify-center rounded-xl bg-card/50">
                    <div class="h-16 w-16 rounded-full border-2 border-secondary/30" />
                  </div>
                </div>
                <div class="h-28 rounded-2xl border border-info/20 bg-info-soft p-3">
                  <div class="h-full w-full rounded-xl bg-card/50" />
                </div>
                <div class="h-28 rounded-2xl border border-tertiary/20 bg-tertiary-soft p-3">
                  <div class="h-full w-full rounded-xl bg-card/50" />
                </div>
              </div>
            </div>
          </div>

          <!-- Floating agent pills -->
          <div class="absolute left-4 top-20 flex items-center gap-2 rounded-full border border-primary/30 bg-card/90 px-3 py-1.5 text-xs font-medium text-primary shadow-lg backdrop-blur-md animate-float-slow">
            <span class="h-1.5 w-1.5 rounded-full bg-primary animate-breathe" />
            辅导智能体就绪
          </div>
          <div class="absolute bottom-24 right-6 flex items-center gap-2 rounded-full border border-success/30 bg-card/90 px-3 py-1.5 text-xs font-medium text-success shadow-lg backdrop-blur-md animate-float-medium">
            <IconCheck :size="12" />
            知识节点已掌握
          </div>
          <div class="absolute top-32 right-12 flex items-center gap-2 rounded-full border border-secondary/30 bg-card/90 px-3 py-1.5 text-xs font-medium text-secondary shadow-lg backdrop-blur-md animate-float-fast">
            <IconRadar :size="12" />
            能力雷达更新
          </div>
          <div class="absolute bottom-12 left-12 flex items-center gap-2 rounded-full border border-info/30 bg-card/90 px-3 py-1.5 text-xs font-medium text-info shadow-lg backdrop-blur-md animate-float-fast" style="animation-delay: 0.5s;">
            <IconDoc :size="12" />
            资源已生成
          </div>
        </div>
      </div>

      <!-- Scroll hint -->
      <div class="absolute bottom-8 left-1/2 -translate-x-1/2 animate-bounce-subtle">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-text-muted">
          <path d="M12 5v14M19 12l-7 7-7-7" />
        </svg>
      </div>
    </section>

    <!-- Ribbon -->
    <section class="border-y border-subtle bg-space-surface/30 py-4 backdrop-blur-sm">
      <div class="flex animate-marquee whitespace-nowrap">
        <span v-for="i in 2" :key="i" class="flex items-center gap-12 px-12 text-xs font-bold uppercase tracking-[0.2em] text-text-muted">
          <span class="flex items-center gap-3"><IconTree :size="16" /> 知识路径</span>
          <span class="flex items-center gap-3"><IconChat :size="16" /> 对话辅导</span>
          <span class="flex items-center gap-3"><IconRadar :size="16" /> 能力雷达</span>
          <span class="flex items-center gap-3"><IconDoc :size="16" /> 多模态资源</span>
          <span class="flex items-center gap-3"><IconQuiz :size="16" /> 诊断测验</span>
          <span class="flex items-center gap-3"><IconExpand :size="16" /> 自适应推荐</span>
        </span>
      </div>
    </section>

    <!-- Knowledge Curriculum -->
    <section id="curriculum" class="py-32 px-6">
      <div class="mx-auto max-w-6xl">
        <div class="mb-20 text-center">
          <p class="reveal mb-4 text-xs font-bold uppercase tracking-[0.2em] text-primary">知识体系</p>
          <h2 class="reveal text-4xl font-black tracking-tight sm:text-5xl md:text-6xl">
            覆盖数据结构与算法<br class="hidden sm:block" />
            <span class="gradient-text">全体系核心模块。</span>
          </h2>
          <p class="reveal mx-auto mt-6 max-w-2xl text-lg font-light text-text-secondary" style="transition-delay: 100ms;">
            从基础线性结构到高级算法策略，每个模块拆解为递进式知识节点，按掌握度自动解锁。
          </p>
        </div>

        <div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          <div
            v-for="(mod, idx) in curriculumModules"
            :key="mod.title"
            class="reveal group relative overflow-hidden rounded-[28px] border border-subtle bg-card p-6 transition-all duration-500 hover:-translate-y-1 hover:shadow-card"
            :style="{ transitionDelay: `${idx * 80}ms` }"
          >
            <div class="mb-4 flex items-center justify-between">
              <div class="flex h-11 w-11 items-center justify-center rounded-2xl bg-space-surface transition-colors duration-300 group-hover:bg-card-hover">
                <component :is="mod.icon" :size="22" :class="`text-${mod.accent}`" />
              </div>
              <span class="text-[11px] font-mono font-bold uppercase tracking-[0.12em] text-text-muted">{{ mod.count }} 节点</span>
            </div>
            <h3 class="text-lg font-bold tracking-tight">{{ mod.title }}</h3>
            <p class="mt-2 text-sm font-light leading-relaxed text-text-secondary">{{ mod.desc }}</p>
            <div class="mt-4 flex flex-wrap gap-1.5">
              <span
                v-for="tag in mod.tags"
                :key="tag"
                class="rounded-full border border-subtle bg-space-surface/50 px-2.5 py-1 text-[11px] font-medium text-text-muted transition-colors group-hover:border-hover group-hover:text-text-secondary"
              >{{ tag }}</span>
            </div>
            <div class="absolute -right-8 -bottom-8 h-32 w-32 rounded-full opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-100" :class="`bg-${mod.accent}/5`" />
          </div>
        </div>
      </div>
    </section>

    <!-- Why section -->
    <section id="why" class="py-32 px-6">
      <div class="mx-auto max-w-6xl">
        <div class="grid items-center gap-16 lg:grid-cols-2">
          <div class="reveal">
            <p class="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-primary">为何选择 EduAgent</p>
            <h2 class="text-4xl font-black tracking-tight sm:text-5xl">
              传统学习工具的<br />
              <span class="gradient-text">痛点，</span>
              我们逐一击破。
            </h2>
          </div>
          <div class="reveal space-y-6" style="transition-delay: 120ms;">
            <div v-for="(pain, idx) in painPoints" :key="pain.title" class="group flex gap-5 rounded-2xl border border-subtle bg-card p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/20 hover:shadow-card">
              <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-space-surface text-primary transition-colors group-hover:bg-primary-soft">
                <component :is="pain.icon" :size="20" />
              </div>
              <div>
                <h3 class="text-base font-bold">{{ pain.title }}</h3>
                <p class="mt-1 text-sm font-light leading-relaxed text-text-secondary">{{ pain.desc }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Feature showcase -->
    <section id="features" class="relative py-32 px-6">
      <div class="pointer-events-none absolute inset-0">
        <div class="absolute top-0 left-1/2 h-[60vh] w-[80vh] -translate-x-1/2 rounded-full bg-secondary/5 blur-[120px]" />
      </div>
      <div class="relative mx-auto max-w-6xl">
        <div class="mb-20 text-center">
          <p class="reveal mb-4 text-xs font-bold uppercase tracking-[0.2em] text-primary">核心功能</p>
          <h2 ref="featureTitle" class="reveal text-4xl font-black tracking-tight sm:text-5xl md:text-6xl">
            一套完整的<br class="hidden sm:block" />
            <span class="gradient-text">学习闭环。</span>
          </h2>
        </div>

        <!-- Feature 1 -->
        <div class="feature-section mb-32 grid items-center gap-12 lg:grid-cols-2">
          <div class="reveal order-2 lg:order-1">
            <div class="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
              <IconQuiz :size="24" />
            </div>
            <h3 class="text-3xl font-bold tracking-tight sm:text-4xl">冷启动学习画像</h3>
            <p class="mt-4 text-lg font-light leading-relaxed text-text-secondary">
              首次进入只需完成 5 分钟测评，系统即可识别你的知识盲区、学习习惯与目标水平，为后续路径推荐提供精准依据。
            </p>
            <ul class="mt-6 space-y-3 text-text-secondary">
              <li class="flex items-center gap-3">
                <span class="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">01</span>
                多维度初始能力评估
              </li>
              <li class="flex items-center gap-3">
                <span class="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">02</span>
                自动生成学习画像
              </li>
              <li class="flex items-center gap-3">
                <span class="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">03</span>
                动态调整推荐策略
              </li>
            </ul>
          </div>
          <div class="reveal relative order-1 lg:order-2" style="transition-delay: 120ms;">
            <div class="aspect-square rounded-[40px] border border-subtle bg-space-panel/50 p-8 shadow-glass backdrop-blur-xl">
              <div class="mb-6 flex items-center justify-between">
                <span class="text-xs font-bold uppercase tracking-wider text-text-muted">学习画像采集</span>
                <span class="text-xs font-medium text-primary">3/6</span>
              </div>
              <div class="mb-6 flex gap-1.5">
                <span v-for="i in 6" :key="i" class="h-1.5 flex-1 rounded-full" :class="i <= 3 ? 'bg-primary' : 'bg-border-strong'" />
              </div>
              <div class="rounded-2xl border border-subtle bg-card p-5">
                <p class="text-sm font-medium text-text-primary">以下哪种数据结构最适合实现 LRU 缓存？</p>
                <div class="mt-4 space-y-2">
                  <div v-for="opt in ['数组 + 排序', '哈希表 + 双向链表', '单调栈', '二叉搜索树']" :key="opt" class="rounded-xl border border-subtle bg-space-surface/50 px-4 py-3 text-sm text-text-secondary transition-colors hover:border-primary/20 hover:text-text-primary">
                    {{ opt }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Feature 2 -->
        <div class="feature-section mb-32 grid items-center gap-12 lg:grid-cols-2">
          <div class="reveal relative">
            <div class="aspect-square rounded-[40px] border border-subtle bg-space-panel/50 p-8 shadow-glass backdrop-blur-xl">
              <div class="space-y-4">
                <div v-for="(step, idx) in knowledgeNodes" :key="step" class="flex items-center gap-4 rounded-2xl border border-subtle bg-card p-4 transition-all duration-300 hover:translate-x-2" :class="idx < 2 ? 'border-success/20 bg-success-soft/30' : ''">
                  <span class="flex h-10 w-10 items-center justify-center rounded-full font-mono text-sm" :class="idx < 2 ? 'bg-success text-success-text' : 'bg-card text-primary'">0{{ idx + 1 }}</span>
                  <span class="text-lg font-medium">{{ step }}</span>
                  <IconCheck v-if="idx < 2" class="ml-auto text-success" :size="18" />
                  <span v-else class="ml-auto h-2 w-2 rounded-full bg-secondary" />
                </div>
              </div>
            </div>
          </div>
          <div class="reveal" style="transition-delay: 120ms;">
            <div class="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-secondary-soft text-secondary">
              <IconTree :size="24" />
            </div>
            <h3 class="text-3xl font-bold tracking-tight sm:text-4xl">结构化知识路径</h3>
            <p class="mt-4 text-lg font-light leading-relaxed text-text-secondary">
              将复杂的数据结构与算法课程拆解为递进式节点，每个节点对应明确的学习目标与掌握阈值，让学习路径像地图一样清晰可见。
            </p>
            <ul class="mt-6 space-y-3 text-text-secondary">
              <li class="flex items-center gap-3">
                <span class="h-1.5 w-1.5 rounded-full bg-secondary" />
                自动编排学习顺序
              </li>
              <li class="flex items-center gap-3">
                <span class="h-1.5 w-1.5 rounded-full bg-secondary" />
                实时掌握度追踪
              </li>
              <li class="flex items-center gap-3">
                <span class="h-1.5 w-1.5 rounded-full bg-secondary" />
                节点解锁与智能推荐
              </li>
            </ul>
          </div>
        </div>

        <!-- Feature 3 -->
        <div class="feature-section mb-32 grid items-center gap-12 lg:grid-cols-2">
          <div class="reveal order-2 lg:order-1">
            <div class="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
              <IconChat :size="24" />
            </div>
            <h3 class="text-3xl font-bold tracking-tight sm:text-4xl">苏格拉底式对话辅导</h3>
            <p class="mt-4 text-lg font-light leading-relaxed text-text-secondary">
              不是直接给答案，而是通过连续追问引导你思考。辅导智能体能够理解你的困惑点，并用适合你当前水平的方式解释概念。
            </p>
          </div>
          <div class="reveal relative order-1 lg:order-2" style="transition-delay: 120ms;">
            <div class="aspect-square rounded-[40px] border border-subtle bg-space-panel/50 p-8 shadow-glass backdrop-blur-xl">
              <div class="flex h-full flex-col justify-end space-y-4">
                <div class="rounded-2xl border-l-4 border-primary bg-card p-4">
                  <p class="text-xs font-bold uppercase tracking-wider text-primary">辅导智能体</p>
                  <p class="mt-1 text-sm text-text-secondary">这道题可以用单调栈来优化时间复杂度，让我为你展开思路…</p>
                </div>
                <div class="self-end rounded-2xl border-r-4 border-secondary bg-secondary-soft p-4 text-right">
                  <p class="text-xs font-bold uppercase tracking-wider text-secondary">我</p>
                  <p class="mt-1 text-sm text-text-secondary">为什么不用哈希表直接查找？</p>
                </div>
                <div class="rounded-2xl border-l-4 border-primary bg-card p-4">
                  <p class="text-xs font-bold uppercase tracking-wider text-primary">辅导智能体</p>
                  <p class="mt-1 text-sm text-text-secondary">好问题。哈希表查找是 O(1)，但本题要求的是「最近」元素关系，需要维护顺序信息…</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Feature 4 -->
        <div class="feature-section grid items-center gap-12 lg:grid-cols-2">
          <div class="reveal relative">
            <div class="aspect-square rounded-[40px] border border-subtle bg-space-panel/50 p-6 shadow-glass backdrop-blur-xl">
              <RadarCanvas class="h-full w-full" :values="[0.85, 0.72, 0.68, 0.9, 0.55]" :high-contrast="true" />
            </div>
          </div>
          <div class="reveal" style="transition-delay: 120ms;">
            <div class="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-tertiary-soft text-tertiary">
              <IconRadar :size="24" />
            </div>
            <h3 class="text-3xl font-bold tracking-tight sm:text-4xl">五维能力雷达</h3>
            <p class="mt-4 text-lg font-light leading-relaxed text-text-secondary">
              从概念理解、代码工程、逻辑推理、错题恢复到时间管理，全方位量化你的学习状态，帮助你发现短板、精准提升。
            </p>
            <div class="mt-6 grid grid-cols-2 gap-3">
              <div v-for="dim in radarDimensions" :key="dim" class="rounded-xl border border-subtle bg-card px-3 py-2 text-sm text-text-secondary">
                {{ dim }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Bento grid -->
    <section class="py-24 px-6">
      <div class="mx-auto max-w-6xl">
        <p class="reveal mb-4 text-center text-xs font-bold uppercase tracking-[0.2em] text-primary">更多能力</p>
        <h2 ref="bentoTitle" class="reveal mb-16 text-center text-3xl font-black tracking-tight sm:text-4xl md:text-5xl">
          为学习体验<br class="hidden sm:block" />
          <span class="gradient-text">重新设计的每一个细节。</span>
        </h2>

        <div class="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-4">
          <div
            v-for="(card, idx) in bentoCards"
            :key="card.title"
            class="reveal group relative overflow-hidden rounded-[28px] border border-subtle bg-card p-6 transition-all duration-500 hover:-translate-y-1 hover:shadow-card"
            :class="card.span || ''"
            :style="{ transitionDelay: `${idx * 80}ms` }"
          >
            <div class="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-space-surface transition-colors duration-300 group-hover:bg-card-hover">
              <component :is="card.icon" :size="22" class="text-primary" />
            </div>
            <h3 class="text-lg font-bold tracking-tight">{{ card.title }}</h3>
            <p class="mt-2 text-sm font-light leading-relaxed text-text-secondary">{{ card.desc }}</p>
            <div class="absolute -right-8 -bottom-8 h-32 w-32 rounded-full bg-primary/5 blur-2xl transition-opacity duration-500 group-hover:opacity-100 opacity-0" />
          </div>
        </div>
      </div>
    </section>

    <!-- Comparison: EduAgent vs Traditional -->
    <section id="comparison" class="relative py-32 px-6">
      <div class="pointer-events-none absolute inset-0">
        <div class="absolute top-1/2 left-1/2 h-[80vh] w-[80vh] -translate-x-1/2 -translate-y-1/2 rounded-full bg-tertiary/5 blur-[100px]" />
      </div>
      <div class="relative mx-auto max-w-6xl">
        <div class="mb-16 text-center">
          <p class="reveal mb-4 text-xs font-bold uppercase tracking-[0.2em] text-primary">为什么与众不同</p>
          <h2 class="reveal text-4xl font-black tracking-tight sm:text-5xl md:text-6xl">
            不是又一个<br class="hidden sm:block" />
            <span class="gradient-text">刷题平台。</span>
          </h2>
        </div>

        <div class="reveal overflow-hidden rounded-[32px] border border-subtle bg-space-panel/60 shadow-glass backdrop-blur-xl" style="transition-delay: 150ms;">
          <!-- Table header -->
          <div class="grid grid-cols-3 border-b border-subtle">
            <div class="p-6">
              <span class="text-xs font-bold uppercase tracking-[0.14em] text-text-muted">对比维度</span>
            </div>
            <div class="p-6 text-center border-x border-subtle bg-card/30">
              <span class="text-xs font-bold uppercase tracking-[0.14em] text-text-muted">传统刷题平台</span>
            </div>
            <div class="p-6 text-center bg-primary-soft/20">
              <span class="text-xs font-bold uppercase tracking-[0.14em] text-primary">EduAgent</span>
            </div>
          </div>
          <!-- Table rows -->
          <div
            v-for="(row, idx) in comparisonRows"
            :key="row.dimension"
            class="grid grid-cols-3 transition-colors duration-200"
            :class="idx % 2 === 0 ? 'bg-transparent' : 'bg-card/20'"
          >
            <div class="flex items-center p-5">
              <span class="text-sm font-semibold text-text-primary">{{ row.dimension }}</span>
            </div>
            <div class="flex items-center gap-2 p-5 text-center border-x border-subtle">
              <span class="text-sm font-light text-text-muted">{{ row.traditional }}</span>
            </div>
            <div class="flex items-center gap-2 p-5 text-center bg-primary-soft/10">
              <IconCheck :size="14" class="text-success shrink-0" />
              <span class="text-sm font-medium text-primary">{{ row.eduagent }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Workflow section -->
    <section id="workflow" class="relative overflow-hidden py-32 px-6">
      <div class="pointer-events-none absolute inset-0">
        <div class="absolute top-1/2 left-1/2 h-[100vh] w-[100vh] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br from-primary/5 via-secondary/5 to-transparent blur-[120px]" />
      </div>
      <div class="relative mx-auto max-w-6xl">
        <div class="mb-20 text-center">
          <p class="reveal mb-4 text-xs font-bold uppercase tracking-[0.2em] text-primary">使用流程</p>
          <h2 class="reveal text-4xl font-black tracking-tight sm:text-5xl md:text-6xl">
            四步开启<br class="hidden sm:block" />
            <span class="gradient-text">智能学习。</span>
          </h2>
        </div>

        <div class="relative">
          <!-- Timeline line -->
          <div class="absolute left-8 top-0 bottom-0 w-px bg-gradient-to-b from-primary via-secondary to-tertiary md:left-1/2" />

          <div class="space-y-16">
            <div v-for="(step, idx) in workflowSteps" :key="step.title" class="relative grid items-center gap-8 md:grid-cols-2" :class="idx % 2 === 1 ? 'md:text-right' : ''">
              <div class="reveal" :class="idx % 2 === 1 ? 'md:order-2' : ''" :style="{ transitionDelay: `${idx * 100}ms` }">
                <div class="flex aspect-[4/3] items-center justify-center rounded-[32px] border border-subtle bg-space-panel/50 p-8 shadow-glass backdrop-blur-xl">
                  <component :is="step.icon" :size="64" :class="`text-${step.accent} opacity-80`" />
                </div>
              </div>
              <div class="reveal pl-20 md:pl-0" :class="idx % 2 === 1 ? 'md:order-1 md:pr-20' : 'md:pl-20'" :style="{ transitionDelay: `${idx * 100 + 100}ms` }">
                <div class="absolute left-6 flex h-10 w-10 items-center justify-center rounded-full border-2 md:left-1/2 md:-translate-x-1/2 text-sm font-bold" :class="`border-${step.accent} bg-card text-${step.accent}`">
                  {{ idx + 1 }}
                </div>
                <h3 class="text-2xl font-bold tracking-tight">{{ step.title }}</h3>
                <p class="mt-3 text-base font-light leading-relaxed text-text-secondary">{{ step.desc }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Demo animation section -->
    <section id="demo" class="relative overflow-hidden py-32 px-6">
      <div class="relative mx-auto max-w-6xl">
        <div class="mb-16 text-center">
          <p class="reveal mb-4 text-xs font-bold uppercase tracking-[0.2em] text-primary">实时演示</p>
          <h2 ref="demoTitle" class="reveal text-4xl font-black tracking-tight sm:text-5xl md:text-6xl">
            看 EduAgent<br class="hidden sm:block" />
            <span class="gradient-text">如何工作。</span>
          </h2>
          <p ref="demoSubtitle" class="reveal mx-auto mt-4 max-w-2xl text-lg font-light text-text-secondary" style="transition-delay: 100ms;">
            从提问到生成个性化资源，多个智能体在毫秒级时间内完成协作编排。
          </p>
        </div>

        <!-- Demo stage -->
        <div ref="demoStage" class="reveal relative mx-auto aspect-[16/9] w-full max-w-5xl overflow-hidden rounded-[40px] border border-subtle bg-space-panel/70 shadow-2xl backdrop-blur-xl" style="transition-delay: 200ms;">
          <div class="absolute inset-0 p-6 md:p-12">
            <!-- ── 学习者节点 ── -->
            <div class="demo-node demo-node--student absolute left-[6%] top-1/2 -translate-y-1/2">
              <div class="flex flex-col items-center gap-3">
                <div class="demo-avatar flex h-14 w-14 items-center justify-center rounded-full bg-card shadow-lg md:h-16 md:w-16">
                  <div class="demo-ring demo-ring--primary" />
                  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="relative z-10 text-text-primary">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                  </svg>
                </div>
                <span class="text-xs font-medium text-text-secondary">学习者</span>
                <!-- 提问气泡 -->
                <div class="demo-speech absolute -right-20 top-0 rounded-2xl rounded-bl-md border border-primary/20 bg-primary-soft/80 px-3 py-2 text-[10px] leading-relaxed text-primary backdrop-blur-sm whitespace-nowrap">
                  什么是动态规划？
                </div>
              </div>
            </div>

            <!-- ── 智能体集群 (中心列) ── -->
            <div class="demo-node demo-node--agent absolute left-[48%] top-[12%] -translate-x-1/2">
              <div class="flex flex-col items-center gap-3">
                <div class="flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/30 bg-primary-soft md:h-16 md:w-16 relative">
                  <div class="demo-ring demo-ring--primary" />
                  <IconDoc :size="24" class="relative z-10 text-primary md:w-[26px]" />
                </div>
                <span class="text-[11px] font-semibold text-primary">文档智能体</span>
                <span class="text-[10px] text-text-muted -mt-2">生成概念导图</span>
              </div>
            </div>

            <div class="demo-node demo-node--agent absolute left-[48%] top-[44%] -translate-x-1/2 -translate-y-1/2">
              <div class="flex flex-col items-center gap-3">
                <div class="flex h-[72px] w-[72px] items-center justify-center rounded-2xl border border-secondary/30 bg-secondary-soft md:h-20 md:w-20 relative">
                  <div class="demo-ring demo-ring--secondary" />
                  <IconChat :size="28" class="relative z-10 text-secondary md:w-[30px]" />
                </div>
                <span class="text-[11px] font-semibold text-secondary">辅导智能体</span>
                <span class="text-[10px] text-text-muted -mt-2">苏格拉底式对话</span>
              </div>
            </div>

            <div class="demo-node demo-node--agent absolute left-[48%] bottom-[12%] -translate-x-1/2">
              <div class="flex flex-col items-center gap-3">
                <div class="flex h-14 w-14 items-center justify-center rounded-2xl border border-tertiary/30 bg-tertiary-soft md:h-16 md:w-16 relative">
                  <div class="demo-ring demo-ring--tertiary" />
                  <IconQuiz :size="24" class="relative z-10 text-tertiary md:w-[26px]" />
                </div>
                <span class="text-[11px] font-semibold text-tertiary">评估智能体</span>
                <span class="text-[10px] text-text-muted -mt-2">诊断测验 & 能力更新</span>
              </div>
            </div>

            <!-- ── 资源画布输出 ── -->
            <div class="demo-node demo-node--output absolute right-[5%] top-1/2 -translate-y-1/2">
              <div class="flex flex-col items-center gap-3">
                <div class="demo-canvas-grid grid w-[130px] gap-2 md:w-[150px]">
                  <div class="demo-canvas-card demo-canvas-card--1 h-14 rounded-xl border border-primary/20 bg-primary-soft p-2 md:h-16">
                    <div class="flex h-full items-center gap-2 rounded-lg bg-card/50 px-2">
                      <div class="h-2 w-2 rounded-full bg-primary" />
                      <div class="h-2 flex-1 rounded bg-primary/20" />
                    </div>
                  </div>
                  <div class="grid grid-cols-2 gap-2">
                    <div class="demo-canvas-card demo-canvas-card--2 h-12 rounded-xl border border-info/20 bg-info-soft p-2 md:h-14">
                      <div class="flex h-full items-center gap-1.5 rounded-lg bg-card/50 px-1.5">
                        <div class="h-1.5 w-1.5 rounded-full bg-info" />
                        <div class="h-1.5 w-full rounded bg-info/20" />
                      </div>
                    </div>
                    <div class="demo-canvas-card demo-canvas-card--3 h-12 rounded-xl border border-secondary/20 bg-secondary-soft p-2 md:h-14">
                      <div class="flex h-full items-center gap-1.5 rounded-lg bg-card/50 px-1.5">
                        <div class="h-1.5 w-1.5 rounded-full bg-secondary" />
                        <div class="h-1.5 w-full rounded bg-secondary/20" />
                      </div>
                    </div>
                  </div>
                </div>
                <span class="text-xs font-medium text-text-secondary">资源画布</span>
                <span class="text-[10px] text-success -mt-2">资源装配完成 ✓</span>
              </div>
            </div>

            <!-- ═══════════════════════════════════════════════════ -->
            <!-- SVG 连线 + 数据流动画                              -->
            <!-- ═══════════════════════════════════════════════════ -->
            <svg class="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid meet">
              <defs>
                <linearGradient id="linePrimary" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.5" />
                  <stop offset="100%" stop-color="var(--color-secondary)" stop-opacity="0.5" />
                </linearGradient>
                <linearGradient id="lineSecondary" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stop-color="var(--color-secondary)" stop-opacity="0.5" />
                  <stop offset="100%" stop-color="var(--color-tertiary)" stop-opacity="0.5" />
                </linearGradient>
                <linearGradient id="lineOutput" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stop-color="var(--color-primary)" stop-opacity="0.4" />
                  <stop offset="100%" stop-color="var(--color-success)" stop-opacity="0.4" />
                </linearGradient>
                <!-- 数据包发光滤镜 -->
                <filter id="packetGlow">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
                </filter>
              </defs>

              <!-- 结构连线 -->
              <path class="demo-line" d="M 70 280 Q 260 160 480 108" fill="none" stroke="url(#linePrimary)" stroke-width="2" opacity="0.5" />
              <path class="demo-line" d="M 70 280 Q 260 280 480 280" fill="none" stroke="url(#linePrimary)" stroke-width="2.5" opacity="0.55" />
              <path class="demo-line" d="M 70 280 Q 260 400 480 452" fill="none" stroke="url(#lineSecondary)" stroke-width="2" opacity="0.5" />
              <path class="demo-line" d="M 480 108 Q 700 170 930 240" fill="none" stroke="url(#lineOutput)" stroke-width="2" opacity="0.45" />
              <path class="demo-line" d="M 480 280 Q 700 280 930 280" fill="none" stroke="url(#lineOutput)" stroke-width="2.5" opacity="0.5" />
              <path class="demo-line" d="M 480 452 Q 700 390 930 320" fill="none" stroke="url(#lineSecondary)" stroke-width="2" opacity="0.45" />

              <!-- 数据包动画粒子 (沿路径运动) -->
              <circle r="4" fill="var(--color-primary)" filter="url(#packetGlow)" class="packet packet--p1" />
              <circle r="5" fill="var(--color-secondary)" filter="url(#packetGlow)" class="packet packet--p2" />
              <circle r="4" fill="var(--color-tertiary)" filter="url(#packetGlow)" class="packet packet--p3" />
              <circle r="3.5" fill="var(--color-primary)" filter="url(#packetGlow)" class="packet packet--p4" />
              <circle r="5" fill="var(--color-success)" filter="url(#packetGlow)" class="packet packet--p5" />
              <circle r="4" fill="var(--color-secondary)" filter="url(#packetGlow)" class="packet packet--p6" />
              <circle r="3" fill="var(--color-info)" filter="url(#packetGlow)" class="packet packet--p7" />
              <circle r="4.5" fill="var(--color-tertiary)" filter="url(#packetGlow)" class="packet packet--p8" />
            </svg>

            <!-- 浮动粒子 -->
            <div class="demo-particles" aria-hidden="true">
              <div class="fp fp--1" />
              <div class="fp fp--2" />
              <div class="fp fp--3" />
              <div class="fp fp--4" />
              <div class="fp fp--5" />
              <div class="fp fp--6" />
              <div class="fp fp--7" />
              <div class="fp fp--8" />
              <div class="fp fp--9" />
              <div class="fp fp--10" />
            </div>
          </div>
        </div>

        <!-- Demo steps -->
        <div ref="demoSteps" class="mt-12 grid grid-cols-1 gap-6 md:grid-cols-3">
          <div v-for="(step, idx) in demoStepsList" :key="step.title" class="reveal rounded-2xl border border-subtle bg-card p-6 text-center transition-all duration-300 hover:-translate-y-1 hover:border-primary/20" :style="{ transitionDelay: `${300 + idx * 100}ms` }">
            <div class="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full border border-subtle bg-space-surface text-sm font-bold text-primary">
              {{ idx + 1 }}
            </div>
            <h4 class="text-base font-bold">{{ step.title }}</h4>
            <p class="mt-2 text-sm font-light text-text-secondary">{{ step.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Architecture section -->
    <section id="architecture" class="py-32 px-6">
      <div class="mx-auto max-w-6xl">
        <div class="mb-16 text-center">
          <p class="reveal mb-4 text-xs font-bold uppercase tracking-[0.2em] text-primary">系统架构</p>
          <h2 class="reveal text-4xl font-black tracking-tight sm:text-5xl md:text-6xl">
            多智能体<br class="hidden sm:block" />
            <span class="gradient-text">协同编排。</span>
          </h2>
        </div>

        <div class="reveal grid gap-5 md:grid-cols-3">
          <div class="rounded-[28px] border border-subtle bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-card">
            <div class="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-primary-soft text-primary">
              <IconDoc :size="22" />
            </div>
            <h3 class="text-lg font-bold">文档智能体</h3>
            <p class="mt-2 text-sm font-light leading-relaxed text-text-secondary">
              负责生成概念导图、代码示例与视频摘要，将复杂知识点结构化呈现。
            </p>
          </div>
          <div class="rounded-[28px] border border-subtle bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-card">
            <div class="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-secondary-soft text-secondary">
              <IconChat :size="22" />
            </div>
            <h3 class="text-lg font-bold">辅导智能体</h3>
            <p class="mt-2 text-sm font-light leading-relaxed text-text-secondary">
              通过苏格拉底式对话引导学生思考，根据掌握度动态调整解释深度。
            </p>
          </div>
          <div class="rounded-[28px] border border-subtle bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-card">
            <div class="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-tertiary-soft text-tertiary">
              <IconQuiz :size="22" />
            </div>
            <h3 class="text-lg font-bold">评估智能体</h3>
            <p class="mt-2 text-sm font-light leading-relaxed text-text-secondary">
              生成诊断测验、分析错题模式，并将结果反馈到能力雷达与路径推荐。
            </p>
          </div>
        </div>

        <div class="reveal mt-8 rounded-[32px] border border-subtle bg-space-panel/50 p-8 shadow-glass backdrop-blur-xl" style="transition-delay: 150ms;">
          <div class="grid items-center gap-8 lg:grid-cols-2">
            <div>
              <h3 class="text-2xl font-bold tracking-tight">后端技术栈</h3>
              <p class="mt-3 text-base font-light leading-relaxed text-text-secondary">
                基于 Python 与 Elasticsearch 构建知识库，使用 LangGraph 编排多智能体工作流，通过 RESTful API 与前端实时通信。
              </p>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="rounded-xl border border-subtle bg-card px-4 py-3 text-sm font-medium text-text-secondary">Python / FastAPI</div>
              <div class="rounded-xl border border-subtle bg-card px-4 py-3 text-sm font-medium text-text-secondary">LangGraph</div>
              <div class="rounded-xl border border-subtle bg-card px-4 py-3 text-sm font-medium text-text-secondary">Elasticsearch</div>
              <div class="rounded-xl border border-subtle bg-card px-4 py-3 text-sm font-medium text-text-secondary">OpenAI / LLM</div>
              <div class="rounded-xl border border-subtle bg-card px-4 py-3 text-sm font-medium text-text-secondary">Vue 3 + Vite</div>
              <div class="rounded-xl border border-subtle bg-card px-4 py-3 text-sm font-medium text-text-secondary">Tailwind CSS</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Testimonials -->
    <section class="relative py-24 px-6">
      <div class="pointer-events-none absolute inset-0">
        <div class="absolute bottom-0 left-1/2 h-[60vh] w-[80vh] -translate-x-1/2 rounded-full bg-secondary/5 blur-[120px]" />
      </div>
      <div class="relative mx-auto max-w-6xl">
        <h2 class="reveal mb-16 text-center text-3xl font-black tracking-tight sm:text-4xl md:text-5xl">
          学习者<br class="hidden sm:block" />
          <span class="gradient-text">怎么说。</span>
        </h2>
        <div class="grid gap-5 md:grid-cols-3">
          <div v-for="(t, idx) in testimonials" :key="t.name" class="reveal rounded-[28px] border border-subtle bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-card" :style="{ transitionDelay: `${idx * 100}ms` }">
            <div class="mb-4 flex gap-1">
              <span v-for="s in 5" :key="s" class="text-warning">★</span>
            </div>
            <p class="text-sm font-light leading-relaxed text-text-secondary">{{ t.quote }}</p>
            <div class="mt-6 flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-primary-soft text-sm font-bold text-primary">
                {{ t.initials }}
              </div>
              <div>
                <p class="text-sm font-semibold">{{ t.name }}</p>
                <p class="text-xs text-text-muted">{{ t.role }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Stats / highlights -->
    <section id="highlights" class="py-24 px-6">
      <div class="mx-auto max-w-6xl">
        <div class="grid grid-cols-2 gap-8 md:grid-cols-4">
          <div
            v-for="(stat, idx) in stats"
            :key="stat.label"
            class="reveal text-center"
            :style="{ transitionDelay: `${idx * 100}ms` }"
          >
            <div class="text-4xl font-black tracking-tight text-primary sm:text-5xl md:text-6xl">
              <span v-if="stat.isNumeric">{{ displayedStats[idx] }}</span>
              <span v-else>{{ stat.value }}</span>
              <span v-if="stat.suffix" class="text-2xl md:text-3xl">{{ stat.suffix }}</span>
            </div>
            <div class="mt-2 text-sm font-medium uppercase tracking-wider text-text-muted">{{ stat.label }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- FAQ -->
    <section id="faq" class="py-24 px-6">
      <div class="mx-auto max-w-3xl">
        <div class="mb-16 text-center">
          <p class="reveal mb-4 text-xs font-bold uppercase tracking-[0.2em] text-primary">常见问题</p>
          <h2 class="reveal text-3xl font-black tracking-tight sm:text-4xl md:text-5xl">
            还有疑问？<br class="hidden sm:block" />
            <span class="gradient-text">我们来解答。</span>
          </h2>
        </div>

        <div class="space-y-4">
          <div
            v-for="(faq, idx) in faqs"
            :key="idx"
            class="reveal overflow-hidden rounded-2xl border border-subtle bg-card transition-all duration-300"
            :class="openFaq === idx ? 'border-primary/20' : 'hover:border-hover'"
            :style="{ transitionDelay: `${idx * 80}ms` }"
          >
            <button
              type="button"
              class="flex w-full items-center justify-between px-6 py-5 text-left"
              @click="toggleFaq(idx)"
            >
              <span class="text-base font-semibold">{{ faq.q }}</span>
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                class="text-text-muted transition-transform duration-300"
                :class="openFaq === idx ? 'rotate-45' : ''"
              >
                <path d="M12 5v14M5 12h14" />
              </svg>
            </button>
            <div
              class="overflow-hidden transition-all duration-300"
              :style="{ maxHeight: openFaq === idx ? '200px' : '0px', opacity: openFaq === idx ? 1 : 0 }"
            >
              <p class="px-6 pb-5 text-sm font-light leading-relaxed text-text-secondary">{{ faq.a }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA footer -->
    <section class="relative py-32 px-6">
      <div class="pointer-events-none absolute inset-0 overflow-hidden">
        <div class="absolute bottom-0 left-1/2 h-[60vh] w-[80vh] -translate-x-1/2 rounded-full bg-primary/10 blur-[120px]" />
      </div>
      <div class="relative mx-auto max-w-4xl text-center">
        <h2 ref="ctaTitle" class="reveal text-4xl font-black tracking-tight sm:text-5xl md:text-6xl">
          准备好开始你的<br class="hidden sm:block" />
          <span class="gradient-text">算法之旅了吗？</span>
        </h2>
        <p ref="ctaSubtitle" class="reveal mx-auto mt-6 max-w-xl text-lg font-light text-text-secondary" style="transition-delay: 100ms;">
          无需配置，一键进入多智能体学习工作台。
        </p>
        <div ref="ctaButtons" class="reveal mt-10 flex flex-wrap items-center justify-center gap-4" style="transition-delay: 200ms;">
          <button
            type="button"
            class="focus-ring btn-capsule px-10 py-4 text-base"
            @click="enterApp"
          >
            立即体验
          </button>
          <button
            type="button"
            class="focus-ring rounded-full border border-subtle bg-card px-8 py-4 text-base font-medium text-text-secondary transition-all duration-200 hover:border-primary/30 hover:text-primary hover:bg-card-hover"
            @click="enterApp"
          >
            登录账户
          </button>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer class="border-t border-subtle py-12 px-6">
      <div class="mx-auto max-w-6xl">
        <div class="grid gap-8 md:grid-cols-4">
          <div>
            <div class="flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary to-secondary text-[10px] font-black text-primary-text">
                EA
              </div>
              <span class="text-lg font-bold tracking-tight">EduAgent</span>
            </div>
            <p class="mt-4 text-sm font-light leading-relaxed text-text-secondary">
              个性化多智能体学习系统，专注于数据结构与算法教育。
            </p>
          </div>
          <div>
            <h4 class="mb-4 text-xs font-bold uppercase tracking-wider text-text-muted">产品</h4>
            <ul class="space-y-2 text-sm text-text-secondary">
              <li><a href="#curriculum" class="transition-colors hover:text-text-primary">知识体系</a></li>
              <li><a href="#features" class="transition-colors hover:text-text-primary">核心功能</a></li>
              <li><a href="#comparison" class="transition-colors hover:text-text-primary">对比传统</a></li>
              <li><a href="#workflow" class="transition-colors hover:text-text-primary">使用流程</a></li>
            </ul>
          </div>
          <div>
            <h4 class="mb-4 text-xs font-bold uppercase tracking-wider text-text-muted">资源</h4>
            <ul class="space-y-2 text-sm text-text-secondary">
              <li><a href="#demo" class="transition-colors hover:text-text-primary">实时演示</a></li>
              <li><a href="#architecture" class="transition-colors hover:text-text-primary">系统架构</a></li>
              <li><a href="#faq" class="transition-colors hover:text-text-primary">常见问题</a></li>
              <li><a href="#" class="transition-colors hover:text-text-primary" @click.prevent="enterApp">进入工作台</a></li>
            </ul>
          </div>
          <div>
            <h4 class="mb-4 text-xs font-bold uppercase tracking-wider text-text-muted">联系</h4>
            <ul class="space-y-2 text-sm text-text-secondary">
              <li>EduAgent Team</li>
              <li>数据结构与算法智能学习工作台</li>
            </ul>
          </div>
        </div>
        <div class="mt-10 flex flex-col items-center justify-between gap-4 border-t border-subtle pt-6 md:flex-row">
          <p class="text-xs text-text-muted">© 2026 EduAgent. 多智能体学习系统。</p>
          <button
            type="button"
            class="focus-ring flex items-center gap-2 rounded-full border border-subtle bg-card px-4 py-2 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
            @click="scrollToTop"
          >
            回到顶部
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </button>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import IconCheck from "./icons/IconCheck.vue";
import IconChat from "./icons/IconChat.vue";
import IconDoc from "./icons/IconDoc.vue";
import IconExpand from "./icons/IconExpand.vue";
import IconQuiz from "./icons/IconQuiz.vue";
import IconRadar from "./icons/IconRadar.vue";
import IconSettings from "./icons/IconSettings.vue";
import IconTree from "./icons/IconTree.vue";
import RadarCanvas from "./RadarCanvas.vue";

const emit = defineEmits(["enter"]);

const navScrolled = ref(false);
const mobileMenuOpen = ref(false);
const scrollProgress = ref(0);
const openFaq = ref(null);
const displayedStats = ref([0, 0, 0, 0]);
const statsAnimated = ref(false);

// Template refs for immediate hero reveal
const heroEyebrow = ref(null);
const heroHeadline = ref(null);
const heroSubhead = ref(null);
const heroCtas = ref(null);
const heroPills = ref(null);
const heroVisual = ref(null);

const menuItems = [
  { href: "#curriculum", label: "知识体系" },
  { href: "#why", label: "为何选择" },
  { href: "#features", label: "功能" },
  { href: "#workflow", label: "流程" },
  { href: "#demo", label: "演示" },
  { href: "#architecture", label: "架构" },
  { href: "#faq", label: "FAQ" },
];

const knowledgeNodes = ["数组与链表", "栈与队列", "树与图", "动态规划"];
const radarDimensions = ["概念理解", "代码工程", "逻辑推理", "错题恢复", "时间管理"];

const curriculumModules = [
  { title: "线性结构", desc: "从数组、链表到栈与队列，掌握最基础的数据组织方式与复杂度分析。", icon: IconTree, accent: "primary", count: 8, tags: ["数组", "链表", "栈", "队列", "哈希表"] },
  { title: "树与图", desc: "二叉树、平衡树、堆、图的遍历与最短路径，构建非线性思维模型。", icon: IconExpand, accent: "secondary", count: 12, tags: ["二叉树", "堆", "Trie", "图遍历", "最短路径"] },
  { title: "算法策略", desc: "递归、分治、贪心、动态规划与回溯，系统掌握五大核心算法范式。", icon: IconSettings, accent: "tertiary", count: 10, tags: ["递归", "分治", "贪心", "DP", "回溯"] },
  { title: "排序与搜索", desc: "从冒泡到快速排序，从二分查找到 A*，理解效率的本质差异。", icon: IconQuiz, accent: "success", count: 7, tags: ["快排", "归并", "二分", "DFS", "BFS"] },
  { title: "高级专题", desc: "位运算、并查集、线段树与字符串匹配，冲刺高阶算法能力。", icon: IconRadar, accent: "warning", count: 6, tags: ["位运算", "并查集", "线段树", "KMP", "LRU"] },
  { title: "复杂度通识", desc: "时间与空间复杂度、均摊分析、NP 完全性，建立效率量化思维。", icon: IconDoc, accent: "info", count: 4, tags: ["Big O", "均摊", "P vs NP", "空间换时间"] },
];

const painPoints = [
  { title: "题海战术效率低", desc: "传统刷题平台只告诉你对错，却无法定位知识盲区与思维误区。", icon: IconQuiz },
  { title: "优质答疑难获得", desc: "搜索引擎答案良莠不齐，难以获得针对你当前水平的个性化解释。", icon: IconChat },
  { title: "学习进度难量化", desc: "缺乏系统性的能力评估，不知道自己在哪些维度上真正进步。", icon: IconRadar },
];

const comparisonRows = [
  { dimension: "学习路径", traditional: "统一题目列表，无个性化排序", eduagent: "基于冷启动画像动态编排递进路径" },
  { dimension: "答疑方式", traditional: "题解文章 / 评论区讨论", eduagent: "苏格拉底式追问引导，多智能体协作解释" },
  { dimension: "知识组织", traditional: "按标签或题号分类", eduagent: "结构化知识图谱，支持多维度关联探索" },
  { dimension: "能力评估", traditional: "通过率 / 排名百分比", eduagent: "五维能力雷达实时量化，短板一目了然" },
  { dimension: "资源形式", traditional: "题目 + 题解文本", eduagent: "概念导图 + 代码示例 + 视频摘要 + 互动练习" },
  { dimension: "难度适配", traditional: "Easy / Medium / Hard 固定标签", eduagent: "掌握度驱动动态调整，学透才解锁下一节点" },
  { dimension: "学习反馈", traditional: "Accept / Wrong Answer", eduagent: "错题模式分析，精准提示思维盲区与改进方向" },
];

const bentoCards = [
  { title: "冷启动测评", desc: "5 分钟快速定位你的知识起点，生成个性化学习画像。", icon: IconQuiz },
  { title: "多模态资源", desc: "概念导图、代码示例、视频摘要、互动练习一键装配。", icon: IconExpand },
  { title: "能力雷达", desc: "五维能力实时可视化，短板一目了然。", icon: IconRadar },
  { title: "对话辅导", desc: "苏格拉底式提问，引导你自主推导出答案。", icon: IconChat },
  { title: "知识路径", desc: "递进式节点解锁，学习进度像地图一样清晰。", icon: IconTree, span: "md:col-span-2 lg:col-span-2" },
  { title: "主题定制", desc: "深色、浅色主题自由切换，支持高对比度与字号调节。", icon: IconSettings },
];

const workflowSteps = [
  { title: "测评画像", desc: "通过冷启动测评与持续交互，系统构建你的专属学习画像。", icon: IconQuiz, accent: "primary" },
  { title: "路径推荐", desc: "基于画像与知识图谱，推荐最适合你当前水平的学习节点。", icon: IconTree, accent: "secondary" },
  { title: "多模态学习", desc: "在学习托盘中对话，在资源画布中查看概念导图、代码与测验。", icon: IconDoc, accent: "tertiary" },
  { title: "诊断提升", desc: "提交诊断测验后，能力雷达更新，系统动态调整后续路径。", icon: IconRadar, accent: "success" },
];

const demoStepsList = [
  { title: "提出疑问", desc: "在学习托盘中输入你的问题或困惑。" },
  { title: "智能体协作", desc: "多个专业智能体并行生成解释、示例与测验。" },
  { title: "资源装配", desc: "结果自动汇聚到资源画布，形成完整学习单元。" },
];

const stats = [
  { value: 6, suffix: "", label: "知识模块", isNumeric: true },
  { value: 47, suffix: "+", label: "递进式知识节点", isNumeric: true },
  { value: 5, suffix: "", label: "能力评估维度", isNumeric: true },
  { value: 3, suffix: "", label: "专业智能体协同", isNumeric: true },
];

const testimonials = [
  { quote: "以前刷了很多题还是感觉没体系，EduAgent 帮我理清了知识路径，每次对话都能问到点子上。", name: "张明", role: "计算机专业大三学生", initials: "ZM" },
  { quote: "辅导智能体不会直接给答案，而是引导我自己推导，这种苏格拉底式教学让我理解更深刻。", name: "李雪", role: "转码学习者", initials: "LX" },
  { quote: "能力雷达让我知道自己哪方面薄弱，针对性地补强后，算法面试通过率明显提高了。", name: "王浩", role: "应届求职者", initials: "WH" },
];

const faqs = [
  { q: "EduAgent 适合什么水平的学习者？", a: "无论你是零基础转码、在校学生还是准备算法面试的求职者，EduAgent 都会通过冷启动测评了解你的起点，并推荐匹配难度的学习路径。系统支持从数组基础到高级动态规划的完整难度跨度。" },
  { q: "对话辅导与直接看答案有什么区别？", a: "辅导智能体采用苏格拉底式提问，会根据你的回答不断调整引导方向，帮助你建立从问题到答案的完整思维链条，而不是简单记忆。这种方式在认知科学中被证明能显著提升长期记忆与迁移能力。" },
  { q: "知识图谱是如何构建的？", a: "知识图谱由 Elasticsearch 向量检索与 Neo4j 图数据库协同构建，覆盖数据结构与算法领域的核心概念及其依赖关系。每个知识节点都有明确的前置要求与掌握阈值。" },
  { q: "多模态资源包含哪些内容？", a: "每个知识节点会生成概念导图（视觉化知识结构）、代码示例（多语言可运行）、视频摘要（核心要点讲解）、互动练习与诊断测验，覆盖视觉、代码与测验多种学习形式。" },
  { q: "能力雷达的五个维度分别是什么？", a: "概念理解（理论掌握度）、代码工程（实现能力）、逻辑推理（问题分析）、错题恢复（从错误中学习的能力）和时间管理（学习效率），五个维度综合反映你的 DSA 学习状态。" },
  { q: "系统如何保证推荐的学习路径适合我？", a: "冷启动测评结合持续的行为数据（答题正确率、对话深度、停留时长等），由路径规划智能体动态调整节点顺序与难度。掌握的节点自动解锁后续依赖。" },
  { q: "数据是否会保存？", a: "你的学习画像、掌握度与能力雷达数据会安全保存在系统中，以便持续优化推荐策略。系统基于 JWT 双令牌认证保障账户安全。具体隐私策略请参见项目文档。" },
];

function enterApp() {
  emit("enter");
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function toggleFaq(idx) {
  openFaq.value = openFaq.value === idx ? null : idx;
}

function animateCountUp(targetValues, duration = 1500) {
  const startTime = performance.now();
  const startValues = displayedStats.value.slice();

  function step(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);

    displayedStats.value = targetValues.map((target, idx) => {
      if (typeof target !== "number") return 0;
      return Math.floor(startValues[idx] + (target - startValues[idx]) * eased);
    });

    if (progress < 1) {
      requestAnimationFrame(step);
    }
  }

  requestAnimationFrame(step);
}

function handleScroll() {
  const scrollTop = window.scrollY;
  const docHeight = document.documentElement.scrollHeight - window.innerHeight;
  navScrolled.value = scrollTop > 40;
  scrollProgress.value = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;

  const parallax = scrollTop * 0.12;
  if (heroVisual.value) {
    heroVisual.value.style.transform = `translateY(${parallax}px)`;
  }
}

function setupObserver() {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("revealed");
          observer.unobserve(entry.target);

          // Trigger stats count-up when highlights section is visible
          if (entry.target.closest("#highlights") && !statsAnimated.value) {
            statsAnimated.value = true;
            animateCountUp(stats.map((s) => (typeof s.value === "number" ? s.value : 0)));
          }
        }
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -60px 0px" },
  );

  const revealEls = document.querySelectorAll(".reveal");
  revealEls.forEach((el) => observer.observe(el));

  return observer;
}

let observer = null;
let scrollListener = null;

onMounted(() => {
  nextTick(() => {
    observer = setupObserver();
    scrollListener = () => handleScroll();
    window.addEventListener("scroll", scrollListener, { passive: true });

    // Trigger hero reveals immediately with stagger
    setTimeout(() => {
      [heroEyebrow.value, heroHeadline.value, heroSubhead.value, heroCtas.value, heroPills.value, heroVisual.value].forEach((el) => {
        if (el) el.classList.add("revealed");
      });
    }, 100);
  });
});

onBeforeUnmount(() => {
  if (observer) observer.disconnect();
  if (scrollListener) window.removeEventListener("scroll", scrollListener);
});
</script>

<style scoped>
.landing-root {
  scroll-behavior: smooth;
}

.reveal {
  opacity: 0;
  transform: translateY(28px);
  transition: opacity 0.8s cubic-bezier(0.16, 1, 0.3, 1), transform 0.8s cubic-bezier(0.16, 1, 0.3, 1);
}

.revealed {
  opacity: 1;
  transform: translateY(0);
}

/* Float animations */
@keyframes float-slow {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-12px); }
}

@keyframes float-medium {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

@keyframes float-fast {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

.animate-float-slow {
  animation: float-slow 5s ease-in-out infinite;
}

.animate-float-medium {
  animation: float-medium 4s ease-in-out infinite;
}

.animate-float-fast {
  animation: float-fast 3.5s ease-in-out infinite;
}

.animate-bounce-subtle {
  animation: float-slow 2.5s ease-in-out infinite;
}

/* Marquee */
@keyframes marquee {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}

.animate-marquee {
  animation: marquee 28s linear infinite;
}

/* ═══════════════════════════════════════════════════════════════════════ */
/* Demo Stage — Multi-Agent Collaborative Animation Engine               */
/* ═══════════════════════════════════════════════════════════════════════ */

/* ── 结构连线 ── */
.demo-line {
  stroke-dasharray: 6 8;
  animation: dash-flow 2s linear infinite;
}

@keyframes dash-flow {
  0% { stroke-dashoffset: 28; }
  100% { stroke-dashoffset: 0; }
}

/* ── 智能体节点顺序入场 ── */
.demo-node {
  opacity: 0;
  transform: scale(0.88);
  animation: demo-node-in 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

.demo-node--student { animation-delay: 0.2s; }
.demo-node--agent:nth-of-type(2) { animation-delay: 0.4s; }
.demo-node--agent:nth-of-type(3) { animation-delay: 0.6s; }
.demo-node--agent:nth-of-type(4) { animation-delay: 0.8s; }
.demo-node--output { animation-delay: 1.0s; }

@keyframes demo-node-in {
  to { opacity: 1; transform: scale(1); }
}

/* ── 环形呼吸激活指示器 ── */
.demo-ring {
  position: absolute;
  inset: -6px;
  border-radius: inherit;
  border: 1.5px solid transparent;
  opacity: 0;
}

.demo-ring--primary {
  border-color: var(--color-primary);
  box-shadow: 0 0 18px var(--color-primary-soft);
  animation: ring-breathe 2.8s ease-in-out infinite;
  animation-delay: 0.8s;
}

.demo-ring--secondary {
  border-color: var(--color-secondary);
  box-shadow: 0 0 22px var(--color-secondary-soft);
  animation: ring-breathe 2.8s ease-in-out infinite;
  animation-delay: 1.4s;
}

.demo-ring--tertiary {
  border-color: var(--color-tertiary);
  box-shadow: 0 0 18px var(--color-tertiary-soft);
  animation: ring-breathe 2.8s ease-in-out infinite;
  animation-delay: 2.0s;
}

@keyframes ring-breathe {
  0%, 100% { opacity: 0.25; transform: scale(1); }
  50% { opacity: 0.8; transform: scale(1.12); }
}

/* ── 学生提问气泡 ── */
.demo-speech {
  opacity: 0;
  transform: translateX(-8px);
  animation: speech-in 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  animation-delay: 1.2s;
}

@keyframes speech-in {
  to { opacity: 1; transform: translateX(0); }
}

/* ── 资源画布卡片逐序出现 ── */
.demo-canvas-card {
  opacity: 0;
  transform: translateX(12px);
  animation: card-slide-in 0.55s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

.demo-canvas-card--1 { animation-delay: 1.6s; }
.demo-canvas-card--2 { animation-delay: 1.85s; }
.demo-canvas-card--3 { animation-delay: 2.1s; }

@keyframes card-slide-in {
  to { opacity: 1; transform: translateX(0); }
}

/* ── SVG 数据包运动粒子 ── */
.packet {
  opacity: 0;
}

/* P1: 学生 → 文档智能体 (上路径) */
.packet--p1 {
  animation: packet-path-1 3.2s ease-in-out infinite;
  animation-delay: 1.4s;
}

@keyframes packet-path-1 {
  0%   { opacity: 0; transform: translate(70px, 280px); }
  8%   { opacity: 1; }
  40%  { opacity: 1; transform: translate(260px, 190px); }
  48%  { opacity: 1; transform: translate(480px, 108px); }
  52%  { opacity: 0; transform: translate(480px, 108px); }
  100% { opacity: 0; transform: translate(480px, 108px); }
}

/* P2: 学生 → 辅导智能体 (中路径) */
.packet--p2 {
  animation: packet-path-2 3.4s ease-in-out infinite;
  animation-delay: 2.2s;
}

@keyframes packet-path-2 {
  0%   { opacity: 0; transform: translate(70px, 280px); }
  8%   { opacity: 1; }
  40%  { opacity: 1; transform: translate(260px, 280px); }
  48%  { opacity: 1; transform: translate(480px, 280px); }
  52%  { opacity: 0; transform: translate(480px, 280px); }
  100% { opacity: 0; transform: translate(480px, 280px); }
}

/* P3: 学生 → 评估智能体 (下路径) */
.packet--p3 {
  animation: packet-path-3 3.6s ease-in-out infinite;
  animation-delay: 3.0s;
}

@keyframes packet-path-3 {
  0%   { opacity: 0; transform: translate(70px, 280px); }
  8%   { opacity: 1; }
  40%  { opacity: 1; transform: translate(260px, 375px); }
  48%  { opacity: 1; transform: translate(480px, 452px); }
  52%  { opacity: 0; transform: translate(480px, 452px); }
  100% { opacity: 0; transform: translate(480px, 452px); }
}

/* P4: 文档智能体 → 资源画布 (上) */
.packet--p4 {
  animation: packet-path-4 3.0s ease-in-out infinite;
  animation-delay: 2.0s;
}

@keyframes packet-path-4 {
  0%   { opacity: 0; transform: translate(480px, 108px); }
  10%  { opacity: 1; }
  45%  { opacity: 1; transform: translate(700px, 175px); }
  52%  { opacity: 0.6; transform: translate(930px, 240px); }
  60%  { opacity: 0; transform: translate(930px, 240px); }
  100% { opacity: 0; transform: translate(930px, 240px); }
}

/* P5: 辅导智能体 → 资源画布 (中, 粗) */
.packet--p5 {
  animation: packet-path-5 3.0s ease-in-out infinite;
  animation-delay: 2.8s;
}

@keyframes packet-path-5 {
  0%   { opacity: 0; transform: translate(480px, 280px); }
  10%  { opacity: 1; }
  45%  { opacity: 1; transform: translate(700px, 280px); }
  52%  { opacity: 0.6; transform: translate(930px, 280px); }
  60%  { opacity: 0; transform: translate(930px, 280px); }
  100% { opacity: 0; transform: translate(930px, 280px); }
}

/* P6: 评估智能体 → 资源画布 (下) */
.packet--p6 {
  animation: packet-path-6 3.2s ease-in-out infinite;
  animation-delay: 3.6s;
}

@keyframes packet-path-6 {
  0%   { opacity: 0; transform: translate(480px, 452px); }
  10%  { opacity: 1; }
  45%  { opacity: 1; transform: translate(700px, 400px); }
  52%  { opacity: 0.6; transform: translate(930px, 320px); }
  60%  { opacity: 0; transform: translate(930px, 320px); }
  100% { opacity: 0; transform: translate(930px, 320px); }
}

/* P7: 反向 — 评估智能体反馈给辅导智能体 */
.packet--p7 {
  animation: packet-path-7 3.8s ease-in-out infinite;
  animation-delay: 4.4s;
}

@keyframes packet-path-7 {
  0%   { opacity: 0; transform: translate(480px, 452px); }
  10%  { opacity: 1; }
  35%  { opacity: 1; transform: translate(480px, 370px); }
  45%  { opacity: 0.5; transform: translate(480px, 280px); }
  55%  { opacity: 0; transform: translate(480px, 280px); }
  100% { opacity: 0; transform: translate(480px, 280px); }
}

/* P8: 资源画布完成脉冲 */
.packet--p8 {
  animation: packet-pulse 2.4s ease-in-out infinite;
  animation-delay: 3.2s;
}

@keyframes packet-pulse {
  0%   { opacity: 0; transform: translate(930px, 280px) scale(1); }
  10%  { opacity: 1; transform: translate(930px, 280px) scale(1.6); }
  30%  { opacity: 0.5; transform: translate(930px, 280px) scale(1); }
  50%  { opacity: 0.8; transform: translate(930px, 280px) scale(1.4); }
  70%  { opacity: 0.3; transform: translate(930px, 280px) scale(1); }
  100% { opacity: 0; transform: translate(930px, 280px) scale(1); }
}

/* ═══════════════════════════════════════════════════════════════════════ */
/* Floating Particles — Ambient Free-Float System                        */
/* ═══════════════════════════════════════════════════════════════════════ */
.fp {
  position: absolute;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  opacity: 0;
  pointer-events: none;
}

.fp--1 {
  background: var(--color-primary);
  box-shadow: 0 0 12px var(--color-primary), 0 0 24px var(--color-primary-soft);
  animation: fp-float-1 6s ease-in-out infinite;
}

.fp--2 {
  background: var(--color-secondary);
  box-shadow: 0 0 14px var(--color-secondary), 0 0 28px var(--color-secondary-soft);
  animation: fp-float-2 7s ease-in-out infinite 0.8s;
  width: 5px; height: 5px;
}

.fp--3 {
  background: var(--color-tertiary);
  box-shadow: 0 0 10px var(--color-tertiary);
  animation: fp-float-3 5.5s ease-in-out infinite 1.6s;
  width: 3px; height: 3px;
}

.fp--4 {
  background: var(--color-success);
  box-shadow: 0 0 10px var(--color-success), 0 0 20px var(--color-success-soft);
  animation: fp-float-4 6.5s ease-in-out infinite 2.4s;
  width: 5px; height: 5px;
}

.fp--5 {
  background: var(--color-info);
  box-shadow: 0 0 12px var(--color-info);
  animation: fp-float-1 5.8s ease-in-out infinite 3.2s;
  width: 4px; height: 4px;
}

.fp--6 {
  background: var(--color-primary);
  box-shadow: 0 0 9px var(--color-primary-light);
  animation: fp-float-2 6.2s ease-in-out infinite 1.2s;
  width: 3px; height: 3px;
}

.fp--7 {
  background: var(--color-secondary);
  box-shadow: 0 0 11px var(--color-secondary-light);
  animation: fp-float-3 5.2s ease-in-out infinite 4.0s;
  width: 4px; height: 4px;
}

.fp--8 {
  background: var(--color-tertiary);
  box-shadow: 0 0 8px var(--color-tertiary-light);
  animation: fp-float-4 6.8s ease-in-out infinite 2.0s;
  width: 3px; height: 3px;
}

.fp--9 {
  background: var(--color-warning);
  box-shadow: 0 0 10px var(--color-warning);
  animation: fp-float-1 5.5s ease-in-out infinite 4.8s;
  width: 4px; height: 4px;
}

.fp--10 {
  background: var(--color-success);
  box-shadow: 0 0 14px var(--color-success-soft);
  animation: fp-float-2 7.2s ease-in-out infinite 3.6s;
  width: 5px; height: 5px;
}

@keyframes fp-float-1 {
  0%   { opacity: 0; left: 15%; top: 65%; }
  10%  { opacity: 0.9; }
  45%  { opacity: 0.6; left: 55%; top: 20%; }
  90%  { opacity: 0; left: 88%; top: 35%; }
  100% { opacity: 0; left: 88%; top: 35%; }
}

@keyframes fp-float-2 {
  0%   { opacity: 0; left: 12%; top: 48%; }
  10%  { opacity: 0.85; }
  50%  { opacity: 0.5; left: 52%; top: 55%; }
  90%  { opacity: 0; left: 90%; top: 52%; }
  100% { opacity: 0; left: 90%; top: 52%; }
}

@keyframes fp-float-3 {
  0%   { opacity: 0; left: 18%; top: 72%; }
  10%  { opacity: 0.8; }
  48%  { opacity: 0.55; left: 50%; top: 78%; }
  90%  { opacity: 0; left: 85%; top: 68%; }
  100% { opacity: 0; left: 85%; top: 68%; }
}

@keyframes fp-float-4 {
  0%   { opacity: 0; left: 10%; top: 30%; }
  10%  { opacity: 0.9; }
  42%  { opacity: 0.5; left: 48%; top: 15%; }
  88%  { opacity: 0; left: 92%; top: 25%; }
  100% { opacity: 0; left: 92%; top: 25%; }
}

/* Fade transition for mobile menu */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 250ms ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
