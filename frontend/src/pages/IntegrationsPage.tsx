import { useCallback, useEffect, useMemo, useState } from "react";
import { api, formatError } from "../api/client";
import type { AgentRunRecord, IntegrationJob, IntegrationRecord } from "../types/domain";
import { EmptyState, LoadingBlock, PageHeader, StatusBadge, formatDate } from "../components/ui";

export function IntegrationsPage() {
  const [jobs, setJobs] = useState<IntegrationJob[]>([]);
  const [records, setRecords] = useState<IntegrationRecord[]>([]);
  const [runs, setRuns] = useState<AgentRunRecord[]>([]);
  const [runId, setRunId] = useState("");
  const [target, setTarget] = useState<"OA" | "ERP">("OA");
  const [mode, setMode] = useState<"queue" | "direct">("queue");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [nextJobs, nextRecords, nextRuns] = await Promise.all([api.integrationJobs(), api.integrationRecords(), api.runs(100)]);
      setJobs(nextJobs); setRecords(nextRecords); setRuns(nextRuns);
      setRunId((current) => current || nextRuns.find((run) => run.status === "COMPLETED")?.run_id || nextRuns[0]?.run_id || "");
    } catch (reason) { setError(formatError(reason)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const counts = useMemo(() => ({ success: jobs.filter((j) => j.status === "SUCCEEDED").length, pending: jobs.filter((j) => ["PENDING", "RUNNING", "RETRY"].includes(j.status)).length, failed: jobs.filter((j) => j.status === "FAILED").length }), [jobs]);
  async function submit() {
    if (!runId) return;
    setBusy(true); setError("");
    try { if (mode === "queue") await api.enqueueIntegration(runId, target); else await api.syncRun(runId, target); await load(); }
    catch (reason) { setError(formatError(reason)); }
    finally { setBusy(false); }
  }
  return <>
    <PageHeader eyebrow="ENTERPRISE CONNECTORS" title="OA / ERP 集成中心" description="管理审批推送与采购数据同步，查看异步任务重试和外部系统回执。" actions={<button className="secondary-button" onClick={() => void load()}>↻ 刷新状态</button>} />
    {error && <div className="alert error"><strong>集成操作失败</strong><span>{error}</span></div>}
    <section className="integration-kpis"><div><small>任务总数</small><strong>{jobs.length}</strong></div><div><small>已成功</small><strong>{counts.success}</strong></div><div><small>处理中</small><strong>{counts.pending}</strong></div><div><small>失败</small><strong>{counts.failed}</strong></div></section>
    <section className="integration-layout">
      <article className="panel integration-launch"><div className="panel-title"><div><p className="eyebrow">DISPATCH</p><h2>发起系统同步</h2></div></div>
        <label className="field"><span>Agent 运行</span><select value={runId} onChange={(e) => setRunId(e.target.value)}>{runs.map((run) => <option key={run.run_id} value={run.run_id}>{run.run_id} · {run.result.request.product}</option>)}</select></label>
        <div className="target-selector"><button className={target === "OA" ? "active" : ""} onClick={() => setTarget("OA")}><b>OA</b><span>发送审批单</span></button><button className={target === "ERP" ? "active" : ""} onClick={() => setTarget("ERP")}><b>ERP</b><span>同步采购数据</span></button></div>
        <label className="field"><span>执行方式</span><select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}><option value="queue">异步队列（推荐，可重试）</option><option value="direct">立即同步</option></select></label>
        <button className="primary-button full" disabled={busy || !runId} onClick={() => void submit()}>{busy ? "正在提交…" : `提交至 ${target}`}</button>
      </article>
      <article className="panel integration-history"><div className="panel-title"><div><p className="eyebrow">JOB QUEUE</p><h2>异步任务</h2></div><span>{jobs.length} 条</span></div>
        {loading ? <LoadingBlock /> : jobs.length ? <div className="job-list">{jobs.map((job) => <div key={job.job_id}><span className="system-mark">{job.target}</span><div><strong>{job.run_id}</strong><p className="mono">{job.job_id}</p>{job.last_error && <small>{job.last_error}</small>}</div><div className="job-state"><StatusBadge value={job.status} /><time>{job.attempts}/{job.max_attempts} 次 · {formatDate(job.updated_at, true)}</time></div></div>)}</div> : <EmptyState title="暂无集成任务" detail="选择一条 Agent 运行并推送至 OA 或 ERP。" />}
      </article>
    </section>
    <article className="panel integration-records"><div className="panel-title"><div><p className="eyebrow">EXTERNAL RECEIPTS</p><h2>外部系统回执</h2></div><span>{records.length} 条</span></div>
      {records.length ? <div className="table-wrap"><table><thead><tr><th>系统</th><th>动作</th><th>资源</th><th>外部编号</th><th>状态</th><th>时间</th></tr></thead><tbody>{records.map((record) => <tr key={record.integration_id}><td><strong>{record.system}</strong></td><td>{record.action}</td><td><strong className="mono">{record.resource_id}</strong><small>{record.resource_type}</small></td><td className="mono">{record.external_reference}</td><td><StatusBadge value={record.status} /></td><td>{formatDate(record.created_at, true)}</td></tr>)}</tbody></table></div> : <EmptyState title="尚无外部回执" detail="同步成功后，外部系统引用号会记录在这里。" />}
    </article>
  </>;
}
