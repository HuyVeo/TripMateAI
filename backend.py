import os 
import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from typing import TypedDict, Annotated
import json
import operator
import re
import time
import uuid

import psycopg
from psycopg.rows import dict_row

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain_groq import ChatGroq
from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights

# Report template (render_plan_html / render_plan_pdf). It lives next to
# this file; if it is missing, the agent keeps working but only returns
# the markdown answer (frontend falls back to the old rendering).
try:
    from report_template import (
        PLAN_JSON_INSTRUCTIONS,
        render_plan_pdf,
    )
except ImportError:  # pragma: no cover - template not deployed
    PLAN_JSON_INSTRUCTIONS = None
    render_plan_pdf = None


def get_database_url():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your Render PostgreSQL External Database URL to .env"
        )

    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")


# =========================
# LLM
# =========================

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=GROQ_API_KEY,
    max_tokens=8192
)


# =========================
# State
# =========================

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int


# =========================
# Prompt-size helpers (Groq free tier: 8000 tokens/min for gpt-oss-120b)
# =========================

def _truncate_text(text: str, max_chars: int) -> str:
    """Cap a tool result before it goes into an LLM prompt."""
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[...truncated to fit the model context...]"


def _is_rate_limit_error(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    message = str(error).lower()
    return (
        status in (413, 429)
        or "rate_limit" in message
        or "too large" in message
        or "request too large" in message
    )


def _is_too_large_error(error: Exception) -> bool:
    """413: the request itself is bigger than the per-minute budget.
    Sleeping will not help — the prompt must be shortened."""
    status = getattr(error, "status_code", None)
    message = str(error).lower()
    return status == 413 or "too large" in message or "request too large" in message


# =========================
# Flight Agent
# =========================

def flight_agent(state: TravelState):
    query = state["user_query"]
    flight_data = search_flights(query)

    return {
        "flight_results": flight_data,
        "messages": [
            AIMessage(content="Flight results fetched.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }



# =========================
# Hotel Agent
# =========================

def hotel_agent(state: TravelState):
    query = f"Best hotels for {state['user_query']}"
    hotel_results = tavily_search(query)

    return {
        "hotel_results": hotel_results,
        "messages": [
            AIMessage(content="Hotel information fetched.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }




# =========================
# Itinerary Agent
# =========================

def itinerary_agent(state: TravelState):
    prompt = f"""
Create a complete travel itinerary.

User Query:
{state['user_query']}

Flight Results:
{_truncate_text(state['flight_results'], 2500)}

Hotel Results:
{_truncate_text(state['hotel_results'], 2500)}

Make the itinerary practical, budget-aware, and easy to follow.
"""

    response = llm.invoke([
        SystemMessage(content="You are an expert travel planner."),
        HumanMessage(content=prompt)
    ])

    return {
        "itinerary": response.content,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }



# =========================
# Final Response Agent
# =========================

def final_agent(state: TravelState):
    # The report template needs structured data, not a markdown blob:
    # ask the model for the plan as one JSON object (see report_template.py).
    # If the template module is not deployed, fall back to the old
    # markdown sections so the app keeps working.
    if PLAN_JSON_INSTRUCTIONS:
        format_instructions = PLAN_JSON_INSTRUCTIONS
    else:
        format_instructions = (
            "Format the final answer beautifully using these sections:\n\n"
            "1. Trip Summary\n2. Flight Information\n3. Hotel Suggestions\n"
            "4. Day-by-Day Itinerary\n5. Estimated Budget\n6. Final Recommendations"
        )

    # Minimal JSON instructions for the emergency retry (no schema example).
    minimal_instructions = (
        "Output ONLY a JSON object, no fences, same language as the query. "
        "Keys: destination, origin, dates, duration, travelers, budget_label, style, "
        "summary_cards[{label,value,note}], flights[{airline,route,duration,price,note,highlight}], "
        "flight_note, visa_note, hotels[{name,area,price,note,highlight}], hotel_note, "
        "days[{title,subtitle,date,items[{time,activity,cost}]}], "
        "budget{items[{name,detail,amount,label}],total_amount,total_label,limit_amount,limit_label,remaining_label}, "
        "tips[{title,text}], disclaimer. \"highlight\" is a short badge or null. "
        "Amounts are plain numbers; items must add up to total_amount. "
        "Never invent links, codes or real-time prices."
    )

    def build_prompt(flight_chars, hotel_chars, itinerary_chars, fmt):
        return f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Flights:
{_truncate_text(state['flight_results'], flight_chars)}

Hotels:
{_truncate_text(state['hotel_results'], hotel_chars)}

Itinerary:
{_truncate_text(state['itinerary'], itinerary_chars)}

{fmt}

Important:
- Be clear and practical.
- Mention that live flight API may not provide ticket prices if pricing is unavailable.
- Keep the response useful for real travel planning.
"""

    def invoke_once(prompt):
        return llm.invoke([
            SystemMessage(content="You are a professional AI travel booking assistant."),
            HumanMessage(content=prompt),
        ])

    # Groq free tier allows 8000 tokens/min for gpt-oss-120b. The old prompt
    # (full flight + hotel + itinerary text + the long JSON schema) reached
    # 8787 tokens and failed with 413 "Request too large". The caps below
    # keep the prompt around ~2500 tokens, and on a 413 we retry once with
    # a much shorter prompt instead of failing the whole request.
    levels = [
        (2000, 1500, 4000, format_instructions),
        (1200, 1000, 2000, minimal_instructions),
    ]
    last_error = None
    for flight_chars, hotel_chars, itinerary_chars, fmt in levels:
        prompt = build_prompt(flight_chars, hotel_chars, itinerary_chars, fmt)
        for attempt in range(2):  # one retry per level (TPM budget refills)
            try:
                response = invoke_once(prompt)
                return {
                    "messages": [response],
                    "llm_calls": state.get("llm_calls", 0) + 1
                }
            except Exception as error:
                last_error = error
                if _is_too_large_error(error):
                    break  # shrinking is the only fix: go to the shorter level
                if _is_rate_limit_error(error) and attempt == 0:
                    time.sleep(5)
                    continue  # TPM refills: retry the same prompt once
                if _is_rate_limit_error(error):
                    break  # already retried: fall through to the fallback
                raise  # not a rate problem (bad key, network...): surface it
        if not _is_too_large_error(last_error):
            break

    # All retries failed on rate limits: return the itinerary as the answer
    # so the request still succeeds (frontend renders it as markdown,
    # plan=None) instead of a 500.
    fallback = state.get("itinerary") or (
        "Could not generate the final travel plan (model rate limit). "
        "Please try again in a minute."
    )
    return {
        "messages": [AIMessage(content=fallback)],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Structured plan (JSON) + PDF export
# =========================

def parse_plan_json(answer: str):
    """Extract the structured plan JSON from the final agent's answer.

    Returns the plan dict, or None when the LLM did not return valid JSON
    (the frontend then falls back to rendering the raw markdown).
    """
    if not answer:
        return None
    text = answer.strip()
    # Strip a ```json ... ``` fence if the model added one.
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start:end + 1].strip()
        else:
            candidate = text

    # 1. Direct json.loads
    try:
        plan = json.loads(candidate)
        if isinstance(plan, dict) and (plan.get("destination") or plan.get("days")):
            return plan
    except Exception:
        pass

    # 2. Resilient parsing with json_repair (handles unclosed brackets, truncation)
    try:
        import json_repair
        plan = json_repair.repair_json(candidate, return_objects=True)
        if isinstance(plan, dict) and (plan.get("destination") or plan.get("days")):
            return plan
    except Exception:
        pass

    return None


def render_travel_plan_pdf(plan: dict) -> bytes:
    """Render a parsed plan dict to PDF bytes (see report_template.py)."""
    if render_plan_pdf is None:
        raise RuntimeError(
            "report_template.py is not available next to backend.py, "
            "so server-side PDF export is disabled."
        )
    return render_plan_pdf(plan)


# =========================
# Build Graph
# =========================

graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)


# =========================
# PostgreSQL Checkpointer
# =========================
DATABASE_URL = get_database_url()

_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)



# =========================
# Function for FastAPI
# =========================

def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = travel_graph.invoke(
        {
            "messages": [
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "itinerary": "",
            "llm_calls": 0
        },
        config=config
    )

    final_answer = result["messages"][-1].content

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        # Structured plan for the designed report; None when the model
        # did not return valid JSON (frontend falls back to markdown).
        "plan": parse_plan_json(final_answer),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "itinerary": result.get("itinerary", ""),
        "llm_calls": result.get("llm_calls", 0),
    }