/* Админ-панель мини-приложения */
(function () {
  "use strict";
  const A = window.App;
  if (!A) return;
  const { api, esc, toast, sheetOptions, sheetCalendar, openOverlay, haptic, icons: I, fmtDate, fmtDateShort, todayISO } = A;

  const screens = {
    stats: { title: "📊 Обзор и статистика", render: renderStats },
    hw: { title: "📚 Управление ДЗ", render: renderHw },
    schedule: { title: "📅 Управление расписанием", render: renderScheduleAdmin },
    students: { title: "👥 Студенты", render: renderStudents },
    disc: { title: "📐 Дисциплины", render: renderDisc },
    tb: { title: "📖 Учебники", render: renderTbAdmin },
    bc: { title: "📣 Уведомление всем", render: renderBroadcast },
  };

  function open(name) {
    const s = screens[name];
    if (!s) return;
    haptic("light");
    openOverlay(s.title, (body, close) => s.render(body, close));
  }
  window.AdminUI = { open };

  /* ================= статистика ================= */
  async function renderStats(body) {
    body.innerHTML = A.skeleton(5);
    let st;
    try { st = await api("/admin/stats"); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const sync = st.last_grades_sync ? `${st.last_grades_sync.slice(8, 10)}.${st.last_grades_sync.slice(5, 7)} ${st.last_grades_sync.slice(11, 16)}` : "ещё не было";
    body.innerHTML = `
      <div class="card"><div class="card-title">Показатели</div>
        <div class="drow"><div class="k">👥 Студенты</div><div class="v"><b>${st.students_auth}</b> / ${st.students_total} авторизовано</div></div>
        <div class="drow"><div class="k">📐 Дисциплины</div><div class="v"><b>${st.disciplines}</b></div></div>
        <div class="drow"><div class="k">📅 Дни расписания</div><div class="v"><b>${st.schedule_days}</b></div></div>
        <div class="drow"><div class="k">📚 ДЗ</div><div class="v"><b>${st.hw_active}</b> активных · ${st.hw_archived} в архиве</div></div>
        <div class="drow"><div class="k">📖 Учебники</div><div class="v"><b>${st.textbooks}</b></div></div>
        <div class="drow"><div class="k">📋 Сегодня ответили</div><div class="v"><b>${st.attendance_today.answered}</b> / ${st.attendance_today.total}</div></div>
      </div>
      <div class="card"><div class="card-title">🔁 Оценки (Google Таблица)</div>
        <div class="muted" style="font-size:12.5px;margin-bottom:8px">Последняя синхронизация: ${esc(sync)}</div>
        <button class="btn primary" id="sync-btn">🔄 Синхронизировать оценки</button>
      </div>`;
    $("#sync-btn", body).addEventListener("click", async (e) => {
      const b = e.currentTarget; b.disabled = true; b.textContent = "⏳ Синхронизирую…";
      try {
        const r = await api("/admin/grades/sync", { method: "POST", body: {} });
        if (r.ok) toast(`Синхронизировано: ${r.marks} отметок из ${r.sheets} листов`);
        else toast(r.error || "Ошибка", true);
        renderStats(body);
      } catch (err) { toast(err.message, true); b.disabled = false; b.textContent = "🔄 Синхронизировать оценки"; }
    });
  }
  function $(sel, root) { return (root || document).querySelector(sel); }

  /* ================= ДЗ ================= */
  async function renderHw(body) {
    body.innerHTML = `
      <div class="btn-row"><button class="btn primary" id="hw-tab-active">Активные</button><button class="btn" id="hw-tab-arc">Архив</button></div>
      <button class="btn" id="hw-new">➕ Новое ДЗ</button>
      <div id="hw-list" class="mt8">${A.skeleton(4)}</div>`;
    let archived = 0;
    const load = async () => {
      const box = $("#hw-list", body);
      try {
        const data = await api("/admin/homework?archived=" + archived);
        if (!data.groups.length) { box.innerHTML = `<div class="empty">${archived ? "Архив пуст" : "Активных ДЗ нет"}</div>`; return; }
        box.innerHTML = data.groups.map((g) => `
          <div class="hw-group"><div class="hw-group-head"><span>${esc(g.discipline.emoji || "📚")}</span> ${esc(g.discipline.name)}</div>
          ${g.items.map((h) => `
            <div class="hw-item" data-hid="${h.id}">
              <div class="hw-item-title">${esc(h.title)}</div>
              <div class="hw-item-meta"><span>${h.due_date ? "📅 " + fmtDateShort(h.due_date) : "— без срока"}</span><span>📎 ${h.files.length}</span></div>
            </div>`).join("")}</div>`).join("");
        box.querySelectorAll("[data-hid]").forEach((el) => el.addEventListener("click", () => {
          const id = parseInt(el.dataset.hid, 10);
          const h = data.groups.flatMap((g) => g.items).find((x) => x.id === id);
          renderHwEdit(body, h, load);
        }));
      } catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
    };
    $("#hw-tab-active", body).addEventListener("click", () => { archived = 0; load(); });
    $("#hw-tab-arc", body).addEventListener("click", () => { archived = 1; load(); });
    $("#hw-new", body).addEventListener("click", () => renderHwForm(body, load));
    await load();
  }

  async function renderHwEdit(body, h, reload) {
    body.innerHTML = A.skeleton(3);
    body.innerHTML = `
      <div class="detail-page">
        <div class="muted" style="font-size:12.5px">${esc(h.title)} · ${h.due_date ? "до " + fmtDate(h.due_date) : "без срока"}</div>
        <div class="detail-rows">
          <div class="drow"><div class="k">📝 Задание</div><div class="v">${esc(h.task)}</div></div>
          ${h.explanation ? `<div class="drow"><div class="k">💡 Пояснение</div><div class="v">${esc(h.explanation)}</div></div>` : ""}
          <div class="drow"><div class="k">📎 Файлы</div><div class="v">${h.files.length ? h.files.map((f) => esc(f.name || f.type)).join(", ") : "—"}</div></div>
        </div>
        <button class="btn primary" id="he-edit">✏️ Редактировать</button>
        ${h.archived
          ? `<button class="btn" id="he-arc">♻️ Восстановить из архива</button>`
          : `<button class="btn" id="he-arc">📦 В архив</button>`}
        <button class="btn danger" id="he-del">🗑 Удалить</button>
        <button class="btn ghost" id="he-back">◀ Назад</button>
      </div>`;
    $("#he-back", body).addEventListener("click", reload);
    $("#he-arc", body).addEventListener("click", async () => {
      try { await api(`/admin/homework/${h.id}`, { method: "PATCH", body: { archived: !h.archived } }); toast(h.archived ? "Восстановлено" : "В архиве"); reload(); }
      catch (e) { toast(e.message, true); }
    });
    $("#he-del", body).addEventListener("click", async () => {
      if (!confirm("Удалить задание полностью?")) return;
      try { await api(`/admin/homework/${h.id}`, { method: "DELETE" }); toast("Удалено"); reload(); }
      catch (e) { toast(e.message, true); }
    });
    $("#he-edit", body).addEventListener("click", () => renderHwForm(body, reload, h));
  }

  async function renderHwForm(body, reload, editing) {
    let discs;
    try { discs = await api("/admin/disciplines"); } catch (e) { toast(e.message, true); return; }
    const f = {
      discipline_id: editing ? editing.discipline_id : null,
      title: editing ? editing.title : "",
      task: editing ? editing.task : "",
      due_date: editing ? editing.due_date : null,
      due_type: editing ? editing.due_type : null,
      explanation: editing ? editing.explanation : "",
      files: editing ? JSON.parse(JSON.stringify(editing.files)) : [],
    };
    let dueOptions = [];

    function draw() {
      const disc = discs.find((d) => d.id === f.discipline_id);
      body.innerHTML = `
        <div class="detail-page">
          <div class="muted" style="font-size:12.5px">${editing ? "Редактирование ДЗ" : "Новое ДЗ"}</div>
          <div class="field mt8"><label>Дисциплина</label><button class="btn" id="f-disc" style="margin:0">${disc ? esc(disc.emoji + " " + disc.name) : "Выбрать дисциплину"}</button></div>
          <div class="field"><label>Название</label><input class="input" id="f-title" value="${esc(f.title)}" placeholder="Прочитать текст"></div>
          <div class="field"><label>Задание</label><textarea class="input" id="f-task" placeholder="Что нужно сделать">${esc(f.task)}</textarea></div>
          <div class="field"><label>Сдать до</label>
            <div class="btn-row" style="margin:0">
              <button class="btn" id="f-due" style="margin:0">${f.due_date ? "📅 " + fmtDate(f.due_date) + (f.due_type ? " (" + esc(f.due_type) + ")" : "") : "Выбрать срок"}</button>
              ${f.due_date ? `<button class="btn danger" id="f-due-x" style="margin:0;flex:none;width:48px">✕</button>` : ""}
            </div>
          </div>
          <div class="field"><label>Пояснение</label><input class="input" id="f-expl" value="${esc(f.explanation || "")}" placeholder="необязательно"></div>
          <div class="field"><label>Файлы (отправятся студентам)</label>
            <div class="file-chips" id="f-chips"></div>
            <label class="upload-btn" for="f-upload">＋ Прикрепить файлы</label>
            <input type="file" id="f-upload" multiple style="display:none">
          </div>
          <button class="btn primary" id="f-save" ${editing ? "" : "disabled"}>${editing ? "💾 Сохранить" : "✅ Опубликовать и разослать"}</button>
          <button class="btn ghost" id="f-back">◀ Назад</button>
        </div>`;
      $("#f-chips", body).innerHTML = f.files.map((x, i) => `<div class="file-chip">${esc(x.name || x.type)}<span class="x" data-i="${i}">✕</span></div>`).join("");
      $("#f-chips", body).querySelectorAll(".x").forEach((x) => x.addEventListener("click", () => { f.files.splice(+x.dataset.i, 1); draw(); }));
      $("#f-disc", body).addEventListener("click", () => {
        sheetOptions("Дисциплина", discs.map((d) => ({ label: (d.emoji || "📚") + " " + d.name, value: d.id, on: d.id === f.discipline_id })), (v) => {
          f.discipline_id = v; dueOptions = []; draw();
        });
      });
      $("#f-due", body).addEventListener("click", async () => {
        if (!f.discipline_id) { toast("Сначала выберите дисциплину"); return; }
        try { dueOptions = await api(`/admin/next-lessons/${f.discipline_id}`); } catch (e) { dueOptions = []; }
        const opts = dueOptions.map((o, i) => ({ label: `${o.type || "Пара"} · ${fmtDateShort(o.date)}`, value: i }));
        opts.push({ label: "📆 Своя дата", value: "custom" });
        sheetOptions("Сдать к паре", opts, (v) => {
          if (v === "custom") {
            sheetCalendar(todayISO(), null, (iso) => { f.due_date = iso; f.due_type = null; draw(); });
          } else { f.due_date = dueOptions[v].date; f.due_type = dueOptions[v].type; draw(); }
        });
      });
      const dx = $("#f-due-x", body);
      if (dx) dx.addEventListener("click", () => { f.due_date = null; f.due_type = null; draw(); });
      $("#f-upload", body).addEventListener("change", async (e) => {
        const files = [...e.target.files];
        e.target.value = "";
        for (const file of files) {
          const fd = new FormData();
          fd.append("file", file);
          try {
            const r = await fetch("/api/admin/upload", { method: "POST", headers: { Authorization: "Bearer " + A.state.token }, body: fd });
            const data = await r.json();
            if (!r.ok) throw new Error(data.detail || "Ошибка загрузки");
            f.files.push(data); toast("Файл добавлен: " + (data.name || ""));
          } catch (err) { toast(err.message, true); }
        }
        draw();
      });
      $("#f-back", body).addEventListener("click", () => (editing ? renderHw(body) : renderHw(body)));
      const checkValid = () => {
        f.title = $("#f-title", body).value; f.task = $("#f-task", body).value; f.explanation = $("#f-expl", body).value;
        $("#f-save", body).disabled = !(f.discipline_id && f.title.trim() && f.task.trim());
      };
      ["#f-title", "#f-task"].forEach((s) => $(s, body).addEventListener("input", checkValid));
      checkValid();
      $("#f-save", body).addEventListener("click", async () => {
        const btn = $("#f-save", body); btn.disabled = true; btn.textContent = "⏳ Сохраняю…";
        const payload = {
          discipline_id: f.discipline_id, title: f.title.trim(), task: f.task.trim(),
          due_date: f.due_date, due_type: f.due_type,
          explanation: f.explanation.trim() || null, files: f.files,
        };
        try {
          if (editing) {
            await api(`/admin/homework/${editing.id}`, { method: "PATCH", body: payload });
            toast("Сохранено"); renderHw(body);
          } else {
            const r = await api("/admin/homework", { method: "POST", body: payload });
            toast(`Опубликовано! Отправлено студентам: ${r.sent}`); renderHw(body);
          }
        } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = editing ? "💾 Сохранить" : "✅ Опубликовать и разослать"; }
      });
    }
    draw();
  }

  /* ================= расписание ================= */
  async function renderScheduleAdmin(body) {
    body.innerHTML = `
      <div class="card"><div class="card-title">📥 Импорт из JSON</div>
        <div class="muted" style="font-size:12.5px;margin-bottom:8px">Вставьте содержимое schedule.json (формат из вашего промпта)</div>
        <textarea class="input" id="imp-json" style="min-height:120px;font-family:monospace;font-size:12px" placeholder='{"format_version":1,"group":"Р 26-1","weeks":[…]}'></textarea>
        <button class="btn primary" id="imp-btn">📥 Импортировать</button>
      </div>
      <div class="card"><div class="card-title">📅 Редактор по дням</div>
        <button class="btn" id="day-edit-btn" style="margin:0">Выбрать день</button>
      </div>`;
    $("#imp-btn", body).addEventListener("click", async () => {
      const text = $("#imp-json", body).value.trim();
      if (!text) { toast("Вставьте JSON", true); return; }
      const btn = $("#imp-btn", body); btn.disabled = true; btn.textContent = "⏳ Импортирую…";
      try {
        const r = await api("/admin/schedule/import", { method: "POST", body: { json: text } });
        let msg = `Импортировано: недель ${r.weeks}, дней ${r.days}, занятий ${r.lessons}`;
        if (r.warnings && r.warnings.length) msg += "\n⚠️ " + r.warnings.slice(0, 5).join("; ");
        toast(msg);
        btn.disabled = false; btn.textContent = "📥 Импортировать";
      } catch (e) { toast(e.message, true); btn.disabled = false; btn.textContent = "📥 Импортировать"; }
    });
    $("#day-edit-btn", body).addEventListener("click", () => {
      sheetCalendar(todayISO(), null, (iso) => renderDayEditor(body, iso));
    });
  }

  async function renderDayEditor(body, iso) {
    body.innerHTML = A.skeleton(3);
    let day, discs;
    try { [day, discs] = await Promise.all([api(`/admin/schedule/day/${iso}`), api("/admin/disciplines")]); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const lessons = day.lessons.map((l) => ({ ...l }));

    function draw() {
      body.innerHTML = `
        <div class="section-head"><div>
          <div class="section-title">${fmtDate(iso)}</div>
          <div class="section-sub">${lessons.length} пар · нажмите на пару для правки</div>
        </div></div>
        <div id="pairs">${lessons.map((l, i) => `
          <div class="a-row" data-i="${i}" style="cursor:pointer">
            <div class="grow"><div class="a-name">${l.pair_no}. ${esc(l.emoji || "")} ${esc(l.discipline)} ${l.lesson_type ? "(" + esc(l.lesson_type) + ")" : ""}</div>
            <div class="a-sub">${esc(l.start)}–${esc(l.end)}${l.room ? " · ауд. " + esc(l.room) : ""}</div></div>
            <span class="chevron">${I.chev}</span>
          </div>`).join("") || '<div class="empty">Пар нет</div>'}</div>
        <button class="btn" id="pair-add">➕ Добавить пару</button>
        ${lessons.length ? `<button class="btn danger" id="day-del">🗑 Удалить расписание на день</button>` : ""}
        <button class="btn ghost" id="day-back">◀ Назад</button>`;
      body.querySelectorAll("[data-i]").forEach((row) => row.addEventListener("click", () => editPair(+row.dataset.i)));
      $("#pair-add", body).addEventListener("click", () => {
        lessons.push({ pair_no: nextFree(), start: "08:30", end: "10:00", discipline_id: discs[0].id, discipline: discs[0].name, emoji: discs[0].emoji, lesson_type: null, room: null });
        editPair(lessons.length - 1);
      });
      const dd = $("#day-del", body);
      if (dd) dd.addEventListener("click", async () => {
        if (!confirm("Удалить всё расписание на этот день?")) return;
        try { await api(`/admin/schedule/day/${iso}`, { method: "DELETE" }); toast("Удалено"); renderDayEditor(body, iso); } catch (e) { toast(e.message, true); }
      });
      $("#day-back", body).addEventListener("click", () => renderScheduleAdmin(body));
    }

    function nextFree() {
      const used = new Set(lessons.map((l) => l.pair_no));
      for (let n = 1; n <= 7; n++) if (!used.has(n)) return n;
      return lessons.length + 1;
    }

    function editPair(i) {
      const l = lessons[i];
      const disc = discs.find((d) => d.id === l.discipline_id) || discs[0];
      body.innerHTML = `
        <div class="section-head"><div><div class="section-title">Пара ${l.pair_no}</div><div class="section-sub">${fmtDate(iso)}</div></div></div>
        <div class="field"><label>Дисциплина</label><button class="btn" id="p-disc" style="margin:0">${esc((disc.emoji || "📚") + " " + disc.name)}</button></div>
        <div class="field"><label>Тип</label><button class="btn" id="p-type" style="margin:0">${l.lesson_type || "— без типа"}</button></div>
        <div class="field"><label>Аудитория</label><input class="input" id="p-room" value="${esc(l.room || "")}" placeholder="415 / С/зал"></div>
        <div class="field"><label>Номер пары (стандартное время)</label><button class="btn" id="p-no" style="margin:0">${l.pair_no} · ${esc(l.start)}–${esc(l.end)}</button></div>
        <button class="btn primary" id="p-save">💾 Сохранить пару</button>
        <button class="btn danger" id="p-del">🗑 Удалить пару</button>
        <button class="btn ghost" id="p-back">◀ К дню</button>`;
      $("#p-disc", body).addEventListener("click", () => {
        sheetOptions("Дисциплина", discs.map((d) => ({ label: (d.emoji || "📚") + " " + d.name, value: d.id, on: d.id === l.discipline_id })), (v) => {
          l.discipline_id = v; const nd = discs.find((d) => d.id === v); l.discipline = nd.name; l.emoji = nd.emoji; editPair(i);
        });
      });
      $("#p-type", body).addEventListener("click", () => {
        sheetOptions("Тип занятия", [
          { label: "ПР — практика", value: "ПР", on: l.lesson_type === "ПР" },
          { label: "ЛЕК — лекция", value: "ЛЕК", on: l.lesson_type === "ЛЕК" },
          { label: "ЛАБ — лабораторная", value: "ЛАБ", on: l.lesson_type === "ЛАБ" },
          { label: "— без типа", value: null, on: !l.lesson_type },
        ], (v) => { l.lesson_type = v; editPair(i); });
      });
      $("#p-no", body).addEventListener("click", () => {
        const times = [["08:30", "10:00"], ["10:10", "11:40"], ["11:50", "13:20"], ["13:50", "15:20"], ["15:30", "17:00"], ["17:10", "18:40"], ["18:50", "20:20"]];
        sheetOptions("Номер пары", times.map((t, idx) => ({ label: `${idx + 1} · ${t[0]}–${t[1]}`, value: idx + 1, on: l.pair_no === idx + 1 })), (v) => {
          l.pair_no = v; l.start = times[v - 1][0]; l.end = times[v - 1][1]; editPair(i);
        });
      });
      $("#p-back", body).addEventListener("click", draw);
      $("#p-del", body).addEventListener("click", () => { lessons.splice(i, 1); draw(); });
      $("#p-save", body).addEventListener("click", async () => {
        l.room = $("#p-room", body).value.trim() || null;
        try {
          await api(`/admin/schedule/day/${iso}`, {
            method: "PUT",
            body: { lessons: lessons.map((x) => ({ pair_no: x.pair_no, start: x.start, end: x.end, discipline_id: x.discipline_id, lesson_type: x.lesson_type, room: x.room })) },
          });
          toast("Сохранено"); renderDayEditor(body, iso);
        } catch (e) { toast(e.message, true); }
      });
    }
    draw();
  }

  /* ================= студенты ================= */
  async function renderStudents(body) {
    body.innerHTML = A.skeleton(4);
    let list;
    try { list = await api("/admin/students"); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    body.innerHTML = `
      <button class="btn" id="stu-add">➕ Добавить студента</button>
      <div class="mt8">${list.map((s) => `
        <div class="a-row">
          <div class="st-dot ${s.authorized ? "on" : "off"}"></div>
          <div class="grow"><div class="a-name">${esc(s.fio)}</div>
          <div class="a-sub">${s.authorized ? "🟢 авторизован" : "⚪ не авторизован"} · код <span class="code">${esc(s.code)}</span></div></div>
          <button class="mini-btn" data-regen="${s.id}">🔑</button>
          <button class="mini-btn" data-unl="${s.id}">🔓</button>
          <button class="mini-btn danger" data-del="${s.id}">🗑</button>
        </div>`).join("")}</div>`;
    $("#stu-add", body).addEventListener("click", async () => {
      const fio = prompt("ФИО нового студента:");
      if (!fio) return;
      try { const r = await api("/admin/students", { method: "POST", body: { fio: fio.trim() } }); toast(`Добавлен. Код: ${r.code}`); renderStudents(body); }
      catch (e) { toast(e.message, true); }
    });
    body.querySelectorAll("[data-regen]").forEach((b) => b.addEventListener("click", async () => {
      try { const r = await api(`/admin/students/${b.dataset.regen}`, { method: "PATCH", body: { action: "regen" } }); toast("Новый код: " + r.code); renderStudents(body); } catch (e) { toast(e.message, true); }
    }));
    body.querySelectorAll("[data-unl]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("Сбросить привязку к Telegram?")) return;
      try { await api(`/admin/students/${b.dataset.unl}`, { method: "PATCH", body: { action: "unlink" } }); toast("Привязка сброшена"); renderStudents(body); } catch (e) { toast(e.message, true); }
    }));
    body.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("Удалить студента вместе с оценками и посещаемостью?")) return;
      try { await api(`/admin/students/${b.dataset.del}`, { method: "DELETE" }); toast("Удалён"); renderStudents(body); } catch (e) { toast(e.message, true); }
    }));
  }

  /* ================= дисциплины ================= */
  async function renderDisc(body) {
    body.innerHTML = A.skeleton(3);
    let list;
    try { list = await api("/admin/disciplines"); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    body.innerHTML = `
      <button class="btn" id="disc-add">➕ Добавить дисциплину</button>
      <div class="mt8">${list.map((d) => `
        <div class="a-row">
          <div class="grow"><div class="a-name">${esc(d.emoji || "📚")} ${esc(d.name)}</div>
          <div class="a-sub">${esc(d.teacher || "—")}${d.has_hw ? " · 📚 есть ДЗ" : ""}${d.has_textbooks ? " · 📖 учебники" : ""}</div></div>
          <button class="mini-btn" data-edit="${d.id}">✏️</button>
        </div>`).join("")}</div>`;
    $("#disc-add", body).addEventListener("click", async () => {
      const name = prompt("Название дисциплины:");
      if (!name) return;
      const emoji = prompt("Эмодзи (или «-»):", "📚") || "📚";
      const teacher = prompt("Преподаватель (Фамилия И.О. или «-»):", "-") || "-";
      try {
        await api("/admin/disciplines", { method: "POST", body: { name: name.trim(), emoji: emoji.trim() === "-" ? null : emoji.trim(), teacher: teacher.trim() === "-" ? null : teacher.trim() } });
        toast("Добавлена"); renderDisc(body);
      } catch (e) { toast(e.message, true); }
    });
    body.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => {
      const d = list.find((x) => x.id === +b.dataset.edit);
      const opts = [
        { label: "✏️ Название", value: "name" },
        { label: "😀 Эмодзи", value: "emoji" },
        { label: "👩‍🏫 Преподаватель", value: "teacher" },
        { label: "🗑 Удалить", value: "del" },
      ];
      sheetOptions(d.name, opts, async (v) => {
        if (v === "del") {
          if (!confirm(`Удалить «${d.name}»?`)) return;
          try { await api(`/admin/disciplines/${d.id}`, { method: "DELETE" }); toast("Удалена"); renderDisc(body); } catch (e) { toast(e.message, true); }
          return;
        }
        const cur = v === "name" ? d.name : v === "emoji" ? d.emoji : (d.teacher || "-");
        const val = prompt("Новое значение:", cur);
        if (val === null) return;
        const payload = {}; payload[v] = val.trim() === "-" && v !== "name" ? (v === "emoji" ? "📚" : "") : val.trim();
        try { await api(`/admin/disciplines/${d.id}`, { method: "PATCH", body: payload }); toast("Сохранено"); renderDisc(body); } catch (e) { toast(e.message, true); }
      });
    }));
  }

  /* ================= учебники ================= */
  async function renderTbAdmin(body) {
    body.innerHTML = A.skeleton(3);
    let data, discs;
    try { [data, discs] = await Promise.all([api("/admin/textbooks"), api("/admin/disciplines")]); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const groups = data.groups.length ? data.groups : [];
    body.innerHTML = `
      <button class="btn" id="tb-add">➕ Добавить учебник</button>
      <div class="mt8">${groups.length ? groups.map((g) => `
        <div class="hw-group"><div class="hw-group-head"><span>${esc(g.discipline.emoji || "📚")}</span> ${esc(g.discipline.name)}</div>
        ${g.items.map((t) => `
          <div class="hw-item" data-tbid="${t.id}">
            <div class="hw-item-title">${esc(t.title)}</div>
            <div class="hw-item-meta"><span>📎 ${t.files.length}</span>${t.description ? `<span>${esc(t.description.slice(0, 50))}</span>` : ""}</div>
          </div>`).join("")}</div>`).join("") : '<div class="empty">Учебников пока нет</div>'}</div>`;
    body.querySelectorAll("[data-tbid]").forEach((el) => el.addEventListener("click", () => {
      const id = +el.dataset.tbid;
      const t = groups.flatMap((g) => g.items).find((x) => x.id === id);
      const g = groups.find((x) => x.items.some((i) => i.id === id));
      sheetOptions(t.title, [
        { label: "✏️ Название", value: "title" },
        { label: "📝 Описание", value: "desc" },
        { label: "🗑 Удалить", value: "del" },
      ], async (v) => {
        if (v === "del") {
          if (!confirm("Удалить учебник?")) return;
          try { await api(`/admin/textbooks/${id}`, { method: "DELETE" }); toast("Удалён"); renderTbAdmin(body); } catch (e) { toast(e.message, true); }
          return;
        }
        const val = prompt(v === "title" ? "Название:" : "Описание:", v === "title" ? t.title : (t.description || ""));
        if (val === null) return;
        const payload = {}; payload[v === "title" ? "title" : "description"] = val.trim();
        try { await api(`/admin/textbooks/${id}`, { method: "PATCH", body: payload }); toast("Сохранено"); renderTbAdmin(body); } catch (e) { toast(e.message, true); }
      });
    }));
    $("#tb-add", body).addEventListener("click", async () => {
      const title = prompt("Название учебника/материала:");
      if (!title) return;
      const desc = prompt("Описание (или «-»):", "-") || "-";
      const discName = prompt(`Дисциплина (точно как в списке):\n${discs.map((d) => d.name).join(", ")}`);
      const disc = discs.find((d) => d.name.toLowerCase() === (discName || "").trim().toLowerCase());
      if (!disc) { toast("Дисциплина не найдена", true); return; }
      try { await api("/admin/textbooks", { method: "POST", body: { discipline_id: disc.id, title: title.trim(), description: desc.trim() === "-" ? null : desc.trim(), files: [] } }); toast("Добавлен"); renderTbAdmin(body); }
      catch (e) { toast(e.message, true); }
    });
  }

  /* ================= рассылка ================= */
  function renderBroadcast(body) {
    body.innerHTML = `
      <div class="card">
        <div class="field"><label>Текст уведомления (важное — придёт всем)</label>
          <textarea class="input" id="bc-text" style="min-height:130px" placeholder="Текст…"></textarea></div>
        <button class="btn primary" id="bc-send">📣 Отправить всем</button>
      </div>`;
    $("#bc-send", body).addEventListener("click", async () => {
      const text = $("#bc-text", body).value.trim();
      if (!text) { toast("Введите текст", true); return; }
      if (!confirm("Отправить всем авторизованным студентам?")) return;
      const btn = $("#bc-send", body); btn.disabled = true; btn.textContent = "⏳ Отправляю…";
      try { const r = await api("/admin/broadcast", { method: "POST", body: { text } }); toast(`Отправлено: ${r.sent} из ${r.total}`); }
      catch (e) { toast(e.message, true); }
      btn.disabled = false; btn.textContent = "📣 Отправить всем";
    });
  }
})();
