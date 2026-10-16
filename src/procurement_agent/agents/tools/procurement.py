from __future__ import annotations

import json
from datetime import date

from langchain_core.tools import BaseTool, StructuredTool

from ...domain.models import (
    PolicyAssessment,
    PurchaseRequest,
    Quotation,
    RequirementAssessment,
    Supplier,
    SupplierRecommendation,
)
from ...infrastructure.knowledge import KnowledgeBase
from ...infrastructure.repositories import CsvRepository
from ..specialists import ComplianceSpecialist, RequirementSpecialist, SupplierSpecialist


class ProcurementToolbox:
    """Read-only tools used by both deterministic nodes and tool-calling models."""

    def __init__(self, repository: CsvRepository, knowledge_base: KnowledgeBase) -> None:
        self.repository = repository
        self.knowledge_base = knowledge_base
        self.requirement_specialist = RequirementSpecialist()
        self.supplier_specialist = SupplierSpecialist()
        self.compliance_specialist = ComplianceSpecialist()

    def get_purchase_request(self, request_id: str) -> PurchaseRequest:
        return self.repository.request_by_id(request_id)

    def find_eligible_suppliers(self, category: str) -> list[Supplier]:
        return self.supplier_specialist.eligible(
            self.repository.suppliers(), category
        )

    def validate_purchase_request(self, request: dict) -> RequirementAssessment:
        purchase_request = PurchaseRequest.model_validate(request)
        try:
            requester = self.repository.employee_by_id(purchase_request.requester_id)
        except LookupError:
            requester = None
        return self.requirement_specialist.assess(purchase_request, requester)

    def get_valid_quotations(
        self, request_id: str, supplier_ids: set[str]
    ) -> list[Quotation]:
        today = date.today()
        valid: list[Quotation] = []
        for quote in self.repository.quotations():
            if quote.request_id != request_id or quote.supplier_id not in supplier_ids:
                continue
            try:
                valid_until = date.fromisoformat(quote.valid_until)
            except ValueError:
                continue
            if valid_until >= today:
                valid.append(quote)
        return valid

    def search_policy(self, query: str, limit: int = 4):
        return self.knowledge_base.search(query, limit)

    def rank_supplier_candidates(
        self,
        request: dict,
        suppliers: list[dict],
        quotations: list[dict],
    ) -> list[SupplierRecommendation]:
        return self.supplier_specialist.rank(
            PurchaseRequest.model_validate(request),
            [Supplier.model_validate(item) for item in suppliers],
            [Quotation.model_validate(item) for item in quotations],
        )

    def evaluate_procurement_policy(
        self,
        request: dict,
        suppliers: list[dict],
        quotations: list[dict],
    ) -> PolicyAssessment:
        purchase_request = PurchaseRequest.model_validate(request)
        supplier_models = [Supplier.model_validate(item) for item in suppliers]
        quotation_models = [Quotation.model_validate(item) for item in quotations]
        return self.compliance_specialist.assess(
            purchase_request, supplier_models, quotation_models
        )

    def as_langchain_tools(self) -> list[BaseTool]:
        def request_lookup(request_id: str) -> str:
            """读取指定采购申请的结构化数据。"""
            return self.get_purchase_request(request_id).model_dump_json()

        def supplier_search(category: str) -> str:
            """查询指定品类中合格且非高风险的供应商。"""
            return json.dumps(
                [item.model_dump(mode="json") for item in self.find_eligible_suppliers(category)],
                ensure_ascii=False,
            )

        def request_validation(request: dict) -> str:
            """校验申请人、部门、状态和需求字段能否进入自动分析。"""
            return self.validate_purchase_request(request).model_dump_json()

        def policy_search(query: str) -> str:
            """检索企业采购制度并返回原文、章节和来源文件。"""
            return json.dumps(
                [item.model_dump(mode="json") for item in self.search_policy(query)],
                ensure_ascii=False,
            )

        def quotation_lookup(request_id: str, supplier_ids: list[str]) -> str:
            """读取申请中属于指定候选供应商的有效报价。"""
            return json.dumps(
                [
                    item.model_dump(mode="json")
                    for item in self.get_valid_quotations(
                        request_id, set(supplier_ids)
                    )
                ],
                ensure_ascii=False,
            )

        def supplier_ranking(
            request: dict, suppliers: list[dict], quotations: list[dict]
        ) -> str:
            """使用确定性采购评分规则对候选供应商排序。"""
            return json.dumps(
                [
                    item.model_dump(mode="json")
                    for item in self.rank_supplier_candidates(
                        request, suppliers, quotations
                    )
                ],
                ensure_ascii=False,
            )

        def policy_evaluation(
            request: dict, suppliers: list[dict], quotations: list[dict]
        ) -> str:
            """执行审批等级、比价数量和寻源充分性等确定性制度检查。"""
            return self.evaluate_procurement_policy(
                request, suppliers, quotations
            ).model_dump_json()

        return [
            StructuredTool.from_function(request_lookup, name="get_purchase_request"),
            StructuredTool.from_function(request_validation, name="validate_purchase_request"),
            StructuredTool.from_function(supplier_search, name="find_eligible_suppliers"),
            StructuredTool.from_function(quotation_lookup, name="get_valid_quotations"),
            StructuredTool.from_function(supplier_ranking, name="rank_supplier_candidates"),
            StructuredTool.from_function(policy_evaluation, name="evaluate_procurement_policy"),
            StructuredTool.from_function(policy_search, name="search_procurement_policy"),
        ]
