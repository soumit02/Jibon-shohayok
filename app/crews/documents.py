"""Document Crew (Sequential): Document Vault Agent (reads an uploaded file) and Deadline Tracker Agent (answers about saved documents)."""
from app.tools.db_tools import make_documents_tool

VAULT_AGENTS = ["Document Vault Agent"]
DEADLINE_AGENTS = ["Deadline Tracker Agent"]


def build_vault_crew(llm, text: str, type_hint: str = ""):
    from crewai import Agent, Crew, Task

    vault = Agent(
        role="Document Vault Agent",
        goal="Read the text of an official document and extract only the key fields, exactly as written.",
        backstory="You are a careful clerk. You never guess a value. If something is not clearly written you answer null.",
        allow_delegation=False, verbose=False, llm=llm, max_iter=3,
    )
    task = Task(
        description=(
            "Extract fields from this document text and answer with ONE JSON object and nothing else.\n"
            "Keys: doc_type (one of: passport, driving_license, nid, insurance, bill, other), title (short), "
            "holder_name, doc_number, issue_date (YYYY-MM-DD), expiry_date (YYYY-MM-DD).\n"
            "Use null when a value is not clearly present. Dates in the text are usually day-month-year "
            "(for example 15 MAR 2028 or 15/03/2028 means 2028-03-15). "
            f"Hint from the user about the type: {type_hint or 'none'}.\n\n"
            f"DOCUMENT TEXT:\n{text[:6000]}"
        ),
        expected_output="One JSON object with the keys doc_type, title, holder_name, doc_number, issue_date, expiry_date.",
        agent=vault,
    )
    return Crew(agents=[vault], tasks=[task], memory=False, verbose=False), task


def build_deadline_crew(llm, question: str, user_context: str, user_id: int):
    from crewai import Agent, Crew, Task

    tracker = Agent(
        role="Deadline Tracker Agent",
        goal="Answer questions about the user's own documents and deadlines using the saved records only.",
        backstory="You read the user's saved documents with the list_my_documents tool (call it with doc_type='all'). Dates and 'days left' come from the tool; you never calculate dates yourself.",
        tools=[make_documents_tool(user_id)],
        allow_delegation=False, verbose=False, llm=llm, max_iter=4,
    )
    task = Task(
        description=(
            f"User question: {question}\n\nAbout the user:\n{user_context}\n\n"
            "Call list_my_documents first with doc_type='all'. Answer ONLY from its result. "
            "If it says NO_DOCUMENTS, tell the user to upload or add the document first. If several documents match (for example two passports), answer for ALL of them and name the holder of each; do not ask which one. "
            "Write in Bangla (Bengali script) unless the user wrote in English. Mention the expiry date and the days left.\n"
            "If a document is expiring or the user asked for a reminder, END your answer with one line per proposed reminder (one line for each document) in exactly this format "
            "(use the suggested_reminder_date from the tool):\n"
            "PROPOSE_REMINDER: <document_id> | <YYYY-MM-DD> | <short reminder message in the user's language>\n"
            "You only PROPOSE reminders; the user must approve them."
        ),
        expected_output="A short Bangla answer, optionally followed by PROPOSE_REMINDER lines.",
        agent=tracker,
    )
    return Crew(agents=[tracker], tasks=[task], memory=False, verbose=False), task
