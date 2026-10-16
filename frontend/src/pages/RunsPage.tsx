import { useCallback, useEffect, useState } from "react";
import { api, formatError } from "../api/client";
import type { AgentExecution, AgentRunRecord, IntegrityReport, PurchaseOrder, TraceEvent } from "../types/domain";
import { EmptyState, LoadingBlock, PageHeader, StatusBadge, formatDate, formatMoney } from "../components/ui";

export function RunsPage() {
  const [runs, setRuns] = useState<AgentRunRecord[]>([]);
  const [selected, setSelected] = useState<AgentRunRecord | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [integrity, setIntegrity] = useState<{ trace?: IntegrityReport; provenance?: IntegrityReport }>({});
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [awardSupplier, setAwardSupplier] = useState("");
  const [awarding, setAwarding] = useState(false);
  const [executionId, setExecutionId] = useState("");
  const [execution, setExecution] = useState<AgentExecution | null>(null);
  const [executionBusy, setExecutionBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const [items, orderItems] = await Promise.all([api.runs(50), api.orders()]); setRuns(items); setOrders(orderItems); setSelected((current) => current || items[0] || null); }
    catch (reason) { setError(formatError(reason)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setAwardSupplier(selected?.result.recommendations[0]?.supplier_id || ""); }, [selected]);

  async function inspect(run: AgentRunRecord) {
    setSelected(run); setTrace([]); setIntegrity({}); setDetailLoading(true); setError("");
    const executionId = run.result.run_id;
    if (!executionId) { setDetailLoading(false); return; }
    try {
      const [events, traceReport, provenance] = await Promise.all([api.trace(executionId), api.traceVerify(executionId), api.provenanceVerify(run.run_id)]);
      setTrace(events); setIntegrity({ trace: traceReport, provenance });
    } catch (reason) { setError(formatError(reason)); }
    finally { setDetailLoading(false); }
  }

  async function decide(decision: "APPROVED" | "REJECTED") {
    if (!selected) return;
    const approver = window.prompt("请输入审批人员工号", "E001");
    if (!approver) return;
    const comment = window.prompt("请输入审批意见", decision === "APPROVED" ? "同意采购建议" : "退回补充材料") || undefined;
    try { const updated = await api.approveRun(selected.run_id, { decision, approver_id: approver, comment }); setSelected(updated); await load(); }
    catch (reason) { setError(formatError(reason)); }
  }

  async function award() {
    if (!selected || !awardSupplier) return;
    const actor = window.prompt("请输入定标人员工号", "E001");
    if (!actor) return;
    const reason = window.prompt("请输入定标理由", "综合评分、报价与交付能力最优") || "依据 Agent 推荐定标";
    setAwarding(true); setError("");
    try {
      await api.createOrder({ run_id: selected.run_id, supplier_id: awardSupplier, decided_by: actor, reason, expected_delivery_date: selected.result.request.required_date });
      setOrders(await api.orders());
    } catch (reasonValue) { setError(formatError(reasonValue)); }
    finally { setAwarding(false); }
  }

  async function lookupExecution(id = executionId) {
    if (!id.trim()) return;
    setExecutionBusy(true); setError("");
    try { const current = await api.execution(id.trim()); setExecution(current); setExecutionId(current.execution_id); }
    catch (reason) { setExecution(null); setError(formatError(reason)); }
    finally { setExecutionBusy(false); }
  }

  async function cancelExecution() {
    if (!execution) return;
    const reason = window.prompt("请输入取消原因", "人工终止异常执行");
    if (!reason) return;
    setExecutionBusy(true); setError("");
    try { await api.cancelExecution(execution.execution_id, reason); await lookupExecution(execution.execution_id); }
    catch (value) { setError(formatError(value)); setExecutionBusy(false); }
  }

  async function retryExecution() {
    if (!execution) return;
    setExecutionBusy(true); setError("");
    try { const recovered = await api.retryExecution(execution.execution_id); await load(); setSelected(recovered); setExecution(await api.execution(execution.execution_id)); }
    catch (value) { setError(formatError(value)); }
    finally { setExecutionBusy(false); }
  }

  return <>
    <PageHeader eyebrow="AGENT OPERATIONS" title="Agent 运行中心" description="查看决策结果、工具时间线、人工审批和防篡改来源证明。" actions={<button className="secondary-button" onClick={() => void load()}>↻ 刷新</button>} />
    {error && <div className="alert error"><span>{error}</span></div>}
    <article className="execution-console panel"><div><p className="eyebrow">EXECUTION CONTROL</p><h2>执行控制与故障恢复</h2><span>输入稳定 execution_id，可检查运行态、请求取消或从检查点恢复。</span></div><div className="execution-search"><input value={executionId} onChange={(e) => setExecutionId(e.target.value)} placeholder="例如 RUN-ABC123" /><button className="secondary-button" disabled={executionBusy || !executionId.trim()} onClick={() => void lookupExecution()}>{executionBusy ? "读取中…" : "查询执行"}</button></div>{execution && <div className="execution-result"><div><StatusBadge value={execution.status} /><strong className="mono">{execution.execution_id}</strong><span>当前步骤 {execution.current_step_id || "—"} · {execution.iterations} 次迭代</span></div>{execution.last_error && <p>{execution.last_error}</p>}<div className="inline-actions">{execution.status === "RUNNING" && <button className="reject-button" disabled={executionBusy} onClick={() => void cancelExecution()}>请求取消</button>}{["FAILED", "CANCELLED"].includes(execution.status) && <button className="primary-button" disabled={executionBusy} onClick={() => void retryExecution()}>从检查点重试</button>}</div></div>}</article>
    <section className="runs-layout">
      <article className="panel runs-table">
        <div className="panel-title"><div><p className="eyebrow">RUN HISTORY</p><h2>运行记录</h2></div><span>{runs.length} 条</span></div>
        {loading ? <LoadingBlock /> : runs.length ? <div className="table-wrap"><table><thead><tr><th>运行编号</th><th>采购内容</th><th>审批</th><th>状态</th><th>时间</th></tr></thead><tbody>{runs.map((run) => <tr className={selected?.run_id === run.run_id ? "selected-row" : ""} key={run.run_id} onClick={() => void inspect(run)}><td><strong className="mono">{run.run_id}</strong><small>{run.request_id}</small></td><td><strong>{run.result.request.product}</strong><small>{formatMoney(run.result.request.budget)}</small></td><td>{run.approval_level}</td><td><StatusBadge value={run.status} /></td><td>{formatDate(run.created_at, true)}</td></tr>)}</tbody></table></div> : <EmptyState title="暂无运行记录" detail="从采购申请页面启动 Agent 分析。" />}
      </article>
      <article className="panel run-inspector">
        {!selected ? <EmptyState title="选择一条运行" detail="查看 Agent 的完整决策与审计证据。" /> : <>
          <div className="inspector-head"><div><p className="eyebrow">DECISION INSPECTOR</p><h2>{selected.result.request.product}</h2><p className="mono">{selected.run_id}</p></div><StatusBadge value={selected.status} /></div>
          <div className="decision-stats"><div><small>审批等级</small><strong>{selected.approval_level}</strong></div><div><small>推荐供应商</small><strong>{selected.result.recommendations.length}</strong></div><div><small>工具迭代</small><strong>{selected.result.agent_iterations}</strong></div></div>
          <div className="next-action"><span>下一步</span><strong>{selected.result.next_action}</strong></div>
          {selected.status === "AWAITING_APPROVAL" && <div className="approval-actions"><button className="approve-button" onClick={() => void decide("APPROVED")}>✓ 批准建议</button><button className="reject-button" onClick={() => void decide("REJECTED")}>× 驳回申请</button></div>}
          {selected.status === "COMPLETED" && selected.result.recommendations.length > 0 && (
            orders.some((order) => order.run_id === selected.run_id)
              ? <div className="order-created"><span>✓</span><div><strong>采购订单已创建</strong><p>{orders.find((order) => order.run_id === selected.run_id)?.po_id}</p></div><a href="#orders">查看订单 →</a></div>
              : <div className="award-box"><div><strong>供应商定标</strong><p>从 Agent 推荐清单选择供应商并创建采购订单。</p></div><select value={awardSupplier} onChange={(event) => setAwardSupplier(event.target.value)}>{selected.result.recommendations.filter((item) => item.quoted_total !== null).map((item) => <option value={item.supplier_id} key={item.supplier_id}>{item.supplier_name} · {formatMoney(item.quoted_total)}</option>)}</select><button className="primary-button" disabled={awarding || !awardSupplier} onClick={() => void award()}>{awarding ? "正在定标…" : "确认定标并创建订单"}</button></div>
          )}
          <div className="verification-row"><Verification label="Trace 哈希链" value={integrity.trace?.valid} /><Verification label="决策来源证明" value={integrity.provenance?.valid} /><Verification label="最终安全闸门" value={selected.result.guardrail_report?.valid} /></div>
          <div className="section-heading"><h3>持久化 Trace</h3><button className="text-button" onClick={() => void inspect(selected)}>重新验证</button></div>
          {detailLoading ? <LoadingBlock label="正在验证证据链" /> : trace.length ? <div className="trace-stream">{trace.slice().reverse().slice(0, 30).map((event) => <div key={event.event_id}><span className={`trace-dot ${event.status.toLowerCase()}`} /><div><strong>{event.event_type}</strong><p>{event.step_id || "run"} · {event.duration_ms === null ? "—" : `${event.duration_ms} ms`}</p></div><time>{formatDate(event.created_at, true)}</time></div>)}</div> : <button className="secondary-button full" onClick={() => void inspect(selected)}>加载 Trace 与完整性验证</button>}
        </>}
      </article>
    </section>
  </>;
}

function Verification({ label, value }: { label: string; value: boolean | undefined }) {
  return <div><span className={value === true ? "verify-ok" : value === false ? "verify-fail" : "verify-idle"}>{value === true ? "✓" : value === false ? "×" : "·"}</span><div><strong>{label}</strong><small>{value === true ? "验证通过" : value === false ? "验证失败" : "待验证"}</small></div></div>;
}
