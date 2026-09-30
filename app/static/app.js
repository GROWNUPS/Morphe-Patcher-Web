let stagedApks = [];
let uploadedApkData = null;
let currentJobId = null;
let eventSource = null;
let isFilenameManuallyEdited = false;

document.addEventListener("DOMContentLoaded", () => {
  setupThemeToggle();
  setupTabs();
  setupUpload();
  setupTerminalControls();
  setupOutputs();
  setupSystem();
  setupPatchUpdateHandlers();
  setupProfiles();
  
  fetchSystemStatus();
  fetchOutputs();
  fetchPatchSources();
  fetchKeystoreDetails();
  fetchCompatibleVersions();
  loadProfilesList();
  setInterval(() => {
    fetchSystemStatus();
    if (document.querySelector('.tab-btn[data-tab="terminal"]')?.classList.contains('active')) {
      refreshTerminalQueue();
    }
  }, 4000);
});

function setupThemeToggle() {
  const toggleBtn = document.getElementById("theme-toggle-btn");
  const darkIcon = document.getElementById("theme-icon-dark");
  const lightIcon = document.getElementById("theme-icon-light");

  function syncThemeUI(theme) {
    if (darkIcon && lightIcon) {
      if (theme === "light") {
        darkIcon.style.display = "none";
        lightIcon.style.display = "block";
      } else {
        darkIcon.style.display = "block";
        lightIcon.style.display = "none";
      }
    }
  }

  const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
  syncThemeUI(currentTheme);

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const activeTheme = document.documentElement.getAttribute("data-theme") || "dark";
      const nextTheme = activeTheme === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", nextTheme);
      try {
        localStorage.setItem("patchium_theme", nextTheme);
      } catch (e) {}
      syncThemeUI(nextTheme);
    });
  }
}

function setupTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      switchTab(target);
    });
  });
}

function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-content").forEach(content => {
    content.classList.toggle("active", content.id === `tab-${tabName}`);
  });

  if (tabName === "outputs") {
    fetchOutputs();
  } else if (tabName === "terminal") {
    refreshTerminalQueue();
  } else if (tabName === "watcher") {
    fetchSystemStatus();
  } else if (tabName === "profiles") {
    loadProfilesList();
  } else if (tabName === "system") {
    fetchSystemStatus();
    fetchKeystoreDetails();
    fetchPatchSources();
  }
}

let compatibleVersionsCache = {};
let activePatchesMeta = null;

async function fetchCompatibleVersions() {
  const container = document.getElementById("suggested-chips-container");
  const pill = document.getElementById("patches-version-pill");
  try {
    const res = await fetch("/api/patches/compatible-versions");
    if (!res.ok) {
      if (pill) pill.textContent = "Bundle: Offline";
      if (container) {
        container.innerHTML = `
          <div style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; color: var(--text-muted);">
            <span>⚠️ Could not load recommended versions.</span>
            <button onclick="fetchCompatibleVersions()" class="chip-find-btn" style="padding: 2px 8px; cursor: pointer;">Retry</button>
          </div>`;
      }
      return;
    }
    const data = await res.json();
    compatibleVersionsCache = data.packages || {};
    activePatchesMeta = data.meta || null;
    renderSuggestedVersionsGuide();
  } catch (e) {
    console.error("Failed to load compatible versions:", e);
    if (pill) pill.textContent = "Bundle: Offline";
    if (container) {
      container.innerHTML = `
        <div style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; color: var(--text-muted);">
          <span>⚠️ Could not load recommended versions.</span>
          <button onclick="fetchCompatibleVersions()" class="chip-find-btn" style="padding: 2px 8px; cursor: pointer;">Retry</button>
        </div>`;
    }
  }
}

function renderSuggestedVersionsGuide() {
  const container = document.getElementById("suggested-chips-container");
  const pill = document.getElementById("patches-version-pill");
  
  if (pill) {
    if (activePatchesMeta && activePatchesMeta.version) {
      pill.textContent = `Official Bundle (${activePatchesMeta.version})`;
      pill.title = `Morphe patches version ${activePatchesMeta.version}`;
    } else {
      pill.textContent = "Official Bundle";
    }
  }

  if (!container) return;

  const pkgs = Object.values(compatibleVersionsCache);
  if (pkgs.length === 0) {
    container.innerHTML = `<span style="font-size: 0.8rem; color: var(--text-muted);">No specific recommended versions found for active patch bundle.</span>`;
    return;
  }

  const icons = {
    "com.google.android.youtube": "🔴",
    "com.google.android.apps.youtube.music": "🎵",
    "com.reddit.frontpage": "🟠",
    "com.twitter.android": "🐦",
    "tv.twitch.android.app": "🟣",
    "com.spotify.music": "🟢",
  };

  container.innerHTML = pkgs.map(item => {
    const icon = icons[item.package_name] || "📱";
    const ver = item.recommended_version || "Latest";
    return `
      <div class="suggested-app-chip" title="Verified compatible with ${item.patch_count} patches">
        <span>${icon}</span>
        <span class="chip-app-name">${escapeHtml(item.app_name)}</span>
        <span class="chip-ver-badge">v${escapeHtml(ver)}</span>
        <a href="${item.apkmirror_url}" target="_blank" rel="noopener noreferrer" class="chip-find-btn" title="Search exact recommended version on APKMirror">
          🔍 APKMirror
        </a>
      </div>
    `;
  }).join("");
}

function setupPatchUpdateHandlers() {
  const btn = document.getElementById("btn-update-patches");
  const icon = document.getElementById("btn-update-icon");
  const text = document.getElementById("btn-update-text");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    if (icon) icon.textContent = "⏳";
    if (text) text.textContent = "Checking...";

    try {
      const checkRes = await fetch("/api/patches/check-update");
      const checkData = await checkRes.json();

      if (!checkData.has_update) {
        if (icon) icon.textContent = "✅";
        if (text) text.textContent = "Up to date!";
        showToast(`Official patches are already up to date (${checkData.current_version || 'Latest'}).`, "info");
        setTimeout(() => {
          if (icon) icon.textContent = "🔄";
          if (text) text.textContent = "Update Patches";
          btn.disabled = false;
        }, 3000);
        return;
      }

      // Update available!
      if (icon) icon.textContent = "⬇️";
      if (text) text.textContent = `Updating to ${checkData.latest_version}...`;
      showToast(`Downloading Morphe patches ${checkData.latest_version}...`, "info");

      const updateRes = await fetch("/api/patches/update-official", { method: "POST" });
      const updateData = await updateRes.json();

      if (!updateRes.ok) {
        throw new Error(updateData.detail || "Failed to update patches");
      }

      compatibleVersionsCache = updateData.packages || {};
      activePatchesMeta = { version: updateData.version };
      renderSuggestedVersionsGuide();

      if (icon) icon.textContent = "🎉";
      if (text) text.textContent = `Updated (${updateData.version})`;
      showToast(`Morphe patches successfully updated to ${updateData.version}!`, "success");

      setTimeout(() => {
        if (icon) icon.textContent = "🔄";
        if (text) text.textContent = "Update Patches";
        btn.disabled = false;
      }, 4000);

    } catch (err) {
      console.error("Patch update error:", err);
      showToast(`Update check failed: ${err.message}`, "error");
      if (icon) icon.textContent = "⚠️";
      if (text) text.textContent = "Retry Update";
      btn.disabled = false;
    }
  });
}

function setupUpload() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const btnChange = document.getElementById("btn-change-file");
  const btnAddToBatch = document.getElementById("btn-add-to-batch");
  const btnStart = document.getElementById("btn-start-patch");
  const brandingChoice = document.getElementById("branding-choice");
  const customAppName = document.getElementById("custom-app-name");
  const optArchToggle = document.getElementById("optimize-arch-toggle");
  const archSelectorGroup = document.getElementById("arch-selector-group");
  const outputNameInput = document.getElementById("output-name");

  // Input Mode Switcher
  const btnModeFile = document.getElementById("input-mode-file");
  const btnModeUrl = document.getElementById("input-mode-url");
  if (btnModeFile) btnModeFile.addEventListener("click", () => setInputMode("file"));
  if (btnModeUrl) btnModeUrl.addEventListener("click", () => setInputMode("url"));

  // URL Download
  const btnFetchUrl = document.getElementById("btn-fetch-url");
  const apkUrlInput = document.getElementById("apk-url-input");
  if (btnFetchUrl) btnFetchUrl.addEventListener("click", fetchApkFromUrl);
  if (apkUrlInput) {
    apkUrlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        fetchApkFromUrl();
      }
    });
  }

  // File Dropzone & Selection
  dropzone.addEventListener("click", () => fileInput.click());

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFilesSelected(e.target.files);
    }
  });

  btnChange.addEventListener("click", () => {
    resetUploadState();
    fileInput.click();
  });

  if (btnAddToBatch) {
    btnAddToBatch.addEventListener("click", () => {
      if (stagedApks.length > 0) {
        showBatchCard();
      }
    });
  }

  if (outputNameInput) {
    outputNameInput.addEventListener("input", () => {
      isFilenameManuallyEdited = true;
    });
  }

  if (brandingChoice) {
    brandingChoice.addEventListener("change", () => {
      if (brandingChoice.value === "custom") {
        customAppName.style.display = "block";
        customAppName.focus();
      } else {
        customAppName.style.display = "none";
      }
      updateSuggestedFilename();
    });
  }

  if (customAppName) {
    customAppName.addEventListener("input", () => {
      updateSuggestedFilename();
    });
  }

  if (optArchToggle) {
    optArchToggle.addEventListener("change", () => {
      if (optArchToggle.checked) {
        archSelectorGroup.style.opacity = "1";
        archSelectorGroup.style.pointerEvents = "auto";
      } else {
        archSelectorGroup.style.opacity = "0.45";
        archSelectorGroup.style.pointerEvents = "none";
      }
      updateSuggestedFilename();
    });
  }

  document.querySelectorAll('input[name="target-arch"]').forEach(radio => {
    radio.addEventListener("change", () => {
      updateSuggestedFilename();
    });
  });

  const patchSourceSelect = document.getElementById("patch-source-select");
  const customPatchesUrlWrap = document.getElementById("custom-patches-url-wrap");
  const patchSourceBadge = document.getElementById("patch-source-badge");

  if (patchSourceSelect) {
    patchSourceSelect.addEventListener("change", () => {
      const val = patchSourceSelect.value;
      if (val === "custom_url") {
        if (customPatchesUrlWrap) customPatchesUrlWrap.style.display = "block";
        if (patchSourceBadge) {
          patchSourceBadge.textContent = "Custom Remote";
          patchSourceBadge.style.color = "#f59e0b";
          patchSourceBadge.style.background = "rgba(245, 158, 11, 0.15)";
        }
      } else {
        if (customPatchesUrlWrap) customPatchesUrlWrap.style.display = "none";
        if (patchSourceBadge) {
          if (val === "default") {
            patchSourceBadge.textContent = "Official";
            patchSourceBadge.style.color = "#818cf8";
            patchSourceBadge.style.background = "rgba(99, 102, 241, 0.15)";
          } else {
            patchSourceBadge.textContent = "Community";
            patchSourceBadge.style.color = "#34d399";
            patchSourceBadge.style.background = "rgba(16, 185, 129, 0.15)";
          }
        }
      }
    });
  }

  const patchProfileSelect = document.getElementById("patch-profile");
  if (patchProfileSelect) {
    patchProfileSelect.addEventListener("change", (e) => {
      const selectedId = e.target.value;
      const found = currentAppProfiles.find(p => p.id === selectedId);
      applyProfileToUi(found || null);
    });
  }

  const btnQuickManageProfile = document.getElementById("btn-quick-manage-profile");
  if (btnQuickManageProfile) {
    btnQuickManageProfile.addEventListener("click", () => {
      switchTab("profiles");
      if (uploadedApkData) {
        openProfileModal({
          name: `${uploadedApkData.app_name || 'App'} Morphe`,
          package_name: uploadedApkData.package_name || "*",
          branding: "custom",
          custom_app_name: "{appName} Morphe",
          output_format: "{appName}_{version}_{arch}_patched.apk",
          optimize_arch: true,
          target_arch: "arm64-v8a",
          is_default: true,
        });
      }
    });
  }

  btnStart.addEventListener("click", startPatchJob);

  // Batch Controls
  setupBatchControls();
}

function setInputMode(mode) {
  const btnFile = document.getElementById("input-mode-file");
  const btnUrl = document.getElementById("input-mode-url");
  const dropzone = document.getElementById("dropzone");
  const urlCard = document.getElementById("url-download-card");

  if (mode === "url") {
    btnUrl?.classList.add("active");
    btnFile?.classList.remove("active");
    if (dropzone) dropzone.style.display = "none";
    if (urlCard) {
      urlCard.style.display = "block";
      document.getElementById("apk-url-input")?.focus();
    }
  } else {
    btnFile?.classList.add("active");
    btnUrl?.classList.remove("active");
    if (urlCard) urlCard.style.display = "none";
    if (stagedApks.length === 0) {
      if (dropzone) dropzone.style.display = "block";
    }
  }
}

async function fetchApkFromUrl() {
  const urlInput = document.getElementById("apk-url-input");
  const statusDiv = document.getElementById("url-download-status");
  const statusText = document.getElementById("url-status-text");
  const btn = document.getElementById("btn-fetch-url");
  const url = urlInput?.value.trim();

  if (!url) {
    alert("Please enter a valid APK download URL.");
    return;
  }
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    alert("URL must start with http:// or https://");
    return;
  }

  btn.disabled = true;
  statusDiv.style.display = "flex";
  statusText.textContent = "Downloading remote APK & analyzing package...";

  try {
    const res = await fetch("/api/upload/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Download failed");
    }

    const data = await res.json();
    urlInput.value = "";
    addApkToStaging(data);

  } catch (e) {
    alert(`URL Download Error: ${e.message}`);
  } finally {
    btn.disabled = false;
    statusDiv.style.display = "none";
  }
}

function handleFilesSelected(files) {
  const validFiles = Array.from(files).filter(f => f.name.toLowerCase().endsWith(".apk"));
  if (validFiles.length === 0) {
    alert("Please select valid Android .apk file(s).");
    return;
  }

  if (validFiles.length === 1) {
    uploadSingleFile(validFiles[0]);
  } else {
    uploadBatchFiles(validFiles);
  }
}

function uploadSingleFile(file) {
  const dropzone = document.getElementById("dropzone");
  const urlCard = document.getElementById("url-download-card");
  const progressContainer = document.getElementById("upload-progress-container");
  const progressFill = document.getElementById("upload-progress-fill");
  const uploadPct = document.getElementById("upload-pct");
  const uploadFilename = document.getElementById("upload-filename");

  dropzone.style.display = "none";
  if (urlCard) urlCard.style.display = "none";
  progressContainer.style.display = "block";
  uploadFilename.textContent = `Uploading ${file.name}...`;

  const formData = new FormData();
  formData.append("file", file);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload", true);

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      progressFill.style.width = `${pct}%`;
      uploadPct.textContent = `${pct}%`;
    }
  };

  xhr.onload = () => {
    progressContainer.style.display = "none";
    if (xhr.status === 200) {
      const data = JSON.parse(xhr.responseText);
      addApkToStaging(data);
    } else {
      alert(`Upload failed: ${xhr.responseText}`);
      resetUploadState();
    }
  };

  xhr.onerror = () => {
    progressContainer.style.display = "none";
    alert("Upload failed due to a network error.");
    resetUploadState();
  };

  xhr.send(formData);
}

function uploadBatchFiles(files) {
  const dropzone = document.getElementById("dropzone");
  const urlCard = document.getElementById("url-download-card");
  const progressContainer = document.getElementById("upload-progress-container");
  const progressFill = document.getElementById("upload-progress-fill");
  const uploadPct = document.getElementById("upload-pct");
  const uploadFilename = document.getElementById("upload-filename");

  dropzone.style.display = "none";
  if (urlCard) urlCard.style.display = "none";
  progressContainer.style.display = "block";
  uploadFilename.textContent = `Uploading batch of ${files.length} APKs...`;

  const formData = new FormData();
  for (const f of files) {
    formData.append("files", f);
  }

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload/batch", true);

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      progressFill.style.width = `${pct}%`;
      uploadPct.textContent = `${pct}%`;
    }
  };

  xhr.onload = () => {
    progressContainer.style.display = "none";
    if (xhr.status === 200) {
      const res = JSON.parse(xhr.responseText);
      if (res.results && res.results.length > 0) {
        res.results.forEach(meta => addApkToStaging(meta, false));
        showBatchCard();
      }
      if (res.errors && res.errors.length > 0) {
        const errMsgs = res.errors.map(e => `${e.file_name}: ${e.error}`).join("\n");
        alert(`Some files could not be processed:\n${errMsgs}`);
      }
    } else {
      alert(`Batch upload failed: ${xhr.responseText}`);
      resetUploadState();
    }
  };

  xhr.onerror = () => {
    progressContainer.style.display = "none";
    alert("Batch upload failed due to a network error.");
    resetUploadState();
  };

  xhr.send(formData);
}

function createStagedApk(data) {
  const cleanName = (data.app_name || "app").toLowerCase().replace(/[^a-z0-9]/g, "_");
  const ver = data.version_name ? `_${data.version_name}` : "";
  const defaultArch = "arm64-v8a";
  const defaultFilename = `${cleanName}${ver}_arm64_patched.apk`;

  return {
    id: "apk_" + Date.now() + "_" + Math.random().toString(36).substr(2, 5),
    temp_path: data.temp_path,
    file_name: data.file_name,
    app_name: data.app_name || "Unknown App",
    package_name: data.package_name || "",
    version_name: data.version_name || "",
    file_size_human: data.file_size_human || "",
    icon_base64: data.icon_base64,
    compatibility: data.compatibility,
    branding: "original",
    custom_app_name: "",
    optimize_arch: true,
    target_arch: defaultArch,
    output_filename: defaultFilename,
    patch_source: "default",
  };
}

function addApkToStaging(data, autoSwitchView = true) {
  const exists = stagedApks.some(a => a.temp_path === data.temp_path);
  if (!exists) {
    const item = createStagedApk(data);
    stagedApks.push(item);
  }

  if (autoSwitchView) {
    if (stagedApks.length === 1) {
      uploadedApkData = stagedApks[0];
      showAppCard(stagedApks[0]);
    } else {
      showBatchCard();
    }
  }
}

function showAppCard(data) {
  uploadedApkData = data;
  isFilenameManuallyEdited = false;
  const appCard = document.getElementById("app-card");
  const batchCard = document.getElementById("batch-card");
  const appIcon = document.getElementById("app-icon");
  const appName = document.getElementById("app-name");
  const appPkg = document.getElementById("app-pkg");
  const appVersion = document.getElementById("app-version");
  const appSize = document.getElementById("app-size");
  const optionsArea = document.getElementById("patch-options-area");
  const brandingChoice = document.getElementById("branding-choice");
  const customAppName = document.getElementById("custom-app-name");
  const dropzone = document.getElementById("dropzone");
  const urlCard = document.getElementById("url-download-card");
  const compatBanner = document.getElementById("compat-banner");

  if (dropzone) dropzone.style.display = "none";
  if (urlCard) urlCard.style.display = "none";
  if (batchCard) batchCard.style.display = "none";

  appIcon.src = data.icon_base64 || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 24 24' fill='none' stroke='%236366f1' stroke-width='2'%3E%3Crect x='4' y='4' width='16' height='16' rx='2'/%3E%3Cpath d='M9 9h6v6H9z'/%3E%3C/svg%3E";
  appName.textContent = data.app_name || "Unknown Application";
  appPkg.textContent = data.package_name || "Unknown Package";
  appVersion.textContent = data.version_name ? `v${data.version_name}` : "Unknown Version";
  appSize.textContent = data.file_size_human || "";

  // Compatibility Banner
  if (compatBanner) {
    const comp = data.compatibility;
    if (comp && comp.status && comp.status !== "UNKNOWN") {
      let icon = "✅";
      let bannerClass = "compat-banner recommended";
      let actionHtml = "";

      if (comp.status === "RECOMMENDED") {
        icon = "✅";
        bannerClass = "compat-banner recommended";
      } else if (comp.status === "COMPATIBLE") {
        icon = "ℹ️";
        bannerClass = "compat-banner compatible";
        if (comp.apkmirror_url) {
          actionHtml = `<a href="${comp.apkmirror_url}" target="_blank" rel="noopener noreferrer" class="compat-action-btn">🔍 Get Target (v${comp.recommended_version})</a>`;
        }
      } else if (comp.status === "EXPERIMENTAL") {
        icon = "⚠️";
        bannerClass = "compat-banner experimental";
        if (comp.apkmirror_url) {
          actionHtml = `<a href="${comp.apkmirror_url}" target="_blank" rel="noopener noreferrer" class="compat-action-btn">🔍 Get Stable (v${comp.recommended_version})</a>`;
        }
      } else if (comp.status === "UNTESTED") {
        icon = "⚠️";
        bannerClass = "compat-banner untested";
        if (comp.apkmirror_url) {
          actionHtml = `<a href="${comp.apkmirror_url}" target="_blank" rel="noopener noreferrer" class="compat-action-btn">🔍 Get Tested (v${comp.recommended_version})</a>`;
        }
      }

      compatBanner.className = bannerClass;
      compatBanner.innerHTML = `
        <div class="compat-content">
          <span class="compat-icon">${icon}</span>
          <div>
            <div class="compat-title">${escapeHtml(comp.badge_text)}</div>
            <div class="compat-desc">${escapeHtml(comp.message)}</div>
          </div>
        </div>
        ${actionHtml}
      `;
      compatBanner.style.display = "flex";
    } else {
      compatBanner.style.display = "none";
    }
  }

  if (brandingChoice) {
    const stockOpt = brandingChoice.querySelector('option[value="original"]');
    if (stockOpt) {
      stockOpt.textContent = `🔴 Original Stock (Keep "${data.app_name || 'Stock'}" & Stock Icon)`;
    }
  }

  loadAndSelectProfileForApp(data.package_name, data.app_name);

  appCard.style.display = "flex";
  optionsArea.style.display = "block";
}

function updateSuggestedFilename(force = false) {
  if (!uploadedApkData) return;
  const outputNameInput = document.getElementById("output-name");
  if (!outputNameInput) return;
  if (!force && isFilenameManuallyEdited) return;

  const cleanName = (uploadedApkData.app_name || "app").toLowerCase().replace(/[^a-z0-9]/g, "_");
  const ver = uploadedApkData.version_name ? `_${uploadedApkData.version_name}` : "";
  const optimizeArch = document.getElementById("optimize-arch-toggle")?.checked ?? true;
  const selectedArch = document.querySelector('input[name="target-arch"]:checked')?.value || "arm64-v8a";

  let archTag = "";
  if (optimizeArch) {
    archTag = selectedArch === "armeabi-v7a" ? "_arm32" : "_arm64";
  } else {
    archTag = "_universal";
  }

  outputNameInput.value = `${cleanName}${ver}${archTag}_patched.apk`;
}

function setupBatchControls() {
  const btnBatchAddFile = document.getElementById("btn-batch-add-file");
  const btnBatchAddUrl = document.getElementById("btn-batch-add-url");
  const btnBatchClear = document.getElementById("btn-batch-clear");
  const btnStartBatch = document.getElementById("btn-start-batch");
  const fileInput = document.getElementById("file-input");

  const batchArchSelect = document.getElementById("batch-arch-select");
  const batchBrandingSelect = document.getElementById("batch-branding-select");
  const batchPatchSourceSelect = document.getElementById("batch-patch-source-select");

  if (btnBatchAddFile) {
    btnBatchAddFile.addEventListener("click", () => fileInput?.click());
  }

  if (btnBatchAddUrl) {
    btnBatchAddUrl.addEventListener("click", () => {
      setInputMode("url");
      const urlCard = document.getElementById("url-download-card");
      if (urlCard) {
        urlCard.scrollIntoView({ behavior: "smooth" });
      }
    });
  }

  if (btnBatchClear) {
    btnBatchClear.addEventListener("click", () => {
      if (confirm("Clear all staged APKs from the batch queue?")) {
        resetUploadState();
      }
    });
  }

  if (batchArchSelect) {
    batchArchSelect.addEventListener("change", () => {
      const archVal = batchArchSelect.value;
      stagedApks.forEach(item => {
        if (archVal === "universal") {
          item.optimize_arch = false;
        } else {
          item.optimize_arch = true;
          item.target_arch = archVal;
        }
        const cleanName = (item.app_name || "app").toLowerCase().replace(/[^a-z0-9]/g, "_");
        const ver = item.version_name ? `_${item.version_name}` : "";
        const tag = archVal === "armeabi-v7a" ? "_arm32" : (archVal === "universal" ? "_universal" : "_arm64");
        item.output_filename = `${cleanName}${ver}${tag}_patched.apk`;
      });
      renderBatchItems();
    });
  }

  if (batchBrandingSelect) {
    batchBrandingSelect.addEventListener("change", () => {
      const brandVal = batchBrandingSelect.value;
      stagedApks.forEach(item => {
        item.branding = brandVal;
      });
      renderBatchItems();
    });
  }

  if (batchPatchSourceSelect) {
    batchPatchSourceSelect.addEventListener("change", () => {
      const patchVal = batchPatchSourceSelect.value;
      stagedApks.forEach(item => {
        item.patch_source = patchVal;
      });
    });
  }

  if (btnStartBatch) {
    btnStartBatch.addEventListener("click", startBatchPatchJobs);
  }
}

function showBatchCard() {
  const dropzone = document.getElementById("dropzone");
  const appCard = document.getElementById("app-card");
  const optionsArea = document.getElementById("patch-options-area");
  const batchCard = document.getElementById("batch-card");
  const batchCount = document.getElementById("batch-count");
  const btnBatchCount = document.getElementById("btn-batch-count");

  if (dropzone) dropzone.style.display = "none";
  if (appCard) appCard.style.display = "none";
  if (optionsArea) optionsArea.style.display = "none";

  if (batchCount) batchCount.textContent = stagedApks.length;
  if (btnBatchCount) btnBatchCount.textContent = stagedApks.length;

  renderBatchItems();
  if (batchCard) batchCard.style.display = "block";
}

function renderBatchItems() {
  const container = document.getElementById("batch-items-container");
  if (!container) return;

  if (stagedApks.length === 0) {
    resetUploadState();
    return;
  }

  const defaultSvg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='44' height='44' viewBox='0 0 24 24' fill='none' stroke='%236366f1' stroke-width='2'%3E%3Crect x='4' y='4' width='16' height='16' rx='2'/%3E%3Cpath d='M9 9h6v6H9z'/%3E%3C/svg%3E";

  container.innerHTML = stagedApks.map((item, idx) => {
    const archTag = !item.optimize_arch || item.target_arch === "universal" 
      ? '<span class="badge" style="background: #374151;">Universal</span>'
      : (item.target_arch === "armeabi-v7a"
        ? '<span class="badge" style="background: #065f46; color: #34d399;">ARM32 (-50%)</span>'
        : '<span class="badge" style="background: #065f46; color: #34d399;">ARM64 (-50%)</span>');

    const brandTag = item.branding === "original"
      ? '<span class="badge" style="background: #7f1d1d; color: #fca5a5;">🔴 Stock Brand</span>'
      : '<span class="badge" style="background: #581c87; color: #d8b4fe;">🟣 Morphe Brand</span>';

    let compatTag = "";
    if (item.compatibility) {
      if (item.compatibility.status === "RECOMMENDED") {
        compatTag = `<span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399;" title="${escapeHtml(item.compatibility.message)}">✅ Target</span>`;
      } else if (item.compatibility.status === "COMPATIBLE") {
        compatTag = `<span class="badge" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa;" title="${escapeHtml(item.compatibility.message)}">ℹ️ Compatible</span>`;
      } else if (item.compatibility.status === "EXPERIMENTAL") {
        compatTag = `<span class="badge" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24;" title="${escapeHtml(item.compatibility.message)}">⚠️ Experimental</span>`;
      } else if (item.compatibility.status === "UNTESTED") {
        compatTag = `<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171;" title="${escapeHtml(item.compatibility.message)}">⚠️ Untested (Rec: v${escapeHtml(item.compatibility.recommended_version || '?')})</span>`;
      }
    }

    return `
      <div class="batch-item-row" data-id="${item.id}">
        <div class="batch-item-info">
          <img class="batch-item-icon" src="${item.icon_base64 || defaultSvg}" alt="Icon">
          <div>
            <div style="font-weight: 700; font-size: 0.95rem; color: var(--text-main);">
              #${idx + 1}. ${escapeHtml(item.app_name)}
            </div>
            <div style="font-size: 0.78rem; color: var(--text-muted); font-family: monospace;">
              ${escapeHtml(item.package_name || item.file_name)}
            </div>
            <div style="display: flex; gap: 0.4rem; margin-top: 0.35rem; align-items: center; flex-wrap: wrap;">
              <span class="badge">${item.version_name ? 'v' + escapeHtml(item.version_name) : 'APK'}</span>
              <span class="badge">${escapeHtml(item.file_size_human)}</span>
              ${archTag}
              ${brandTag}
              ${compatTag}
            </div>
          </div>
        </div>
        <div class="batch-item-options">
          <div style="display: flex; flex-direction: column; gap: 0.25rem;">
            <span style="font-size: 0.75rem; color: var(--text-muted);">Output APK Filename:</span>
            <input type="text" class="form-control batch-out-name" data-id="${item.id}" value="${escapeHtml(item.output_filename)}" style="width: 280px; font-size: 0.82rem; padding: 0.4rem 0.65rem;">
          </div>
          <button type="button" class="batch-remove-btn" data-id="${item.id}" title="Remove from batch">🗑️</button>
        </div>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".batch-out-name").forEach(input => {
    input.addEventListener("input", (e) => {
      const id = e.target.dataset.id;
      const targetItem = stagedApks.find(a => a.id === id);
      if (targetItem) {
        targetItem.output_filename = e.target.value.trim();
      }
    });
  });

  container.querySelectorAll(".batch-remove-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      stagedApks = stagedApks.filter(a => a.id !== id);
      const batchCount = document.getElementById("batch-count");
      const btnBatchCount = document.getElementById("btn-batch-count");
      if (batchCount) batchCount.textContent = stagedApks.length;
      if (btnBatchCount) btnBatchCount.textContent = stagedApks.length;

      if (stagedApks.length === 0) {
        resetUploadState();
      } else if (stagedApks.length === 1) {
        uploadedApkData = stagedApks[0];
        showAppCard(stagedApks[0]);
      } else {
        renderBatchItems();
      }
    });
  });
}

function resetUploadState() {
  stagedApks = [];
  uploadedApkData = null;
  isFilenameManuallyEdited = false;
  document.getElementById("dropzone").style.display = "block";
  document.getElementById("upload-progress-container").style.display = "none";
  document.getElementById("app-card").style.display = "none";
  document.getElementById("patch-options-area").style.display = "none";
  document.getElementById("batch-card").style.display = "none";
  document.getElementById("file-input").value = "";

  const compatBanner = document.getElementById("compat-banner");
  if (compatBanner) {
    compatBanner.style.display = "none";
    compatBanner.innerHTML = "";
  }

  const customAppName = document.getElementById("custom-app-name");
  if (customAppName) {
    customAppName.style.display = "none";
    customAppName.value = "";
  }
}

async function startPatchJob() {
  if (!uploadedApkData || !uploadedApkData.temp_path) {
    alert("Please upload an APK first.");
    return;
  }

  const outputName = document.getElementById("output-name").value.trim() || undefined;
  const profileName = document.getElementById("patch-profile").value || undefined;
  const branding = document.getElementById("branding-choice")?.value || "original";
  const customAppNameVal = document.getElementById("custom-app-name")?.value.trim() || undefined;
  const optimizeArch = document.getElementById("optimize-arch-toggle")?.checked ?? true;
  const selectedArch = document.querySelector('input[name="target-arch"]:checked')?.value || "arm64-v8a";
  const stripLibs = optimizeArch ? selectedArch : undefined;
  const patchSource = document.getElementById("patch-source-select")?.value || "default";
  const customPatchesUrl = document.getElementById("custom-patches-url-input")?.value.trim() || undefined;

  const payload = {
    file_path: uploadedApkData.temp_path,
    output_filename: outputName,
    package_name: uploadedApkData.package_name,
    version_name: uploadedApkData.version_name,
    profile_name: profileName,
    branding: branding,
    custom_app_name: customAppNameVal,
    strip_libs: stripLibs,
    patch_source: patchSource,
    custom_patches_url: customPatchesUrl,
  };

  try {
    const res = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to start job");
    }

    const job = await res.json();
    currentJobId = job.id;
    stagedApks = [];

    switchTab("terminal");
    startLogStream(job.id);
    refreshTerminalQueue();

  } catch (e) {
    alert(`Error: ${e.message}`);
  }
}

async function startBatchPatchJobs() {
  if (stagedApks.length === 0) {
    alert("No APKs in the batch queue.");
    return;
  }

  const btnStartBatch = document.getElementById("btn-start-batch");
  if (btnStartBatch) btnStartBatch.disabled = true;

  const jobsPayload = stagedApks.map(apk => {
    const stripLibs = apk.optimize_arch && apk.target_arch !== "universal" ? apk.target_arch : undefined;
    return {
      file_path: apk.temp_path,
      output_filename: apk.output_filename,
      package_name: apk.package_name,
      version_name: apk.version_name,
      strip_libs: stripLibs,
      branding: apk.branding,
      custom_app_name: apk.custom_app_name || undefined,
      patch_source: apk.patch_source || "default",
    };
  });

  try {
    const res = await fetch("/api/jobs/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobs: jobsPayload }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to launch batch jobs");
    }

    const createdJobs = await res.json();
    stagedApks = [];
    resetUploadState();

    switchTab("terminal");
    if (createdJobs.length > 0) {
      currentJobId = createdJobs[0].id;
      startLogStream(createdJobs[0].id);
    }
    refreshTerminalQueue();

  } catch (e) {
    alert(`Batch Launch Error: ${e.message}`);
  } finally {
    if (btnStartBatch) btnStartBatch.disabled = false;
  }
}

function startLogStream(jobId) {
  if (eventSource) {
    eventSource.close();
  }

  const terminal = document.getElementById("terminal-output");
  terminal.innerHTML = "";
  document.getElementById("btn-cancel-job").style.display = "inline-flex";

  eventSource = new EventSource(`/api/jobs/${jobId}/stream`);

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      handleStreamMessage(data);
    } catch (err) {
      console.error("Error parsing SSE data", err);
    }
  };

  eventSource.onerror = (e) => {
    console.warn("SSE stream disconnected or ended.");
    eventSource?.close();
    eventSource = null;
    document.getElementById("btn-cancel-job").style.display = "none";
  };
}

function handleStreamMessage(data) {
  const terminal = document.getElementById("terminal-output");
  const termStatus = document.getElementById("term-status-text");
  const termPhase = document.getElementById("term-phase-text");
  const termPct = document.getElementById("term-pct-text");
  const termProgress = document.getElementById("term-progress-fill");
  const autoscroll = document.getElementById("autoscroll-toggle").checked;

  if (data.type === "log") {
    const div = document.createElement("div");
    div.className = "log-line";
    const line = data.line;
    if (line.includes("[SUCCESS]") || line.includes("completed successfully")) {
      div.className += " log-success";
    } else if (line.includes("[ERROR]") || line.includes("[EXCEPTION]")) {
      div.className += " log-error";
    } else if (line.includes("[INFO]")) {
      div.className += " log-info";
    }
    div.textContent = line;
    terminal.appendChild(div);

    if (autoscroll) {
      terminal.scrollTop = terminal.scrollHeight;
    }
  }

  if (data.status) termStatus.textContent = data.status;
  if (data.phase) termPhase.textContent = data.phase;
  if (data.progress !== undefined) {
    termPct.textContent = `${data.progress}%`;
    termProgress.style.width = `${data.progress}%`;
  }

  if (data.type === "finished" || data.status === "COMPLETED" || data.status === "FAILED") {
    document.getElementById("btn-cancel-job").style.display = "none";
    fetchOutputs();
    fetchSystemStatus();
    refreshTerminalQueue();

    if (data.status === "COMPLETED") {
      setTimeout(async () => {
        try {
          const res = await fetch("/api/jobs");
          if (!res.ok) return;
          const jobs = await res.json();
          const nextRunning = jobs.find(j => j.status === "RUNNING");
          if (nextRunning && nextRunning.id !== currentJobId) {
            currentJobId = nextRunning.id;
            startLogStream(nextRunning.id);
            refreshTerminalQueue();
          }
        } catch (e) {
          console.error("Auto-advance error:", e);
        }
      }, 1500);
    }
  }
}

async function refreshTerminalQueue() {
  try {
    const res = await fetch("/api/jobs");
    if (!res.ok) return;
    const jobs = await res.json();
    renderTerminalQueue(jobs);
  } catch (e) {
    console.error("Failed to fetch jobs for queue tracker:", e);
  }
}

function renderTerminalQueue(jobs) {
  const bar = document.getElementById("term-queue-bar");
  const countEl = document.getElementById("term-queue-count");
  const chipsContainer = document.getElementById("term-queue-chips");
  if (!bar || !chipsContainer) return;

  if (!jobs || jobs.length === 0) {
    bar.style.display = "none";
    return;
  }

  const activeJobs = jobs.filter(j => j.status === "RUNNING" || j.status === "QUEUED");
  if (activeJobs.length === 0 && !currentJobId) {
    bar.style.display = "none";
    return;
  }

  bar.style.display = "block";
  if (countEl) {
    countEl.textContent = `${activeJobs.length} active`;
  }

  chipsContainer.innerHTML = jobs.slice(0, 10).map((job, idx) => {
    let chipClass = "queue-chip";
    let statusBadge = job.status;

    if (job.status === "RUNNING") {
      chipClass += " running";
      statusBadge = `Running (${job.progress}%)`;
    } else if (job.status === "QUEUED") {
      chipClass += " queued";
      statusBadge = "Queued";
    } else if (job.status === "COMPLETED") {
      chipClass += " completed";
      statusBadge = "Done";
    } else if (job.status === "FAILED") {
      chipClass += " failed";
      statusBadge = "Failed";
    }

    if (job.id === currentJobId) {
      chipClass += " selected";
    }

    const appTitle = job.package_name && job.package_name !== "Unknown" 
      ? job.package_name.split('.').pop()
      : job.input_filename.replace(/\.apk$/i, '');

    return `
      <div class="${chipClass}" data-job-id="${job.id}" title="Click to view log stream">
        <span class="chip-dot"></span>
        <span><strong>${escapeHtml(appTitle)}</strong> <span style="font-size: 0.75rem; color: var(--text-muted);">${statusBadge}</span></span>
      </div>
    `;
  }).join("");

  chipsContainer.querySelectorAll(".queue-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const jid = chip.dataset.jobId;
      if (jid && jid !== currentJobId) {
        currentJobId = jid;
        startLogStream(jid);
        renderTerminalQueue(jobs);
      }
    });
  });
}

function setupTerminalControls() {
  document.getElementById("btn-copy-logs").addEventListener("click", () => {
    const text = document.getElementById("terminal-output").innerText;
    navigator.clipboard.writeText(text).then(() => alert("Logs copied to clipboard."));
  });

  document.getElementById("btn-cancel-job").addEventListener("click", async () => {
    if (!currentJobId) return;
    if (!confirm("Are you sure you want to cancel the current patching process?")) return;

    try {
      await fetch(`/api/jobs/${currentJobId}/cancel`, { method: "POST" });
    } catch (e) {
      alert(`Failed to cancel: ${e}`);
    }
  });
}

function setupOutputs() {
  document.getElementById("btn-refresh-outputs").addEventListener("click", fetchOutputs);
}

async function fetchOutputs() {
  try {
    const res = await fetch("/api/files/output");
    if (!res.ok) return;
    const files = await res.json();
    renderOutputsTable(files);
  } catch (e) {
    console.error("Failed to fetch outputs:", e);
  }
}

function renderOutputsTable(files) {
  const tbody = document.getElementById("outputs-tbody");
  const countSpan = document.getElementById("output-count");
  countSpan.textContent = files.length;

  if (files.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No patched APKs yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  files.forEach(f => {
    const tr = document.createElement("tr");
    const fullDownloadUrl = `${window.location.origin}${f.download_url}`;

    tr.innerHTML = `
      <td>
        <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(f.filename)}</div>
      </td>
      <td><span class="badge">${f.size_human}</span></td>
      <td style="color: var(--text-muted); font-size: 0.85rem;">${f.modified_human}</td>
      <td>
        <div style="display: flex; gap: 0.5rem; align-items: center;">
          <a href="${f.download_url}" download class="btn" style="padding: 0.35rem 0.75rem; font-size: 0.8rem; text-decoration: none;">
            Download
          </a>
          <button class="btn btn-secondary btn-copy-link" data-url="${fullDownloadUrl}" style="padding: 0.35rem 0.65rem; font-size: 0.8rem;" title="Copy Download Link">
            📋 Copy Link
          </button>
          <button class="btn btn-danger btn-del" data-name="${escapeHtml(f.filename)}" style="padding: 0.35rem 0.6rem; font-size: 0.8rem;" title="Delete APK">
            🗑️
          </button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });

  document.querySelectorAll(".btn-copy-link").forEach(btn => {
    btn.addEventListener("click", () => {
      navigator.clipboard.writeText(btn.dataset.url).then(() => {
        const origText = btn.textContent;
        btn.textContent = "✅ Copied!";
        setTimeout(() => { btn.textContent = origText; }, 2000);
      });
    });
  });

  document.querySelectorAll(".btn-del").forEach(btn => {
    btn.addEventListener("click", async () => {
      const name = btn.dataset.name;
      if (confirm(`Delete ${name}?`)) {
        await fetch(`/api/files/output/${encodeURIComponent(name)}`, { method: "DELETE" });
        fetchOutputs();
      }
    });
  });
}

function setupSystem() {
  // 1. Official patches update button
  const btnUpdatePatches = document.getElementById("btn-update-patches");
  if (btnUpdatePatches) {
    btnUpdatePatches.addEventListener("click", async () => {
      btnUpdatePatches.textContent = "Updating...";
      btnUpdatePatches.disabled = true;
      try {
        const res = await fetch("/api/system/update-patches", { method: "POST" });
        const data = await res.json();
        alert(data.message || "Patches updated successfully.");
        fetchSystemStatus();
        fetchPatchSources();
      } catch (e) {
        alert(`Update failed: ${e}`);
      } finally {
        btnUpdatePatches.textContent = "🔄 Update Official Patches (.mpp)";
        btnUpdatePatches.disabled = false;
      }
    });
  }

  // 2. Keystore Upload Form
  const formUploadKeystore = document.getElementById("form-upload-keystore");
  if (formUploadKeystore) {
    formUploadKeystore.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fileInput = document.getElementById("keystore-file-input");
      const passInput = document.getElementById("keystore-storepass-input");
      const aliasInput = document.getElementById("keystore-alias-input");
      const keypassInput = document.getElementById("keystore-keypass-input");
      const alertBox = document.getElementById("keystore-upload-alert");
      const submitBtn = document.getElementById("btn-submit-keystore");

      if (!fileInput.files || fileInput.files.length === 0) {
        alert("Please select a keystore file.");
        return;
      }

      const formData = new FormData();
      formData.append("file", fileInput.files[0]);
      formData.append("password", passInput.value);
      if (aliasInput.value.trim()) formData.append("alias", aliasInput.value.trim());
      if (keypassInput.value.trim()) formData.append("key_password", keypassInput.value.trim());

      submitBtn.disabled = true;
      submitBtn.textContent = "Verifying & Activating...";
      alertBox.style.display = "none";

      try {
        const res = await fetch("/api/keystore/upload", {
          method: "POST",
          body: formData,
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Failed to activate keystore.");
        }

        alertBox.style.display = "block";
        alertBox.style.background = "rgba(16, 185, 129, 0.15)";
        alertBox.style.color = "#34d399";
        alertBox.style.border = "1px solid #10b981";
        alertBox.textContent = `✓ Success: Custom keystore activated! Active alias: ${data.keystore.alias}. All future builds will be signed with this keystore.`;

        fileInput.value = "";
        passInput.value = "";
        aliasInput.value = "";
        keypassInput.value = "";

        fetchKeystoreDetails();
      } catch (err) {
        alertBox.style.display = "block";
        alertBox.style.background = "rgba(239, 68, 68, 0.15)";
        alertBox.style.color = "#f87171";
        alertBox.style.border = "1px solid #ef4444";
        alertBox.textContent = `✗ Keystore Verification Failed: ${err.message}`;
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "🔐 Verify & Activate Custom Keystore";
      }
    });
  }

  // 3. Reset Keystore Button
  const btnResetKeystore = document.getElementById("btn-reset-keystore");
  if (btnResetKeystore) {
    btnResetKeystore.addEventListener("click", async () => {
      if (confirm("Reset signing keystore back to default auto-generated keystore?")) {
        try {
          const res = await fetch("/api/keystore/reset", { method: "POST" });
          const data = await res.json();
          alert(data.message || "Reset to default keystore.");
          fetchKeystoreDetails();
        } catch (err) {
          alert(`Failed to reset keystore: ${err}`);
        }
      }
    });
  }

  // 4. Upload Community .mpp Bundle
  const btnUploadPatchBundle = document.getElementById("btn-upload-patch-bundle");
  if (btnUploadPatchBundle) {
    btnUploadPatchBundle.addEventListener("click", async () => {
      const fileInput = document.getElementById("patch-file-input");
      if (!fileInput.files || fileInput.files.length === 0) {
        alert("Please select a .mpp file to upload.");
        return;
      }

      const formData = new FormData();
      formData.append("file", fileInput.files[0]);

      btnUploadPatchBundle.disabled = true;
      btnUploadPatchBundle.textContent = "Uploading...";

      try {
        const res = await fetch("/api/patches/upload", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Upload failed");

        alert(data.message || "Patch bundle uploaded successfully!");
        fileInput.value = "";
        fetchPatchSources();
      } catch (e) {
        alert(`Error: ${e.message}`);
      } finally {
        btnUploadPatchBundle.disabled = false;
        btnUploadPatchBundle.textContent = "📤 Upload .mpp Bundle";
      }
    });
  }

  // 5. Download .mpp from URL
  const btnDownloadPatchUrl = document.getElementById("btn-download-patch-url");
  if (btnDownloadPatchUrl) {
    btnDownloadPatchUrl.addEventListener("click", async () => {
      const urlInput = document.getElementById("patch-url-input");
      const url = urlInput.value.trim();
      if (!url) {
        alert("Please enter a valid .mpp URL.");
        return;
      }

      btnDownloadPatchUrl.disabled = true;
      btnDownloadPatchUrl.textContent = "Downloading...";

      try {
        const res = await fetch("/api/patches/download-url", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: url }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Download failed");

        alert(data.message || "Patch bundle downloaded!");
        urlInput.value = "";
        fetchPatchSources();
      } catch (e) {
        alert(`Error: ${e.message}`);
      } finally {
        btnDownloadPatchUrl.disabled = false;
        btnDownloadPatchUrl.textContent = "🌐 Download to Server";
      }
    });
  }
}

async function fetchKeystoreDetails() {
  try {
    const res = await fetch("/api/keystore");
    if (!res.ok) return;
    const ks = await res.json();

    const badge = document.getElementById("keystore-badge");
    const filenameEl = document.getElementById("keystore-filename");
    const tag = document.getElementById("keystore-type-tag");
    const aliasEl = document.getElementById("keystore-alias");
    const sha256El = document.getElementById("keystore-sha256");
    const validityEl = document.getElementById("keystore-validity");

    if (ks.is_custom) {
      if (badge) {
        badge.textContent = "Custom Active";
        badge.style.background = "rgba(16, 185, 129, 0.2)";
        badge.style.color = "#34d399";
      }
      if (tag) {
        tag.textContent = "User Custom";
        tag.style.background = "#065f46";
        tag.style.color = "#34d399";
      }
    } else {
      if (badge) {
        badge.textContent = "Default Active";
        badge.style.background = "rgba(99, 102, 241, 0.2)";
        badge.style.color = "#818cf8";
      }
      if (tag) {
        tag.textContent = "Default Auto-Generated";
        tag.style.background = "#312e81";
        tag.style.color = "#a5b4fc";
      }
    }

    if (filenameEl) filenameEl.textContent = ks.filename || "morphe.keystore";
    if (aliasEl) aliasEl.textContent = ks.alias || "morphe";
    if (sha256El) sha256El.textContent = ks.sha256 || "Valid (Registered)";
    if (validityEl) validityEl.textContent = ks.validity || "Permanent";

  } catch (e) {
    console.error("Failed to fetch keystore details:", e);
  }
}

async function fetchPatchSources() {
  try {
    const res = await fetch("/api/patches/sources");
    if (!res.ok) return;
    const data = await res.json();

    const selectEl = document.getElementById("patch-source-select");
    const currentVal = selectEl ? selectEl.value : "default";

    if (selectEl) {
      selectEl.innerHTML = "";
      data.sources.forEach(src => {
        const opt = document.createElement("option");
        opt.value = src.id;
        opt.textContent = src.name;
        if (src.id === currentVal) opt.selected = true;
        selectEl.appendChild(opt);
      });

      const urlOpt = document.createElement("option");
      urlOpt.value = "custom_url";
      urlOpt.textContent = "🌐 Custom Remote URL / GitHub Repository...";
      if (currentVal === "custom_url") urlOpt.selected = true;
      selectEl.appendChild(urlOpt);
    }

    const tbody = document.getElementById("patches-sources-tbody");
    if (tbody) {
      if (!data.sources || data.sources.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No patch bundles found.</td></tr>`;
        return;
      }

      tbody.innerHTML = data.sources.map(s => {
        const isDef = s.is_default;
        const typeBadge = isDef
          ? `<span class="badge" style="background: rgba(99, 102, 241, 0.2); color: #818cf8;">Official</span>`
          : `<span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">Community</span>`;

        const actionBtn = isDef
          ? `<span style="color: var(--text-muted); font-size: 0.8rem;">Protected</span>`
          : `<button class="btn btn-danger btn-del-patch" data-filename="${escapeHtml(s.filename)}" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;">Delete</button>`;

        return `
          <tr>
            <td style="font-weight: 600;">${escapeHtml(s.name)}</td>
            <td><code style="font-size: 0.8rem;">${escapeHtml(s.filename)}</code></td>
            <td><span class="badge">${s.size_human}</span></td>
            <td>${typeBadge}</td>
            <td>${actionBtn}</td>
          </tr>
        `;
      }).join("");

      document.querySelectorAll(".btn-del-patch").forEach(btn => {
        btn.addEventListener("click", async () => {
          const fn = btn.dataset.filename;
          if (confirm(`Delete patch bundle ${fn}?`)) {
            await fetch(`/api/patches/sources/${encodeURIComponent(fn)}`, { method: "DELETE" });
            fetchPatchSources();
          }
        });
      });
    }

    fetchCompatibleVersions();

  } catch (e) {
    console.error("Failed to fetch patch sources:", e);
  }
}

async function fetchSystemStatus() {
  try {
    const res = await fetch("/api/system/status");
    if (!res.ok) return;
    const data = await res.json();

    const q = data.queue;
    const headerQueue = document.getElementById("header-queue-status");
    if (q.active_job) {
      headerQueue.textContent = `Queue: 1 Active (${q.active_job.package_name})`;
      headerQueue.style.color = "var(--accent)";
    } else {
      headerQueue.textContent = "Queue: Idle";
      headerQueue.style.color = "var(--text-muted)";
    }

    const ks = data.keystore;
    document.getElementById("keystore-status").textContent = ks.exists ? "Active (Valid)" : "Not Found";
    document.getElementById("keystore-status").style.color = ks.exists ? "var(--accent)" : "var(--danger)";
    document.getElementById("keystore-alias").textContent = ks.alias || "morphe";
    document.getElementById("keystore-path").textContent = ks.path;

    document.getElementById("jar-status").textContent = data.morphe_jar.exists ? "Ready (Installed)" : "Missing";
    document.getElementById("jar-status").style.color = data.morphe_jar.exists ? "var(--accent)" : "var(--danger)";
    document.getElementById("mpp-status").textContent = data.patches_bundle.exists ? "Ready (Installed)" : "Missing";
    document.getElementById("mpp-status").style.color = data.patches_bundle.exists ? "var(--accent)" : "var(--danger)";

    const w = data.watcher;
    document.getElementById("watcher-dir-text").textContent = w.watch_dir;
    document.getElementById("watcher-status-text").textContent = w.enabled ? "Active & Monitoring" : "Disabled";

    const profileSelect = document.getElementById("patch-profile");
    if (profileSelect && !uploadedApkData && data.profile_details) {
      const currentVal = profileSelect.value;
      profileSelect.innerHTML = `<option value="">Standard Defaults (No Profile)</option>`;
      data.profile_details.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `${p.is_default ? '⭐' : '📋'} ${p.name}`;
        if (p.id === currentVal) opt.selected = true;
        profileSelect.appendChild(opt);
      });
    }

    const pendingEl = document.getElementById("watcher-pending-list");
    if (w.pending_files && w.pending_files.length > 0) {
      pendingEl.innerHTML = w.pending_files.map(f => `<div>⏳ Stabilizing file: <strong>${escapeHtml(f)}</strong></div>`).join("");
      pendingEl.style.color = "var(--warning)";
    } else {
      pendingEl.textContent = "No files currently stabilizing or transferring.";
      pendingEl.style.color = "var(--text-muted)";
    }

    renderWatcherEvents(w.recent_events || []);

  } catch (e) {
    console.error("Failed to fetch system status:", e);
  }
}

function renderWatcherEvents(events) {
  const tbody = document.getElementById("watcher-events-tbody");
  if (!events || events.length === 0) {
    tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">No recent watcher events.</td></tr>`;
    return;
  }

  tbody.innerHTML = events.slice().reverse().map(e => {
    const time = new Date(e.timestamp * 1000).toLocaleTimeString();
    return `
      <tr>
        <td style="color: var(--text-muted); font-size: 0.85rem;">${time}</td>
        <td style="font-weight: 600;">${escapeHtml(e.filename)}</td>
        <td><span class="badge" style="background: #1e3a8a; color: #93c5fd;">${e.status}</span></td>
      </tr>
    `;
  }).join("");
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/[&<>'"]/g, 
    tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag)
  );
}

// -------------------------------------------------------------
// PROFILES & PRESETS SYSTEM
// -------------------------------------------------------------

let currentAppProfiles = [];
let allProfilesCache = [];

async function loadAndSelectProfileForApp(packageName, appName) {
  const profileSelect = document.getElementById("patch-profile");
  if (!profileSelect) return;

  try {
    const res = await fetch(`/api/profiles?package=${encodeURIComponent(packageName || '')}`);
    if (!res.ok) throw new Error("Failed to fetch profiles");
    currentAppProfiles = await res.json();

    profileSelect.innerHTML = `<option value="">Standard Defaults (No Profile)</option>`;
    
    let defaultProfile = null;
    currentAppProfiles.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.is_default ? '⭐' : '📋'} ${p.name} ${p.is_default ? '(Default)' : ''}`;
      if (p.is_default && !defaultProfile) {
        defaultProfile = p;
        opt.selected = true;
      }
      profileSelect.appendChild(opt);
    });

    if (defaultProfile) {
      profileSelect.value = defaultProfile.id;
      applyProfileToUi(defaultProfile);
    } else {
      profileSelect.value = "";
      applyProfileToUi(null);
    }
  } catch (e) {
    console.error("Error loading profiles for app:", e);
    profileSelect.innerHTML = `<option value="">Standard Defaults (No Profile)</option>`;
    applyProfileToUi(null);
  }
}

function applyProfileToUi(profile) {
  const summaryBar = document.getElementById("profile-summary-bar");
  const summaryText = document.getElementById("profile-summary-text");
  const tagBadge = document.getElementById("profile-tag-badge");
  const brandingChoice = document.getElementById("branding-choice");
  const customAppName = document.getElementById("custom-app-name");
  const outputNameInput = document.getElementById("output-name");
  const optArchToggle = document.getElementById("optimize-arch-toggle");
  const appName = uploadedApkData?.app_name || "App";
  const ver = uploadedApkData?.version_name || "";

  if (profile) {
    if (summaryBar) summaryBar.style.display = "flex";
    if (tagBadge) {
      tagBadge.textContent = profile.is_default ? "⭐ Default" : "Custom Preset";
      tagBadge.style.background = profile.is_default ? "rgba(99, 102, 241, 0.25)" : "var(--badge-bg)";
      tagBadge.style.color = profile.is_default ? "#a5b4fc" : "var(--text-muted)";
    }
    if (summaryText) {
      const brandDesc = profile.branding === "custom" 
        ? `Branding: "${profile.custom_app_name || '{appName} Morphe'}"` 
        : (profile.branding === "morphe" ? "Branding: Morphe" : "Branding: Stock");
      const archDesc = profile.optimize_arch ? (profile.target_arch === "armeabi-v7a" ? "ARM32" : "ARM64") : "Universal";
      summaryText.innerHTML = `✨ <strong>Active:</strong> ${escapeHtml(profile.name)} &bull; ${escapeHtml(brandDesc)} &bull; ${escapeHtml(archDesc)}`;
    }

    // Set branding
    if (brandingChoice) {
      brandingChoice.value = profile.branding || "original";
      if (profile.branding === "custom") {
        if (customAppName) {
          customAppName.style.display = "block";
          const rawTemplate = profile.custom_app_name || "{appName} Morphe";
          customAppName.value = rawTemplate.replace(/\{appName\}|\{app_name\}|\{app\}/g, appName);
        }
      } else {
        if (customAppName) customAppName.style.display = "none";
      }
    }

    // Set arch
    if (optArchToggle) {
      optArchToggle.checked = profile.optimize_arch ?? true;
      const archGroup = document.getElementById("arch-selector-group");
      if (archGroup) {
        archGroup.style.opacity = optArchToggle.checked ? "1" : "0.45";
        archGroup.style.pointerEvents = optArchToggle.checked ? "auto" : "none";
      }
    }
    const targetArch = profile.target_arch || "arm64-v8a";
    const radio = document.querySelector(`input[name="target-arch"][value="${targetArch}"]`);
    if (radio) radio.checked = true;

    // Set output name
    if (outputNameInput) {
      let rawOut = profile.output_format || "{appName}_{version}_{arch}_patched.apk";
      const cleanApp = appName.toLowerCase().replace(/[^a-z0-9]/g, "_");
      const archTag = (profile.optimize_arch ?? true) ? (targetArch === "armeabi-v7a" ? "arm32" : "arm64") : "universal";
      let resolved = rawOut
        .replace(/\{appName\}|\{app_name\}|\{app\}/g, cleanApp)
        .replace(/\{version\}|\{ver\}/g, ver)
        .replace(/\{arch\}/g, archTag);
      resolved = resolved.replace(/_+/g, "_").replace("._", ".").replace("_.", ".");
      if (!resolved.toLowerCase().endsWith(".apk")) resolved += ".apk";
      outputNameInput.value = resolved;
    }

  } else {
    // Standard defaults
    if (summaryBar) summaryBar.style.display = "flex";
    if (tagBadge) {
      tagBadge.textContent = "Stock Defaults";
      tagBadge.style.background = "rgba(16, 185, 129, 0.15)";
      tagBadge.style.color = "#34d399";
    }
    if (summaryText) {
      summaryText.innerHTML = `✨ <strong>Active:</strong> Recommended Morphe Patches (Keep stock app name & icon)`;
    }
    if (brandingChoice) {
      brandingChoice.value = "original";
      if (customAppName) customAppName.style.display = "none";
    }
    updateSuggestedFilename(true);
  }
}

function setupProfiles() {
  const btnCreate = document.getElementById("btn-create-profile");
  const btnClose = document.getElementById("btn-close-profile-modal");
  const btnCancel = document.getElementById("btn-cancel-profile");
  const form = document.getElementById("profile-form");
  const searchInput = document.getElementById("profile-search-input");
  const packageSelect = document.getElementById("modal-package-select");
  const customPackageInput = document.getElementById("modal-custom-package");
  const brandingSelect = document.getElementById("modal-branding-select");
  const customNameWrap = document.getElementById("modal-custom-name-wrap");

  if (btnCreate) {
    btnCreate.addEventListener("click", () => openProfileModal());
  }
  if (btnClose) {
    btnClose.addEventListener("click", closeProfileModal);
  }
  if (btnCancel) {
    btnCancel.addEventListener("click", closeProfileModal);
  }

  if (packageSelect) {
    packageSelect.addEventListener("change", () => {
      if (packageSelect.value === "custom") {
        customPackageInput.style.display = "block";
        customPackageInput.focus();
      } else {
        customPackageInput.style.display = "none";
      }
    });
  }

  if (brandingSelect) {
    brandingSelect.addEventListener("change", () => {
      if (brandingSelect.value === "custom") {
        customNameWrap.style.display = "block";
      } else {
        customNameWrap.style.display = "none";
      }
    });
  }

  document.querySelectorAll(".tag-pill").forEach(pill => {
    pill.addEventListener("click", (e) => {
      const tag = e.target.dataset.tag;
      const input = document.getElementById("modal-output-format");
      if (tag && input) {
        input.value = `${input.value}${tag}`;
      }
    });
  });

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      renderProfilesGrid(searchInput.value.trim().toLowerCase());
    });
  }

  if (form) {
    form.addEventListener("submit", handleProfileFormSubmit);
  }
}

async function loadProfilesList() {
  try {
    const res = await fetch("/api/profiles");
    if (!res.ok) throw new Error("Failed to load profiles");
    allProfilesCache = await res.json();
    renderProfilesGrid();
  } catch (e) {
    console.error("Error fetching profiles:", e);
  }
}

function renderProfilesGrid(filter = "") {
  const container = document.getElementById("profiles-grid");
  const countBadge = document.getElementById("profiles-count-badge");
  if (!container) return;

  let profiles = allProfilesCache;
  if (filter) {
    profiles = profiles.filter(p => 
      p.name.toLowerCase().includes(filter) || 
      p.package_name.toLowerCase().includes(filter) ||
      (p.description && p.description.toLowerCase().includes(filter))
    );
  }

  if (countBadge) {
    countBadge.textContent = `${profiles.length} Preset${profiles.length === 1 ? '' : 's'}`;
  }

  if (profiles.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 3rem 1.5rem; background: var(--bg-card); border: 1px dashed var(--border); border-radius: 12px; color: var(--text-muted);">
        <div style="font-size: 2.2rem; margin-bottom: 0.5rem;">📋</div>
        <div style="font-weight: 600; font-size: 1.05rem; color: var(--text-main);">No Presets Found</div>
        <div style="font-size: 0.85rem; margin-top: 0.25rem;">Create a preset to configure custom naming, architecture, and output formats.</div>
      </div>
    `;
    return;
  }

  const packageIcons = {
    "com.google.android.youtube": "📺",
    "com.google.android.apps.youtube.music": "🎵",
    "com.reddit.frontpage": "🤖",
    "com.twitter.android": "🐦",
    "com.spotify.music": "🎧",
    "*": "🌐",
  };

  container.innerHTML = profiles.map(p => {
    const icon = packageIcons[p.package_name] || "📱";
    const isDefault = p.is_default;
    const defaultBadge = isDefault ? `<span class="badge" style="background: rgba(99, 102, 241, 0.25); color: #818cf8; font-weight: 700;">⭐ Default</span>` : "";
    const brandLabel = p.branding === "custom" 
      ? `✏️ "${p.custom_app_name || '{appName} Morphe'}"` 
      : (p.branding === "morphe" ? "🟣 Morphe" : "🔴 Original Stock");
    const archLabel = p.optimize_arch ? (p.target_arch === "armeabi-v7a" ? "ARM32" : "ARM64") : "Universal";

    return `
      <div class="profile-card ${isDefault ? 'is-default' : ''}">
        <div>
          <div class="profile-card-header">
            <div>
              <div class="profile-card-title">
                <span>${icon}</span>
                <span>${escapeHtml(p.name)}</span>
              </div>
              <div class="profile-card-pkg">${escapeHtml(p.package_name === "*" ? "Universal (Any App)" : p.package_name)}</div>
            </div>
            ${defaultBadge}
          </div>

          <div style="font-size: 0.82rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.5rem;">
            ${escapeHtml(p.description || "Preset with customized naming and patching settings.")}
          </div>

          <div class="profile-details-list">
            <div class="profile-detail-row">
              <span class="profile-detail-label">Branding:</span>
              <span class="profile-detail-val" title="${escapeHtml(brandLabel)}">${escapeHtml(brandLabel)}</span>
            </div>
            <div class="profile-detail-row">
              <span class="profile-detail-label">Output Filename:</span>
              <span class="profile-detail-val" title="${escapeHtml(p.output_format || '')}">${escapeHtml(p.output_format || 'default')}</span>
            </div>
            <div class="profile-detail-row">
              <span class="profile-detail-label">Architecture:</span>
              <span class="profile-detail-val">${archLabel}</span>
            </div>
          </div>
        </div>

        <div class="profile-card-actions">
          ${!isDefault ? `<button type="button" class="btn btn-secondary btn-action-default" data-id="${escapeHtml(p.id)}" style="padding: 0.35rem 0.65rem; font-size: 0.78rem;">⭐ Make Default</button>` : ''}
          <button type="button" class="btn btn-secondary btn-action-edit" data-id="${escapeHtml(p.id)}" style="padding: 0.35rem 0.65rem; font-size: 0.78rem;">✏️ Edit</button>
          <button type="button" class="btn btn-danger btn-action-delete" data-id="${escapeHtml(p.id)}" style="padding: 0.35rem 0.65rem; font-size: 0.78rem;">🗑️ Delete</button>
        </div>
      </div>
    `;
  }).join("");

  // Attach event handlers
  container.querySelectorAll(".btn-action-default").forEach(b => {
    b.addEventListener("click", () => handleSetDefaultProfile(b.dataset.id));
  });
  container.querySelectorAll(".btn-action-edit").forEach(b => {
    b.addEventListener("click", () => handleEditProfile(b.dataset.id));
  });
  container.querySelectorAll(".btn-action-delete").forEach(b => {
    b.addEventListener("click", () => handleDeleteProfile(b.dataset.id));
  });
}

function openProfileModal(data = null) {
  const modal = document.getElementById("profile-editor-modal");
  const heading = document.getElementById("modal-profile-heading");
  const idInput = document.getElementById("modal-profile-id");
  const nameInput = document.getElementById("modal-profile-name");
  const packageSelect = document.getElementById("modal-package-select");
  const customPackageInput = document.getElementById("modal-custom-package");
  const brandingSelect = document.getElementById("modal-branding-select");
  const customNameInput = document.getElementById("modal-custom-name");
  const customNameWrap = document.getElementById("modal-custom-name-wrap");
  const outputFormatInput = document.getElementById("modal-output-format");
  const isDefaultCheckbox = document.getElementById("modal-is-default");

  if (!modal) return;

  if (data) {
    heading.textContent = data.id ? "Edit Preset Profile" : "Create Preset Profile";
    idInput.value = data.id || "";
    nameInput.value = data.name || "";

    const pkg = data.package_name || "*";
    const foundOpt = Array.from(packageSelect.options).find(o => o.value === pkg);
    if (foundOpt) {
      packageSelect.value = pkg;
      customPackageInput.style.display = "none";
      customPackageInput.value = "";
    } else {
      packageSelect.value = "custom";
      customPackageInput.style.display = "block";
      customPackageInput.value = pkg;
    }

    brandingSelect.value = data.branding || "custom";
    customNameWrap.style.display = brandingSelect.value === "custom" ? "block" : "none";
    customNameInput.value = data.custom_app_name || "{appName} Morphe";

    outputFormatInput.value = data.output_format || "{appName}_{version}_{arch}_patched.apk";
    
    const arch = data.target_arch || "arm64-v8a";
    const radio = document.querySelector(`input[name="modal-arch"][value="${arch}"]`);
    if (radio) radio.checked = true;

    isDefaultCheckbox.checked = !!data.is_default;
  } else {
    heading.textContent = "Create Preset Profile";
    idInput.value = "";
    nameInput.value = "";
    packageSelect.value = "com.google.android.youtube";
    customPackageInput.style.display = "none";
    customPackageInput.value = "";
    brandingSelect.value = "custom";
    customNameWrap.style.display = "block";
    customNameInput.value = "{appName} Morphe";
    outputFormatInput.value = "{appName}_{version}_{arch}_patched.apk";
    const radio = document.querySelector('input[name="modal-arch"][value="arm64-v8a"]');
    if (radio) radio.checked = true;
    isDefaultCheckbox.checked = true;
  }

  modal.classList.add("active");
}

function closeProfileModal() {
  const modal = document.getElementById("profile-editor-modal");
  if (modal) modal.classList.remove("active");
}

async function handleProfileFormSubmit(e) {
  e.preventDefault();
  const idInput = document.getElementById("modal-profile-id");
  const nameInput = document.getElementById("modal-profile-name");
  const packageSelect = document.getElementById("modal-package-select");
  const customPackageInput = document.getElementById("modal-custom-package");
  const brandingSelect = document.getElementById("modal-branding-select");
  const customNameInput = document.getElementById("modal-custom-name");
  const outputFormatInput = document.getElementById("modal-output-format");
  const isDefaultCheckbox = document.getElementById("modal-is-default");
  const selectedArch = document.querySelector('input[name="modal-arch"]:checked')?.value || "arm64-v8a";

  let pkg = packageSelect.value;
  if (pkg === "custom") {
    pkg = customPackageInput.value.trim() || "*";
  }

  const payload = {
    id: idInput.value || undefined,
    name: nameInput.value.trim(),
    package_name: pkg,
    branding: brandingSelect.value,
    custom_app_name: customNameInput.value.trim() || "{appName} Morphe",
    output_format: outputFormatInput.value.trim() || "{appName}_{version}_{arch}_patched.apk",
    optimize_arch: selectedArch !== "universal",
    target_arch: selectedArch,
    is_default: isDefaultCheckbox.checked,
  };

  try {
    const res = await fetch("/api/profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Failed to save profile");
    }
    closeProfileModal();
    await loadProfilesList();
    if (uploadedApkData) {
      await loadAndSelectProfileForApp(uploadedApkData.package_name, uploadedApkData.app_name);
    }
  } catch (err) {
    alert("Error saving profile: " + err.message);
  }
}

async function handleSetDefaultProfile(profileId) {
  try {
    const res = await fetch(`/api/profiles/${encodeURIComponent(profileId)}/set-default`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to set default profile");
    await loadProfilesList();
    if (uploadedApkData) {
      await loadAndSelectProfileForApp(uploadedApkData.package_name, uploadedApkData.app_name);
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function handleEditProfile(profileId) {
  const prof = allProfilesCache.find(p => p.id === profileId);
  if (prof) {
    openProfileModal(prof);
  }
}

async function handleDeleteProfile(profileId) {
  if (!confirm(`Are you sure you want to delete profile "${profileId}"?`)) return;
  try {
    const res = await fetch(`/api/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete profile");
    await loadProfilesList();
    if (uploadedApkData) {
      await loadAndSelectProfileForApp(uploadedApkData.package_name, uploadedApkData.app_name);
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}


