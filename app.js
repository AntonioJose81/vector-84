const STORAGE_KEYS = {
  saved: "vector84_saved_ids",
  read: "vector84_read_ids",
  retroFx: "vector84_retro_fx",
};

const CATEGORY_META = {
  fdm: { label: "FDM / 3D", icon: "▲", badgeClass: "badge-fdm", cover: "./assets/cover-fdm.svg" },
  ia: { label: "IA", icon: "◆", badgeClass: "badge-ia", cover: "./assets/cover-ia.svg" },
  emprendimiento: { label: "Emprendimiento", icon: "●", badgeClass: "badge-emprendimiento", cover: "./assets/cover-startup.svg" },
  cruce: { label: "Cruce", icon: "✦", badgeClass: "badge-cruce", cover: "./assets/cover-cross.svg" },
};

const state = {
  feed: null,
  view: "all", // all | news | papers | saved
  category: "all", // all | fdm | ia | emprendimiento | crossover
  search: "",
  sort: "importance", // importance | recent
  hideRead: false,
  savedIds: new Set(loadJsonStorage(STORAGE_KEYS.saved, [])),
  readIds: new Set(loadJsonStorage(STORAGE_KEYS.read, [])),
  activeDialogItem: null,
};

const els = {
  metaEdition: document.getElementById("meta-edition"),
  metaUpdated: document.getElementById("meta-updated"),
  toggleRetroFx: document.getElementById("toggle-retro-fx"),
  briefingSection: document.getElementById("briefing-section"),
  briefingHeading: document.getElementById("briefing-heading"),
  briefingIntro: document.getElementById("briefing-intro"),
  briefingList: document.getElementById("briefing-list"),
  toggleBriefing: document.getElementById("toggle-briefing"),
  searchInput: document.getElementById("search-input"),
  sortSelect: document.getElementById("sort-select"),
  hideReadCheckbox: document.getElementById("hide-read-checkbox"),
  statusBanner: document.getElementById("status-banner"),
  newsSection: document.getElementById("news-section"),
  papersSection: document.getElementById("papers-section"),
  newsGrid: document.getElementById("news-grid"),
  papersGrid: document.getElementById("papers-grid"),
  newsCounter: document.getElementById("news-counter"),
  papersCounter: document.getElementById("papers-counter"),
  emptyState: document.getElementById("empty-state"),
  resetFiltersBtn: document.getElementById("reset-filters-btn"),
  dialog: document.getElementById("reader-dialog"),
  dialogBadges: document.getElementById("dialog-badges"),
  dialogMediaWrap: document.getElementById("dialog-media-wrap"),
  dialogImage: document.getElementById("dialog-image"),
  dialogTitle: document.getElementById("dialog-title"),
  dialogOriginalTitle: document.getElementById("dialog-original-title"),
  dialogMeta: document.getElementById("dialog-meta"),
  dialogSummary: document.getElementById("dialog-summary"),
  dialogDeep: document.getElementById("dialog-deep"),
  dialogPaperBreakdown: document.getElementById("dialog-paper-breakdown"),
  dialogProblem: document.getElementById("dialog-problem"),
  dialogMethod: document.getElementById("dialog-method"),
  dialogTakeaway: document.getElementById("dialog-takeaway"),
  dialogTags: document.getElementById("dialog-tags"),
  dialogPdfLink: document.getElementById("dialog-pdf-link"),
  dialogSourceLink: document.getElementById("dialog-source-link"),
  dialogSaveBtn: document.getElementById("dialog-save-btn"),
  dialogShareBtn: document.getElementById("dialog-share-btn"),
  toast: document.getElementById("toast"),
};

function loadJsonStorage(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function saveSetStorage(key, set) {
  try {
    localStorage.setItem(key, JSON.stringify([...set]));
  } catch {
    // Ignore storage quota errors
  }
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(d);
}

function formatDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

function getFallbackCover(item) {
  if (item.is_crossover) return CATEGORY_META.cruce.cover;
  return (CATEGORY_META[item.primary_category] || CATEGORY_META.ia).cover;
}

function createEl(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderBadges(item, includePaperCode = false) {
  const row = createEl("div", "badge-row");
  const cats = item.categories?.length ? item.categories : [item.primary_category || "ia"];

  for (const cat of cats) {
    const meta = CATEGORY_META[cat];
    if (!meta) continue;
    const badge = createEl("span", `badge ${meta.badgeClass}`);
    const icon = createEl("span", "", meta.icon);
    icon.setAttribute("aria-hidden", "true");
    badge.append(icon, createEl("span", "", meta.label));
    row.append(badge);
  }

  if (item.is_crossover) {
    const cross = createEl("span", "badge badge-cruce");
    const icon = createEl("span", "", "✦");
    icon.setAttribute("aria-hidden", "true");
    cross.append(icon, createEl("span", "", "Cruce"));
    row.append(cross);
  }

  if (includePaperCode && item.paper_code) {
    row.append(createEl("span", "badge badge-code", item.paper_code));
  }
  return row;
}

let toastTimer = null;
function showToast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    els.toast.hidden = true;
  }, 2600);
}

function initRetroToggle() {
  const saved = loadJsonStorage(STORAGE_KEYS.retroFx, true);
  applyRetroFx(Boolean(saved));

  els.toggleRetroFx.addEventListener("click", () => {
    const next = !document.body.classList.contains("retro-fx-on");
    applyRetroFx(next);
    try {
      localStorage.setItem(STORAGE_KEYS.retroFx, JSON.stringify(next));
    } catch {
      // ignore
    }
  });
}

function applyRetroFx(enabled) {
  document.body.classList.toggle("retro-fx-on", enabled);
  els.toggleRetroFx.setAttribute("aria-pressed", String(enabled));
  els.toggleRetroFx.lastElementChild.textContent = enabled ? "Efectos 80s: ON" : "Efectos 80s: OFF";
}

function initDialogFallbacks() {
  // Limpia returnValue en cada cierre para evitar valores obsoletos (modern-web-guidance: dialog)
  els.dialog.addEventListener("close", () => {
    els.dialog.returnValue = "";
  });

  // Fallback progresivo de light-dismiss solo en navegadores sin closedBy nativo (ej. Safari)
  if (!("closedBy" in HTMLDialogElement.prototype)) {
    const isOutside = (e, dialog) => {
      const r = dialog.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    let pressedOutside = false;
    els.dialog.addEventListener("pointerdown", (e) => {
      pressedOutside = isOutside(e, els.dialog);
    });
    els.dialog.addEventListener("pointerup", (e) => {
      if (pressedOutside && isOutside(e, els.dialog)) {
        els.dialog.close();
      }
    });
  }
}

function findItemById(id) {
  if (!state.feed) return null;
  return (
    state.feed.news.find((n) => n.id === id) ||
    state.feed.papers.find((p) => p.id === id) ||
    null
  );
}

function openReaderDialog(item) {
  state.activeDialogItem = item;
  state.readIds.add(item.id);
  saveSetStorage(STORAGE_KEYS.read, state.readIds);

  els.dialogBadges.replaceChildren(renderBadges(item, item.type === "paper"));

  if (item.type === "news") {
    const imgSrc = item.image || getFallbackCover(item);
    els.dialogImage.src = imgSrc;
    els.dialogImage.alt = item.title_es;
    els.dialogImage.onerror = () => {
      els.dialogImage.onerror = null;
      els.dialogImage.src = getFallbackCover(item);
    };
    els.dialogMediaWrap.hidden = false;
  } else {
    els.dialogMediaWrap.hidden = true;
  }

  els.dialogTitle.textContent = item.title_es;
  if (item.original_title && item.original_title !== item.title_es) {
    els.dialogOriginalTitle.textContent = `Título original: ${item.original_title}`;
    els.dialogOriginalTitle.hidden = false;
  } else {
    els.dialogOriginalTitle.hidden = true;
  }

  const metaParts = [item.source, formatDate(item.published_at)];
  if (item.authors?.length) {
    metaParts.push(item.authors.join(", "));
  }
  els.dialogMeta.textContent = metaParts.filter(Boolean).join(" · ");

  els.dialogSummary.textContent = item.summary_es;

  if (item.deep_summary_es) {
    els.dialogDeep.textContent = item.deep_summary_es;
    els.dialogDeep.hidden = false;
  } else {
    els.dialogDeep.hidden = true;
  }

  const hasBreakdown = item.type === "paper" && (item.problem_es || item.method_es || item.takeaway_es);
  els.dialogPaperBreakdown.hidden = !hasBreakdown;
  if (hasBreakdown) {
    els.dialogProblem.textContent = item.problem_es || "—";
    els.dialogMethod.textContent = item.method_es || "—";
    els.dialogTakeaway.textContent = item.takeaway_es || "—";
  }

  els.dialogTags.replaceChildren(
    ...(item.tags || []).map((t) => createEl("span", "tag-chip", `#${t}`))
  );

  if (item.pdf_url) {
    els.dialogPdfLink.href = item.pdf_url;
    els.dialogPdfLink.hidden = false;
  } else {
    els.dialogPdfLink.hidden = true;
  }

  els.dialogSourceLink.href = item.url;
  els.dialogSourceLink.firstElementChild.textContent =
    item.type === "paper" ? "Ver ficha original" : "Abrir artículo original";

  syncDialogSaveButton();
  els.dialog.showModal();
  renderAll();
}

function syncDialogSaveButton() {
  const item = state.activeDialogItem;
  if (!item) return;
  const saved = state.savedIds.has(item.id);
  els.dialogSaveBtn.setAttribute("aria-pressed", String(saved));
  els.dialogSaveBtn.lastElementChild.textContent = saved ? "Guardado" : "Guardar";
}

function toggleSaved(id) {
  if (state.savedIds.has(id)) {
    state.savedIds.delete(id);
    showToast("Quitado de guardados");
  } else {
    state.savedIds.add(id);
    showToast("Guardado en tus favoritos");
  }
  saveSetStorage(STORAGE_KEYS.saved, state.savedIds);
  syncDialogSaveButton();
  renderAll();
}

function toggleRead(id) {
  if (state.readIds.has(id)) {
    state.readIds.delete(id);
  } else {
    state.readIds.add(id);
  }
  saveSetStorage(STORAGE_KEYS.read, state.readIds);
  renderAll();
}

function matchesFilters(item) {
  if (state.view === "saved" && !state.savedIds.has(item.id)) return false;
  if (state.hideRead && state.readIds.has(item.id)) return false;

  if (state.category === "crossover") {
    if (!item.is_crossover) return false;
  } else if (state.category !== "all") {
    const cats = item.categories || [item.primary_category];
    if (!cats.includes(state.category)) return false;
  }

  if (state.search) {
    const haystack = [
      item.title_es,
      item.original_title,
      item.summary_es,
      item.deep_summary_es,
      item.takeaway_es,
      item.source,
      item.paper_code,
      ...(item.tags || []),
      ...(item.authors || []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (!haystack.includes(state.search)) return false;
  }

  return true;
}

function sortItems(items) {
  const list = [...items];
  if (state.sort === "recent") {
    list.sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));
  } else {
    list.sort((a, b) => {
      const diff = (b.importance || 0) - (a.importance || 0);
      if (diff !== 0) return diff;
      return (b.published_at || "").localeCompare(a.published_at || "");
    });
  }
  return list;
}

function buildNewsCard(item, index) {
  const isLead = index === 0 && state.view !== "saved" && !state.search && state.category === "all";
  const isDeferred = index >= 3;
  const article = createEl("article", `card${isLead ? " is-lead" : ""}${isDeferred ? " card-deferred" : ""}${state.readIds.has(item.id) ? " is-read" : ""}`);

  // Región 1: Media (<img> directo, fetchpriority="high" solo en la LCP lead)
  const img = document.createElement("img");
  img.src = item.image || getFallbackCover(item);
  img.alt = item.title_es;
  img.width = 800;
  img.height = 450;
  if (index === 0) {
    img.fetchPriority = "high";
  } else {
    img.loading = "lazy";
  }
  img.decoding = "async";
  img.onerror = () => {
    img.onerror = null;
    img.src = getFallbackCover(item);
  };
  article.append(img);

  // Región 2: Header
  const header = createEl("header");
  header.append(renderBadges(item));

  const title = createEl("h3", "card-title");
  const titleLink = createEl("a", "card-link", item.title_es);
  titleLink.href = `#item-${item.id}`;
  titleLink.addEventListener("click", (e) => {
    e.preventDefault();
    openReaderDialog(item);
  });
  title.append(titleLink);
  header.append(title);

  const meta = createEl("div", "card-meta");
  meta.textContent = `${item.source} · ${formatDate(item.published_at)}`;
  header.append(meta);
  article.append(header);

  // Región 3: Content
  const content = createEl("div", "card-content");
  content.append(createEl("p", "", item.summary_es));
  if (item.tags?.length) {
    const tags = createEl("div", "tag-row");
    for (const tag of item.tags.slice(0, 3)) {
      tags.append(createEl("span", "tag-chip", `#${tag}`));
    }
    content.append(tags);
  }
  article.append(content);

  // Región 4: Footer (acciones nativas independientes elevadas sobre stretched link)
  const footer = createEl("footer");
  const leftActions = createEl("div", "footer-actions");

  const origLink = createEl("a", "btn-ghost");
  origLink.href = item.url;
  origLink.target = "_blank";
  origLink.rel = "noopener noreferrer";
  origLink.innerHTML = `<span>Original</span><span class="sr-only">: ${escapeHtml(item.title_es)}</span><span aria-hidden="true">↗</span>`;
  leftActions.append(origLink);

  const rightActions = createEl("div", "footer-actions");
  rightActions.append(buildSaveButton(item), buildReadButton(item));

  footer.append(leftActions, rightActions);
  article.append(footer);
  return article;
}

function buildPaperCard(item, index) {
  const isDeferred = index >= 3;
  const article = createEl(
    "article",
    `card paper-card primary-${item.primary_category || "fdm"}${item.is_crossover ? " is-crossover" : ""}${isDeferred ? " card-deferred" : ""}${state.readIds.has(item.id) ? " is-read" : ""}`
  );

  // Región 1: Header (sin media -> queda columna única limpia)
  const header = createEl("header");
  header.append(renderBadges(item, true));

  const title = createEl("h3", "card-title");
  const titleLink = createEl("a", "card-link", item.title_es);
  titleLink.href = `#item-${item.id}`;
  titleLink.addEventListener("click", (e) => {
    e.preventDefault();
    openReaderDialog(item);
  });
  title.append(titleLink);
  header.append(title);

  if (item.original_title && item.original_title !== item.title_es) {
    header.append(createEl("p", "card-original-sub", item.original_title));
  }

  const meta = createEl("div", "card-meta");
  const authorsText = item.authors?.length ? item.authors.slice(0, 3).join(", ") : item.source;
  meta.textContent = `${item.source} · ${formatDate(item.published_at)} · ${authorsText}`;
  header.append(meta);
  article.append(header);

  // Región 2: Content
  const content = createEl("div", "card-content");
  content.append(createEl("p", "", item.summary_es));

  if (item.problem_es || item.takeaway_es) {
    const box = createEl("div", "paper-points");
    if (item.problem_es) {
      const row = createEl("div", "paper-point");
      row.append(createEl("span", "paper-point-key", "PROBLEMA"), createEl("span", "", item.problem_es));
      box.append(row);
    }
    if (item.takeaway_es) {
      const row = createEl("div", "paper-point");
      row.append(createEl("span", "paper-point-key", "IMPACTO"), createEl("span", "", item.takeaway_es));
      box.append(row);
    }
    content.append(box);
  }

  if (item.tags?.length) {
    const tags = createEl("div", "tag-row");
    for (const tag of item.tags.slice(0, 4)) {
      tags.append(createEl("span", "tag-chip", `#${tag}`));
    }
    content.append(tags);
  }
  article.append(content);

  // Región 3: Footer con botón directo de Descargar PDF
  const footer = createEl("footer");
  const leftActions = createEl("div", "footer-actions");

  if (item.pdf_url) {
    const pdfBtn = createEl("a", "btn-pdf");
    pdfBtn.href = item.pdf_url;
    pdfBtn.target = "_blank";
    pdfBtn.rel = "noopener noreferrer";
    pdfBtn.innerHTML = `<span aria-hidden="true">⬇</span><span>Descargar PDF</span><span class="sr-only"> de ${escapeHtml(item.title_es)}</span>`;
    leftActions.append(pdfBtn);
  }

  const srcBtn = createEl("a", "btn-ghost");
  srcBtn.href = item.url;
  srcBtn.target = "_blank";
  srcBtn.rel = "noopener noreferrer";
  srcBtn.innerHTML = `<span>Ficha</span><span class="sr-only"> original de ${escapeHtml(item.title_es)}</span><span aria-hidden="true">↗</span>`;
  leftActions.append(srcBtn);

  const rightActions = createEl("div", "footer-actions");
  rightActions.append(buildSaveButton(item), buildReadButton(item));

  footer.append(leftActions, rightActions);
  article.append(footer);
  return article;
}

function buildSaveButton(item) {
  const isSaved = state.savedIds.has(item.id);
  const btn = createEl("button", "icon-btn save-btn");
  btn.type = "button";
  btn.setAttribute("aria-pressed", String(isSaved));
  btn.setAttribute("aria-label", isSaved ? `Quitar ${item.title_es} de guardados` : `Guardar ${item.title_es}`);
  btn.title = isSaved ? "Quitar de guardados" : "Guardar favorito";
  btn.textContent = isSaved ? "★" : "☆";
  btn.addEventListener("click", () => toggleSaved(item.id));
  return btn;
}

function buildReadButton(item) {
  const isRead = state.readIds.has(item.id);
  const btn = createEl("button", "icon-btn read-btn");
  btn.type = "button";
  btn.setAttribute("aria-pressed", String(isRead));
  btn.setAttribute("aria-label", isRead ? `Marcar ${item.title_es} como no leído` : `Marcar ${item.title_es} como leído`);
  btn.title = isRead ? "Marcar como no leído" : "Marcar como leído";
  btn.textContent = "✓";
  btn.addEventListener("click", () => toggleRead(item.id));
  return btn;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderBriefing() {
  const briefing = state.feed?.briefing;
  if (!briefing || (!briefing.headline && !briefing.bullets?.length)) {
    els.briefingSection.hidden = true;
    return;
  }

  els.briefingSection.hidden = state.view === "saved";
  els.briefingHeading.textContent = briefing.headline || "Claves del día";
  els.briefingIntro.textContent = briefing.intro || "";

  const nodes = (briefing.bullets || []).map((b) => {
    const li = createEl("li", "briefing-item");
    const top = createEl("div", "briefing-item-top");
    const catKey = b.category || "ia";
    top.append(createEl("span", `briefing-label cat-${catKey}`, b.label || catKey.toUpperCase()));
    li.append(top);
    li.append(createEl("p", "briefing-text", b.text));

    if (b.ref_id) {
      const refItem = findItemById(b.ref_id);
      if (refItem) {
        const jump = createEl("button", "briefing-jump", refItem.type === "paper" ? "Abrir paper →" : "Leer noticia →");
        jump.type = "button";
        jump.addEventListener("click", () => openReaderDialog(refItem));
        li.append(jump);
      }
    }
    return li;
  });

  els.briefingList.replaceChildren(...nodes);
}

function updateCounters() {
  const allNews = state.feed?.news || [];
  const allPapers = state.feed?.papers || [];
  const allItems = [...allNews, ...allPapers];

  document.getElementById("count-all").textContent = String(allItems.length);
  document.getElementById("count-news").textContent = String(allNews.length);
  document.getElementById("count-papers").textContent = String(allPapers.length);
  document.getElementById("count-saved").textContent = String(
    allItems.filter((i) => state.savedIds.has(i.id)).length
  );

  const scopeItems =
    state.view === "news"
      ? allNews
      : state.view === "papers"
        ? allPapers
        : state.view === "saved"
          ? allItems.filter((i) => state.savedIds.has(i.id))
          : allItems;

  document.getElementById("cat-count-all").textContent = String(scopeItems.length);
  document.getElementById("cat-count-fdm").textContent = String(
    scopeItems.filter((i) => (i.categories || []).includes("fdm")).length
  );
  document.getElementById("cat-count-ia").textContent = String(
    scopeItems.filter((i) => (i.categories || []).includes("ia")).length
  );
  document.getElementById("cat-count-emprendimiento").textContent = String(
    scopeItems.filter((i) => (i.categories || []).includes("emprendimiento")).length
  );
  document.getElementById("cat-count-crossover").textContent = String(
    scopeItems.filter((i) => i.is_crossover).length
  );
}

function renderAll() {
  if (!state.feed) return;
  updateCounters();
  renderBriefing();

  const filteredNews = sortItems((state.feed.news || []).filter(matchesFilters));
  const filteredPapers = sortItems((state.feed.papers || []).filter(matchesFilters));

  const showNews = state.view === "all" || state.view === "news" || state.view === "saved";
  const showPapers = state.view === "all" || state.view === "papers" || state.view === "saved";

  els.newsSection.hidden = !showNews || filteredNews.length === 0;
  els.papersSection.hidden = !showPapers || filteredPapers.length === 0;

  if (!els.newsSection.hidden) {
    els.newsCounter.textContent = `${filteredNews.length} ${filteredNews.length === 1 ? "artículo" : "artículos"}`;
    els.newsGrid.replaceChildren(...filteredNews.map((item, idx) => buildNewsCard(item, idx)));
  }

  if (!els.papersSection.hidden) {
    els.papersCounter.textContent = `${filteredPapers.length} ${filteredPapers.length === 1 ? "paper con PDF" : "papers con PDF"}`;
    els.papersGrid.replaceChildren(...filteredPapers.map((item, idx) => buildPaperCard(item, idx)));
  }

  els.emptyState.hidden = !(els.newsSection.hidden && els.papersSection.hidden);
}

function bindEvents() {
  // Pestañas de sección
  for (const tab of document.querySelectorAll(".nav-tab")) {
    tab.addEventListener("click", () => {
      state.view = tab.dataset.view;
      for (const other of document.querySelectorAll(".nav-tab")) {
        const active = other === tab;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-pressed", String(active));
      }
      renderAll();
    });
  }

  // Chips de categoría
  for (const pill of document.querySelectorAll(".filter-pill")) {
    pill.addEventListener("click", () => {
      state.category = pill.dataset.cat;
      for (const other of document.querySelectorAll(".filter-pill")) {
        const active = other === pill;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-pressed", String(active));
      }
      renderAll();
    });
  }

  // Buscador
  els.searchInput.addEventListener("input", () => {
    state.search = els.searchInput.value.trim().toLowerCase();
    renderAll();
  });

  // Orden y ocultar leídos
  els.sortSelect.addEventListener("change", () => {
    state.sort = els.sortSelect.value;
    renderAll();
  });

  els.hideReadCheckbox.addEventListener("change", () => {
    state.hideRead = els.hideReadCheckbox.checked;
    renderAll();
  });

  // Colapsar Parte Diario
  els.toggleBriefing.addEventListener("click", () => {
    const collapsed = !els.briefingList.hidden;
    els.briefingList.hidden = collapsed;
    els.toggleBriefing.setAttribute("aria-expanded", String(!collapsed));
    els.toggleBriefing.textContent = collapsed ? "Mostrar parte" : "Ocultar parte";
  });

  // Restablecer filtros
  els.resetFiltersBtn.addEventListener("click", () => {
    state.view = "all";
    state.category = "all";
    state.search = "";
    state.hideRead = false;
    els.searchInput.value = "";
    els.hideReadCheckbox.checked = false;
    for (const tab of document.querySelectorAll(".nav-tab")) {
      const active = tab.dataset.view === "all";
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-pressed", String(active));
    }
    for (const pill of document.querySelectorAll(".filter-pill")) {
      const active = pill.dataset.cat === "all";
      pill.classList.toggle("is-active", active);
      pill.setAttribute("aria-pressed", String(active));
    }
    renderAll();
  });

  // Acciones dentro del modal
  els.dialogSaveBtn.addEventListener("click", () => {
    if (state.activeDialogItem) {
      toggleSaved(state.activeDialogItem.id);
    }
  });

  els.dialogShareBtn.addEventListener("click", async () => {
    if (!state.activeDialogItem) return;
    const shareUrl = new URL(window.location.href);
    shareUrl.searchParams.set("item", state.activeDialogItem.id);
    try {
      await navigator.clipboard.writeText(shareUrl.toString());
      showToast("Enlace directo copiado al portapapeles");
    } catch {
      showToast("Copia la URL desde la barra del navegador");
    }
  });
}

async function boot() {
  initRetroToggle();
  initDialogFallbacks();
  bindEvents();

  try {
    const res = await fetch("./data/feed.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.feed = await res.json();

    els.metaEdition.textContent = `EDICIÓN ${state.feed.edition || "HOY"}`;
    els.metaUpdated.textContent = `Actualizado: ${formatDateTime(state.feed.updated_at)}`;

    renderAll();

    // Si alguien comparte un enlace directo (?item=<id>), abrirlo en el lector
    const sharedId = new URLSearchParams(window.location.search).get("item");
    if (sharedId) {
      const target = findItemById(sharedId);
      if (target) openReaderDialog(target);
    }
  } catch (err) {
    els.statusBanner.hidden = false;
    els.statusBanner.textContent =
      "No se pudo cargar data/feed.json. Si estás abriendo index.html en local, ejecútalo con un servidor local (por ejemplo: python3 -m http.server 8000).";
    console.error("Error cargando feed.json:", err);
  }
}

boot();
