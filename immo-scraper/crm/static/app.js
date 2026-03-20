/* ==========================================================================
   Immo CRM – Frontend Application
   ========================================================================== */

(function () {
  "use strict";

  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  let agencies = [];          // full list from API
  let filtered = [];          // after filters applied
  let selectedSlug = null;    // currently open agency slug
  let selectedIndex = -1;     // index in filtered[]
  let currentView = "map";    // "map" or "list"
  let sortField = "lead_score";
  let sortAsc = false;
  let map, markerClusterGroup;
  let markers = {};           // slug -> L.marker

  // Status labels (French)
  const STATUS_LABELS = {
    not_contacted: "Pas contact\u00e9",
    contacted: "Contact\u00e9",
    waiting: "En attente de r\u00e9ponse",
    responded: "R\u00e9pondu",
    converted: "Converti",
    not_interested: "Pas int\u00e9ress\u00e9",
  };

  // Status -> marker colour
  const STATUS_COLORS = {
    not_contacted: "#e53935",
    contacted: "#ff9800",
    waiting: "#ff9800",
    responded: "#00c853",
    converted: "#00c853",
    not_interested: "#78909c",
  };

  // -----------------------------------------------------------------------
  // Map setup
  // -----------------------------------------------------------------------
  function initMap() {
    map = L.map("map", { zoomControl: true }).setView([48.856, 2.352], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);

    markerClusterGroup = L.markerClusterGroup({
      maxClusterRadius: 45,
      spiderfyOnMaxZoom: true,
      showCoverageOnHover: false,
      disableClusteringAtZoom: 17,
    });
    map.addLayer(markerClusterGroup);
  }

  // Create a coloured circle-marker icon
  function makeIcon(color, isActive) {
    const size = isActive ? 16 : 12;
    const border = isActive ? "3px solid #0066ff" : "2px solid #fff";
    return L.divIcon({
      className: "custom-marker",
      html: '<div style="width:' + size + "px;height:" + size + "px;border-radius:50%;background:" + color + ";border:" + border + ';box-shadow:0 1px 4px rgba(0,0,0,0.3);"></div>',
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }

  function addMarkers() {
    markerClusterGroup.clearLayers();
    markers = {};

    filtered.forEach(function (ag) {
      if (ag.lat == null || ag.lng == null) return;
      var color = STATUS_COLORS[ag.status] || STATUS_COLORS.not_contacted;
      var isActive = ag.slug === selectedSlug;
      var marker = L.marker([ag.lat, ag.lng], { icon: makeIcon(color, isActive) });
      marker.bindTooltip(ag.name, { direction: "top", offset: [0, -8] });
      marker.on("click", function () {
        openDetail(ag.slug);
      });
      markers[ag.slug] = marker;
      markerClusterGroup.addLayer(marker);
    });
  }

  function highlightMarker(slug) {
    // Reset previous
    Object.keys(markers).forEach(function (s) {
      var ag = agencies.find(function (a) { return a.slug === s; });
      if (ag && markers[s]) {
        var c = STATUS_COLORS[ag.status] || STATUS_COLORS.not_contacted;
        markers[s].setIcon(makeIcon(c, s === slug));
      }
    });
  }

  // -----------------------------------------------------------------------
  // Data loading
  // -----------------------------------------------------------------------
  function loadAgencies() {
    fetch("/api/agencies")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        agencies = data;
        applyFilters();
        loadStats();
        populateNetworkFilter();
      })
      .catch(function (err) {
        console.error("Erreur chargement agences:", err);
      });
  }

  function loadStats() {
    fetch("/api/stats")
      .then(function (r) { return r.json(); })
      .then(function (stats) {
        renderStats(stats);
      });
  }

  function renderStats(s) {
    var bar = document.getElementById("stats-bar");
    var sc = s.status_counts;
    bar.innerHTML =
      '<span class="stat-badge"><span class="dot dot-blue"></span>' + s.total + " agences</span>" +
      '<span class="stat-badge"><span class="dot dot-red"></span>' + sc.not_contacted + "</span>" +
      '<span class="stat-badge"><span class="dot dot-orange"></span>' + (sc.contacted + sc.waiting) + "</span>" +
      '<span class="stat-badge"><span class="dot dot-green"></span>' + (sc.responded + sc.converted) + "</span>" +
      '<span class="stat-badge"><span class="dot dot-grey"></span>' + sc.not_interested + "</span>" +
      '<span class="stat-badge">Score moy. ' + s.avg_lead_score + "</span>";
  }

  function populateNetworkFilter() {
    var nets = {};
    agencies.forEach(function (ag) {
      var n = ag.network_affiliation || "ind\u00e9pendant";
      nets[n] = (nets[n] || 0) + 1;
    });
    var sel = document.getElementById("filter-network");
    // Keep the first option
    sel.innerHTML = '<option value="">Tous les r\u00e9seaux</option>';
    var sorted = Object.entries(nets).sort(function (a, b) { return b[1] - a[1]; });
    sorted.forEach(function (pair) {
      var opt = document.createElement("option");
      opt.value = pair[0];
      opt.textContent = pair[0] + " (" + pair[1] + ")";
      sel.appendChild(opt);
    });
  }

  // -----------------------------------------------------------------------
  // Filtering & sorting
  // -----------------------------------------------------------------------
  function applyFilters() {
    var search = document.getElementById("filter-search").value.toLowerCase();
    var status = document.getElementById("filter-status").value;
    var network = document.getElementById("filter-network").value;
    var scoreRange = document.getElementById("filter-score").value;

    filtered = agencies.filter(function (ag) {
      if (search && ag.name.toLowerCase().indexOf(search) === -1 &&
          ag.address.toLowerCase().indexOf(search) === -1) return false;
      if (status && ag.status !== status) return false;
      if (network && (ag.network_affiliation || "ind\u00e9pendant") !== network) return false;
      if (scoreRange) {
        var parts = scoreRange.split("-");
        var lo = parseInt(parts[0], 10);
        var hi = parseInt(parts[1], 10);
        var score = ag.lead_score || 0;
        if (score < lo || score > hi) return false;
      }
      return true;
    });

    // Sort
    filtered.sort(function (a, b) {
      var va = a[sortField], vb = b[sortField];
      if (va == null) va = sortAsc ? Infinity : -Infinity;
      if (vb == null) vb = sortAsc ? Infinity : -Infinity;
      if (typeof va === "string") va = va.toLowerCase();
      if (typeof vb === "string") vb = vb.toLowerCase();
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });

    renderList();
    renderTable();
    addMarkers();
    updateCount();
  }

  function updateCount() {
    document.getElementById("list-count").textContent =
      filtered.length + " / " + agencies.length + " agences";
  }

  // -----------------------------------------------------------------------
  // Sidebar list rendering
  // -----------------------------------------------------------------------
  function renderList() {
    var container = document.getElementById("agency-list");
    container.innerHTML = "";

    filtered.forEach(function (ag, idx) {
      var card = document.createElement("div");
      card.className = "agency-card" + (ag.slug === selectedSlug ? " active" : "");
      card.dataset.slug = ag.slug;
      card.dataset.index = idx;

      var scoreTxt = ag.lead_score != null ? Math.round(ag.lead_score) : "--";
      card.innerHTML =
        '<div class="card-name">' + escHtml(ag.name) + "</div>" +
        '<div class="card-address">' + escHtml(ag.address) + "</div>" +
        '<div class="card-meta">' +
          '<span class="status-dot status-' + ag.status + '"></span>' +
          '<span class="score-mini">' + scoreTxt + "</span>" +
          '<span class="network-label">' + escHtml(ag.network_affiliation || "") + "</span>" +
        "</div>";

      card.addEventListener("click", function () {
        openDetail(ag.slug);
      });
      container.appendChild(card);
    });
  }

  // -----------------------------------------------------------------------
  // Table rendering
  // -----------------------------------------------------------------------
  function renderTable() {
    var tbody = document.getElementById("table-body");
    tbody.innerHTML = "";

    filtered.forEach(function (ag, idx) {
      var tr = document.createElement("tr");
      tr.className = ag.slug === selectedSlug ? "active" : "";
      tr.dataset.slug = ag.slug;

      var scoreTxt = ag.lead_score != null ? Math.round(ag.lead_score) : "--";
      tr.innerHTML =
        "<td>" + escHtml(ag.name) + "</td>" +
        "<td>" + scoreTxt + "</td>" +
        '<td><span class="status-dot status-' + ag.status + '" style="display:inline-block;width:8px;height:8px;border-radius:50;margin-right:4px;"></span> ' + (STATUS_LABELS[ag.status] || ag.status) + "</td>" +
        "<td>" + escHtml(ag.network_affiliation || "") + "</td>" +
        "<td>" + escHtml(ag.last_contact_date || "") + "</td>";

      tr.addEventListener("click", function () {
        openDetail(ag.slug);
      });
      tbody.appendChild(tr);
    });
  }

  // -----------------------------------------------------------------------
  // Detail panel
  // -----------------------------------------------------------------------
  function openDetail(slug) {
    selectedSlug = slug;
    selectedIndex = filtered.findIndex(function (a) { return a.slug === slug; });

    // Highlight in list/table
    document.querySelectorAll(".agency-card").forEach(function (el) {
      el.classList.toggle("active", el.dataset.slug === slug);
    });
    document.querySelectorAll("#table-body tr").forEach(function (el) {
      el.classList.toggle("active", el.dataset.slug === slug);
    });

    // Highlight marker
    highlightMarker(slug);

    // Pan map to marker
    if (markers[slug]) {
      markerClusterGroup.zoomToShowLayer(markers[slug], function () {
        map.panTo(markers[slug].getLatLng());
      });
    }

    // Scroll card into view
    var card = document.querySelector('.agency-card[data-slug="' + slug + '"]');
    if (card) card.scrollIntoView({ block: "nearest", behavior: "smooth" });

    // Fetch full detail
    fetch("/api/agencies/" + encodeURIComponent(slug))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderDetailPanel(data);
        document.getElementById("detail-panel").classList.add("open");
        document.getElementById("overlay").classList.add("visible");
      });
  }

  function closeDetail() {
    document.getElementById("detail-panel").classList.remove("open");
    document.getElementById("overlay").classList.remove("visible");
    selectedSlug = null;
    document.querySelectorAll(".agency-card.active").forEach(function (el) { el.classList.remove("active"); });
    document.querySelectorAll("#table-body tr.active").forEach(function (el) { el.classList.remove("active"); });
    highlightMarker(null);
  }

  function renderDetailPanel(ag) {
    document.getElementById("panel-title").textContent = ag.name;

    var crm = ag.crm || {};
    var score = ag.lead_score != null ? Math.round(ag.lead_score) : null;
    var scoreClass = score >= 70 ? "score-high" : score >= 40 ? "score-mid" : "score-low";
    var scoreWidth = score != null ? score : 0;

    var html = "";

    // --- Contact info section ---
    html += '<div class="detail-section">';
    html += "<h3>Informations</h3>";
    html += detailRow("Adresse", ag.address);
    if (ag.phone) html += detailRow("T\u00e9l\u00e9phone", '<a href="tel:' + escAttr(ag.phone.trim()) + '">' + escHtml(ag.phone.trim()) + "</a>");
    if (ag.email) html += detailRow("Email", '<a href="mailto:' + escAttr(ag.email) + '">' + escHtml(ag.email) + "</a>");
    if (ag.website) html += detailRow("Site web", '<a href="' + escAttr(ag.website) + '" target="_blank" rel="noopener">' + truncUrl(ag.website) + "</a>");
    if (ag.siret) html += detailRow("SIRET", ag.siret);
    html += "</div>";

    // --- Google / Network section ---
    html += '<div class="detail-section">';
    html += "<h3>Google & R\u00e9seau</h3>";
    html += detailRow("Note Google", ag.google_rating != null ? ag.google_rating + " / 5" : "--");
    html += detailRow("Avis", ag.google_review_count != null ? ag.google_review_count : "--");
    html += detailRow("R\u00e9seau", ag.network_affiliation || "ind\u00e9pendant");
    if (ag.site_quality) html += detailRow("Qualit\u00e9 site", ag.site_quality);
    if (ag.website_tech) html += detailRow("Technologie", ag.website_tech);
    if (ag.director_name) html += detailRow("Directeur", ag.director_name);
    if (ag.year_founded) html += detailRow("Fond\u00e9e en", ag.year_founded);
    if (ag.has_blog != null) html += detailRow("Blog", ag.has_blog ? "Oui" : "Non");
    if (ag.is_mobile_friendly != null) html += detailRow("Mobile OK", ag.is_mobile_friendly ? "Oui" : "Non");
    html += "</div>";

    // --- Lead score ---
    html += '<div class="detail-section">';
    html += "<h3>Score de prospection</h3>";
    html += '<div class="score-bar-container">';
    html += '<div class="score-bar"><div class="fill ' + scoreClass + '" style="width:' + scoreWidth + '%"></div></div>';
    html += '<span class="score-label">' + (score != null ? score + " / 100" : "Non calcul\u00e9") + "</span>";
    html += "</div>";
    if (ag.lead_score_details) {
      var details = ag.lead_score_details;
      var keys = Object.keys(details);
      html += '<div style="font-size:11px;color:#6b7280;margin-top:6px;">';
      keys.forEach(function (k) {
        html += "<span>" + k + ": " + details[k] + "</span> &nbsp; ";
      });
      html += "</div>";
    }
    html += "</div>";

    // --- Social links ---
    var socials = [];
    if (ag.facebook_url) socials.push({ label: "Facebook", url: ag.facebook_url });
    if (ag.instagram_url) socials.push({ label: "Instagram", url: ag.instagram_url });
    if (ag.linkedin_url) socials.push({ label: "LinkedIn", url: ag.linkedin_url });
    if (ag.google_maps_url) socials.push({ label: "Google Maps", url: ag.google_maps_url });
    if (socials.length) {
      html += '<div class="detail-section">';
      html += "<h3>Liens</h3>";
      html += '<div class="social-links">';
      socials.forEach(function (s) {
        html += '<a href="' + escAttr(s.url) + '" target="_blank" rel="noopener">' + s.label + "</a>";
      });
      html += "</div></div>";
    }

    // --- Description ---
    if (ag.linkup_description) {
      html += '<div class="detail-section">';
      html += "<h3>Description</h3>";
      html += '<p style="font-size:12px;color:#6b7280;">' + escHtml(ag.linkup_description) + "</p>";
      html += "</div>";
    }

    // --- CRM Section ---
    html += '<div class="crm-section">';
    html += "<h3>Suivi commercial</h3>";

    html += '<div class="crm-field">';
    html += "<label>Statut</label>";
    html += '<select id="crm-status">';
    Object.keys(STATUS_LABELS).forEach(function (k) {
      var sel = crm.status === k ? " selected" : "";
      html += '<option value="' + k + '"' + sel + ">" + STATUS_LABELS[k] + "</option>";
    });
    html += "</select></div>";

    html += '<div class="crm-field">';
    html += "<label>Date du dernier contact</label>";
    html += '<input type="date" id="crm-date" value="' + escAttr(crm.last_contact_date || "") + '" />';
    html += "</div>";

    html += '<div class="crm-field">';
    html += "<label>Message envoy\u00e9</label>";
    html += '<textarea id="crm-message" rows="3" placeholder="D\u00e9crivez le message envoy\u00e9...">' + escHtml(crm.message_sent || "") + "</textarea>";
    html += "</div>";

    html += '<div class="crm-field">';
    html += "<label>Notes</label>";
    html += '<textarea id="crm-notes" rows="3" placeholder="Notes internes...">' + escHtml(crm.notes || "") + "</textarea>";
    html += "</div>";

    html += '<button class="btn-save" id="btn-save-crm">Enregistrer</button>';
    html += "</div>";

    // --- History ---
    if (crm.history && crm.history.length > 0) {
      html += '<div class="detail-section" style="margin-top:16px;">';
      html += "<h3>Historique</h3>";
      html += '<ul class="history-list">';
      crm.history.slice().reverse().forEach(function (h) {
        html += "<li>";
        html += '<div class="hist-date">' + escHtml(h.date || "") + "</div>";
        html += "<div>" + escHtml(h.action || "") + "</div>";
        if (h.details) html += '<div style="font-size:11px;color:#6b7280;">' + escHtml(h.details) + "</div>";
        html += "</li>";
      });
      html += "</ul></div>";
    }

    document.getElementById("panel-body").innerHTML = html;

    // Bind save button
    document.getElementById("btn-save-crm").addEventListener("click", function () {
      saveCRM(ag.slug);
    });
  }

  function saveCRM(slug) {
    var payload = {
      status: document.getElementById("crm-status").value,
      last_contact_date: document.getElementById("crm-date").value || null,
      message_sent: document.getElementById("crm-message").value || null,
      notes: document.getElementById("crm-notes").value || null,
    };

    var btn = document.getElementById("btn-save-crm");
    btn.textContent = "Enregistrement...";
    btn.disabled = true;

    fetch("/api/agencies/" + encodeURIComponent(slug) + "/contact", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json(); })
      .then(function (resp) {
        btn.textContent = "Enregistr\u00e9 !";
        btn.classList.add("saved");
        showToast("Modifications enregistr\u00e9es");

        // Update local data
        var ag = agencies.find(function (a) { return a.slug === slug; });
        if (ag) {
          ag.status = payload.status;
          ag.last_contact_date = payload.last_contact_date || "";
        }

        // Refresh markers and list to reflect new status
        applyFilters();

        // Re-highlight the selected item
        setTimeout(function () {
          highlightMarker(slug);
          document.querySelectorAll(".agency-card").forEach(function (el) {
            el.classList.toggle("active", el.dataset.slug === slug);
          });
        }, 50);

        setTimeout(function () {
          btn.textContent = "Enregistrer";
          btn.classList.remove("saved");
          btn.disabled = false;
        }, 1500);
      })
      .catch(function (err) {
        btn.textContent = "Erreur !";
        btn.disabled = false;
        showToast("Erreur lors de l'enregistrement");
        console.error(err);
        setTimeout(function () { btn.textContent = "Enregistrer"; }, 2000);
      });
  }

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------
  function detailRow(label, value) {
    return '<div class="detail-row"><span class="label">' + label + '</span><span class="value">' + (value || "--") + "</span></div>";
  }

  function escHtml(str) {
    if (!str) return "";
    var d = document.createElement("div");
    d.textContent = String(str);
    return d.innerHTML;
  }

  function escAttr(str) {
    return escHtml(str).replace(/"/g, "&quot;");
  }

  function truncUrl(url) {
    try {
      var u = new URL(url);
      return u.hostname;
    } catch (e) {
      return url;
    }
  }

  function showToast(msg) {
    var t = document.getElementById("toast");
    t.textContent = msg;
    t.classList.add("visible");
    setTimeout(function () { t.classList.remove("visible"); }, 2500);
  }

  // -----------------------------------------------------------------------
  // View toggle
  // -----------------------------------------------------------------------
  document.getElementById("btn-map-view").addEventListener("click", function () {
    currentView = "map";
    this.classList.add("active");
    document.getElementById("btn-list-view").classList.remove("active");
    document.getElementById("agency-list").classList.remove("hidden");
    document.getElementById("table-view").classList.remove("visible");
  });

  document.getElementById("btn-list-view").addEventListener("click", function () {
    currentView = "list";
    this.classList.add("active");
    document.getElementById("btn-map-view").classList.remove("active");
    document.getElementById("agency-list").classList.add("hidden");
    document.getElementById("table-view").classList.add("visible");
  });

  // Table header sort
  document.querySelectorAll("#agencies-table th[data-sort]").forEach(function (th) {
    th.addEventListener("click", function () {
      var field = th.dataset.sort;
      if (sortField === field) {
        sortAsc = !sortAsc;
      } else {
        sortField = field;
        sortAsc = true;
      }
      // Update arrows
      document.querySelectorAll("#agencies-table th .sort-arrow").forEach(function (s) { s.textContent = ""; });
      th.querySelector(".sort-arrow").textContent = sortAsc ? " \u25B2" : " \u25BC";
      applyFilters();
    });
  });

  // -----------------------------------------------------------------------
  // Filter events
  // -----------------------------------------------------------------------
  document.getElementById("filter-search").addEventListener("input", debounce(applyFilters, 200));
  document.getElementById("filter-status").addEventListener("change", applyFilters);
  document.getElementById("filter-network").addEventListener("change", applyFilters);
  document.getElementById("filter-score").addEventListener("change", applyFilters);

  function debounce(fn, delay) {
    var timer;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(fn, delay);
    };
  }

  // -----------------------------------------------------------------------
  // Keyboard shortcuts
  // -----------------------------------------------------------------------
  document.addEventListener("keydown", function (e) {
    // Escape closes panel
    if (e.key === "Escape") {
      closeDetail();
      return;
    }

    // Don't navigate if typing in an input
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;

    // Arrow up/down to navigate agencies
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (filtered.length === 0) return;
      if (e.key === "ArrowDown") {
        selectedIndex = Math.min(selectedIndex + 1, filtered.length - 1);
      } else {
        selectedIndex = Math.max(selectedIndex - 1, 0);
      }
      openDetail(filtered[selectedIndex].slug);
    }
  });

  // -----------------------------------------------------------------------
  // Close events
  // -----------------------------------------------------------------------
  document.getElementById("panel-close").addEventListener("click", closeDetail);
  document.getElementById("overlay").addEventListener("click", closeDetail);

  // -----------------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------------
  initMap();
  loadAgencies();

})();
