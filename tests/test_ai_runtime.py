from procurement_agent.application.intake import RuleBasedDemandUnderstanding
from procurement_agent.core.config import Settings
from procurement_agent.infrastructure.llm.factory import build_demand_understanding


def test_local_ai_runtime_needs_no_external_key(tmp_path) -> None:
    runtime = build_demand_understanding(
        Settings(project_root=tmp_path, llm_provider="local")
    )
    assert isinstance(runtime, RuleBasedDemandUnderstanding)
    assert runtime.provider == "local"


def test_missing_openai_key_falls_back_to_local(tmp_path) -> None:
    runtime = build_demand_understanding(
        Settings(project_root=tmp_path, llm_provider="openai", openai_api_key=None)
    )
    assert runtime.provider == "local"
