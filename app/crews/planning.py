"""
Planning Crew (Hierarchical) - same shape as Leo's Teaching crew:
  Planning Manager (like Coordinator) -> Trip Planner (like Explainer) -> Budget Estimator (like Quiz Master)
The Estimator can say OVER_BUDGET, then the code asks the crew to re-plan (like Leo's RE-TEACH).
"""
from app.tools.common_tools import make_calculator_tool, make_weather_tool, make_web_search_tool
from app.tools.db_tools import make_travel_cost_tool

AGENTS_USED = ["Planning Manager", "Trip and Logistics Planner", "Budget and Cost Estimator"]


def build_planning_crew(llm, request: str, user_context: str, extra_note: str = ""):
    from crewai import Agent, Crew, Process, Task

    manager = Agent(
        role="Planning Manager",
        goal="Coordinate the Trip Planner and the Budget Estimator so the final plan fits the user's budget.",
        backstory="You lead a small planning team inside a personal life-admin assistant for people in Bangladesh.",
        allow_delegation=True, verbose=False, llm=llm,
    )
    planner = Agent(
        role="Trip and Logistics Planner",
        goal="Build a practical plan: how to travel, where to stay, what to do. Use the tools for facts.",
        backstory="You know travel inside Bangladesh. You never invent prices; you use the cost table or at most one web search. You only use the tools you were given (never browser or web_open tools).",
        tools=[make_travel_cost_tool(), make_weather_tool(), make_web_search_tool()],
        allow_delegation=False, verbose=False, llm=llm, max_iter=4,
    )
    estimator = Agent(
        role="Budget and Cost Estimator",
        goal="Cost every option, compare with the budget, and say clearly if it is over budget.",
        backstory="You are careful with money. You ALWAYS use the calculator tool for sums and you label prices as estimates.",
        tools=[make_calculator_tool(), make_travel_cost_tool()],
        allow_delegation=False, verbose=False, llm=llm, max_iter=4,
    )

    plan_task = Task(
        description=(
            f"User request: {request}\n\nWhat we know about the user:\n{user_context}\n\n"
            "Create a travel/event plan with THREE options: Economy, Balanced, Comfort. "
            "TOOL BUDGET (very important, it keeps the answer fast): use at most 3 tool calls in total - lookup_travel_costs once, "
            "weather_forecast at most once (only if the trip is within 7 days), web_search at most once (only if the cost table has no data). "
            "Then write the plan immediately. "
            "If a price is missing, say 'price not available' - do NOT invent it.\n"
            f"{extra_note}"
        ),
        expected_output="A short plan with three options and the cost items you found (transport, stay, food, other).",
        agent=planner,
    )
    cost_task = Task(
        description=(
            "Using the plan, calculate the total for each option (use the calculator tool), compare with the user's budget, "
            "and write the FINAL answer for the user. Write in Bangla (Bengali script) unless the user wrote in English. "
            "Show prices in BDT (taka). Say that all prices are estimates to verify before booking.\n"
            "The LAST TWO lines must be exactly:\n"
            "FINAL_STATUS: WITHIN_BUDGET   (or OVER_BUDGET if NO option fits the budget)\n"
            "BEST_FIT_TOTAL_BDT: <number, or 0>"
        ),
        expected_output="A clear Bangla answer with three costed options, which ones fit the budget, and the two final status lines.",
        agent=estimator,
        context=[plan_task],
    )
    crew = Crew(
        agents=[planner, estimator], tasks=[plan_task, cost_task],
        manager_agent=manager, process=Process.hierarchical, memory=False, verbose=False,
    )
    return crew, cost_task
