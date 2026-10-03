"""A framework-less ASGI app with an N+1 query, standing in for Litestar, Quart or any
other ASGI framework. No Profyle code: run it with `profyle run`.

    profyle run uvicorn app:app --reload
"""

import json
import sqlite3
import time

db = sqlite3.connect(":memory:", check_same_thread=False)
db.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
db.executemany("INSERT INTO customers VALUES (?, ?)", [(i, f"customer {i}") for i in range(100)])


def get_customer(customer_id: int) -> str:
    time.sleep(0.002)  # stands in for the network round trip to a real database
    return db.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()[0]


async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    orders = [{"order": i, "customer": get_customer(i)} for i in range(50)]
    body = json.dumps(orders).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})
