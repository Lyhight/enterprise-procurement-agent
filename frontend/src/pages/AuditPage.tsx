import { useCallback, useEffect, useMemo, useState } from "react";
import { api, formatError } from "../api/client";
import type { AuditEvent } from "../types/domain";
import { EmptyState, LoadingBlock, PageHeader, formatDate } from "../components/ui";

export function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("ALL");
  const load = useCallback(async () => { setLoading(true); setError(""); try { setEvents(await api.audit(100)); } catch (reason) { setError(formatError(reason)); } finally { setLoading(false); } }, []);
  useEffect(() => { void load(); }, [load]);
  const types = useMemo(() => ["ALL", ...new Set(events.map((event) => event.resource_type))], [events]);
  const filtered = filter === "ALL" ? events : events.filter((event) => event.resource_type === filter);
  return <>
    <PageHeader eyebrow="AUDIT & GOVERNANCE" title="审计与治理中心" description="查询业务操作记录，并从 Agent 运行中心验证不可篡改的执行与决策证据。" actions={<button className="secondary-button" onClick={() => void load()}>↻ 刷新</button>} />
    {error && <div className="alert error"><span>{error}</span></div>}
    <section className="audit-summary"><div><span>◎</span><div><small>审计事件</small><strong>{events.length}</strong></div></div><div><span>♢</span><div><small>资源类型</small><strong>{Math.max(0, types.length - 1)}</strong></div></div><div><span>✓</span><div><small>Agent 证据链</small><strong>可验证</strong></div></div></section>
    <article className="panel audit-panel">
      <div className="panel-title"><div><p className="eyebrow">BUSINESS AUDIT LOG</p><h2>业务审计日志</h2></div><select value={filter} onChange={(event) => setFilter(event.target.value)}>{types.map((type) => <option value={type} key={type}>{type === "ALL" ? "全部资源" : type}</option>)}</select></div>
      {loading ? <LoadingBlock /> : filtered.length ? <div className="audit-stream">{filtered.map((event) => <div className="audit-event" key={event.event_id}><span className="audit-symbol">{event.action.includes("APPROV") ? "✓" : event.action.includes("CREAT") ? "+" : "·"}</span><div className="audit-copy"><div><strong>{event.action}</strong><span className="mono">{event.event_id}</span></div><p><b>{event.actor_id}</b> 操作 {event.resource_type} / {event.resource_id}</p></div><time>{formatDate(event.created_at, true)}</time></div>)}</div> : <EmptyState title="暂无审计事件" detail="业务操作发生后会自动写入不可变审计记录。" />}
    </article>
  </>;
}
