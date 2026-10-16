import { useEffect, useState } from "react";
import { Shell, type PageKey } from "./components/Shell";
import { DashboardPage } from "./pages/DashboardPage";
import { IntakePage } from "./pages/IntakePage";
import { RequestsPage } from "./pages/RequestsPage";
import { RunsPage } from "./pages/RunsPage";
import { OrdersPage } from "./pages/OrdersPage";
import { AuditPage } from "./pages/AuditPage";
import { ConversationsPage } from "./pages/ConversationsPage";
import { IntegrationsPage } from "./pages/IntegrationsPage";

const pages: Record<PageKey, () => React.JSX.Element> = {
  dashboard: DashboardPage,
  intake: IntakePage,
  conversations: ConversationsPage,
  requests: RequestsPage,
  runs: RunsPage,
  orders: OrdersPage,
  integrations: IntegrationsPage,
  audit: AuditPage
};

function readPage(): PageKey {
  const value = window.location.hash.replace("#", "") as PageKey;
  return value in pages ? value : "dashboard";
}

export function App() {
  const [page, setPage] = useState<PageKey>(readPage);
  useEffect(() => {
    const listener = () => setPage(readPage());
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  const CurrentPage = pages[page];
  return <Shell active={page} onNavigate={setPage}><CurrentPage /></Shell>;
}
