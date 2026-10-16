import { useState, type FormEvent } from "react";
import { api, formatError } from "../api/client";
import type { IntakePayload, ParsedPurchaseDraft, PurchaseRequest } from "../types/domain";
import { PageHeader, StatusBadge, formatMoney } from "../components/ui";

const initial: IntakePayload = {
  text: "采购 20 台 GPU 服务器，预算 120 万元，用于研发部 AI 训练集群",
  requester_id: "E002",
  department: "研发部",
  priority: "HIGH",
  required_date: "2026-12-20"
};

export function IntakePage() {
  const [form, setForm] = useState<IntakePayload>(initial);
  const [draft, setDraft] = useState<ParsedPurchaseDraft | null>(null);
  const [created, setCreated] = useState<PurchaseRequest | null>(null);
  const [busy, setBusy] = useState<"parse" | "submit" | "">("");
  const [error, setError] = useState("");

  async function parse(event: FormEvent) {
    event.preventDefault(); setBusy("parse"); setError(""); setCreated(null);
    try { setDraft(await api.parseIntake(form)); } catch (reason) { setError(formatError(reason)); }
    finally { setBusy(""); }
  }
  async function submit() {
    setBusy("submit"); setError("");
    try { const result = await api.submitIntake(form); setCreated(result); }
    catch (reason) { setError(formatError(reason)); }
    finally { setBusy(""); }
  }

  return (
    <>
      <PageHeader eyebrow="DEMAND INTAKE" title="自然语言需求录入" description="用业务语言描述采购目标，Agent 自动抽取产品、数量、预算、品类和交付要求。" />
      <section className="split-layout intake-layout">
        <form className="panel form-panel" onSubmit={parse}>
          <div className="panel-title"><div><p className="eyebrow">REQUEST BRIEF</p><h2>描述采购需求</h2></div><span className="step-chip">01</span></div>
          <label className="field"><span>需求描述</span><textarea rows={8} value={form.text} onChange={(event) => setForm({ ...form, text: event.target.value })} placeholder="例如：研发部需要采购 20 台 GPU 服务器……" /><small>建议写明产品、数量、预算和用途。</small></label>
          <div className="form-grid">
            <label className="field"><span>申请人员工号</span><input value={form.requester_id} onChange={(event) => setForm({ ...form, requester_id: event.target.value })} /></label>
            <label className="field"><span>所属部门</span><input value={form.department} onChange={(event) => setForm({ ...form, department: event.target.value })} /></label>
            <label className="field"><span>期望交付日期</span><input type="date" value={form.required_date || ""} onChange={(event) => setForm({ ...form, required_date: event.target.value })} /></label>
            <label className="field"><span>优先级</span><select value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value as IntakePayload["priority"] })}><option value="LOW">低</option><option value="MEDIUM">中</option><option value="HIGH">高</option></select></label>
          </div>
          {error && <div className="alert error"><span>{error}</span></div>}
          <button className="primary-button" disabled={!!busy}>{busy === "parse" ? "正在解析…" : "✦ 解析需求"}</button>
        </form>

        <article className="panel draft-panel">
          <div className="panel-title"><div><p className="eyebrow">STRUCTURED DRAFT</p><h2>结构化草稿</h2></div><span className="step-chip">02</span></div>
          {!draft ? <div className="draft-placeholder"><div className="scan-graphic"><span /><span /><span /></div><strong>等待需求解析</strong><p>解析结果会在这里显示，不完整字段将被明确标记。</p></div> : (
            <div className="draft-content">
              <div className={`readiness ${draft.ready_to_submit ? "ready" : "incomplete"}`}><div><span>{draft.ready_to_submit ? "✓" : "!"}</span><div><strong>{draft.ready_to_submit ? "需求信息完整" : "仍需补充信息"}</strong><p>{draft.ready_to_submit ? "可以创建正式采购申请" : `缺少：${draft.missing_fields.join("、")}`}</p></div></div><StatusBadge value={draft.ready_to_submit ? "READY" : "INCOMPLETE"} /></div>
              <dl className="draft-fields"><div><dt>采购产品</dt><dd>{draft.product || "—"}</dd></div><div><dt>采购品类</dt><dd>{draft.category || "—"}</dd></div><div><dt>数量</dt><dd>{draft.quantity ?? "—"}</dd></div><div><dt>预算</dt><dd>{formatMoney(draft.budget)}</dd></div><div><dt>交付日期</dt><dd>{draft.required_date || "—"}</dd></div><div><dt>优先级</dt><dd><StatusBadge value={draft.priority} /></dd></div></dl>
              <button className="primary-button full" disabled={!draft.ready_to_submit || !!busy || !!created} onClick={() => void submit()}>{busy === "submit" ? "正在创建…" : created ? "✓ 已创建采购申请" : "创建正式采购申请"}</button>
              {created && <div className="success-card"><span>✓</span><div><strong>{created.request_id} 创建成功</strong><p>现在可前往采购申请页面启动 Agent 分析。</p></div><a href="#requests">前往分析 →</a></div>}
            </div>
          )}
        </article>
      </section>
    </>
  );
}
