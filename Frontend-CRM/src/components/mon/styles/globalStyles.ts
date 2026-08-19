const globalStyles = `
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=DM+Mono:wght@400;500&display=swap');
:root {
  --bg:#f4f5f7;--surface:#ffffff;--surface-2:#f9fafb;--border:#e8eaed;--border-light:#f0f2f5;
  --text-primary:#0d1117;--text-secondary:#5c6370;--text-muted:#9ca3af;
  --blue:#2563eb;--blue-light:#eff6ff;--blue-mid:#bfdbfe;
  --green:#16a34a;--green-light:#f0fdf4;--green-mid:#bbf7d0;
  --red:#dc2626;--red-light:#fef2f2;--red-mid:#fecaca;
  --orange:#ea580c;--orange-light:#fff7ed;--orange-mid:#fed7aa;
  --yellow:#ca8a04;--yellow-light:#fefce8;--yellow-mid:#fef08a;
  --purple:#7c3aed;--purple-light:#faf5ff;
  --indigo:#4f46e5;--indigo-light:#eef2ff;
  --topbar-h:60px;
  --radius-sm:8px;--radius:12px;--radius-lg:16px;
  --shadow-sm:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --shadow:0 4px 12px rgba(0,0,0,.06),0 2px 6px rgba(0,0,0,.04);
  --shadow-lg:0 12px 32px rgba(0,0,0,.08),0 4px 12px rgba(0,0,0,.04);
  --transition:0.18s cubic-bezier(.4,0,.2,1);
}
.mon-app,.mon-app *{box-sizing:border-box}
.mon-app{margin:0;padding:0;font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text-primary);font-size:14px;line-height:1.5}
.mon-app{display:flex;height:100%;min-height:0;background:var(--bg);font-family:'DM Sans',sans-serif;font-size:14px;line-height:1.5;color:var(--text-primary)}
.mon-content{flex:1;min-width:0;width:100%;display:flex;flex-direction:column;position:relative;height:100%;min-height:0}
.mon-topbar{position:sticky;top:0;height:var(--topbar-h);background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 24px;gap:12px;z-index:120}
.mon-breadcrumb{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text-muted)}
.mon-breadcrumb-sep{color:var(--border)}
.mon-breadcrumb-current{color:var(--text-primary);font-weight:500}
.mon-breadcrumb span{cursor:pointer;transition:color var(--transition)}
.mon-breadcrumb span:hover{color:var(--blue)}
.mon-topbar-right{margin-left:auto;display:flex;align-items:center;gap:8px;min-width:0}
.mon-icon-btn{width:34px;height:34px;border-radius:var(--radius-sm);border:1px solid var(--border);background:transparent;display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--text-secondary);font-size:15px;transition:all var(--transition);position:relative}
.mon-icon-btn:hover{background:var(--bg);color:var(--text-primary)}
.mon-notif-dot{position:absolute;top:6px;right:6px;width:7px;height:7px;background:var(--red);border-radius:50%;border:2px solid white}
.mon-main{padding:28px 32px;flex:1;min-height:0;overflow-y:auto}
.page-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:28px}
.page-title{font-size:22px;font-weight:700;letter-spacing:-0.4px}
.page-subtitle{font-size:13px;color:var(--text-muted);margin-top:3px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:var(--radius-sm);font-family:inherit;font-size:13.5px;font-weight:500;cursor:pointer;transition:all var(--transition);border:1px solid transparent;white-space:nowrap}
.btn-primary{background:var(--blue);color:white;border-color:var(--blue)}
.btn-primary:hover{background:#1d4ed8;border-color:#1d4ed8;box-shadow:0 4px 12px rgba(37,99,235,.3);transform:translateY(-1px)}
.btn-secondary{background:white;color:var(--text-primary);border-color:var(--border)}
.btn-secondary:hover{background:var(--bg);border-color:#cbd5e1;transform:translateY(-1px)}
.btn-ghost{background:transparent;color:var(--text-secondary);border-color:transparent}
.btn-ghost:hover{background:var(--bg);color:var(--text-primary)}
.btn-danger{background:var(--red);color:white;border-color:var(--red)}
.btn-danger:hover{background:#b91c1c;border-color:#b91c1c}
.btn-success{background:var(--green);color:white;border-color:var(--green)}
.btn-success:hover{background:#15803d;border-color:#15803d;box-shadow:0 4px 12px rgba(22,163,74,.28);transform:translateY(-1px)}
.btn-sm{padding:5px 11px;font-size:12.5px}
.metrics-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}
.metric-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px 22px;box-shadow:var(--shadow-sm);transition:all var(--transition);position:relative;overflow:hidden;cursor:pointer}
.metric-card:hover{box-shadow:var(--shadow);transform:translateY(-2px)}
.metric-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:3px 3px 0 0}
.metric-card.red::before{background:var(--red)}
.metric-card.orange::before{background:var(--orange)}
.metric-card.blue::before{background:var(--blue)}
.metric-card.green::before{background:var(--green)}
.metric-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.metric-icon-wrap{width:38px;height:38px;border-radius:var(--radius-sm);display:flex;align-items:center;justify-content:center;font-size:17px}
.metric-card.red .metric-icon-wrap{background:var(--red-light)}
.metric-card.orange .metric-icon-wrap{background:var(--orange-light)}
.metric-card.blue .metric-icon-wrap{background:var(--blue-light)}
.metric-card.green .metric-icon-wrap{background:var(--green-light)}
.metric-trend{font-size:11.5px;font-weight:500;padding:2px 7px;border-radius:20px}
.trend-up{background:var(--red-light);color:var(--red)}
.trend-down{background:var(--green-light);color:var(--green)}
.trend-neutral{background:var(--blue-light);color:var(--blue)}
.metric-value{font-size:30px;font-weight:700;letter-spacing:-1px;line-height:1;margin-bottom:4px}
.metric-label{font-size:12.5px;font-weight:500;color:var(--text-secondary)}
.metric-sub{font-size:11.5px;color:var(--text-muted);margin-top:3px}
.tabs-bar{display:flex;gap:0;border-bottom:1px solid var(--border);margin-bottom:20px;overflow-x:auto}
.tab-item{padding:10px 20px;font-size:13.5px;font-weight:500;color:var(--text-muted);cursor:pointer;position:relative;transition:color var(--transition);border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;border:none;background:transparent;font-family:inherit;border-bottom:2px solid transparent}
.tab-item:hover{color:var(--text-primary)}
.tab-item.active{color:var(--blue);border-bottom-color:var(--blue)}
.tab-count{font-size:11px;background:var(--bg);border:1px solid var(--border);border-radius:20px;padding:1px 6px;margin-left:5px;color:var(--text-muted)}
.tab-item.active .tab-count{background:var(--blue-light);border-color:var(--blue-mid);color:var(--blue)}
.tab-dropdown{position:relative;display:inline-flex;align-items:stretch}
.tab-dropdown-trigger{display:inline-flex;align-items:center;gap:6px;padding:10px 16px;font-size:13.5px;font-weight:500;color:var(--text-muted);cursor:pointer;position:relative;transition:color var(--transition),background var(--transition);border:none;background:transparent;font-family:inherit;border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;border-radius:6px 6px 0 0}
.tab-dropdown-trigger:hover{color:var(--text-primary);background:var(--bg)}
.tab-dropdown-trigger.active{color:var(--blue);border-bottom-color:var(--blue);background:transparent}
.tab-dropdown-trigger .tab-count{margin-left:2px}
.tab-dropdown-trigger.active .tab-count{background:var(--blue-light);border-color:var(--blue-mid);color:var(--blue)}
.tab-dropdown-caret{transition:transform var(--transition);font-size:10px;color:currentColor;display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;line-height:1}
.tab-dropdown-trigger[aria-expanded="true"] .tab-dropdown-caret{transform:rotate(180deg)}
.tab-dropdown-menu{min-width:240px;background:var(--surface);border:1px solid var(--border);border-radius:10px;box-shadow:0 12px 28px rgba(13,17,23,.12),0 4px 10px rgba(13,17,23,.06);padding:6px;z-index:1000;display:flex;flex-direction:column;gap:2px}
.tab-dropdown-item{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 12px 9px 28px;border-radius:6px;font-size:13px;font-weight:500;color:var(--text-primary);background:transparent;border:none;cursor:pointer;transition:background var(--transition),color var(--transition);font-family:inherit;text-align:left;width:100%;position:relative}
.tab-dropdown-item:hover{background:var(--blue-light);color:var(--blue)}
.tab-dropdown-item.active{background:var(--blue-light);color:var(--blue);font-weight:600}
.tab-dropdown-item.active::before{content:"\\2713";position:absolute;left:10px;top:50%;transform:translateY(-50%);font-size:12px;font-weight:700;color:var(--blue)}
.tab-dropdown-item .tab-count{margin-left:auto}
.tab-dropdown-item.active .tab-count{background:var(--blue);border-color:var(--blue);color:#fff}
.tab-dropdown-item-meta{display:block;font-size:11.5px;font-weight:400;color:var(--text-muted);margin-top:2px}
.tab-dropdown-item.active .tab-dropdown-item-meta{color:var(--blue)}
.table-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow-sm);overflow:hidden}
.table-toolbar{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.filter-group{display:flex;gap:8px;flex:1;flex-wrap:wrap}
.table-toolbar-actions{display:flex;align-items:center;gap:8px;flex-shrink:0;margin-left:auto;flex-wrap:wrap}
.table-toolbar-search{display:flex;align-items:center;gap:8px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 11px;min-width:140px;flex:1 1 180px;max-width:280px;transition:all var(--transition)}
.table-toolbar-search:focus-within{border-color:var(--blue);background:white;box-shadow:0 0 0 3px rgba(37,99,235,.08)}
.table-toolbar-search input{border:none;background:transparent;font-size:13px;color:var(--text-primary);font-family:inherit;outline:none;width:100%;min-width:0}
.table-toolbar-search input::placeholder{color:var(--text-muted)}
.filter-select{appearance:none;background:var(--bg) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E") no-repeat right 10px center;border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 28px 6px 11px;font-family:inherit;font-size:13px;color:var(--text-primary);cursor:pointer;transition:all var(--transition);outline:none}
.filter-select:hover{border-color:#94a3b8}
.filter-select:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(37,99,235,.08)}
.mon-app table{width:100%;border-collapse:collapse}
.mon-app thead th{padding:11px 16px;text-align:left;font-size:11.5px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted);background:var(--surface-2);border-bottom:1px solid var(--border);white-space:nowrap}
.mon-app tbody tr{border-bottom:1px solid var(--border-light);transition:background var(--transition);cursor:pointer}
.mon-app tbody tr:last-child{border-bottom:none}
.mon-app tbody tr:hover{background:#fafbff}
.mon-app tbody td{padding:13px 16px;font-size:13.5px}
.td-primary{font-weight:500;color:var(--text-primary)}
.mon-app .td-site-name{max-width:min(280px,30vw);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle}
.td-secondary{color:var(--text-secondary)}
.badge{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:500;padding:3px 9px;border-radius:20px;white-space:nowrap}
.badge-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.badge.green{background:var(--green-light);color:var(--green)}
.badge.green .badge-dot{background:var(--green)}
.badge.red{background:var(--red-light);color:var(--red)}
.badge.red .badge-dot{background:var(--red)}
.badge.orange{background:var(--orange-light);color:var(--orange)}
.badge.orange .badge-dot{background:var(--orange)}
.badge.yellow{background:var(--yellow-light);color:var(--yellow)}
.badge.yellow .badge-dot{background:var(--yellow)}
.badge.blue{background:var(--blue-light);color:var(--blue)}
.badge.blue .badge-dot{background:var(--blue)}
.badge.purple{background:var(--purple-light);color:var(--purple)}
.badge.indigo{background:var(--indigo-light);color:var(--indigo)}
.badge.indigo .badge-dot{background:var(--indigo)}
.badge.gray{background:var(--bg);color:var(--text-secondary);border:1px solid var(--border)}
.action-btns{display:flex;gap:4px}
.action-btn{width:28px;height:28px;border-radius:6px;border:1px solid var(--border);background:transparent;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:13px;color:var(--text-muted);transition:all var(--transition)}
.action-btn:hover{background:var(--bg);color:var(--text-primary);border-color:#94a3b8}
.table-footer{padding:12px 18px;border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;background:var(--surface-2)}
.pagination{display:flex;gap:4px}
.page-btn{width:30px;height:30px;border-radius:var(--radius-sm);border:1px solid var(--border);background:white;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:13px;font-weight:500;color:var(--text-secondary);transition:all var(--transition)}
.page-btn:hover{border-color:var(--blue);color:var(--blue)}
.page-btn.active{background:var(--blue);border-color:var(--blue);color:white}
.table-info{font-size:12.5px;color:var(--text-muted)}
/* ── Visit Workflow Stepper ───────────────────────────────────────────────── */
.vws-root{display:flex;align-items:flex-start;padding:20px 24px;margin-bottom:20px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);box-shadow:var(--shadow-sm)}
.vws-item{display:flex;flex-direction:column;align-items:center;gap:8px;flex-shrink:0;position:relative;min-width:80px}
.vws-bubble-wrap{position:relative;display:flex;align-items:center;justify-content:center}
.vws-bubble{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:700;border:2px solid;transition:background .2s,border-color .2s,box-shadow .2s;position:relative;z-index:1}
.vws-num{font-size:13px;font-weight:700;line-height:1}
.vws-pulse{position:absolute;inset:-6px;border-radius:50%;background:rgba(37,99,235,.12);animation:vwsPulse 2s cubic-bezier(.4,0,.6,1) infinite;z-index:0}
@keyframes vwsPulse{0%,100%{transform:scale(1);opacity:.7}50%{transform:scale(1.2);opacity:0}}
.vws-label{font-size:11.5px;font-weight:600;text-align:center;line-height:1.35;max-width:82px;letter-spacing:.01em;white-space:normal}
/* upcoming (default) */
.vws-upcoming .vws-bubble{background:var(--surface-2);border-color:var(--border);color:var(--text-muted);box-shadow:none}
.vws-upcoming .vws-label{color:var(--text-muted)}
/* active */
.vws-active .vws-bubble{background:var(--blue);border-color:var(--blue);color:#fff;box-shadow:0 0 0 5px rgba(37,99,235,.15),0 4px 14px rgba(37,99,235,.35)}
.vws-active .vws-label{color:var(--blue);font-weight:700}
/* done */
.vws-done .vws-bubble{background:var(--green);border-color:var(--green);color:#fff;box-shadow:0 2px 8px rgba(22,163,74,.25)}
.vws-done .vws-label{color:var(--green)}
/* connector track */
.vws-track{flex:1;height:2px;margin-top:19px;position:relative;background:var(--border-light);border-radius:2px;overflow:hidden;min-width:16px}
.vws-track-fill{position:absolute;inset:0;background:var(--border);transform:scaleX(0);transform-origin:left;transition:transform .4s ease}
.vws-track-done .vws-track-fill{background:var(--green);transform:scaleX(1)}
.detail-header{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:24px 28px;margin-bottom:20px;box-shadow:var(--shadow-sm)}
.detail-title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px}
.detail-title{font-size:20px;font-weight:700;letter-spacing:-0.3px}
.detail-subtitle{font-size:13px;color:var(--text-muted);margin-top:3px}
.detail-badges{display:flex;gap:8px;margin-top:10px;align-items:center}
.detail-actions{display:flex;gap:8px;flex-shrink:0;flex-wrap:wrap}
.detail-meta{display:flex;gap:24px;padding-top:16px;border-top:1px solid var(--border);flex-wrap:wrap}
.meta-item{display:flex;flex-direction:column;gap:2px}
.meta-label{font-size:11px;color:var(--text-muted);font-weight:600;letter-spacing:.05em;text-transform:uppercase}
.meta-val{font-size:13.5px;font-weight:500}
.overview-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.info-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px 22px;box-shadow:var(--shadow-sm)}
.info-card-title{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);margin-bottom:14px}
.info-rows{display:flex;flex-direction:column;gap:10px}
.info-row{display:flex;justify-content:space-between;align-items:center}
.info-key{font-size:13px;color:var(--text-secondary)}
.info-val{font-size:13px;font-weight:500;color:var(--text-primary)}
.doc-toolbar{display:flex;gap:8px;padding:12px 16px;border-bottom:1px solid var(--border);background:var(--surface-2);border-radius:var(--radius) var(--radius) 0 0;flex-wrap:wrap}
.doc-viewer{background:white;padding:40px 48px;min-height:400px;border-radius:0 0 var(--radius) var(--radius);border:1px solid var(--border);border-top:none;font-size:14px;line-height:1.8;color:var(--text-primary)}
.doc-viewer h3{font-size:16px;font-weight:700;margin-bottom:8px}
.doc-viewer p{margin-bottom:12px;color:var(--text-secondary)}
.doc-section{margin-bottom:24px}
.doc-meta{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px;padding:16px;background:var(--bg);border-radius:var(--radius-sm)}
.doc-meta-item{font-size:13px}
.doc-meta-item strong{display:block;font-weight:600;color:var(--text-primary)}
.doc-meta-item span{color:var(--text-muted);font-size:12px}
.doc-meta--rich{background:linear-gradient(135deg,#f0f9ff 0%,#f8fafc 50%,#faf5ff 100%);border:1px solid #e2e8f0;box-shadow:0 1px 3px rgba(15,23,42,.06)}
.doc-meta--rich .doc-meta-item span{color:var(--text-primary);font-size:13px;font-weight:500}
.conf-letter{max-width:820px;margin:0 auto;font-family:inherit}
.conf-letter-banner{display:flex;align-items:center;gap:16px;margin-bottom:28px;padding-bottom:22px;border-bottom:2px solid var(--border)}
.conf-letter-banner-icon{width:52px;height:52px;border-radius:12px;background:linear-gradient(135deg,#0ea5e9,#6366f1);display:flex;align-items:center;justify-content:center;color:#fff;font-size:26px;flex-shrink:0;box-shadow:0 4px 14px rgba(99,102,241,.35)}
.conf-letter-title{margin:0;font-size:20px;font-weight:700;color:var(--text-primary);letter-spacing:-.02em}
.conf-letter-subtitle{margin:6px 0 0;font-size:13px;color:var(--text-muted)}
.conf-envelope-lines{margin-top:12px;padding-top:10px;border-top:1px solid var(--border)}
.conf-envelope-line{margin:0 0 6px;font-size:12.5px;color:var(--text-secondary);line-height:1.45}
.conf-envelope-line:last-child{margin-bottom:0}
.conf-envelope-label{font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted);margin-right:8px;font-size:10.5px}
.conf-header-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 24px;margin-bottom:28px;padding:18px 20px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm)}
.conf-header-cell{display:flex;flex-direction:column;gap:4px;min-width:0}
.conf-header-label{font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted)}
.conf-header-value{font-size:13.5px;font-weight:500;color:var(--text-primary);line-height:1.45;word-break:break-word}
.conf-salutation{margin:0 0 16px;font-size:15px;font-weight:600;color:var(--text-primary)}
.conf-paragraph{margin:0 0 14px;font-size:14px;line-height:1.75;color:var(--text-secondary)}
.conf-section{margin-bottom:22px;padding:18px 20px 16px;border-left:4px solid var(--blue);background:var(--surface);border:1px solid var(--border);border-radius:0 var(--radius-sm) var(--radius-sm) 0;box-shadow:var(--shadow-sm)}
.conf-section-title{margin:0 0 12px;font-size:14.5px;font-weight:700;letter-spacing:.01em}
.conf-list{margin:0;padding-left:1.25rem;list-style:disc}
.conf-list-item{margin-bottom:8px;font-size:13.5px;line-height:1.65;color:var(--text-secondary)}
.conf-list-item:last-child{margin-bottom:0}
.conf-ack{background:linear-gradient(135deg,#f0fdf4 0%,#fff 100%);border-color:#bbf7d0}
.conf-signature{margin-top:32px;padding-top:22px;border-top:1px solid var(--border)}
.conf-signature-lead{margin:0 0 14px;font-size:14px;color:var(--text-muted)}
.conf-signature-line{margin:0 0 6px;font-size:14px;color:var(--text-secondary)}
.conf-signature-name{margin:0 0 6px;font-size:15px;font-weight:700;color:var(--text-primary)}
.conf-letter-editor{max-width:820px;margin:0 auto;display:flex;flex-direction:column;gap:16px}
.conf-letter-editor-locked{padding:14px 16px;background:#f1f5f9;border:1px solid #cbd5e1;border-radius:var(--radius-sm)}
.conf-letter-editor-locked-label{margin:0 0 8px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#64748b}
.conf-letter-editor-locked-text{margin:0;font-family:inherit;font-size:13.5px;line-height:1.7;color:#334155;white-space:pre-wrap;word-break:break-word}
.conf-letter-editor-editable{display:flex;flex-direction:column;gap:6px}
.conf-letter-editor-editable-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#475569}
.conf-letter-editor-textarea{width:100%;min-height:120px;border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;font-family:inherit;font-size:14px;line-height:1.7;color:var(--text-primary);background:#fff;outline:none;resize:vertical}
.conf-letter-editor-textarea:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(59,130,246,.15)}
.doc-viewer--letter{background:linear-gradient(180deg,#f8fafc 0%,#fff 12%);padding:32px 40px 48px}
.form-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;box-shadow:var(--shadow-sm);margin-bottom:16px}
.form-card-title{font-size:13.5px;font-weight:600;margin-bottom:18px;color:var(--text-primary)}
.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.form-group{display:flex;flex-direction:column;gap:6px}
.form-group.full{grid-column:1/-1}
.form-label{font-size:12.5px;font-weight:500;color:var(--text-secondary)}
.form-input,.form-select,.form-textarea{border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;font-family:inherit;font-size:13.5px;color:var(--text-primary);background:var(--surface);transition:all var(--transition);outline:none}
.form-input:focus,.form-select:focus,.form-textarea:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(37,99,235,.08)}
.form-select{appearance:none;background:var(--surface) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E") no-repeat right 10px center;padding-right:28px;cursor:pointer}
.form-textarea{resize:vertical;min-height:100px}
.form-actions{display:flex;gap:10px;justify-content:flex-end;padding-top:8px}
.avatar{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;color:white;flex-shrink:0}
.av-blue{background:linear-gradient(135deg,#3b82f6,#1d4ed8)}
.av-purple{background:linear-gradient(135deg,#8b5cf6,#7c3aed)}
.av-green{background:linear-gradient(135deg,#10b981,#059669)}
.av-orange{background:linear-gradient(135deg,#f59e0b,#d97706)}
.av-red{background:linear-gradient(135deg,#ef4444,#dc2626)}
.av-teal{background:linear-gradient(135deg,#14b8a6,#0d9488)}
.avatar-stack{display:flex;align-items:center;gap:8px}
.finding-action-primary{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0}
.finding-action-more{display:inline-flex;align-items:center;padding:1px 7px;border-radius:999px;font-size:11px;font-weight:600;color:var(--blue);background:var(--blue-light);white-space:nowrap;cursor:default}
.finding-action-more--inline{padding:0;background:transparent;font-size:12px;font-weight:500}
.finding-action-resolution{display:block;max-width:180px;font-size:12.5px;color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.finding-action-due{font-size:13px;white-space:nowrap}
.finding-action-summary{font-size:13px;color:var(--text-secondary);white-space:nowrap}
.finding-action-summary-sep{color:var(--text-muted)}
.finding-action-summary--multi{font-weight:500;color:var(--blue)}
.chat-container{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow-sm);display:flex;flex-direction:column;height:520px}
.chat-header{padding:14px 18px;border-bottom:1px solid var(--border);font-weight:600;font-size:13.5px;display:flex;align-items:center;gap:8px;flex-shrink:0}
.chat-header-right{margin-left:auto;display:flex;align-items:center;gap:8px}
.online-dot{width:8px;height:8px;background:var(--green);border-radius:50%}
.chat-msgs{flex:1;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:16px}
.chat-bubble{background:var(--bg);border:1px solid var(--border);border-radius:0 12px 12px 12px;padding:10px 14px;max-width:480px}
.chat-msg{display:flex;gap:10px;align-items:flex-start}
.chat-msg.me{flex-direction:row-reverse}
.chat-msg.me .chat-bubble{background:var(--blue-light);border-color:var(--blue-mid);border-radius:12px 0 12px 12px}
.chat-sender{font-size:12px;font-weight:600;color:var(--text-primary)}
.chat-text{font-size:13px;color:var(--text-secondary);margin-top:2px;line-height:1.5}
.chat-time{font-size:11px;color:var(--text-muted);margin-top:4px}
.chat-input-bar{padding:12px 16px;border-top:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-shrink:0}
.chat-input{flex:1;border:1px solid var(--border);border-radius:var(--radius-sm);padding:9px 13px;font-family:inherit;font-size:13.5px;outline:none;transition:all var(--transition)}
.chat-input:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(37,99,235,.08)}
.chat-participants{display:flex;gap:8px;padding:10px 18px;border-bottom:1px solid var(--border);background:var(--surface-2);font-size:12px;color:var(--text-muted);align-items:center;flex-wrap:wrap}
.participant-chip{display:flex;align-items:center;gap:5px;background:white;border:1px solid var(--border);border-radius:20px;padding:2px 8px 2px 4px;font-size:12px}
.severity-group{margin-bottom:20px}
.severity-header{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.severity-line{flex:1;height:1px;background:var(--border)}
.finding-row{display:flex;align-items:center;gap:12px;padding:10px 14px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:6px;transition:background var(--transition)}
.finding-row:hover{background:#f1f5f9}
.find-num{font-family:'DM Mono',monospace;font-size:11.5px;color:var(--text-muted);width:40px;flex-shrink:0}
.find-title{font-size:13px;font-weight:500;flex:1}
.find-meta{font-size:12px;color:var(--text-muted);flex-shrink:0}
.toast-container{position:fixed;bottom:24px;right:24px;z-index:1000;display:flex;flex-direction:column;gap:8px}
.toast{background:var(--text-primary);color:white;padding:12px 16px;border-radius:var(--radius);font-size:13.5px;display:flex;align-items:center;gap:10px;box-shadow:var(--shadow-lg);min-width:260px}
.toast.success{background:#15803d}
.toast.error{background:var(--red)}
.toast-icon{font-size:16px}
.toast-close{margin-left:auto;cursor:pointer;opacity:.7;font-size:16px;background:none;border:none;color:white}
.toast-close:hover{opacity:1}
.empty-state{display:flex;flex-direction:column;align-items:center;padding:60px 20px;color:var(--text-muted);text-align:center}
.empty-icon{font-size:40px;margin-bottom:12px;opacity:.5}
.empty-title{font-size:15px;font-weight:600;color:var(--text-secondary);margin-bottom:6px}
.empty-sub{font-size:13px;max-width:260px}
.progress-bar-wrap{background:var(--border);border-radius:20px;height:6px;overflow:hidden}
.progress-bar-fill{height:100%;border-radius:20px;transition:width .5s ease}
.stat-row{display:flex;gap:12px;margin-bottom:20px}
.stat-box{flex:1;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px 18px;text-align:center;box-shadow:var(--shadow-sm)}
.stat-num{font-size:24px;font-weight:700;letter-spacing:-0.5px;line-height:1}
.stat-lbl{font-size:12px;color:var(--text-muted);margin-top:4px}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:500;display:flex;align-items:center;justify-content:center;padding:24px}
.modal{background:var(--surface);border-radius:var(--radius-lg);max-width:700px;width:min(700px,calc(100vw - 48px));max-height:min(90vh,calc(100dvh - 48px));box-shadow:var(--shadow-lg);display:flex;flex-direction:column;overflow:hidden}
.modal-header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:24px 28px 0;flex-shrink:0}
.modal-header--accent{align-items:flex-start;padding:22px 28px;background:linear-gradient(135deg,#168AAD 0%,#76C893 100%);position:relative;overflow:hidden}
.modal-header--accent::before{content:"";position:absolute;right:-32px;top:-40px;width:140px;height:140px;border-radius:50%;background:rgba(255,255,255,.08)}
.modal-header--accent .modal-title{color:#fff}
.modal-header--accent .modal-subtitle{color:rgba(255,255,255,.82)}
.modal-header--accent .modal-close{color:rgba(255,255,255,.85)}
.modal-header--accent .modal-close:hover{color:#fff;background:rgba(255,255,255,.18)}
.modal-header-icon{position:relative;flex-shrink:0;display:flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:12px;background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.3);color:#fff}
.modal-title{font-size:17px;font-weight:700;margin:0;line-height:1.3}
.modal-subtitle{font-size:12.5px;margin-top:3px;line-height:1.4;color:var(--text-muted)}
.modal-close{position:relative;background:none;border:none;font-size:18px;line-height:1;cursor:pointer;color:var(--text-muted);padding:4px;border-radius:var(--radius-sm);flex-shrink:0}
.modal-close:hover{color:var(--text-primary);background:var(--surface-2)}
.modal-body{padding:20px 28px;overflow-y:auto;overflow-x:hidden;flex:1;min-height:0;-webkit-overflow-scrolling:touch}
.modal-footer{display:flex;gap:8px;justify-content:flex-end;flex-shrink:0;padding:16px 28px 24px;border-top:1px solid var(--border);background:var(--surface)}
.action-item-card{border:1px solid var(--border);border-radius:12px;padding:16px;background:var(--surface);transition:border-color var(--transition),box-shadow var(--transition)}
.action-item-card:hover{border-color:#76C893;box-shadow:0 2px 10px rgba(22,138,173,.08)}
.action-item-badge{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:999px;background:linear-gradient(135deg,#168AAD 0%,#76C893 100%);color:#fff;font-size:11px;font-weight:700;flex-shrink:0}
.action-item-remove{display:inline-flex;align-items:center;gap:4px;border:none;background:transparent;color:var(--red);font-size:12px;font-weight:600;cursor:pointer;padding:4px 6px;border-radius:6px}
.action-item-remove:hover{background:var(--red-light)}
.alert-banner{display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:var(--radius-sm);margin-bottom:16px;font-size:13px}
.alert-banner.warning{background:var(--orange-light);border:1px solid var(--orange-mid);color:var(--orange)}
.alert-banner.error{background:var(--red-light);border:1px solid var(--red-mid);color:var(--red)}
.alert-banner.info{background:var(--blue-light);border:1px solid var(--blue-mid);color:var(--blue)}
.alert-banner.success{background:var(--green-light);border:1px solid var(--green-mid);color:var(--green)}
.checklist{display:flex;flex-direction:column;gap:8px}
.check-item{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);transition:background var(--transition);cursor:pointer}
.check-item:hover{background:#f1f5f9}
.check-item input[type="checkbox"]{width:16px;height:16px;accent-color:var(--blue);cursor:pointer;flex-shrink:0}
.check-label{font-size:13px;flex:1}
.check-item.done .check-label{text-decoration:line-through;color:var(--text-muted)}
.check-tag{font-size:11px;padding:2px 7px;border-radius:20px;flex-shrink:0}
.check-tag.required-tag{background:var(--red-light);color:var(--red)}
.check-tag.optional-tag{background:var(--blue-light);color:var(--blue)}
.check-tag.done-tag{background:var(--green-light);color:var(--green)}
.pending-list{display:flex;flex-direction:column;gap:8px}
.pending-item{display:flex;align-items:center;justify-content:space-between;padding:9px 12px;background:var(--bg);border-radius:var(--radius-sm);border:1px solid var(--border)}
.pending-item-left{display:flex;align-items:center;gap:8px;font-size:13px}
.docs-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}
.doc-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:18px 16px;display:flex;flex-direction:column;align-items:center;gap:10px;text-align:center;cursor:pointer;transition:all var(--transition);box-shadow:var(--shadow-sm)}
.doc-card:hover{box-shadow:var(--shadow);transform:translateY(-2px);border-color:#94a3b8}
.doc-card-icon{font-size:32px}
.doc-card-name{font-size:12.5px;font-weight:500;color:var(--text-primary);word-break:break-all}
.doc-card-size{font-size:11px;color:var(--text-muted)}
.doc-card-date{font-size:11px;color:var(--text-muted)}
.doc-card-actions{display:flex;gap:6px}
.risk-select-wrap{position:relative}
.risk-indicator{width:10px;height:10px;border-radius:50%;position:absolute;left:11px;top:50%;transform:translateY(-50%);pointer-events:none}
.risk-select-wrap .form-select{padding-left:28px}
.risk-high{background:var(--red)}
.risk-medium{background:var(--orange)}
.risk-low{background:var(--yellow)}
.divider{height:1px;background:var(--border);margin:20px 0}
.skeleton{background:linear-gradient(90deg,#f0f2f5 25%,#e8eaed 50%,#f0f2f5 75%);background-size:200% 100%;border-radius:4px;animation:shimmer 1.6s infinite}
@keyframes shimmer{from{background-position:200% 0}to{background-position:-200% 0}}
.sk-line{height:14px;margin-bottom:8px;border-radius:4px}
.mon-app ::-webkit-scrollbar{width:6px;height:6px}
.mon-app ::-webkit-scrollbar-track{background:transparent}
.mon-app ::-webkit-scrollbar-thumb{background:#dde1e7;border-radius:10px}
.mon-app ::-webkit-scrollbar-thumb:hover{background:#c1c9d2}
.findings-summary-bar{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.fsb-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;display:flex;align-items:center;gap:12px;box-shadow:var(--shadow-sm)}
.fsb-icon{width:36px;height:36px;border-radius:var(--radius-sm);display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.fsb-val{font-size:22px;font-weight:700;letter-spacing:-0.5px;line-height:1}
.fsb-lbl{font-size:12px;color:var(--text-muted);margin-top:2px}
.report-stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:24px}
.report-stat-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px 22px;box-shadow:var(--shadow-sm)}
.report-type-pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:500;padding:4px 10px;border-radius:20px;background:var(--bg);border:1px solid var(--border);color:var(--text-secondary)}
.sites-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
.site-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;box-shadow:var(--shadow-sm);transition:all var(--transition);cursor:pointer}
.site-card:hover{box-shadow:var(--shadow);transform:translateY(-2px)}
.site-card-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:14px}
.site-card-name{font-size:15px;font-weight:600;letter-spacing:-0.2px}
.site-card-sub{font-size:12.5px;color:var(--text-muted);margin-top:2px}
.site-card-metrics{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;padding-top:14px;border-top:1px solid var(--border)}
.scm-item{text-align:center}
.scm-val{font-size:18px;font-weight:700;letter-spacing:-0.3px}
.scm-lbl{font-size:11px;color:var(--text-muted);margin-top:2px}
.team-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.team-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;box-shadow:var(--shadow-sm);display:flex;align-items:flex-start;gap:14px;transition:all var(--transition)}
.team-card:hover{box-shadow:var(--shadow);transform:translateY(-2px)}
.team-card-info{flex:1}
.team-card-name{font-size:14px;font-weight:600}
.team-card-role{font-size:12.5px;color:var(--text-muted);margin-top:2px}
.team-card-meta{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
.settings-layout{display:grid;grid-template-columns:220px 1fr;gap:20px}
.settings-nav{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow-sm);padding:8px;height:fit-content}
.settings-nav-item{display:flex;align-items:center;gap:8px;padding:9px 12px;border-radius:var(--radius-sm);cursor:pointer;transition:all var(--transition);font-size:13.5px;color:var(--text-secondary);border:none;background:transparent;width:100%;text-align:left;font-family:inherit}
.settings-nav-item:hover{background:var(--bg);color:var(--text-primary)}
.settings-nav-item.active{background:var(--blue-light);color:var(--blue);font-weight:500}
.settings-content{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;box-shadow:var(--shadow-sm)}
.settings-section{margin-bottom:28px}
.settings-section-title{font-size:13.5px;font-weight:600;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid var(--border)}
.settings-row{display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--border-light)}
.settings-row:last-child{border-bottom:none}
.settings-row-info{flex:1}
.settings-row-label{font-size:13.5px;font-weight:500}
.settings-row-sub{font-size:12.5px;color:var(--text-muted);margin-top:2px}
.toggle{position:relative;width:42px;height:24px;flex-shrink:0}
.toggle input{opacity:0;width:0;height:0}
.toggle-slider{position:absolute;cursor:pointer;inset:0;background:#d1d5db;border-radius:24px;transition:.3s}
.toggle-slider:before{position:absolute;content:'';height:18px;width:18px;left:3px;bottom:3px;background:white;border-radius:50%;transition:.3s;box-shadow:0 1px 3px rgba(0,0,0,.2)}
.toggle input:checked + .toggle-slider{background:var(--blue)}
.toggle input:checked + .toggle-slider:before{transform:translateX(18px)}
.upload-zone{border:2px dashed var(--border);border-radius:var(--radius);padding:32px;text-align:center;transition:all var(--transition);cursor:pointer;background:var(--surface-2)}
.upload-zone:hover,.upload-zone.drag-over{border-color:var(--blue);background:var(--blue-light)}
.upload-zone-icon{font-size:32px;margin-bottom:8px}
.upload-zone-text{font-size:13.5px;font-weight:500;color:var(--text-secondary)}
.upload-zone-sub{font-size:12px;color:var(--text-muted);margin-top:4px}
.notif-panel{position:fixed;top:var(--topbar-h);right:0;width:360px;background:var(--surface);border-left:1px solid var(--border);height:calc(100vh - var(--topbar-h));z-index:200;box-shadow:var(--shadow-lg);display:flex;flex-direction:column;transition:transform var(--transition)}
.notif-panel.hidden{transform:translateX(100%)}
.notif-header{padding:16px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.notif-title{font-size:14px;font-weight:600}
.notif-item{padding:14px 18px;border-bottom:1px solid var(--border-light);transition:background var(--transition);cursor:pointer}
.notif-item:hover{background:var(--bg)}
.notif-item.unread{background:var(--blue-light)}
.notif-icon{font-size:18px;width:36px;height:36px;border-radius:var(--radius-sm);background:var(--bg);display:flex;align-items:center;justify-content:center;flex-shrink:0}
@media(max-width:1100px){.metrics-grid{grid-template-columns:repeat(2,1fr)}.findings-summary-bar{grid-template-columns:repeat(2,1fr)}}
@media(max-width:768px){
  .mon-topbar{padding:0 12px;gap:8px}
  .mon-breadcrumb{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
  .mon-topbar-right{gap:6px}
  .table-toolbar-search{flex:1 1 160px;max-width:none}
  .table-toolbar-search input{font-size:12px}
  .vws-root{padding:14px 16px;gap:0}
  .vws-label{font-size:11px;max-width:70px}
  .vws-bubble{width:32px;height:32px}
  .vws-track{margin-top:16px}
  .mon-main{padding:20px 16px}
  .metrics-grid{grid-template-columns:1fr 1fr;gap:12px}
  .overview-grid{grid-template-columns:1fr}
  .form-grid{grid-template-columns:1fr}
  .settings-layout{grid-template-columns:1fr}
  .findings-summary-bar{grid-template-columns:1fr 1fr}
  .report-stat-grid{grid-template-columns:1fr}
  .sites-grid{grid-template-columns:1fr}
  .team-grid{grid-template-columns:1fr}
  .table-card{overflow-x:auto}
  .mon-app table{min-width:760px}
  .notif-panel{width:min(88vw,340px)}
}
@media(max-width:480px){
  .mon-topbar{height:52px;padding:0 8px;gap:6px}
  .mon-icon-btn{width:30px;height:30px;font-size:13px}
  .mon-breadcrumb{font-size:12px}
  .mon-topbar{padding:0 10px}
  .mon-main{padding:12px 8px}
  .metrics-grid,.findings-summary-bar{grid-template-columns:1fr}
  .tabs-bar{gap:6px}
  .tab-item{padding:8px 10px;font-size:12.5px}
  .vws-root{padding:12px;flex-wrap:wrap;gap:12px}
  .vws-track{display:none}
  .vws-item{flex-direction:row;align-items:center;gap:10px;min-width:unset;width:calc(50% - 6px)}
  .vws-label{text-align:left;max-width:unset}
  .page-header{flex-direction:column;gap:10px}
  .page-title{font-size:18px}
  .page-subtitle{font-size:12px}
  .metric-card{padding:14px}
  .metric-value{font-size:24px}
  .table-toolbar{padding:10px 12px}
  .mon-app thead th,.mon-app tbody td{padding:10px 12px}
  .btn{padding:7px 12px;font-size:12.5px}
  .notif-panel{width:100vw}
  .notif-header{padding:12px 14px}
  .notif-item{padding:10px 12px}
}
@media(max-width:390px){
  .mon-topbar{height:48px}
  .mon-main{padding:10px 6px}
  .page-title{font-size:17px}
  .tab-item{padding:7px 8px;font-size:12px}
  .filter-select{font-size:12px;padding:6px 24px 6px 9px}
  .table-info{font-size:11px}
  .mon-app table{min-width:700px}
}
@keyframes toastIn{from{opacity:0;transform:translateX(20px) scale(.95)}to{opacity:1;transform:translateX(0) scale(1)}}
@keyframes fadeSlide{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.fade-in{animation:fadeSlide .2s ease}
`;

export default globalStyles;
