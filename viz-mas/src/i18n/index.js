// Tiny reactive i18n.
//
// Reactive `lang` ref (zh | en) backed by localStorage. `t(key)` resolves a
// dot-path against the active locale's dictionary. Provided globally via
// App.vue so descendants can `inject('t')`.
//
// Strings are intentionally English-language-source-of-truth: when adding a
// new key, write the EN value first, then the ZH translation. Missing keys
// fall back to the EN string, then to the raw key.

import { ref, watch, computed } from 'vue'

const KEY = 'cmgpd-lang'
export const lang = ref(localStorage.getItem(KEY) || 'zh')
watch(lang, v => { try { localStorage.setItem(KEY, v) } catch {} })

export function setLang(v) { if (v === 'zh' || v === 'en') lang.value = v }
export function toggleLang() { lang.value = lang.value === 'zh' ? 'en' : 'zh' }

// MAS prompts and LLM-emitted text intentionally NOT translated — those run
// against an English-trained Qwen prompt template at the backend.
const messages = {
  en: {
    titlebar: {
      year: 'YEAR',
      reset: 'Reset',
      backendOk: 'backend ok',
      backendStatic: 'static data',
      keyTooltipSet: 'DashScope API key set',
      keyTooltipMissing: 'Set DashScope API key',
      model: 'model',
      dashscopeKey: 'DashScope key',
      save: 'Save',
      close: 'Close',
      langZh: '中',
      langEn: 'EN',
    },
    mode: {
      trainingPrefix: '🟢 training mode · ',
      trainingSuffix: ' (full GT) — F panel weight sliders adjustable, "save to cell" persists per-hex rule profiles',
      transferPrefix: '🔵 transfer mode · ',
      transferSuffix: ' (no GT) — F panel cell rules loaded from 1882; sliders read-only and feed MAS as soft prior',
    },
    panel: {
      v1: 'A: Overview',
      v2: 'B: Process View',
      v3: 'C: Embedding View',
      v4: 'D: Bipartite View',
      v5: 'E: MAS View',
      v6: 'F: Rules View',
    },
    fullscreen: 'Full screen',
    v1: {
      searchPlaceholder: 'person id (e.g. P101000)',
      find: 'find',
      cells: 'cell(s)',
      person: 'person',
      prevTitle: 'previous cell',
      nextTitle: 'next cell',
      cells_prefix: 'cells: ',
      dropped: 'pair(s) dropped by per-cell cap',
      notFound: 'not found in current cohort',
      everyDropped: 'every pair dropped by per-cell cap',
      idNotInCohort: 'id not in this cohort',
      // Eval-mode chart
      legendMas: 'MAS recall@1 vs accepted relations',
      legendHgtBaseline: 'HGT static baseline',
      footnoteEval: 'x-axis = cumulative # of relations accepted in this cohort (E ▶ arena accepts, manual overrides, auto-commits). y-axis = running fraction of accepted matches that hit the cohort\'s ground-truth wife. The dashed horizontal is HGT-only Hungarian recall@1 — the baseline you have to beat with the agent loop.',
      // Transfer-mode histogram
      legendHist: 'HGT pair score distribution',
      legendMean: 'cohort mean',
      footnoteTransfer: 'no GT in {year} — A summarises the HGT score distribution of every (husband, wife) pair in the current cohort. Higher density at high scores = the model is generally confident on this cohort; a fat low-end tail = many uncertain candidates that will need MAS deliberation. Vertical line marks the cohort mean; ticks at quartiles.',
      resetTitle: 'Clear the accept log + per-husband latest map (server-side)',
      resetBtn: '↺ reset',
    },
    v2: {
      accepted: 'accepted',
      showGt: 'show GT',
      showGtTitle: 'Reveal whether the accepted edge is the true r_hw (GT)',
      cols: { husband: 'husband', wife: 'wife', score: 'score', gap: 'gap', H: 'H.', GT: 'GT', source: 'source' },
      empty: 'no accepted matches yet — accept from D batch or E arena to log here',
      restoreBtn: '↶ restore',
    },
    v3: {
      modeHoneycomb: '⬢ honeycomb',
      modeScatter: '• scatter',
      modeMixed: '⬢• mixed',
      colorEval: '⚖ eval',
      colorDeploy: '↪ deploy',
      lasso: '◩ lasso',
      lassoOn: '◩ lasso on',
      hintHoneycomb: 'click a hex; cluster borders mark cluster boundaries',
      hintScatter: 'raw MDS embedding · click a dot · drag-lasso for multi-select',
      hintMixed: 'mixed: translucent hex aggregate + raw dots on top',
      legendGap: 'score gap',
      legendHgtScore: 'HGT score',
      legendTrainRef: 'train ref',
      lowTick: 'low',
      highTick: 'high',
      loadingEmbeddings: 'loading embeddings…',
      pairsPerHusband: 'Pairs per husband for the dot layer (1 = best-scoring; higher exposes hard negatives)',
      tooltipColorEval: 'eval mode (GT-aware): cell color = mean score_gap (red=wrong, green=right)',
      tooltipColorDeploy: 'deploy mode (GT-free): cell color = mean HGT score (sequential, confidence only — NOT correctness)',
      tooltipLegendGap: 'ψ(m,w_true) − ψ(m,w_best_neg) for positives; ψ(m,w_neg) − ψ(m,w_true) for hard-negs. Anchors saturate at ±2 logits.',
      tooltipLegendScore: 'HGT raw logit, GT-free. Anchors at the cohort min/max — sequential ramp, NOT a correctness signal.',
      tooltipLegendTrainRef: 'Background heatmap = training-cohort density',
      tooltipLasso: 'Drag-rectangle select → D',
    },
    v4: {
      pair: 'pair(s) · click a person',
      gapGt: 'gap ≥',
      batch: 'batch',
      noSelection: 'no selection — click a hex (C honeycomb) or a dot (C scatter)',
      profileFields: { sex: 'sex', birth: 'birth', banner: 'banner', region: 'region', community: 'community', household: 'household' },
    },
    v5: {
      arena: '▶ arena',
      gtOn: '👁 GT on',
      gtOff: '👁 GT off',
      gtTooltip: 'Reveal which candidate is the ground-truth wife',
      approveAdvance: 'Approve & Advance →',
      hintConsole: 'hint console · use',
      hintVerbs: '· verbs: boost / penalise / eliminate / accept',
      hintPlaceholder: '@c-P12345 boost: same banner, +2',
      send: 'send',
      noMessages: 'no messages',
      clickHusband: 'click a husband in C (hex / scatter) or B to load target',
      fetchingProfile: 'fetching profile…',
      cohort: 'cohort',
      topCandidates: 'top candidates',
      gtSpouse: 'GT spouse',
      gtSpouseMissing: 'GT spouse not in current candidates',
      noCandidates: 'no candidates yet — press ▶ arena to spin up the per-person agents',
      lifeBtn: '🔍 life',
      lifeTooltip: 'open life-history popup (events + income chart)',
      lifeTooltipTarget: 'open life-history popup for this husband',
      lifeHistory: 'life history',
      events: 'events',
      incomeYears: 'income years',
      finalRanking: 'final ranking · score = (s + t)/2 − λ·|s − t| · top',
      // Card actions
      accept: 'accept', eliminate: 'eliminate', boost: 'boost', penalise: 'penalise',
      conversation: 'conversation',
      noConversation: 'no conversation yet — round queries and answers will appear here',
      gtBadge: 'GT', negBadge: 'neg',
      gtBadgeTooltip: 'ground-truth wife in the cohort JSON',
      negBadgeTooltip: 'hard-negative candidate sampled within the cohort',
      directives: 'applied directives',
      // Popup
      popupClose: 'close',
      narrativeLoading: 'composing life narrative…',
      narrativeUnavailable: 'no narrative available',
      incomeTrajectory: 'income trajectory',
      rawEvents: 'raw event records',
    },
    v6: {
      macroFeatures: 'MACRO FEATURES',
      ruleWeights: 'RULE WEIGHTS',
      microMotifs: 'MICRO MOTIFS',
      ctxV5: 'V5 arena',
      ctxV4: 'V4 click',
      candidate: 'candidate(s)',
      cell: 'cell',
      bound: 'bound',
      lastSaved: 'last saved',
      unbound: 'unbound',
      saveBtn: '💾 save to cell',
      saveBtnSaving: '… saving',
      saveBtnTitle: "Aggregate per-husband rule sheets into this cell's rule profile (year 1882).",
      // RuleWeightsEditor
      sliderLabels: { paternal: 'paternal', siblings: 'siblings', household: 'household', banner: 'banner' },
      motifs: 'motifs',
      readonlyBanner: 'read-only · loaded from 1882 cell profile',
      selectHusbandRules: 'select a husband in D to set rule weights',
      // MotifMatchList
      selectHusbandMotifs: 'select a husband in D to detect motifs',
      noCandidatesMotifs: 'no candidates',
      noMotifsDetected: 'no motifs detected for any candidate',
      motifServiceUnavailable: 'motif service unavailable',
      scanningCandidates: 'scanning candidates… ({done}/{total} done)',
      matchedBy: 'matched_by:',
      // PairSimilarityBarChart
      selectHusbandSim: 'select a husband in D to see candidate similarity',
      // MacroCombinedChart
      grainAxis: 'grain price',
      disasterAxis: 'Disasters',
    },
  },
  zh: {
    titlebar: {
      year: '年份',
      reset: '重置',
      backendOk: '后端在线',
      backendStatic: '静态数据',
      keyTooltipSet: '已设置 DashScope API key',
      keyTooltipMissing: '设置 DashScope API key',
      model: '模型',
      dashscopeKey: 'DashScope 密钥',
      save: '保存',
      close: '关闭',
      langZh: '中',
      langEn: 'EN',
    },
    mode: {
      trainingPrefix: '🟢 训练模式 · ',
      trainingSuffix: '（完整 GT）— F 面板权重滑条可调，「保存至 cell」持久化每个六边形的规则档案',
      transferPrefix: '🔵 迁移模式 · ',
      transferSuffix: '（无 GT）— F 面板规则从 1882 载入；滑条只读，作为 MAS 的软先验',
    },
    panel: {
      v1: 'A：总览',
      v2: 'B：处理视图',
      v3: 'C：嵌入视图',
      v4: 'D：二部图',
      v5: 'E：MAS 协商',
      v6: 'F：规则视图',
    },
    fullscreen: '全屏',
    v1: {
      searchPlaceholder: '个体编号（如 P101000）',
      find: '查找',
      cells: '个 cell',
      person: '个体',
      prevTitle: '上一个 cell',
      nextTitle: '下一个 cell',
      cells_prefix: '所在 cell：',
      dropped: '对因 cell 容量上限被丢弃',
      notFound: '在当前 cohort 中未找到',
      everyDropped: '所有配对均因 cell 容量上限被丢弃',
      idNotInCohort: '该编号不在当前 cohort 中',
      legendMas: 'MAS recall@1 随 accept 数变化',
      legendHgtBaseline: 'HGT 静态基线',
      footnoteEval: '横轴：本 cohort 已 accept 的边数（来自 E ▶ arena、手动 override、自动 commit）。纵轴：accept 的边里命中真妻的比例。绿色虚线是仅用 HGT 跑匈牙利的 recall@1 — agent loop 必须超过它。',
      legendHist: 'HGT 配对得分分布',
      legendMean: 'cohort 均值',
      footnoteTransfer: '{year} 年无 GT — A 面板汇总当前 cohort 中每对（夫，妻）候选的 HGT 得分分布。高分密度高 = 模型整体对这一 cohort 有信心；低分长尾 = 大量不确定候选需 MAS 协商。竖直线为 cohort 均值，刻度线为四分位数。',
      resetTitle: '清除 accept 日志 + 每位 husband 的 latest map（服务端）',
      resetBtn: '↺ 重置',
    },
    v2: {
      accepted: '已 accept',
      showGt: '显示 GT',
      showGtTitle: '揭示 accept 的边是否为真实 r_hw（GT）',
      cols: { husband: '丈夫', wife: '妻子', score: '得分', gap: '边际', H: 'H.', GT: 'GT', source: '来源' },
      empty: '尚无 accept 的配对 — 在 D 批量或 E 协商中 accept 后将记录于此',
      restoreBtn: '↶ 恢复',
    },
    v3: {
      modeHoneycomb: '⬢ 蜂巢',
      modeScatter: '• 散点',
      modeMixed: '⬢• 混合',
      colorEval: '⚖ eval',
      colorDeploy: '↪ deploy',
      lasso: '◩ 套索',
      lassoOn: '◩ 套索（开）',
      hintHoneycomb: '点击 hex；簇间边线为聚类分界',
      hintScatter: '原始 MDS 嵌入 · 点击点位 · 拖拽框选',
      hintMixed: '混合：半透明 hex 聚合 + 原始点位叠加',
      legendGap: '得分边际',
      legendHgtScore: 'HGT 得分',
      legendTrainRef: '训练参考',
      lowTick: '低',
      highTick: '高',
      loadingEmbeddings: '加载 embeddings 中…',
      pairsPerHusband: '每位 husband 在散点层显示的 pair 数（1 = 最佳；越高越能暴露 hard-neg）',
      tooltipColorEval: 'eval 模式（依赖 GT）：cell 颜色 = score_gap 均值（红=判错，绿=判对）',
      tooltipColorDeploy: 'deploy 模式（无 GT）：cell 颜色 = HGT 原始得分均值（顺序色板，仅置信度，非正确性）',
      tooltipLegendGap: 'GT pair：ψ(m,w_true) − ψ(m,w_best_neg)；hard-neg：ψ(m,w_neg) − ψ(m,w_true)。锚点饱和在 ±2 logits。',
      tooltipLegendScore: 'HGT 原始 logit，无 GT。锚定在 cohort min/max — 顺序色板，非正确性信号。',
      tooltipLegendTrainRef: '背景热力图 = 训练集密度',
      tooltipLasso: '矩形拖拽选择 → D',
    },
    v4: {
      pair: '对 · 点击个体',
      gapGt: '边际 ≥',
      batch: '批量',
      noSelection: '尚未选择 — 在 C 蜂巢中点击 hex，或在 C 散点中点击点位',
      profileFields: { sex: '性别', birth: '生年', banner: '旗', region: '地区', community: '社区', household: '户' },
    },
    v5: {
      arena: '▶ 协商',
      gtOn: '👁 GT 开',
      gtOff: '👁 GT 关',
      gtTooltip: '显示哪一位候选是真实 GT',
      approveAdvance: '确认并进入下一轮 →',
      hintConsole: 'hint 控制台 · 使用',
      hintVerbs: '· 动词：boost / penalise / eliminate / accept',
      hintPlaceholder: '@c-P12345 boost: same banner, +2',
      send: '发送',
      noMessages: '无消息',
      clickHusband: '在 C（hex / 散点）或 B 中点击一位 husband 加载',
      fetchingProfile: '加载个体信息中…',
      cohort: 'cohort',
      topCandidates: '位候选',
      gtSpouse: 'GT 配偶',
      gtSpouseMissing: 'GT 配偶不在当前候选中',
      noCandidates: '尚无候选 — 按 ▶ 协商 启动 per-person agents',
      lifeBtn: '🔍 一生',
      lifeTooltip: '打开 life-history 弹窗（事件 + 收入图）',
      lifeTooltipTarget: '打开该 husband 的 life-history 弹窗',
      lifeHistory: '一生',
      events: '事件',
      incomeYears: '年收入记录',
      finalRanking: '最终排序 · score = (s + t)/2 − λ·|s − t| · 取前',
      accept: 'accept', eliminate: 'eliminate', boost: 'boost', penalise: 'penalise',
      conversation: '对话',
      noConversation: '尚无对话 — 各轮的提问与回答将显示在此',
      gtBadge: 'GT', negBadge: '负',
      gtBadgeTooltip: 'cohort JSON 中的真实妻子',
      negBadgeTooltip: '从 cohort 中采样的 hard-negative 候选',
      directives: '已应用的指令',
      popupClose: '关闭',
      narrativeLoading: '正在生成生平叙事…',
      narrativeUnavailable: '无可用叙事',
      incomeTrajectory: '收入轨迹',
      rawEvents: '原始事件记录',
    },
    v6: {
      macroFeatures: '宏观特征',
      ruleWeights: '规则权重',
      microMotifs: '微观图模',
      ctxV5: 'E 协商',
      ctxV4: 'D 点击',
      candidate: '位候选',
      cell: 'cell',
      bound: '已绑定',
      lastSaved: '上次保存',
      unbound: '未绑定',
      saveBtn: '💾 保存至 cell',
      saveBtnSaving: '… 保存中',
      saveBtnTitle: '将 per-husband 规则表合并为该 cell 的规则档案（1882 年）。',
      sliderLabels: { paternal: '父系', siblings: '兄妹', household: '同户', banner: '同旗' },
      motifs: '图模',
      readonlyBanner: '只读 · 加载自 1882 cell 档案',
      selectHusbandRules: '在 D 中选择一位 husband 以设定规则权重',
      selectHusbandMotifs: '在 D 中选择一位 husband 以检测图模',
      noCandidatesMotifs: '无候选',
      noMotifsDetected: '所有候选均未检测到图模',
      motifServiceUnavailable: 'motif 服务不可用',
      scanningCandidates: '扫描候选中… ({done}/{total} 完成)',
      matchedBy: '匹配候选：',
      selectHusbandSim: '在 D 中选择一位 husband 以查看候选相似度',
      grainAxis: '粮价',
      disasterAxis: '灾害',
    },
  },
}

function _resolve(dict, path) {
  const parts = path.split('.')
  let cur = dict
  for (const p of parts) {
    if (cur && typeof cur === 'object' && p in cur) cur = cur[p]
    else return undefined
  }
  return cur
}

export const t = (path, vars) => {
  const tryPath = (locale) => _resolve(messages[locale], path)
  let s = tryPath(lang.value)
  if (s === undefined) s = tryPath('en')
  if (s === undefined) return path
  if (typeof s === 'string' && vars) {
    return s.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : `{${k}}`))
  }
  return s
}

// Expose a computed proxy so templates can do `{{ T.panel.v1 }}` reactively.
export const T = computed(() => messages[lang.value] ?? messages.en)
