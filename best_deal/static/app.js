(function () {
  const { esc } = Charts;
  const COLORS = { Grab: "var(--grab)", Gojek: "var(--gojek)", ComfortDelGro: "var(--comfort)" };
  const colorOf = (p) => COLORS[p] || "var(--muted)";
  const money = (v) => (v == null ? "–" : `$${Number(v).toFixed(2)}`);
  const $ = (sel) => document.querySelector(sel);
  // Show ride times in the trip's own timezone (as stored), not the browser's.
  const localDate = (iso) => new Date(iso.slice(0, 16));
  const fmtTime = (iso) => localDate(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const fmtDateTime = (iso) => localDate(iso).toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  const state = { result: null, sort: "best", providers: new Set(), seats: "all" };

  async function api(path, body) {
    const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`);
    return data;
  }

  /* ---------- Tabs ---------- */
  function showView(name) {
    document.querySelectorAll(".tab").forEach((t) => {
      const on = t.dataset.view === name;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on);
    });
    document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== `view-${name}`));
    if (name === "history") loadHistory();
    if (name === "insights") loadInsights();
  }
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showView(t.dataset.view)));

  /* ---------- Search ---------- */
  api("/api/places?limit=50").then((places) => {
    $("#places").innerHTML = places.map((p) => `<option value="${esc(p.name)}"></option>`).join("");
  });

  $("#swap").addEventListener("click", () => {
    const f = $("#search-form");
    [f.origin.value, f.destination.value] = [f.destination.value, f.origin.value];
  });

  $("#search-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    const body = { origin: f.origin.value, destination: f.destination.value, when: f.when.value || null };
    const btn = f.querySelector(".go");
    btn.disabled = true;
    btn.textContent = "Searching…";
    try {
      const [result, timeline] = await Promise.all([api("/api/search", body), api("/api/timeline", body)]);
      state.result = result;
      state.providers = new Set(result.quotes.map((q) => q.provider));
      renderResults();
      renderTimeline(timeline);
      renderRouteHistory(result.trip.route_key);
      showView("search");
    } catch (err) {
      $("#search-empty").innerHTML = `<p class="error">${esc(err.message)}</p>`;
      $("#search-empty").hidden = false;
      $("#search-results").hidden = true;
    } finally {
      btn.disabled = false;
      btn.textContent = "Search";
    }
  });

  function visibleQuotes() {
    return state.result.quotes.filter((q) =>
      state.providers.has(q.provider) &&
      (state.seats === "all" || (state.seats === "4" ? q.seats <= 4 : q.seats >= 6)));
  }

  function totalTime(q) { return q.pickup_eta_min + q.trip_min; }

  function bestScore(quotes) {
    const prices = quotes.map((q) => q.price), times = quotes.map(totalTime);
    const [lp, hp, lt, ht] = [Math.min(...prices), Math.max(...prices), Math.min(...times), Math.max(...times)];
    return (q) => 0.7 * (hp > lp ? (q.price - lp) / (hp - lp) : 0) + 0.3 * (ht > lt ? (totalTime(q) - lt) / (ht - lt) : 0);
  }

  function renderResults() {
    const r = state.result;
    $("#search-empty").hidden = true;
    $("#search-results").hidden = false;
    $("#trip-summary").innerHTML = `
      <span class="route">${esc(r.trip.origin.name)} → ${esc(r.trip.destination.name)}</span>
      <span class="muted">${r.trip.distance_km} km · ~${Math.round(r.trip.duration_min)} min drive · ${esc(fmtDateTime(r.trip.when))}</span>
      <span class="muted small">Saved as search #${r.search_id}</span>`;

    const providers = [...new Set(r.quotes.map((q) => q.provider))];
    $("#provider-filters").innerHTML = providers.map((p) => `
      <label><input type="checkbox" value="${esc(p)}" ${state.providers.has(p) ? "checked" : ""}>
      <span class="dot" style="background:${colorOf(p)}"></span>${esc(p)}</label>`).join("");
    $("#provider-filters").querySelectorAll("input").forEach((cb) => cb.addEventListener("change", () => {
      cb.checked ? state.providers.add(cb.value) : state.providers.delete(cb.value);
      renderList();
    }));
    renderList();
  }

  document.querySelectorAll('input[name="seats"]').forEach((r) => r.addEventListener("change", () => {
    state.seats = r.value;
    renderList();
  }));

  function renderList() {
    const quotes = visibleQuotes();
    const list = $("#quote-list");
    if (!quotes.length) {
      $("#sort-tabs").innerHTML = "";
      list.innerHTML = '<p class="muted">No options match these filters.</p>';
      return;
    }
    const score = bestScore(quotes);
    const sorters = {
      best: (a, b) => score(a) - score(b),
      cheapest: (a, b) => a.price - b.price || a.pickup_eta_min - b.pickup_eta_min,
      fastest: (a, b) => totalTime(a) - totalTime(b) || a.price - b.price,
    };
    const tops = Object.fromEntries(Object.entries(sorters).map(([k, f]) => [k, [...quotes].sort(f)[0]]));
    $("#sort-tabs").innerHTML = ["best", "cheapest", "fastest"].map((k) => `
      <button class="sort-tab ${state.sort === k ? "active" : ""}" data-sort="${k}">
        <span class="label">${k[0].toUpperCase() + k.slice(1)}</span>
        <span class="val">${money(tops[k].price)}</span>
        <span class="sub">${esc(tops[k].provider)} · ${Math.round(totalTime(tops[k]))} min</span>
      </button>`).join("");
    $("#sort-tabs").querySelectorAll(".sort-tab").forEach((b) => b.addEventListener("click", () => {
      state.sort = b.dataset.sort;
      renderList();
    }));

    const sorted = [...quotes].sort(sorters[state.sort]);
    list.innerHTML = sorted.map((q) => {
      const tags = Object.entries(tops).filter(([, t]) => t === q).map(([k]) => `<span class="chip tag">${k}</span>`).join("");
      const range = q.price_low !== q.price_high ? `<div class="range">${money(q.price_low)} – ${money(q.price_high)}</div>` : "";
      const surge = q.surge > 1.01 ? `<span>${q.provider === "ComfortDelGro" && q.product === "Metered Taxi" ? "surcharge" : "surge"} ×${q.surge.toFixed(2)}</span>` : "";
      return `
      <article class="quote" data-id="${q.id}">
        <div class="logo ${esc(q.provider)}" aria-hidden="true">${esc(q.provider[0])}</div>
        <div>
          <div class="q-title">${esc(q.provider)} · ${esc(q.product)}</div>
          <div class="q-meta">
            <span>${q.seats} seats</span>
            <span>pickup ~${Math.round(q.pickup_eta_min)} min</span>
            <span>arrive in ~${Math.round(totalTime(q))} min</span>
            ${surge}
          </div>
          <div class="chips">${tags}${q.notes.map((n) => `<span class="chip">${esc(n)}</span>`).join("")}<span class="chip">${esc(q.source)}</span></div>
        </div>
        <div class="q-price">
          <div><div class="amt">${money(q.price)}</div>${range}</div>
          <div class="q-actions">
            <button class="btn" data-action="observe">Record actual</button>
            ${q.deeplink ? `<a class="btn primary" href="${esc(q.deeplink)}">Open app</a>` : ""}
          </div>
        </div>
      </article>`;
    }).join("");
    list.querySelectorAll('[data-action="observe"]').forEach((b) => b.addEventListener("click", () => openObserve(b.closest(".quote"))));
  }

  function openObserve(card) {
    if (card.querySelector(".observe")) return;
    const q = state.result.quotes.find((x) => String(x.id) === card.dataset.id);
    const form = document.createElement("form");
    form.className = "observe";
    form.innerHTML = `
      <span>Price shown in ${esc(q.provider)} for ${esc(q.product)}:</span>
      <label>$ <input name="price" type="number" step="0.1" min="0.1" required value="${q.price.toFixed(2)}" aria-label="Observed price"></label>
      <label>pickup <input name="eta" type="number" step="1" min="0" placeholder="min" aria-label="Observed pickup minutes"></label>
      <button class="btn primary" type="submit">Save</button>
      <button class="btn" type="button" data-cancel>Cancel</button>
      <span class="msg"></span>`;
    card.appendChild(form);
    form.price.select();
    form.querySelector("[data-cancel]").addEventListener("click", () => form.remove());
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const saved = await api("/api/observations", {
          search_id: state.result.search_id, provider: q.provider, product: q.product,
          price: parseFloat(form.price.value), pickup_eta_min: form.eta.value ? parseFloat(form.eta.value) : null,
        });
        const err = saved.estimate_error_pct;
        form.innerHTML = `<span class="observed-ok">✓ Saved ${money(saved.price)} for ${esc(q.product)}${err != null ? ` (estimate was ${err > 0 ? "under" : "over"} by ${Math.abs(err)}%)` : ""}.</span>`;
      } catch (err) {
        form.querySelector(".msg").innerHTML = `<span class="error">${esc(err.message)}</span>`;
      }
    });
  }

  function renderTimeline(t) {
    const providers = [...new Set(t.slots.flatMap((s) => Object.keys(s.prices)))];
    const labels = t.slots.map((s) => fmtTime(s.when));
    const now = t.slots[0];
    const nowBest = Math.min(...Object.values(now.prices));
    const c = t.cheapest;
    const saving = nowBest - c.price;
    $("#timeline-callout").innerHTML = saving >= 0.5
      ? `Waiting until <b>${esc(fmtTime(c.when))}</b> could save about <b>${money(saving)}</b> (${esc(c.provider)} from ${money(c.price)}).`
      : `Now is about as cheap as it gets in the next 12 hours (from ${money(nowBest)}).`;
    Charts.lineChart($("#timeline-chart"), {
      categories: labels,
      series: providers.map((p) => ({ name: p, color: colorOf(p), values: t.slots.map((s) => s.prices[p] ?? null) })),
      yFormat: (v) => `$${v.toFixed(v < 10 ? 2 : 0)}`,
      xLabelEvery: 4,
      ariaLabel: "Cheapest estimated fare per provider over the next 12 hours",
    });
  }

  async function renderRouteHistory(routeKey) {
    const rows = await api(`/api/searches?limit=20&route_key=${encodeURIComponent(routeKey)}`);
    const panel = $("#route-history-panel");
    if (rows.length < 2) { panel.hidden = true; return; }
    panel.hidden = false;
    const prices = rows.map((r) => r.best_price).filter((v) => v != null);
    $("#route-history").innerHTML = `
      <p class="muted small">${rows.length} searches on this route · lowest seen ${money(Math.min(...prices))} · highest ${money(Math.max(...prices))}</p>
      ${historyTable(rows.slice(0, 8))}`;
  }

  /* ---------- History ---------- */
  function historyTable(rows) {
    if (!rows.length) return '<p class="muted">No searches yet.</p>';
    return `<div class="table-scroll"><table>
      <thead><tr><th>#</th><th>Ride time</th><th>Route</th><th class="num">km</th><th>Cheapest</th><th class="num">Price</th><th class="num">Observed</th></tr></thead>
      <tbody>${rows.map((r) => `
        <tr>
          <td>${r.id}</td>
          <td>${esc(fmtDateTime(r.trip_time))}</td>
          <td>${esc(r.origin_name)} → ${esc(r.dest_name)}</td>
          <td class="num">${r.distance_km.toFixed(1)}</td>
          <td><span class="dot" style="background:${colorOf(r.best_provider)}"></span>${esc(r.best_provider || "–")}</td>
          <td class="num">${money(r.best_price)}</td>
          <td class="num">${r.observed || ""}</td>
        </tr>`).join("")}</tbody></table></div>`;
  }

  async function loadHistory() {
    $("#history-table").innerHTML = historyTable(await api("/api/searches?limit=100"));
  }

  /* ---------- Insights ---------- */
  $("#insight-source").addEventListener("change", loadInsights);

  async function loadInsights() {
    const d = await api(`/api/insights?source=${$("#insight-source").value}`);
    const s = d.summary;
    $("#stat-tiles").innerHTML = [
      ["Searches recorded", s.searches],
      ["Real prices observed", s.observed_quotes],
      ["Routes", s.routes],
      ["Avg saving vs priciest", s.avg_spread == null ? "–" : money(s.avg_spread)],
    ].map(([k, v]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
    $("#findings").innerHTML = d.findings.map((f) => `<li>${esc(f)}</li>`).join("");

    Charts.barChart($("#wins-chart"), d.providers.filter((p) => p.win_rate != null).map((p) => ({
      label: p.provider, value: p.win_rate, color: colorOf(p.provider),
      detail: `Cheapest in ${p.wins} searches<br>Avg ${money(p.avg_price)} · ${p.avg_price_per_km?.toFixed(2)}/km<br>Avg surge ×${p.avg_surge?.toFixed(2) ?? "–"}`,
    })), { format: (v) => `${Math.round(v * 100)}%`, max: 1, ariaLabel: "Share of searches each provider was cheapest" });

    const hourLabels = [...Array(24).keys()].map((h) => `${String(h).padStart(2, "0")}:00`);
    Charts.lineChart($("#hourly-chart"), {
      categories: hourLabels,
      series: Object.entries(d.hourly).map(([p, pts]) => ({ name: p, color: colorOf(p), values: pts.map((x) => x.avg_price_per_km) })),
      yFormat: (v) => `$${v.toFixed(2)}`,
      xLabelEvery: 3,
      ariaLabel: "Average price per km by hour and provider",
    });

    Charts.heatmap($("#heatmap"), d.heatmap.map((c) => ({ ...c, value: c.avg_price_per_km })), {
      format: (v) => `$${v.toFixed(2)}`, ariaLabel: "Cheapest price per km by weekday and hour",
    });

    $("#routes-table").innerHTML = d.routes.length ? `<div class="table-scroll"><table>
      <thead><tr><th>Route</th><th class="num">Searches</th><th class="num">Avg best</th><th class="num">Range</th><th>Usually cheapest</th><th>Cheapest hour</th><th>Priciest hour</th></tr></thead>
      <tbody>${d.routes.map((r) => `<tr>
        <td>${esc(r.route)}</td><td class="num">${r.searches}</td><td class="num">${money(r.avg_best_price)}</td>
        <td class="num">${money(r.min_best_price)}–${money(r.max_best_price)}</td>
        <td><span class="dot" style="background:${colorOf(r.usual_winner)}"></span>${esc(r.usual_winner)} (${Math.round(r.usual_winner_share * 100)}%)</td>
        <td>${String(r.cheapest_hour).padStart(2, "0")}:00 · ${money(r.cheapest_hour_avg)}</td>
        <td>${String(r.priciest_hour).padStart(2, "0")}:00 · ${money(r.priciest_hour_avg)}</td></tr>`).join("")}</tbody></table></div>`
      : '<p class="muted">No routes yet.</p>';

    $("#calibration-table").innerHTML = d.calibration.length ? `<div class="table-scroll"><table>
      <thead><tr><th>Provider</th><th>Product</th><th class="num">Samples</th><th class="num">Observed ÷ estimate</th><th class="num">Mean error</th></tr></thead>
      <tbody>${d.calibration.map((c) => `<tr>
        <td><span class="dot" style="background:${colorOf(c.provider)}"></span>${esc(c.provider)}</td><td>${esc(c.product)}</td>
        <td class="num">${c.samples}</td><td class="num">×${c.median_ratio.toFixed(3)}</td><td class="num">${c.mean_abs_error_pct}%</td></tr>`).join("")}</tbody></table></div>`
      : '<p class="muted">No observed prices yet. Use "Record actual" on a result after checking the app.</p>';
  }
})();
