/* 行程播报控制台交互：无第三方依赖，全部走 /api。 */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function toast(title, message = "", type = "ok") {
  const wrap = $("#toastWrap");
  if (!wrap) return;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.innerHTML = `<div class="t">${title}</div>${message ? `<div class="m">${message}</div>` : ""}`;
  wrap.appendChild(node);
  setTimeout(() => node.remove(), 4200);
}

async function api(url, options = {}) {
  const opts = { headers: { "Content-Type": "application/json" }, ...options };
  if (opts.body && typeof opts.body !== "string") opts.body = JSON.stringify(opts.body);
  const resp = await fetch(url, opts);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `请求失败（HTTP ${resp.status}）`);
  return data;
}

/* ---------------- 全站音色：语音工坊里选一次，所有页面共用 ---------------- */
const VOICE_KEY = "itinerary-voice";
const voiceChannel = "BroadcastChannel" in window ? new BroadcastChannel("itinerary-voice") : null;

function readVoicePref() {
  try {
    const raw = JSON.parse(localStorage.getItem(VOICE_KEY) || "{}");
    return {
      lang: raw.lang || "zh-CN",
      voice: raw.voice || null,
      style: raw.style || "natural",
      name: raw.name || "",
    };
  } catch (e) {
    return { lang: "zh-CN", voice: null, style: "natural", name: "" };
  }
}

function paintGlobalVoice(pref = readVoicePref()) {
  const badge = document.getElementById("globalVoice");
  if (badge) badge.textContent = `音色：${pref.name || "默认"}`;
  const state = document.getElementById("globalVoiceState");
  if (state) {
    state.textContent = pref.voice
      ? `${pref.name || pref.voice} · ${pref.lang} · ${pref.style || "natural"}`
      : "尚未指定，使用默认音色";
  }
  const dash = document.getElementById("dashVoiceName");
  if (dash) dash.textContent = pref.name || "默认音色";
  window.dispatchEvent(new CustomEvent("voice:changed", { detail: pref }));
}

const voicePref = {
  get: readVoicePref,
  set(patch = {}) {
    const next = { ...readVoicePref(), ...patch };
    try { localStorage.setItem(VOICE_KEY, JSON.stringify(next)); } catch (e) { /* 隐私模式忽略 */ }
    paintGlobalVoice(next);
    voiceChannel?.postMessage(next);
    return next;
  },
};

window.voicePref = voicePref;
paintGlobalVoice();
voiceChannel?.addEventListener("message", (event) => paintGlobalVoice(event?.data || readVoicePref()));
window.addEventListener("storage", (event) => {
  if (event.key === VOICE_KEY) paintGlobalVoice();
});

/* ---------------- 今日待办：浏览器本地存储，跨天自动带入未完成项 ---------------- */
const TODO_KEY = "itinerary-todos";
const todayKey = () => new Date().toLocaleDateString("sv-SE"); // YYYY-MM-DD

const todoStore = {
  load() {
    let data = null;
    try { data = JSON.parse(localStorage.getItem(TODO_KEY) || "null"); } catch (e) { data = null; }
    if (!data || !Array.isArray(data.items)) return { date: todayKey(), items: [] };
    const today = todayKey();
    if (data.date !== today) {
      // 新的一天：未完成的事继续带着，已完成的不再占位置
      data.items = data.items.filter((item) => !item.done);
      data.date = today;
      todoStore.save(data.items);
    }
    return data;
  },
  save(items) {
    try { localStorage.setItem(TODO_KEY, JSON.stringify({ date: todayKey(), items })); } catch (e) { /* 忽略 */ }
    window.dispatchEvent(new CustomEvent("todos:changed", { detail: items }));
    return items;
  },
  add(text) {
    const items = todoStore.load().items;
    items.push({ id: Date.now().toString(36), text, done: false, created: new Date().toISOString() });
    return todoStore.save(items);
  },
  toggle(id) {
    return todoStore.save(todoStore.load().items.map((item) => (
      item.id === id ? { ...item, done: !item.done } : item
    )));
  },
  remove(id) {
    return todoStore.save(todoStore.load().items.filter((item) => item.id !== id));
  },
  clearDone() {
    return todoStore.save(todoStore.load().items.filter((item) => !item.done));
  },
};

window.todoStore = todoStore;

/* 顶部徽标与跨标签页同步 */
window.addEventListener("storage", (event) => {
  if (event.key === TODO_KEY) window.dispatchEvent(new CustomEvent("todos:changed"));
});


function setAudio(url) {
  const players = $$(".js-audio");
  if (!players.length) {
    const fallback = document.getElementById("latestAudio");
    if (!fallback) return;
    fallback.src = url;
    fallback.load();
    fallback.play().catch(() => toast("音频已更新", "浏览器拦截了自动播放，请点击播放键", "ok"));
    return;
  }
  players.forEach((audio) => { audio.src = url; audio.load(); });
  players[0].play().catch(() => toast("音频已更新", "浏览器拦截了自动播放，请点击播放键", "ok"));
}

function updateWeather(data) {
  const now = data.now || {};
  const set = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
  set("wTemp", now.temp ?? "--");
  set("wFeels", now.feelsLike ?? "--");
  set("wText", now.text ?? "--");
  set("wHumidity", now.humidity ?? "--");
  set("wWind", now.windDir ?? "--");
  set("wAdvice", data.advice || "暂无建议");
  set("outWindDir", now.windDir ?? "--");
  set("outWindScale", now.windScale ?? "");
  set("outHumidity", now.humidity ?? "--");
  const rain = /雨|雪/.test(now.text || "");
  const rainBox = $("#outRain");
  if (rainBox) {
    rainBox.classList.toggle("is-on", rain);
    const title = rainBox.querySelector("strong");
    const desc = rainBox.querySelector("span");
    if (title) title.textContent = rain ? "带伞" : "不用带伞";
    if (desc) desc.textContent = rain ? "今天有雨雪，别淋湿" : "今天没有雨雪";
  }
  const temp = Number(now.feelsLike ?? now.temp ?? 20);
  const tempBox = $("#outTemp");
  if (tempBox) {
    const cold = temp < 8;
    const hot = temp > 28;
    tempBox.classList.toggle("is-on", cold || hot);
    const title = tempBox.querySelector("strong");
    const desc = tempBox.querySelector("span");
    if (title) title.textContent = cold ? "穿厚一点" : hot ? "注意防晒" : "穿舒适即可";
    if (desc) desc.textContent = cold ? "气温偏低，注意保暖" : hot ? "天气偏热，多喝水" : "温度刚好，适合出门";
  }
  const humid = Number(now.humidity ?? 50);
  const humidHint = $("#outHumidityHint");
  if (humidHint) humidHint.textContent = humid > 70 ? "有点潮，注意通风" : "体感比较舒服";
  const source = document.getElementById("wSource");
  if (source) {
    source.textContent = data.source === "mock" ? "离线样例" : data.source === "qweather" ? "和风天气" : "暂不可用";
    source.className = `badge-soft ${data.source === "mock" ? "badge-warn" : data.source === "qweather" ? "badge-accent" : "badge-danger"}`;
  }
}

function updateDashboard(data) {
  const now = data.now || {};
  const set = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
  set("dashFeels", now.feelsLike ?? "--");
  set("dashText", now.text ?? "暂无数据");
  set("dashSource", data.source || "-");
  set("dashTemp", now.temp ?? "--");
  set("dashWeatherText", now.text ?? "暂无数据");
  set("dashFeelsTag", now.feelsLike ?? "--");
  set("dashHumidity", now.humidity ?? "--");
  set("dashWind", now.windDir ?? "--");
  set("dashWindScale", now.windScale ?? "");
  const badge = document.getElementById("dashSourceBadge");
  if (badge) {
    badge.textContent = data.source === "mock" ? "离线样例" : data.source === "qweather" ? "和风天气" : "暂不可用";
    badge.className = `badge-soft ${data.source === "mock" ? "badge-warn" : data.source === "qweather" ? "badge-accent" : "badge-danger"}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // 顶栏时钟
  const clock = $("#clock");
  const tick = () => {
    if (!clock) return;
    const d = new Date();
    clock.textContent = d.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }) + " " +
      d.toLocaleTimeString("zh-CN", { hour12: false });
  };
  tick();
  setInterval(tick, 1000);

  // 下一节课倒计时
  const countdown = $("#countdown");
  if (countdown && countdown.dataset.next) {
    const target = new Date(countdown.dataset.next.replace("T", " "));
    const course = countdown.dataset.course || "";
    const render = () => {
      const diff = Math.floor((target - new Date()) / 1000);
      if (Number.isNaN(diff)) return;
      if (diff <= 0) { countdown.textContent = `${course} · 即将上课`; return; }
      const h = Math.floor(diff / 3600);
      const m = Math.floor((diff % 3600) / 60);
      const wait = `还有 ${h ? h + " 小时 " : ""}${m} 分钟`;
      countdown.textContent = course ? `${course} · ${wait}` : wait;
    };
    render();
    setInterval(render, 30000);
  }

  // 仪表盘：一键播报。地区 / 语言 / 音色角色 / 播报方式都读控制台的下拉框
  const castState = $("#castState");

  const renderNews = (items) => {
    const strip = $(".news-strip");
    if (!strip) return;
    const rows = (items || []).slice(0, 3);
    strip.innerHTML = rows.length ? rows.map((row, index) => `
      <div class="news-line">
        <span class="idx">${index + 1}</span>
        <span class="txt">${row.title}</span>
        <span class="tag ${row.local ? "local" : ""}">${row.local ? "本地" : "综合"}</span>
      </div>`).join("") : `<div class="empty">暂时没有抓到资讯，断网时会读取本地缓存</div>`;
  };

  const loadCity = async (city, silent = false) => {
    if (!city) return;
    try {
      const weatherData = await api(`/api/weather?city=${encodeURIComponent(city)}`);
      updateWeather(weatherData);
      updateDashboard(weatherData);
      const advice = $("#latestAdvice");
      if (advice) advice.textContent = weatherData.advice;
      const newsData = await api(`/api/news?city=${encodeURIComponent(city)}`);
      renderNews(newsData.items);
      const updated = $("#dashNewsUpdated");
      if (updated) updated.textContent = newsData.updated || "暂无";
      const url = new URL(location.href);
      url.searchParams.set("city", city);
      history.replaceState(null, "", url);
      window.citySync?.set(city);
      if (silent) return;
      const label = $("#castCity")?.selectedOptions?.[0]?.textContent || city;
      toast("地区已切换", `${label} · ${weatherData.now.text || ""} ${weatherData.now.temp || "--"}°C`, "ok");
    } catch (err) { if (!silent) toast("切换失败", err.message, "err"); }
  };

  async function runBroadcast(btn) {
    if (!btn || btn.disabled) return;
    const pref = voicePref.get();
    const city = $("#castCity")?.value || window.citySync?.current || "";
    const lang = $("#castLang")?.value || pref.lang || "zh-CN";
    const style = $("#castStyle")?.value || pref.style || "natural";
    // 语音工坊选中的音色属于某一种语言，跨语言时不强行指定，避免后端报错
    const voice = pref.lang === lang ? pref.voice : null;
    const mode = $("#castMode")?.value || "fast";
    const label = btn.innerHTML;
    btn.disabled = true;
    btn.textContent = "合成中…";
    if (castState) castState.textContent = "正在准备播报…";
    try {
      const data = await api("/api/trigger", { method: "POST", body: { city, lang, style, mode, voice } });
      const advice = $("#latestAdvice");
      if (advice) advice.textContent = data.advice;
      const engine = $("#latestEngine");
      if (engine) engine.textContent = `${data.voice}${data.style ? " · " + data.style : ""}`;
      setAudio(data.audio);
      const detail = `${data.voice}${data.style ? " · " + data.style : ""} · 时长 ${data.duration}s`;
      if (castState) {
        castState.textContent = detail + (data.fallback_reason ? ` · ${data.fallback_reason}` : "");
      }
      // 大屏等页面监听这个事件，同步刷新卡片里的播报信息
      document.dispatchEvent(new CustomEvent("broadcast:done", { detail: data }));
      toast("播报完成", `${data.course} · ${data.voice} · ${seconds}s`, "ok");
    } catch (err) {
      if (castState) castState.textContent = "播报失败：" + err.message;
      toast("播报失败", err.message, "err");
    } finally {
      btn.disabled = false;
      btn.innerHTML = label;
    }
  }

  $("#castBtn")?.addEventListener("click", (event) => runBroadcast(event.currentTarget));
  $("#triggerBtn")?.addEventListener("click", (event) => runBroadcast(event.currentTarget));
  $("#castCity")?.addEventListener("change", (event) => loadCity(event.target.value));

  // 仪表盘上改语言 / 角色，等同在语音工坊里改全站偏好
  $("#castLang")?.addEventListener("change", (event) => {
    voicePref.set({ lang: event.target.value, voice: null, name: "" });
    toast("语言已切换", `全站播报将使用 ${event.target.value}`, "ok");
  });
  $("#castStyle")?.addEventListener("change", (event) => {
    voicePref.set({ style: event.target.value });
    toast("角色已切换", "全站播报立即生效", "ok");
  });

  // 打开发布页时，用全站偏好回填控制台
  (function initCastControls() {
    const pref = voicePref.get();
    const lang = $("#castLang");
    const style = $("#castStyle");
    if (lang && Array.from(lang.options).some((o) => o.value === pref.lang)) lang.value = pref.lang;
    if (style && Array.from(style.options).some((o) => o.value === pref.style)) style.value = pref.style;
  })();

  // 仪表盘每 60 秒静默刷新当前城市的天气与资讯，页面开着也能看到最新数据
  if ($("#castCity")) {
    setInterval(() => {
      const city = window.citySync?.current || $("#castCity")?.value;
      if (city && document.visibilityState === "visible") loadCity(city, true);
    }, 60000);
  }

  $("#demoBtn")?.addEventListener("click", async () => {
    try {
      await api("/api/courses/demo", { method: "POST" });
      toast("示例课程已载入", "页面即将刷新", "ok");
      setTimeout(() => location.reload(), 700);
    } catch (err) { toast("载入失败", err.message, "err"); }
  });

  // 课程表
  $("#courseForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const time = $("#courseTime").value;
    const name = $("#courseName").value.trim();
    if (!time || !name) return toast("请填写完整", "时间和课程名都不能为空", "err");
    try {
      await api("/api/courses", { method: "POST", body: { time, course_name: name } });
      toast("课程已添加", `${time} · ${name}`, "ok");
      setTimeout(() => location.reload(), 500);
    } catch (err) { toast("添加失败", err.message, "err"); }
  });

  $$(".del-course").forEach((btn) => btn.addEventListener("click", async () => {
    const time = btn.dataset.time;
    if (!confirm(`删除 ${time} 的课程？`)) return;
    try {
      await api(`/api/courses/${encodeURIComponent(time)}`, { method: "DELETE" });
      toast("已删除", time, "ok");
      setTimeout(() => location.reload(), 400);
    } catch (err) { toast("删除失败", err.message, "err"); }
  }));

  $("#triggerNext")?.addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    btn.disabled = true;
    try {
      const data = await api("/api/trigger", { method: "POST", body: {} });
      setAudio(data.audio);
      const box = $("#triggerResult");
      if (box) box.textContent = data.advice;
      toast("播报完成", `${data.course} · ${data.engine}`, "ok");
    } catch (err) { toast("播报失败", err.message, "err"); }
    finally { btn.disabled = false; }
  });

  // 天气页
  const loadWeather = async (city) => {
    const target = city || window.citySync?.current || $("#citySelect")?.value || "";
    try {
      const data = await api(`/api/weather${target ? `?city=${encodeURIComponent(target)}` : ""}`);
      updateWeather(data);
      if (target && data.city) {
        window.citySync?.set(data.city);
        const url = new URL(location.href);
        url.searchParams.set("city", data.city);
        history.replaceState(null, "", url);
      }
    } catch (err) { toast("天气获取失败", err.message, "err"); }
  };
  $("#citySelect")?.addEventListener("change", (event) => loadWeather(event.target.value));
  $("#refreshWeather")?.addEventListener("click", () => loadWeather($("#citySelect")?.value));
  if ($("#citySelect")) {
    // 天气页每 60 秒自动刷新，切换城市后不用手动点
    setInterval(() => { if (document.visibilityState === "visible") loadWeather(); }, 60000);
  }

  $("#synthAdvice")?.addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    const text = $("#wAdvice").textContent.trim();
    if (!text) return toast("没有建议文本", "请先刷新天气", "err");
    btn.disabled = true;
    btn.textContent = "合成中…";
    try {
      const data = await api("/api/tts", { method: "POST", body: { text, engine: "auto", speed: 1.0 } });
      setAudio(data.audio);
      toast("合成完成", `${data.meta.engine} · ${data.meta.duration}s`, "ok");
    } catch (err) { toast("合成失败", err.message, "err"); }
    finally { btn.disabled = false; btn.textContent = "用这段建议合成语音"; }
  });

  // 语音工坊
  $("#studioTextForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const btn = $("#studioSubmit");
    const text = $("#studioText")?.value.trim();
    if (!text) return toast("文本为空", "请输入要合成的内容", "err");
    const pref = voicePref.get();
    btn.disabled = true;
    btn.textContent = "合成中…";
    try {
      const data = await api("/api/voice/tts", {
        method: "POST",
        body: { text, lang: pref.lang, voice: pref.voice, speed: 1.0, style: pref.style },
      });
      const audio = $("#studioAudio");
      if (audio) { audio.src = data.audio; audio.load(); audio.play().catch(() => {}); }
      toast("合成完成", `${data.meta.voice_name} · ${data.meta.duration}s`, "ok");
    } catch (err) { toast("合成失败", err.message, "err"); }
    finally { btn.disabled = false; btn.textContent = "生成语音"; }
  });

  // 设置
  $("#configForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {
      provider: $("#providerSelect").value,
      default_city: $("#cityCode").value,
      speed: Number($("#settingSpeed").value),
    };
    const engine = $("#engineSetting")?.value;
    if (engine) body.tts_engine = engine;
    const key = $("#apiKey").value.trim();
    if (key) body.api_key = key;
    try {
      await api("/api/config", { method: "POST", body });
      toast("设置已保存", "配置写入 config.yaml，立即生效", "ok");
    } catch (err) { toast("保存失败", err.message, "err"); }
  });

  // 日志
  $("#refreshLogs")?.addEventListener("click", async () => {
    try {
      const logs = await api("/api/logs");
      const tbody = $("#logBody");
      if (!tbody) return;
      tbody.innerHTML = logs.length ? logs.map((row) => `
        <tr>
          <td class="mono dim">${row.time || "-"}</td>
          <td>${row.course || "-"}</td>
          <td>${row.provider || "-"}</td>
          <td><span class="badge-soft ${row.engine === "openvoice" ? "badge-accent" : "badge-warn"}">${row.engine || "-"}</span></td>
          <td class="muted">${(row.advice || "").slice(0, 48)}${(row.advice || "").length > 48 ? "…" : ""}</td>
        </tr>`).join("") : `<tr><td colspan="5" class="dim">暂无记录</td></tr>`;
      toast("日志已刷新", `共 ${logs.length} 条`, "ok");
    } catch (err) { toast("刷新失败", err.message, "err"); }
  });
});

/* ---------------- 主题切换（糖果 / 赛博） ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  const toggle = $("#themeToggle");
  const label = $("#themeLabel");
  const sync = () => {
    const theme = document.documentElement.dataset.theme || "candy";
    if (label) label.textContent = theme === "candy" ? "糖果青春" : "赛博校园";
  };
  sync();
  toggle?.addEventListener("click", () => {
    const next = (document.documentElement.dataset.theme || "candy") === "candy" ? "cyber" : "candy";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("itinerary-theme", next);
    sync();
    toast(next === "candy" ? "已切换：糖果青春" : "已切换：赛博校园", "配色会记住，下次打开自动生效", "ok");
  });
});

/* ---------------- 多语言音色实验室：选中即设为全站音色 ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  const holder = document.getElementById("voiceCatalog");
  if (!holder) return;
  const catalog = JSON.parse(holder.textContent);
  const grid = $("#voiceGrid");
  const textArea = $("#voiceText");
  const styleSelect = $("#voiceStyle");
  if (!grid || !catalog.languages?.length) return;

  const pref = voicePref.get();
  const langExists = catalog.languages.some((row) => row.code === pref.lang);
  let currentLang = langExists ? pref.lang : catalog.languages[0].code;
  let currentVoice = langExists ? pref.voice : null;

  $$(".lang-tab", $("#langTabs")).forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.lang === currentLang);
  });
  if (styleSelect && Array.from(styleSelect.options).some((o) => o.value === pref.style)) {
    styleSelect.value = pref.style;
  }

  const releaseGlobal = (voice, langMeta) => {
    currentVoice = voice.id;
    voicePref.set({
      lang: currentLang,
      voice: voice.id,
      name: voice.name,
      style: styleSelect?.value || pref.style || "natural",
    });
    toast("已设为全站音色", `${voice.name} · ${langMeta.name}，所有页面立即生效`, "ok");
  };

  const renderVoices = () => {
    const row = catalog.languages.find((item) => item.code === currentLang) || catalog.languages[0];
    currentLang = row.code;
    if (!row.voices.some((voice) => voice.id === currentVoice)) currentVoice = null;
    grid.innerHTML = "";
    row.voices.forEach((voice) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "voice-opt" + (voice.id === currentVoice ? " active" : "");
      btn.dataset.id = voice.id;
      if (!voice.available) btn.title = voice.reason;
      btn.innerHTML = `
        <span class="v-state ${voice.available ? "" : "bad"}">${voice.available ? "可用" : "需配置"}</span>
        <span class="v-name">${voice.name}</span>
        <span class="v-meta">${voice.gender} · ${voice.desc}</span>
        <span class="v-engine">${voice.engine}</span>`;
      btn.addEventListener("click", () => {
        $$(".voice-opt", grid).forEach((node) => node.classList.remove("active"));
        btn.classList.add("active");
        releaseGlobal(voice, row);
      });
      grid.appendChild(btn);
    });
  };

  $$(".lang-tab", $("#langTabs")).forEach((tab) => {
    tab.addEventListener("click", () => {
      $$(".lang-tab", $("#langTabs")).forEach((node) => node.classList.remove("active"));
      tab.classList.add("active");
      currentLang = tab.dataset.lang;
      const saved = voicePref.get();
      currentVoice = saved.lang === currentLang ? saved.voice : null;
      if (textArea && tab.dataset.sample) textArea.value = tab.dataset.sample;
      renderVoices();
    });
  });

  styleSelect?.addEventListener("change", () => {
    voicePref.set({ style: styleSelect.value });
    toast("角色已更新", "全站播报立即生效", "ok");
  });

  renderVoices();

  $("#voicePlay")?.addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    const state = $("#voiceState");
    const text = (textArea?.value || "").trim();
    if (!text) return toast("文本为空", "请输入要试听的内容", "err");
    btn.disabled = true;
    btn.textContent = "合成中…";
    if (state) state.textContent = "正在调用 " + currentLang + " 音色…";
    try {
      const data = await api("/api/voice/tts", {
        method: "POST",
        body: {
          text,
          lang: currentLang,
          voice: currentVoice,
          speed: 1.0,
          style: styleSelect?.value || "natural",
        },
      });
      const audio = $("#voiceAudio");
      if (audio) { audio.src = data.audio; audio.load(); audio.play().catch(() => {}); }
      const meta = data.meta;
      if (state) {
        state.textContent = `${meta.voice_name} · ${meta.style_name || "自然"} · ${meta.duration}s`
          + (meta.fallback_reason ? ` · ${meta.fallback_reason}` : "");
      }
      toast("试听已生成", `${meta.voice_name} · ${meta.duration}s`, "ok");
    } catch (err) {
      if (state) state.textContent = "合成失败";
      toast("合成失败", err.message, "err");
    } finally {
      btn.disabled = false;
      btn.textContent = "合成并试听";
    }
  });
});

/* ---------------- 今日资讯页 ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("localNews");
  if (!page) return;

  $$(".play-news").forEach((btn) => btn.addEventListener("click", async () => {
    const text = btn.dataset.text || "";
    const lang = btn.dataset.lang || "zh-CN";
    const pref = voicePref.get();
    const state = $("#newsPlayState");
    btn.disabled = true;
    btn.textContent = "合成中…";
    try {
      const data = await api("/api/voice/tts", {
        method: "POST",
        body: {
          text,
          lang,
          voice: pref.lang === lang ? pref.voice : null,
          speed: 1.0,
          style: pref.style,
        },
      });
      const audio = $("#latestAudio");
      if (audio) { audio.src = data.audio; audio.load(); audio.play().catch(() => {}); }
      if (state) state.textContent = `${data.meta.voice_name} · ${data.meta.duration}s`;
      toast("资讯试听已生成", data.meta.voice_name, "ok");
    } catch (err) {
      if (state) state.textContent = "合成失败";
      toast("合成失败", err.message, "err");
    } finally {
      btn.disabled = false;
      btn.textContent = "播报";
    }
  }));

  $("#refreshNews")?.addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    const city = $("#newsCity")?.value;
    btn.disabled = true;
    btn.textContent = "刷新中…";
    try {
      await api(`/api/news?refresh=true${city ? `&city=${encodeURIComponent(city)}` : ""}`);
      location.reload();
    } catch (err) {
      toast("刷新失败", err.message, "err");
      btn.disabled = false;
      btn.textContent = "刷新资讯";
    }
  });

  $("#newsCity")?.addEventListener("change", (event) => {
    const city = event.target.value;
    window.citySync?.set(city);
    location.href = `/news?city=${encodeURIComponent(city)}`;
  });

  // 资讯页自动检查更新：服务端缓存刷新后（updated 变化）自动重载列表
  const stamp = $("#newsStamp");
  setInterval(async () => {
    if (document.visibilityState !== "visible" || !stamp) return;
    const city = window.citySync?.current || $("#newsCity")?.value || "";
    try {
      const data = await api(`/api/news${city ? `?city=${encodeURIComponent(city)}` : ""}`);
      if (data.updated && !stamp.textContent.includes(data.updated)) location.reload();
    } catch (err) { /* 静默失败，下一次轮询继续 */ }
  }, 120000);
});

/* ---------------- 今日待办页 ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("todoPage");
  if (!page) return;
  const form = $("#todoForm");
  const input = $("#todoText");
  const list = $("#todoList");
  const summary = $("#todoSummary");
  const ring = $("#todoRing");
  const empty = $("#todoEmpty");
  let filter = "all";

  const render = () => {
    const items = todoStore.load().items;
    const done = items.filter((item) => item.done).length;
    const active = items.length - done;
    const shown = items.filter((item) => (
      filter === "all" || (filter === "active" ? !item.done : item.done)
    ));

    list.innerHTML = "";
    shown.forEach((item) => {
      const row = document.createElement("div");
      row.className = "todo-item" + (item.done ? " is-done" : "");
      const check = document.createElement("button");
      check.type = "button";
      check.className = "todo-check";
      check.dataset.act = "toggle";
      check.dataset.id = item.id;
      check.setAttribute("aria-label", item.done ? "标记为未完成" : "标记为完成");
      check.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M5 12l5 5L19 7"/></svg>';
      const text = document.createElement("span");
      text.className = "todo-text";
      text.textContent = item.text;
      const del = document.createElement("button");
      del.type = "button";
      del.className = "todo-del";
      del.dataset.act = "remove";
      del.dataset.id = item.id;
      del.setAttribute("aria-label", "删除待办");
      del.textContent = "×";
      row.append(check, text, del);
      list.appendChild(row);
    });

    if (empty) empty.hidden = shown.length > 0;
    if (summary) {
      summary.textContent = items.length
        ? `完成 ${done} / ${items.length}${active ? ` · 还剩 ${active} 件` : " · 今天全部完成"}`
        : "今天还没有待办，先加一件吧";
    }
    if (ring) {
      const percent = items.length ? Math.round((done / items.length) * 100) : 0;
      ring.style.setProperty("--p", `${percent}%`);
      ring.dataset.percent = `${percent}%`;
      const label = $("#todoPercent");
      if (label) label.textContent = `${percent}%`;
    }
  };

  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = (input?.value || "").trim();
    if (!text) return;
    todoStore.add(text);
    input.value = "";
    input.focus();
    render();
    toast("已添加", "记得今天完成它", "ok");
  });

  list?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-act]");
    if (!btn) return;
    if (btn.dataset.act === "toggle") todoStore.toggle(btn.dataset.id);
    if (btn.dataset.act === "remove") todoStore.remove(btn.dataset.id);
    render();
  });

  $$(".todo-filter").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".todo-filter").forEach((node) => node.classList.remove("active"));
      btn.classList.add("active");
      filter = btn.dataset.filter;
      render();
    });
  });

  $("#todoClear")?.addEventListener("click", () => {
    todoStore.clearDone();
    render();
    toast("已清理", "完成的事项已移除", "ok");
  });

  window.addEventListener("todos:changed", render);
  render();
});

/* ---------------- 专注计时 ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("focusPage");
  if (!page) return;
  const clock = $("#focusClock");
  const ring = $("#focusRing");
  const hint = $("#focusHint");
  const startBtn = $("#focusStart");
  const FOCUS_KEY = "itinerary-focus";

  let total = 25 * 60;
  let remain = total;
  let running = false;
  let kind = "focus";
  let tickId = null;
  const today = todayKey();

  const loadStats = () => {
    try {
      const data = JSON.parse(localStorage.getItem(FOCUS_KEY) || "null");
      if (data && data.date === today) return data;
    } catch (e) { /* 忽略 */ }
    return { date: today, sessions: 0, minutes: 0 };
  };
  let stats = loadStats();

  const saveStats = () => {
    stats.date = today;
    try { localStorage.setItem(FOCUS_KEY, JSON.stringify(stats)); } catch (e) { /* 忽略 */ }
  };

  const paintStats = () => {
    const sessions = $("#focusSessions");
    const minutes = $("#focusMinutes");
    if (sessions) sessions.textContent = stats.sessions;
    if (minutes) minutes.textContent = stats.minutes;
  };

  const fmt = (seconds) => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  const paint = () => {
    if (clock) clock.textContent = fmt(remain);
    if (ring) ring.style.setProperty("--p", `${total ? ((total - remain) / total) * 100 : 0}%`);
  };

  const chime = () => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      [0, 0.38].forEach((offset) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = offset ? 660 : 880;
        osc.connect(gain);
        gain.connect(ctx.destination);
        gain.gain.setValueAtTime(0.0001, ctx.currentTime + offset);
        gain.gain.exponentialRampToValueAtTime(0.22, ctx.currentTime + offset + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + offset + 0.32);
        osc.start(ctx.currentTime + offset);
        osc.stop(ctx.currentTime + offset + 0.34);
      });
    } catch (e) { /* 无声音也不影响计时 */ }
  };

  const stop = () => {
    if (tickId) clearInterval(tickId);
    tickId = null;
    running = false;
  };

  const finish = () => {
    stop();
    remain = 0;
    paint();
    if (startBtn) startBtn.textContent = "再来一轮";
    chime();
    if (kind === "focus") {
      stats.sessions += 1;
      stats.minutes += Math.round(total / 60);
      saveStats();
      paintStats();
      if (hint) hint.textContent = "这一轮完成了，起身走走、喝口水。";
      toast("专注完成", `已完成 ${stats.sessions} 轮 · 累计 ${stats.minutes} 分钟`, "ok");
    } else {
      if (hint) hint.textContent = "休息结束，准备好就开始下一轮。";
      toast("休息结束", "回来继续吧", "ok");
    }
  };

  const start = () => {
    stop();
    if (remain <= 0) remain = total;
    running = true;
    if (startBtn) startBtn.textContent = "暂停";
    if (hint) hint.textContent = kind === "focus" ? "专注中，先不看手机。" : "休息中，放松一下。";
    tickId = setInterval(() => {
      remain -= 1;
      paint();
      if (remain <= 0) finish();
    }, 1000);
  };

  startBtn?.addEventListener("click", () => {
    if (running) {
      stop();
      if (startBtn) startBtn.textContent = "继续专注";
      if (hint) hint.textContent = "已暂停，准备好再继续。";
      return;
    }
    start();
  });

  $("#focusReset")?.addEventListener("click", () => {
    stop();
    remain = total;
    paint();
    paintStats();
    if (startBtn) startBtn.textContent = "开始专注";
    if (hint) hint.textContent = "重新计时，准备好了就开始。";
  });

  $$(".focus-mode").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".focus-mode").forEach((node) => node.classList.remove("active"));
      btn.classList.add("active");
      stop();
      kind = btn.dataset.kind;
      total = Number(btn.dataset.min) * 60;
      remain = total;
      paint();
      if (startBtn) startBtn.textContent = kind === "focus" ? "开始专注" : "开始休息";
      if (hint) hint.textContent = kind === "focus" ? "选一段时间，开始今天的专注。" : "休息一下，回来效率更高。";
    });
  });

  paint();
  paintStats();
});

/* ---------------- 城市同步：一个城市贯穿所有页面与标签页 ---------------- */
(function citySyncModule() {
  const KEY = "itinerary-city";
  const SYNC_PAGES = new Set(["/", "/stage", "/weather", "/news"]);
  const known = Array.isArray(window.__CITIES__) && window.__CITIES__.length ? window.__CITIES__ : null;
  const serverCity = window.__CITY__ || "";
  const urlCity = new URLSearchParams(location.search).get("city") || "";
  let stored = "";
  try { stored = localStorage.getItem(KEY) || ""; } catch (e) { stored = ""; }
  // 记忆里的城市已不在配置中（删过城市 / 手改过）就丢弃，避免死循环跳转
  if (known && stored && !known.includes(stored)) stored = "";

  const remember = (city) => { try { localStorage.setItem(KEY, city); } catch (e) { /* 隐私模式忽略 */ } };

  let current = urlCity || stored || serverCity || "";

  // 站内导航链接一律带上当前城市，换页后服务端渲染的天气 / 资讯才是同一个地区
  const decorate = () => {
    if (!current) return;
    $$('a[href^="/"]').forEach((a) => {
      if (a.target === "_blank") return;
      const url = new URL(a.getAttribute("href"), location.origin);
      if (url.origin !== location.origin || !SYNC_PAGES.has(url.pathname)) return;
      url.searchParams.set("city", current);
      a.setAttribute("href", url.pathname + url.search);
    });
  };

  // 其他标签页切了城市：整页跟随，天气 / 资讯 / 建议一起换
  const follow = (city) => {
    if (!city || city === current) return;
    remember(city);
    current = city;
    if (!SYNC_PAGES.has(location.pathname)) return;
    const next = new URL(location.href);
    next.searchParams.set("city", city);
    location.replace(next);
  };

  const channel = "BroadcastChannel" in window ? new BroadcastChannel("itinerary-city") : null;
  window.addEventListener("storage", (event) => { if (event.key === KEY && event.newValue) follow(event.newValue); });
  channel?.addEventListener("message", (event) => follow(event?.data?.city));

  // 打开页面时记忆城市与服务端渲染的不一致：先补上 URL 参数再重载一次
  if (!urlCity && stored && serverCity && stored !== serverCity && SYNC_PAGES.has(location.pathname)) {
    const next = new URL(location.href);
    next.searchParams.set("city", stored);
    location.replace(next);
    return;
  }
  if (current) remember(current);
  decorate();

  window.citySync = {
    key: KEY,
    get current() { return current; },
    set(city) {
      if (!city) return;
      const changed = city !== current;
      current = city;
      remember(city);
      decorate();
      if (changed) channel?.postMessage({ city });
    },
  };
})();
