# agent_inventory.py
import os
import json
import argparse
from typing import Set, Callable, Any


from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import FunctionTool,ToolSet

load_dotenv()

PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
MODEL_DEPLOYMENT_NAME = os.environ["MODEL_DEPLOYMENT_NAME"]
FUNCTION_APP_URL = os.environ["FUNCTION_APP_URL"]
DEFAULT_AGENT_ID = os.environ.get("AGENT_ID")

# generate the schema for function calling
def get_inventory_kpis(key: str | None = None) -> str:
    import requests

    """
    Get inventory KPIs and time series from the inventory analytics API.

    Use this whenever the user asks questions about inventory levels, sales,
    trends, graphs, KPIs, or any analytics based on the CSV inventory file.

    :param key: Optional SKU key (e.g. "y1sp001") to filter the results.
                If omitted, return KPIs and time series for all products.
    :return: A JSON string of the form:
        {
            "items": [
                {
                    "key": "...",
                    "key_name": "...",
                    "current_month": 11,
                    "total_sales": 1900.0,
                    "avg_daily_sales": 475.0,
                    "min_inventory": 78.0,
                    "max_inventory": 100.0,
                    "days_below_100": 3,
                    "time_series": [
                        {
                          "status_date": "2025-11-01",
                          "current_status_inventory": 94,
                          "sales": 600
                        },
                        ...
                    ]
                },
                ...
            ]
        }
    """
    params = {}
    if key:
        params["key"] = key

    resp = requests.get(FUNCTION_APP_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.text


# Build the ReAct-style agent
# Define the set of user functions
#user_functions: Set[Callable[..., Any]] = {get_inventory_kpis}

# Wrap into a FunctionTool
#functions = FunctionTool(functions=user_functions)

#toolset = ToolSet()
#toolset.add(functions)

def create_agent():

    if not PROJECT_ENDPOINT or not MODEL_DEPLOYMENT_NAME:
        raise RuntimeError("PROJECT_ENDPOINT or MODEL_DEPLOYMENT_NAME missing in environment.")


    project_client = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    # Define the tool for the agent
    tool = {
        "type": "function",
        "function": {
            "name": "get_inventory_kpis",
            "description": "Read inventory KPIs and time-series data for an item key",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                }
            }
        }
    }

    #with project_client:
    agent = project_client.agents.create_agent(
        model=MODEL_DEPLOYMENT_NAME,
        name="InventoryAnalyticsAgent",
        instructions=(
            "You are an inventory analytics assistant.\n"
            "You have access to a tool called `get_inventory_kpis` use it "
            "that returns KPIs and daily time series data from an inventory CSV.\n\n"
            "Use a ReAct (Reason + Act) pattern:\n"
            "1. First, think step-by-step about what the user is asking.\n"
            "2. If you need data from the file (almost always), call the tool.\n"
            "3. After receiving tool output, carefully analyze it and then respond clearly.\n\n"
            "When answering:\n"
            "- For tables, output Markdown tables.\n"
            "- For graphs, output a JSON 'chart_spec' object like:\n"
            "  {\"x\": [...], \"y\": [...], \"series_name\": \"...\", \"type\": \"line\"}\n"
            "  that a frontend could render.\n"
            "- Always explain the KPIs in plain language.\n"
        ),
        tools=[tool]
    )

    print(f"Created agent: {agent.id}")
    print("NOW save this ID into your .env as AGENT_ID = ", agent.id)

    return project_client, agent
    
#ReAct conversation with function calling
# agent_inventory.py (continued)

def chat_with_agent(question: str, agent_id: str):

    if not PROJECT_ENDPOINT:
        raise RuntimeError("PROJECT_ENDPOINT missing in environment.")
        
    #with project_client:

    project_client = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    # Register the Python callback implementation
    project_client.agents.enable_auto_function_calls(tools=[get_inventory_kpis])

    # Create a thread
    thread = project_client.agents.threads.create()
    print(f"Thread: {thread.id}")

    # Add user message
    project_client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content=question,
    )

    # Run the agent, letting it automatically call tools if needed
    run = project_client.agents.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent_id,
    )

    print(f"Run finished with status: {run.status}")
    if run.status == "failed":
        print(f"Error: {run.last_error}")

    # Fetch messages (including final assistant answer)
    messages = project_client.agents.messages.list(thread_id=thread.id)
    
    print("\n===== ASSISTANT RESPONSE =====\n")
    for m in messages:
        if m.role == "assistant":
            for c in m.content:

                # Only process text blocks
                if c.type == "text":
                    # Some SDK versions use c.text, others use c.text.value
                    text = getattr(c.text, "value", c.text)

                    print(text)
#    for m in messages:
#        role = m["role"]
#        content = m["content"]
#        print(f"{role.upper()}: {content}")

    # Clean up (optional)
    #project_client.agents.delete_agent(agent.id)

def main():
    parser = argparse.ArgumentParser(description="Inventory Agent CLI")

    parser.add_argument("--create-agent", action="store_true",
                        help="Create the agent in Foundry")

    parser.add_argument("--chat", type=str,
                        help="Send a question to the agent")

    parser.add_argument("--agent-id", type=str,
                        help="Override agent ID instead of using .env")

    args = parser.parse_args()

    # Action: Create the agent
    if args.create_agent:
        create_agent()
        return

    # Action: Chat
    if args.chat:
        agent_id = args.agent_id or DEFAULT_AGENT_ID
        if not agent_id:
            raise RuntimeError(
                "No agent ID provided. Use --agent-id or define AGENT_ID in .env"
            )

        chat_with_agent(args.chat, agent_id)
        return

    # If no arguments
    parser.print_help()


if __name__ == "__main__":
    main()


#if __name__ == "__main__":
#    q = (
#        "For product key y1sp001 in November, show me:\n"
#        "- A table of day, inventory, and sales.\n"
#        "- KPIs (total sales, average daily sales, min/max inventory, days below 100).\n"
#        "- A JSON spec for a line chart of inventory over time."
#    )
#    chat_with_agent(q)
