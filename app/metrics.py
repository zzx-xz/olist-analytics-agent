"""Business metric definitions used to ground agent answers.

Review these definitions against the SQL from the original Olist analysis before
using the project in a portfolio or interview.
"""

METRICS = [
    {
        "name": "GMV",
        "definition": "Sum of payment_value in payments, following the original project metric.",
        "tables": ["payments"],
        "notes": (
            "Do not substitute order_items.price; that field is product sales "
            "amount and has a different grain. GMV is not profit."
        ),
    },
    {
        "name": "Product sales amount",
        "definition": "Sum of order_items.price, following the original product and seller analyses.",
        "tables": ["order_items"],
        "notes": (
            "This measures product item prices, not payment GMV. It excludes "
            "freight_value and includes all order statuses unless the user asks otherwise."
        ),
    },
    {
        "name": "Order count",
        "definition": "Count of distinct order_id values in orders.",
        "tables": ["orders"],
        "notes": (
            "State whether the answer includes all statuses or only delivered orders. "
            "For a customer-state filter, join orders to customers and count distinct "
            "orders.order_id. Do not join payments or order_items for a plain order "
            "count: they are one-to-many per order, and an order can lack a payment row."
        ),
    },
    {
        "name": "Repeat customer rate",
        "definition": (
            "Users with at least two distinct orders divided by users with at "
            "least one order, using customer_unique_id."
        ),
        "tables": ["orders", "customers"],
        "notes": (
            "Join orders.customer_id to customers.customer_id; use "
            "customers.customer_unique_id for identity. The original project "
            "counts orders across statuses, without a delivered-only filter."
        ),
    },
    {
        "name": "Late delivery rate",
        "definition": (
            "Delivered orders whose actual delivered timestamp is after the "
            "estimated delivery date, divided by delivered orders with both dates."
        ),
        "tables": ["orders"],
        "notes": (
            "Match the original project: require order_status = 'delivered' and "
            "non-null purchase, actual-delivery, and estimated-delivery timestamps."
        ),
    },
    {
        "name": "Average review score",
        "definition": "Average review_score in reviews.",
        "tables": ["reviews"],
        "notes": "Use the review rows available in the dataset; do not imply causality.",
    },
    {
        "name": "Negative review rate",
        "definition": "Orders with review_score <= 2 divided by orders with a non-null review score.",
        "tables": ["reviews"],
        "notes": "The original project defines a negative review as review_score <= 2.",
    },
]


def get_metric_definitions() -> list[dict[str, object]]:
    return METRICS
