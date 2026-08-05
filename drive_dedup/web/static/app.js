(() => {
  const state = {
    authenticated: Boolean(window.__DRIVE_DEDUP__?.authenticated),
    jobId: null,
    demo: false,
    groups: [],
    selections: new Map(), // fileId -> 'keep' | 'remove'
    pollTimer: null,
  };

  const els = {
    hero: document.getElementById("hero"),
    workspace: document.getElementById("workspace"),
    workspaceTitle: document.getElementById("workspace-title"),
    workspaceSub: document.getElementById("workspace-sub"),
    scanForm: document.getElementById("scan-form"),
    progressPanel: document.getElementById("progress-panel"),
    progressFill: document.getElementById("progress-fill"),
    progressMessage: document.getElementById("progress-message"),
    results: document.getElementById("results"),
    resultsSummaryText: document.getElementById("results-summary-text"),
    groups: document.getElementById("groups"),
    btnStartScan: document.getElementById("btn-start-scan"),
    btnDemo: document.getElementById("btn-demo"),
    btnRescanTop: document.getElementById("btn-rescan-top"),
    btnSelectRecommended: document.getElementById("btn-select-recommended"),
    btnRemove: document.getElementById("btn-remove"),
    modal: document.getElementById("confirm-modal"),
    confirmBody: document.getElementById("confirm-body"),
    confirmThumbs: document.getElementById("confirm-thumbs"),
    btnCancelRemove: document.getElementById("btn-cancel-remove"),
    btnConfirmRemove: document.getElementById("btn-confirm-remove"),
    authPill: document.getElementById("auth-pill"),
  };

  function showWorkspace(mode) {
    els.hero.classList.add("hidden");
    els.workspace.classList.remove("hidden");
    if (mode === "demo") {
      els.workspaceTitle.textContent = "Visual demo";
      els.workspaceSub.textContent =
        "Sample duplicate groups so you can preview the review flow without Drive access.";
      els.scanForm.classList.add("hidden");
    } else {
      els.workspaceTitle.textContent = "Scan Google Drive";
      els.workspaceSub.textContent =
        "Optionally limit to a folder, then review lookalikes before anything is removed.";
      els.scanForm.classList.remove("hidden");
    }
  }

  function setProgress(current, total, message) {
    els.progressPanel.classList.remove("hidden");
    const pct =
      total > 0 ? Math.max(8, Math.min(100, Math.round((current / total) * 100))) : 12;
    els.progressFill.style.width = `${pct}%`;
    els.progressMessage.textContent = message || "Working…";
  }

  function applyRecommendedSelections() {
    state.selections.clear();
    for (const group of state.groups) {
      for (const image of group.images) {
        state.selections.set(image.id, image.action);
      }
    }
    renderGroups();
    updateRemoveButton();
  }

  function selectedRemovals() {
    return [...state.selections.entries()]
      .filter(([, action]) => action === "remove")
      .map(([id]) => id);
  }

  function updateRemoveButton() {
    const count = selectedRemovals().length;
    els.btnRemove.disabled = count === 0;
    els.btnRemove.textContent =
      count === 0 ? "Remove selected" : `Remove selected (${count})`;
  }

  function toggleAction(fileId, groupId) {
    const current = state.selections.get(fileId) || "remove";
    const next = current === "keep" ? "remove" : "keep";

    // Ensure at least one keep remains in the group.
    const group = state.groups.find((g) => g.group_id === groupId);
    if (!group) return;

    if (next === "remove") {
      const keepCount = group.images.filter(
        (img) => (state.selections.get(img.id) || img.action) === "keep" && img.id !== fileId
      ).length;
      if (keepCount === 0) {
        // Promote another image to keep.
        const other = group.images.find((img) => img.id !== fileId);
        if (other) state.selections.set(other.id, "keep");
      }
    }

    state.selections.set(fileId, next);
    renderGroups();
    updateRemoveButton();
  }

  function renderGroups() {
    els.groups.innerHTML = "";
    state.groups.forEach((group, index) => {
      const section = document.createElement("section");
      section.className = "group";
      section.style.animationDelay = `${Math.min(index * 0.05, 0.4)}s`;

      const head = document.createElement("div");
      head.className = "group-head";
      head.innerHTML = `
        <div>
          <h3>Group ${group.group_id}</h3>
          <p class="group-meta">${escapeHtml(group.reason)} · ${escapeHtml(
            group.reclaimable_label
          )} reclaimable</p>
        </div>
        <span class="match-tag ${group.match_type}">${escapeHtml(group.match_type)}</span>
      `;
      section.appendChild(head);

      const grid = document.createElement("div");
      grid.className = "image-grid";

      for (const image of group.images) {
        const action = state.selections.get(image.id) || image.action;
        const tile = document.createElement("button");
        tile.type = "button";
        tile.className = "image-tile";
        tile.dataset.action = action;
        tile.addEventListener("click", () => toggleAction(image.id, group.group_id));
        tile.innerHTML = `
          <div class="tile-top">
            <span class="action-chip">${action}</span>
            <span class="tile-meta">${escapeHtml(image.size_label)}</span>
          </div>
          <div class="thumb-wrap">
            <img src="${image.thumbnail_url}" alt="${escapeHtml(image.name)}" loading="lazy" />
          </div>
          <p class="tile-name">${escapeHtml(image.name)}</p>
          <p class="tile-meta">${escapeHtml(image.resolution)}</p>
        `;
        grid.appendChild(tile);
      }

      section.appendChild(grid);
      els.groups.appendChild(section);
    });
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  async function startScan({ demo = false, folderId = "", exactOnly = false, threshold = 5 } = {}) {
    state.demo = demo;
    state.groups = [];
    state.selections.clear();
    els.results.classList.add("hidden");
    showWorkspace(demo ? "demo" : "live");
    setProgress(0, 1, demo ? "Preparing demo library…" : "Starting Drive scan…");

    const response = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        demo,
        folder_id: folderId || null,
        exact_only: exactOnly,
        threshold,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      setProgress(0, 1, err.detail || "Could not start scan");
      return;
    }

    const job = await response.json();
    state.jobId = job.id;
    pollJob(job.id);
  }

  function pollJob(jobId) {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(async () => {
      try {
        const response = await fetch(`/api/scan/${jobId}`);
        if (!response.ok) return;
        const job = await response.json();
        setProgress(job.current || 0, job.total || 1, job.message);

        if (job.status === "completed") {
          clearInterval(state.pollTimer);
          state.pollTimer = null;
          els.progressFill.style.width = "100%";
          const result = job.result || { groups: [], group_count: 0, remove_count: 0 };
          state.groups = result.groups || [];
          if (!state.groups.length) {
            els.results.classList.remove("hidden");
            els.resultsSummaryText.textContent = "No duplicate images found.";
            els.groups.innerHTML = "";
            updateRemoveButton();
            return;
          }
          els.results.classList.remove("hidden");
          els.resultsSummaryText.textContent = `${result.group_count} group(s) · ${result.remove_count} recommended for removal · ${result.reclaimable_label} reclaimable`;
          applyRecommendedSelections();
        }

        if (job.status === "failed") {
          clearInterval(state.pollTimer);
          state.pollTimer = null;
          setProgress(job.current || 0, job.total || 1, job.error || "Scan failed");
        }
      } catch (_err) {
        // Keep polling; transient network blips are fine.
      }
    }, 600);
  }

  function openConfirmModal() {
    const ids = selectedRemovals();
    if (!ids.length) return;
    const images = state.groups.flatMap((g) => g.images).filter((img) => ids.includes(img.id));
    els.confirmBody.textContent = state.demo
      ? `Demo mode will pretend to trash ${ids.length} selected image(s).`
      : `Move ${ids.length} selected duplicate(s) to Google Drive Trash? You can restore them from Trash later.`;
    els.confirmThumbs.innerHTML = images
      .slice(0, 8)
      .map((img) => `<img src="${img.thumbnail_url}" alt="${escapeHtml(img.name)}" />`)
      .join("");
    els.modal.classList.remove("hidden");
  }

  function closeConfirmModal() {
    els.modal.classList.add("hidden");
  }

  async function confirmRemove() {
    const fileIds = selectedRemovals();
    els.btnConfirmRemove.disabled = true;
    try {
      const response = await fetch("/api/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_ids: fileIds,
          confirm: true,
          demo: state.demo,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        alert(payload.detail || "Removal failed");
        return;
      }

      const trashed = new Set(payload.trashed || []);
      state.groups = state.groups
        .map((group) => {
          const images = group.images.filter((img) => !trashed.has(img.id));
          return { ...group, images };
        })
        .filter((group) => group.images.length > 1);

      for (const id of trashed) state.selections.delete(id);

      closeConfirmModal();
      if (!state.groups.length) {
        els.resultsSummaryText.textContent = payload.message || "Selected duplicates removed.";
        els.groups.innerHTML = "";
      } else {
        els.resultsSummaryText.textContent = `${payload.message || "Removed."} Remaining groups below.`;
        renderGroups();
      }
      updateRemoveButton();
    } finally {
      els.btnConfirmRemove.disabled = false;
    }
  }

  // Event wiring
  els.btnDemo?.addEventListener("click", () => startScan({ demo: true }));
  els.btnStartScan?.addEventListener("click", () => showWorkspace("live"));
  els.btnRescanTop?.addEventListener("click", () => showWorkspace("live"));

  els.scanForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(els.scanForm);
    startScan({
      demo: false,
      folderId: String(data.get("folder_id") || "").trim(),
      exactOnly: data.get("exact_only") === "on",
      threshold: Number(data.get("threshold") || 5),
    });
  });

  els.btnSelectRecommended?.addEventListener("click", applyRecommendedSelections);
  els.btnRemove?.addEventListener("click", openConfirmModal);
  els.btnCancelRemove?.addEventListener("click", closeConfirmModal);
  els.btnConfirmRemove?.addEventListener("click", confirmRemove);

  els.modal?.addEventListener("click", (event) => {
    if (event.target === els.modal) closeConfirmModal();
  });

  // Surface auth query feedback
  const params = new URLSearchParams(window.location.search);
  if (params.get("auth") === "success" && els.authPill) {
    els.authPill.dataset.state = "in";
    els.authPill.textContent = "Drive connected";
    history.replaceState({}, "", "/");
  }
  if (params.get("auth") === "error") {
    alert(`Google auth error: ${params.get("message") || "unknown"}`);
    history.replaceState({}, "", "/");
  }
})();
