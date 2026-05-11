let bars = [];
let comments = [];
let trades = [];
let tradePnlList = [];
let dailyPnlList = [];
let flowEvents = [];
let selectedIndex = null;
let pending = [];
let mode = 'bar';
let flowMode = 'ops'; // ops | all
let rangeStart = null;
let globalYRange = [0, 1];
let fixedYSpan = 1;

const BASE_PX_PER_BAR = 11;
const MINI_CHART_HEIGHT = 120;
const DEFAULT_VISIBLE_BARS = 120;
const FIXED_VIEW_SCALE = 1.5;
const MAIN_VIEW_HEIGHT = 760;
const Y_VISUAL_ZOOM = 4.5;
const STRUCT_RELAXED_MODE = false; // 与EA默认保持一致：严格结构判定
const INITIAL_BALANCE = 1000;
const MAIN_MARGIN_LEFT = 50;
const MAIN_MARGIN_RIGHT = 20;
let currentPxPerBar = BASE_PX_PER_BAR;
let syncMiniRelayout = false;
let lastSelectAt = 0;
let scrollRaf = 0;
let barIndexByTime = new Map();

function barX(i) {
  return i;
}

const chartEl = document.getElementById('chart');
const miniChartEl = document.getElementById('miniChart');
const chartWrapEl = document.getElementById('chartWrap');
const chartViewportEl = document.getElementById('chartViewport');
const chartPanelEl = document.getElementById('chartPanel');
const infoEl = document.getElementById('selectedInfo');
const dataMetaEl = document.getElementById('dataMeta');
const pendingListEl = document.getElementById('pendingList');
const logListEl = document.getElementById('logList');
const flowListEl = document.getElementById('flowList');
const datasetBucketEl = document.getElementById('datasetBucket');
const datasetFileEl = document.getElementById('datasetFile');
const switchDatasetBtn = document.getElementById('switchDatasetBtn');
const engineFileEl = document.getElementById('engineFile');
const switchEngineBtn = document.getElementById('switchEngineBtn');
const statsGridEl = document.getElementById('statsGrid');
const statsHintEl = document.getElementById('statsHint');
const tradeDateFromEl = document.getElementById('tradeDateFrom');
const tradeDateToEl = document.getElementById('tradeDateTo');
const applyTradeRangeBtn = document.getElementById('applyTradeRangeBtn');
const resetTradeRangeBtn = document.getElementById('resetTradeRangeBtn');
const tradeSummaryGridEl = document.getElementById('tradeSummaryGrid');
const dailyListTableEl = document.getElementById('dailyListTable');
const tradeListTableEl = document.getElementById('tradeListTable');
const tradeListTitleEl = document.getElementById('tradeListTitle');
const openCommonConfigBtn = document.getElementById('openCommonConfigBtn');

const modeBarBtn = document.getElementById('modeBarBtn');
const modeRangeBtn = document.getElementById('modeRangeBtn');
const submitPendingTop = document.getElementById('submitPendingTop');
const clearCommentsBtn = document.getElementById('clearCommentsBtn');
const flowOpsBtn = document.getElementById('flowOpsBtn');
const flowAllBtn = document.getElementById('flowAllBtn');

const modal = document.getElementById('commentModal');
const modalTitle = document.getElementById('modalTitle');
const modalTarget = document.getElementById('modalTarget');
const kindEl = document.getElementById('kind');
const tagEl = document.getElementById('tag');
const commentEl = document.getElementById('comment');
const saveBtn = document.getElementById('saveBtn');
const cancelBtn = document.getElementById('cancelBtn');

const commonConfigModal = document.getElementById('commonConfigModal');
const commonConfigPathEl = document.getElementById('commonConfigPath');
const cfgDailyLossPctEl = document.getElementById('cfgDailyLossPct');
const cfgPerTradeLossPctEl = document.getElementById('cfgPerTradeLossPct');
const cfgDailyConsecLossEl = document.getElementById('cfgDailyConsecLoss');
const commonConfigSaveBtn = document.getElementById('commonConfigSaveBtn');
const commonConfigCancelBtn = document.getElementById('commonConfigCancelBtn');

let modalPayload = null;
let datasetCatalog = { year: [], month: [], week: [], day: [] };
let datasetCurrent = { bucket: null, file: null, source_file: '' };
let engineCatalog = [];
let engineCurrent = { file: null, path: null };
let currentBuildId = '';
let commonParams = { daily_max_loss_pct: 0.08, per_trade_max_loss_pct: 0.08, daily_max_consecutive_losses: 3 };
let selectedTradeDay = '';
let tradeRangeInitialized = false;
let lastValidTradeFrom = '';
let lastValidTradeTo = '';

async function fetchJsonNoCache(url) {
  const sep = url.includes('?') ? '&' : '?';
  const bust = `ts=${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  return fetch(`${url}${sep}${bust}`, {
    cache: 'no-store',
    headers: {
      'Cache-Control': 'no-store, no-cache, max-age=0',
      Pragma: 'no-cache',
    },
  }).then(r => r.json());
}

function resetBehaviorViews(statusText = '行为数据已清空，等待重新加载...') {
  trades = [];
  tradePnlList = [];
  dailyPnlList = [];
  flowEvents = [];
  selectedIndex = null;
  rangeStart = null;
  selectedTradeDay = '';
  tradeRangeInitialized = false;
  lastValidTradeFrom = '';
  lastValidTradeTo = '';
  if (tradeDateFromEl) tradeDateFromEl.value = '';
  if (tradeDateToEl) tradeDateToEl.value = '';
  currentBuildId = '';
  if (flowListEl) {
    flowListEl.innerHTML = `<div class="logItem"><div class="m">${statusText}</div></div>`;
  }
  if (statsGridEl) statsGridEl.innerHTML = '';
  if (chartEl && chartEl.data) {
    try { Plotly.purge(chartEl); } catch (_) {}
  }
  if (miniChartEl && miniChartEl.data) {
    try { Plotly.purge(miniChartEl); } catch (_) {}
  }
}

function toTime(t) {
  if (!t) return '';
  if (t.includes('.')) {
    const [d, hm] = t.split(' ');
    const [y, m, day] = d.split('.');
    return `${y}-${m}-${day}T${hm}:00`;
  }
  return t.replace('.000000000', '');
}

function baseName(p) {
  if (!p) return '';
  const s = String(p);
  const i = s.lastIndexOf('/');
  return i >= 0 ? s.slice(i + 1) : s;
}

function inferBucketFromFileName(name) {
  if (!name) return 'week';
  if (name.startsWith('Year_')) return 'year';
  if (name.startsWith('Month_')) return 'month';
  if (name.startsWith('Week_')) return 'week';
  if (name.startsWith('Day_')) return 'day';
  return 'week';
}

function bucketLabel(bucket) {
  const m = { year: '年', month: '月', week: '周', day: '日' };
  return m[bucket] || bucket;
}

function renderEngineFiles(preferredFile = null) {
  if (!engineFileEl) return;
  const files = engineCatalog || [];
  engineFileEl.innerHTML = files.map(f => `<option value="${f}">${f}</option>`).join('');
  if (preferredFile && files.includes(preferredFile)) {
    engineFileEl.value = preferredFile;
  } else if (files.length > 0) {
    engineFileEl.value = files[0];
  }
}

function syncEngineControls() {
  const fallback = baseName(engineCurrent?.path || '');
  renderEngineFiles(engineCurrent?.file || fallback);
}

async function loadCommonParams() {
  const res = await fetchJsonNoCache('/api/common-params');
  if (!res.ok) throw new Error(res.error || '加载公共配置失败');
  commonParams = res.params || commonParams;
  if (commonConfigPathEl) {
    commonConfigPathEl.textContent = `配置文件: ${res.file || ''}`;
  }
  if (cfgDailyLossPctEl) cfgDailyLossPctEl.value = Number(commonParams.daily_max_loss_pct ?? 0.08);
  if (cfgPerTradeLossPctEl) cfgPerTradeLossPctEl.value = Number(commonParams.per_trade_max_loss_pct ?? 0.08);
  if (cfgDailyConsecLossEl) cfgDailyConsecLossEl.value = Number(commonParams.daily_max_consecutive_losses ?? 3);
}

function openCommonConfigModal() {
  if (!commonConfigModal) return;
  loadCommonParams()
    .then(() => commonConfigModal.showModal())
    .catch((e) => alert(`加载公共配置失败: ${e.message}`));
}

async function saveCommonConfig() {
  const payload = {
    daily_max_loss_pct: Number(cfgDailyLossPctEl?.value || 0),
    per_trade_max_loss_pct: Number(cfgPerTradeLossPctEl?.value || 0),
    daily_max_consecutive_losses: Number(cfgDailyConsecLossEl?.value || 0),
  };
  const res = await fetch('/api/common-params', {
    method: 'POST',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ params: payload }),
  }).then(r => r.json());
  if (!res.ok) {
    alert(`保存失败: ${res.error || ''}`);
    return;
  }
  commonParams = res.params || payload;
  commonConfigModal.close();
  alert('公共配置已保存，点击“切换引擎”或“刷新”后生效。');
}

async function switchEngineAndRefresh() {
  if (!engineFileEl || !switchEngineBtn) return;
  const file = engineFileEl.value;
  if (!file) {
    alert('请先选择引擎文件');
    return;
  }
  switchEngineBtn.disabled = true;
  switchEngineBtn.textContent = '切换中...';
  resetBehaviorViews('引擎切换中，旧行为数据已清空...');
  try {
    const res = await fetch('/api/engines/select', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file }),
    }).then(r => r.json());
    if (!res.ok) {
      alert(`切换引擎失败: ${res.error || ''}`);
      return;
    }
    await fullRefreshAfterSwitch();
  } catch (e) {
    alert(`切换引擎失败: ${e.message}`);
  } finally {
    switchEngineBtn.disabled = false;
    switchEngineBtn.textContent = '切换引擎';
  }
}

function renderDatasetFiles(bucket, preferredFile = null) {
  if (!datasetFileEl) return;
  const files = datasetCatalog[bucket] || [];
  datasetFileEl.innerHTML = files.map(f => `<option value="${f}">${f}</option>`).join('');
  if (preferredFile && files.includes(preferredFile)) {
    datasetFileEl.value = preferredFile;
  } else if (files.length > 0) {
    datasetFileEl.value = files[files.length - 1];
  }
}

function syncDatasetControls() {
  if (!datasetBucketEl || !datasetFileEl) return;
  const fallbackFile = baseName(datasetCurrent?.source_file || '');
  const bucket = datasetCurrent?.bucket || inferBucketFromFileName(datasetCurrent?.file || fallbackFile);
  datasetBucketEl.value = bucket;
  renderDatasetFiles(bucket, datasetCurrent?.file || fallbackFile);
}

async function switchDatasetAndRefresh() {
  if (!datasetBucketEl || !datasetFileEl || !switchDatasetBtn) return;
  const bucket = datasetBucketEl.value;
  const file = datasetFileEl.value;
  if (!bucket || !file) {
    alert('请先选择数据范围和文件');
    return;
  }
  switchDatasetBtn.disabled = true;
  switchDatasetBtn.textContent = '切换中...';
  resetBehaviorViews('数据切换中，旧行为数据已清空...');
  try {
    const res = await fetch('/api/datasets/select', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bucket, file }),
    }).then(r => r.json());
    if (!res.ok) {
      alert(`切换失败: ${res.error || ''}`);
      return;
    }
    await fullRefreshAfterSwitch();
  } catch (e) {
    alert(`切换失败: ${e.message}`);
  } finally {
    switchDatasetBtn.disabled = false;
    switchDatasetBtn.textContent = '刷新';
  }
}

async function fullRefreshAfterSwitch() {
  resetBehaviorViews('正在加载新行为数据源...');
  await loadData();
  computeGlobalYRange();
  renderPending();
  renderLogs();
  updateSubmitCount();
  computeFlowEvents();
  renderFlowList();
  renderStats();
  renderTradeExplorer();
  buildChart();
  buildMiniChart();
}

function reasonLabel(code) {
  const m = {
    tp: '达到止盈',
    sl: '触发止损',
    xgold: '出现金叉信号平仓',
    xdead: '出现死叉信号平仓',
    final: '回测结束强制平仓',
  };
  if (code == null) return '规则判定触发';
  return m[String(code)] || String(code);
}

function fmtBar(bar, idx) {
  return [
    `index: ${idx}`,
    `time : ${bar.time}`,
    `open : ${bar.open}`,
    `high : ${bar.high}`,
    `low  : ${bar.low}`,
    `close: ${bar.close}`,
    `ema5 : ${bar.ema5 ?? ''}`,
    `ema20: ${bar.ema20 ?? ''}`,
    `bb_up: ${bar.bb_up ?? ''}`,
    `bb_mid:${bar.bb_mid ?? ''}`,
    `bb_dn: ${bar.bb_down ?? ''}`,
  ].join('\n');
}

function fmtNum(n, digits = 2) {
  return Number.isFinite(n) ? n.toFixed(digits) : '0.00';
}

function fmtPct(v) {
  return `${fmtNum(v * 100, 2)}%`;
}

function setMode(next) {
  mode = next;
  rangeStart = null;
  modeBarBtn.classList.toggle('active', mode === 'bar');
  modeRangeBtn.classList.toggle('active', mode === 'range');
}

function setFlowMode(next) {
  flowMode = next;
  flowOpsBtn.classList.toggle('active', flowMode === 'ops');
  flowAllBtn.classList.toggle('active', flowMode === 'all');
  renderFlowList();
}

function getMainViewportWidth() {
  const host = chartViewportEl || chartPanelEl;
  return Math.max(360, host.clientWidth);
}

function getMainChartHeight(mainWidth) {
  return MAIN_VIEW_HEIGHT;
}

function updateSubmitCount() {
  submitPendingTop.textContent = `提交评论(${pending.length})`;
}

function groupBarComments() {
  const map = new Map();
  for (const c of comments) {
    if (c.mode === 'range') continue;
    const key = toTime(c.bar_time);
    const arr = map.get(key) || [];
    arr.push(c);
    map.set(key, arr);
  }
  return map;
}

function getRangeComments() {
  return comments.filter(c => c.mode === 'range');
}

function buildIndicatorTraces() {
  const x = bars.map((_, i) => barX(i));
  return [
    {
      x, y: bars.map(b => b.ema5), type: 'scatter', mode: 'lines', name: 'EMA5',
      line: { color: '#a855f7', width: 1.8 }, hovertemplate: 'idx=%{x}<br>EMA5=%{y:.2f}<extra></extra>'
    },
    {
      x, y: bars.map(b => b.ema20), type: 'scatter', mode: 'lines', name: 'EMA20',
      line: { color: '#ef4444', width: 1.8 }, hovertemplate: 'idx=%{x}<br>EMA20=%{y:.2f}<extra></extra>'
    },
    {
      x, y: bars.map(b => b.bb_up), type: 'scatter', mode: 'lines', name: 'Boll_UP',
      line: { color: '#22d3ee', width: 1.2 }, hovertemplate: 'idx=%{x}<br>BB_UP=%{y:.2f}<extra></extra>'
    },
    {
      x, y: bars.map(b => b.bb_mid), type: 'scatter', mode: 'lines', name: 'Boll_MID',
      line: { color: '#14b8a6', width: 1.1, dash: 'dot' }, hovertemplate: 'idx=%{x}<br>BB_MID=%{y:.2f}<extra></extra>'
    },
    {
      x, y: bars.map(b => b.bb_down), type: 'scatter', mode: 'lines', name: 'Boll_DOWN',
      line: { color: '#22d3ee', width: 1.2 }, hovertemplate: 'idx=%{x}<br>BB_DOWN=%{y:.2f}<extra></extra>'
    },
  ];
}

function buildTradeTraces() {
  const xBuy = [], yBuy = [], txtBuy = [];
  const xSell = [], ySell = [], txtSell = [];
  const xExit = [], yExit = [], txtExit = [];

  const xLongLine = [], yLongLine = [];
  const xShortLine = [], yShortLine = [];

  for (const t of trades) {
    const et = toTime(t.entry_time);
    const xt = toTime(t.exit_time);
    const ei = barIndexByTime.get(et);
    const xi = barIndexByTime.get(xt);
    if (ei == null || xi == null) continue;

    if (t.side === 'long') {
      xBuy.push(barX(ei)); yBuy.push(t.entry_price);
      txtBuy.push(`开多 | reason=${t.reason} | pnl=${t.pnl.toFixed(2)}`);
      xLongLine.push(barX(ei), barX(xi), null);
      yLongLine.push(t.entry_price, t.exit_price, null);
    } else {
      xSell.push(barX(ei)); ySell.push(t.entry_price);
      txtSell.push(`开空 | reason=${t.reason} | pnl=${t.pnl.toFixed(2)}`);
      xShortLine.push(barX(ei), barX(xi), null);
      yShortLine.push(t.entry_price, t.exit_price, null);
    }

    xExit.push(barX(xi));
    yExit.push(t.exit_price);
    txtExit.push(`平仓 | side=${t.side} | reason=${t.reason} | pnl=${t.pnl.toFixed(2)}`);
  }

  return [
    {
      x: xLongLine, y: yLongLine, type: 'scatter', mode: 'lines', name: '多单连线',
      line: { color: 'rgba(34,197,94,0.65)', width: 1.8 }, hoverinfo: 'skip'
    },
    {
      x: xShortLine, y: yShortLine, type: 'scatter', mode: 'lines', name: '空单连线',
      line: { color: 'rgba(239,68,68,0.65)', width: 1.8 }, hoverinfo: 'skip'
    },
    {
      x: xBuy, y: yBuy, type: 'scatter', mode: 'markers+text', name: '开多',
      marker: { color: '#22c55e', size: 10, symbol: 'triangle-up', line: { color: '#ffffff', width: 1.2 } },
      text: xBuy.map(() => '开多'), textposition: 'top center',
      textfont: { color: '#22c55e', size: 10 },
      hovertext: txtBuy, hovertemplate: '%{x}<br>%{hovertext}<extra></extra>'
    },
    {
      x: xSell, y: ySell, type: 'scatter', mode: 'markers+text', name: '开空',
      marker: { color: '#ef4444', size: 10, symbol: 'triangle-down', line: { color: '#ffffff', width: 1.2 } },
      text: xSell.map(() => '开空'), textposition: 'bottom center',
      textfont: { color: '#ef4444', size: 10 },
      hovertext: txtSell, hovertemplate: '%{x}<br>%{hovertext}<extra></extra>'
    },
    {
      x: xExit, y: yExit, type: 'scatter', mode: 'markers+text', name: '平仓',
      marker: { color: '#f59e0b', size: 8, symbol: 'x', line: { color: '#ffffff', width: 1.2 } },
      text: xExit.map(() => '平'), textposition: 'top right',
      textfont: { color: '#f59e0b', size: 9 },
      hovertext: txtExit, hovertemplate: '%{x}<br>%{hovertext}<extra></extra>'
    },
  ];
}

function buildCommentTrace() {
  const grouped = groupBarComments();
  const mx = [], my = [], mtext = [];

  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    const arr = grouped.get(b.time);
    if (!arr || arr.length === 0) continue;
    mx.push(barX(i));
    my.push(b.high * 1.0002);
    mtext.push(arr.map(a => `${a.kind} ${a.tag || ''}: ${a.comment}`).join('<br>'));
  }

  return {
    x: mx, y: my, mode: 'markers', type: 'scatter', name: '评论标注',
    marker: { color: '#f59e0b', size: 8, symbol: 'diamond' },
    text: mtext, hovertemplate: 'idx=%{x}<br>%{text}<extra></extra>'
  };
}

function buildRangeShapes() {
  const mapByTime = new Map(bars.map((b, i) => [b.time, { ...b, i }]));
  const shapes = [];

  for (const c of getRangeComments()) {
    const s = mapByTime.get(toTime(c.start_time));
    const e = mapByTime.get(toTime(c.end_time));
    if (!s || !e) continue;

    const i1 = Math.min(s.i, e.i), i2 = Math.max(s.i, e.i);
    let yMin = Infinity, yMax = -Infinity;
    for (let i = i1; i <= i2; i++) {
      yMin = Math.min(yMin, bars[i].low);
      yMax = Math.max(yMax, bars[i].high);
    }

    shapes.push({
      type: 'rect', xref: 'x', yref: 'y',
      x0: barX(i1), x1: barX(i2),
      y0: yMin, y1: yMax,
      line: { color: 'rgba(56,189,248,0.9)', width: 1 },
      fillcolor: 'rgba(56,189,248,0.12)',
      layer: 'below',
    });
  }

  return shapes;
}

function buildSelectionShape() {
  if (selectedIndex == null || selectedIndex < 0 || selectedIndex >= bars.length) return null;
  const t = barX(selectedIndex);
  return {
    type: 'line',
    xref: 'x',
    yref: 'paper',
    x0: t,
    x1: t,
    y0: 0,
    y1: 1,
    line: { color: 'rgba(250, 204, 21, 0.95)', width: 2, dash: 'dot' },
    layer: 'above',
  };
}

function buildAllShapes() {
  const shapes = buildRangeShapes();
  const sel = buildSelectionShape();
  if (sel) shapes.push(sel);
  return shapes;
}

function computeFlowEvents() {
  const mapIdx = new Map(bars.map((b, i) => [b.time, i]));
  const events = [];
  const fallbackReason = '规则判定触发';

  // 操作/状态变更
  for (const t of trades) {
    const eTime = toTime(t.entry_time);
    const xTime = toTime(t.exit_time);
    const ei = mapIdx.get(eTime);
    const xi = mapIdx.get(xTime);

    if (ei != null) {
      events.push({
        time: eTime, barIndex: ei, category: 'op',
        title: t.side === 'long' ? '开多' : '开空',
        detail: `entry=${t.entry_price.toFixed(2)}`,
        reason: reasonLabel(t.reason || fallbackReason)
      });
      events.push({
        time: eTime, barIndex: ei, category: 'state',
        title: '状态变更',
        detail: t.side === 'long' ? 'FLAT -> LONG' : 'FLAT -> SHORT',
        reason: `由${t.side === 'long' ? '开多' : '开空'}触发（${reasonLabel(t.reason || fallbackReason)}）`
      });
    }

    if (xi != null) {
      events.push({
        time: xTime, barIndex: xi, category: 'op',
        title: '平仓',
        detail: `exit=${t.exit_price.toFixed(2)} pnl=${t.pnl.toFixed(2)}`,
        reason: reasonLabel(t.reason || fallbackReason)
      });
      events.push({
        time: xTime, barIndex: xi, category: 'state',
        title: '状态变更',
        detail: 'LONG/SHORT -> FLAT',
        reason: `由平仓触发（${reasonLabel(t.reason || fallbackReason)}）`
      });
    }
  }

  // 全部模式：补充信号事件
  for (let i = 3; i < bars.length; i++) {
    const l = i - 3, m = i - 2, r = i - 1;
    const bm = bars[m], bl = bars[l], br = bars[r];

    const brPriceDown = Math.min(br.open, br.close); // K_LINE_PRICE_DOWN
    const brPriceUp = Math.max(br.open, br.close);   // K_LINE_PRICE_UP
    const bmPriceUp = Math.max(bm.open, bm.close);   // 中间K实体上沿

    // STRUCT_UP:
    // 1) 中间K K_LINE_TOP > Bollinger_UP
    // 2) 中间K K_LINE_TOP 为三根最高
    // 3) 右侧K K_LINE_PRICE_DOWN < 左侧K K_LINE_BOTTOM
    const upC1 = (bm.high > (bm.bb_up ?? Infinity));
    const upC2 = (bm.high > bl.high && bm.high > br.high);
    const upC3Strict = (brPriceDown < bl.low);
    const upC3Relaxed = (br.low < bl.low);
    const structUpStrict = upC1 && upC2 && upC3Strict;
    const structUp = upC1 && upC2 && (upC3Strict || (STRUCT_RELAXED_MODE && upC3Relaxed));

    // STRUCT_DOWN:
    // 1) 中间K K_LINE_BOTTOM < Bollinger_DOWN
    // 2) 中间K K_LINE_BOTTOM 为三根最低
    // 3) 右侧K K_LINE_PRICE_UP > 中间K K_LINE_TOP
    const downC1 = (bm.low < (bm.bb_down ?? -Infinity));
    const downC2 = (bm.low < bl.low && bm.low < br.low);
    const downC3Strict = (brPriceUp > bm.high);
    const downC3Relaxed = (br.high > bm.high) || (brPriceUp > bmPriceUp);
    const structDownStrict = downC1 && downC2 && downC3Strict;
    const structDown = downC1 && downC2 && (downC3Strict || (STRUCT_RELAXED_MODE && downC3Relaxed));

    const xgold = bars[i-2].ema5 != null && bars[i-1].ema5 != null && bars[i-2].ema20 != null && bars[i-1].ema20 != null
      ? (bars[i-2].ema5 <= bars[i-2].ema20 && bars[i-1].ema5 > bars[i-1].ema20)
      : false;
    const xdead = bars[i-2].ema5 != null && bars[i-1].ema5 != null && bars[i-2].ema20 != null && bars[i-1].ema20 != null
      ? (bars[i-2].ema5 >= bars[i-2].ema20 && bars[i-1].ema5 < bars[i-1].ema20)
      : false;

    if (structUp) {
      events.push({
        time: bars[r].time, barIndex: r, category: 'signal', title: 'STRUCT_UP',
        detail: `3K高区结构触发 | ${structUpStrict ? 'STRICT' : 'RELAXED'}`,
        reason: structUpStrict ? '严格结构条件成立' : '宽松结构回补成立'
      });
    }
    if (structDown) {
      events.push({
        time: bars[r].time, barIndex: r, category: 'signal', title: 'STRUCT_DOWN',
        detail: `3K低区结构触发 | ${structDownStrict ? 'STRICT' : 'RELAXED'}`,
        reason: structDownStrict ? '严格结构条件成立' : '宽松结构回补成立'
      });
    }
    if (xgold) {
      events.push({
        time: bars[i-1].time, barIndex: i-1, category: 'signal', title: 'X_GOLD',
        detail: 'EMA5上穿EMA20',
        reason: '快线由下向上穿越慢线'
      });
    }
    if (xdead) {
      events.push({
        time: bars[i-1].time, barIndex: i-1, category: 'signal', title: 'X_DEAD',
        detail: 'EMA5下穿EMA20',
        reason: '快线由上向下穿越慢线'
      });
    }
  }

  events.sort((a, b) => a.barIndex - b.barIndex || a.time.localeCompare(b.time));
  flowEvents = events;
}

function renderFlowList() {
  if (!flowListEl) return;
  const showAll = flowMode === 'all';
  const items = showAll
    ? flowEvents
    : flowEvents.filter(e => e.category === 'op' || e.category === 'state');
  if (items.length === 0) {
    flowListEl.innerHTML = '<div class="logItem"><div class="m">当前数据源暂无行为事件</div></div>';
    return;
  }

  const visualForEvent = (e) => {
    if (e.title === '开多') return { symbol: '▲', cls: 'op-long' };
    if (e.title === '开空') return { symbol: '▼', cls: 'op-short' };
    if (e.title === '平仓') return { symbol: '✖', cls: 'op-exit' };
    if (e.title === '状态变更') return { symbol: '●', cls: 'op-state' };
    if (e.title === 'STRUCT_UP' || e.title === 'STRUCT_DOWN') return { symbol: '◇', cls: 'op-signal' };
    if (e.title === 'X_GOLD' || e.title === 'X_DEAD') return { symbol: '✛', cls: 'op-signal' };
    if (e.title === '区间评论' || e.title === '单K评论') return { symbol: '◆', cls: 'op-comment' };
    return { symbol: '•', cls: 'op-default' };
  };

  const recent = items.slice(-400).reverse();
  flowListEl.innerHTML = recent.map((e, idx) => {
    const v = visualForEvent(e);
    return `
    <div class="flowItem" data-idx="${e.barIndex}">
      <div class="t">
        <span class="opIcon ${v.cls}">${v.symbol}</span>
        <span class="opTitle ${v.cls}">${e.time} | ${e.title}</span>
      </div>
      <div class="m">#${e.barIndex} | ${e.detail}</div>
      <div class="r">触发原因：${e.reason || '—'}</div>
    </div>
  `;
  }).join('');

  flowListEl.querySelectorAll('.flowItem').forEach(el => {
    el.onclick = () => {
      const idx = Number(el.dataset.idx);
      focusBarIndex(idx);
    };
  });
}

function renderStats() {
  if (!statsGridEl) return;

  const closeCount = trades.length;
  const openLongCount = trades.filter(t => t.side === 'long').length;
  const openShortCount = trades.filter(t => t.side === 'short').length;

  const pnlList = trades.map(t => Number(t.pnl) || 0);
  const netPnl = pnlList.reduce((a, b) => a + b, 0);
  const winCloseCount = pnlList.filter(v => v > 0).length;
  const lossCloseCount = pnlList.filter(v => v <= 0).length;
  const winRate = closeCount > 0 ? (winCloseCount / closeCount) : 0;

  const reasonOf = (t) => String(t.reason || '').toLowerCase();
  const tpCount = trades.filter(t => reasonOf(t) === 'tp').length;
  const slCount = trades.filter(t => reasonOf(t) === 'sl').length;
  const xGoldExitCount = trades.filter(t => reasonOf(t) === 'xgold').length;
  const xDeadExitCount = trades.filter(t => reasonOf(t) === 'xdead').length;
  const finalExitCount = trades.filter(t => reasonOf(t) === 'final').length;

  const sigCount = (name) => flowEvents.filter(e => e.category === 'signal' && e.title === name).length;
  const structUpCount = sigCount('STRUCT_UP');
  const structDownCount = sigCount('STRUCT_DOWN');
  const xGoldCount = sigCount('X_GOLD');
  const xDeadCount = sigCount('X_DEAD');

  const finalBalance = INITIAL_BALANCE + netPnl;
  const returnRate = netPnl / INITIAL_BALANCE;

  const items = [
    { k: '开多次数', v: `${openLongCount}` },
    { k: '开空次数', v: `${openShortCount}` },
    { k: '平仓总次数', v: `${closeCount}` },
    { k: '平仓盈利次数', v: `${winCloseCount}` },
    { k: '平仓亏损次数', v: `${lossCloseCount}` },
    { k: '止盈次数(TP)', v: `${tpCount}` },
    { k: '止损次数(SL)', v: `${slCount}` },
    { k: '金叉平仓次数', v: `${xGoldExitCount}` },
    { k: '死叉平仓次数', v: `${xDeadExitCount}` },
    { k: '结束平仓次数', v: `${finalExitCount}` },
    { k: 'STRUCT_UP次数', v: `${structUpCount}` },
    { k: 'STRUCT_DOWN次数', v: `${structDownCount}` },
    { k: 'X_GOLD次数', v: `${xGoldCount}` },
    { k: 'X_DEAD次数', v: `${xDeadCount}` },
    { k: '总盈利', v: fmtNum(netPnl), cls: netPnl >= 0 ? 'pos' : 'neg' },
    { k: '盈利比例', v: fmtPct(winRate), cls: winRate >= 0.5 ? 'pos' : 'neg' },
    { k: '收益率', v: fmtPct(returnRate), cls: returnRate >= 0 ? 'pos' : 'neg' },
    { k: '当前余额', v: fmtNum(finalBalance), cls: finalBalance >= INITIAL_BALANCE ? 'pos' : 'neg' },
  ];

  statsGridEl.innerHTML = items.map(it => `
    <div class="statItem ${it.cls || ''}">
      <div class="k">${it.k}</div>
      <div class="v">${it.v}</div>
    </div>
  `).join('');

  if (statsHintEl) {
    statsHintEl.textContent = '统计口径：初始资金固定1000；盈利比例=盈利平仓次数/平仓总次数；收益率=总盈利/1000。';
  }
}

function fmtDateInputValue(dateStr) {
  return /^\d{4}-\d{2}-\d{2}$/.test(dateStr || '') ? dateStr : '';
}

function inDateRange(d, from, to) {
  if (from && d < from) return false;
  if (to && d > to) return false;
  return true;
}

function applyTradeRangeAndRender(keepSelected = true, opts = {}) {
  const sortedDays = [...dailyPnlList].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const minDay = sortedDays.length ? String(sortedDays[0].date) : '';
  const maxDay = sortedDays.length ? String(sortedDays[sortedDays.length - 1].date) : '';
  const forceReset = !!opts.forceReset;

  if (tradeDateFromEl) {
    tradeDateFromEl.min = fmtDateInputValue(minDay);
    tradeDateFromEl.max = fmtDateInputValue(maxDay);
  }
  if (tradeDateToEl) {
    tradeDateToEl.min = fmtDateInputValue(minDay);
    tradeDateToEl.max = fmtDateInputValue(maxDay);
  }

  let fromRaw = tradeDateFromEl ? String(tradeDateFromEl.value || '') : '';
  let toRaw = tradeDateToEl ? String(tradeDateToEl.value || '') : '';
  let from = fmtDateInputValue(fromRaw);
  let to = fmtDateInputValue(toRaw);

  if (forceReset || !tradeRangeInitialized) {
    from = fmtDateInputValue(minDay);
    to = fmtDateInputValue(maxDay);
    tradeRangeInitialized = true;
  } else {
    // Apply 时保留用户选择；若浏览器把非法/未完成输入清空，则回退到上一次有效值
    if (!from) from = lastValidTradeFrom || fmtDateInputValue(minDay);
    if (!to) to = lastValidTradeTo || fmtDateInputValue(maxDay);
  }

  // 保证区间合法，优先保留用户设定的开始日期
  if (from && to && from > to) {
    to = from;
  }

  if (tradeDateFromEl) tradeDateFromEl.value = from || '';
  if (tradeDateToEl) tradeDateToEl.value = to || '';
  lastValidTradeFrom = from || '';
  lastValidTradeTo = to || '';

  const filteredDaily = sortedDays.filter(d => inDateRange(String(d.date), from, to));
  const dailySet = new Set(filteredDaily.map(d => String(d.date)));
  const filteredTrades = tradePnlList.filter(t => dailySet.has(String(t.date)));

  if (!keepSelected || !selectedTradeDay || !dailySet.has(selectedTradeDay)) {
    selectedTradeDay = filteredDaily.length ? String(filteredDaily[0].date) : '';
  }
  renderTradeSummary(filteredDaily, filteredTrades, from, to);
  renderDailyList(filteredDaily);
  renderTradeList(filteredTrades, selectedTradeDay);
}

function renderTradeSummary(filteredDaily, filteredTrades, from, to) {
  if (!tradeSummaryGridEl) return;
  const closeCount = filteredTrades.length;
  const winCount = filteredTrades.filter(t => Number(t.pnl) > 0).length;
  const lossCount = closeCount - winCount;
  const net = filteredTrades.reduce((s, t) => s + Number(t.pnl || 0), 0);
  const winRate = closeCount > 0 ? (winCount / closeCount) : 0;
  const selectedCount = selectedTradeDay ? filteredTrades.filter(t => String(t.date) === selectedTradeDay).length : 0;
  const items = [
    { k: '区间开始', v: from || '-' },
    { k: '区间结束', v: to || '-' },
    { k: '日期数量', v: `${filteredDaily.length}` },
    { k: '区间交易数', v: `${closeCount}` },
    { k: '区间盈利数', v: `${winCount}` },
    { k: '区间亏损数', v: `${lossCount}` },
    { k: '区间总盈亏', v: fmtNum(net), cls: net >= 0 ? 'pos' : 'neg' },
    { k: '区间胜率', v: fmtPct(winRate), cls: winRate >= 0.5 ? 'pos' : 'neg' },
    { k: '当前选中日期', v: selectedTradeDay || '-' },
    { k: '当日交易数', v: `${selectedCount}` },
  ];
  tradeSummaryGridEl.innerHTML = items.map(it => `
    <div class="statItem ${it.cls || ''}">
      <div class="k">${it.k}</div>
      <div class="v">${it.v}</div>
    </div>
  `).join('');
}

function renderDailyList(filteredDaily) {
  if (!dailyListTableEl) return;
  if (!filteredDaily.length) {
    dailyListTableEl.innerHTML = '<div class="logItem"><div class="m">当前区间无日期数据</div></div>';
    return;
  }
  const rows = filteredDaily.map(d => {
    const day = String(d.date);
    return `
      <tr class="${selectedTradeDay === day ? 'active' : ''}" data-day="${day}">
        <td>${day}</td>
        <td>${d.trades}</td>
        <td class="${Number(d.net_pnl) >= 0 ? 'pnlPos' : 'pnlNeg'}">${Number(d.net_pnl).toFixed(2)}</td>
      </tr>
    `;
  }).join('');
  dailyListTableEl.innerHTML = `
    <div class="tableWrap tableWrapTall">
      <table class="pnlTable">
        <thead><tr><th>日期</th><th>交易数</th><th>当日盈亏</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
  dailyListTableEl.querySelectorAll('tr[data-day]').forEach(row => {
    row.onclick = () => {
      selectedTradeDay = String(row.dataset.day || '');
      applyTradeRangeAndRender(true);
    };
  });
}

function renderTradeList(filteredTrades, day) {
  if (!tradeListTableEl) return;
  const list = filteredTrades.filter(t => String(t.date) === String(day || ''));
  if (tradeListTitleEl) {
    tradeListTitleEl.textContent = day ? `交易明细（${day}）` : '交易明细';
  }
  if (!list.length) {
    tradeListTableEl.innerHTML = '<div class="logItem"><div class="m">该日期暂无交易</div></div>';
    return;
  }
  const rows = list.map(t => {
    const entryTime = toTime(String(t.entry_time || ''));
    const exitTime = toTime(String(t.exit_time || ''));
    const entryIdx = barIndexByTime.get(entryTime);
    const exitIdx = barIndexByTime.get(exitTime);
    return `
    <tr data-entry="${entryTime}" data-exit="${exitTime}">
      <td>${t.id}</td>
      <td>${t.side === 'long' ? '开多' : '开空'}</td>
      <td class="jumpTime" data-idx="${entryIdx != null ? entryIdx : ''}">入: ${entryTime.slice(11, 16)}</td>
      <td class="jumpTime" data-idx="${exitIdx != null ? exitIdx : ''}">平: ${exitTime.slice(11, 16)}</td>
      <td class="${Number(t.pnl) >= 0 ? 'pnlPos' : 'pnlNeg'}">${Number(t.pnl).toFixed(2)}</td>
      <td>${t.reason || ''}</td>
    </tr>
  `;
  }).join('');
  tradeListTableEl.innerHTML = `
    <div class="tableWrap tableWrapTall">
      <table class="pnlTable">
        <thead><tr><th>ID</th><th>方向</th><th>入场节点</th><th>平仓节点</th><th>盈亏</th><th>原因</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
  tradeListTableEl.onclick = (ev) => {
    const target = ev.target;
    if (!target || !target.classList || !target.classList.contains('jumpTime')) return;
    ev.stopPropagation();
    const idx = Number(target.dataset.idx);
    if (Number.isFinite(idx)) {
      focusBarIndex(idx);
    }
  };
}

function renderTradeExplorer() {
  applyTradeRangeAndRender(false);
}

function focusBarIndex(idx) {
  if (!Number.isFinite(idx)) return;
  if (idx < 0 || idx >= bars.length) return;
  selectedIndex = idx;
  centerOnIndex(idx);
  if (idx >= 0 && idx < bars.length) {
    infoEl.textContent = fmtBar(bars[idx], idx);
  }
  if (chartEl && chartEl.data) {
    Plotly.relayout(chartEl, { shapes: buildAllShapes() });
  }
}

function moveMainChartToCenter(idx) {
  const raw = MAIN_MARGIN_LEFT + idx * currentPxPerBar - chartWrapEl.clientWidth / 2;
  const contentWidth = Math.max(chartEl.scrollWidth || 0, chartWrapEl.scrollWidth || 0);
  const maxScroll = Math.max(0, contentWidth - chartWrapEl.clientWidth);
  const clamped = Math.max(0, Math.min(maxScroll, raw));
  chartWrapEl.scrollTo({ left: clamped, behavior: 'auto' });
  return clamped;
}

function centerOnIndex(idx) {
  if (idx < 0 || idx >= bars.length) return;
  moveMainChartToCenter(idx);
  syncMiniWindowFromMainScroll();
  updateMainYRangeByViewport();
  // next-frame hard align: avoid one-frame lag when Plotly just relayouted
  requestAnimationFrame(() => {
    moveMainChartToCenter(idx);
    syncMiniWindowFromMainScroll();
    updateMainYRangeByViewport();
  });
}

function calcMinMaxPrice(i1, i2) {
  let minY = Infinity;
  let maxY = -Infinity;
  for (let i = i1; i <= i2; i++) {
    const b = bars[i];
    minY = Math.min(minY, b.low);
    maxY = Math.max(maxY, b.high);
  }
  if (!isFinite(minY) || !isFinite(maxY)) return { min: 0, max: 1 };
  return { min: minY, max: maxY };
}

function calcMinMax(i1, i2) {
  let minY = Infinity;
  let maxY = -Infinity;

  for (let i = i1; i <= i2; i++) {
    const b = bars[i];
    minY = Math.min(minY, b.low);
    maxY = Math.max(maxY, b.high);

    if (b.ema5 != null) { minY = Math.min(minY, b.ema5); maxY = Math.max(maxY, b.ema5); }
    if (b.ema20 != null) { minY = Math.min(minY, b.ema20); maxY = Math.max(maxY, b.ema20); }
    if (b.bb_up != null) { minY = Math.min(minY, b.bb_up); maxY = Math.max(maxY, b.bb_up); }
    if (b.bb_mid != null) { minY = Math.min(minY, b.bb_mid); maxY = Math.max(maxY, b.bb_mid); }
    if (b.bb_down != null) { minY = Math.min(minY, b.bb_down); maxY = Math.max(maxY, b.bb_down); }
  }

  if (!isFinite(minY) || !isFinite(maxY)) return { min: 0, max: 1 };
  return { min: minY, max: maxY };
}

function calcYRange(i1, i2) {
  const mm = calcMinMax(i1, i2);
  const pad = (mm.max - mm.min) * 0.08 || 1;
  return [mm.min - pad, mm.max + pad];
}

function computeGlobalYRange() {
  globalYRange = calcYRange(0, Math.max(0, bars.length - 1));
}

function getVisibleIndexRange() {
  const leftChartPx = chartWrapEl.scrollLeft;
  const rightChartPx = leftChartPx + chartWrapEl.clientWidth;
  const i1 = Math.max(0, Math.floor(indexFromChartPixel(leftChartPx)) - 1);
  const i2 = Math.min(bars.length - 1, Math.ceil(indexFromChartPixel(rightChartPx)) + 1);
  return [i1, Math.max(i1, i2)];
}

function updateMainYRangeByViewport() {
  if (!bars.length) return;
  const centerIdx = getCenterIndexByViewportX();
  const centerK = bars[centerIdx];
  const anchor = (centerK.high + centerK.low) / 2;

  // 固定比例核心：中心K线中点严格对齐center_Y，只做平移不缩放
  let y0 = anchor - fixedYSpan / 2;
  let y1 = anchor + fixedYSpan / 2;

  // 硬校准：保持center_K中点严格在center_Y
  const mid = (y0 + y1) / 2;
  const delta = anchor - mid;
  y0 += delta;
  y1 += delta;

  Plotly.relayout(chartEl, { 'yaxis.range': [y0, y1] });
}

function computeFixedYSpan(visibleBars) {
  const barsInView = Math.max(20, Math.min(bars.length, visibleBars));
  let maxSpan = 1;
  for (let i = 0; i < bars.length; i++) {
    const s = i;
    const e = Math.min(bars.length - 1, i + barsInView - 1);
    const mm = calcMinMaxPrice(s, e);
    const c = Math.floor((s + e) / 2);
    const a = (bars[c].high + bars[c].low) / 2;
    const spanNeed = 2 * Math.max(mm.max - a, a - mm.min);
    maxSpan = Math.max(maxSpan, spanNeed);
    if (e >= bars.length - 1) break;
  }
  // 固定比例下的安全边距，确保窗口上下边界都可完整展示
  fixedYSpan = (maxSpan * 1.04) / Y_VISUAL_ZOOM;
}

function getPlotWidthPx() {
  return Math.max(1, chartEl.clientWidth - MAIN_MARGIN_LEFT - MAIN_MARGIN_RIGHT);
}

function indexFromChartPixel(chartPx) {
  const xData = chartPx - MAIN_MARGIN_LEFT;
  return xData / currentPxPerBar;
}

function getCenterIndexByViewportX() {
  const centerChartPx = chartWrapEl.scrollLeft + chartWrapEl.clientWidth / 2;
  const idx = Math.round(indexFromChartPixel(centerChartPx));
  return Math.max(0, Math.min(bars.length - 1, idx));
}

function visibleRangeFromMain() {
  const [i1, i2] = getVisibleIndexRange();
  return [barX(i1), barX(i2)];
}

function syncMiniWindowFromMainScroll() {
  if (!bars.length || !miniChartEl.data) return;
  const [x0, x1] = visibleRangeFromMain();
  const full0 = barX(0);
  const full1 = barX(Math.max(0, bars.length - 1));
  syncMiniRelayout = true;
  Plotly.relayout(miniChartEl, {
    'xaxis.range': [x0, x1],
    // 强制保持rangeslider始终覆盖全量数据
    'xaxis.rangeslider.range': [full0, full1],
  }).finally(() => {
    syncMiniRelayout = false;
  });
}

function renderLogs() {
  if (!logListEl) return;
  const recent = [...comments].slice(-200).reverse();
  logListEl.innerHTML = recent.map(c => {
    const target = c.mode === 'range' ? `[${c.start_time} ~ ${c.end_time}]` : `[${c.bar_time}]`;
    return `
      <div class="logItem">
        <div class="t">${c.created_at} | ${c.mode} | ${c.kind} | ${c.tag || ''}</div>
        <div class="m">${target} ${c.comment}</div>
      </div>
    `;
  }).join('');
}

function renderPending() {
  if (!pendingListEl) return;
  pendingListEl.innerHTML = pending.map((p, idx) => {
    const target = p.mode === 'range' ? `[${p.start_time} ~ ${p.end_time}]` : `[${p.bar_time}]`;
    return `
      <div class="logItem">
        <div class="t">#${idx + 1} | ${p.mode} | ${p.kind} | ${p.tag || ''}</div>
        <div class="m">${target} ${p.comment}</div>
        <div class="btns"><button data-rm="${idx}">移除</button></div>
      </div>
    `;
  }).join('');

  pendingListEl.querySelectorAll('button[data-rm]').forEach(btn => {
    btn.onclick = () => {
      const i = Number(btn.dataset.rm);
      pending.splice(i, 1);
      renderPending();
      updateSubmitCount();
    };
  });
}

function buildMiniChart() {
  const x = bars.map((_, i) => barX(i));
  const close = bars.map(b => b.close);
  const [x0, x1] = visibleRangeFromMain();
  const full0 = barX(0);
  const full1 = barX(Math.max(0, bars.length - 1));

  const miniTrace = {
    x,
    y: close,
    type: 'scatter',
    mode: 'lines',
    name: 'Overview',
    line: { color: '#64748b', width: 1 },
    hoverinfo: 'skip',
  };

  const buyX = [];
  const buyY = [];
  const buyText = [];
  const sellX = [];
  const sellY = [];
  const sellText = [];
  const exitX = [];
  const exitY = [];
  const exitText = [];

  for (const t of trades) {
    const ei = barIndexByTime.get(toTime(t.entry_time));
    const xi = barIndexByTime.get(toTime(t.exit_time));
    if (ei == null || xi == null) continue;

    if (t.side === 'long') {
      buyX.push(barX(ei));
      buyY.push(bars[ei].close);
      buyText.push(`开多 | idx=${ei} | pnl=${t.pnl.toFixed(2)}`);
    } else {
      sellX.push(barX(ei));
      sellY.push(bars[ei].close);
      sellText.push(`开空 | idx=${ei} | pnl=${t.pnl.toFixed(2)}`);
    }

    exitX.push(barX(xi));
    exitY.push(bars[xi].close);
    exitText.push(`平仓 | idx=${xi} | ${t.reason}`);
  }

  const buyTrace = {
    x: buyX,
    y: buyY,
    type: 'scatter',
    mode: 'markers',
    name: '开多',
    marker: { color: '#22c55e', size: 7, symbol: 'triangle-up', line: { color: '#ffffff', width: 1.1 } },
    hovertext: buyText,
    hovertemplate: '%{hovertext}<extra></extra>',
  };

  const sellTrace = {
    x: sellX,
    y: sellY,
    type: 'scatter',
    mode: 'markers',
    name: '开空',
    marker: { color: '#ef4444', size: 7, symbol: 'triangle-down', line: { color: '#ffffff', width: 1.1 } },
    hovertext: sellText,
    hovertemplate: '%{hovertext}<extra></extra>',
  };

  const exitTrace = {
    x: exitX,
    y: exitY,
    type: 'scatter',
    mode: 'markers',
    name: '平仓',
    marker: { color: '#f59e0b', size: 6, symbol: 'x', line: { color: '#ffffff', width: 1.1 } },
    hovertext: exitText,
    hovertemplate: '%{hovertext}<extra></extra>',
  };

  const layout = {
    width: getMainViewportWidth(),
    height: MINI_CHART_HEIGHT,
    paper_bgcolor: '#0b0e14',
    plot_bgcolor: '#0b0e14',
    margin: { l: 38, r: 12, t: 6, b: 16 },
    xaxis: {
      gridcolor: '#1f2937',
      range: [x0, x1],
      fixedrange: false,
      rangeslider: {
        visible: true,
        thickness: 0.7,
        bgcolor: '#0f172a',
        autorange: false,
        range: [full0, full1],
      },
    },
    yaxis: {
      showgrid: false,
      fixedrange: true,
      showticklabels: false,
    },
    showlegend: false,
    hovermode: 'closest',
  };

  Plotly.newPlot(miniChartEl, [miniTrace, buyTrace, sellTrace, exitTrace], layout, {
    responsive: false,
    scrollZoom: false,
    displaylogo: false,
    modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'autoScale2d', 'resetScale2d'],
  });

  miniChartEl.on('plotly_relayout', (ev) => {
    if (!ev || syncMiniRelayout) return;
    const xStart = ev['xaxis.range[0]'];
    const xEnd = ev['xaxis.range[1]'];
    if (xStart == null || xEnd == null) return;

    const i1 = Math.max(0, Math.min(bars.length - 1, Math.floor(Number(xStart))));
    const i2 = Math.max(0, Math.min(bars.length - 1, Math.ceil(Number(xEnd))));
    const mid = Math.floor((i1 + i2) / 2);
    centerOnIndex(mid);
  });

  miniChartEl.on('plotly_click', (ev) => {
    if (!ev.points || ev.points.length === 0) return;
    const idx = Math.round(Number(ev.points[0].x));
    if (Number.isFinite(idx)) centerOnIndex(Math.max(0, Math.min(bars.length - 1, idx)));
  });
}

function resolveBarIndexFromClick(ev) {
  if (!ev || !ev.points || ev.points.length === 0) return null;
  for (const p of ev.points) {
    if (p && p.x != null) {
      const idx = Math.round(Number(p.x));
      if (Number.isFinite(idx) && idx >= 0 && idx < bars.length) return idx;
    }
  }
  const p0 = ev.points[0];
  if (p0 && typeof p0.pointNumber === 'number' && p0.fullData && p0.fullData.type === 'candlestick') {
    return p0.pointNumber;
  }
  return null;
}

function handleBarSelection(idx) {
  if (idx == null || idx < 0 || idx >= bars.length) return;

  const now = Date.now();
  if (now - lastSelectAt < 120) return;
  lastSelectAt = now;

  selectedIndex = idx;
  const bar = bars[idx];
  infoEl.textContent = fmtBar(bar, idx);
  Plotly.relayout(chartEl, { shapes: buildAllShapes() });

  if (mode === 'bar') {
    openBarModal(idx);
    return;
  }

  if (rangeStart == null) {
    rangeStart = idx;
    infoEl.textContent += '\n\n[区间起点已选，请再点一根K线作为终点]';
  } else {
    const a = Math.min(rangeStart, idx);
    const b = Math.max(rangeStart, idx);
    openRangeModal(a, b);
    rangeStart = null;
  }
}

function buildChart() {
  // 主览：固定间距，仅横向滚动
  const mainWidth = getMainViewportWidth();
  const mainHeight = getMainChartHeight(mainWidth);
  const pxPerBar = BASE_PX_PER_BAR * FIXED_VIEW_SCALE;
  currentPxPerBar = pxPerBar;
  const dataWidth = MAIN_MARGIN_LEFT + MAIN_MARGIN_RIGHT + Math.max(1, (bars.length - 1) * pxPerBar);
  const chartWidth = Math.max(mainWidth, Math.round(dataWidth));
  const visibleBars = Math.max(20, Math.ceil((mainWidth - MAIN_MARGIN_LEFT - MAIN_MARGIN_RIGHT) / pxPerBar) + 1);
  computeFixedYSpan(visibleBars);

  chartWrapEl.style.width = `${mainWidth}px`;
  chartWrapEl.style.height = `${mainHeight}px`;
  chartEl.style.width = `${chartWidth}px`;
  chartEl.style.height = `${mainHeight}px`;

  const candle = {
    x: bars.map((_, i) => barX(i)),
    open: bars.map(b => b.open),
    high: bars.map(b => b.high),
    low: bars.map(b => b.low),
    close: bars.map(b => b.close),
    type: 'candlestick',
    name: 'XAUUSD M5',
    increasing: { line: { color: '#22c55e' } },
    decreasing: { line: { color: '#ef4444' } },
  };

  const traces = [
    candle,
    ...buildIndicatorTraces(),
    ...buildTradeTraces(),
    buildCommentTrace(),
  ];

  const layout = {
    paper_bgcolor: '#0b0e14',
    plot_bgcolor: '#0b0e14',
    font: { color: '#cbd5e1' },
    width: chartWidth,
    height: mainHeight,
    dragmode: false,
    xaxis: {
      type: 'linear',
      fixedrange: true,
      range: [0, Math.max(0, bars.length - 1)],
      rangeslider: { visible: false },
      gridcolor: '#1f2937',
      tickmode: 'array',
      tickvals: bars.map((_, i) => i).filter(i => i % 24 === 0),
      ticktext: bars.map((b, i) => (i % 24 === 0 ? b.time.slice(11, 16) : null)).filter(v => v != null),
    },
    yaxis: {
      fixedrange: true,
      gridcolor: '#1f2937',
      range: globalYRange,
    },
    margin: { l: MAIN_MARGIN_LEFT, r: MAIN_MARGIN_RIGHT, t: 20, b: 40 },
    shapes: buildAllShapes(),
    legend: { orientation: 'h', y: 1.08, x: 0 },
  };

  Plotly.newPlot(chartEl, traces, layout, {
    responsive: false,
    scrollZoom: false,
    displaylogo: false,
    modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'autoScale2d', 'resetScale2d'],
  });

  // 初始滚动到最近K线附近，并动态调整可见区Y范围
  centerOnIndex(Math.max(0, bars.length - 1));
  chartWrapEl.onscroll = () => {
    if (scrollRaf) cancelAnimationFrame(scrollRaf);
    scrollRaf = requestAnimationFrame(() => {
      syncMiniWindowFromMainScroll();
      updateMainYRangeByViewport();
    });
  };
  chartWrapEl.onclick = (ev) => {
    const wrapRect = chartWrapEl.getBoundingClientRect();
    const xInWrap = ev.clientX - wrapRect.left;
    const xInChart = chartWrapEl.scrollLeft + xInWrap;
    const idx = Math.round(indexFromChartPixel(xInChart));
    handleBarSelection(Math.max(0, Math.min(bars.length - 1, idx)));
  };
  updateMainYRangeByViewport();

  chartEl.on('plotly_click', (ev) => {
    const idx = resolveBarIndexFromClick(ev);
    handleBarSelection(idx);
  });
}

function openBarModal(idx) {
  const b = bars[idx];
  modalPayload = { mode: 'bar', bar_time: b.time, bar_index: idx, price: b.close };
  modalTitle.textContent = '单K评论';
  modalTarget.textContent = fmtBar(b, idx);
  commentEl.value = '';
  modal.showModal();
}

function openRangeModal(a, b) {
  const start = bars[a];
  const end = bars[b];
  modalPayload = {
    mode: 'range',
    start_time: start.time,
    end_time: end.time,
    start_index: a,
    end_index: b,
    bar_time: start.time,
    bar_index: a,
    price: (start.close + end.close) / 2,
  };

  modalTitle.textContent = '区间评论';
  modalTarget.textContent = `start: ${start.time} (#${a})\nend  : ${end.time} (#${b})\nbars : ${b - a + 1}`;
  commentEl.value = '';
  modal.showModal();
}

async function saveToPending() {
  if (!modalPayload) return;
  const text = commentEl.value.trim();
  if (!text) {
    alert('评论不能为空');
    return;
  }

  const item = {
    ...modalPayload,
    kind: kindEl.value,
    tag: tagEl.value.trim(),
    comment: text,
  };

  try {
    const res = await fetch('/api/comments', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(item),
    }).then(r => r.json());
    if (!res.ok) {
      alert(`保存失败: ${res.error || ''}`);
      return;
    }
    const saved = res.item || item;
    pending.push(saved);
    comments.push(saved);
  } catch (e) {
    alert(`保存失败: ${e.message}`);
    return;
  }

  modal.close();
  modalPayload = null;
  renderPending();
  renderLogs();
  updateSubmitCount();
  computeFlowEvents();
  renderFlowList();
  if (chartEl && chartEl.data) {
    buildChart();
  }
}

async function submitPending() {
  if (pending.length === 0) {
    alert('没有待提交评论');
    return;
  }

  const res = await fetch('/api/comments/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ engine_file: engineCurrent?.file || '' }),
  }).then(r => r.json());

  if (!res.ok) {
    alert(`提交失败: ${res.error || ''}`);
    return;
  }

  comments = [];
  pending = [];
  renderPending();
  renderLogs();
  updateSubmitCount();
  computeFlowEvents();
  renderFlowList();
  renderStats();
  buildChart();
  alert(`提交完成：${res.count || 0} 条，归档到 ${res.archive_file || '(无)'}`);
}

async function clearAllComments() {
  if (!confirm('确认清空所有已提交评论吗？此操作不可撤销。')) return;
  try {
    const res = await fetch('/api/comments/clear', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    }).then(r => r.json());
    if (!res.ok) {
      alert(`清空失败: ${res.error || ''}`);
      return;
    }
    comments = [];
    pending = [];
    renderPending();
    updateSubmitCount();
    renderLogs();
    computeFlowEvents();
    renderFlowList();
    buildChart();
    alert('评论已清空');
  } catch (e) {
    alert(`清空失败: ${e.message}`);
  }
}

async function loadData() {
  const [ohlcRes, commentsRes, tradesRes, datasetsRes, enginesRes] = await Promise.all([
    fetchJsonNoCache('/api/ohlc'),
    fetchJsonNoCache('/api/comments'),
    fetchJsonNoCache('/api/trades'),
    fetchJsonNoCache('/api/datasets'),
    fetchJsonNoCache('/api/engines'),
  ]);

  if (!ohlcRes.ok) throw new Error(ohlcRes.error || '加载OHLC失败');

  bars = (ohlcRes.data.rows || []).map(b => ({ ...b, time: toTime(b.time) }));
  barIndexByTime = new Map(bars.map((b, i) => [b.time, i]));
  comments = commentsRes.items || [];
  pending = [...comments];
  trades = (tradesRes.data && tradesRes.data.trades) ? tradesRes.data.trades : [];
  tradePnlList = (tradesRes.data && tradesRes.data.trade_pnl_list) ? tradesRes.data.trade_pnl_list : [];
  dailyPnlList = (tradesRes.data && tradesRes.data.daily_pnl_list) ? tradesRes.data.daily_pnl_list : [];
  commonParams = (tradesRes.data && tradesRes.data.summary && tradesRes.data.summary.common_params)
    ? tradesRes.data.summary.common_params
    : commonParams;
  currentBuildId = String(
    (ohlcRes.data && ohlcRes.data.build_id) ||
    (tradesRes.data && tradesRes.data.summary && tradesRes.data.summary.build_id) ||
    ''
  );

  if (datasetsRes && datasetsRes.ok) {
    datasetCatalog = datasetsRes.catalog || datasetCatalog;
    datasetCurrent = datasetsRes.current || datasetCurrent;
    // ohlc源优先，避免current缺失时控件不同步
    const sourceFile = baseName(ohlcRes.data.source_file || '');
    if (sourceFile) {
      datasetCurrent.file = sourceFile;
      if (!datasetCurrent.bucket) {
        datasetCurrent.bucket = inferBucketFromFileName(sourceFile);
      }
    }
    syncDatasetControls();
  }
  if (enginesRes && enginesRes.ok) {
    engineCatalog = enginesRes.catalog || [];
    engineCurrent = enginesRes.current || engineCurrent;
    syncEngineControls();
  }

  const bollDev = (ohlcRes.data.bollinger_deviation != null ? ohlcRes.data.bollinger_deviation : 'n/a');
  const srcFile = baseName(ohlcRes.data.source_file || datasetCurrent.file || '');
  const srcBucket = datasetCurrent.bucket || inferBucketFromFileName(srcFile);
  const engineName = engineCurrent?.file || 'N/A';
  const engineModule = baseName(ohlcRes.data.engine_module || '');
  const genAt = ohlcRes.data.generated_at || (tradesRes.data && tradesRes.data.summary && tradesRes.data.summary.generated_at) || '';
  if (dataMetaEl) {
    dataMetaEl.textContent = `${ohlcRes.data.symbol} | ${ohlcRes.data.timeframe} | 引擎=${engineName} (${engineModule || 'n/a'}) | ${bucketLabel(srcBucket)}=${srcFile || 'N/A'} | BollDev=${bollDev} | ${ohlcRes.data.count} bars | trades: ${trades.length} | build=${currentBuildId || 'n/a'} | rebuilt=${genAt || 'n/a'}`;
  }
}

modeBarBtn.onclick = () => setMode('bar');
modeRangeBtn.onclick = () => setMode('range');
flowOpsBtn.onclick = () => setFlowMode('ops');
flowAllBtn.onclick = () => setFlowMode('all');
saveBtn.onclick = saveToPending;
cancelBtn.onclick = () => { modal.close(); modalPayload = null; };
submitPendingTop.onclick = submitPending;
if (clearCommentsBtn) {
  clearCommentsBtn.onclick = clearAllComments;
}
if (datasetBucketEl) {
  datasetBucketEl.onchange = () => renderDatasetFiles(datasetBucketEl.value);
}
if (switchDatasetBtn) {
  switchDatasetBtn.onclick = switchDatasetAndRefresh;
}
if (switchEngineBtn) {
  switchEngineBtn.onclick = switchEngineAndRefresh;
}
if (openCommonConfigBtn) {
  openCommonConfigBtn.onclick = openCommonConfigModal;
}
if (commonConfigSaveBtn) {
  commonConfigSaveBtn.onclick = saveCommonConfig;
}
if (commonConfigCancelBtn) {
  commonConfigCancelBtn.onclick = () => { if (commonConfigModal) commonConfigModal.close(); };
}
if (applyTradeRangeBtn) {
  applyTradeRangeBtn.onclick = () => applyTradeRangeAndRender(false, { forceReset: false });
}
if (resetTradeRangeBtn) {
  resetTradeRangeBtn.onclick = () => {
    applyTradeRangeAndRender(false, { forceReset: true });
  };
}

window.addEventListener('resize', () => {
  if (bars.length > 0) {
    buildChart();
    buildMiniChart();
  }
});

(async function init() {
  try {
    await loadData();
    computeGlobalYRange();
    renderPending();
    renderLogs();
    updateSubmitCount();
    computeFlowEvents();
    renderFlowList();
    renderStats();
    renderTradeExplorer();
    buildChart();
    buildMiniChart();
  } catch (e) {
    if (dataMetaEl) dataMetaEl.textContent = `加载失败: ${e.message}`;
    console.error(e);
  }
})();
