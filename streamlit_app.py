# streamlit_app.py
# Brazilian Olist E-Commerce Analytics Dashboard
# Built on top of our custom CSV parser + DataFrame implementation (no pandas).

from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import streamlit as st
import matplotlib.pyplot as plt

from dataframe import (
    parse_csv,
    DataFrame,
    add_category_name_to_order_items,
    top_categories_by_revenue,
)

DATA_DIR = Path("data")  


# helper functions 

def df_to_dict(df: DataFrame, columns: List[str] | None = None) -> Dict[str, List[Any]]:
    #convert dataframe into dict of lists 
    if columns is None:
        columns = df.columns
    return {col: df._data[col] for col in columns}


def parse_timestamp(value: Any) -> datetime | None:
    #parse timestamp string into datetime object 
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


@st.cache_data
def load_datasets() -> Dict[str, DataFrame]:
    """Load all Olist CSVs with our custom parser (cached by Streamlit)."""
    orders = parse_csv(DATA_DIR / "olist_orders_dataset.csv")
    customers = parse_csv(DATA_DIR / "olist_customers_dataset.csv")
    order_items = parse_csv(DATA_DIR / "olist_order_items_dataset.csv")
    payments = parse_csv(DATA_DIR / "olist_order_payments_dataset.csv")
    reviews = parse_csv(DATA_DIR / "olist_order_reviews_dataset.csv")
    products = parse_csv(DATA_DIR / "olist_products_dataset.csv")
    product_cat = parse_csv(DATA_DIR / "product_category_name_translation.csv")

    return {
        "orders": orders,
        "customers": customers,
        "order_items": order_items,
        "payments": payments,
        "reviews": reviews,
        "products": products,
        "product_cat": product_cat,
    }


# customer insights! 

def view_customer_insights(datasets: Dict[str, DataFrame]):
    st.header("Customer Insights")

    orders = datasets["orders"]
    customers = datasets["customers"]

    # Join orders + customers on customer_id
    orders_customers = orders.join(
        customers,
        left_on="customer_id",
        right_on="customer_id",
        how="inner",
    )

    # Group by state, number of orders
    by_state = orders_customers.groupby(["customer_state"]).agg(
        {"order_id": "count"}
    )
    states = by_state._data["customer_state"]
    order_counts = by_state._data["order_id"]

    st.subheader("Orders by State")
    state_chart = {
        "customer_state": states,
        "num_orders": order_counts,
    }
    if states:
        st.bar_chart(state_chart, x="customer_state", y="num_orders")
    st.dataframe(state_chart)


# product analytics by category name 

def view_product_analytics(datasets: Dict[str, DataFrame]):
    st.header("Product Analytics")

    order_items = datasets["order_items"]
    products = datasets["products"]
    product_cat = datasets["product_cat"]

    # enrich order_items with category names 
    full = add_category_name_to_order_items(order_items, products, product_cat)

    # choose category column (prefer English)
    if "product_category_name_english" in full.columns:
        cat_col = "product_category_name_english"
    else:
        # fallback to whatever contains "product_category_name"
        from dataframe import _find_col_by_substring
        cat_col = _find_col_by_substring(full.columns, "product_category_name")

    # group by category: quantity (count of order_id), revenue (sum price), avg freight
    grouped = full.groupby([cat_col]).agg(
        {
            "order_id": "count",
            "price": "sum",
            "freight_value": "mean",
        }
    )

    cat_names = grouped._data[cat_col]
    quantities = grouped._data["order_id"]
    revenues = grouped._data["price"]
    avg_freight = grouped._data["freight_value"]

    # build list and filter out None categories
    rows = [
        (c, r, q, f)
        for c, r, q, f in zip(cat_names, revenues, quantities, avg_freight)
        if c is not None
    ]

    # Sort by revenue descending
    rows.sort(key=lambda x: x[1] if x[1] is not None else 0.0, reverse=True)

    top_n = st.slider("Number of top categories by revenue", 5, 50, 20)
    top_rows = rows[:top_n]

    if not top_rows:
        st.write("No product category data available.")
        return

    cat_list = [r[0] for r in top_rows]
    revenue_list = [r[1] for r in top_rows]
    qty_list = [r[2] for r in top_rows]

    bar_data = {
        "product_category": cat_list,
        "total_revenue": revenue_list,
        "quantity_sold": qty_list,
    }

    st.subheader("Top Product Categories by Revenue")
    st.bar_chart(bar_data, x="product_category", y="total_revenue")
    st.dataframe(bar_data)

    st.subheader("Average Freight Cost for Top Categories ")
    freight_sample = {
        "product_category": cat_list,
        "avg_freight_value": [r[3] for r in top_rows],
    }
    st.dataframe(freight_sample)


# payment trends

def view_payment_trends(datasets: Dict[str, DataFrame]):
    st.header("Payment Trends")

    payments = datasets["payments"]

    # payment type distribution
    pt_grp = payments.groupby(["payment_type"]).agg(
        {"payment_value": "count"}
    )
    ptypes = pt_grp._data["payment_type"]
    counts = pt_grp._data["payment_value"]

    chart_data = {
        "payment_type": ptypes,
        "num_payments": counts,
    }

    st.subheader("Number of Payments by Type ")
    if ptypes:
        st.bar_chart(chart_data, x="payment_type", y="num_payments")
    st.dataframe(chart_data)

    # Pie chart using matplotlib
    st.subheader("Payment Type Share")
    fig, ax = plt.subplots()
    labels = [t for t in ptypes if t is not None]
    sizes = [counts[i] for i, t in enumerate(ptypes) if t is not None]
    if labels and sizes:
        ax.pie(sizes, labels=labels, autopct="%1.1f%%")
        ax.axis("equal")
        st.pyplot(fig)
    else:
        st.write("No valid payment types for pie chart.")

    # Average payment value by type
    pt_value_grp = payments.groupby(["payment_type"]).agg(
        {"payment_value": "mean"}
    )
    v_ptypes = pt_value_grp._data["payment_type"]
    avg_values = pt_value_grp._data["payment_value"]

    value_data = {
        "payment_type": v_ptypes,
        "avg_payment_value": avg_values,
    }

    st.subheader("Average Payment Value by Type ")
    if v_ptypes:
        st.bar_chart(value_data, x="payment_type", y="avg_payment_value")
    st.dataframe(value_data)


# review explorer and heatmap

def view_review_explorer(datasets: Dict[str, DataFrame]):
    st.header("Review Explorer")

    reviews = datasets["reviews"]
    payments = datasets["payments"]

    # Review score distribution
    rs_grp = reviews.groupby(["review_score"]).agg(
        {"review_id": "count"}
    )
    scores = rs_grp._data["review_score"]
    counts = rs_grp._data["review_id"]

    chart_data = {
        "review_score": scores,
        "num_reviews": counts,
    }

    st.subheader("Review Score Distribution ")
    if scores:
        st.bar_chart(chart_data, x="review_score", y="num_reviews")
    st.dataframe(chart_data)

    
    st.subheader("Review Score vs Payment Type ")

    # Join reviews + payments on order_id
    joined = reviews.join(
        payments,
        left_on="order_id",
        right_on="order_id",
        how="inner",
    )

    j_scores = joined._data.get("review_score", [])
    j_ptypes = joined._data.get("payment_type", [])

    combo_counts: Dict[tuple, int] = {}
    score_set = set()
    type_set = set()
    for s, t in zip(j_scores, j_ptypes):
        if s is None or t is None:
            continue
        key = (s, t)
        combo_counts[key] = combo_counts.get(key, 0) + 1
        score_set.add(s)
        type_set.add(t)

    if not combo_counts:
        st.write("Not enough data to build heatmap.")
    else:
        sorted_scores = sorted(score_set)
        sorted_types = sorted(type_set)

        matrix: List[List[int]] = []
        for s in sorted_scores:
            row_vals = []
            for t in sorted_types:
                row_vals.append(combo_counts.get((s, t), 0))
            matrix.append(row_vals)

        fig, ax = plt.subplots()
        cax = ax.imshow(matrix, aspect="auto")
        ax.set_xticks(range(len(sorted_types)))
        ax.set_xticklabels(sorted_types, rotation=45, ha="right")
        ax.set_yticks(range(len(sorted_scores)))
        ax.set_yticklabels(sorted_scores)
        ax.set_xlabel("Payment Type")
        ax.set_ylabel("Review Score")
        fig.colorbar(cax, ax=ax, label="Count")
        st.pyplot(fig)


# filtered product explorer 

def view_filtered_products(datasets: Dict[str, DataFrame]):
    st.header("Filtered Product Explorer")

    orders = datasets["orders"]
    customers = datasets["customers"]
    order_items = datasets["order_items"]
    products = datasets["products"]
    product_cat = datasets["product_cat"]

    # orders + customers -> state per order
    orders_customers = orders.join(
        customers,
        left_on="customer_id",
        right_on="customer_id",
        how="inner",
    )
    # order_items + orders_customers -> price + state
    full = order_items.join(
        orders_customers,
        left_on="order_id",
        right_on="order_id",
        how="inner",
    )

    
    full_cat = add_category_name_to_order_items(full, products, product_cat)

    # choose category column 
    if "product_category_name_english" in full_cat.columns:
        cat_col = "product_category_name_english"
    else:
        from dataframe import _find_col_by_substring
        cat_col = _find_col_by_substring(full_cat.columns, "product_category_name")

    # state filter
    states = sorted(set(s for s in full_cat._data.get("customer_state", []) if s is not None))
    state_options = ["All"] + states
    selected_state = st.selectbox("Filter by customer_state:", state_options)

    # price filter
    prices_all = [
        p for p in full_cat._data.get("price", [])
        if isinstance(p, (int, float))
    ]
    if prices_all:
        min_price = float(min(prices_all))
        max_price = float(max(prices_all))
    else:
        min_price, max_price = 0.0, 0.0

    price_min, price_max = st.slider(
        "Filter by item price range",
        min_value=float(min_price),
        max_value=float(max_price),
        value=(float(min_price), float(max_price)),
    )

    # filter rows based on state + price
    def predicate(row: Dict[str, Any]) -> bool:
        if selected_state != "All" and row.get("customer_state") != selected_state:
            return False
        price = row.get("price")
        if not isinstance(price, (int, float)):
            return False
        if price < price_min or price > price_max:
            return False
        return True

    filtered = full_cat.filter_rows(predicate)

    st.write(f"Filtered rows: {len(filtered)}")

    if len(filtered) == 0:
        st.write("No data for the selected filters.")
        return

    # group by category: count items, sum price
    grouped = filtered.groupby([cat_col]).agg(
        {
            "order_id": "count",
            "price": "sum",
        }
    )
    cats = grouped._data[cat_col]
    counts = grouped._data["order_id"]
    revenues = grouped._data["price"]

    rows = [
        (c, cnt, rev)
        for c, cnt, rev in zip(cats, counts, revenues)
        if c is not None
    ]

    # sort by count (most sold categories)
    rows.sort(key=lambda x: x[1] if x[1] is not None else 0, reverse=True)

    top_n = st.slider("Number of top categories to show", 5, 50, 20)
    top_rows = rows[:top_n]

    if not top_rows:
        st.write("No categories after filtering.")
        return

    cat_list = [r[0] for r in top_rows]
    count_list = [r[1] for r in top_rows]
    rev_list = [r[2] for r in top_rows]

    chart_data = {
        "product_category": cat_list,
        "num_items_sold": count_list,
        "total_revenue": rev_list,
    }

    st.subheader("Most Sold Categories ")
    st.bar_chart(chart_data, x="product_category", y="num_items_sold")

    st.subheader("Top Categories Table")
    st.dataframe(chart_data)


# time series order and revenu over time 

def view_time_series(datasets: Dict[str, DataFrame]):
    st.header("Time Series Orders & Revenue ")

    orders = datasets["orders"]
    order_items = datasets["order_items"]

    
    items_orders = order_items.join(
        orders,
        left_on="order_id",
        right_on="order_id",
        how="inner",
    )

    # build metrics per year, month
    metrics: Dict[tuple, Dict[str, Any]] = {}

    for i in range(len(items_orders)):
        row = items_orders.row(i)
        ts = parse_timestamp(row.get("order_purchase_timestamp"))
        if ts is None:
            continue

        year = ts.year
        month = ts.month
        key = (year, month)

        price = row.get("price")
        if not isinstance(price, (int, float)):
            price = 0.0

        m = metrics.setdefault(key, {"revenue": 0.0, "order_ids": set()})
        m["revenue"] += price
        m["order_ids"].add(row.get("order_id"))

    if not metrics:
        st.write("No time series data available.")
        return

    all_years = sorted({year for (year, _) in metrics.keys()})
    selected_years = st.multiselect(
        "Select year(s) to display",
        options=all_years,
        default=all_years,
    )
    if not selected_years:
        st.write("Please select at least one year.")
        return

    # filter keys by selected years and sort chronologically
    filtered_keys = [
        (y, m) for (y, m) in metrics.keys() if y in selected_years
    ]
    filtered_keys.sort()

    periods: List[str] = []
    order_counts: List[int] = []
    revenues: List[float] = []

    for (year, month) in filtered_keys:
        label = f"{year:04d}-{month:02d}"
        periods.append(label)
        order_counts.append(len(metrics[(year, month)]["order_ids"]))
        revenues.append(metrics[(year, month)]["revenue"])

    # revenue line chart
    st.subheader("Revenue Over Time ")
    revenue_data = {
        "period": periods,
        "revenue": revenues,
    }
    if periods:
        st.line_chart(revenue_data, x="period", y="revenue")
    st.dataframe(revenue_data)

    # orders line chart
    st.subheader("Number of Orders Over Time ")
    orders_data = {
        "period": periods,
        "num_orders": order_counts,
    }
    if periods:
        st.line_chart(orders_data, x="period", y="num_orders")
    st.dataframe(orders_data)


# main streamlit app 

def main():
    st.title("Brazilian Olist E-Commerce Analytics Dashboard")

    st.sidebar.header("Views")
    view = st.sidebar.radio(
        "Select a view",
        [
            "Customer Insights",
            "Product Analytics",
            "Payment Trends",
            "Review Explorer",
            "Filtered Product Explorer",
            "Time Series (Orders & Revenue)",
        ],
    )

    datasets = load_datasets()

    if view == "Customer Insights":
        view_customer_insights(datasets)
    elif view == "Product Analytics":
        view_product_analytics(datasets)
    elif view == "Payment Trends":
        view_payment_trends(datasets)
    elif view == "Review Explorer":
        view_review_explorer(datasets)
    elif view == "Filtered Product Explorer":
        view_filtered_products(datasets)
    elif view == "Time Series (Orders & Revenue)":
        view_time_series(datasets)


if __name__ == "__main__":
    main()
