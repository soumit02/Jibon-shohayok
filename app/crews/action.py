"""Action Crew (Sequential, one agent) - runs ONLY after the user pressed 'Yes'."""
from app.tools.db_tools import make_reminder_tool

AGENTS_USED = ["Reminder and Action Agent"]


def build_action_crew(llm, user_id: int, message: str, remind_on: str, document_id: int):
    from crewai import Agent, Crew, Task

    agent = Agent(
        role="Reminder and Action Agent",
        goal="Create exactly the reminder the user approved, then confirm it politely.",
        backstory="You only do what the user approved. You call create_reminder once, with exactly the approved values.",
        tools=[make_reminder_tool(user_id)],
        allow_delegation=False, verbose=False, llm=llm, max_iter=3,
    )
    task = Task(
        description=(
            "The user APPROVED this reminder. Call create_reminder ONCE with exactly these values:\n"
            f"message = {message}\nremind_on = {remind_on}\ndocument_id = {document_id}\n"
            "Then confirm to the user in one short friendly sentence (same language as the message)."
        ),
        expected_output="One short confirmation sentence.",
        agent=agent,
    )
    return Crew(agents=[agent], tasks=[task], memory=False, verbose=False), task
