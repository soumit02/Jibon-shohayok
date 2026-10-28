"""Procedure Guide Crew (Sequential, one agent) - uses RAG (Chroma + Gemini embeddings)."""
from app.tools.db_tools import make_documents_tool
from app.tools.rag_tools import make_rag_tool

AGENTS_USED = ["Procedure Guide Agent"]


def build_procedure_crew(llm, question: str, user_context: str, user_id: int, sources_sink: list):
    from crewai import Agent, Crew, Task

    guide = Agent(
        role="Procedure Guide Agent",
        goal="Explain official procedures (documents needed, steps, fees) using ONLY the official documents found by the search tool.",
        backstory=(
            "You help people in Bangladesh with passport, driving licence and tax procedures. "
            "The documents may be in English while the user writes Bangla: read them and answer in the user's language. "
            "You never answer from memory. If the search says NO_RELIABLE_INFO you say you do not know."
        ),
        tools=[make_rag_tool(sources_sink), make_documents_tool(user_id)],
        allow_delegation=False, verbose=False, llm=llm, max_iter=6,
    )
    task = Task(
        description=(
            f"User question: {question}\n\nAbout the user:\n{user_context}\n\n"
            "Steps: 1) call search_official_docs with the user's question; 2) call it AGAIN with a short English version of the question; "
            "3) call list_my_documents with doc_type='all' to see which documents the user already saved.\n"
            "Then answer in Bangla (Bengali script) unless the user wrote in English: list the needed documents/steps, "
            "mark which ones the user already has and which are missing (only if relevant), and name the source title for each important fact. "
            "End with: rules change, so please check the latest rules on the official website.\n"
            "If the search result is NO_RELIABLE_INFO or SEARCH_ERROR, do not guess: say you do not have reliable information and suggest the official website."
        ),
        expected_output="A clear Bangla answer with the required documents or steps, the sources, and a note to verify the latest rules.",
        agent=guide,
    )
    return Crew(agents=[guide], tasks=[task], memory=False, verbose=False), task
