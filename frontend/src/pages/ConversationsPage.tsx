import { useState, type FormEvent } from "react";
import { api, formatError } from "../api/client";
import type { ConversationState, PurchaseRequest } from "../types/domain";
import { EmptyState, PageHeader, StatusBadge, formatDate, formatMoney } from "../components/ui";

export function ConversationsPage() {
  const [state, setState] = useState<ConversationState | null>(null);
  const [requester, setRequester] = useState("E002");
  const [department, setDepartment] = useState("研发部");
  const [message, setMessage] = useState("");
  const [requiredDate, setRequiredDate] = useState("");
  const [priority, setPriority] = useState<"LOW" | "MEDIUM" | "HIGH">("MEDIUM");
  const [created, setCreated] = useState<PurchaseRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function start(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setCreated(null);
    try { setState(await api.startConversation({ requester_id: requester, department })); }
    catch (reason) { setError(formatError(reason)); }
    finally { setBusy(false); }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!state || !message.trim()) return;
    setBusy(true); setError("");
    try {
      setState(await api.sendConversationMessage(state.session_id, {
        text: message.trim(),
        ...(requiredDate ? { required_date: requiredDate } : {}),
        priority
      }));
      setMessage("");
    } catch (reason) { setError(formatError(reason)); }
    finally { setBusy(false); }
  }

  async function submit() {
    if (!state) return;
    setBusy(true); setError("");
    try { const next = await api.submitConversation(state.session_id); setCreated(next); setState(await api.getConversation(state.session_id)); }
    catch (reason) { setError(formatError(reason)); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeader eyebrow="REQUIREMENT DIALOGUE" title="多轮需求澄清" description="通过连续对话补齐产品、数量、预算和交付时间，再生成正式采购申请。" actions={state ? <button className="secondary-button" onClick={() => { setState(null); setCreated(null); }}>新建会话</button> : undefined} />
    {error && <div className="alert error"><strong>操作失败</strong><span>{error}</span></div>}
    <section className="conversation-layout">
      <article className="panel conversation-panel">
        {!state ? <form className="conversation-start" onSubmit={start}>
          <div className="dialogue-hero"><span>◇</span><h2>开始采购需求访谈</h2><p>Agent 会识别缺失字段并逐步追问，避免不完整需求进入审批链。</p></div>
          <div className="form-grid"><label className="field"><span>申请人员工号</span><input value={requester} onChange={(e) => setRequester(e.target.value)} required /></label><label className="field"><span>所属部门</span><input value={department} onChange={(e) => setDepartment(e.target.value)} required /></label></div>
          <button className="primary-button full" disabled={busy}>{busy ? "正在创建…" : "开始澄清会话"}</button>
        </form> : <>
          <div className="conversation-head"><div><p className="eyebrow">SESSION</p><strong className="mono">{state.session_id}</strong></div><StatusBadge value={state.status} /></div>
          <div className="message-stream">{state.messages.map((item) => <div className={`message ${item.role}`} key={item.message_id}><span>{item.role === "assistant" ? "A" : "我"}</span><div><p>{item.content}</p><time>{formatDate(item.created_at, true)}</time></div></div>)}</div>
          {state.status !== "SUBMITTED" && <form className="message-composer" onSubmit={send}><textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="例如：需要 20 台 GPU 服务器，预算 120 万元……" rows={3} required /><div><input type="date" value={requiredDate} onChange={(e) => setRequiredDate(e.target.value)} /><select value={priority} onChange={(e) => setPriority(e.target.value as typeof priority)}><option value="LOW">低优先级</option><option value="MEDIUM">普通</option><option value="HIGH">紧急</option></select><button className="primary-button" disabled={busy}>{busy ? "处理中…" : "发送"}</button></div></form>}
        </>}
      </article>
      <article className="panel draft-panel">
        <div className="panel-title"><div><p className="eyebrow">LIVE DRAFT</p><h2>结构化需求草稿</h2></div>{state && <StatusBadge value={state.draft.ready_to_submit ? "READY" : "INCOMPLETE"} />}</div>
        {!state ? <EmptyState title="等待会话开始" detail="Agent 提取出的采购字段会实时显示在这里。" /> : <>
          <dl className="draft-fields"><Draft label="产品" value={state.draft.product} /><Draft label="品类" value={state.draft.category} /><Draft label="数量" value={state.draft.quantity ? `${state.draft.quantity} 件` : null} /><Draft label="预算" value={state.draft.budget ? formatMoney(state.draft.budget) : null} /><Draft label="交付日期" value={state.draft.required_date} /><Draft label="优先级" value={state.draft.priority} /></dl>
          {state.draft.missing_fields.length > 0 && <div className="missing-fields"><strong>仍需补充</strong>{state.draft.missing_fields.map((field) => <span key={field}>{field}</span>)}</div>}
          <button className="primary-button full" disabled={!state.draft.ready_to_submit || busy || state.status === "SUBMITTED"} onClick={() => void submit()}>{state.status === "SUBMITTED" ? "已生成采购申请" : "确认并生成采购申请"}</button>
          {created && <div className="success-card"><span>✓</span><div><strong>采购申请已创建</strong><p>{created.request_id} · {created.product}</p></div><a href="#requests">查看 →</a></div>}
        </>}
      </article>
    </section>
  </>;
}

function Draft({ label, value }: { label: string; value: string | number | null }) {
  return <div><dt>{label}</dt><dd className={value === null ? "draft-empty" : ""}>{value ?? "待补充"}</dd></div>;
}
