import { useCallback, useEffect, useMemo, useState } from "react";
import { api, formatError } from "../api/client";
import type { AgentRunRecord, PurchaseRequest, Quotation, RfqRecord } from "../types/domain";
import { EmptyState, LoadingBlock, PageHeader, StatusBadge, formatMoney } from "../components/ui";

export function RequestsPage() {
  const [requests, setRequests] = useState<PurchaseRequest[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [run, setRun] = useState<AgentRunRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [rfqs, setRfqs] = useState<RfqRecord[]>([]);
  const [quotations, setQuotations] = useState<Quotation[]>([]);
  const [sourcingBusy, setSourcingBusy] = useState(false);
  const [quoteOpen, setQuoteOpen] = useState(false);
  const [quoteRfq, setQuoteRfq] = useState("");
  const [quote, setQuote] = useState({ unit_price: "", currency: "CNY", delivery_days: "15", warranty_months: "12", valid_until: "" });

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const items = await api.requests(); setRequests(items); setSelected((current) => current || items[0]?.request_id || null); }
    catch (reason) { setError(formatError(reason)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => requests.filter((item) => [item.request_id, item.product, item.department, item.category].some((value) => value.toLowerCase().includes(query.toLowerCase()))), [requests, query]);
  const request = requests.find((item) => item.request_id === selected) || null;

  useEffect(() => {
    if (!selected) return;
    Promise.all([api.rfqs(selected), api.quotations(selected)])
      .then(([nextRfqs, nextQuotations]) => { setRfqs(nextRfqs); setQuotations(nextQuotations); setQuoteRfq((current) => current || nextRfqs[0]?.rfq_id || ""); })
      .catch(() => { setRfqs([]); setQuotations([]); });
  }, [selected]);

  async function analyze() {
    if (!request) return;
    setRunning(true); setError(""); setRun(null);
    try { setRun(await api.createRun(request.request_id)); }
    catch (reason) { setError(formatError(reason)); }
    finally { setRunning(false); }
  }

  async function createRfqs() {
    if (!request) return;
    setSourcingBusy(true); setError("");
    try { setRfqs(await api.createRfqs(request.request_id)); setQuotations(await api.quotations(request.request_id)); }
    catch (reason) { setError(formatError(reason)); }
    finally { setSourcingBusy(false); }
  }

  async function submitQuote(event: React.FormEvent) {
    event.preventDefault();
    if (!request || !quoteRfq) return;
    setSourcingBusy(true); setError("");
    try {
      await api.submitQuotation(quoteRfq, {
        unit_price: Number(quote.unit_price), currency: quote.currency,
        delivery_days: Number(quote.delivery_days), warranty_months: Number(quote.warranty_months),
        valid_until: quote.valid_until
      });
      setQuotations(await api.quotations(request.request_id));
      setQuoteOpen(false);
      setQuote({ unit_price: "", currency: "CNY", delivery_days: "15", warranty_months: "12", valid_until: "" });
    } catch (reason) { setError(formatError(reason)); }
    finally { setSourcingBusy(false); }
  }

  return (
    <>
      <PageHeader eyebrow="PURCHASE REQUESTS" title="采购申请工作台" description="浏览需求池并启动完整的 Plan-and-Execute 采购分析。" actions={<a className="primary-button link-button" href="#intake">＋ 新建需求</a>} />
      {error && <div className="alert error"><strong>操作失败</strong><span>{error}</span></div>}
      <section className="master-detail">
        <article className="panel request-list-panel">
          <div className="list-toolbar"><div className="search-box">⌕<input placeholder="搜索编号、产品或部门" value={query} onChange={(event) => setQuery(event.target.value)} /></div><span>{filtered.length} 条</span></div>
          {loading ? <LoadingBlock /> : filtered.length ? <div className="request-cards">{filtered.map((item) => (
            <button key={item.request_id} className={`request-card ${selected === item.request_id ? "selected" : ""}`} onClick={() => { setSelected(item.request_id); setRun(null); }}>
              <div><strong>{item.product}</strong><span className="mono">{item.request_id}</span></div><p>{item.department} · {item.category} · {item.quantity} 件</p><footer><StatusBadge value={item.priority} /><b>{formatMoney(item.budget)}</b></footer>
            </button>
          ))}</div> : <EmptyState title="没有匹配的申请" detail="调整搜索条件或创建新的采购需求。" />}
        </article>

        <article className="panel request-detail-panel">
          {!request ? <EmptyState title="请选择采购申请" detail="从左侧需求池选择一条申请查看详情。" /> : (
            <>
              <div className="detail-hero"><div><p className="eyebrow">{request.request_id}</p><h2>{request.product}</h2><p>{request.category} · {request.department}</p></div><StatusBadge value={request.status} /></div>
              <dl className="detail-grid"><div><dt>申请人</dt><dd>{request.requester_id}</dd></div><div><dt>采购数量</dt><dd>{request.quantity} 件</dd></div><div><dt>预算金额</dt><dd>{formatMoney(request.budget)}</dd></div><div><dt>期望交付</dt><dd>{request.required_date}</dd></div></dl>
              <div className="sourcing-strip"><div><strong>询价准备</strong><p>{rfqs.length ? `已创建 ${rfqs.length} 张询价单，收到 ${quotations.length} 份报价` : "为合格供应商批量创建询价单并等待报价"}</p></div><div className="inline-actions"><button className="secondary-button" disabled={sourcingBusy} onClick={() => void createRfqs()}>{sourcingBusy ? "正在创建…" : rfqs.length ? "刷新询价" : "创建询价单"}</button>{rfqs.length > 0 && <button className="primary-button" onClick={() => setQuoteOpen((value) => !value)}>＋ 录入报价</button>}</div></div>
              {quoteOpen && <form className="quotation-form" onSubmit={submitQuote}><div className="panel-title"><div><p className="eyebrow">SUPPLIER RESPONSE</p><h3>供应商报价录入</h3></div><button type="button" className="text-button" onClick={() => setQuoteOpen(false)}>关闭</button></div><div className="quotation-form-grid"><label className="field"><span>询价单 / 供应商</span><select value={quoteRfq} onChange={(e) => setQuoteRfq(e.target.value)} required>{rfqs.map((rfq) => <option key={rfq.rfq_id} value={rfq.rfq_id}>{rfq.supplier_name} · {rfq.rfq_id}</option>)}</select></label><label className="field"><span>单价</span><input type="number" min="0.01" step="0.01" value={quote.unit_price} onChange={(e) => setQuote({ ...quote, unit_price: e.target.value })} required /></label><label className="field"><span>币种</span><select value={quote.currency} onChange={(e) => setQuote({ ...quote, currency: e.target.value })}><option>CNY</option><option>USD</option><option>EUR</option></select></label><label className="field"><span>交付天数</span><input type="number" min="1" value={quote.delivery_days} onChange={(e) => setQuote({ ...quote, delivery_days: e.target.value })} required /></label><label className="field"><span>质保月数</span><input type="number" min="0" value={quote.warranty_months} onChange={(e) => setQuote({ ...quote, warranty_months: e.target.value })} required /></label><label className="field"><span>报价有效期</span><input type="date" value={quote.valid_until} onChange={(e) => setQuote({ ...quote, valid_until: e.target.value })} required /></label></div><button className="primary-button" disabled={sourcingBusy}>{sourcingBusy ? "正在提交…" : "确认提交报价"}</button></form>}
              {!!quotations.length && <div className="quotation-strip">{quotations.slice(0, 4).map((quote) => <div key={quote.quotation_id}><span>{quote.supplier_id}</span><strong>{formatMoney(Number(quote.unit_price) * request.quantity, quote.currency)}</strong><small>{quote.delivery_days} 天交付 · {quote.warranty_months} 月质保</small></div>)}</div>}
              {!run && <div className="agent-launch"><div className="agent-emblem">✦</div><div><strong>启动采购决策 Agent</strong><p>自动执行需求校验、供应商筛选、报价比对、制度检索与决策安全校验。</p></div><button className="primary-button" onClick={() => void analyze()} disabled={running}>{running ? "Agent 执行中…" : "开始分析"}</button></div>}
              {running && <div className="agent-running"><div className="runner-line"><span /><span /><span /><span /></div><strong>Plan-and-Execute 正在运行</strong><p>执行结果会在所有安全校验通过后发布。</p></div>}
              {run && <AnalysisView run={run} />}
            </>
          )}
        </article>
      </section>
    </>
  );
}

function AnalysisView({ run }: { run: AgentRunRecord }) {
  const result = run.result;
  return <div className="analysis-view">
    <div className="decision-banner"><div><span>✦</span><div><p>AGENT DECISION</p><strong>{result.next_action}</strong></div></div><div><small>审批等级</small><b>{result.approval_level}</b></div><StatusBadge value={run.status} /></div>
    {!!result.warnings.length && <div className="warning-list">{result.warnings.map((warning) => <p key={warning}>! {warning}</p>)}</div>}
    <div className="section-heading"><h3>供应商推荐</h3><span>{result.recommendations.length} 家候选</span></div>
    <div className="recommendation-list">{result.recommendations.map((item, index) => <div className="recommendation" key={item.supplier_id}><span className="rank">{index + 1}</span><div><strong>{item.supplier_name}</strong><p>{item.reasons.join(" · ")}</p></div><div className="score"><b>{item.score}</b><small>综合分</small></div><strong>{formatMoney(item.quoted_total)}</strong></div>)}{!result.recommendations.length && <EmptyState title="未生成自动推荐" detail="当前申请需要人工寻源或补充信息。" />}</div>
    <div className="section-heading"><h3>执行轨迹</h3><span>{result.agent_iterations} 次工具迭代</span></div>
    <div className="step-timeline">{result.trace.map((step, index) => <div key={`${step.step}-${index}`}><span className={step.status === "waiting" ? "waiting" : "done"}>{step.status === "waiting" ? "!" : "✓"}</span><div><strong>{step.step}</strong><p>{step.summary}</p></div></div>)}</div>
    <div className="evidence-grid"><div><strong>安全闸门</strong><StatusBadge value={result.guardrail_report?.valid ? "VALID" : "UNKNOWN"} /></div><div><strong>Planner</strong><span>{result.planner_provider}</span></div><div><strong>制度证据</strong><span>{result.policy_evidence.length} 条</span></div><div><strong>降级次数</strong><span>{result.planner_fallback_count}</span></div></div>
    <a href="#runs" className="secondary-button link-button">查看审计详情 →</a>
  </div>;
}
