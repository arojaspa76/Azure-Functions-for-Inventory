# LLM Inventory Analytics with Microsoft Foundry + Azure Functions (ReAct + Tool Calling)

This repository implements an **end-to-end inventory analytics assistant** that:

- Uses a **LLM agent in Microsoft AI Foundry** with the **ReAct (Reason + Act)** pattern and **Tool Calling**.
- Calls an **Azure Function (Python v2)** that reads an inventory **CSV from Blob Storage** and computes KPIs + time series.
- Provides a **Python CLI** to chat with the agent from the console and see nicely formatted responses.

> This README takes you **step by step from zero (prerequisites)** up to the last thing we did:  
> calling the agent from the console with a formatted answer.

---

## 0. High-Level Architecture

```text
┌───────────────────────────────┐
│        Console (CLI)         │
│  python agent_inventory.py   │
│        --chat "..."          │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│  AIProjectClient (local SDK)  │
│  - Calls Agent in Foundry     │
│  - Executes tool via Python   │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│   Agent in Microsoft Foundry  │
│  ReAct + Tool Calling         │
│  Tool: get_inventory_kpis     │
└──────────────┬────────────────┘
               │  (HTTP)
               ▼
┌───────────────────────────────┐
│ Azure Function App (Python v2)│
│   /api/inventory_stats        │
│ - Reads CSV from Blob Storage │
│ - Computes KPIs + time series │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│        Azure Blob Storage     │
│  container: inventory-data    │
│  blob:      inventory.csv     │
└───────────────────────────────┘
```

---

## 1. Prerequisites

### 1.1. Azure & Services

- An active **Azure subscription**.
- Access to **Microsoft AI Foundry** (Azure AI Studio).
- Permissions to:
  - Create **Storage Accounts**
  - Create **Function Apps**
  - Create **AI Foundry Projects & Agents**

### 1.2. Local Tools

On your development machine (Ubuntu 24.04 in your case):

- **Python** 3.10 or 3.12
- **Git** (optional but recommended)
- **Azure CLI** installed and logged in:

  ```bash
  az login
  ```

- **Azure Functions Core Tools v4** (for Python, v2 model)

Example install for Ubuntu 24.04:

```bash
curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > microsoft.gpg
sudo mv microsoft.gpg /etc/apt/trusted.gpg.d/microsoft.gpg

echo "deb [arch=amd64] https://packages.microsoft.com/ubuntu/24.04/prod noble main" \
  | sudo tee /etc/apt/sources.list.d/azure-functions.list

sudo apt-get update
sudo apt-get install azure-functions-core-tools-4

func --version  # verify it works
```

---

## 2. Inventory CSV in Blob Storage

Create a **Storage Account** (or reuse an existing one) and a **container**.

1. In Azure Portal → Storage Accounts → create/select an account.
2. Go to **Containers** → create container: `inventory-data`.
3. Upload a file named `inventory.csv` with content similar to:

```csv
key,key_name,current_month,montly_begin_inventory,last_inventory,status_date,current_status_inventory,sales
y1sp001,tintaxyz,11,100,0,11-01-2025,94,600
y1sp001,tintaxyz,11,94,6,11-02-2025,91,300
y1sp001,tintaxyz,11,91,3,11-03-2025,81,1000
y1sp001,tintaxyz,11,81,10,11-04-2025,78,300
y1sp002,tintadef,11,250,0,11-01-2025,201,49
y1sp002,tintadef,11,201,49,11-02-2025,101,100
y1sp002,tintadef,11,101,100,11-03-2025,92,9
y1sp002,tintadef,11,92,9,11-04-2025,91,0
```

4. In the Storage Account → **Access keys** → copy the **Connection string**.  
   You will use it as `BLOB_CONNECTION_STRING`.

---

## 3. Azure Function App (Python v2) – `inventory_stats`

We'll create a Function App project named `azfuncinventory` and a route:

```http
GET /api/inventory_stats?key=y1sp001
```

which:

- Reads `inventory.csv` from Blob.
- Optionally filters by `key`.
- Computes KPIs and a daily time series.
- Returns JSON.

### 3.1. Create Function Project (local)

```bash
mkdir azfuncinventory
cd azfuncinventory

python3 -m venv .venv
source .venv/bin/activate

func init . --worker-runtime python --model V2
```

Install required packages:

```bash
pip install azure-functions azure-storage-blob pandas
pip freeze > requirements.txt
```

### 3.2. Configure `local.settings.json`

Edit `local.settings.json`:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",

    "BLOB_CONNECTION_STRING": "<YOUR_CONNECTION_STRING>",
    "BLOB_CONTAINER": "inventory-data",
    "BLOB_NAME": "inventory.csv"
  }
}
```

> Never commit real connection strings to GitHub.

### 3.3. Implement `inventory_stats` in `function_app.py`

Create or edit `function_app.py`:

```python
import logging
import json
import os
from io import StringIO

import azure.functions as func
from azure.storage.blob import BlobServiceClient
import pandas as pd

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

BLOB_CONNECTION_STRING = os.environ["BLOB_CONNECTION_STRING"]
BLOB_CONTAINER = os.environ.get("BLOB_CONTAINER", "inventory-data")
BLOB_NAME = os.environ.get("BLOB_NAME", "inventory.csv")


@app.route(route="inventory_stats", methods=["GET"])
def inventory_stats(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("inventory_stats HTTP trigger called.")

    try:
        key = req.params.get("key")  # optional filter

        blob_service = BlobServiceClient.from_connection_string(
            BLOB_CONNECTION_STRING
        )
        blob_client = blob_service.get_blob_client(
            container=BLOB_CONTAINER, blob=BLOB_NAME
        )

        # Read CSV into memory
        stream = blob_client.download_blob()
        csv_text = stream.readall().decode("utf-8")

        df = pd.read_csv(StringIO(csv_text))

        if "status_date" in df.columns:
            df["status_date"] = pd.to_datetime(df["status_date"], format="%m-%d-%Y")

        if key:
            df = df[df["key"] == key]

        if df.empty:
            body = {"items": [], "message": "No data found for given filters"}
            return func.HttpResponse(
                json.dumps(body), mimetype="application/json", status_code=200
            )

        result = []

        for sku, group in df.groupby("key"):
            group = group.sort_values("status_date")

            total_sales = float(group["sales"].sum())
            avg_daily_sales = float(group["sales"].mean())
            min_inventory = float(group["current_status_inventory"].min())
            max_inventory = float(group["current_status_inventory"].max())
            days_below_100 = int(
                (group["current_status_inventory"] < 100).sum()
            )

            item = {
                "key": sku,
                "key_name": group["key_name"].iloc[0],
                "current_month": int(group["current_month"].iloc[0]),
                "total_sales": total_sales,
                "avg_daily_sales": avg_daily_sales,
                "min_inventory": min_inventory,
                "max_inventory": max_inventory,
                "days_below_100": days_below_100,
                "time_series": group[
                    ["status_date", "current_status_inventory", "sales"]
                ]
                .assign(status_date=lambda g: g["status_date"].dt.strftime("%Y-%m-%d"))
                .to_dict(orient="records"),
            }

            result.append(item)

        body = {"items": result}
        return func.HttpResponse(
            json.dumps(body), mimetype="application/json", status_code=200
        )

    except Exception as e:
        logging.exception("Error in inventory_stats")
        body = {"error": str(e)}
        return func.HttpResponse(
            json.dumps(body), mimetype="application/json", status_code=500
        )
```

### 3.4. Test locally

Start Functions:

```bash
func start
```

In another terminal:

```bash
curl "http://localhost:7071/api/inventory_stats?key=y1sp001"
```

You should see JSON with `items`, KPIs, and `time_series`.

### 3.5. Deploy to Azure

1. In the Azure Portal, create a **Function App** (e.g. `azfunction`).
2. In the Function App → **Configuration → Application settings**, add:

   - `BLOB_CONNECTION_STRING`
   - `BLOB_CONTAINER = inventory-data`
   - `BLOB_NAME = inventory.csv`

3. Publish from your local project:

```bash
func azure functionapp publish azfunction
```

4. Test in the cloud:

```bash
curl "https://azfunction.azurewebsites.net/api/inventory_stats?key=y1sp001"
```

---

## 4. Microsoft AI Foundry – Project & Model Deployment

### 4.1. Create Project & Model Deployment

1. Go to **Microsoft AI Foundry**.
2. Create a **Project** (e.g. `sample`).
3. Inside the project, create a **Model deployment**:
   - Model: `gpt-4.1-mini` (or similar)
   - Deployment name (e.g.): `ReAct-Tool-Calling-gpt-4.1-mini-inventory`

### 4.2. Collect Key Values

From your Foundry project, note:

- `PROJECT_ENDPOINT`, for example:

  ```text
  https://sample.services.ai.azure.com/api/projects/sample
  ```

- `MODEL_DEPLOYMENT_NAME`:

  ```text
  ReAct-Tool-Calling-gpt-4.1-mini-inventory
  ```

We will use these in the CLI project.

---

## 5. Local CLI Project – `mfagent_inventory`

This project will:

- Call the Function App → `inventory_stats`.
- Create an LLM agent in Foundry with the `get_inventory_kpis` tool.
- Send prompts from the console.

### 5.1. Folder Layout

Recommended structure:

```text
tssdev/
  azfuncinventory/           # Azure Functions project
  mfagent_inventory/         # CLI & agent client
```

### 5.2. Create the project and venv

```bash
mkdir mfagent_inventory
cd mfagent_inventory

python3 -m venv .venv
source .venv/bin/activate

pip install azure-ai-projects azure-identity azure-ai-agents requests python-dotenv
pip freeze > requirements.txt
```

### 5.3. `.env` file

Create `.env`:

```env
PROJECT_ENDPOINT=""
MODEL_DEPLOYMENT_NAME=""
FUNCTION_APP_URL=""

# Will be filled after creating the agent
AGENT_ID=""
```

> Commit a `.env.example` to GitHub, but **never** the real `.env`.

---

## 6. `agent_inventory.py` – Tools, Agent, and CLI

Create `agent_inventory.py` with the following content:

```python
import os
import argparse
from dotenv import load_dotenv

import requests
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import FunctionTool

load_dotenv()

PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
MODEL_DEPLOYMENT_NAME = os.environ["MODEL_DEPLOYMENT_NAME"]
FUNCTION_APP_URL = os.environ["FUNCTION_APP_URL"]
DEFAULT_AGENT_ID = os.environ.get("AGENT_ID", "")


# -------------------------------------------------------
# Tool: calls the Azure Function inventory_stats
# -------------------------------------------------------
def get_inventory_kpis(key: str | None = None) -> str:
    params = {"key": key} if key else {}
    resp = requests.get(FUNCTION_APP_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.text  # JSON string


# -------------------------------------------------------
# Create agent in Foundry (one-time)
# -------------------------------------------------------
def create_agent() -> str:
    client = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential()
    )

    # Register Python functions as tools
    user_functions = {get_inventory_kpis}
    function_tool = FunctionTool(functions=user_functions)

    agent = client.agents.create_agent(
        model=MODEL_DEPLOYMENT_NAME,
        name="inventory-react-agent",
        instructions=(
            "You are an inventory analytics assistant.\n"
            "Use the tool get_inventory_kpis to fetch inventory KPIs and\n"
            "daily time series from a CSV stored in Blob Storage.\n\n"
            "Always follow a Reason + Act pattern:\n"
            "1) Reason about what data you need.\n"
            "2) Call the tool whenever you require real inventory data.\n"
            "3) Produce Markdown tables, KPIs, and chart descriptions.\n"
        ),
        tools=function_tool.definitions,
    )

    print(f"Created agent: {agent.id}")
    print("Copy this ID into your .env as AGENT_ID")
    return agent.id


# -------------------------------------------------------
# Chat with existing agent
# -------------------------------------------------------
def chat_with_agent(agent_id: str, question: str) -> None:
    client = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential()
    )

    # Enable auto tool-calling with our Python function
    client.agents.enable_auto_tool_calls(functions=[get_inventory_kpis])

    # 1. Create thread
    thread = client.agents.threads.create()
    print(f"Thread: {thread.id}")

    # 2. Add user message
    client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content=question
    )

    # 3. Run agent with ReAct + tool-calling
    run = client.agents.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent_id
    )
    print(f"Run finished with status: {run.status}")

    # 4. List messages and print assistant text nicely
    messages = client.agents.messages.list(thread_id=thread.id)

    print("\n===== ASSISTANT RESPONSE =====\n")
    for m in messages:
        if m.role == "assistant":
            for c in m.content:
                if c.type == "text":
                    # Some SDKs use c.text.value, others c.text directly
                    text = getattr(c.text, "value", c.text)
                    print(text)


# -------------------------------------------------------
# CLI entry point
# -------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Inventory LLM Agent CLI")

    parser.add_argument(
        "--create-agent",
        action="store_true",
        help="Create the agent in Foundry (one-time)"
    )

    parser.add_argument(
        "--chat",
        type=str,
        help="Send a question to the agent"
    )

    parser.add_argument(
        "--agent-id",
        type=str,
        help="Override agent ID (otherwise uses AGENT_ID from .env)"
    )

    args = parser.parse_args()

    if args.create-agent:
        create_agent()
        return

    if args.chat:
        agent_id = args.agent_id or DEFAULT_AGENT_ID
        if not agent_id:
            raise RuntimeError(
                "No AGENT_ID found. Use --agent-id or set AGENT_ID in .env"
            )
        chat_with_agent(agent_id, args.chat)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
```

---

## 7. Create the Agent and Test from Console

### 7.1. Login to Azure (for DefaultAzureCredential)

```bash
az login
```

### 7.2. Create the Agent (one-time)

```bash
cd mfagent_inventory
source .venv/bin/activate

python agent_inventory.py --create-agent
```

Output example:

```text
Created agent: asst_01HXZEXAMPLE123
Copy this ID into your .env as AGENT_ID
```

Update `.env`:

```env
AGENT_ID="asst_01HXZEXAMPLE123"
```

### 7.3. Run a Chat

```bash
python agent_inventory.py --chat "Give me KPIs for item y1sp001"
```

Example output:

```text
Thread: thread_01t6XRCHEn3QhKtIxC2QZo1K
Run finished with status: RunStatus.COMPLETED

===== ASSISTANT RESPONSE =====

Here are the KPIs for item y1sp001 (tintaxyz) for the current month (November 2025):

- Total Sales: 2200 units
- Average Daily Sales: 550 units per day
- Minimum Inventory Level: 78 units
- Maximum Inventory Level: 94 units
- Days with Inventory Below 100 Units: 4 days

The time series data shows daily inventory and sales for the first 4 days of the month. 
Let me know if you want a breakdown or a chart specification.
```

You can ask for tables and chart specs:

```bash
python agent_inventory.py \
  --chat "For key y1sp001, give me KPIs, a Markdown table of date/inventory/sales, and a JSON chart_spec for inventory over time."
```

---

## 8. Common Errors & Fixes

### 8.1. `HTTP transport has already been closed`

- **Cause**: Reusing a client created in a `with` block or mixing create-agent calls and runs incorrectly.
- **Fix**: Do not use `with AIProjectClient(...)`; create the agent once (`--create-agent`) and reuse `AGENT_ID`.

### 8.2. `Invalid 'assistant_id': 'Give me KPIs...'`

- **Cause**: Swapped parameters (prompt passed where agent ID should be).
- **Fix**: Ensure `chat_with_agent(agent_id, question)` signature & call order are correct.

### 8.3. `Function 'get_inventory_kpis' not found. Provide this function to enable_auto_tool_calls`

- **Cause**: Agent knows the tool *by name*, but the SDK isn't given the Python callback.
- **Fix**:

  ```python
  client.agents.enable_auto_function_calls(tools=[get_inventory_kpis])
  ```

### 8.4. Assistant output printed as Python structures

- **Fix**: Use:

  ```python
  text = getattr(c.text, "value", c.text)
  print(text)
  ```

---

## 9. Suggested Repository Structure

```text
project-root/
  README.md                    # this document
  azfuncinventory/
    function_app.py
    requirements.txt
    local.settings.json        # without real secrets
  mfagent_inventory/
    agent_inventory.py
    requirements.txt
    .env.example               # template for environment variables
```

Example `.env.example`:

```env
PROJECT_ENDPOINT="<your-project-endpoint>"
MODEL_DEPLOYMENT_NAME="ReAct-Tool-Calling-gpt-4.1-mini-inventory"
FUNCTION_APP_URL="https://<your-function-app>.azurewebsites.net/api/inventory_stats"
AGENT_ID="<agent-id-created-with-cli>"
```

---

