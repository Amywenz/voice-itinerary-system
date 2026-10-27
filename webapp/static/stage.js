/* 可视化大屏交互：倒计时、实时天气刷新、波形动画、全屏，无第三方依赖。 */
const stage$ = (sel, root = document) => root.querySelector(sel);

const SCENE_MAP = [
  { keys: ["雨"], cls: "wx-scene--rain" },
  { keys: ["雪"], cls: "wx-scene--snow" },
  { keys: ["晴"], cls: "wx-scene--sun" },
  { keys: ["云", "阴", "雾", "霾"], cls: "wx-scene--cloud" },
];

function applyScene(text) {
  const scene = stage$("#swScene");
  if (!scene) return;
  const hit = SCENE_MAP.find((item) => item.keys.some((k) => (text || "").includes(k)));
  scene.className = `wx-scene ${hit ? hit.cls : "wx-scene--cloud"}`;
}

/* ---------------- 波形：静态柱高 + 播放时跳动 ---------------- */
(function buildWave() {
  const wrap = stage$("#waveBars");
  if (!wrap) return;
  const count = 34;
  for (let i = 0; i < count; i += 1) {
    const bar = document.createElement("i");
    const base = 14 + Math.abs(Math.sin(i * 1.7)) * 66;
    bar.style.setProperty("--h", `${base.toFixed(0)}%`);
    bar.style.setProperty("--d", `${((i % 9) * 0.06).toFixed(2)}s`);
    wrap.appendChild(bar);
  }
})();

/* ---------------- 倒计时环 ---------------- */
(function countdown() {
  const label = stage$("#stageCountdown");
  const ring = stage$("#ringFg");
  if (!label) return;
  const raw = label.dataset.target;
  const fresh = raw ? new Date(raw.replace("T", " ")) : null;
  const total = fresh ? Math.max(fresh - new Date(), 1) : 0;
  const CIRC = 326.73;
  const pad = (n) => String(n).padStart(2, "0");

  const render = () => {
    if (!fresh || Number.isNaN(fresh.getTime())) {
      label.textContent = "--:--";
      if (ring) ring.style.strokeDashoffset = 0;
      return;
    }
    const diff = Math.floor((fresh - new Date()) / 1000);
    if (diff <= 0) {
      label.textContent = "已到时间";
      if (ring) ring.style.strokeDashoffset = CIRC;
      return;
    }
    if (diff >= 3600) {
      label.textContent = `${Math.floor(diff / 3600)}时${pad(Math.floor((diff % 3600) / 60))}分`;
    } else {
      label.textContent = `${pad(Math.floor(diff / 60))}:${pad(diff % 60)}`;
    }
    if (ring) ring.style.strokeDashoffset = CIRC * (1 - diff / total);
  };
  render();
  setInterval(render, 1000);
})();

/* ---------------- 实时刷新 ---------------- */
function paintWeather(data) {
  const now = data.now || {};
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };
  set("swTemp", now.temp ?? "--");
  set("swFeels", `${now.feelsLike ?? "--"}°C`);
  set("swHumidity", `${now.humidity ?? "--"}%`);
  set("swWind", `${now.windDir ?? "--"} ${now.windScale ?? ""}级`);
  set("swText", now.text ?? "暂无数据");
  set("swAdvice", data.advice || "暂无建议");
  const src = document.getElementById("swSource");
  if (src) {
    src.textContent = data.source === "mock" ? "离线样例" : data.source === "qweather" ? "和风天气" : "暂不可用";
  }
  applyScene(now.text);
}

function paintStatus(info) {
  if (!info) return;
  const dur = document.getElementById("statDuration");
  if (dur && info.audio) dur.textContent = info.audio.duration;
}

/* ---------------- 全站音色 & 播报结果 ---------------- */
function paintStageVoice() {
  const chip = document.getElementById("stageVoiceName");
  if (!chip) return;
  const pref = window.voicePref?.get?.() || {};
  chip.textContent = pref.name || "默认音色";
}
paintStageVoice();
window.addEventListener("voice:changed", paintStageVoice);

document.addEventListener("broadcast:done", (event) => {
  const data = event.detail || {};
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el && value !== undefined && value !== null && value !== "") el.textContent = value;
  };
  set("stageVoiceName", data.voice);
  set("stageCourse", data.course);
  set("stageSpoken", data.advice);
  set("statDuration", data.duration);
  const runs = document.getElementById("kpiRuns");
  if (runs) runs.textContent = String((Number(runs.textContent) || 0) + 1);
});

/* ---------------- 今日待办卡片 ---------------- */
function renderStageTodos() {
  const wrap = document.getElementById("stageTodoList");
  if (!wrap || !window.todoStore) return;
  const items = window.todoStore.load().items;
  const done = items.filter((item) => item.done).length;
  const undone = items.filter((item) => !item.done);

  const kpi = document.getElementById("kpiTodo");
  if (kpi) kpi.textContent = items.length ? `${done}/${items.length}` : "--";
  const hint = document.getElementById("kpiTodoHint");
  if (hint) hint.textContent = items.length ? (undone.length ? `还剩 ${undone.length} 件` : "今天全部完成") : "还没有添加待办";
  const summary = document.getElementById("stageTodoSummary");
  if (summary) summary.textContent = items.length ? `完成 ${done} / ${items.length}` : "完成后会在这里打勾";

  wrap.innerHTML = "";
  if (!items.length) {
    wrap.innerHTML = '<div class="stage-empty slim">还没有待办，去「今日待办」添加一件吧</div>';
    return;
  }
  [...undone, ...items.filter((item) => item.done)].slice(0, 4).forEach((item) => {
    const row = document.createElement("div");
    row.className = "stage-todo" + (item.done ? " is-done" : "");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "stage-todo-check";
    btn.dataset.id = item.id;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M5 12l5 5L19 7"/></svg>';
    const text = document.createElement("span");
    text.textContent = item.text;
    row.append(btn, text);
    wrap.appendChild(row);
  });
}
renderStageTodos();
window.addEventListener("todos:changed", renderStageTodos);
document.getElementById("stageTodoList")?.addEventListener("click", (event) => {
  const btn = event.target.closest(".stage-todo-check");
  if (!btn) return;
  window.todoStore.toggle(btn.dataset.id);
  renderStageTodos();
});

async function refreshStage(showToast = false) {
  const btn = stage$("#stageRefresh");
  if (btn) btn.disabled = true;
  const city = window.citySync?.current || window.__CITY__ || "";
  try {
    const [weatherData, status] = await Promise.all([
      api(`/api/weather${city ? `?city=${encodeURIComponent(city)}` : ""}`),
      api("/api/status"),
    ]);
    paintWeather(weatherData);
    paintStatus(status);
    if (showToast) toast("数据已刷新", `${weatherData.now?.text || "天气"} · ${weatherData.source}`, "ok");
  } catch (err) {
    toast("刷新失败", err.message, "err");
  } finally {
    if (btn) btn.disabled = false;
  }
}

stage$("#stageRefresh")?.addEventListener("click", () => refreshStage(true));
setInterval(() => refreshStage(false), 60000);

/* ---------------- 音频波形联动 ---------------- */
const audio = stage$("#latestAudio");
const voiceCard = stage$(".voice-card");
if (audio && voiceCard) {
  const active = () => voiceCard.classList.add("is-playing");
  const idle = () => voiceCard.classList.remove("is-playing");
  audio.addEventListener("play", active);
  audio.addEventListener("pause", idle);
  audio.addEventListener("ended", idle);
  audio.addEventListener("loadedmetadata", () => {
    if (audio.duration) {
      const dur = document.getElementById("statDuration");
      if (dur) dur.textContent = audio.duration.toFixed(2);
    }
  });
  stage$("#waveBars")?.addEventListener("click", () => {
    if (audio.paused) audio.play().catch(() => toast("无法播放", "请检查浏览器音频权限", "err"));
    else audio.pause();
  });
}

/* ---------------- 全屏 ---------------- */
stage$("#stageFullscreen")?.addEventListener("click", () => {
  if (document.fullscreenElement) {
    document.exitFullscreen?.();
  } else {
    document.documentElement.requestFullscreen?.().catch(() => toast("全屏失败", "浏览器未允许全屏", "err"));
  }
});

applyScene(document.getElementById("swText")?.textContent || "");
