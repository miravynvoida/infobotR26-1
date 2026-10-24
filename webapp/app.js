/* Дневник студента — основное приложение */
(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const $ = (s, r) => (r || document).querySelector(s);
  const appEl = $("#app");

  const state = {
    token: null, me: null, tab: "main",
    sch: { week: null, date: null, weeks: [], days: [] },
    overlays: [],
  };

  /* ---------- утилиты ---------- */
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }
  const WD = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];
  const WDS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];
  const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];

  function fmtDate(iso) { const d = new Date(iso + "T00:00:00"); return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" }); }
  function fmtDateShort(iso) { const d = new Date(iso + "T00:00:00"); return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }); }
  function todayISO() {
    return new Date().toLocaleDateString("sv-SE");
  }
  function fmtAvg(x) { return x == null ? "—" : (Math.round(x * 100) / 100).toFixed(2).replace(".", ",").replace(/,?0+$/, "").replace(/,$/, "") || "0"; }
  function fmtPub(ts) { return ts ? `${ts.slice(8, 10)}.${ts.slice(5, 7)}.${ts.slice(0, 4)} ${ts.slice(11, 16)}` : ""; }
  function stripHtml(s) { const d = document.createElement("div"); d.innerHTML = s == null ? "" : s; return d.textContent || ""; }

  function haptic(kind) {
    try { tg && tg.HapticFeedback && tg.HapticFeedback.impactOccurred(kind || "light"); } catch (e) {}
  }

  async function api(path, opts) {
    opts = opts || {};
    const conf = { method: opts.method || "GET", headers: {} };
    if (state.token) conf.headers.Authorization = "Bearer " + state.token;
    if (opts.body !== undefined) { conf.headers["Content-Type"] = "application/json"; conf.body = JSON.stringify(opts.body); }
    const r = await fetch("/api" + path, conf);
    if (r.status === 401) { renderBootError("Сессия истекла. Закройте и откройте приложение заново."); throw new Error("unauthorized"); }
    let data = null;
    try { data = await r.json(); } catch (e) {}
    if (!r.ok) {
      const msg = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : ("Ошибка " + r.status);
      throw new Error(msg);
    }
    return data;
  }

  function toast(msg, isErr) {
    const el = document.createElement("div");
    el.className = "toast" + (isErr ? " err" : "");
    el.textContent = msg;
    $("#toast-root").appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, 2400);
    setTimeout(() => el.remove(), 2800);
  }

  /* ---------- иконки (SVG, единые на всех платформах) ---------- */
  const I = {
    cap: '<svg width="26" height="26" viewBox="0 0 24 24" fill="none"><path d="M12 3 1.8 8.2 12 13.4l8.2-4.1v5.2h1.6V8.2L12 3Z" fill="currentColor"/><path d="M5.5 11.4v4.1c0 1.5 2.9 3 6.5 3s6.5-1.5 6.5-3v-4.1L12 14.7l-6.5-3.3Z" fill="currentColor" opacity=".55"/></svg>',
    sun: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.4" fill="currentColor" stroke="none"/><path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M5 5l1.7 1.7M17.3 17.3 19 19M19 5l-1.7 1.7M6.7 17.3 5 19"/></svg>',
    moon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M20.6 14.4A8.6 8.6 0 0 1 9.6 3.4a8.6 8.6 0 1 0 11 11Z"/></svg>',
    chev: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m9 5 7 7-7 7"/></svg>',
    back: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5 8 12l7 7"/></svg>',
    home: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3.5 10.5 12 3.5l8.5 7v8.5a1.5 1.5 0 0 1-1.5 1.5h-4v-6h-6v6H5a1.5 1.5 0 0 1-1.5-1.5v-8.5Z"/></svg>',
    cal: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 9.5h17M8 2.8v4M16 2.8v4"/></svg>',
    chart: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M5 20V9M12 20V4M19 20v-7"/></svg>',
    person: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="3.6"/><path d="M4.8 20c.9-3.4 3.8-5.2 7.2-5.2s6.3 1.8 7.2 5.2"/></svg>',
    book: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15.5H6.5A2.5 2.5 0 0 0 4 21V5.5Z"/><path d="M4 18.5A2.5 2.5 0 0 1 6.5 16H20"/></svg>',
    task: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 4h8a2 2 0 0 1 2 2v14l-6-3-6 3V6a2 2 0 0 1 2-2Z"/><path d="m9.5 9.5 2 2 3.5-3.5"/></svg>',
    search: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>',
    check: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    send: '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M3 11.5 21 3l-8.5 18-2.4-7.1L3 11.5Z"/></svg>',
    gear: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3.2"/><path d="M12 2.8v2.6M12 18.6v2.6M2.8 12h2.6M18.6 12h2.6M5.5 5.5l1.8 1.8M16.7 16.7l1.8 1.8M18.5 5.5l-1.8 1.8M7.3 16.7l-1.8 1.8"/></svg>',
    plus: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  };

  /* ---------- тема ---------- */
  function applyTheme(theme) {
    const t = theme === "light" ? "light" : "dark";
    document.documentElement.className = t;
    try { localStorage.setItem("theme", t); } catch (e) {}
    if (tg && tg.setHeaderColor) {
      try {
        tg.setHeaderColor(t === "dark" ? "#0a0d14" : "#f3f5fa");
        tg.setBackgroundColor(t === "dark" ? "#0a0d14" : "#f3f5fa");
      } catch (e) {}
    }
  }
  async function toggleTheme() {
    const cur = document.documentElement.className === "light" ? "light" : "dark";
    const next = cur === "dark" ? "light" : "dark";
    applyTheme(next);
    haptic("light");
    try { await api("/settings", { method: "POST", body: { theme: next } }); } catch (e) {}
    if (state.me) state.me.settings.theme = next;
    renderHeader();
  }

  /* ---------- шторки (кастомные, «стеклянные») ---------- */
  function sheetOpen(node, onMount) {
    const root = $("#overlays");
    const back = document.createElement("div");
    back.className = "sheet-back";
    const sheet = document.createElement("div");
    sheet.className = "sheet";
    sheet.appendChild(node);
    root.appendChild(back); root.appendChild(sheet);
    requestAnimationFrame(() => { back.classList.add("open"); sheet.classList.add("open"); });
    const close = () => {
      back.classList.remove("open"); sheet.classList.remove("open");
      setTimeout(() => { back.remove(); sheet.remove(); }, 260);
    };
    back.addEventListener("click", close);
    if (onMount) onMount(sheet, close);
    return close;
  }

  function sheetOptions(title, options, cb) {
    // options: [{label, value, on, sub}]
    const div = document.createElement("div");
    div.innerHTML = '<div class="sheet-handle"></div>' + (title ? '<div class="sheet-title"></div>' : "");
    if (title) div.querySelector(".sheet-title").textContent = title;
    options.forEach((o) => {
      const el = document.createElement("div");
      el.className = "sheet-opt" + (o.on ? " on" : "");
      el.innerHTML = `<span>${esc(o.label)}</span>${o.on ? `<span class="check">${I.check}</span>` : ""}`;
      el.addEventListener("click", () => { haptic("light"); cb(o.value); });
      div.appendChild(el);
    });
    let closed = false;
    const close = sheetOpen(div, (sheet, closeFn) => {
      div.querySelectorAll(".sheet-opt").forEach((el) => el.addEventListener("click", () => {
        if (!closed) { closed = true; setTimeout(closeFn, 120); }
      }));
    });
    return close;
  }

  function sheetCalendar(initialISO, hasDays, cb) {
    let cur = initialISO ? new Date(initialISO + "T00:00:00") : new Date();
    let sel = initialISO;
    const div = document.createElement("div");
    div.className = "cal";
    function draw() {
      const y = cur.getFullYear(), m = cur.getMonth();
      const first = new Date(y, m, 1);
      const startOffset = (first.getDay() + 6) % 7;
      const daysInMonth = new Date(y, m + 1, 0).getDate();
      const tISO = todayISO();
      let html = `<div class="sheet-handle"></div><div class="cal-head">
        <button class="cal-nav" data-nav="-1">‹</button>
        <div class="cal-title">${MONTHS[m]} ${y}</div>
        <button class="cal-nav" data-nav="1">›</button></div><div class="cal-grid">`;
      ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"].forEach((w) => html += `<div class="cal-wd">${w}</div>`);
      for (let i = 0; i < startOffset; i++) html += "<div></div>";
      for (let d = 1; d <= daysInMonth; d++) {
        const iso = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
        const cls = ["cal-day"];
        if (hasDays && hasDays.has(iso)) cls.push("has");
        if (iso === tISO) cls.push("today");
        if (iso === sel) cls.push("on");
        html += `<div class="${cls.join(" ")}" data-d="${iso}">${d}</div>`;
      }
      html += "</div>";
      div.innerHTML = html;
      div.querySelectorAll(".cal-nav").forEach((b) => b.addEventListener("click", () => {
        haptic("light");
        cur = new Date(y, m + parseInt(b.dataset.nav, 10), 1);
        draw();
      }));
      div.querySelectorAll(".cal-day[data-d]").forEach((b) => b.addEventListener("click", () => {
        haptic("light"); sel = b.dataset.d; draw();
        setTimeout(() => closeFn(), 160);
      }));
    }
    const closeFn = sheetOpen(div);
    draw();
    div.addEventListener("click", (e) => {
      const day = e.target.closest(".cal-day[data-d]");
      if (day) cb(day.dataset.d);
    });
    return closeFn;
  }

  /* ---------- каркас ---------- */
  function renderHeader() {
    const light = document.documentElement.className === "light";
    const h = $("#app-header");
    if (!h) return;
    h.innerHTML = `
      <div class="header-cap" style="color:var(--accent)">${I.cap}</div>
      <div class="header-titles">
        <div class="header-title">Дневник студента</div>
        <div class="header-sub">Учись легко · ${esc(state.me ? state.me.group : "Р 26-1")}</div>
      </div>
      <button class="icon-btn" id="theme-btn" title="Тема">${light ? I.sun : I.moon}</button>`;
    $("#theme-btn").addEventListener("click", toggleTheme);
  }

  function renderShell() {
    appEl.innerHTML = `
      <div class="header" id="app-header"></div>
      <main class="view" id="view"></main>
      <nav class="tabbar"><div class="tabbar-inner">
        <button class="tab" data-tab="main">${I.home}<span>Главное</span></button>
        <button class="tab" data-tab="schedule">${I.cal}<span>Расписание</span></button>
        <button class="tab" data-tab="grades">${I.chart}<span>Оценки</span></button>
        <button class="tab" data-tab="profile">${I.person}<span>Кабинет</span></button>
      </div></nav>`;
    renderHeader();
    document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  }

  function showTab(tab) {
    state.tab = tab;
    haptic("light");
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
    const v = $("#view");
    if (tab === "main") viewMain(v);
    else if (tab === "schedule") viewSchedule(v);
    else if (tab === "grades") viewGrades(v);
    else if (tab === "profile") viewProfile(v);
    window.scrollTo(0, 0);
  }

  function skeleton(n) {
    let h = "";
    for (let i = 0; i < (n || 3); i++) h += `<div class="sk" style="margin:10px 0;width:${60 + ((i * 13) % 35)}%"></div>`;
    return `<div class="card">${h}</div>`;
  }

  /* ---------- компоненты ---------- */
  // Цветной чип с первой буквой дисциплины — вместо эмодзи (эмодзи на разных ОС разные)
  function discChip(name) {
    return `<span class="lchip">${esc(String(name || "?").trim().charAt(0).toUpperCase())}</span>`;
  }

  function lessonCard(l) {
    const badges = [];
    if (l.type) badges.push(`<span class="badge ${l.type === "ЛЕК" ? "lek" : l.type === "ЛАБ" ? "lab" : ""}">${esc(l.type)}</span>`);
    if (l.status === "done") badges.push('<span class="st done">прошла</span>');
    if (l.status === "now") badges.push('<span class="st now">идёт сейчас</span>');
    if (l.status === "next") badges.push('<span class="st next">скоро</span>');
    const meta = [l.teacher, l.room ? "ауд. " + l.room : null].filter(Boolean).join(" • ");
    return `<div class="lesson">
      <div class="lesson-time"><div class="t1">${esc(l.start)}</div><div class="t2">${esc(l.end)}</div></div>
      <div class="lesson-body">
        <div class="lesson-disc">${discChip(l.discipline)}<span>${esc(l.discipline)}</span>${badges.join("")}</div>
        ${meta ? `<div class="lesson-meta">${esc(meta)}</div>` : ""}
      </div></div>`;
  }

  function lessonsBlock(lessons, emptyText) {
    if (!lessons || !lessons.length) return `<div class="empty">${esc(emptyText || "Пар нет")}</div>`;
    return lessons.map(lessonCard).join("");
  }

  function profileCard(me) {
    const letter = (me.fio || "?").trim().charAt(0).toUpperCase();
    return `<div class="card profile" id="profile-card" style="cursor:pointer">
      <div class="avatar">${esc(letter)}</div>
      <div style="min-width:0">
        <div class="profile-name">${esc(me.fio)}</div>
        <div class="profile-tags"><span class="tag">${esc(me.group)}</span><span class="tag ghost">${esc(me.specialty)}</span></div>
      </div>
      <span class="chevron">${I.chev}</span>
    </div>`;
  }

  /* ---------- Главная ---------- */
  async function viewMain(v) {
    v.innerHTML = skeleton(5);
    let today, hw, att, summ;
    try {
      [today, hw, att] = await Promise.all([
        api("/today"), api("/homework"),
        api("/attendance/today"),
      ]);
      if (state.me && state.me.is_staff) { try { summ = await api("/attendance/summary"); } catch (e) { summ = null; } }
    } catch (e) { v.innerHTML = `<div class="card"><div class="empty">${esc(e.message)}</div></div>`; return; }

    const hour = new Date().getHours();
    const hello = hour < 5 ? "Доброй ночи" : hour < 12 ? "Доброе утро" : hour < 18 ? "Добрый день" : "Добрый вечер";
    const firstName = (state.me.fio || "").trim().split(" ")[1] || (state.me.fio || "").trim();
    const newHw = hw.total_new || 0;

    let html = `
      <div class="section-head"><div>
        <div class="section-title">${hello}, ${esc(firstName)}!</div>
        <div class="section-sub">${today.weekday}, ${fmtDate(today.date)}${today.week_number ? " · учебная неделя " + today.week_number : ""}</div>
      </div></div>
      ${profileCard(state.me)}
      <div class="tiles tiles-2">
        <div class="tile wide" data-act="hw"><div class="tile-ico">${I.task}</div><div class="tile-body"><div class="tile-name">Домашнее задание</div><div class="tile-sub">${newHw ? newHw + " новых" : "всё просмотрено"}</div></div>${newHw ? `<div class="dot">${newHw}</div>` : ""}</div>
        <div class="tile wide" data-act="tb"><div class="tile-ico">${I.book}</div><div class="tile-body"><div class="tile-name">Учебники</div><div class="tile-sub">материалы дисциплин</div></div></div>
      </div>
      <div class="status-line" id="today-status">${today.status_text}</div>`;

    if (att.active && !att.response) {
      html += `<div class="att-card" id="att-card">
        <div class="att-q">Будете ли вы сегодня на парах?</div>
        <div class="att-sub">Первая пара в ${esc(att.first_start)}. Ответ увидят староста и зам. Отметиться можно до конца последней пары.</div>
        <div class="att-grid">
          <button class="btn sm" data-att="full">Буду на всех</button>
          <button class="btn sm" data-att="none">Не буду</button>
          <button class="btn sm" data-att="partial">Частично</button>
          <button class="btn sm" data-att="sick">Заболел</button>
        </div>
        <div id="att-extra" style="display:none;margin-top:10px"></div>
      </div>`;
    } else if (att.active && att.response) {
      const labels = { full: "Вы будете на всех парах", none: "Вас сегодня не будет", sick: "Вы болеете", partial: "Вы будете частично" };
      html += `<div class="att-card"><div class="att-q">${labels[att.response.status] || ""}</div></div>`;
    }

    if (summ) {
      html += staffSummaryCard(summ);
    }

    html += `<div class="card"><div class="card-title">Расписание на сегодня<span class="right">${today.lessons.length} пар</span></div>
      <div id="today-lessons">${lessonsBlock(today.lessons, "Сегодня пар нет")}</div></div>`;

    v.innerHTML = html;
    $("#profile-card").addEventListener("click", () => showTab("profile"));
    v.querySelectorAll(".tile").forEach((t) => t.addEventListener("click", () => {
      const act = t.dataset.act;
      if (act === "hw") openHomework();
      else if (act === "tb") openTextbooks();
      else if (act === "sch") showTab("schedule");
      else if (act === "gr") showTab("grades");
    }));
    v.querySelectorAll("[data-att]").forEach((b) => b.addEventListener("click", () => answerAttendance(b.dataset.att, att)));
    const sumBtn = $("#staff-refresh");
    if (sumBtn) sumBtn.addEventListener("click", async () => {
      try { const s = await api("/attendance/summary"); const card = $("#staff-card-body"); if (card) card.innerHTML = staffSummaryBody(s); toast("Обновлено"); } catch (e) { toast(e.message, true); }
    });
  }

  function staffSummaryBody(s) {
    const list = (arr) => arr && arr.length ? esc(arr.join(", ")) : "—";
    let part = "—";
    if (s.partial && s.partial.length) part = s.partial.map((p) => `${esc(p[0])} (без ${esc(String(p[1]))} пар)`).join(", ");
    return `
      <div class="drow"><div class="k">На всех парах</div><div class="v">${s.full_count} чел.</div></div>
      <div class="drow"><div class="k">Не будут</div><div class="v">${list(s.none)}</div></div>
      <div class="drow"><div class="k">Частично</div><div class="v">${part}</div></div>
      <div class="drow"><div class="k">Заболели</div><div class="v">${list(s.sick)}</div></div>
      <div class="drow"><div class="k">Не ответили</div><div class="v">${list(s.no_answer)}</div></div>`;
  }
  function staffSummaryCard(s) {
    return `<div class="card"><div class="card-title">Сводка посещаемости<button class="mini-btn" id="staff-refresh" style="margin-left:auto">Обновить</button></div>
      <div class="detail-rows" id="staff-card-body">${staffSummaryBody(s)}</div></div>`;
  }

  async function answerAttendance(kind, att) {
    haptic("medium");
    if (kind !== "partial") {
      try {
        await api("/attendance", { method: "POST", body: { status: kind } });
        toast("Ответ записан");
        showTab("main");
      } catch (e) { toast(e.message, true); }
      return;
    }
    const extra = $("#att-extra");
    extra.style.display = "block";
    extra.innerHTML = `<div class="att-sub" style="margin-top:8px">Отметьте пары, которые вы пропустите:</div>` +
      att.lessons.map((l) => `<button class="btn sm" style="text-align:left" data-pair="${l.pair_no}" data-sel="0">▫️ ${esc(l.pair_no)}. ${esc(l.start)} ${esc(l.discipline)}</button>`).join("") +
      `<button class="btn primary sm" id="att-ok">Подтвердить</button>`;
    extra.querySelectorAll("[data-pair]").forEach((b) => b.addEventListener("click", () => {
      const on = b.dataset.sel === "1";
      b.dataset.sel = on ? "0" : "1";
      b.textContent = (on ? "◦ " : "× ") + " " + b.textContent.slice(2).replace("× ", "").replace("◦ ", "");
      b.style.opacity = on ? "1" : ".7";
      haptic("light");
    }));
    $("#att-ok").addEventListener("click", async () => {
      const missing = [...extra.querySelectorAll("[data-pair][data-sel='1']")].map((b) => parseInt(b.dataset.pair, 10));
      try {
        await api("/attendance", { method: "POST", body: { status: "partial", missing_pairs: missing } });
        toast("Ответ записан");
        showTab("main");
      } catch (e) { toast(e.message, true); }
    });
  }

  /* ---------- Расписание ---------- */
  async function viewSchedule(v, keepState) {
    v.innerHTML = skeleton(4);
    let weeks;
    try { weeks = (await api("/schedule/weeks")).weeks; } catch (e) { v.innerHTML = `<div class="card"><div class="empty">${esc(e.message)}</div></div>`; return; }
    if (!keepState || !state.sch.week) {
      const tISO = todayISO();
      let cur = weeks.find((w) => w.start <= tISO && w.end >= tISO);
      if (!cur) cur = weeks.find((w) => w.start >= tISO) || weeks[weeks.length - 1] || null;
      state.sch.week = cur ? cur.n : null;
    }
    await loadWeek();
    await renderSchedule(v);
  }

  async function loadWeek() {
    if (!state.sch.week) { state.sch.days = []; return; }
    try {
      const data = await api("/schedule/week/" + state.sch.week);
      state.sch.days = data.days;
      state.sch.weeks = (await api("/schedule/weeks")).weeks;
      if (!state.sch.date) {
        const tISO = todayISO();
        const inWeek = state.sch.days.find((d) => d.date === tISO);
        state.sch.date = inWeek ? tISO : (state.sch.days.find((d) => d.lessons.length && d.date >= tISO) || state.sch.days.find((d) => d.lessons.length) || state.sch.days[0]).date;
      }
    } catch (e) { toast(e.message, true); state.sch.days = []; }
  }

  async function renderSchedule(v) {
    v = v || $("#view");
    const weeks = state.sch.weeks || [];
    const w = weeks.find((x) => x.n === state.sch.week);
    const days = state.sch.days;
    const tISO = todayISO();

    let chips = "";
    if (w) {
      chips = `<div class="chips">` + WDS.map((name, i) => {
        const d = days[i];
        if (!d) return "";
        const on = d.date === state.sch.date;
        const cls = ["chip", on ? "on" : "", d.lessons.length ? "has" : ""].join(" ");
        return `<div class="${cls}" data-d="${d.date}">${name}<span class="sub">${+d.date.slice(8)}</span></div>`;
      }).join("") + `</div>`;
    }
    const selDay = days.find((d) => d.date === state.sch.date);
    const isToday = state.sch.date === tISO;
    let lessons = selDay ? selDay.lessons : [];
    if (isToday) {
      try { const td = await api("/schedule/day/" + tISO); lessons = td.lessons; } catch (e) {}
    }

    v.innerHTML = `
      <div class="section-head"><div>
        <div class="section-title">Расписание</div>
      </div></div>
      <div class="sch-controls">
        <button class="select-btn" id="week-sel">${I.cal}<span>${w ? "Неделя " + w.n + " · " + fmtDateShort(w.start) + "–" + fmtDateShort(w.end) : "Выбрать неделю"}</span></button>
        <button class="select-btn sq" id="day-sel" title="Календарь">${I.cal}</button>
        <button class="select-btn sq" id="next-search" title="Следующая пара">${I.search}</button>
      </div>
      ${chips}
      <div class="card">
        <div class="card-title">${selDay ? WD[new Date(selDay.date + "T00:00:00").getDay() === 0 ? 6 : new Date(selDay.date + "T00:00:00").getDay() - 1] + ", " + fmtDate(selDay.date) : ""}
          <span class="right">${isToday ? "сегодня" : ""}</span></div>
        ${lessonsBlock(lessons, "На этот день расписания нет")}
      </div>`;

    $("#week-sel").addEventListener("click", () => {
      sheetOptions("Учебная неделя", weeks.map((x) => ({
        label: "Неделя " + x.n + " · " + fmtDateShort(x.start) + " – " + fmtDateShort(x.end),
        value: x.n, on: x.n === state.sch.week,
      })), async (n) => {
        state.sch.week = n; state.sch.date = null;
        await loadWeek(); renderSchedule();
      });
    });
    $("#day-sel").addEventListener("click", () => {
      const has = new Set();
      days.forEach((d) => { if (d.lessons.length) has.add(d.date); });
      sheetCalendar(state.sch.date || tISO, has, (iso) => { state.sch.date = iso; renderSchedule(); });
    });
    $("#next-search").addEventListener("click", openNextSearch);
    v.querySelectorAll(".chip[data-d]").forEach((c) => c.addEventListener("click", () => {
      state.sch.date = c.dataset.d; haptic("light"); renderSchedule();
    }));
  }

  async function openNextSearch() {
    // все дисциплины есть в /api/grades — используем как справочник
    let all;
    try { all = await api("/grades"); } catch (e) { toast(e.message, true); return; }
    const list = all.disciplines.map((d) => ({ label: d.name, value: d.id }));
    sheetOptions("Все будущие пары по дисциплине", list, async (id) => {
      try {
        const r = await api(`/schedule/next/${id}?all=1`);
        showLessonsModal(r.discipline, r.lessons || []);
      } catch (e) { toast(e.message, true); }
    });
  }

  function showLessonsModal(discipline, lessons) {
    const root = $("#overlays");
    const back = document.createElement("div");
    back.className = "sheet-back";
    const modal = document.createElement("div");
    modal.className = "modal";
    const items = lessons.length
      ? lessons.map((x) => `
          <div class="modal-row">
            <div class="modal-date">${esc(x.weekday)}, ${fmtDate(x.date)}</div>
            ${lessonCard(x.lesson)}
          </div>`).join("")
      : `<div class="empty">Будущих пар по «${esc(discipline)}» не найдено</div>`;
    modal.innerHTML = `
      <div class="modal-head">
        <div class="modal-title">${discChip(discipline)}<span>${esc(discipline)}</span></div>
        <button class="icon-btn" data-close>✕</button>
      </div>
      <div class="modal-body">${items}</div>`;
    root.appendChild(back); root.appendChild(modal);
    requestAnimationFrame(() => { back.classList.add("open"); modal.classList.add("open"); });
    const close = () => {
      back.classList.remove("open"); modal.classList.remove("open");
      setTimeout(() => { back.remove(); modal.remove(); }, 220);
    };
    back.addEventListener("click", close);
    modal.querySelector("[data-close]").addEventListener("click", close);
  }

  /* ---------- Оценки ---------- */
  async function viewGrades(v) {
    v.innerHTML = skeleton(4);
    let g;
    try { g = await api("/grades"); } catch (e) { v.innerHTML = `<div class="card"><div class="empty">${esc(e.message)}</div></div>`; return; }
    const pct = g.avg == null ? 0 : Math.min(1, g.avg / 5);
    const C = 2 * Math.PI * 36;
    v.innerHTML = `
      <div class="section-head"><div>
        <div class="section-title">Оценки</div>
        <div class="section-sub">Средний балл и отметки по дисциплинам</div>
      </div></div>
      <div class="stat-grid">
        <div class="stat-card"><div class="donut-wrap">
          <div class="donut"><svg width="84" height="84">
            <circle cx="42" cy="42" r="36" stroke="var(--card-2)" stroke-width="6" fill="none"/>
            <circle cx="42" cy="42" r="36" stroke="var(--accent)" stroke-width="6" fill="none"
              stroke-linecap="round" stroke-dasharray="${(C * pct).toFixed(1)} ${C.toFixed(1)}"/>
          </svg><div class="donut-center"><b>${fmtAvg(g.avg)}</b><span>из 5</span></div></div>
          <div><div class="stat-num" style="font-size:19px">${g.total}</div><div class="stat-label">оценок всего</div></div>
        </div></div>
        <div class="stat-card hbo">
          <div class="hbo-cell"><div class="stat-num">${g.counts.h}</div><div class="stat-label">Н — пропуски</div></div>
          <div class="hbo-cell"><div class="stat-num">${g.counts.b}</div><div class="stat-label">Б — болезни</div></div>
          <div class="hbo-cell"><div class="stat-num">${g.counts.o}</div><div class="stat-label">О — опоздания</div></div>
        </div>
      </div>
      <div class="card"><div class="card-title">Все дисциплины</div>
        ${g.disciplines.map((d) => `
          <div class="disc-row" data-disc="${d.id}">
            <div class="disc-head">
              ${discChip(d.name)}
              <div class="disc-name">${esc(d.name)}</div>
              <div class="disc-avg">${fmtAvg(d.avg)}</div>
              <span class="chevron">${I.chev}</span>
            </div>
            <div class="disc-grades">${d.grades.length ? d.grades.map((x) => gradePill(x)).join("") : '<span class="muted" style="font-size:12.5px">Оценок пока нет</span>'}</div>
          </div>`).join("")}
      </div>`;
    v.querySelectorAll(".disc-head").forEach((h) => h.addEventListener("click", () => {
      h.parentElement.classList.toggle("open"); haptic("light");
    }));
  }

  function gradePill(x) {
    const v = x.value;
    let cls = "";
    if (["5", "4", "3", "2"].includes(v)) cls = "g" + v;
    else if (v === "Н") cls = "gn";
    const label = v === "Зачет" ? "зач" : v === "Незачет" ? "незач" : v;
    return `<div class="grade-pill ${cls}">${esc(label)}<i>${x.date ? fmtDateShort(x.date) : ""}</i></div>`;
  }

  /* ---------- Кабинет ---------- */
  async function viewProfile(v) {
    try { state.me = await api("/me"); } catch (e) {}
    const me = state.me, s = me.settings;
    const light = document.documentElement.className === "light";
    v.innerHTML = `
      <div class="section-head"><div>
        <div class="section-title">Личный кабинет</div>
        <div class="section-sub">Профиль, уведомления и оформление</div>
      </div></div>
      ${profileCard(me)}
      <div class="card"><div class="card-title">Успеваемость</div>
        <div class="drow"><div class="k">Средний балл</div><div class="v"><b>${fmtAvg(me.stats.avg)}</b> (${me.stats.total} оценок)</div></div>
        <div class="drow"><div class="k">Пропуски (Н)</div><div class="v"><b>${me.stats.h}</b></div></div>
        <div class="drow"><div class="k">Болезни (Б)</div><div class="v"><b>${me.stats.b}</b></div></div>
        <div class="drow"><div class="k">Опоздания (О)</div><div class="v"><b>${me.stats.o}</b></div></div>
      </div>
      <div class="card"><div class="card-title">Уведомления</div>
        <div class="set-row">
          <div><div class="set-name">О следующей паре</div><div class="set-sub">Перед каждой парой</div></div>
          <div class="set-ctrl">
            <select class="mini-select" id="np-min">${[5, 10, 15, 30, 45, 60, 90].map((m) => `<option value="${m}" ${s.next_pair_min === m ? "selected" : ""}>${m} мин</option>`).join("")}</select>
            <div class="switch ${s.next_pair ? "on" : ""}" id="np-sw"></div>
          </div>
        </div>
        <div class="set-row">
          <div><div class="set-name">Расписание на завтра</div><div class="set-sub">Вечером накануне</div></div>
          <div class="set-ctrl">
            <select class="mini-select" id="tm-time">${["17:00", "18:00", "19:00", "20:00", "21:00", "22:00"].map((t) => `<option ${s.tomorrow_time === t ? "selected" : ""}>${t}</option>`).join("")}</select>
            <div class="switch ${s.tomorrow ? "on" : ""}" id="tm-sw"></div>
          </div>
        </div>
        <div class="set-row">
          <div><div class="set-name">Прочие уведомления</div><div class="set-sub">Обновления и мелочи</div></div>
          <div class="set-ctrl"><div class="switch ${s.misc ? "on" : ""}" id="ms-sw"></div></div>
        </div>
        <div class="set-row">
          <div><div class="set-name">Важные и новые ДЗ</div><div class="set-sub">Посещаемость тоже</div></div>
          <div class="set-ctrl"><span class="locked">всегда включено</span></div>
        </div>
      </div>
      <div class="card"><div class="card-title">Тема</div>
        <div class="seg" id="theme-seg">
          <button data-t="dark" class="${light ? "" : "on"}">Тёмная</button>
          <button data-t="light" class="${light ? "on" : ""}">Светлая</button>
        </div>
      </div>
      ${me.is_admin ? `
      <div class="card"><div class="card-title">Админ-панель</div>
        <div class="tiles" style="grid-template-columns:repeat(3,1fr)">
          ${[["stats", "Статистика"], ["hw", "ДЗ"], ["schedule", "Расписание"], ["students", "Студенты"], ["disc", "Дисциплины"], ["tb", "Учебники"], ["bc", "Рассылка"]].map((x) =>
            `<div class="tile" data-adm="${x[0]}"><div class="tile-name">${x[1]}</div></div>`).join("")}
        </div>
      </div>` : (me.is_staff ? `
      <div class="card"><div class="card-title">Сводка посещаемости</div>
        <button class="btn" id="staff-sum-btn">Показать сводку за сегодня</button>
        <div id="staff-sum-body" class="mt8"></div>
      </div>` : "")}`;

    $("#profile-card").addEventListener("click", () => {});
    const setSave = (body) => api("/settings", { method: "POST", body }).catch((e) => toast(e.message, true));
    $("#np-sw").addEventListener("click", async (e) => {
      const on = !e.currentTarget.classList.contains("on");
      e.currentTarget.classList.toggle("on", on); haptic("medium");
      me.settings.next_pair = on; await setSave({ next_pair: on });
    });
    $("#np-min").addEventListener("change", async (e) => { me.settings.next_pair_min = +e.target.value; await setSave({ next_pair_min: +e.target.value, next_pair: true }); });
    $("#tm-sw").addEventListener("click", async (e) => {
      const on = !e.currentTarget.classList.contains("on");
      e.currentTarget.classList.toggle("on", on); haptic("medium");
      me.settings.tomorrow = on; await setSave({ tomorrow: on });
    });
    $("#tm-time").addEventListener("change", async (e) => { me.settings.tomorrow_time = e.target.value; await setSave({ tomorrow_time: e.target.value, tomorrow: true }); });
    $("#ms-sw").addEventListener("click", async (e) => {
      const on = !e.currentTarget.classList.contains("on");
      e.currentTarget.classList.toggle("on", on); haptic("medium");
      me.settings.misc = on; await setSave({ misc: on });
    });
    document.querySelectorAll("#theme-seg button").forEach((b) => b.addEventListener("click", async () => {
      applyTheme(b.dataset.t); me.settings.theme = b.dataset.t;
      document.querySelectorAll("#theme-seg button").forEach((x) => x.classList.toggle("on", x === b));
      renderHeader(); await setSave({ theme: b.dataset.t });
    }));
    v.querySelectorAll("[data-adm]").forEach((t) => t.addEventListener("click", () => {
      if (window.AdminUI) window.AdminUI.open(t.dataset.adm);
    }));
    const sbtn = $("#staff-sum-btn");
    if (sbtn) sbtn.addEventListener("click", async () => {
      try { const s = await api("/attendance/summary"); $("#staff-sum-body").innerHTML = `<div class="detail-rows">${staffSummaryBody(s)}</div>`; }
      catch (e) { toast(e.message, true); }
    });
  }

  /* ---------- Оверлеи (ДЗ / учебники) ---------- */
  const backBtn = tg && tg.BackButton ? tg.BackButton : null;

  function openOverlay(title, renderBody) {
    const ov = document.createElement("div");
    ov.className = "overlay";
    ov.innerHTML = `
      <div class="overlay-header">
        <button class="icon-btn ov-back">${I.back}</button>
        <div class="overlay-title">${esc(title)}</div>
      </div>
      <div class="overlay-body">${skeleton(4)}</div>`;
    $("#overlays").appendChild(ov);
    state.overlays.push(ov);
    const close = () => {
      const i = state.overlays.indexOf(ov);
      if (i >= 0) state.overlays.splice(i, 1);
      ov.remove(); syncBack();
    };
    ov.querySelector(".ov-back").addEventListener("click", close);
    syncBack();
    renderBody(ov.querySelector(".overlay-body"), close, ov);
    return close;
  }
  function syncBack() {
    if (!backBtn) return;
    if (state.overlays.length) { backBtn.show(); backBtn.onClick(() => { const top = state.overlays[state.overlays.length - 1]; if (top) top.querySelector(".ov-back").click(); }); }
    else backBtn.hide();
  }

  async function openHomework() {
    openOverlay("Домашнее задание", async (body) => {
      let hw;
      try { hw = await api("/homework"); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
      if (!hw.groups.length) { body.innerHTML = `<div class="empty">📭 Актуальных заданий нет</div>`; return; }
      body.innerHTML = `<div class="muted" style="font-size:12.5px;margin:0 2px 10px">Актуальные задания по дисциплинам. Пометка «новое» — непросмотренное, галочка — выполнено.</div>` +
        hw.groups.map((g) => `
          <div class="hw-group">
            <div class="hw-group-head">${discChip(g.discipline.name)}<span>${esc(g.discipline.name)}</span></div>
            ${g.items.map((h) => hwItemHtml(h)).join("")}
          </div>`).join("");
      body.querySelectorAll(".hw-item[data-id]").forEach((el) => el.addEventListener("click", () => openHwDetail(parseInt(el.dataset.id, 10), body)));
    });
  }

  function hwItemHtml(h) {
    return `<div class="hw-item ${h.done ? "done" : ""}" data-id="${h.id}">
      ${h.done ? `<span class="check">${I.check}</span>` : ""}
      <div class="hw-item-title">${esc(h.title)}</div>
      <div class="hw-item-meta">
        ${h.due_date ? `<span>до ${fmtDateShort(h.due_date)}</span>` : ""}
        ${h.has_files ? `<span>${h.files.length} файл(ов)</span>` : ""}
      </div>
      ${h.new ? `<span class="newdot">новое</span>` : ""}
    </div>`;
  }

  async function openHwDetail(hid, body) {
    body.innerHTML = skeleton(4);
    let h;
    try { h = await api("/homework/" + hid); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    haptic("light");
    body.innerHTML = `
      <div class="detail-page">
        <div class="muted" style="font-size:12.5px">${esc(h.discipline.name)}</div>
        <div class="detail-title">${esc(h.title)}</div>
        <div class="detail-rows">
          ${h.due_date ? `<div class="drow"><div class="k">Сдать до</div><div class="v">${fmtDate(h.due_date)}${h.due_type ? ", к паре (" + esc(h.due_type) + ")" : ""}</div></div>` : ""}
          ${h.published_at ? `<div class="drow"><div class="k">Публикация</div><div class="v">${esc(fmtPub(h.published_at))}</div></div>` : ""}
          <div class="drow"><div class="k">Задание</div><div class="v">${esc(h.task || "—")}</div></div>
          ${h.explanation ? `<div class="drow"><div class="k">Пояснение</div><div class="v">${esc(h.explanation)}</div></div>` : ""}
        </div>
        ${h.has_files ? `
          <div class="card-title mt14">Материалы</div>
          <div class="file-chips">${h.files.map((f) => `<div class="file-chip">${esc(f.name || f.type)}</div>`).join("")}</div>
          <button class="btn primary" id="hw-send">${I.send} Прислать все материалы в Telegram</button>` : ""}
        <button class="btn ${h.done ? "" : "primary"}" id="hw-done">${h.done ? "Вернуть в работу" : "Отметить выполненным"}</button>
        <button class="btn ghost ov-sub-back">◀ К списку заданий</button>
      </div>`;
    body.querySelector(".ov-sub-back").addEventListener("click", () => openHomeworkListBack(body));
    const sendBtn = $("#hw-send");
    if (sendBtn) sendBtn.addEventListener("click", async () => {
      sendBtn.disabled = true; sendBtn.textContent = "Отправляю…";
      try { const r = await api(`/homework/${hid}/send`, { method: "POST", body: {} }); toast(`Отправлено материалов: ${r.sent}/${r.total}`); }
      catch (e) { toast(e.message, true); sendBtn.disabled = false; sendBtn.innerHTML = I.send + " Прислать все материалы в Telegram"; }
    });
    $("#hw-done").addEventListener("click", async () => {
      try {
        const r = await api(`/homework/${hid}/done`, { method: "POST", body: { done: !h.done } });
        toast(r.done ? "Выполнено" : "Возвращено");
        openHomeworkListBack(body);
      } catch (e) { toast(e.message, true); }
    });
  }
  function openHomeworkListBack(body) { const ov = body.closest(".overlay"); if (ov) { const t = ov.querySelector(".overlay-title").textContent; openOverlayRefresh(ov, t); } }
  function openOverlayRefresh(ov, title) {
    const body = ov.querySelector(".overlay-body");
    body.innerHTML = skeleton(4);
    if (title === "Домашнее задание") {
      (async () => {
        let hw; try { hw = await api("/homework"); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
        if (!hw.groups.length) { body.innerHTML = `<div class="empty">📭 Актуальных заданий нет</div>`; return; }
        body.innerHTML = hw.groups.map((g) => `
          <div class="hw-group"><div class="hw-group-head">${discChip(g.discipline.name)}<span>${esc(g.discipline.name)}</span></div>
          ${g.items.map((h) => hwItemHtml(h)).join("")}</div>`).join("");
        body.querySelectorAll(".hw-item[data-id]").forEach((el) => el.addEventListener("click", () => openHwDetail(parseInt(el.dataset.id, 10), body)));
      })();
    } else if (title === "Учебники") {
      renderTextbooksBody(body);
    }
  }

  function openTextbooks() {
    openOverlay("Учебники", (body) => renderTextbooksBody(body));
  }
  async function renderTextbooksBody(body) {
    let tbs;
    try { tbs = await api("/textbooks"); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    if (!tbs.groups.length) { body.innerHTML = `<div class="empty">📭 Учебников пока нет</div>`; return; }
    body.innerHTML = tbs.groups.map((g) => `
      <div class="hw-group"><div class="hw-group-head">${discChip(g.discipline.name)}<span>${esc(g.discipline.name)}</span></div>
      ${g.items.map((t) => `
        <div class="hw-item" data-tb="${t.id}">
          <div class="hw-item-title">${esc(t.title)}</div>
          <div class="hw-item-meta">${t.files.length ? `<span>${t.files.length} файл(ов)</span>` : ""}${t.description ? `<span>${esc(t.description.slice(0, 60))}</span>` : ""}</div>
        </div>`).join("")}</div>`).join("");
    body.querySelectorAll("[data-tb]").forEach((el) => el.addEventListener("click", async () => {
      const id = parseInt(el.dataset.tb, 10);
      const g = tbs.groups.find((x) => x.items.some((i) => i.id === id));
      const t = g.items.find((i) => i.id === id);
      body.innerHTML = `
        <div class="detail-page">
          <div class="muted" style="font-size:12.5px">${esc(g.discipline.name)}</div>
          <div class="detail-title">${esc(t.title)}</div>
          ${t.description ? `<div class="detail-rows"><div class="drow"><div class="k">Описание</div><div class="v">${esc(t.description)}</div></div></div>` : ""}
          ${t.files.length ? `
            <div class="card-title mt14">Материалы</div>
            <div class="file-chips">${t.files.map((f) => `<div class="file-chip">${esc(f.name || f.type)}</div>`).join("")}</div>
            <button class="btn primary" id="tb-send">${I.send} Прислать материалы в Telegram</button>` : `<div class="empty">Файлов нет</div>`}
          <button class="btn ghost" id="tb-back">◀ К списку</button>
        </div>`;
      $("#tb-back").addEventListener("click", () => renderTextbooksBody(body));
      const sb = $("#tb-send");
      if (sb) sb.addEventListener("click", async () => {
        sb.disabled = true; sb.textContent = "Отправляю…";
        try { const r = await api(`/textbooks/${id}/send`, { method: "POST", body: {} }); toast(`Отправлено: ${r.sent}/${r.total}`); }
        catch (e) { toast(e.message, true); sb.disabled = false; }
      });
    }));
  }

  /* ---------- Загрузка ---------- */
  function renderBootError(msg) {
    appEl.innerHTML = `<div class="boot"><div class="boot-logo">🎓</div><div class="boot-title">Дневник студента</div><div class="boot-err">${esc(msg)}</div></div>`;
  }

  async function boot() {
    let cached = "dark";
    try { cached = localStorage.getItem("theme") || "dark"; } catch (e) {}
    applyTheme(cached);
    if (tg) { try { tg.ready(); tg.expand(); } catch (e) {} }
    try {
      const initData = tg && tg.initData ? tg.initData : "";
      const auth = await api("/auth", { method: "POST", body: { init_data: initData } });
      state.token = auth.token;
      state.me = await api("/me");
      applyTheme(state.me.settings.theme || cached);
      renderShell();
      showTab("main");
    } catch (e) {
      renderBootError(e.message || "Не удалось войти. Откройте приложение из бота.");
    }
  }

  /* экспорт для admin.js */
  window.App = {
    api, esc, toast, sheetOpen, sheetOptions, sheetCalendar, haptic,
    openOverlay, skeleton, lessonCard, lessonsBlock, fmtDate, fmtDateShort, fmtAvg,
    state, icons: I, WD, WDS, MONTHS, todayISO,
  };

  boot();
})();
