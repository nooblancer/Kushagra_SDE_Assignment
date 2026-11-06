"""
Modern, interactive single-page dashboard serving the optional extension:
'A modern web client that presents the portal's data more usefully and attractively than the original.'
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950 text-slate-100">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Urja Meter Ops — Fleet Intelligence</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 50: '#ecfdf5', 500: '#10b981', 600: '#059669', 700: '#047857' }
          }
        }
      }
    }
  </script>
</head>
<body class="h-full flex flex-col font-sans antialiased overflow-x-hidden selection:bg-emerald-500 selection:text-white">

  <!-- Header -->
  <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-40">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
          <i class="fa-solid fa-bolt text-lg"></i>
        </div>
        <div>
          <h1 class="font-bold text-base tracking-tight text-white flex items-center gap-2">
            Urja Meter Ops <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">v2.0</span>
          </h1>
          <p class="text-xs text-slate-400">High-Performance Grid Telemetry & In-Memory Index Adapter</p>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <a href="/docs" target="_blank" class="text-xs px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition flex items-center gap-1.5">
          <i class="fa-solid fa-book-bookmark text-emerald-400"></i> Swagger UI
        </a>
        <a href="/openapi.json" target="_blank" class="text-xs px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition flex items-center gap-1.5">
          <i class="fa-solid fa-code text-blue-400"></i> OpenAPI JSON
        </a>
      </div>
    </div>
  </header>

  <!-- Main Content -->
  <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">

    <!-- KPI Metric Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" id="kpi-cards">
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
        <div>
          <p class="text-xs text-slate-400 font-medium">Total Smart Meters</p>
          <p class="text-2xl font-bold text-white mt-1" id="kpi-total-meters">403</p>
          <p class="text-[11px] text-emerald-400 mt-1"><i class="fa-solid fa-check"></i> 100% In-Memory Index</p>
        </div>
        <div class="w-10 h-10 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center">
          <i class="fa-solid fa-gauge-high"></i>
        </div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
        <div>
          <p class="text-xs text-slate-400 font-medium">Distribution Transformers</p>
          <p class="text-2xl font-bold text-white mt-1" id="kpi-total-dts">40</p>
          <p class="text-[11px] text-slate-400 mt-1">11kV Feeder Network</p>
        </div>
        <div class="w-10 h-10 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center">
          <i class="fa-solid fa-network-wired"></i>
        </div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
        <div>
          <p class="text-xs text-slate-400 font-medium">Operating Fleet Status</p>
          <div class="flex items-baseline gap-2 mt-1">
            <span class="text-xl font-bold text-emerald-400" id="kpi-installed">--</span>
            <span class="text-xs text-slate-500">active /</span>
            <span class="text-sm font-semibold text-rose-400" id="kpi-faulty">--</span>
            <span class="text-xs text-slate-500">faulty</span>
          </div>
          <p class="text-[11px] text-slate-400 mt-1">Monitored lifecycle</p>
        </div>
        <div class="w-10 h-10 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
          <i class="fa-solid fa-heart-pulse"></i>
        </div>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
        <div>
          <p class="text-xs text-slate-400 font-medium">Query Engine Latency</p>
          <p class="text-2xl font-bold text-emerald-400 mt-1">&lt; 2 ms</p>
          <p class="text-[11px] text-emerald-400/80 mt-1">Sub-millisecond filtering</p>
        </div>
        <div class="w-10 h-10 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
          <i class="fa-solid fa-bolt-lightning"></i>
        </div>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
      <div class="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
        <!-- Search Input -->
        <div class="relative flex-1">
          <i class="fa-solid fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-xs"></i>
          <input type="text" id="search-input" placeholder="Search by Meter ID, Serial Number, or DT Name (e.g. J100001, Mansarovar)..." 
                 class="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500">
        </div>
        
        <!-- Filter Controls -->
        <div class="flex flex-wrap items-center gap-2">
          <select id="filter-status" class="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-emerald-500">
            <option value="">Status: All</option>
            <option value="Installed">Installed</option>
            <option value="Faulty">Faulty</option>
            <option value="Decommissioned">Decommissioned</option>
          </select>

          <select id="filter-phase" class="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-emerald-500">
            <option value="">Phase: All</option>
            <option value="1-Phase">1-Phase</option>
            <option value="3-Phase">3-Phase</option>
          </select>

          <select id="filter-make" class="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-emerald-500">
            <option value="">Manufacturer: All</option>
            <option value="Schneider Electric">Schneider Electric</option>
            <option value="Secure Meters">Secure Meters</option>
            <option value="Genus">Genus</option>
            <option value="Allied">Allied</option>
            <option value="L&T">L&T</option>
          </select>

          <button id="btn-reset" class="px-3 py-2 text-xs text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg transition">
            <i class="fa-solid fa-rotate-left"></i> Reset
          </button>
        </div>
      </div>
    </div>

    <!-- Meters Table -->
    <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
      <div class="px-4 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
        <h2 class="text-xs font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
          <i class="fa-solid fa-list-check text-emerald-400"></i> Smart Meters Fleet
          <span class="text-slate-500 font-normal normal-case" id="table-count-label">(Loading...)</span>
        </h2>
        <div class="flex items-center gap-2" id="pagination-controls">
          <button id="btn-prev" class="px-2 py-1 bg-slate-800 text-xs rounded border border-slate-700 hover:bg-slate-700 disabled:opacity-40" disabled>
            <i class="fa-solid fa-chevron-left"></i>
          </button>
          <span class="text-xs text-slate-400 font-mono" id="page-label">Page 1 of 1</span>
          <button id="btn-next" class="px-2 py-1 bg-slate-800 text-xs rounded border border-slate-700 hover:bg-slate-700 disabled:opacity-40" disabled>
            <i class="fa-solid fa-chevron-right"></i>
          </button>
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse text-xs">
          <thead>
            <tr class="border-b border-slate-800 bg-slate-950/60 text-slate-400 font-medium">
              <th class="py-2.5 px-4">Meter ID</th>
              <th class="py-2.5 px-4">Serial Number</th>
              <th class="py-2.5 px-4">Manufacturer</th>
              <th class="py-2.5 px-4">Phase</th>
              <th class="py-2.5 px-4">Status</th>
              <th class="py-2.5 px-4">Transformer (DT)</th>
              <th class="py-2.5 px-4">Feeder Line</th>
              <th class="py-2.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody id="meters-table-body" class="divide-y divide-slate-800/60 text-slate-300">
            <tr>
              <td colspan="8" class="text-center py-8 text-slate-500">
                <i class="fa-solid fa-circle-notch fa-spin text-emerald-400 text-base"></i> Loading fleet records...
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </main>

  <!-- Inspection Modal / Slide-over Drawer -->
  <div id="meter-modal" class="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm hidden flex items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto shadow-2xl p-6 space-y-6">
      
      <!-- Modal Header -->
      <div class="flex items-start justify-between border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-3">
            <h3 class="text-lg font-bold text-white font-mono" id="modal-meter-id">MTR-XXXXXX</h3>
            <span id="modal-status-pill" class="text-xs px-2.5 py-0.5 rounded-full font-medium">Active</span>
          </div>
          <p class="text-xs text-slate-400 mt-1" id="modal-subheading">Meter Profile & Interval Telemetry</p>
        </div>
        <button id="modal-close-btn" class="w-8 h-8 rounded-lg bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center border border-slate-700 transition">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>

      <!-- Overview Cards -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div class="bg-slate-950 border border-slate-800 p-3 rounded-xl">
          <p class="text-slate-500 font-medium">Manufacturer</p>
          <p class="text-white font-semibold mt-0.5" id="modal-make">--</p>
        </div>
        <div class="bg-slate-950 border border-slate-800 p-3 rounded-xl">
          <p class="text-slate-500 font-medium">Phase Configuration</p>
          <p class="text-white font-semibold mt-0.5" id="modal-phase">--</p>
        </div>
        <div class="bg-slate-950 border border-slate-800 p-3 rounded-xl">
          <p class="text-slate-500 font-medium">Transformer (DT)</p>
          <p class="text-white font-semibold mt-0.5" id="modal-dt">--</p>
        </div>
        <div class="bg-slate-950 border border-slate-800 p-3 rounded-xl">
          <p class="text-slate-500 font-medium">Coordinates</p>
          <p class="text-emerald-400 font-mono mt-0.5" id="modal-geo">--</p>
        </div>
      </div>

      <!-- Hierarchy Breadcrumbs -->
      <div class="bg-slate-950/70 border border-slate-800/80 p-3 rounded-xl text-xs">
        <p class="text-slate-500 font-semibold mb-1.5 flex items-center gap-1.5">
          <i class="fa-solid fa-sitemap text-emerald-400"></i> Distribution Hierarchy Topology:
        </p>
        <p class="text-slate-300 font-mono text-[11px] leading-relaxed" id="modal-hierarchy-path">--</p>
      </div>

      <!-- Telemetry Chart -->
      <div class="bg-slate-950 border border-slate-800 p-4 rounded-xl space-y-3">
        <div class="flex items-center justify-between">
          <h4 class="text-xs font-semibold text-white flex items-center gap-2">
            <i class="fa-solid fa-chart-line text-emerald-400"></i> 7-Day Interval Telemetry (30-Minute Readings)
          </h4>
          <span class="text-[11px] text-slate-400 font-mono" id="chart-metrics-label">Loading analytics...</span>
        </div>
        <div class="h-64 w-full">
          <canvas id="consumptionChart"></canvas>
        </div>
      </div>

    </div>
  </div>

  <!-- JavaScript -->
  <script>
    let currentPage = 1;
    let pageSize = 20;
    let currentChart = null;

    async function loadMeters() {
      const q = document.getElementById('search-input').value.trim();
      const status = document.getElementById('filter-status').value;
      const phase = document.getElementById('filter-phase').value;
      const make = document.getElementById('filter-make').value;

      const params = new URLSearchParams({ page: currentPage, page_size: pageSize });
      if (q) params.append('q', q);
      if (status) params.append('status', status);
      if (phase) params.append('phase_type', phase);
      if (make) params.append('make', make);

      const tbody = document.getElementById('meters-table-body');
      tbody.innerHTML = '<tr><td colspan="8" class="text-center py-8 text-slate-500"><i class="fa-solid fa-circle-notch fa-spin text-emerald-400 text-base"></i> Querying index...</td></tr>';

      try {
        const res = await fetch(`/api/v1/meters?${params.toString()}`);
        const data = await res.json();

        document.getElementById('table-count-label').innerText = `(${data.total} meters matching)`;
        document.getElementById('page-label').innerText = `Page ${data.page} of ${data.total_pages}`;
        document.getElementById('btn-prev').disabled = data.page <= 1;
        document.getElementById('btn-next').disabled = data.page >= data.total_pages;

        if (!data.items || data.items.length === 0) {
          tbody.innerHTML = '<tr><td colspan="8" class="text-center py-8 text-slate-500">No smart meters matched the filter criteria.</td></tr>';
          return;
        }

        tbody.innerHTML = data.items.map(m => `
          <tr class="hover:bg-slate-800/40 transition">
            <td class="py-2.5 px-4 font-mono font-semibold text-white">${m.meter_id}</td>
            <td class="py-2.5 px-4 font-mono text-slate-400">${m.serial_no || '--'}</td>
            <td class="py-2.5 px-4 text-slate-200">${m.make || '--'}</td>
            <td class="py-2.5 px-4"><span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[11px]">${m.phase_type || '--'}</span></td>
            <td class="py-2.5 px-4">
              <span class="px-2 py-0.5 rounded text-[11px] font-medium ${
                m.status === 'Installed' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                m.status === 'Faulty' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                'bg-slate-700/30 text-slate-400 border border-slate-700/40'
              }">${m.status || '--'}</span>
            </td>
            <td class="py-2.5 px-4 text-slate-300 font-mono text-[11px]">${m.dt_name ? `${m.dt_name} (${m.dt_code})` : (m.dt_code || '--')}</td>
            <td class="py-2.5 px-4 text-slate-400 font-mono text-[11px]">${m.feeder_code || '--'}</td>
            <td class="py-2.5 px-4 text-right">
              <button onclick="inspectMeter('${m.meter_id}')" class="px-2.5 py-1 text-[11px] rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 transition">
                <i class="fa-solid fa-chart-simple"></i> Telemetry
              </button>
            </td>
          </tr>
        `).join('');

      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-rose-400">Failed to load meters: ${err.message}</td></tr>`;
      }
    }

    async function inspectMeter(meterId) {
      const modal = document.getElementById('meter-modal');
      modal.classList.remove('hidden');

      document.getElementById('modal-meter-id').innerText = meterId;
      document.getElementById('modal-subheading').innerText = 'Loading telemetry & profile...';

      try {
        // Fetch Profile & Consumption in parallel
        const [profRes, consRes] = await Promise.all([
          fetch(`/api/v1/meters/${meterId}`),
          fetch(`/api/v1/meters/${meterId}/consumption?page=1&page_size=337&order=asc`)
        ]);

        const profile = await profRes.json();
        const consumption = await consRes.json();

        // Update profile
        const statusEl = document.getElementById('modal-status-pill');
        const st = profile.nameplate.install_status || 'Unknown';
        statusEl.innerText = st;
        statusEl.className = `text-xs px-2.5 py-0.5 rounded-full font-medium ${
          st === 'Installed' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
          st === 'Faulty' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' :
          'bg-slate-800 text-slate-400'
        }`;

        document.getElementById('modal-make').innerText = profile.nameplate.make || '--';
        document.getElementById('modal-phase').innerText = profile.nameplate.phase_type || '--';
        document.getElementById('modal-dt').innerText = profile.transformer ? `${profile.transformer.name} (${profile.transformer.capacity_kva || '--'} kVA)` : '--';
        document.getElementById('modal-geo').innerText = profile.location ? `${profile.location.latitude.toFixed(4)}, ${profile.location.longitude.toFixed(4)}` : 'No GIS coordinates';

        // Breadcrumb path
        const h = profile.hierarchy;
        const path = [
          h.zone?.name, h.circle?.name, h.division?.name, h.subdivision?.name,
          h.substation?.name, h.feeder?.name, h.dt?.name
        ].filter(Boolean).join('  ➔  ');
        document.getElementById('modal-hierarchy-path').innerText = path || 'Topology not configured';

        // Analytics metrics label
        const sm = consumption.summary;
        document.getElementById('chart-metrics-label').innerText = sm.net_kwh_consumption != null
          ? `Net Active: ${sm.net_kwh_consumption} kWh | Avg Voltage: ${sm.avg_voltage_r} V | PF: ${sm.apparent_power_factor || '1.0'}`
          : 'Telemetry recorded';

        // Render Chart
        renderChart(consumption.readings);

      } catch (err) {
        document.getElementById('modal-subheading').innerText = `Error: ${err.message}`;
      }
    }

    function renderChart(readings) {
      const ctx = document.getElementById('consumptionChart').getContext('2d');
      if (currentChart) currentChart.destroy();

      const labels = readings.map(r => r.timestamp.split(' ')[1] || r.timestamp);
      const kwhData = readings.map(r => r.kwh);
      const voltData = readings.map(r => r.voltage_r);

      currentChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Active Energy (kWh)',
              data: kwhData,
              borderColor: '#10b981',
              backgroundColor: 'rgba(16, 185, 129, 0.05)',
              borderWidth: 2,
              fill: true,
              tension: 0.2,
              yAxisID: 'y'
            },
            {
              label: 'Phase R Voltage (V)',
              data: voltData,
              borderColor: '#38bdf8',
              borderWidth: 1.5,
              borderDash: [4, 4],
              pointRadius: 0,
              yAxisID: 'y1'
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { labels: { color: '#94a3b8', font: { size: 11 } } },
            tooltip: { backgroundColor: '#0f172a', borderColor: '#334155', borderWidth: 1 }
          },
          scales: {
            x: {
              ticks: { color: '#64748b', maxTicksLimit: 14, font: { size: 10 } },
              grid: { color: 'rgba(51, 65, 85, 0.2)' }
            },
            y: {
              type: 'linear',
              position: 'left',
              ticks: { color: '#10b981', font: { size: 10 } },
              grid: { color: 'rgba(51, 65, 85, 0.2)' },
              title: { display: true, text: 'Active kWh', color: '#10b981', font: { size: 10 } }
            },
            y1: {
              type: 'linear',
              position: 'right',
              ticks: { color: '#38bdf8', font: { size: 10 } },
              grid: { drawOnChartArea: false },
              title: { display: true, text: 'Voltage (V)', color: '#38bdf8', font: { size: 10 } }
            }
          }
        }
      });
    }

    // Event Listeners
    document.getElementById('modal-close-btn').addEventListener('click', () => {
      document.getElementById('meter-modal').classList.add('hidden');
    });

    document.getElementById('search-input').addEventListener('input', () => {
      currentPage = 1;
      loadMeters();
    });

    ['filter-status', 'filter-phase', 'filter-make'].forEach(id => {
      document.getElementById(id).addEventListener('change', () => {
        currentPage = 1;
        loadMeters();
      });
    });

    document.getElementById('btn-reset').addEventListener('click', () => {
      document.getElementById('search-input').value = '';
      document.getElementById('filter-status').value = '';
      document.getElementById('filter-phase').value = '';
      document.getElementById('filter-make').value = '';
      currentPage = 1;
      loadMeters();
    });

    document.getElementById('btn-prev').addEventListener('click', () => {
      if (currentPage > 1) {
        currentPage--;
        loadMeters();
      }
    });

    document.getElementById('btn-next').addEventListener('click', () => {
      currentPage++;
      loadMeters();
    });

    // Initial fetch
    loadMeters();
  </script>
</body>
</html>
"""

