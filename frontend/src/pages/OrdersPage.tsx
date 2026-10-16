import { useCallback, useEffect, useState } from "react";
import { api, formatError } from "../api/client";
import type { GoodsReceipt, PurchaseOrder } from "../types/domain";
import { EmptyState, LoadingBlock, PageHeader, StatusBadge, formatDate, formatMoney } from "../components/ui";

export function OrdersPage() {
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [receiptOrder, setReceiptOrder] = useState<PurchaseOrder | null>(null);
  const [receipts, setReceipts] = useState<GoodsReceipt[]>([]);
  const [receiptsLoading, setReceiptsLoading] = useState(false);
  const load = useCallback(async () => { setLoading(true); setError(""); try { setOrders(await api.orders()); } catch (reason) { setError(formatError(reason)); } finally { setLoading(false); } }, []);
  useEffect(() => { void load(); }, [load]);
  const total = orders.reduce((sum, order) => sum + Number(order.total_amount), 0);

  async function advance(order: PurchaseOrder) {
    const transitions: Record<string, string> = { DRAFT: "ISSUED", ISSUED: "ACKNOWLEDGED", ACKNOWLEDGED: "IN_TRANSIT" };
    const status = transitions[order.status];
    if (!status) return;
    const actor = window.prompt("请输入操作人员工号", "E001");
    if (!actor) return;
    setBusy(order.po_id); setError("");
    try { await api.updateOrderStatus(order.po_id, { status, actor_id: actor, note: `管理控制台推进至 ${status}` }); await load(); }
    catch (reason) { setError(formatError(reason)); }
    finally { setBusy(""); }
  }

  async function showReceipts(order: PurchaseOrder) {
    setReceiptOrder(order); setReceiptsLoading(true); setError("");
    try { setReceipts(await api.orderReceipts(order.po_id)); }
    catch (reason) { setError(formatError(reason)); setReceipts([]); }
    finally { setReceiptsLoading(false); }
  }

  async function receive(order: PurchaseOrder) {
    const receiver = window.prompt("请输入仓库收货人员工号", "E004");
    if (!receiver) return;
    setBusy(order.po_id); setError("");
    try {
      await api.receiveOrder(order.po_id, { received_quantity: order.quantity, accepted_quantity: order.quantity, rejected_quantity: 0, receiver_id: receiver, note: "管理控制台全量验收" });
      await load(); await showReceipts(order);
    } catch (reason) { setError(formatError(reason)); }
    finally { setBusy(""); }
  }

  return <>
    <PageHeader eyebrow="ORDER FULFILLMENT" title="订单履约中心" description="跟踪定标后的采购订单、交付进度与收货验收状态。" actions={<button className="secondary-button" onClick={() => void load()}>↻ 刷新</button>} />
    {error && <div className="alert error"><span>{error}</span></div>}
    <section className="order-kpis"><div><small>订单总数</small><strong>{orders.length}</strong></div><div><small>订单总额</small><strong>{formatMoney(total)}</strong></div><div><small>运输中</small><strong>{orders.filter((item) => item.status === "IN_TRANSIT").length}</strong></div><div><small>已交付</small><strong>{orders.filter((item) => item.status === "DELIVERED").length}</strong></div></section>
    <article className="panel">
      <div className="panel-title"><div><p className="eyebrow">PURCHASE ORDERS</p><h2>采购订单</h2></div><span>{orders.length} 条记录</span></div>
      {loading ? <LoadingBlock /> : orders.length ? <div className="order-grid">{orders.map((order) => <article className="order-card" key={order.po_id}>
        <header><div><span className="mono">{order.po_id}</span><h3>{order.supplier_name}</h3></div><StatusBadge value={order.status} /></header>
        <dl><div><dt>采购申请</dt><dd>{order.request_id}</dd></div><div><dt>采购数量</dt><dd>{order.quantity} 件</dd></div><div><dt>订单金额</dt><dd>{formatMoney(order.total_amount, order.currency)}</dd></div><div><dt>预计交付</dt><dd>{order.expected_delivery_date}</dd></div></dl>
        <div className="fulfillment-track"><span className="complete" /><span className={!['DRAFT', 'ISSUED'].includes(order.status) ? "complete" : ""} /><span className={['IN_TRANSIT', 'DELIVERED'].includes(order.status) ? "complete" : ""} /><span className={order.status === "DELIVERED" ? "complete" : ""} /></div>
        {["DRAFT", "ISSUED", "ACKNOWLEDGED"].includes(order.status) && <button className="secondary-button full order-action" disabled={busy === order.po_id} onClick={() => void advance(order)}>{busy === order.po_id ? "处理中…" : order.status === "DRAFT" ? "签发订单" : order.status === "ISSUED" ? "供应商确认" : "标记运输中"}</button>}
        {order.status === "IN_TRANSIT" && <button className="primary-button full order-action" disabled={busy === order.po_id} onClick={() => void receive(order)}>{busy === order.po_id ? "验收中…" : "办理全量收货"}</button>}
        <button className="text-button receipt-link" onClick={() => void showReceipts(order)}>查看收货记录 →</button>
        <footer><span>创建于 {formatDate(order.created_at, true)}</span><strong>{order.created_by}</strong></footer>
      </article>)}</div> : <EmptyState title="暂无采购订单" detail="Agent 建议通过审批并完成供应商定标后，订单会显示在这里。" />}
    </article>
    {receiptOrder && <article className="panel receipt-panel"><div className="panel-title"><div><p className="eyebrow">GOODS RECEIPTS</p><h2>{receiptOrder.po_id} 收货记录</h2></div><button className="text-button" onClick={() => setReceiptOrder(null)}>关闭</button></div>{receiptsLoading ? <LoadingBlock label="正在读取收货记录" /> : receipts.length ? <div className="receipt-list">{receipts.map((receipt) => <div key={receipt.receipt_id}><span className="receipt-mark">✓</span><div><strong>接收 {receipt.received_quantity} / 合格 {receipt.accepted_quantity} / 拒收 {receipt.rejected_quantity}</strong><p>{receipt.note || "无备注"}</p></div><div><span className="mono">{receipt.receipt_id}</span><time>{receipt.receiver_id} · {formatDate(receipt.received_at, true)}</time></div></div>)}</div> : <EmptyState title="暂无收货记录" detail="订单进入运输中状态后，可办理收货验收。" />}</article>}
  </>;
}
