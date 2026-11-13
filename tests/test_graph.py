from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from multi_agent_orchestrator.api.service import initial_state
from multi_agent_orchestrator.graph import build_graph
from tests.fakes import MalformedStructuredModel, ScriptedModel


async def test_graph_pauses_and_resumes_for_critical_result() -> None:
    graph = build_graph(ScriptedModel(), checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "critical-job"}}

    paused = await graph.ainvoke(
        initial_state("Investiga el impacto de errores de checkout y calcula su prioridad."),
        config=config,
    )

    assert paused["approval_status"] == "pending"
    assert paused["analysis_result"]["priority"] == "P1"
    assert paused["__interrupt__"][0].value["kind"] == "critical_result_approval"

    completed = await graph.ainvoke(
        Command(resume={"approved": True, "feedback": "Riesgo revisado."}),
        config=config,
    )

    assert completed["approval_status"] == "approved"
    assert completed["final_answer"].startswith("Prioridad P1")
    assert completed["completed_agents"] == [
        "researcher",
        "analyst",
        "validator",
        "approval",
        "synthesizer",
    ]


async def test_human_rejection_stops_before_synthesis() -> None:
    graph = build_graph(ScriptedModel(), checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "rejected-job"}}
    await graph.ainvoke(initial_state("Analiza el incidente critico de checkout."), config=config)

    rejected = await graph.ainvoke(
        Command(resume={"approved": False, "feedback": "Se requiere mas evidencia."}),
        config=config,
    )

    assert rejected["approval_status"] == "rejected"
    assert "Se requiere mas evidencia" in rejected["final_answer"]
    assert "synthesizer" not in rejected["completed_agents"]


async def test_malformed_structured_outputs_use_valid_fallbacks() -> None:
    graph = build_graph(
        MalformedStructuredModel(), checkpointer=MemorySaver()
    )
    config = {"configurable": {"thread_id": "malformed-output-job"}}

    paused = await graph.ainvoke(
        initial_state("Investiga el impacto de errores de checkout y calcula su prioridad."),
        config=config,
    )

    assert paused["task_completed"] is True
    assert paused["analysis_result"]["priority"] == "P1"
    assert paused["analysis_result"]["drivers"]

    completed = await graph.ainvoke(
        Command(resume={"approved": True, "feedback": "Salida revisada."}),
        config=config,
    )

    assert completed["final_answer"].startswith("Prioridad P1")
    assert completed["approval_status"] == "approved"


async def test_specialists_keep_bounded_toolsets() -> None:
    from multi_agent_orchestrator.agents import AnalysisAgent, ResearchAgent

    research_tools = {item.name for item in ResearchAgent.tools}
    analysis_tools = {item.name for item in AnalysisAgent.tools}

    assert research_tools == {"search_incident_knowledge"}
    assert analysis_tools == {"calculate_incident_priority"}
    assert research_tools.isdisjoint(analysis_tools)
