"""Application composition root shared by API routers."""

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from ..application.conversation import ConversationService
from ..application.integrations import EnterpriseIntegrationService
from ..application.integration_worker import IntegrationQueueService, IntegrationWorker
from ..application.orders import OrderService
from ..application.rfq_delivery import (
    RfqDeliveryService,
    RfqDeliveryWorker,
    SupplierQuotationCallbackService,
)
from ..application.workflow import ProcurementWorkflow
from ..agents.interactive_graph import InteractiveProcurementAgent
from ..core.config import get_settings
from ..core.auth import BearerTokenAuth
from ..infrastructure.knowledge import KnowledgeBase
from ..infrastructure.execution_control import AgentExecutionControlStore
from ..infrastructure.memory import AgentMemoryStore
from ..infrastructure.tracing import AgentTraceStore
from ..infrastructure.llm.factory import build_agent_planner, build_demand_understanding
from ..infrastructure.integrations.factory import build_integration_gateways
from ..infrastructure.integration_jobs import IntegrationJobStore
from ..infrastructure.persistence import (
    AuditStore,
    ConversationStore,
    IntegrationStore,
    OrderStore,
    RequestStore,
    RunStore,
)
from ..infrastructure.repositories import CsvRepository
from ..infrastructure.supplier_messaging import (
    RfqDeliveryStore,
    SupplierCallbackStore,
    SupplierCallbackVerifier,
)
from ..infrastructure.supplier_messaging.factory import build_supplier_gateway

settings = get_settings()
auth_service = BearerTokenAuth(settings.auth_tokens)
demand_understanding = build_demand_understanding(settings)

request_store = RequestStore(settings.database_path)
request_store.initialize()

repository = CsvRepository(
    settings.company_data_dir,
    request_store.list,
    request_store.quotations,
)

knowledge_base = KnowledgeBase(settings.documents_dir)
memory_store = AgentMemoryStore(settings.database_path)
memory_store.initialize()
trace_store = AgentTraceStore(settings.database_path)
trace_store.initialize()
execution_control_store = AgentExecutionControlStore(settings.database_path)
execution_control_store.initialize()
execution_checkpoint_connection = sqlite3.connect(
    settings.database_path, check_same_thread=False
)
execution_checkpointer = SqliteSaver(execution_checkpoint_connection)
workflow = ProcurementWorkflow(
    repository,
    knowledge_base,
    planner=build_agent_planner(settings),
    memory_reader=memory_store,
    memory_writer=memory_store,
    checkpointer=execution_checkpointer,
    trace_writer=trace_store,
    max_iterations=settings.agent_max_iterations,
    max_runtime_seconds=settings.agent_max_runtime_seconds,
    cancellation_reader=execution_control_store,
)
interactive_agent = InteractiveProcurementAgent(
    workflow.agent, settings.database_path, memory_store
)

run_store = RunStore(settings.database_path)
run_store.initialize()

audit_store = AuditStore(settings.database_path)
audit_store.initialize()

conversation_store = ConversationStore(settings.database_path)
conversation_store.initialize()
conversation_service = ConversationService(
    conversation_store, request_store, demand_understanding
)

integration_store = IntegrationStore(settings.database_path)
integration_store.initialize()
oa_gateway, erp_gateway = build_integration_gateways(settings)
integration_service = EnterpriseIntegrationService(
    integration_store, oa_gateway, erp_gateway
)
integration_job_store = IntegrationJobStore(settings.database_path)
integration_job_store.initialize()
integration_queue = IntegrationQueueService(integration_job_store, run_store)
integration_worker = IntegrationWorker(
    integration_job_store, run_store, integration_service
)

order_store = OrderStore(settings.database_path)
order_store.initialize()
order_service = OrderService(order_store)

rfq_delivery_store = RfqDeliveryStore(settings.database_path)
rfq_delivery_store.initialize()
supplier_callback_store = SupplierCallbackStore(settings.database_path)
supplier_callback_store.initialize()
supplier_gateway = build_supplier_gateway(settings)
rfq_delivery_service = RfqDeliveryService(
    rfq_delivery_store, request_store, repository
)
rfq_delivery_worker = RfqDeliveryWorker(
    rfq_delivery_store, request_store, supplier_gateway
)
supplier_callback_service = (
    SupplierQuotationCallbackService(
        SupplierCallbackVerifier(
            settings.supplier_callback_secret,
            settings.supplier_callback_tolerance_seconds,
        ),
        supplier_callback_store,
        request_store,
    )
    if settings.supplier_callback_secret
    else None
)

