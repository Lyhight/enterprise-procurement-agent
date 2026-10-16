import { useEffect, useState, type ReactNode } from "react";
import { getToken, setToken } from "../api/client";

export type PageKey = "dashboard" | "intake" | "conversations" | "requests" | "runs" | "orders" | "integrations" | "audit";

const nav: Array<{ key: PageKey; label: string; icon: string }> = [
  { key: "dashboard", label: "运营总览", icon: "⌂" },
  { key: "intake", label: "需求录入", icon: "＋" },
  { key: "conversations", label: "需求澄清", icon: "◇" },
  { key: "requests", label: "采购申请", icon: "▤" },
  { key: "runs", label: "Agent 运行", icon: "✦" },
  { key: "orders", label: "订单履约", icon: "□" },
  { key: "integrations", label: "系统集成", icon: "⇄" },
  { key: "audit", label: "审计中心", icon: "◎" }
];

export function Shell({
  active,
  onNavigate,
  children
}: {
  active: PageKey;
  onNavigate: (page: PageKey) => void;
  children: ReactNode;
}) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [token, updateToken] = useState(getToken());
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [active]);

  const navigate = (page: PageKey) => {
    window.location.hash = page;
    onNavigate(page);
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><span>采</span></div>
          <div><strong>采购智枢</strong><small>AGENT CONSOLE</small></div>
        </div>
        <div className="environment-chip"><span /> 企业演示环境</div>
        <nav aria-label="主导航">
          {nav.map((item) => (
            <button
              key={item.key}
              className={active === item.key ? "active" : ""}
              onClick={() => navigate(item.key)}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="system-state"><span className="pulse" /><div><strong>Agent Core</strong><small>服务运行中</small></div></div>
          <button className="settings-button" onClick={() => setSettingsOpen(true)}>⚙ 接口设置</button>
        </div>
      </aside>
      {mobileOpen && <button className="backdrop" aria-label="关闭导航" onClick={() => setMobileOpen(false)} />}
      <main className="main-area">
        <div className="topbar">
          <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="打开导航">☰</button>
          <div className="breadcrumb"><span>东方智能制造集团</span><b>/</b>{nav.find((item) => item.key === active)?.label}</div>
          <div className="topbar-actions"><span className="today">企业采购决策中心</span><div className="avatar">采</div></div>
        </div>
        <div className="content">{children}</div>
      </main>
      {settingsOpen && (
        <div className="modal-layer" role="dialog" aria-modal="true" aria-label="接口设置">
          <button className="modal-backdrop" onClick={() => setSettingsOpen(false)} />
          <section className="settings-panel">
            <div className="panel-heading"><div><p className="eyebrow">CONNECTION</p><h2>接口认证</h2></div><button onClick={() => setSettingsOpen(false)}>×</button></div>
            <p className="muted">后端关闭认证时可留空。生产环境请填写采购角色的 Bearer Token，凭证只保存在当前浏览器。</p>
            <label className="field"><span>Bearer Token</span><input type="password" value={token} onChange={(event) => updateToken(event.target.value)} placeholder="输入 AUTH_TOKENS 中的 token" /></label>
            <div className="settings-note"><strong>API 地址</strong><code>{import.meta.env.VITE_API_BASE_URL || "同源 / Vite 代理"}</code></div>
            <button className="primary-button full" onClick={() => { setToken(token); setSettingsOpen(false); window.location.reload(); }}>保存并重新连接</button>
          </section>
        </div>
      )}
    </div>
  );
}
