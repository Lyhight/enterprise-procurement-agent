import { useCallback, useEffect, useState } from "react";
import { api, formatError } from "../api/client";
import type {
  AgentRunRecord,
  AiRuntimeStatus,
  DashboardSummary,
  KnowledgeStatus,
  PurchaseOrder,
  PurchaseRequest
} from "../types/domain";
import {
  EmptyState,
  LoadingBlock,
  MetricCard,
  PageHeader,
  StatusBadge,
  formatDate,
  formatMoney
} from "../components/ui";

export function DashboardPage() {
  const [data, setData] = useState<{
    summary: DashboardSummary;
    runs: AgentRunRecord[];
    requests: PurchaseRequest[];
    orders: PurchaseOrder[];
    ai: AiRuntimeStatus;
    knowledge: KnowledgeStatus;
  } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [summary, runs, requests, orders, ai, knowledge] = await Promise.all([
        api.dashboard(), api.runs(8), api.requests(), api.orders(), api.aiStatus(), api.knowledgeStatus()
      ]);
      setData({ summary, runs, requests, orders, ai, knowledge });
    } catch (reason) {
      setError(formatError(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <>
      <PageHeader
        eyebrow="OPERATIONS OVERVIEW"
        title="采购运营总览"
        description="从需求进入到订单履约，实时掌握 Agent 决策、审批与业务执行状态。"
        actions={<button className="secondary-button" onClick={() => void load()}>↻ 刷新数据</button>}
      />
      {error && <div className="alert error"><strong>连接失败</strong><span>{error}</span><button onClick={() => void load()}>重试</button></div>}
      {loading && !data ? <LoadingBlock /> : data && (
        <>
          <section className="metrics-grid">
            <MetricCard label="采购申请" value={data.summary.total_requests} detail="进入需求池的申请总数" icon="▤" />
            <MetricCard label="Agent 决策" value={data.summary.total_agent_runs} detail={`${data.summary.pending_approvals} 项等待人工审批`} icon="✦" tone="blue" />
            <MetricCard label="采购订单" value={data.summary.total_orders} detail={`${Object.keys(data.summary.orders_by_status).length} 种履约状态`} icon="□" tone="amber" />
            <MetricCard label="已定标金额" value={formatMoney(data.summary.approved_order_value)} detail="已创建订单的累计金额" icon="¥" tone="ink" />
          </section>

          <section className="dashboard-grid">
            <article className="panel span-2">
              <div className="panel-title"><div><p className="eyebrow">LATEST REQUESTS</p><h2>近期采购需求</h2></div><a href="#requests">查看全部 →</a></div>
              {data.requests.length ? (
                <div className="table-wrap"><table><thead><tr><th>申请编号</th><th>采购内容</th><th>部门</th><th>预算</th><th>优先级</th><th>交付日期</th></tr></thead><tbody>
                  {data.requests.slice(0, 6).map((request) => <tr key={request.request_id}><td><strong className="mono">{request.request_id}</strong></td><td><strong>{request.product}</strong><small>{request.category} · {request.quantity} 件</small></td><td>{request.department}</td><td>{formatMoney(request.budget)}</td><td><StatusBadge value={request.priority} /></td><td>{request.required_date}</td></tr>)}
                </tbody></table></div>
              ) : <EmptyState title="暂无采购申请" detail="从需求录入页面提交第一条采购需求。" />}
            </article>

            <article className="panel agent-health">
              <div className="panel-title"><div><p className="eyebrow">AGENT HEALTH</p><h2>智能体状态</h2></div><span className="live-chip"><i /> LIVE</span></div>
              <div className="health-orbit"><div className="orbit-ring"><div className="orbit-core">AI</div><span className="node node-a" /><span className="node node-b" /><span className="node node-c" /></div></div>
              <dl className="health-list">
                <div><dt>规划引擎</dt><dd>{data.ai.provider}</dd></div>
                <div><dt>运行模型</dt><dd>{data.ai.model || "本地确定性"}</dd></div>
                <div><dt>知识库</dt><dd>{data.knowledge.documents} 文档 / {data.knowledge.chunks} 分块</dd></div>
                <div><dt>检索模式</dt><dd>{data.knowledge.retrieval_mode}</dd></div>
              </dl>
            </article>

            <article className="panel span-2">
              <div className="panel-title"><div><p className="eyebrow">DECISION STREAM</p><h2>Agent 决策动态</h2></div><a href="#runs">进入运行中心 →</a></div>
              <div className="activity-list">
                {data.runs.slice(0, 5).map((run) => (
                  <a href="#runs" className="activity-item" key={run.run_id}>
                    <span className="activity-symbol">{run.status === "AWAITING_APPROVAL" ? "!" : "✓"}</span>
                    <div><strong>{run.result.request.product}</strong><p>{run.request_id} · {run.result.recommendations[0]?.supplier_name || "等待人工寻源"}</p></div>
                    <div className="activity-meta"><StatusBadge value={run.status} /><time>{formatDate(run.created_at, true)}</time></div>
                  </a>
                ))}
                {!data.runs.length && <EmptyState title="暂无 Agent 运行" detail="选择采购申请并启动一次智能分析。" />}
              </div>
            </article>

            <article className="panel">
              <div className="panel-title"><div><p className="eyebrow">ORDER FLOW</p><h2>订单履约</h2></div><a href="#orders">全部订单 →</a></div>
              <div className="order-summary">
                {Object.entries(data.summary.orders_by_status).map(([status, count]) => <div key={status}><span><StatusBadge value={status} /></span><strong>{count}</strong></div>)}
                {!Object.keys(data.summary.orders_by_status).length && <EmptyState title="暂无订单" detail="完成审批定标后将在这里展示。" />}
              </div>
            </article>
          </section>
        </>
      )}
    </>
  );
}
