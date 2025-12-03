import logging
import json
import os
from io import StringIO

import azure.functions as func
from azure.storage.blob import BlobServiceClient
import pandas as pd

# Create the FunctionApp object (v2 programming model)
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Environment variables for blob access
BLOB_CONNECTION_STRING = os.environ["BLOB_CONNECTION_STRING"]
BLOB_CONTAINER = os.environ.get("BLOB_CONTAINER", "datasets")
BLOB_NAME = os.environ.get("BLOB_NAME", "gestion_demanda.csv")


@app.route(route="inventory_stats", methods=["GET"])
def inventory_stats(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP GET /api/inventory_stats?key=<sku>

    Reads the inventory CSV from Blob Storage, optionally filters by SKU key,
    computes KPIs and a time series usable for graphs, and returns JSON.
    """
    logging.info("inventory_stats HTTP trigger (v2) processed a request.")

    try:
        key = req.params.get("key")  # optional filter by SKU

        # Connect to Blob Storage
        blob_service = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
        blob_client = blob_service.get_blob_client(
            container=BLOB_CONTAINER,
            blob=BLOB_NAME,
        )

        # Download CSV
        csv_bytes = blob_client.download_blob().readall()
        df = pd.read_csv(StringIO(csv_bytes.decode("utf-8")))

        # Parse date for sorting if present
        if "status_date" in df.columns:
            df["status_date"] = pd.to_datetime(df["status_date"], format="%m-%d-%Y")

        # Filter by key if provided
        if key:
            df = df[df["key"] == key]

        if df.empty:
            body = {"items": [], "message": "No data found for given filters"}
            return func.HttpResponse(
                json.dumps(body),
                mimetype="application/json",
                status_code=200,
            )

        result = []

        # Group by SKU/key
        for sku, group in df.groupby("key"):
            group = group.sort_values("status_date")

            total_sales = float(group["sales"].sum())
            avg_daily_sales = float(group["sales"].mean())
            min_inventory = float(group["current_status_inventory"].min())
            max_inventory = float(group["current_status_inventory"].max())
            days_below_100 = int((group["current_status_inventory"] < 100).sum())

            item = {
                "key": sku,
                "key_name": group["key_name"].iloc[0],
                "current_month": int(group["current_month"].iloc[0]),
                "total_sales": total_sales,
                "avg_daily_sales": avg_daily_sales,
                "min_inventory": min_inventory,
                "max_inventory": max_inventory,
                "days_below_100": days_below_100,
                # Time series for charts
                "time_series": group[
                    ["status_date", "current_status_inventory", "sales"]
                ]
                .assign(
                    status_date=lambda g: g["status_date"].dt.strftime("%Y-%m-%d")
                )
                .to_dict(orient="records"),
            }
            result.append(item)

        body = {"items": result}
        return func.HttpResponse(
            json.dumps(body),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as e:
        logging.exception("Error processing inventory_stats function (v2 model)")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
        )
