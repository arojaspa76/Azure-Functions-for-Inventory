import matplotlib.pyplot as plt
import pandas as pd

# Data for each item
data = {
    "tintaxyz": {
        "dates": ["2025-11-01", "2025-11-02", "2025-11-03", "2025-11-04"],
        "inventory": [94, 91, 81, 78],
        "sales": [600, 300, 1000, 300],
    },
    "tintadef": {
        "dates": ["2025-11-01", "2025-11-02", "2025-11-03", "2025-11-04"],
        "inventory": [201, 101, 92, 91],
        "sales": [49, 100, 9, 1],
    },
    "tintaxyz23": {
        "dates": ["2025-11-01", "2025-11-02", "2025-11-03", "2025-11-04"],
        "inventory": [94, 91, 81, 78],
        "sales": [600, 300, 1000, 300],
    },
    "tintadef12": {
        "dates": ["2025-11-01", "2025-11-02", "2025-11-03", "2025-11-04"],
        "inventory": [201, 101, 92, 91],
        "sales": [49, 100, 9, 1],
    },
}

for item, item_data in data.items():
    df = pd.DataFrame({
        "Date": pd.to_datetime(item_data["dates"]),
        "Inventory": item_data["inventory"],
        "Sales": item_data["sales"],
    })
    
    fig, ax1 = plt.subplots(figsize=(10, 5))
    
    ax1.set_title(f"Inventory and Sales Over Time for {item}")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Inventory", color="tab:blue")
    ax1.plot(df["Date"], df["Inventory"], marker='o', color="tab:blue", label="Inventory")
    ax1.tick_params(axis='y', labelcolor="tab:blue")
    
    ax2 = ax1.twinx()
    ax2.set_ylabel("Sales", color="tab:red")
    ax2.plot(df["Date"], df["Sales"], marker='x', linestyle='--', color="tab:red", label="Sales")
    ax2.tick_params(axis='y', labelcolor="tab:red")

    fig.tight_layout()
    plt.show()