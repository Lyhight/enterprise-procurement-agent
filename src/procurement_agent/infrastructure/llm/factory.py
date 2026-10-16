from __future__ import annotations

from ...application.intake import RuleBasedDemandUnderstanding
from ...application.ports.language_model import DemandUnderstanding
from ...agents.core import LocalPlanAndExecutePlanner, PlanAndExecutePlanner
from ...core.config import Settings


def build_demand_understanding(settings: Settings) -> DemandUnderstanding:
    if settings.llm_provider != "openai" or not settings.openai_api_key:
        return RuleBasedDemandUnderstanding()
    try:
        from .openai_understanding import OpenAIDemandUnderstanding

        return OpenAIDemandUnderstanding(settings.openai_api_key, settings.openai_model)
    except ImportError:
        return RuleBasedDemandUnderstanding()


def build_agent_planner(settings: Settings) -> PlanAndExecutePlanner:
    if settings.llm_provider != "openai" or not settings.openai_api_key:
        return LocalPlanAndExecutePlanner()
    try:
        from .openai_planner import OpenAIPlanAndExecutePlanner

        return OpenAIPlanAndExecutePlanner(
            settings.openai_api_key,
            settings.openai_model,
        )
    except ImportError:
        return LocalPlanAndExecutePlanner()
