const PAGE = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Project 04 — Performance &amp; Analysis</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/exceljs@4.4.0/dist/exceljs.min.js"></script>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #eef1f6; color: #1a1a1a; }
  .wrap { max-width: 1400px; margin: 0 auto; padding: 0 24px 40px; }

  .hero { background: linear-gradient(120deg, #4338ca 0%, #6d28d9 45%, #7c3aed 100%); color: #fff; padding: 28px 24px; margin-bottom: 24px; }
  .hero .wrap { padding: 0 24px; }
  .hero h1 { font-size: 24px; margin: 0 0 6px; font-weight: 700; letter-spacing: -0.01em; }
  .hero .updated { display: inline-flex; align-items: center; gap: 8px; background: rgba(255,255,255,0.14); padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500; }
  .hero .agent-scope-badge { display: inline-flex; align-items: center; gap: 8px; background: #fbbf24; color: #1a1a1a; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 700; margin-left: 10px; }
  .hero .updated .dot { width: 8px; height: 8px; border-radius: 50%; background: #4ade80; box-shadow: 0 0 0 3px rgba(74,222,128,0.3); }

  .date-bar { display: flex; align-items: center; gap: 14px; margin-bottom: 22px; flex-wrap: wrap; }
  .day-label { font-size: 11px; color: #9ca3af; font-weight: 700; letter-spacing: 0.06em; }
  .day-status { font-size: 15px; color: #ea580c; font-weight: 800; letter-spacing: 0.02em; }
  .day-status.past { color: #6b7280; }
  .date-bar input[type=date] { padding: 8px 12px; border-radius: 8px; border: 1px solid #d8dce5; font-size: 13px; background: #fff; }
  .date-bar button { padding: 8px 16px; border-radius: 8px; border: 1px solid #d8dce5; background: #fff; font-size: 13px; cursor: pointer; font-weight: 600; color: #444; }
  .date-bar button.active { background: #4338ca; color: #fff; border-color: #4338ca; }
  .date-bar .spacer { flex: 1; }
  .date-bar .stat { font-size: 13px; color: #555; }
  .date-bar .stat b { color: #1a1a1a; font-weight: 700; }

  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 18px; }
  @media (max-width: 1100px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
  @media (max-width: 560px) { .kpi-grid { grid-template-columns: 1fr; } }
  .kpi-grid.row2 { grid-template-columns: repeat(3, 1fr); margin-top: 18px; margin-bottom: 28px; }
  @media (max-width: 900px) { .kpi-grid.row2 { grid-template-columns: repeat(2, 1fr); } }
  .kpi { background: #fff; border-radius: 12px; padding: 22px 18px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.06); border-left: 4px solid #ccc; }
  .kpi .dash { width: 28px; height: 3px; border-radius: 2px; margin: 0 auto 12px; }
  .kpi .value { font-size: 22px; font-weight: 800; color: #111; letter-spacing: -0.01em; }
  .kpi .label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; font-weight: 700; margin-top: 8px; }
  .kpi .desc { font-size: 11px; color: #9ca3af; margin-top: 4px; }
  .kpi.c-green { border-left-color: #10b981; } .kpi.c-green .dash { background: #10b981; } .kpi.c-green .value { color: #059669; }
  .kpi.c-red { border-left-color: #e11d48; } .kpi.c-red .dash { background: #e11d48; } .kpi.c-red .value { color: #be123c; }
  .kpi.c-amber { border-left-color: #f59e0b; } .kpi.c-amber .dash { background: #f59e0b; } .kpi.c-amber .value { color: #b45309; }
  .kpi.c-pink { border-left-color: #ec4899; } .kpi.c-pink .dash { background: #ec4899; } .kpi.c-pink .value { color: #be185d; }
  .kpi.c-sky { border-left-color: #0ea5e9; } .kpi.c-sky .dash { background: #0ea5e9; } .kpi.c-sky .value { color: #0369a1; }
  .kpi.c-orange { border-left-color: #f97316; } .kpi.c-orange .dash { background: #f97316; } .kpi.c-orange .value { color: #c2410c; }
  .kpi.c-purple { border-left-color: #7c3aed; } .kpi.c-purple .dash { background: #7c3aed; } .kpi.c-purple .value { color: #6d28d9; }
  .kpi.c-emerald2 { border-left-color: #10b981; } .kpi.c-emerald2 .dash { background: #10b981; } .kpi.c-emerald2 .value { color: #047857; }

  .su-searchbar { display: flex; align-items: center; gap: 10px; background: #fff; border: 1px solid #d8dce5; border-radius: 12px; padding: 6px 6px 6px 16px; margin: 4px 0 22px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); max-width: 560px; }
  .su-searchbar-icon { font-size: 16px; color: #9ca3af; }
  .su-searchbar input { flex: 1; border: none; outline: none; font-size: 15px; padding: 10px 0; background: transparent; }
  .su-searchbar button { padding: 12px 26px; border: none; border-radius: 9px; background: #4338ca; color: #fff; font-weight: 700; font-size: 14px; cursor: pointer; }
  .su-searchbar button:disabled { background: #a5a6f0; cursor: default; }
  .su-searchbar button:hover:not(:disabled) { background: #3730a3; }

  .su-reassign-card { background: #f8f9fc; border: 1px solid #e5e7eb; border-radius: 12px; padding: 14px 16px; margin: 0 0 22px; max-width: 560px; }
  .su-reassign-title { display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; color: #374151; margin-bottom: 10px; }
  .su-reassign-title .badge { width: 24px; height: 24px; border-radius: 6px; background: #dbeafe; display: flex; align-items: center; justify-content: center; font-size: 12px; }
  .su-reassign-row { display: flex; align-items: center; gap: 8px; flex-wrap: nowrap; }
  .su-reassign-row input, .su-reassign-row select { border: 1px solid #d8dce5; border-radius: 8px; padding: 9px 10px; font-size: 13px; background: #fff; }
  .su-reassign-row input { width: 110px; flex: none; }
  .su-reassign-row select { width: 150px; flex: none; }
  .su-reassign-row button { padding: 9px 16px; border: none; border-radius: 8px; background: #2563eb; color: #fff; font-weight: 700; font-size: 13px; cursor: pointer; white-space: nowrap; }
  .su-reassign-row button:disabled { background: #93b4e8; cursor: default; }
  .su-reassign-row button:hover:not(:disabled) { background: #1d4ed8; }
  .su-reassign-msg { margin-top: 10px; font-size: 13px; }
  .su-reassign-msg.ok { color: #059669; }
  .su-reassign-msg.err { color: #991b1b; }

  .su-ban-card { border-color: #fecdd3; background: #fff5f5; }
  .su-ban-card .su-reassign-title .badge { background: #fecdd3; }
  .su-ban-note { font-size: 12px; color: #9f1239; margin-bottom: 10px; max-width: 480px; }
  .su-ban-btn { background: #be123c !important; }
  .su-ban-btn:hover:not(:disabled) { background: #9f1239 !important; }
  .su-ban-btn:disabled { background: #fca5a5 !important; }

  .su-state { padding: 30px; text-align: center; color: #6b7280; font-size: 14px; }
  .su-state-error { color: #991b1b; background: #fef2f2; border-radius: 10px; font-weight: 600; }

  .su-profile-card { background: #fff; border-radius: 14px; padding: 24px 28px; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); border-left: 5px solid #4338ca; }
  .su-profile-top { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; }
  .su-profile-id { font-size: 22px; font-weight: 800; color: #111; letter-spacing: -0.01em; }
  .su-profile-meta { font-size: 13px; color: #6b7280; margin-top: 6px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .su-profile-balance { text-align: right; }
  .su-profile-balance .lbl { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #9ca3af; }
  .su-profile-balance .amt { font-size: 26px; font-weight: 800; color: #0369a1; letter-spacing: -0.01em; }

  .su-fin-panel { background: #fff; border-radius: 14px; padding: 18px 24px; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .su-fin-section + .su-fin-section { margin-top: 16px; padding-top: 16px; border-top: 1px solid #eef0f4; }
  .su-fin-section-title { font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; margin-bottom: 12px; }
  .su-fin-section-title .su-fin-note { font-weight: 500; text-transform: none; letter-spacing: 0; color: #9ca3af; margin-left: 4px; }
  .su-fin-stats { display: flex; flex-wrap: wrap; gap: 28px; }
  .su-fin-stat { min-width: 130px; }
  .su-fin-label { font-size: 12px; color: #6b7280; margin-bottom: 4px; }
  .su-fin-value { font-size: 19px; font-weight: 800; letter-spacing: -0.01em; }
  .su-fin-value.c-green { color: #059669; }
  .su-fin-value.c-red { color: #be123c; }
  .su-fin-value.c-blue { color: #0369a1; }
  @media (max-width: 640px) { .su-fin-stats { gap: 18px; } .su-profile-balance { text-align: left; } }

  .su-vip-badge { padding: 8px 18px; border-radius: 20px; font-weight: 800; font-size: 13px; white-space: nowrap; }
  .su-vip-standard { background: #e5e7eb; color: #374151; }
  .su-vip-gold { background: #dbeafe; color: #1e40af; }
  .su-vip-elite { background: #ede9fe; color: #6d28d9; }

  .su-pill { padding: 3px 10px; border-radius: 20px; font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: 0.02em; white-space: nowrap; }
  .su-pill-green { background: #d1fae5; color: #065f46; }
  .su-pill-blue { background: #dbeafe; color: #1e40af; }
  .su-pill-amber { background: #fef3c7; color: #92400e; }
  .su-pill-red { background: #fee2e2; color: #991b1b; }
  .su-pill-grey { background: #e5e7eb; color: #374151; }

  .reactivation-highlight { display: flex; align-items: baseline; gap: 18px; background: #ecfeff; border-radius: 10px; padding: 14px 18px; margin-bottom: 14px; flex-wrap: wrap; }
  .reactivation-highlight .rh-count { font-size: 28px; font-weight: 800; color: #0e7490; letter-spacing: -0.01em; }
  .reactivation-highlight .rh-count small { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #0e7490; margin-left: 6px; }
  .reactivation-highlight .rh-pct { font-size: 20px; font-weight: 800; color: #0891b2; }
  .reactivation-highlight .rh-pct small { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #0891b2; margin-left: 4px; }

  .net-flow { display: flex; align-items: center; justify-content: space-between; background: #f3f4f6; border-radius: 10px; padding: 12px 18px; margin-bottom: 18px; flex-wrap: wrap; gap: 10px; }
  .net-flow .nf-label { font-size: 11px; font-weight: 700; letter-spacing: 0.06em; color: #6b7280; }
  .net-flow .nf-stats { display: flex; gap: 24px; font-size: 13px; color: #444; }
  .net-flow .nf-stats b { color: #1a1a1a; }
  .net-flow .nf-stats b.pos { color: #059669; }
  .net-flow .nf-stats b.neg { color: #be123c; }

  .analysis-heading { display: flex; align-items: center; gap: 10px; margin: 30px 0 14px; }
  .analysis-heading h2 { font-size: 15px; margin: 0; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; color: #374151; }
  .analysis-heading .line { flex: 1; height: 1px; background: #dfe3ea; }
  .analysis-heading .tag { font-size: 11px; padding: 3px 10px; border-radius: 20px; font-weight: 700; }
  .analysis-heading.deposit .tag { background: #d1fae5; color: #065f46; }
  .analysis-heading.withdrawal .tag { background: #fee2e2; color: #991b1b; }
  .today-tag { font-size: 11px; padding: 3px 10px; border-radius: 20px; font-weight: 700; background: #e0e7ff; color: #3730a3; }

  .row2col { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }
  @media (max-width: 1000px) { .row2col { grid-template-columns: 1fr; } }

  section { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px 18px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); border-left: 4px solid #6366f1; }
  section.acc-blue { border-left-color: #3b82f6; }
  section.acc-purple { border-left-color: #8b5cf6; }
  section.acc-orange { border-left-color: #f59e0b; }
  section.acc-rose { border-left-color: #f43f5e; }
  section.acc-cyan { border-left-color: #06b6d4; }
  section.acc-emerald { border-left-color: #10b981; }
  .sec-title { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; }
  .sec-title .badge { width: 26px; height: 26px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }
  .sec-title h2 { font-size: 14px; margin: 0; font-weight: 700; }
  .badge.b-blue { background: #dbeafe; }
  .badge.b-purple { background: #ede9fe; }
  .badge.b-orange { background: #fef3c7; }
  .badge.b-indigo { background: #e0e7ff; }
  .badge.b-rose { background: #ffe4e6; }
  .badge.b-cyan { background: #cffafe; }
  .badge.b-emerald { background: #d1fae5; }

  .section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
  .download-btn { padding: 7px 14px; border-radius: 20px; border: none; background: linear-gradient(135deg, #10b981, #059669); color: #fff; font-size: 12px; cursor: pointer; font-weight: 600; box-shadow: 0 2px 8px rgba(16,185,129,0.3); }
  .download-btn:hover { filter: brightness(1.05); }
  .download-btn-sm { padding: 5px 11px; border-radius: 16px; border: none; background: linear-gradient(135deg, #10b981, #059669); color: #fff; font-size: 11px; cursor: pointer; font-weight: 600; white-space: nowrap; }
  .download-btn-sm:hover { filter: brightness(1.05); }

  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 7px 9px; border: 1px solid #edeff3; }
  th { color: #6b7280; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em; position: sticky; top: 0; background: #f9fafb; cursor: pointer; }
  tbody tr:hover { background: #f8f9fc; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .bar-cell { position: relative; }
  .bar { position: absolute; left: 0; top: 0; bottom: 0; background: #ddeaff; z-index: 0; border-radius: 4px; }
  .bar-cell span { position: relative; z-index: 1; }
  .table-wrap { max-height: 420px; overflow: auto; }
  canvas { max-height: 280px; }
  .loading { padding: 60px; text-align: center; color: #888; }
  .no-data { color: #999; font-style: italic; padding: 12px 0; }

  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }
  .sub-table h3 { font-size: 12px; color: #444; margin: 0 0 8px; font-weight: 700; }
  .pct-good { color: #15803d; font-weight: 700; }
  .pct-mid { color: #a16207; font-weight: 700; }
  .pct-bad { color: #b91c1c; font-weight: 700; }

  .heat-legend { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #666; margin-bottom: 12px; flex-wrap: wrap; }
  .chip { padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
  .chip.good { background: #bbf7d0; color: #166534; }
  .chip.mid { background: #fef08a; color: #854d0e; }
  .chip.bad { background: #fecaca; color: #991b1b; }
  .chip.none { background: #eee; color: #999; }
  .heat-table { border-collapse: collapse; font-size: 12px; }
  .heat-table th, .heat-table td { padding: 6px 9px; text-align: center; border: 1px solid #edeff3; white-space: nowrap; border-radius: 4px; }
  .heat-table th.row-label, .heat-table td.row-label { text-align: left; position: sticky; left: 0; background: #fff; z-index: 2; font-weight: 500; }
  .heat-table th { position: sticky; top: 0; background: #f9fafb; z-index: 1; }
  .heat-table th.row-label { z-index: 3; }
  .heat-table th.row-total, .heat-table td.row-total { font-weight: 700; background: #f9fafb; }

  .layout { display: flex; align-items: flex-start; max-width: 1560px; margin: 0 auto; }
  .sidebar { width: 190px; flex-shrink: 0; padding: 20px 12px; position: sticky; top: 0; }
  .sidebar .nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-radius: 8px; color: #444; text-decoration: none; font-size: 13px; font-weight: 600; margin-bottom: 6px; }
  .sidebar .nav-item:hover { background: #e5e7eb; }
  .sidebar .nav-item.active { background: #4338ca; color: #fff; }
  .main { flex: 1; min-width: 0; }

  .ac-note { font-size: 11px; color: #9ca3af; margin: -6px 0 10px; font-style: italic; }
  .ac-pagination { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 10px; font-size: 12px; color: #666; }
  .ac-pagination button { padding: 5px 12px; border-radius: 16px; border: 1px solid #d8dce5; background: #fff; font-size: 12px; cursor: pointer; font-weight: 600; color: #444; }
  .ac-pagination button:disabled { opacity: 0.4; cursor: default; }
  .badge.b-indigo2 { background: #e0e7ff; }

  .date-switch { display: flex; gap: 8px; margin-bottom: 18px; flex-wrap: wrap; }
  .date-switch button { padding: 8px 16px; border-radius: 20px; border: 1px solid #d8dce5; background: #fff; font-size: 13px; cursor: pointer; font-weight: 600; color: #444; }
  .date-switch button.active { background: #4338ca; color: #fff; border-color: #4338ca; }

  .perf-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 12px 16px; margin-bottom: 20px; }
  .perf-controls input[type=date] { border: 1px solid #d8dce5; border-radius: 8px; padding: 8px 10px; font-size: 13px; }
  .perf-controls .perf-to { color: #9ca3af; font-size: 12px; font-weight: 700; }
  .perf-preset { padding: 7px 14px; border-radius: 18px; border: 1px solid #d8dce5; background: #f9fafb; font-size: 12px; cursor: pointer; font-weight: 700; color: #444; }
  .perf-preset.active { background: #4338ca; color: #fff; border-color: #4338ca; }

  .perf-podium { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 26px; }
  @media (max-width: 900px) { .perf-podium { grid-template-columns: 1fr; } }
  .perf-podium-card { border-radius: 16px; padding: 20px 18px; color: #fff; position: relative; overflow: hidden; box-shadow: 0 6px 20px rgba(0,0,0,0.12); }
  .perf-podium-card.p1 { background: linear-gradient(145deg, #f5c542, #d4941f); order: 2; transform: scale(1.05); }
  .perf-podium-card.p2 { background: linear-gradient(145deg, #b8c2cc, #8a97a3); order: 1; }
  .perf-podium-card.p3 { background: linear-gradient(145deg, #d0925a, #a86a37); order: 3; }
  @media (max-width: 900px) { .perf-podium-card.p1, .perf-podium-card.p2, .perf-podium-card.p3 { order: initial; transform: none; } }
  .perf-podium-medal { font-size: 30px; }
  .perf-podium-name { font-size: 18px; font-weight: 800; margin-top: 4px; }
  .perf-podium-score { font-size: 34px; font-weight: 900; margin-top: 8px; letter-spacing: -0.02em; }
  .perf-podium-score small { font-size: 13px; font-weight: 700; opacity: 0.85; margin-left: 4px; }
  .perf-podium-incentive { margin-top: 12px; background: rgba(255,255,255,0.22); border-radius: 10px; padding: 8px 12px; font-size: 13px; font-weight: 700; }
  .perf-podium-incentive .amt { font-size: 20px; font-weight: 900; display: block; }
  .perf-podium-none { margin-top: 12px; font-size: 12px; opacity: 0.85; font-style: italic; }

  .perf-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px 18px; margin-bottom: 12px; display: flex; align-items: center; gap: 16px; }
  .perf-card .perf-rank { width: 34px; height: 34px; border-radius: 50%; background: #f3f4f6; color: #444; font-weight: 800; font-size: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .perf-card .perf-rank.top3 { background: linear-gradient(145deg, #4338ca, #6366f1); color: #fff; }
  .perf-card .perf-agent-name { font-weight: 800; font-size: 14px; color: #1a1a1a; min-width: 140px; }
  .perf-card .perf-score-big { font-size: 20px; font-weight: 900; min-width: 70px; text-align: right; }
  .perf-criteria-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; flex: 1; }
  @media (max-width: 1100px) { .perf-criteria-grid { grid-template-columns: repeat(4, 1fr); } }
  .perf-crit { font-size: 10px; color: #6b7280; }
  .perf-crit .pc-label { font-weight: 700; text-transform: uppercase; letter-spacing: 0.02em; font-size: 9px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .perf-crit .pc-value { font-weight: 800; font-size: 12px; color: #1a1a1a; margin: 2px 0; }
  .perf-bar { height: 6px; border-radius: 4px; background: #eef0f4; overflow: hidden; }
  .perf-bar-fill { height: 100%; border-radius: 4px; }
  .perf-bar-fill.pb-green { background: #10b981; }
  .perf-bar-fill.pb-amber { background: #f59e0b; }
  .perf-bar-fill.pb-red { background: #e11d48; }
  .perf-bar-fill.pb-na { background: #d1d5db; }
  .perf-crit-na .pc-value { color: #9ca3af; font-style: italic; font-size: 10px; }
  .perf-incentive-chip { padding: 4px 10px; border-radius: 14px; font-size: 11px; font-weight: 800; white-space: nowrap; }
  .perf-incentive-chip.tier1 { background: #dbeafe; color: #1e40af; }
  .perf-incentive-chip.tier2 { background: #ede9fe; color: #6d28d9; }
  .perf-incentive-chip.tier3 { background: #fef3c7; color: #92400e; }
  .perf-legend { display: flex; gap: 18px; flex-wrap: wrap; font-size: 12px; color: #6b7280; margin: 4px 0 20px; }
  .perf-legend span { display: inline-flex; align-items: center; gap: 6px; }
  .perf-legend i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
</style>
</head>
<body>
<div class="hero">
  <div class="wrap">
    <h1>Project 04 &mdash; Performance &amp; Analysis</h1>
    <div class="updated" id="updated-badge"><span class="dot"></span> Loading&hellip;</div>
    <div class="agent-scope-badge" id="agent-scope-badge" style="display:none"></div>
  </div>
</div>
<div class="layout">
  <nav class="sidebar">
    <a href="/" class="nav-item" id="nav-home">&#127968; Home</a>
    <a href="/action-center" class="nav-item" id="nav-action-center">&#9889; Action Center</a>
    <a href="/performance" class="nav-item" id="nav-performance">&#127942; Performance</a>
    <a href="/analytics" class="nav-item" id="nav-analytics">&#128202; Analytics</a>
    <a href="/platform-analysis" class="nav-item" id="nav-platform-analysis">&#127918; Platform Analysis</a>
    <a href="/search-user" class="nav-item" id="nav-search-user">&#128269; Search User</a>
  </nav>
  <div class="main">
    <div class="wrap" id="home-wrap">
      <div class="date-bar" id="date-bar" style="display:none">
        <div class="day-label">DAY</div>
        <div class="day-status" id="day-status">TODAY</div>
        <input type="date" id="date-picker">
        <button id="btn-today">Reset to Today</button>
        <div class="spacer"></div>
        <div class="stat">Total Users: <b id="stat-total-users">&mdash;</b></div>
        <div class="stat">Registered Active: <b id="stat-registered-active">&mdash;</b></div>
      </div>
      <div id="app" class="loading">Loading report data&hellip;</div>
    </div>
    <div class="wrap" id="action-center-wrap" style="display:none">
      <div id="action-center-app" class="loading">Loading report data&hellip;</div>
    </div>
    <div class="wrap" id="performance-wrap" style="display:none">
      <div id="performance-app" class="loading">Loading report data&hellip;</div>
    </div>
    <div class="wrap" id="analytics-wrap" style="display:none">
      <div id="analytics-app" class="loading">Loading report data&hellip;</div>
    </div>
    <div class="wrap" id="platform-analysis-wrap" style="display:none">
      <div id="platform-analysis-app" class="loading">Loading report data&hellip;</div>
    </div>
    <div class="wrap" id="search-user-wrap" style="display:none">
      <div id="search-user-app"></div>
    </div>
  </div>
</div>

<script>
function fmt(n) { return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 }); }
function money(n) { return '₹' + fmt(n); }

function sortableTable(container, headers, rows, rowRenderer, numericCols) {
  let sortCol = null, sortDir = -1;
  function render() {
    let data = rows.slice();
    if (sortCol !== null) {
      data.sort((a, b) => {
        const av = a[sortCol], bv = b[sortCol];
        if (typeof av === 'number') return (av - bv) * sortDir;
        return String(av).localeCompare(String(bv)) * sortDir;
      });
    }
    const thead = '<thead><tr>' + headers.map((h, i) =>
      '<th data-i="' + i + '"' + (numericCols && numericCols.includes(i) ? ' class="num"' : '') + '>' +
      h + (sortCol === i ? (sortDir === 1 ? ' ▲' : ' ▼') : '') + '</th>'
    ).join('') + '</tr></thead>';
    const tbody = '<tbody>' + data.map(rowRenderer).join('') + '</tbody>';
    container.innerHTML = '<div class="table-wrap"><table>' + thead + tbody + '</table></div>';
    container.querySelectorAll('th').forEach(th => {
      th.addEventListener('click', () => {
        const i = Number(th.dataset.i);
        if (sortCol === i) sortDir *= -1; else { sortCol = i; sortDir = -1; }
        render();
      });
    });
  }
  render();
}

const EMPTY_SCOPE = {
  totals: { count: 0, total_amount: 0 }, by_channel: [], by_amount_range: [], by_channel_and_range: [], hourly: [],
  success_by_range: [], success_by_channel: [], hourly_success_by_channel: [], hourly_success_by_range: [],
  withdrawal_review_by_channel: [], withdrawal_completion_by_channel: [], withdrawal_orders: [],
  summary: {
    total_deposit: 0, total_withdraw: 0, deposit_orders: 0, withdraw_orders: 0,
    deposit_users: 0, withdraw_users: 0, active_users: 0, difference: 0, withdraw_deposit_pct: null,
  },
};

function pctClass(pct) {
  if (pct >= 41) return 'pct-good';
  if (pct >= 30) return 'pct-mid';
  return 'pct-bad';
}
function heatColor(total, pct) {
  if (!total) return { bg: '#f3f4f6', color: '#bbb' };
  if (pct >= 41) return { bg: '#bbf7d0', color: '#166534' };
  if (pct >= 30) return { bg: '#fef08a', color: '#854d0e' };
  return { bg: '#fecaca', color: '#991b1b' };
}

function todayLocalISO() {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

// Per-agent dashboards live under /agent/<encoded-name>(/<page>)? -- the
// name is URL-decoded directly from the path (no lookup table/file needed)
// and must match an agent_assignments value exactly, since that's the key
// build_deposit_report.py slugified when uploading reports/agent/*.json.
const AGENT_URL_MATCH = location.pathname.match(/^\\/agent\\/([^/]+)(\\/(action-center|analytics|search-user))?\\/?$/);
const AGENT_NAME = AGENT_URL_MATCH ? decodeURIComponent(AGENT_URL_MATCH[1]) : null;
const IS_AGENT_SCOPED = !!AGENT_NAME;
const AGENT_SUBPAGE = AGENT_URL_MATCH ? (AGENT_URL_MATCH[3] || '') : '';
function agentUrl(page) {
  return '/agent/' + encodeURIComponent(AGENT_NAME) + (page ? '/' + page : '');
}

const IS_ACTION_CENTER = IS_AGENT_SCOPED ? AGENT_SUBPAGE === 'action-center' : location.pathname.indexOf('/action-center') === 0;
const IS_PERFORMANCE = !IS_AGENT_SCOPED && location.pathname.indexOf('/performance') === 0;
const IS_ANALYTICS = IS_AGENT_SCOPED ? AGENT_SUBPAGE === 'analytics' : location.pathname.indexOf('/analytics') === 0;
const IS_PLATFORM_ANALYSIS = !IS_AGENT_SCOPED && location.pathname.indexOf('/platform-analysis') === 0;
const IS_SEARCH_USER = IS_AGENT_SCOPED ? AGENT_SUBPAGE === 'search-user' : location.pathname.indexOf('/search-user') === 0;
document.getElementById(IS_SEARCH_USER ? 'nav-search-user' : (IS_PLATFORM_ANALYSIS ? 'nav-platform-analysis' : (IS_ANALYTICS ? 'nav-analytics' : (IS_PERFORMANCE ? 'nav-performance' : (IS_ACTION_CENTER ? 'nav-action-center' : 'nav-home'))))).classList.add('active');
document.getElementById('home-wrap').style.display = (IS_ACTION_CENTER || IS_PERFORMANCE || IS_ANALYTICS || IS_PLATFORM_ANALYSIS || IS_SEARCH_USER) ? 'none' : '';
document.getElementById('action-center-wrap').style.display = IS_ACTION_CENTER ? '' : 'none';
document.getElementById('performance-wrap').style.display = IS_PERFORMANCE ? '' : 'none';
document.getElementById('analytics-wrap').style.display = IS_ANALYTICS ? '' : 'none';
document.getElementById('platform-analysis-wrap').style.display = IS_PLATFORM_ANALYSIS ? '' : 'none';
document.getElementById('search-user-wrap').style.display = IS_SEARCH_USER ? '' : 'none';

// Client-side deterrent only (this is a static page, no real auth backend) --
// gates the Ban User/Reassign Agent actions and the whole Platform Analysis
// page behind a shared PIN.
const ACTION_PASSWORD = '3177';
function checkActionPassword(msgEl, actionLabel) {
  const entered = prompt('Enter password to ' + actionLabel + ':');
  if (entered === null) return false; // cancelled
  if (entered !== ACTION_PASSWORD) {
    msgEl.textContent = 'Access Denied';
    msgEl.className = 'su-reassign-msg err';
    return false;
  }
  return true;
}

if (IS_AGENT_SCOPED) {
  document.getElementById('nav-home').href = agentUrl('');
  document.getElementById('nav-action-center').href = agentUrl('action-center');
  document.getElementById('nav-analytics').href = agentUrl('analytics');
  document.getElementById('nav-search-user').href = agentUrl('search-user');
  // Performance stays a global, unscoped link (full cross-agent leaderboard,
  // by design) -- Platform Analysis is hidden entirely for agent dashboards.
  document.getElementById('nav-platform-analysis').style.display = 'none';
  const badge = document.getElementById('agent-scope-badge');
  badge.textContent = 'Agent: ' + AGENT_NAME;
  badge.style.display = '';
}

// Filters every per-row "agent"-tagged section of the (already-fetched,
// global) report down to one agent's own users -- reused across Action
// Center, Analytics, and Weekly Cashback Shield, all of which already ship
// an "agent" field per row and need no separate per-agent backend file.
// cohort_size/pct_converted/pct_reactivated/pct_upgraded are intentionally
// left as the GLOBAL platform-wide rate: the true agent-specific cohort
// (including non-converted members) isn't shipped to the browser at all,
// so recomputing them here would either be wrong or require guessing.
function scopeReportToAgent(data, agentName) {
  if (!agentName) return data;
  const filterRows = rows => (rows || []).filter(r => r.agent === agentName);
  const scoped = { ...data };

  if (scoped.action_center) {
    const ac = scoped.action_center;
    const acOut = {};
    for (const key of ['near_upgrade_low', 'near_upgrade_high', 'inactive_high', 'inactive_low', 'active_low', 'active_high']) {
      if (!ac[key]) continue;
      const rows = filterRows(ac[key].rows);
      acOut[key] = { ...ac[key], rows, total_matching: rows.length };
    }
    scoped.action_center = acOut;
  }

  if (scoped.action_center_extra) {
    scoped.action_center_extra = {
      ...scoped.action_center_extra,
      yesterday_first_deposit_users: filterRows(scoped.action_center_extra.yesterday_first_deposit_users),
      deposit_challenge_bonus: filterRows(scoped.action_center_extra.deposit_challenge_bonus),
    };
  }

  if (scoped.weekly_cashback_shield) {
    const rows = filterRows(scoped.weekly_cashback_shield.rows);
    scoped.weekly_cashback_shield = {
      ...scoped.weekly_cashback_shield,
      rows,
      eligible_count: rows.length,
      total_bonus: Math.round(rows.reduce((s, r) => s + r.bonus_amount, 0) * 100) / 100,
    };
  }

  for (const key of ['reactivation', 'vip_upgrade']) {
    if (!scoped[key]) continue;
    const out = { ...scoped[key] };
    for (const tier of ['low', 'high']) {
      if (!scoped[key][tier]) continue;
      const rows = filterRows(scoped[key][tier].rows);
      out[tier] = { ...scoped[key][tier], rows };
      if (key === 'reactivation') out[tier].reactivated_count = rows.length;
      if (key === 'vip_upgrade') out[tier].upgraded_count = rows.length;
    }
    scoped[key] = out;
  }

  if (scoped.retention) {
    const out = { ...scoped.retention };
    for (const sub of ['first_deposit', 'bonus_claimer']) {
      if (!scoped.retention[sub]) continue;
      const rows = filterRows(scoped.retention[sub].rows);
      out[sub] = { ...scoped.retention[sub], rows, converted_count: rows.length };
    }
    scoped.retention = out;
  }

  if (scoped.premium_active) {
    const out = { ...scoped.premium_active };
    for (const tier of ['low', 'high']) {
      if (!scoped.premium_active[tier]) continue;
      const rows = filterRows(scoped.premium_active[tier].rows);
      out[tier] = { ...scoped.premium_active[tier], rows, converted_count: rows.length };
    }
    scoped.premium_active = out;
  }

  if (scoped.withdrawal_orders_full) {
    scoped.withdrawal_orders_full = filterRows(scoped.withdrawal_orders_full);
  }

  if (scoped.by_date) {
    const byDateOut = {};
    for (const [date, dayData] of Object.entries(scoped.by_date)) {
      byDateOut[date] = { ...dayData, withdrawal_orders: filterRows(dayData.withdrawal_orders) };
    }
    scoped.by_date = byDateOut;
  }

  return scoped;
}

function paginatedTable(containerId, paginationId, rows, columns, pageSize) {
  let page = 0;
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  function render() {
    const container = document.getElementById(containerId);
    const pageRows = rows.slice(page * pageSize, page * pageSize + pageSize);
    if (!pageRows.length) {
      container.innerHTML = '<div class="no-data">No matching users.</div>';
    } else {
      const thead = '<thead><tr>' + columns.map(c => '<th' + (c.num ? ' class="num"' : '') + '>' + c.label + '</th>').join('') + '</tr></thead>';
      const tbody = '<tbody>' + pageRows.map(r => '<tr>' + columns.map(c =>
        '<td class="' + (c.num ? 'num' : '') + '">' + c.render(r) + '</td>'
      ).join('') + '</tr>').join('') + '</tbody>';
      container.innerHTML = '<div class="table-wrap"><table>' + thead + tbody + '</table></div>';
    }
    const pag = document.getElementById(paginationId);
    pag.innerHTML = 'Page ' + (page + 1) + ' of ' + totalPages +
      ' <button id="' + paginationId + '-prev"' + (page === 0 ? ' disabled' : '') + '>&larr; Prev</button>' +
      ' <button id="' + paginationId + '-next"' + (page >= totalPages - 1 ? ' disabled' : '') + '>Next &rarr;</button>';
    const prevBtn = document.getElementById(paginationId + '-prev');
    const nextBtn = document.getElementById(paginationId + '-next');
    if (prevBtn) prevBtn.addEventListener('click', () => { page = Math.max(0, page - 1); render(); });
    if (nextBtn) nextBtn.addEventListener('click', () => { page = Math.min(totalPages - 1, page + 1); render(); });
  }
  render();
}

function shortDate(isoDateStr) {
  if (!isoDateStr) return '&mdash;';
  const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  const parts = isoDateStr.split('-');
  const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  return d.getDate() + '-' + MONTHS[d.getMonth()];
}

const HEADER_FILL = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFDBEAFE' } };

function styleHeaderRow(ws) {
  const row = ws.getRow(1);
  row.font = { bold: true };
  row.eachCell(c => { c.fill = HEADER_FILL; });
}

async function saveWorkbook(wb, filename) {
  const buf = await wb.xlsx.writeBuffer();
  const blob = new Blob([buf], { type: 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// rowObjects: array of plain objects, keys become the header row (same shape
// XLSX.utils.json_to_sheet expected) -- bold + light-blue header on every export.
async function downloadStyledExcel(rowObjects, sheetName, filename) {
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet(sheetName);
  if (rowObjects.length) {
    ws.columns = Object.keys(rowObjects[0]).map(k => ({ header: k, key: k, width: Math.max(12, k.length + 2) }));
    ws.addRows(rowObjects);
  }
  styleHeaderRow(ws);
  await saveWorkbook(wb, filename);
}

function downloadExcel(rows, columns, sheetName, filename) {
  const data = rows.map(r => {
    const obj = {};
    columns.forEach(c => { obj[c.label] = c.raw ? c.raw(r) : c.render(r); });
    return obj;
  });
  downloadStyledExcel(data, sheetName, filename);
}

if (IS_ACTION_CENTER) {
  (async () => {
    const res = await fetch('/data.json');
    if (!res.ok) {
      document.getElementById('action-center-app').textContent = 'Failed to load report data (' + res.status + ')';
      return;
    }
    const data = scopeReportToAgent(await res.json(), AGENT_NAME);
    const ac = data.action_center;
    const acx = data.action_center_extra;
    document.getElementById('updated-badge').innerHTML =
      '<span class="dot"></span> Records updated through ' +
      (data.latest_record_time ? new Date(data.latest_record_time).toLocaleString() : 'n/a');
    document.getElementById('action-center-app').className = '';

    if (!ac) {
      document.getElementById('action-center-app').innerHTML = '<div class="no-data">Action Center data not available in this report yet.</div>';
      return;
    }

    const newUserCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'VIP', render: r => (r.vip_level == null ? '&mdash;' : r.vip_level), num: true },
      { label: 'Deposit Count', render: r => fmt(r.deposit_count), raw: r => r.deposit_count, num: true },
      { label: 'Total Deposit Amount', render: r => money(r.total_deposit), raw: r => r.total_deposit, num: true },
      { label: 'Total Withdraw', render: r => money(r.total_withdraw), raw: r => r.total_withdraw, num: true },
      { label: 'Profit/Loss', render: r => money(r.profit_loss), raw: r => r.profit_loss, num: true },
      { label: 'Region', render: r => r.region || '&mdash;' },
    ];
    const bonusCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'FD Date', render: r => shortDate(r.fd_date), raw: r => r.fd_date },
      { label: 'Bonus Rule', render: r => r.rule },
      { label: 'Bonus Amount', render: r => money(r.bonus_amount), raw: r => r.bonus_amount, num: true },
    ];

    const nearCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'Current VIP Level', render: r => r.current_vip, num: true },
      { label: 'Next VIP Level', render: r => r.next_vip, num: true },
      { label: 'Total Deposit', render: r => money(r.total_deposit), raw: r => r.total_deposit, num: true },
      { label: 'Amount to Reach Next Level', render: r => money(r.amount_to_next), raw: r => r.amount_to_next, num: true },
      { label: 'Inactive Days', render: r => (r.inactive_days == null ? '&mdash;' : fmt(r.inactive_days)), raw: r => r.inactive_days, num: true },
    ];
    const inactiveCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'VIP Level', render: r => r.vip_level, num: true },
      { label: 'Total Deposit', render: r => money(r.total_deposit), raw: r => r.total_deposit, num: true },
      { label: 'Wallet Balance', render: r => money(r.wallet_balance), raw: r => r.wallet_balance, num: true },
      { label: 'Inactive Days', render: r => fmt(r.inactive_days), raw: r => r.inactive_days, num: true },
      { label: 'Last Active Date', render: r => r.last_active_date || '&mdash;', raw: r => r.last_active_date },
    ];
    const activeCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'VIP Level', render: r => r.vip_level, num: true },
      { label: 'Total Deposit', render: r => money(r.total_deposit), raw: r => r.total_deposit, num: true },
      { label: 'Wallet Balance', render: r => money(r.wallet_balance), raw: r => r.wallet_balance, num: true },
      { label: 'Inactive Days', render: r => fmt(r.inactive_days), raw: r => r.inactive_days, num: true },
    ];
    const cashbackCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'VIP', render: r => (r.vip == null ? '&mdash;' : r.vip), raw: r => r.vip, num: true },
      { label: 'Total Deposit', render: r => money(r.total_deposit), raw: r => r.total_deposit, num: true },
      { label: 'Total Withdraw', render: r => money(r.total_withdraw), raw: r => r.total_withdraw, num: true },
      { label: 'User Balance', render: r => money(r.user_balance), raw: r => r.user_balance, num: true },
      { label: 'Verified Loss', render: r => money(r.verified_loss), raw: r => r.verified_loss, num: true },
      { label: 'Eligible %', render: r => r.eligible_pct + '%', raw: r => r.eligible_pct, num: true },
      { label: 'Bonus Amount', render: r => money(r.bonus_amount), raw: r => r.bonus_amount, num: true },
    ];
    const wcs = data.weekly_cashback_shield;

    document.getElementById('action-center-app').innerHTML = \`
      \${wcs ? \`
      <div class="analysis-heading withdrawal"><h2>Weekly Cashback Shield</h2><div class="line"></div><span class="today-tag">\${shortDate(wcs.week_start)} - \${shortDate(wcs.week_end)}</span><span class="tag">ACTION CENTER</span></div>
      <section class="acc-orange">
        <div class="section-head">
          <div class="sec-title"><div class="badge b-orange">&#128737;&#65039;</div><h2>Eligible Users This Week</h2></div>
          <button class="download-btn-sm" id="btn-dl-cashback">&#128190; Excel</button>
        </div>
        <div class="reactivation-highlight">
          <div class="rh-count">\${fmt(wcs.eligible_count)}<small>Eligible Users</small></div>
          <div class="rh-pct">\${money(wcs.total_bonus)}<small>Total Bonus Payable</small></div>
        </div>
        <div class="ac-note">VIP 2+ only &middot; Loss Rs 500-4,999 (80%+ of week's deposit lost): flat 1% &middot; Loss Rs 5,000-500,000: 50%+ = 2%, 75%+ = 3%, 100% = 7% cashback &middot; credited Sunday morning, no wagering requirement</div>
        <div id="cashback-table"></div>
        <div class="ac-pagination" id="cashback-pagination"></div>
      </section>
      \` : ''}

      <div class="analysis-heading deposit"><h2>VIP Near Upgrade</h2><div class="line"></div><span class="tag">ACTION CENTER</span></div>
      <div class="row2col">
        <section class="acc-purple">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-purple">&#11014;&#65039;</div><h2>Low - VIP Near Upgrade</h2></div>
            <button class="download-btn-sm" id="btn-dl-near-low">&#128190; Excel</button>
          </div>
          <div class="ac-note">\${ac.near_upgrade_low.note} &middot; showing top \${ac.near_upgrade_low.total_matching.toLocaleString('en-IN')} matching, sorted closest-first</div>
          <div id="near-low-table"></div>
          <div class="ac-pagination" id="near-low-pagination"></div>
        </section>
        <section class="acc-purple">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-purple">&#11014;&#65039;</div><h2>High - VIP Near Upgrade</h2></div>
            <button class="download-btn-sm" id="btn-dl-near-high">&#128190; Excel</button>
          </div>
          <div class="ac-note">\${ac.near_upgrade_high.note} &middot; showing top \${ac.near_upgrade_high.total_matching.toLocaleString('en-IN')} matching, sorted closest-first</div>
          <div id="near-high-table"></div>
          <div class="ac-pagination" id="near-high-pagination"></div>
        </section>
      </div>

      <div class="analysis-heading withdrawal"><h2>Inactive Users</h2><div class="line"></div><span class="tag">ACTION CENTER</span></div>
      <div class="row2col">
        <section class="acc-rose">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-rose">&#128564;</div><h2>Inactive Users - High</h2></div>
            <button class="download-btn-sm" id="btn-dl-inactive-high">&#128190; Excel</button>
          </div>
          <div class="ac-note">\${ac.inactive_high.note} &middot; showing top \${ac.inactive_high.total_matching.toLocaleString('en-IN')} matching, most-inactive-first</div>
          <div id="inactive-high-table"></div>
          <div class="ac-pagination" id="inactive-high-pagination"></div>
        </section>
        <section class="acc-rose">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-rose">&#128564;</div><h2>Inactive Users - Low</h2></div>
            <button class="download-btn-sm" id="btn-dl-inactive-low">&#128190; Excel</button>
          </div>
          <div class="ac-note">\${ac.inactive_low.note} &middot; showing top \${ac.inactive_low.total_matching.toLocaleString('en-IN')} matching, most-inactive-first</div>
          <div id="inactive-low-table"></div>
          <div class="ac-pagination" id="inactive-low-pagination"></div>
        </section>
      </div>

      \${acx ? \`
      <div class="analysis-heading deposit"><h2>New Users &amp; Bonuses</h2><div class="line"></div><span class="tag">ACTION CENTER</span></div>
      <div class="row2col">
        <section class="acc-blue">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-blue">&#127881;</div><h2>Yesterday First Deposit Users</h2></div>
            <button class="download-btn-sm" id="btn-dl-new-users">&#128190; Excel</button>
          </div>
          <div class="ac-note">Flagged by the source system's own first-deposit marker &middot; \${acx.yesterday_first_deposit_users.length.toLocaleString('en-IN')} users</div>
          <div id="new-users-table"></div>
          <div class="ac-pagination" id="new-users-pagination"></div>
        </section>
        <section class="acc-cyan">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-cyan">&#127942;</div><h2>3-Day Deposit Challenge Bonus</h2></div>
            <button class="download-btn-sm" id="btn-dl-bonus">&#128190; Excel</button>
          </div>
          <div class="ac-note">Bonuses payable today &middot; \${acx.deposit_challenge_bonus.length.toLocaleString('en-IN')} entries</div>
          <div id="bonus-table"></div>
          <div class="ac-pagination" id="bonus-pagination"></div>
        </section>
      </div>
      \` : ''}

      <div class="analysis-heading withdrawal"><h2>Active Users</h2><div class="line"></div><span class="tag">ACTION CENTER</span></div>
      <div class="row2col">
        <section class="acc-cyan">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-cyan">&#9989;</div><h2>Low - Active Users (V2-V4)</h2></div>
            <button class="download-btn-sm" id="btn-dl-active-low">&#128190; Excel</button>
          </div>
          <div class="ac-note">\${ac.active_low.note} &middot; showing top \${ac.active_low.total_matching.toLocaleString('en-IN')} matching, most-recently-active-first</div>
          <div id="active-low-table"></div>
          <div class="ac-pagination" id="active-low-pagination"></div>
        </section>
        <section class="acc-cyan">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-cyan">&#9989;</div><h2>High - Active Users (V5-V15)</h2></div>
            <button class="download-btn-sm" id="btn-dl-active-high">&#128190; Excel</button>
          </div>
          <div class="ac-note">\${ac.active_high.note} &middot; showing top \${ac.active_high.total_matching.toLocaleString('en-IN')} matching, most-recently-active-first</div>
          <div id="active-high-table"></div>
          <div class="ac-pagination" id="active-high-pagination"></div>
        </section>
      </div>
    \`;

    if (wcs) {
      paginatedTable('cashback-table', 'cashback-pagination', wcs.rows, cashbackCols, 10);
      document.getElementById('btn-dl-cashback').addEventListener('click', () =>
        downloadExcel(wcs.rows, cashbackCols, 'Weekly Cashback Shield', 'weekly-cashback-shield-' + wcs.week_start + '.xlsx'));
    }

    paginatedTable('near-low-table', 'near-low-pagination', ac.near_upgrade_low.rows, nearCols, 10);
    paginatedTable('near-high-table', 'near-high-pagination', ac.near_upgrade_high.rows, nearCols, 10);
    paginatedTable('inactive-high-table', 'inactive-high-pagination', ac.inactive_high.rows, inactiveCols, 10);
    paginatedTable('inactive-low-table', 'inactive-low-pagination', ac.inactive_low.rows, inactiveCols, 10);

    document.getElementById('btn-dl-near-low').addEventListener('click', () =>
      downloadExcel(ac.near_upgrade_low.rows, nearCols, 'Low VIP Near Upgrade', 'low-vip-near-upgrade.xlsx'));
    document.getElementById('btn-dl-near-high').addEventListener('click', () =>
      downloadExcel(ac.near_upgrade_high.rows, nearCols, 'High VIP Near Upgrade', 'high-vip-near-upgrade.xlsx'));
    document.getElementById('btn-dl-inactive-high').addEventListener('click', () =>
      downloadExcel(ac.inactive_high.rows, inactiveCols, 'Inactive Users High', 'inactive-users-high.xlsx'));
    document.getElementById('btn-dl-inactive-low').addEventListener('click', () =>
      downloadExcel(ac.inactive_low.rows, inactiveCols, 'Inactive Users Low', 'inactive-users-low.xlsx'));

    paginatedTable('active-low-table', 'active-low-pagination', ac.active_low.rows, activeCols, 10);
    paginatedTable('active-high-table', 'active-high-pagination', ac.active_high.rows, activeCols, 10);
    document.getElementById('btn-dl-active-low').addEventListener('click', () =>
      downloadExcel(ac.active_low.rows, activeCols, 'Active Users Low', 'active-users-low.xlsx'));
    document.getElementById('btn-dl-active-high').addEventListener('click', () =>
      downloadExcel(ac.active_high.rows, activeCols, 'Active Users High', 'active-users-high.xlsx'));

    if (acx) {
      paginatedTable('new-users-table', 'new-users-pagination', acx.yesterday_first_deposit_users, newUserCols, 10);
      paginatedTable('bonus-table', 'bonus-pagination', acx.deposit_challenge_bonus, bonusCols, 10);
      document.getElementById('btn-dl-new-users').addEventListener('click', () =>
        downloadExcel(acx.yesterday_first_deposit_users, newUserCols, 'Yesterday First Deposit Users', 'yesterday-first-deposit-users.xlsx'));
      document.getElementById('btn-dl-bonus').addEventListener('click', () =>
        downloadExcel(acx.deposit_challenge_bonus, bonusCols, '3-Day Deposit Challenge Bonus', 'deposit-challenge-bonus.xlsx'));
    }
  })();
}

if (IS_PERFORMANCE) {
  (async () => {
    const res = await fetch('/data.json');
    if (!res.ok) {
      document.getElementById('performance-app').textContent = 'Failed to load report data (' + res.status + ')';
      return;
    }
    const data = await res.json();
    const perfRows = data.agent_performance || [];
    const targets = data.agent_performance_targets || {};
    const agents = (data.agent_list || []).slice();
    const categories = ['Reactivation Low', 'Reactivation High', 'Retention', 'Low VIP Upgrade', 'High VIP Upgrade', 'Low Premium Active', 'High Premium Active'];
    const allDates = Array.from(new Set(perfRows.map(r => r.date))).sort();
    const todayStr = data.report_today || allDates[allDates.length - 1];
    // Incentives are always judged on the CURRENT CALENDAR MONTH's cumulative
    // performance, independent of whatever range is picked below for
    // browsing day-to-day numbers -- so the podium never moves just because
    // someone clicked "Yesterday" to look something up.
    const monthFrom = todayStr.slice(0, 7) + '-01';
    const monthTo = todayStr;

    const el = document.getElementById('performance-app');
    el.className = '';
    el.innerHTML = \`
      <div class="analysis-heading deposit"><h2>Monthly Leaderboard &amp; Incentives</h2><div class="line"></div><span class="tag">\${shortDate(monthFrom)} - \${shortDate(monthTo)}</span></div>
      <div class="perf-legend">
        <span><i style="background:#10b981"></i> 100%+ of target</span>
        <span><i style="background:#f59e0b"></i> 60-99% of target</span>
        <span><i style="background:#e11d48"></i> Below 60%</span>
        <span><i style="background:#d1d5db"></i> No users assigned -- excluded, not counted against them</span>
        <span style="margin-left:auto">Incentive brackets (rank 1 / 2 / 3): <b class="perf-incentive-chip tier1">60%+: Rs1500/800/500</b> <b class="perf-incentive-chip tier2">75%+: Rs4000/2000/1400</b> <b class="perf-incentive-chip tier3">90%+: Rs10000/5000/2000</b></span>
      </div>
      <div id="perf-podium" class="perf-podium"></div>

      <div class="analysis-heading withdrawal"><h2>Daily / Range Performance</h2><div class="line"></div><span class="tag">7 KPIs, equal weight</span></div>
      <div class="perf-controls">
        <button class="perf-preset active" data-preset="today">Today</button>
        <button class="perf-preset" data-preset="yesterday">Yesterday</button>
        <button class="perf-preset" data-preset="7d">Last 7 Days</button>
        <button class="perf-preset" data-preset="30d">Last 30 Days</button>
        <button class="perf-preset" data-preset="35d">Last 35 Days</button>
        <span class="perf-to">|</span>
        <input type="date" id="perf-from">
        <span class="perf-to">to</span>
        <input type="date" id="perf-to">
      </div>
      <div id="perf-list"></div>
    \`;

    function fmtMoney(v) { return 'Rs' + Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 }); }
    function tierForPct(pct) {
      if (pct >= 90) return 3;
      if (pct >= 75) return 2;
      if (pct >= 60) return 1;
      return 0;
    }
    const INCENTIVE_TABLE = {
      1: [1500, 800, 500],
      2: [4000, 2000, 1400],
      3: [10000, 5000, 2000],
    };
    function barClass(pct) {
      if (pct >= 100) return 'pb-green';
      if (pct >= 60) return 'pb-amber';
      return 'pb-red';
    }

    function computeLeaderboard(fromDate, toDate) {
      const inRange = perfRows.filter(r => r.date >= fromDate && r.date <= toDate);
      const byAgentCat = {};
      for (const r of inRange) {
        if (r.agent === 'Un-Assigned') continue;
        byAgentCat[r.agent] = byAgentCat[r.agent] || {};
        const cur = byAgentCat[r.agent][r.category] || { num: 0, den: 0 };
        cur.num += r.numerator || 0;
        cur.den += r.denominator || 0;
        byAgentCat[r.agent][r.category] = cur;
      }
      const results = agents.map(agent => {
        const catData = byAgentCat[agent] || {};
        // Every APPLICABLE KPI shares an equal weight in the composite below
        // -- a KPI is "not applicable" when the agent had zero assigned/
        // eligible users for it (e.g. nobody who made a first deposit
        // yesterday, so Retention has nothing to measure). Rather than
        // scoring that as an unearnable 0%, it's excluded entirely and its
        // share redistributed across whichever KPIs DO apply, so an agent
        // is only ever judged on what was actually possible for them.
        const criteria = categories.map(cat => {
          const meta = targets[cat] || { type: 'count', target: 0 };
          const agg = catData[cat] || { num: 0, den: 0 };
          const applicable = agg.den > 0;
          let actualDisplay, pctOfTarget;
          if (meta.type === 'rate') {
            const rawRate = agg.den > 0 ? (agg.num / agg.den) * 100 : 0;
            pctOfTarget = meta.target > 0 ? (rawRate / meta.target) * 100 : 0;
            // Show the raw assigned/retained counts alongside the rate --
            // a bare percentage on a tiny cohort (e.g. 1 of 1 = "100%") reads
            // as misleading without the counts backing it up.
            actualDisplay = applicable
              ? Math.round(agg.num) + ' / ' + Math.round(agg.den) + ' (' + rawRate.toFixed(1) + '%)'
              : 'No users assigned';
          } else {
            pctOfTarget = agg.den > 0 ? (agg.num / agg.den) * 100 : 0;
            actualDisplay = Math.round(agg.num) + ' / ' + Math.round(agg.den);
          }
          return { category: cat, pctOfTarget, actualDisplay, applicable };
        });
        const applicableCriteria = criteria.filter(c => c.applicable);
        // Each KPI's contribution to the composite is capped at 100% -- a
        // single small-sample rate (e.g. 1 of 2 retained = 50%, which is
        // 167% of a 30% target) would otherwise swing the whole average on
        // its own, letting one lucky data point outrank agents who are
        // genuinely stronger across every other KPI. The uncapped
        // pctOfTarget is still shown per-KPI, so real overshoots stay
        // visible -- they just can't outweigh the rest of the scorecard.
        const composite = applicableCriteria.length
          ? applicableCriteria.reduce((s, c) => s + Math.min(c.pctOfTarget, 100), 0) / applicableCriteria.length
          : 0;
        return { agent, criteria, composite };
      });
      results.sort((a, b) => b.composite - a.composite);
      return results;
    }

    function renderPodium() {
      const ranked = computeLeaderboard(monthFrom, monthTo);
      const podiumEl = document.getElementById('perf-podium');
      const medals = ['&#129351;', '&#129352;', '&#129353;'];
      const podiumClasses = ['p1', 'p2', 'p3'];
      podiumEl.innerHTML = ranked.slice(0, 3).map((r, i) => {
        const tier = tierForPct(r.composite);
        const incentive = tier > 0 ? INCENTIVE_TABLE[tier][i] : null;
        return '<div class="perf-podium-card ' + podiumClasses[i] + '">' +
          '<div class="perf-podium-medal">' + medals[i] + '</div>' +
          '<div class="perf-podium-name">' + r.agent + '</div>' +
          '<div class="perf-podium-score">' + r.composite.toFixed(2) + '<small>% of target (month)</small></div>' +
          (incentive
            ? '<div class="perf-podium-incentive">Incentive earned<span class="amt">' + fmtMoney(incentive) + '</span></div>'
            : '<div class="perf-podium-none">Below 60% of target -- no incentive yet</div>') +
          '</div>';
      }).join('');
    }

    function render(fromDate, toDate) {
      const ranked = computeLeaderboard(fromDate, toDate);
      const listEl = document.getElementById('perf-list');

      listEl.innerHTML = ranked.map((r, i) => {
        const rankNum = i + 1;
        const critHtml = r.criteria.map(c => {
          if (!c.applicable) {
            return '<div class="perf-crit perf-crit-na">' +
              '<div class="pc-label">' + c.category + '</div>' +
              '<div class="pc-value">' + c.actualDisplay + '</div>' +
              '<div class="perf-bar"><div class="perf-bar-fill pb-na" style="width:100%"></div></div>' +
              '</div>';
          }
          const pct = Math.max(0, Math.min(c.pctOfTarget, 999));
          const barPct = Math.min(pct, 100);
          return '<div class="perf-crit">' +
            '<div class="pc-label">' + c.category + '</div>' +
            '<div class="pc-value">' + c.actualDisplay + '</div>' +
            '<div class="perf-bar"><div class="perf-bar-fill ' + barClass(pct) + '" style="width:' + barPct + '%"></div></div>' +
            '</div>';
        }).join('');
        return '<div class="perf-card">' +
          '<div class="perf-rank' + (rankNum <= 3 ? ' top3' : '') + '">' + rankNum + '</div>' +
          '<div class="perf-agent-name">' + r.agent + '</div>' +
          '<div class="perf-criteria-grid">' + critHtml + '</div>' +
          '<div class="perf-score-big" style="color:' + (r.composite >= 100 ? '#059669' : r.composite >= 60 ? '#b45309' : '#be123c') + '">' + r.composite.toFixed(2) + '%</div>' +
          '</div>';
      }).join('');
    }

    const fromInput = document.getElementById('perf-from');
    const toInput = document.getElementById('perf-to');
    const presetBtns = Array.from(document.querySelectorAll('.perf-preset'));

    function applyPreset(preset) {
      let from = todayStr, to = todayStr;
      const idx = allDates.indexOf(todayStr);
      function dateNDaysBack(n) {
        const anchorIdx = idx >= 0 ? idx : allDates.length - 1;
        const backIdx = Math.max(0, anchorIdx - (n - 1));
        return allDates[backIdx] || allDates[0];
      }
      if (preset === 'today') { from = todayStr; to = todayStr; }
      else if (preset === 'yesterday') {
        const anchorIdx = idx >= 0 ? idx : allDates.length - 1;
        const yIdx = Math.max(0, anchorIdx - 1);
        from = allDates[yIdx] || todayStr; to = from;
      }
      else if (preset === '7d') { from = dateNDaysBack(7); to = todayStr; }
      else if (preset === '30d') { from = dateNDaysBack(30); to = todayStr; }
      else if (preset === '35d') { from = allDates[0] || todayStr; to = todayStr; }
      fromInput.value = from;
      toInput.value = to;
      presetBtns.forEach(b => b.classList.toggle('active', b.dataset.preset === preset));
      render(from, to);
    }

    presetBtns.forEach(btn => btn.addEventListener('click', () => applyPreset(btn.dataset.preset)));
    fromInput.addEventListener('change', () => {
      presetBtns.forEach(b => b.classList.remove('active'));
      render(fromInput.value, toInput.value || fromInput.value);
    });
    toInput.addEventListener('change', () => {
      presetBtns.forEach(b => b.classList.remove('active'));
      render(fromInput.value || toInput.value, toInput.value);
    });

    renderPodium();
    applyPreset('today');
  })();
}

if (IS_ANALYTICS) {
  (async () => {
    const res = await fetch('/data.json');
    if (!res.ok) {
      document.getElementById('analytics-app').textContent = 'Failed to load report data (' + res.status + ')';
      return;
    }
    const globalData = await res.json();
    let data = scopeReportToAgent(globalData, AGENT_NAME);
    if (IS_AGENT_SCOPED) {
      // region_vip_analytics can't be scoped client-side (derived from raw
      // per-transaction records never shipped to the browser) -- pull it
      // from the small per-agent file instead, same pattern the Home page uses.
      const agentRes = await fetch('/data.json?agent=' + encodeURIComponent(AGENT_NAME));
      if (!agentRes.ok) {
        document.getElementById('analytics-app').textContent = 'Failed to load this agent\\'s report (' + agentRes.status + ')';
        return;
      }
      const agentData = await agentRes.json();
      data = { ...data, region_vip_analytics: agentData.region_vip_analytics };
    }
    document.getElementById('updated-badge').innerHTML =
      '<span class="dot"></span> Records updated through ' +
      (data.latest_record_time ? new Date(data.latest_record_time).toLocaleString() : 'n/a');
    document.getElementById('analytics-app').className = '';

    const rv = data.region_vip_analytics || {};
    const dates = Object.keys(rv).sort();
    if (!dates.length) {
      document.getElementById('analytics-app').innerHTML = '<div class="no-data">Analytics data not available in this report yet.</div>';
      return;
    }
    let selectedDate = dates[dates.length - 1];

    // Reactivation/VIP Upgrade/Retention/Premium Active are single "as of
    // that day" computations, overwritten every pipeline run -- so browsing
    // to a past date needs that day's own snapshot (a separate small R2
    // object per day, fetched on demand via /api/analytics-history), not
    // something derivable from the main report. Today's snapshot is already
    // sitting in the already-fetched data itself, so it's seeded here to skip a redundant fetch.
    const snapshotCache = {
      [data.report_today]: {
        reactivation: data.reactivation,
        vip_upgrade: data.vip_upgrade,
        retention: data.retention,
        premium_active: data.premium_active,
      },
    };
    function dateTag(d) {
      return '<span class="today-tag">' + (d === data.report_today ? 'TODAY: ' : 'DATE: ') + shortDate(d) + '</span>';
    }

    const reactivationCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'VIP Level', render: r => r.vip_level, num: true },
      { label: 'Inactive Days', render: r => fmt(r.inactive_days), raw: r => r.inactive_days, num: true },
      { label: 'Total Deposit Today', render: r => money(r.total_deposit), raw: r => r.total_deposit, num: true },
    ];

    const vipUpgradeCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'VIP Before', render: r => r.vip_before, num: true },
      { label: 'VIP After', render: r => r.vip_after, num: true },
      { label: 'Total Deposit Today', render: r => money(r.total_deposit), raw: r => r.total_deposit, num: true },
      { label: 'Amount Over Minimum', render: r => money(r.amount_over_minimum), raw: r => r.amount_over_minimum, num: true },
    ];

    const retentionCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'Total Deposit Today', render: r => money(r.total_deposit), raw: r => r.total_deposit, num: true },
      { label: 'Deposit Count', render: r => fmt(r.deposit_count), raw: r => r.deposit_count, num: true },
      { label: 'Region', render: r => r.region, raw: r => r.region },
    ];

    const premiumActiveCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'VIP', render: r => r.vip, raw: r => r.vip, num: true },
      { label: 'Deposit Amount', render: r => money(r.deposit_amount), raw: r => r.deposit_amount, num: true },
      { label: 'Deposit Count', render: r => fmt(r.deposit_count), raw: r => r.deposit_count, num: true },
    ];

    function funnelLine(funnel, tier) {
      if (!funnel) return '';
      const parts = ['3', '7'].map(w => {
        const f = funnel[w] && funnel[w][tier];
        return f
          ? w + '-day: <b>' + f.pct + '%</b> (' + fmt(f.converted) + ' of ' + fmt(f.cohort_size) + ')'
          : w + '-day: not enough history yet';
      });
      return '<div class="ac-note">Conversion funnel &middot; ' + parts.join(' &middot; ') + '</div>';
    }

    document.getElementById('analytics-app').innerHTML = \`
      <div class="analysis-heading deposit"><h2>Analytics</h2><div class="line"></div><span class="tag">ALL SECTIONS BELOW</span></div>
      <div class="date-switch" id="analytics-date-switch"></div>

      <div class="analysis-heading deposit"><h2>Region &amp; VIP Deposit Analytics</h2><div class="line"></div><span class="tag">ANALYTICS</span></div>
      <div class="row2col">
        <section class="acc-blue">
          <div class="sec-title"><div class="badge b-blue">&#127758;</div><h2>Top 10 Regions by Deposit</h2></div>
          <canvas id="region-chart"></canvas>
        </section>
        <section class="acc-purple">
          <div class="sec-title"><div class="badge b-purple">&#128142;</div><h2>Deposit by VIP Level</h2></div>
          <canvas id="vip-chart"></canvas>
        </section>
      </div>
      <div id="analytics-sections">\${sectionsTemplate(selectedDate, snapshotCache[selectedDate])}</div>
    \`;

    function sectionsTemplate(dateForTag, snap) {
      if (!snap) {
        return '<div class="no-data">No historical snapshot captured for this date yet -- snapshots started the day this feature shipped, so earlier dates will fill in as they occur.</div>';
      }
      const reactivation = snap.reactivation;
      const vipUpgrade = snap.vip_upgrade;
      const retention = snap.retention;
      const premiumActive = snap.premium_active;
      const todayTag = dateTag(dateForTag);
      return \`
      \${reactivation ? \`
      <div class="analysis-heading withdrawal"><h2>Reactivation</h2><div class="line"></div>\${todayTag}<span class="tag">ANALYTICS</span></div>
      <div class="row2col">
        <section class="acc-cyan">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-cyan">&#128260;</div><h2>Low V - Reactivation (V2-V4)</h2></div>
            <button class="download-btn-sm" id="btn-dl-reactivation-low">&#128190; Excel</button>
          </div>
          <div class="reactivation-highlight">
            <div class="rh-count">\${fmt(reactivation.low.reactivated_count)}<small>Reactivated Today</small></div>
            <div class="rh-pct">\${reactivation.low.pct_reactivated}%<small>of Inactive-Low Cohort</small></div>
          </div>
          <div class="ac-note">\${reactivation.low.note}</div>
          \${funnelLine(reactivation.funnel, 'low')}
          <div id="reactivation-low-table"></div>
          <div class="ac-pagination" id="reactivation-low-pagination"></div>
        </section>
        <section class="acc-cyan">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-cyan">&#128260;</div><h2>High V - Reactivation (V5-V15)</h2></div>
            <button class="download-btn-sm" id="btn-dl-reactivation-high">&#128190; Excel</button>
          </div>
          <div class="reactivation-highlight">
            <div class="rh-count">\${fmt(reactivation.high.reactivated_count)}<small>Reactivated Today</small></div>
            <div class="rh-pct">\${reactivation.high.pct_reactivated}%<small>of Inactive-High Cohort</small></div>
          </div>
          <div class="ac-note">\${reactivation.high.note}</div>
          \${funnelLine(reactivation.funnel, 'high')}
          <div id="reactivation-high-table"></div>
          <div class="ac-pagination" id="reactivation-high-pagination"></div>
        </section>
      </div>
      \` : ''}

      \${vipUpgrade ? \`
      <div class="analysis-heading deposit"><h2>VIP Level Upgrade</h2><div class="line"></div>\${todayTag}<span class="tag">ANALYTICS</span></div>
      <div class="row2col">
        <section class="acc-purple">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-purple">&#127942;</div><h2>Low - VIP Upgrade (V2-V4)</h2></div>
            <button class="download-btn-sm" id="btn-dl-vip-upgrade-low">&#128190; Excel</button>
          </div>
          <div class="reactivation-highlight">
            <div class="rh-count">\${fmt(vipUpgrade.low.upgraded_count)}<small>Upgraded Today</small></div>
            <div class="rh-pct">\${vipUpgrade.low.pct_upgraded}%<small>of Near-Upgrade Cohort</small></div>
          </div>
          <div class="ac-note">\${vipUpgrade.low.note}</div>
          \${funnelLine(vipUpgrade.funnel, 'low')}
          <div id="vip-upgrade-low-table"></div>
          <div class="ac-pagination" id="vip-upgrade-low-pagination"></div>
        </section>
        <section class="acc-purple">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-purple">&#127942;</div><h2>High - VIP Upgrade (V5-V15)</h2></div>
            <button class="download-btn-sm" id="btn-dl-vip-upgrade-high">&#128190; Excel</button>
          </div>
          <div class="reactivation-highlight">
            <div class="rh-count">\${fmt(vipUpgrade.high.upgraded_count)}<small>Upgraded Today</small></div>
            <div class="rh-pct">\${vipUpgrade.high.pct_upgraded}%<small>of Near-Upgrade Cohort</small></div>
          </div>
          <div class="ac-note">\${vipUpgrade.high.note}</div>
          \${funnelLine(vipUpgrade.funnel, 'high')}
          <div id="vip-upgrade-high-table"></div>
          <div class="ac-pagination" id="vip-upgrade-high-pagination"></div>
        </section>
      </div>
      \` : ''}

      \${retention ? \`
      <div class="analysis-heading withdrawal"><h2>Retention</h2><div class="line"></div>\${todayTag}<span class="tag">ANALYTICS</span></div>
      <div class="row2col">
        <section class="acc-emerald">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-emerald">&#127793;</div><h2>First-Deposit Day-1 Retention</h2></div>
            <button class="download-btn-sm" id="btn-dl-retention-fd">&#128190; Excel</button>
          </div>
          <div class="reactivation-highlight">
            <div class="rh-count">\${fmt(retention.first_deposit.converted_count)}<small>of \${fmt(retention.first_deposit.cohort_size)} Deposited Again</small></div>
            <div class="rh-pct">\${retention.first_deposit.pct_converted}%<small>Conversion</small></div>
            <div class="rh-pct">\${money(retention.first_deposit.avg_deposit_amount)}<small>Avg Deposit</small></div>
          </div>
          <div class="ac-note">\${retention.first_deposit.note}</div>
          <div id="retention-fd-table"></div>
          <div class="ac-pagination" id="retention-fd-pagination"></div>
        </section>
        <section class="acc-emerald">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-emerald">&#127793;</div><h2>Bonus Claimer Retention (Rs30/Rs60)</h2></div>
            <button class="download-btn-sm" id="btn-dl-retention-bonus">&#128190; Excel</button>
          </div>
          <div class="reactivation-highlight">
            <div class="rh-count">\${fmt(retention.bonus_claimer.converted_count)}<small>of \${fmt(retention.bonus_claimer.cohort_size)} Deposited Again</small></div>
            <div class="rh-pct">\${retention.bonus_claimer.pct_converted}%<small>Conversion</small></div>
            <div class="rh-pct">\${money(retention.bonus_claimer.avg_deposit_amount)}<small>Avg Deposit</small></div>
          </div>
          <div class="ac-note">\${retention.bonus_claimer.note}</div>
          <div id="retention-bonus-table"></div>
          <div class="ac-pagination" id="retention-bonus-pagination"></div>
        </section>
      </div>
      \` : ''}

      \${premiumActive ? \`
      <div class="row2col">
        <section class="acc-emerald">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-emerald">&#128142;</div><h2>Low Premium Active</h2></div>
            <button class="download-btn-sm" id="btn-dl-premium-active-low">&#128190; Excel</button>
          </div>
          <div class="reactivation-highlight">
            <div class="rh-count">\${fmt(premiumActive.low.converted_count)}<small>of \${fmt(premiumActive.low.cohort_size)} Deposited Today</small></div>
            <div class="rh-pct">\${premiumActive.low.pct_converted}%<small>Conversion</small></div>
            <div class="rh-pct">\${money(premiumActive.low.avg_deposit_amount)}<small>Avg Deposit</small></div>
          </div>
          <div class="ac-note">\${premiumActive.low.note}</div>
          <div id="premium-active-low-table"></div>
          <div class="ac-pagination" id="premium-active-low-pagination"></div>
        </section>
        <section class="acc-emerald">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-emerald">&#128142;</div><h2>High Premium Active</h2></div>
            <button class="download-btn-sm" id="btn-dl-premium-active-high">&#128190; Excel</button>
          </div>
          <div class="reactivation-highlight">
            <div class="rh-count">\${fmt(premiumActive.high.converted_count)}<small>of \${fmt(premiumActive.high.cohort_size)} Deposited Today</small></div>
            <div class="rh-pct">\${premiumActive.high.pct_converted}%<small>Conversion</small></div>
            <div class="rh-pct">\${money(premiumActive.high.avg_deposit_amount)}<small>Avg Deposit</small></div>
          </div>
          <div class="ac-note">\${premiumActive.high.note}</div>
          <div id="premium-active-high-table"></div>
          <div class="ac-pagination" id="premium-active-high-pagination"></div>
        </section>
      </div>
      \` : ''}
      \`;
    }

    function wireSections(snap) {
      if (!snap) return;
      const reactivation = snap.reactivation;
      const vipUpgrade = snap.vip_upgrade;
      const retention = snap.retention;
      const premiumActive = snap.premium_active;

      if (reactivation) {
        paginatedTable('reactivation-low-table', 'reactivation-low-pagination', reactivation.low.rows, reactivationCols, 5);
        paginatedTable('reactivation-high-table', 'reactivation-high-pagination', reactivation.high.rows, reactivationCols, 5);
        document.getElementById('btn-dl-reactivation-low').addEventListener('click', () =>
          downloadExcel(reactivation.low.rows, reactivationCols, 'Reactivation Low', 'reactivation-low.xlsx'));
        document.getElementById('btn-dl-reactivation-high').addEventListener('click', () =>
          downloadExcel(reactivation.high.rows, reactivationCols, 'Reactivation High', 'reactivation-high.xlsx'));
      }

      if (vipUpgrade) {
        paginatedTable('vip-upgrade-low-table', 'vip-upgrade-low-pagination', vipUpgrade.low.rows, vipUpgradeCols, 5);
        paginatedTable('vip-upgrade-high-table', 'vip-upgrade-high-pagination', vipUpgrade.high.rows, vipUpgradeCols, 5);
        document.getElementById('btn-dl-vip-upgrade-low').addEventListener('click', () =>
          downloadExcel(vipUpgrade.low.rows, vipUpgradeCols, 'VIP Upgrade Low', 'vip-upgrade-low.xlsx'));
        document.getElementById('btn-dl-vip-upgrade-high').addEventListener('click', () =>
          downloadExcel(vipUpgrade.high.rows, vipUpgradeCols, 'VIP Upgrade High', 'vip-upgrade-high.xlsx'));
      }

      if (retention) {
        paginatedTable('retention-fd-table', 'retention-fd-pagination', retention.first_deposit.rows, retentionCols, 5);
        paginatedTable('retention-bonus-table', 'retention-bonus-pagination', retention.bonus_claimer.rows, retentionCols, 5);
        document.getElementById('btn-dl-retention-fd').addEventListener('click', () =>
          downloadExcel(retention.first_deposit.rows, retentionCols, 'First Deposit Retention', 'retention-first-deposit.xlsx'));
        document.getElementById('btn-dl-retention-bonus').addEventListener('click', () =>
          downloadExcel(retention.bonus_claimer.rows, retentionCols, 'Bonus Claimer Retention', 'retention-bonus-claimer.xlsx'));
      }

      if (premiumActive) {
        paginatedTable('premium-active-low-table', 'premium-active-low-pagination', premiumActive.low.rows, premiumActiveCols, 5);
        paginatedTable('premium-active-high-table', 'premium-active-high-pagination', premiumActive.high.rows, premiumActiveCols, 5);
        document.getElementById('btn-dl-premium-active-low').addEventListener('click', () =>
          downloadExcel(premiumActive.low.rows, premiumActiveCols, 'Low Premium Active', 'low-premium-active.xlsx'));
        document.getElementById('btn-dl-premium-active-high').addEventListener('click', () =>
          downloadExcel(premiumActive.high.rows, premiumActiveCols, 'High Premium Active', 'high-premium-active.xlsx'));
      }
    }

    let sectionsLoadToken = 0;
    async function renderSections(date) {
      const token = ++sectionsLoadToken;
      const container = document.getElementById('analytics-sections');
      if (!(date in snapshotCache)) {
        container.innerHTML = '<div class="no-data">Loading ' + shortDate(date) + '&hellip;</div>';
        try {
          const r = await fetch('/api/analytics-history?date=' + date);
          snapshotCache[date] = r.ok ? scopeReportToAgent(await r.json(), AGENT_NAME) : null;
        } catch (e) {
          snapshotCache[date] = null;
        }
        if (token !== sectionsLoadToken) return; // a newer date was clicked meanwhile
      }
      const snap = snapshotCache[date];
      container.innerHTML = sectionsTemplate(date, snap);
      wireSections(snap);
    }

    function renderDateSwitch() {
      const el = document.getElementById('analytics-date-switch');
      el.innerHTML = dates.map(d =>
        '<button data-date="' + d + '" class="' + (d === selectedDate ? 'active' : '') + '">' + shortDate(d) + '</button>'
      ).join('');
      el.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', () => {
          selectedDate = btn.dataset.date;
          renderDateSwitch();
          renderCharts();
          renderSections(selectedDate);
        });
      });
    }

    let regionChart = null, vipChart = null;
    function renderCharts() {
      const scope = rv[selectedDate] || { top_regions: [], vip_breakdown: [] };

      if (regionChart) regionChart.destroy();
      regionChart = new Chart(document.getElementById('region-chart'), {
        type: 'bar',
        data: {
          labels: scope.top_regions.map(r => r.region + ' (' + fmt(r.user_count) + ' users)'),
          datasets: [{ label: 'Total Deposit', data: scope.top_regions.map(r => r.total_deposit), backgroundColor: '#3b82f6', borderRadius: 6 }],
        },
        options: {
          indexAxis: 'y',
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: ctx => {
              const r = scope.top_regions[ctx.dataIndex];
              return money(ctx.parsed.x) + ' · ' + fmt(r.user_count) + ' users · ' + fmt(r.count) + ' orders';
            } } },
          },
          scales: { x: { beginAtZero: true, ticks: { callback: v => money(v) } } },
        },
      });

      if (vipChart) vipChart.destroy();
      vipChart = new Chart(document.getElementById('vip-chart'), {
        type: 'bar',
        data: {
          labels: scope.vip_breakdown.map(r => 'VIP ' + r.vip_level + ' (' + fmt(r.user_count) + ' users)'),
          datasets: [{ label: 'Total Deposit', data: scope.vip_breakdown.map(r => r.total_deposit), backgroundColor: '#8b5cf6', borderRadius: 6 }],
        },
        options: {
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: ctx => {
              const r = scope.vip_breakdown[ctx.dataIndex];
              return money(ctx.parsed.y) + ' · ' + fmt(r.user_count) + ' users · ' + fmt(r.count) + ' orders';
            } } },
          },
          scales: { y: { beginAtZero: true, ticks: { callback: v => money(v) } } },
        },
      });
    }

    renderDateSwitch();
    renderCharts();
    wireSections(snapshotCache[selectedDate]);
  })();
}

if (IS_PLATFORM_ANALYSIS) {
  (async () => {
    const appEl = document.getElementById('platform-analysis-app');
    const entered = prompt('Enter password to access Platform Analysis:');
    if (entered !== ACTION_PASSWORD) {
      appEl.textContent = 'Access Denied';
      return;
    }
    const res = await fetch('/data.json');
    if (!res.ok) {
      document.getElementById('platform-analysis-app').textContent = 'Failed to load report data (' + res.status + ')';
      return;
    }
    const data = await res.json();
    document.getElementById('updated-badge').innerHTML =
      '<span class="dot"></span> Records updated through ' +
      (data.latest_record_time ? new Date(data.latest_record_time).toLocaleString() : 'n/a');
    document.getElementById('platform-analysis-app').className = '';

    const profitUsers = data.profit_users;
    const netRevRegionVip = data.region_vip_analytics || {};
    const netRevDates = Object.keys(netRevRegionVip).sort();
    const netRevLatest = netRevDates.length ? netRevRegionVip[netRevDates[netRevDates.length - 1]] : null;
    const acqChannel = data.channel_performance;
    const bonusClaimsByDate = data.bonus_claims_by_date || {};
    const bonusDates = Object.keys(bonusClaimsByDate).sort();
    let selectedBonusDate = data.report_today && bonusClaimsByDate[data.report_today] ? data.report_today : bonusDates[bonusDates.length - 1];
    let bonusClaims = bonusClaimsByDate[selectedBonusDate] || data.bonus_claims;

    document.getElementById('platform-analysis-app').innerHTML = \`
      <div class="analysis-heading deposit"><h2>Game &amp; Revenue Economics</h2><div class="line"></div><span class="tag">PLATFORM</span></div>
      <div class="row2col">
        <section class="acc-orange">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-orange">&#128181;</div><h2>Profit Users of the Day</h2></div>
            <button class="download-btn-sm" id="btn-dl-profit-users">&#128190; Excel</button>
          </div>
          <div class="ac-note">Top users by CURRENT wallet balance -- who's sitting on the most money right now. Last Dep/WD show "Today" or how many days ago, tracked permanently so it stays accurate even beyond the 33-day window.</div>
          <div id="profit-users-table"></div>
          <div class="ac-pagination" id="profit-users-pagination"></div>
        </section>
        <section class="acc-emerald">
          <div class="section-head">
            <div class="sec-title"><div class="badge b-emerald">&#128176;</div><h2>Net Revenue by Region &amp; VIP</h2></div>
            <button class="download-btn-sm" id="btn-dl-net-revenue">&#128190; Excel</button>
          </div>
          <div class="ac-note">Deposit minus withdrawal, not just gross deposit volume -- a region/tier can look like a top performer by deposit total while actually net-negative once withdrawals are subtracted. Most recent date in the report.</div>
          <div class="date-switch" id="net-rev-switch">
            <button data-view="region" class="active">By Region</button>
            <button data-view="vip">By VIP Level</button>
          </div>
          <div id="net-rev-table"></div>
        </section>
      </div>

      <div class="analysis-heading withdrawal"><h2>Acquisition &amp; Bonus Economics</h2><div class="line"></div><span class="tag">PLATFORM</span></div>
      <section class="acc-blue">
        <div class="section-head">
          <div class="sec-title"><div class="badge b-blue">&#128202;</div><h2>Channel performance &mdash; 4-day combined</h2></div>
          <button class="download-btn-sm" id="btn-dl-acq-channel">&#128190; Excel</button>
        </div>
        <div id="acq-channel-table"></div>
        <div class="ac-pagination" id="acq-channel-pagination"></div>
      </section>
      <section class="acc-purple">
        <div class="section-head">
          <div class="sec-title"><div class="badge b-purple">&#127942;</div><h2>Bonus Claim Report</h2></div>
          <button class="download-btn-sm" id="btn-dl-bonus-claims">&#128190; Excel</button>
        </div>
        <div class="ac-note">All bonuses claimed on the selected date, and % who deposited afterward.</div>
        <div class="date-switch" id="bonus-claims-date-switch"></div>
        <div class="date-switch" id="bonus-claims-switch">
          <button data-view="wallet" class="active">Wallet Bonuses</button>
          <button data-view="dcb">Deposit Challenge Bonus</button>
        </div>
        <div id="bonus-claims-table"></div>
      </section>
    \`;

    // --- Profit Users of the Day ---
    function coloredMoney(v, positiveColor, zeroColor) {
      const color = v > 0 ? positiveColor : (v < 0 ? '#dc2626' : zeroColor);
      return '<span style="color:' + color + ';font-weight:' + (v !== 0 ? '700' : '400') + '">' + money(v) + '</span>';
    }
    function lastActivityPill(label) {
      if (!label) return '<span style="color:#9ca3af">&mdash;</span>';
      if (label === 'Today') return '<span style="background:#d1fae5;color:#065f46;padding:2px 9px;border-radius:20px;font-weight:700;font-size:12px">Today</span>';
      return '<span style="color:#6b7280">' + label + '</span>';
    }
    const profitUsersCols = [
      { label: 'User ID', render: r => r.user_id, raw: r => r.user_id },
      { label: 'Agent', render: r => r.agent || 'Un-Assigned', raw: r => r.agent || 'Un-Assigned' },
      { label: 'VIP', render: r => r.vip, raw: r => r.vip, num: true },
      { label: 'Dep Today', render: r => coloredMoney(r.dep_today, '#16a34a', '#9ca3af'), raw: r => r.dep_today, num: true },
      { label: 'Wallet Bal', render: r => money(r.wallet_bal), raw: r => r.wallet_bal, num: true },
      { label: 'WD Today', render: r => coloredMoney(r.wd_today, '#dc2626', '#9ca3af'), raw: r => r.wd_today, num: true },
      { label: 'Net Dep', render: r => coloredMoney(r.net_dep, '#16a34a', '#9ca3af'), raw: r => r.net_dep, num: true },
      { label: 'Last Dep', render: r => lastActivityPill(r.last_dep), raw: r => r.last_dep },
      { label: 'Last WD', render: r => lastActivityPill(r.last_wd), raw: r => r.last_wd },
    ];
    if (profitUsers && profitUsers.length) {
      paginatedTable('profit-users-table', 'profit-users-pagination', profitUsers, profitUsersCols, 10);
      document.getElementById('btn-dl-profit-users').addEventListener('click', () =>
        downloadExcel(profitUsers, profitUsersCols, 'Profit Users of the Day', 'profit-users-of-the-day.xlsx'));
    } else {
      document.getElementById('profit-users-table').innerHTML = '<div class="no-data">No wallet balance data available.</div>';
    }

    // --- Net Revenue by Region & VIP ---
    let netRevView = 'region';
    function netRevRows() {
      if (!netRevLatest) return [];
      if (netRevView === 'region') return netRevLatest.top_regions.slice().sort((a, b) => b.net_revenue - a.net_revenue);
      return netRevLatest.vip_breakdown.slice().sort((a, b) => b.net_revenue - a.net_revenue);
    }
    function netRevCols() {
      return [
        { label: netRevView === 'region' ? 'Region' : 'VIP Level', render: r => (netRevView === 'region' ? r.region : 'VIP ' + r.vip_level), raw: r => (netRevView === 'region' ? r.region : r.vip_level) },
        { label: 'Total Deposit', render: r => money(r.total_deposit), raw: r => r.total_deposit, num: true },
        { label: 'Total Withdrawal', render: r => money(r.total_withdrawal), raw: r => r.total_withdrawal, num: true },
        { label: 'Net Revenue', render: r => money(r.net_revenue), raw: r => r.net_revenue, num: true },
        { label: 'Users', render: r => fmt(r.user_count), raw: r => r.user_count, num: true },
      ];
    }
    function renderNetRev() {
      const rows = netRevRows();
      const cols = netRevCols();
      const container = document.getElementById('net-rev-table');
      if (!rows.length) {
        container.innerHTML = '<div class="no-data">No data available.</div>';
        return;
      }
      const thead = '<thead><tr>' + cols.map(c => '<th' + (c.num ? ' class="num"' : '') + '>' + c.label + '</th>').join('') + '</tr></thead>';
      const tbody = '<tbody>' + rows.map(r => '<tr>' + cols.map(c => '<td class="' + (c.num ? 'num' : '') + '">' + c.render(r) + '</td>').join('') + '</tr>').join('') + '</tbody>';
      container.innerHTML = '<div class="table-wrap"><table>' + thead + tbody + '</table></div>';
    }
    document.querySelectorAll('#net-rev-switch button').forEach(btn => {
      btn.addEventListener('click', () => {
        netRevView = btn.dataset.view;
        document.querySelectorAll('#net-rev-switch button').forEach(b => b.classList.toggle('active', b === btn));
        renderNetRev();
      });
    });
    renderNetRev();
    document.getElementById('btn-dl-net-revenue').addEventListener('click', () => {
      const userDetailCols = [
        { label: 'User ID', raw: r => r.user_id },
        { label: 'Agent', raw: r => r.agent || 'Un-Assigned' },
        { label: 'Deposit Today', raw: r => r.dep_today },
        { label: 'Wallet Balance', raw: r => r.wallet_bal },
        { label: 'Withdraw Today', raw: r => r.wd_today },
        { label: 'Net Deposit', raw: r => r.net_dep },
      ];
      (async () => {
        const wb = new ExcelJS.Workbook();
        const summaryCols = netRevCols();
        const ws1 = wb.addWorksheet('Net Revenue');
        ws1.columns = summaryCols.map(c => ({ header: c.label, key: c.label, width: 18 }));
        ws1.addRows(netRevRows().map(r => summaryCols.reduce((o, c) => { o[c.label] = c.raw(r); return o; }, {})));
        styleHeaderRow(ws1);

        const ws2 = wb.addWorksheet('User Detail');
        const userRows = profitUsers || [];
        ws2.columns = userDetailCols.map(c => ({ header: c.label, key: c.label, width: 16 }));
        ws2.addRows(userRows.map(r => userDetailCols.reduce((o, c) => { o[c.label] = c.raw(r); return o; }, {})));
        styleHeaderRow(ws2);

        await saveWorkbook(wb, 'net-revenue-' + netRevView + '.xlsx');
      })();
    });

    // --- Channel performance -- 4-day combined ---
    function pctPill(pct) {
      const bg = pct >= 25 ? '#d1fae5' : (pct >= 15 ? '#fef3c7' : '#fee2e2');
      const fg = pct >= 25 ? '#065f46' : (pct >= 15 ? '#92400e' : '#991b1b');
      return '<span style="background:' + bg + ';color:' + fg + ';padding:3px 10px;border-radius:20px;font-weight:700;font-size:12px">' + pct + '%</span>';
    }
    function qualityPill(q) {
      const styles = {
        'High value': ['#d1fae5', '#065f46'], 'Good': ['#d1fae5', '#065f46'],
        'Average': ['#fef3c7', '#92400e'], 'Weak': ['#fee2e2', '#991b1b'],
      };
      const [bg, fg] = styles[q] || ['#e5e7eb', '#374151'];
      return '<span style="background:' + bg + ';color:' + fg + ';padding:3px 10px;border-radius:20px;font-weight:700;font-size:12px">' + q + '</span>';
    }
    const acqChannelCols = [
      { label: 'Channel', render: r => r.channel, raw: r => r.channel },
      { label: 'FD Users', render: r => fmt(r.fd_users), raw: r => r.fd_users, num: true },
      { label: 'FD Amount', render: r => money(r.fd_amount), raw: r => r.fd_amount, num: true },
      { label: 'Avg FD', render: r => money(r.avg_fd), raw: r => r.avg_fd, num: true },
      { label: 'D2 Users', render: r => fmt(r.d2_users), raw: r => r.d2_users, num: true },
      { label: 'D2 %', render: r => pctPill(r.d2_pct), raw: r => r.d2_pct, num: true },
      { label: 'D3 Users', render: r => fmt(r.d3_users), raw: r => r.d3_users, num: true },
      { label: 'D3 %', render: r => pctPill(r.d3_pct), raw: r => r.d3_pct, num: true },
      { label: 'Quality', render: r => qualityPill(r.quality), raw: r => r.quality },
    ];
    if (acqChannel && acqChannel.length) {
      paginatedTable('acq-channel-table', 'acq-channel-pagination', acqChannel, acqChannelCols, 10);
      document.getElementById('btn-dl-acq-channel').addEventListener('click', () =>
        downloadExcel(acqChannel, acqChannelCols, 'Channel Performance', 'channel-performance-4day.xlsx'));
    } else {
      document.getElementById('acq-channel-table').innerHTML = '<div class="no-data">No channel data available for the last 4 days.</div>';
    }

    // --- Bonus Claim Report -- today only, both views share the same shape ---
    let bonusView = 'wallet';
    function bonusRows() {
      if (!bonusClaims) return [];
      return bonusView === 'wallet' ? bonusClaims.wallet_bonuses : bonusClaims.deposit_challenge_bonuses;
    }
    function bonusCols() {
      return [
        { label: bonusView === 'wallet' ? 'Bonus Category' : 'Rule', render: r => r.bonus_category, raw: r => r.bonus_category },
        { label: 'Claimed Users', render: r => fmt(r.claimed_users), raw: r => r.claimed_users, num: true },
        { label: 'Total Bonus', render: r => money(r.total_value), raw: r => r.total_value, num: true },
        { label: 'Deposited After', render: r => fmt(r.deposited_after), raw: r => r.deposited_after, num: true },
        { label: 'Deposit Amount', render: r => money(r.deposit_amount), raw: r => r.deposit_amount, num: true },
        { label: '%', render: r => r.pct_deposited + '%', raw: r => r.pct_deposited, num: true },
      ];
    }
    function renderBonusClaims() {
      const rows = bonusRows();
      const cols = bonusCols();
      const container = document.getElementById('bonus-claims-table');
      if (!rows.length) {
        container.innerHTML = '<div class="no-data">No bonus claims recorded yet.</div>';
        return;
      }
      const thead = '<thead><tr>' + cols.map(c => '<th' + (c.num ? ' class="num"' : '') + '>' + c.label + '</th>').join('') + '</tr></thead>';
      const tbody = '<tbody>' + rows.map(r => '<tr>' + cols.map(c => '<td class="' + (c.num ? 'num' : '') + '">' + c.render(r) + '</td>').join('') + '</tr>').join('') + '</tbody>';
      container.innerHTML = '<div class="table-wrap"><table>' + thead + tbody + '</table></div>';
    }
    function renderBonusDateSwitch() {
      const el = document.getElementById('bonus-claims-date-switch');
      el.innerHTML = bonusDates.map(d =>
        '<button data-date="' + d + '" class="' + (d === selectedBonusDate ? 'active' : '') + '">' + shortDate(d) + '</button>'
      ).join('');
      el.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', () => {
          selectedBonusDate = btn.dataset.date;
          bonusClaims = bonusClaimsByDate[selectedBonusDate] || { wallet_bonuses: [], deposit_challenge_bonuses: [] };
          renderBonusDateSwitch();
          renderBonusClaims();
        });
      });
    }
    if (bonusDates.length) {
      renderBonusDateSwitch();
      document.querySelectorAll('#bonus-claims-switch button').forEach(btn => {
        btn.addEventListener('click', () => {
          bonusView = btn.dataset.view;
          document.querySelectorAll('#bonus-claims-switch button').forEach(b => b.classList.toggle('active', b === btn));
          renderBonusClaims();
        });
      });
      renderBonusClaims();
      document.getElementById('btn-dl-bonus-claims').addEventListener('click', () =>
        downloadExcel(bonusRows(), bonusCols(), 'Bonus Claims', 'bonus-claims-' + bonusView + '-' + selectedBonusDate + '.xlsx'));
    } else {
      document.getElementById('bonus-claims-table').innerHTML = '<div class="no-data">No bonus claims recorded yet.</div>';
    }
  })();
}

const REASSIGN_ENDPOINT = 'https://master-userlist-upload.devtrip4646.workers.dev/reassign-agent';
const BAN_USER_ENDPOINT = 'https://master-userlist-upload.devtrip4646.workers.dev/ban-user';

if (IS_SEARCH_USER) {
  const container = document.getElementById('search-user-app');
  container.innerHTML = \`
    <div class="analysis-heading deposit"><h2>Search User</h2><div class="line"></div><span class="tag">LOOKUP</span></div>
    <div class="su-searchbar">
      <span class="su-searchbar-icon">&#128269;</span>
      <input type="text" id="search-user-input" placeholder="Enter or paste a User ID&hellip;" inputmode="numeric">
      <button id="search-user-btn">Search</button>
    </div>

    \${IS_AGENT_SCOPED ? '' : \`
    <div class="su-reassign-card">
      <div class="su-reassign-title"><span class="badge">&#128100;</span> Reassign Agent</div>
      <div class="su-reassign-row">
        <input type="text" id="reassign-user-input" placeholder="User ID" inputmode="numeric">
        <select id="reassign-agent-select"><option value="">Un-Assigned</option></select>
        <button id="reassign-save-btn">&#128190; Save</button>
      </div>
      <div id="reassign-msg" class="su-reassign-msg"></div>
    </div>

    <div class="su-reassign-card su-ban-card">
      <div class="su-reassign-title"><span class="badge">&#128683;</span> Ban User</div>
      <div class="su-ban-note">Permanently deletes ALL of this user's records (deposits, withdrawals, wallet activity, agent assignment) and hides them from the dashboard forever. This cannot be undone.</div>
      <div class="su-reassign-row">
        <input type="text" id="ban-user-input" placeholder="User ID" inputmode="numeric">
        <button id="ban-user-btn" class="su-ban-btn">&#128683; Ban &amp; Delete</button>
      </div>
      <div id="ban-user-msg" class="su-reassign-msg"></div>
    </div>
    \`}

    <div id="search-user-result"></div>
  \`;

  // Agent dropdown options come from the report's agent_list (distinct real
  // agent names already in agent_assignments) -- fetched lazily so the
  // Search User page doesn't have to wait on /data.json before rendering.
  // Reassign Agent is hidden entirely for agent-scoped dashboards, so none
  // of this dropdown/save wiring applies there.
  if (!IS_AGENT_SCOPED) {
  (async () => {
    try {
      const res = await fetch('/data.json');
      const reportData = await res.json();
      const select = document.getElementById('reassign-agent-select');
      (reportData.agent_list || []).forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
      });
    } catch (e) {
      // Dropdown just falls back to "Un-Assigned" only -- not fatal.
    }
  })();

  document.getElementById('reassign-save-btn').addEventListener('click', async () => {
    const userInput = document.getElementById('reassign-user-input');
    const select = document.getElementById('reassign-agent-select');
    const btn = document.getElementById('reassign-save-btn');
    const msg = document.getElementById('reassign-msg');
    const userId = userInput.value.trim();
    const userIdNum = Number(userId);
    if (!userId || !Number.isInteger(userIdNum) || userIdNum <= 0) {
      msg.textContent = 'Enter a valid numeric User ID.';
      msg.className = 'su-reassign-msg err';
      return;
    }
    if (!checkActionPassword(msg, 'reassign this user')) return;
    btn.disabled = true;
    msg.textContent = 'Saving...';
    msg.className = 'su-reassign-msg';
    try {
      const res = await fetch(REASSIGN_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ user_id: Number(userId), agent: select.value }),
      });
      const resData = await res.json();
      if (!res.ok) throw new Error(resData.error || res.status);
      msg.textContent = 'Saved - ' + (select.value || 'Un-Assigned') + ' will show for User #' + userId + ' within a minute or two.';
      msg.className = 'su-reassign-msg ok';
    } catch (err) {
      msg.textContent = 'Error: ' + err.message;
      msg.className = 'su-reassign-msg err';
    }
    btn.disabled = false;
  });

  document.getElementById('ban-user-btn').addEventListener('click', async () => {
    const userInput = document.getElementById('ban-user-input');
    const btn = document.getElementById('ban-user-btn');
    const msg = document.getElementById('ban-user-msg');
    const userId = userInput.value.trim();
    const userIdNum = Number(userId);
    if (!userId || !Number.isInteger(userIdNum) || userIdNum <= 0) {
      msg.textContent = 'Enter a valid numeric User ID.';
      msg.className = 'su-reassign-msg err';
      return;
    }
    btn.disabled = true;
    msg.textContent = 'Checking...';
    msg.className = 'su-reassign-msg';
    // A user_id that's already banned (or never existed) was already purged
    // from the search index, so it 404s here -- same check the Search box
    // uses. Ban Delete should refuse rather than dispatch a no-op.
    const checkRes = await fetch('/api/user-search?user_id=' + encodeURIComponent(userId));
    if (!checkRes.ok) {
      msg.textContent = 'Not valid user';
      msg.className = 'su-reassign-msg err';
      btn.disabled = false;
      return;
    }
    if (!confirm('Ban User #' + userId + ' and PERMANENTLY DELETE all their records? This cannot be undone.')) {
      btn.disabled = false;
      return;
    }
    if (!checkActionPassword(msg, 'ban this user')) {
      btn.disabled = false;
      return;
    }
    msg.textContent = 'Banning...';
    msg.className = 'su-reassign-msg';
    try {
      const res = await fetch(BAN_USER_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ user_id: Number(userId) }),
      });
      const resData = await res.json();
      if (!res.ok) throw new Error(resData.error || res.status);
      msg.textContent = 'User #' + userId + ' banned. Their records will be deleted from the dashboard within a minute or two.';
      msg.className = 'su-reassign-msg ok';
      userInput.value = '';
    } catch (err) {
      msg.textContent = 'Error: ' + err.message;
      msg.className = 'su-reassign-msg err';
    }
    btn.disabled = false;
  });
  }

  function fmtMoney(v) { return '₹' + Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 }); }
  function daysAgoLabel(iso) {
    if (!iso) return null;
    const d = new Date(String(iso).replace(' ', 'T'));
    if (isNaN(d)) return null;
    const gap = Math.floor((Date.now() - d.getTime()) / 86400000);
    return gap <= 0 ? 'Today' : gap + 'd ago';
  }
  function activityPill(label) {
    if (!label) return '<span class="su-pill su-pill-grey">No data</span>';
    return label === 'Today' ? '<span class="su-pill su-pill-green">Active Today</span>' : '<span class="su-pill su-pill-grey">' + label + '</span>';
  }
  function vipBadge(level) {
    let cls = 'su-vip-standard', label = 'Standard';
    if (level >= 10) { cls = 'su-vip-elite'; label = 'Elite'; }
    else if (level >= 5) { cls = 'su-vip-gold'; label = 'Gold'; }
    return '<span class="su-vip-badge ' + cls + '">VIP ' + (level ?? '&mdash;') + ' &middot; ' + label + '</span>';
  }
  function statusPill(status) {
    const s = String(status).toLowerCase();
    let cls = 'su-pill-grey';
    if (s.includes('complete')) cls = 'su-pill-green';
    else if (s.includes('process')) cls = 'su-pill-blue';
    else if (s.includes('review')) cls = 'su-pill-amber';
    else if (s.includes('reject') || s.includes('fail')) cls = 'su-pill-red';
    return '<span class="su-pill ' + cls + '">' + status + '</span>';
  }
  function gameTypeBadge(type) {
    return '<span class="su-pill ' + (type === 'Win' ? 'su-pill-green' : 'su-pill-blue') + '">' + type + '</span>';
  }
  function sumIf(rows, statusMatch) {
    return (rows || [])
      .filter(r => String(r.status).toLowerCase().includes(statusMatch))
      .reduce((s, r) => s + Number(r.amount || 0), 0);
  }
  function recordTable(rows, cols, emptyMsg) {
    if (!rows || !rows.length) return '<div class="no-data">' + (emptyMsg || 'No records in this period.') + '</div>';
    const thead = '<thead><tr>' + cols.map(c => '<th' + (c.num ? ' class="num"' : '') + '>' + c.label + '</th>').join('') + '</tr></thead>';
    const tbody = '<tbody>' + rows.map(r => '<tr>' + cols.map(c => '<td class="' + (c.num ? 'num' : '') + '">' + c.render(r) + '</td>').join('') + '</tr>').join('') + '</tbody>';
    return '<div class="table-wrap"><table>' + thead + tbody + '</table></div>';
  }

  async function runSearch() {
    const input = document.getElementById('search-user-input');
    const resultEl = document.getElementById('search-user-result');
    const userId = input.value.trim();
    if (!userId) return;
    document.getElementById('search-user-btn').disabled = true;
    resultEl.innerHTML = '<div class="su-state">Searching&hellip;</div>';
    try {
      const res = await fetch('/api/user-search?user_id=' + encodeURIComponent(userId));
      const data = await res.json();
      if (!res.ok) {
        resultEl.innerHTML = '<div class="su-state su-state-error">&#9888;&#65039; ' + (data.error || 'User not found') + '</div>';
        return;
      }
      if (IS_AGENT_SCOPED && data.agent !== AGENT_NAME) {
        resultEl.innerHTML = '<div class="su-state su-state-error">&#9888;&#65039; User #' + userId + ' is not assigned to your agent account.</div>';
        return;
      }
      const dep7 = sumIf(data.recent_deposits, 'complete');
      const wd7 = sumIf(data.recent_withdrawals, 'complete');

      resultEl.innerHTML = \`
        <div class="su-profile-card">
          <div class="su-profile-top">
            <div>
              <div class="su-profile-id">User #\${data.user_id}</div>
              <div class="su-profile-meta">Agent \${data.agent || 'Un-Assigned'} &middot; \${data.region || 'Unknown region'} &middot; Channel \${data.acquisition_channel || '&mdash;'} &middot; Registered \${data.registered ? shortDate(String(data.registered).slice(0,10)) : '&mdash;'} &middot; \${activityPill(daysAgoLabel(data.last_active_time))}</div>
            </div>
            <div class="su-profile-balance">
              <div class="lbl">Wallet Balance</div>
              <div class="amt">\${fmtMoney(data.wallet_balance)}</div>
            </div>
            \${vipBadge(data.vip_level)}
          </div>
        </div>

        <div class="analysis-heading withdrawal"><h2>Financial Overview</h2><div class="line"></div><span class="tag">LOOKUP</span></div>
        <div class="su-fin-panel">
          <div class="su-fin-section">
            <div class="su-fin-section-title">Lifetime</div>
            <div class="su-fin-stats">
              <div class="su-fin-stat"><div class="su-fin-label">Total Deposit</div><div class="su-fin-value c-green">\${fmtMoney(data.total_deposit)}</div></div>
              <div class="su-fin-stat"><div class="su-fin-label">Total Withdraw</div><div class="su-fin-value c-red">\${fmtMoney(data.total_withdraw)}</div></div>
              <div class="su-fin-stat"><div class="su-fin-label">Wallet Balance</div><div class="su-fin-value c-blue">\${fmtMoney(data.wallet_balance)}</div></div>
              <div class="su-fin-stat"><div class="su-fin-label">Net Lifetime (Deposit &minus; Withdraw)</div><div class="su-fin-value \${data.net_lifetime >= 0 ? 'c-blue' : 'c-red'}">\${fmtMoney(data.net_lifetime)}</div></div>
            </div>
          </div>
          <div class="su-fin-section">
            <div class="su-fin-section-title">Last 7 Days <span class="su-fin-note">(completed only)</span></div>
            <div class="su-fin-stats">
              <div class="su-fin-stat"><div class="su-fin-label">Deposits</div><div class="su-fin-value c-green">\${fmtMoney(dep7)}</div></div>
              <div class="su-fin-stat"><div class="su-fin-label">Withdrawals</div><div class="su-fin-value c-red">\${fmtMoney(wd7)}</div></div>
              <div class="su-fin-stat"><div class="su-fin-label">Net</div><div class="su-fin-value \${(dep7 - wd7) >= 0 ? 'c-blue' : 'c-red'}">\${fmtMoney(dep7 - wd7)}</div></div>
            </div>
          </div>
        </div>

        <div class="analysis-heading deposit"><h2>Last 7 Days Activity</h2><div class="line"></div><span class="tag">LOOKUP</span></div>
        <div class="row2col">
          <section class="acc-emerald">
            <div class="sec-title"><div class="badge b-emerald">&#128176;</div><h2>Deposits (\${(data.recent_deposits || []).length})</h2></div>
            \${recordTable(data.recent_deposits, [
              { label: 'Date', render: r => r.date },
              { label: 'Amount', render: r => fmtMoney(r.amount), num: true },
              { label: 'Status', render: r => statusPill(r.status) },
              { label: 'Order No', render: r => r.order_no || '&mdash;' },
              { label: 'Channel', render: r => r.channel || '&mdash;' },
            ], 'No deposits in the last 7 days.')}
          </section>
          <section class="acc-rose">
            <div class="sec-title"><div class="badge b-rose">&#128181;</div><h2>Withdrawals (\${(data.recent_withdrawals || []).length})</h2></div>
            \${recordTable(data.recent_withdrawals, [
              { label: 'Date', render: r => r.date },
              { label: 'Amount', render: r => fmtMoney(r.amount), num: true },
              { label: 'Status', render: r => statusPill(r.status) },
              { label: 'Order No', render: r => r.order_no || '&mdash;' },
              { label: 'Channel', render: r => r.channel || '&mdash;' },
            ], 'No withdrawals in the last 7 days.')}
          </section>
        </div>

        <div class="analysis-heading withdrawal"><h2>Recent Games &amp; Bonuses</h2><div class="line"></div><span class="tag">LOOKUP</span></div>
        <div class="row2col">
          <section class="acc-orange">
            <div class="sec-title"><div class="badge b-orange">&#127918;</div><h2>Recent Games Played (\${(data.recent_games || []).length})</h2></div>
            <div class="ac-note">Last 2 days &middot; excludes bonus payouts</div>
            \${recordTable(data.recent_games, [
              { label: 'Game', render: r => r.game_name },
              { label: 'Type', render: r => gameTypeBadge(r.type) },
              { label: 'Amount', render: r => fmtMoney(r.amount), num: true },
              { label: 'Date', render: r => r.date },
            ], 'No games played in the last 2 days.')}
          </section>
          <section class="acc-purple">
            <div class="sec-title"><div class="badge b-purple">&#127873;</div><h2>Bonuses Claimed (\${(data.recent_bonuses || []).length})</h2></div>
            <div class="ac-note">Last 7 days</div>
            \${recordTable(data.recent_bonuses, [
              { label: 'Bonus', render: r => r.category },
              { label: 'Amount', render: r => fmtMoney(r.amount), num: true },
              { label: 'Date', render: r => r.date },
            ], 'No bonuses claimed in the last 7 days.')}
          </section>
        </div>
      \`;
    } catch (e) {
      resultEl.innerHTML = '<div class="su-state su-state-error">Search failed: ' + e.message + '</div>';
    } finally {
      document.getElementById('search-user-btn').disabled = false;
    }
  }
  document.getElementById('search-user-btn').addEventListener('click', runSearch);
  document.getElementById('search-user-input').addEventListener('keydown', e => { if (e.key === 'Enter') runSearch(); });
  document.getElementById('search-user-input').focus();
}

if (!IS_ACTION_CENTER && !IS_PERFORMANCE && !IS_ANALYTICS && !IS_PLATFORM_ANALYSIS && !IS_SEARCH_USER)
(async () => {
  const res = await fetch('/data.json');
  if (!res.ok) {
    document.getElementById('app').textContent = 'Failed to load report data (' + res.status + ')';
    return;
  }
  const globalData = await res.json();
  let data = globalData;
  if (IS_AGENT_SCOPED) {
    // The per-agent file only has all_time/by_date/withdrawal_analysis/
    // region_vip_analytics (the aggregates that genuinely can't be scoped
    // client-side) -- everything else (dates, amount_ranges, metadata, and
    // withdrawal_orders_full, which already carries an "agent" field per
    // row) comes from the global report, so the two are merged here.
    const agentRes = await fetch('/data.json?agent=' + encodeURIComponent(AGENT_NAME));
    if (!agentRes.ok) {
      document.getElementById('app').textContent = 'Failed to load this agent\\'s report (' + agentRes.status + ')';
      return;
    }
    const agentData = await agentRes.json();
    data = {
      ...globalData,
      ...agentData,
      withdrawal_orders_full: (globalData.withdrawal_orders_full || []).filter(o => o.agent === AGENT_NAME),
    };
  }
  const rangeOrder = data.amount_ranges.concat(['Other']);

  document.getElementById('updated-badge').innerHTML =
    '<span class="dot"></span> Records updated through ' +
    (data.latest_record_time ? new Date(data.latest_record_time).toLocaleString() : 'n/a');

  document.getElementById('app').className = '';
  document.getElementById('app').innerHTML = \`
    <div class="kpi-grid">
      <div class="kpi c-green"><div class="dash"></div><div class="value" id="k-deposit"></div><div class="label">Total Deposit</div><div class="desc">&#10003; Complete orders only</div></div>
      <div class="kpi c-red"><div class="dash"></div><div class="value" id="k-withdraw"></div><div class="label">Total Withdraw</div><div class="desc">&#10003; In-Review + Processing + Complete</div></div>
      <div class="kpi c-amber"><div class="dash"></div><div class="value" id="k-deposit-orders"></div><div class="label">Deposit Orders</div><div class="desc">&#10003; Complete order count for the day</div></div>
      <div class="kpi c-pink"><div class="dash"></div><div class="value" id="k-withdraw-orders"></div><div class="label">Withdraw Orders</div><div class="desc">&#10003; In-Review + Processing + Complete count</div></div>
    </div>

    <div class="net-flow">
      <div class="nf-label">NET FLOW</div>
      <div class="nf-stats">
        <div>Difference: <b id="nf-difference">&mdash;</b></div>
        <div>Withdraw/Deposit: <b id="nf-ratio">&mdash;</b></div>
      </div>
    </div>

    <div class="kpi-grid row2">
      <div class="kpi c-sky"><div class="dash"></div><div class="value" id="k-deposit-users"></div><div class="label">Deposit Users</div><div class="desc">&#10003; Unique users with complete deposits</div></div>
      <div class="kpi c-orange"><div class="dash"></div><div class="value" id="k-withdraw-users"></div><div class="label">Withdraw Users</div><div class="desc">&#10003; Unique users with active withdrawals</div></div>
      <div class="kpi c-purple"><div class="dash"></div><div class="value" id="k-active-users"></div><div class="label">Active Users</div><div class="desc">&#10003; Unique users with deposit history, active via deposit/withdraw/bets</div></div>
    </div>

    <div class="analysis-heading deposit"><h2>Deposit Analysis</h2><div class="line"></div><span class="tag">DEPOSITS</span></div>

    <section class="acc-blue">
      <div class="section-head">
        <div class="sec-title"><div class="badge b-blue">&#128202;</div><h2>Amount Range</h2></div>
        <button class="download-btn-sm" id="btn-dl-amount-range">&#128190; Excel</button>
      </div>
      <div id="range-table"></div>
    </section>

    <section class="acc-purple">
      <div class="section-head">
        <div class="sec-title"><div class="badge b-purple">&#127974;</div><h2>Deposit Channel Analysis</h2></div>
        <button class="download-btn" id="btn-download">&#128190; Download Excel</button>
      </div>
      <div class="two-col">
        <div class="sub-table">
          <h3>Deposit Success Rate by Amount Range</h3>
          <div id="success-range-table"></div>
        </div>
        <div class="sub-table">
          <h3>Deposit by Channel</h3>
          <div id="success-channel-table"></div>
        </div>
      </div>
    </section>

    <section class="acc-orange">
      <div class="section-head">
        <div class="sec-title"><div class="badge b-orange">&#9200;</div><h2>Hourly Success Rate &mdash; By Amount Range</h2></div>
        <button class="download-btn-sm" id="btn-dl-heatmap-range">&#128190; Excel</button>
      </div>
      <div class="heat-legend">
        <span class="chip good">&ge;41%</span>
        <span class="chip mid">30&ndash;40%</span>
        <span class="chip bad">&lt;30%</span>
        <span class="chip none">&mdash;</span>
      </div>
      <div id="heatmap-range-table" class="table-wrap"></div>
    </section>

    <section class="acc-orange">
      <div class="section-head">
        <div class="sec-title"><div class="badge b-orange">&#9200;</div><h2>Hourly Success Rate &mdash; By Channel</h2></div>
        <button class="download-btn-sm" id="btn-dl-heatmap-channel">&#128190; Excel</button>
      </div>
      <div class="heat-legend">
        <span class="chip good">&ge;41%</span>
        <span class="chip mid">30&ndash;40%</span>
        <span class="chip bad">&lt;30%</span>
        <span class="chip none">&mdash;</span>
      </div>
      <div id="heatmap-channel-table" class="table-wrap"></div>
    </section>

    <div class="analysis-heading withdrawal"><h2>Withdrawal Analysis</h2><div class="line"></div><span class="tag">WITHDRAWALS</span></div>

    <div class="row2col">
      <section class="acc-rose">
        <div class="section-head">
          <div class="sec-title"><div class="badge b-rose">&#9203;</div><h2>Channel-wise Processing Time (create &rarr; review) &mdash; status 1</h2></div>
          <button class="download-btn-sm" id="btn-dl-withdrawal-orders">&#128190; Download Orders (Excel)</button>
        </div>
        <div id="withdrawal-review-table"></div>
      </section>
      <section class="acc-cyan">
        <div class="section-head">
          <div class="sec-title"><div class="badge b-cyan">&#9989;</div><h2>Channel-wise Completion Time (review &rarr; complete) &mdash; status 2</h2></div>
          <button class="download-btn-sm" id="btn-dl-withdrawal-completion">&#128190; Excel</button>
        </div>
        <div id="withdrawal-completion-table"></div>
      </section>
    </div>

    <div class="row2col">
      <section class="acc-rose">
        <div class="section-head">
          <div class="sec-title"><div class="badge b-rose">&#8987;</div><h2>Processing Orders &mdash; Aging</h2></div>
          <button class="download-btn-sm" id="btn-dl-processing-backlog">&#128190; Excel</button>
        </div>
        <canvas id="processing-backlog-chart"></canvas>
      </section>
      <section class="acc-cyan">
        <div class="section-head">
          <div class="sec-title"><div class="badge b-cyan">&#128269;</div><h2>In-Review Orders &mdash; Aging</h2></div>
          <button class="download-btn-sm" id="btn-dl-inreview-backlog">&#128190; Excel</button>
        </div>
        <canvas id="inreview-backlog-chart"></canvas>
      </section>
    </div>

    <section class="acc-rose">
      <div class="section-head">
        <div class="sec-title"><div class="badge b-rose">&#9989;</div><h2>Completed Orders &mdash; Within 4h vs More than 4h (Last 4 Days)</h2></div>
        <button class="download-btn-sm" id="btn-dl-last4days">&#128190; Excel</button>
      </div>
      <canvas id="last4days-chart"></canvas>
    </section>
  \`;

  let currentScope = null;

  function render(scope, label) {
    currentScope = scope;

    const s = scope.summary;
    document.getElementById('k-deposit').textContent = money(s.total_deposit);
    document.getElementById('k-withdraw').textContent = money(s.total_withdraw);
    document.getElementById('k-deposit-orders').textContent = fmt(s.deposit_orders);
    document.getElementById('k-withdraw-orders').textContent = fmt(s.withdraw_orders);
    document.getElementById('k-deposit-users').textContent = fmt(s.deposit_users);
    document.getElementById('k-withdraw-users').textContent = fmt(s.withdraw_users);
    document.getElementById('k-active-users').textContent = fmt(s.active_users);

    const diffEl = document.getElementById('nf-difference');
    diffEl.textContent = (s.difference < 0 ? '-' : '') + money(Math.abs(s.difference));
    diffEl.className = s.difference < 0 ? 'neg' : 'pos';
    document.getElementById('nf-ratio').textContent = s.withdraw_deposit_pct == null ? '—' : s.withdraw_deposit_pct + '%';

    const rangeRows = rangeOrder.map(r => scope.by_amount_range.find(x => x.range === r) || { range: r, count: 0, users: 0, total_amount: 0 });
    const maxRangeAmount = Math.max(...rangeRows.map(r => r.total_amount), 1);
    sortableTable(
      document.getElementById('range-table'),
      ['Amount Range', 'Count', 'Users', 'Total Amount'],
      rangeRows.map(r => [r.range, r.count, r.users, r.total_amount]),
      r => '<tr><td>' + r[0] + '</td><td class="num">' + fmt(r[1]) + '</td><td class="num">' + fmt(r[2]) + '</td>' +
           '<td class="num bar-cell"><div class="bar" style="width:' + (r[3] / maxRangeAmount * 100) + '%"></div><span>' + money(r[3]) + '</span></td></tr>',
      [1, 2, 3]
    );
    const channels = scope.by_channel.map(c => c.channel);

    // Deposit Success Rate by Amount Range
    const srRows = rangeOrder
      .map(r => scope.success_by_range.find(x => x.range === r) || { range: r, total: 0, completed: 0, success_pct: 0, avg_minutes: null })
      .filter(r => r.total > 0 || r.range !== 'Other');
    sortableTable(
      document.getElementById('success-range-table'),
      ['Amount Range', 'Total', 'Completed', 'Success %', 'Avg Time'],
      srRows.map(r => [r.range, r.total, r.completed, r.success_pct, r.avg_minutes]),
      r => '<tr><td>' + r[0] + '</td><td class="num">' + fmt(r[1]) + '</td><td class="num">' + fmt(r[2]) + '</td>' +
           '<td class="num ' + pctClass(r[3]) + '">' + r[3] + '%</td>' +
           '<td class="num">' + (r[4] == null ? '&mdash;' : r[4] + ' min') + '</td></tr>',
      [1, 2, 3, 4]
    );

    // Deposit by Channel (success rate)
    sortableTable(
      document.getElementById('success-channel-table'),
      ['Channel', 'Total Orders', 'Comp. Orders', 'Comp. Users', 'Comp. Amount', 'Success %', 'Avg Mins'],
      scope.success_by_channel.map(c => [c.channel, c.total, c.comp_orders, c.comp_users, c.comp_amount, c.success_pct, c.avg_minutes]),
      r => '<tr><td>' + r[0] + '</td><td class="num">' + fmt(r[1]) + '</td><td class="num">' + fmt(r[2]) + '</td><td class="num">' + fmt(r[3]) + '</td>' +
           '<td class="num">' + money(r[4]) + '</td>' +
           '<td class="num ' + pctClass(r[5]) + '">' + r[5] + '%</td>' +
           '<td class="num">' + (r[6] == null ? '&mdash;' : r[6] + ' min') + '</td></tr>',
      [1, 2, 3, 4, 5, 6]
    );

    renderHeatmap('channel', 'heatmap-channel-table', channels);
    renderHeatmap('range', 'heatmap-range-table', rangeOrder);

    renderWithdrawalTimingTable('withdrawal-review-table', scope.withdrawal_review_by_channel || [], 'No processing (status 1) withdrawals for this date.');
    renderWithdrawalTimingTable('withdrawal-completion-table', scope.withdrawal_completion_by_channel || [], 'No completed (status 2) withdrawals for this date.');
  }

  function renderWithdrawalTimingTable(containerId, matrix, emptyMsg) {
    const procBuckets = data.withdrawal_analysis.processing_time_buckets;
    const channels = [...new Set(matrix.map(r => r.channel))];
    const container = document.getElementById(containerId);
    if (!channels.length) {
      container.innerHTML = '<div class="no-data">' + emptyMsg + '</div>';
      return;
    }
    const rows = channels.map(ch => {
      const row = { channel: ch };
      let total = 0;
      for (const b of procBuckets) {
        const found = matrix.find(x => x.channel === ch && x.bucket === b);
        row[b] = found ? found.count : 0;
        total += row[b];
      }
      row._total = total;
      return row;
    });
    const headers = ['Channel'].concat(procBuckets).concat(['Total']);
    container.innerHTML = '<div class="table-wrap"><table><thead><tr>' +
      headers.map((h, i) => '<th' + (i > 0 ? ' class="num"' : '') + '>' + h + '</th>').join('') + '</tr></thead><tbody>' +
      rows.map(row => '<tr><td>' + row.channel + '</td>' +
        procBuckets.map(b => '<td class="num">' + (row[b] || '') + '</td>').join('') +
        '<td class="num"><strong>' + row._total + '</strong></td></tr>').join('') +
      '</tbody></table></div>';
  }

  let processingBacklogChart = null, inreviewBacklogChart = null, last4daysChart = null;
  function renderBacklogCharts() {
    const wa = data.withdrawal_analysis;
    if (processingBacklogChart) processingBacklogChart.destroy();
    processingBacklogChart = new Chart(document.getElementById('processing-backlog-chart'), {
      type: 'bar',
      data: {
        labels: wa.processing_backlog.map(r => r.bucket),
        datasets: [{ label: 'Orders', data: wa.processing_backlog.map(r => r.count), backgroundColor: '#fb7185', borderRadius: 6 }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
    });
    if (inreviewBacklogChart) inreviewBacklogChart.destroy();
    inreviewBacklogChart = new Chart(document.getElementById('inreview-backlog-chart'), {
      type: 'bar',
      data: {
        labels: wa.inreview_backlog.map(r => r.bucket),
        datasets: [{ label: 'Orders', data: wa.inreview_backlog.map(r => r.count), backgroundColor: '#22d3ee', borderRadius: 6 }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
    });
    if (last4daysChart) last4daysChart.destroy();
    const last4 = wa.last4days_completion || [];
    last4daysChart = new Chart(document.getElementById('last4days-chart'), {
      type: 'bar',
      data: {
        labels: last4.map(r => r.date),
        datasets: [
          { label: 'Within 4h', data: last4.map(r => r.within_4h), backgroundColor: '#34d399', borderRadius: 6 },
          { label: 'More than 4h', data: last4.map(r => r.more_than_4h), backgroundColor: '#f87171', borderRadius: 6 },
        ],
      },
      options: {
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: true },
          tooltip: {
            mode: 'index',
            intersect: false,
            callbacks: {
              footer: (items) => {
                const total = items.reduce((sum, item) => sum + item.parsed.y, 0);
                return 'Total: ' + total.toLocaleString('en-IN');
              },
            },
          },
        },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  }

  function renderHeatmap(mode, containerId, rowKeys) {
    if (!currentScope) return;
    const container = document.getElementById(containerId);
    const hours = Array.from({ length: 24 }, (_, h) => h);
    const source = mode === 'channel' ? currentScope.hourly_success_by_channel : currentScope.hourly_success_by_range;
    const keyField = mode === 'channel' ? 'channel' : 'range';
    const dataRows = rowKeys.map(key => ({
      label: key,
      byHour: hours.map(h => source.find(x => x.hour === h && x[keyField] === key)),
    }));
    if (!dataRows.length) {
      container.innerHTML = '<div class="no-data">No deposits for this date.</div>';
      return;
    }
    const thead = '<thead><tr><th class="row-label">' + (mode === 'channel' ? 'Channel' : 'Amount Range') + '</th>' +
      hours.map(h => '<th>' + h + '</th>').join('') + '<th class="row-total">Total Orders</th></tr></thead>';
    const tbody = '<tbody>' + dataRows.map(row => {
      const rowTotal = row.byHour.reduce((sum, c) => sum + (c ? c.total : 0), 0);
      return '<tr><td class="row-label">' + row.label + '</td>' +
      row.byHour.map(cell => {
        const total = cell ? cell.total : 0;
        const pct = cell ? cell.success_pct : 0;
        const { bg, color } = heatColor(total, pct);
        const text = total ? pct + '%' : '&mdash;';
        return '<td style="background:' + bg + ';color:' + color + '" title="' + (total ? total + ' orders' : 'no orders') + '">' + text + '</td>';
      }).join('') + '<td class="num row-total">' + fmt(rowTotal) + '</td></tr>';
    }).join('') + '</tbody>';
    container.innerHTML = '<table class="heat-table">' + thead + tbody + '</table>';
  }

  document.getElementById('btn-download').addEventListener('click', async () => {
    if (!currentScope) return;
    const wb = new ExcelJS.Workbook();
    const wsRange = wb.addWorksheet('Success by Amount Range');
    const rangeData = currentScope.success_by_range.map(r => ({
      'Amount Range': r.range, Total: r.total, Completed: r.completed, 'Success %': r.success_pct, 'Avg Time (min)': r.avg_minutes,
    }));
    if (rangeData.length) {
      wsRange.columns = Object.keys(rangeData[0]).map(k => ({ header: k, key: k, width: Math.max(12, k.length + 2) }));
      wsRange.addRows(rangeData);
    }
    styleHeaderRow(wsRange);
    const wsChannel = wb.addWorksheet('Success by Channel');
    const channelData = currentScope.success_by_channel.map(c => ({
      Channel: c.channel, 'Total Orders': c.total, 'Comp. Orders': c.comp_orders, 'Comp. Users': c.comp_users, 'Comp. Amount': c.comp_amount, 'Success %': c.success_pct, 'Avg Mins': c.avg_minutes,
    }));
    if (channelData.length) {
      wsChannel.columns = Object.keys(channelData[0]).map(k => ({ header: k, key: k, width: Math.max(12, k.length + 2) }));
      wsChannel.addRows(channelData);
    }
    styleHeaderRow(wsChannel);
    await saveWorkbook(wb, 'deposit-channel-analysis-' + (datePicker.value || 'report') + '.xlsx');
  });

  document.getElementById('btn-dl-amount-range').addEventListener('click', () => {
    if (!currentScope) return;
    const rangeRows = rangeOrder.map(r => currentScope.by_amount_range.find(x => x.range === r) || { range: r, count: 0, users: 0, total_amount: 0 });
    downloadStyledExcel(rangeRows.map(r => ({
      'Amount Range': r.range, Count: r.count, Users: r.users, 'Total Amount': r.total_amount,
    })), 'Amount Range', 'amount-range-' + (datePicker.value || 'report') + '.xlsx');
  });

  function heatColorARGB(total, pct) {
    if (!total) return 'FFF3F4F6';
    if (pct >= 41) return 'FFBBF7D0';
    if (pct >= 30) return 'FFFEF08A';
    return 'FFFECACA';
  }

  async function downloadHeatmapExcel(mode, rowKeys, filenamePrefix, sheetName) {
    if (!currentScope) return;
    const hours = Array.from({ length: 24 }, (_, h) => h);
    const source = mode === 'channel' ? currentScope.hourly_success_by_channel : currentScope.hourly_success_by_range;
    const keyField = mode === 'channel' ? 'channel' : 'range';
    const headerLabel = mode === 'channel' ? 'Channel' : 'Amount Range';

    const wb = new ExcelJS.Workbook();
    const ws = wb.addWorksheet(sheetName);
    ws.columns = [
      { header: headerLabel, key: 'label', width: 26 },
      ...hours.map(h => ({ header: String(h) + 'h', key: 'h' + h, width: 12 })),
      { header: 'Total Orders', key: 'total', width: 14 },
    ];
    ws.getRow(1).font = { bold: true };
    ws.getRow(1).alignment = { horizontal: 'center' };
    ws.getRow(1).eachCell(c => { c.fill = HEADER_FILL; });

    rowKeys.forEach(key => {
      const cellsByHour = hours.map(h => source.find(x => x.hour === h && x[keyField] === key));
      const rowTotal = cellsByHour.reduce((sum, c) => sum + (c ? c.total : 0), 0);
      const rowData = { label: key, total: rowTotal };
      hours.forEach((h, idx) => {
        const cell = cellsByHour[idx];
        const total = cell ? cell.total : 0;
        const pct = cell ? cell.success_pct : 0;
        rowData['h' + h] = total ? (pct + '% (' + total + ' orders)') : '—';
      });
      const row = ws.addRow(rowData);
      hours.forEach((h, idx) => {
        const cell = cellsByHour[idx];
        const total = cell ? cell.total : 0;
        const pct = cell ? cell.success_pct : 0;
        const c = row.getCell(2 + idx);
        c.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: heatColorARGB(total, pct) } };
        c.alignment = { horizontal: 'center' };
      });
      const totalCell = row.getCell(2 + hours.length);
      totalCell.font = { bold: true };
      totalCell.alignment = { horizontal: 'center' };
      totalCell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFF9FAFB' } };
    });

    ws.eachRow(row => {
      row.eachCell(c => {
        c.border = { top: { style: 'thin', color: { argb: 'FFEDEFF3' } }, bottom: { style: 'thin', color: { argb: 'FFEDEFF3' } },
          left: { style: 'thin', color: { argb: 'FFEDEFF3' } }, right: { style: 'thin', color: { argb: 'FFEDEFF3' } } };
      });
    });

    const buf = await wb.xlsx.writeBuffer();
    const blob = new Blob([buf], { type: 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filenamePrefix + '-' + (datePicker.value || 'report') + '.xlsx';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  document.getElementById('btn-dl-heatmap-range').addEventListener('click', () => {
    downloadHeatmapExcel('range', rangeOrder, 'hourly-success-by-range', 'Hourly Success by Range');
  });

  document.getElementById('btn-dl-heatmap-channel').addEventListener('click', () => {
    if (!currentScope) return;
    const channels = currentScope.by_channel.map(c => c.channel);
    downloadHeatmapExcel('channel', channels, 'hourly-success-by-channel', 'Hourly Success by Channel');
  });

  // Order Number below uses payment_center_order_no (the "TW..."-prefixed
  // field) -- the closest match found to a requested "TP"-prefixed order
  // number; order_no itself is "DIZC..."-prefixed and doesn't match.
  document.getElementById('btn-dl-withdrawal-orders').addEventListener('click', () => {
    if (!currentScope) return;
    const orders = (currentScope.withdrawal_orders || []).filter(o => o.status === 'Processing');
    downloadStyledExcel(orders.map(o => ({
      'User ID': o.user_id, Agent: o.agent || 'Un-Assigned', VIP: o.vip_level, 'Withdraw Amount': o.amount, Channel: o.channel,
      'Order Number': o.payment_center_order_no || o.order_no,
      'Hrs Processing': o.hours_processing == null ? '' : o.hours_processing,
    })), 'Withdrawal Orders (Processing)', 'withdrawal-orders-processing-' + (datePicker.value || 'report') + '.xlsx');
  });

  document.getElementById('btn-dl-withdrawal-completion').addEventListener('click', () => {
    if (!currentScope) return;
    const orders = (currentScope.withdrawal_orders || []).filter(o => o.status === 'Complete');
    downloadStyledExcel(orders.map(o => ({
      'User ID': o.user_id, Agent: o.agent || 'Un-Assigned', VIP: o.vip_level, 'Withdraw Amount': o.amount, Channel: o.channel,
      'Order Number': o.payment_center_order_no || o.order_no,
      'Hrs Completed': o.waiting_hours == null ? '' : o.waiting_hours,
    })), 'Withdrawal Orders (Completed)', 'withdrawal-orders-completed-' + (datePicker.value || 'report') + '.xlsx');
  });

  document.getElementById('btn-dl-processing-backlog').addEventListener('click', () => {
    const orders = (data.withdrawal_orders_full || []).filter(o => o.status === 'Processing');
    downloadStyledExcel(orders.map(o => ({
      'User ID': o.user_id, Agent: o.agent || 'Un-Assigned', VIP: o.vip_level, 'Withdraw Amount': o.amount, Channel: o.channel,
      'Order Number': o.payment_center_order_no || o.order_no,
      'Hrs in Processing': o.hours_processing == null ? '' : o.hours_processing,
    })), 'Processing Backlog', 'processing-orders-aging.xlsx');
  });

  document.getElementById('btn-dl-inreview-backlog').addEventListener('click', () => {
    const orders = (data.withdrawal_orders_full || []).filter(o => o.status === 'In-Review');
    downloadStyledExcel(orders.map(o => ({
      'User ID': o.user_id, Agent: o.agent || 'Un-Assigned', VIP: o.vip_level, 'Withdraw Amount': o.amount, Channel: o.channel,
      'Order Number': o.payment_center_order_no || o.order_no,
      'Hrs in Review': o.hours_in_review == null ? '' : o.hours_in_review,
    })), 'In-Review Backlog', 'inreview-orders-aging.xlsx');
  });

  document.getElementById('btn-dl-last4days').addEventListener('click', () => {
    const last4 = (data.dates || []).slice(-4);
    const orders = (data.withdrawal_orders_full || []).filter(o => o.status === 'Complete' && last4.includes(o.date));
    downloadStyledExcel(orders.map(o => ({
      'User ID': o.user_id, Agent: o.agent || 'Un-Assigned', VIP: o.vip_level, 'Withdraw Amount': o.amount, Channel: o.channel,
      'Order Number': o.payment_center_order_no || o.order_no,
      'Hrs Completed': o.waiting_hours == null ? '' : o.waiting_hours,
    })), 'Last 4 Days Completed Orders', 'completed-orders-last-4-days.xlsx');
  });

  // Date picker wiring
  const dateBar = document.getElementById('date-bar');
  const datePicker = document.getElementById('date-picker');
  const btnToday = document.getElementById('btn-today');
  const dayStatus = document.getElementById('day-status');
  dateBar.style.display = 'flex';

  if (data.total_registered_users != null) {
    document.getElementById('stat-total-users').textContent = fmt(data.total_registered_users);
    document.getElementById('stat-registered-active').textContent = fmt(data.total_registered_users);
  }

  const WEEKDAYS = ['SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];
  function selectDate(dateStr) {
    datePicker.value = dateStr;
    const isToday = dateStr === todayLocalISO();
    btnToday.classList.toggle('active', isToday);
    dayStatus.textContent = isToday ? 'TODAY' : WEEKDAYS[new Date(dateStr + 'T00:00:00').getDay()];
    dayStatus.classList.toggle('past', !isToday);
    const scope = data.by_date[dateStr] || EMPTY_SCOPE;
    render(scope, dateStr);
  }
  datePicker.addEventListener('change', () => selectDate(datePicker.value));
  btnToday.addEventListener('click', () => selectDate(todayLocalISO()));

  selectDate(todayLocalISO());
  renderBacklogCharts();
})();
</script>
</body>
</html>`;

// Must match slugify() in build_deposit_report.py exactly -- this is how
// the Worker maps a decoded agent name from the URL to the R2 object key
// build_deposit_report.py uploaded it under.
function slugifyAgentName(name) {
  const s = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return s || "agent";
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Per-agent dashboards: /agent/<name>(/action-center|analytics|search-user)?
    // -- the name is URL-encoded so decodeURIComponent recovers the exact
    // agent_assignments value client-side, with no lookup table needed.
    // Performance and Platform Analysis are never agent-scoped (no
    // /agent/<name>/performance or /agent/<name>/platform-analysis route).
    const agentPageMatch = url.pathname.match(/^\/agent\/([^/]+)(\/(action-center|analytics|search-user))?\/?$/);

    if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/action-center" || url.pathname === "/performance" || url.pathname === "/analytics" || url.pathname === "/platform-analysis" || url.pathname === "/search-user" || agentPageMatch)) {
      return new Response(PAGE, { headers: { "content-type": "text/html; charset=utf-8" } });
    }

    if (request.method === "GET" && url.pathname === "/data.json") {
      const agentParam = url.searchParams.get("agent");
      const key = agentParam ? `reports/agent/${slugifyAgentName(agentParam)}.json` : "reports/deposit_report.json";
      const obj = await env.USERLIST_BUCKET.get(key);
      if (!obj) {
        return new Response(JSON.stringify({ error: agentParam ? "Agent report not generated yet" : "Report not generated yet" }), {
          status: 404,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(obj.body, {
        headers: { "content-type": "application/json", "cache-control": "public, max-age=60" },
      });
    }

    // A 224MB+ SQLite file can't practically be queried per-request from a
    // Worker -- build_and_upload_user_search_index (build_deposit_report.py)
    // precomputes 40 small JSON shards every pipeline run instead, so a
    // search here is just one cheap R2 GET (shard = user_id % 40).
    if (request.method === "GET" && url.pathname === "/api/user-search") {
      const userIdParam = url.searchParams.get("user_id");
      const userId = parseInt(userIdParam, 10);
      if (!userIdParam || Number.isNaN(userId)) {
        return new Response(JSON.stringify({ error: "user_id must be a number" }), {
          status: 400,
          headers: { "content-type": "application/json" },
        });
      }
      const shard = ((userId % 40) + 40) % 40;
      const key = `user_search/shard_${String(shard).padStart(2, "0")}.json`;
      const obj = await env.USERLIST_BUCKET.get(key);
      if (!obj) {
        return new Response(JSON.stringify({ error: "Search index not built yet" }), {
          status: 404,
          headers: { "content-type": "application/json" },
        });
      }
      const shardData = await obj.json();
      const profile = shardData[String(userId)];
      if (!profile) {
        return new Response(JSON.stringify({ error: "User not found" }), {
          status: 404,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(JSON.stringify(profile), {
        headers: { "content-type": "application/json", "cache-control": "no-store" },
      });
    }

    if (request.method === "GET" && url.pathname === "/api/analytics-history") {
      const date = url.searchParams.get("date");
      if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        return new Response(JSON.stringify({ error: "date must be YYYY-MM-DD" }), {
          status: 400,
          headers: { "content-type": "application/json" },
        });
      }
      const obj = await env.USERLIST_BUCKET.get(`reports/analytics_history/${date}.json`);
      if (!obj) {
        return new Response(JSON.stringify({ error: "No snapshot for this date" }), {
          status: 404,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(obj.body, {
        headers: { "content-type": "application/json", "cache-control": "public, max-age=300" },
      });
    }

    return new Response("Not found", { status: 404 });
  },
};
