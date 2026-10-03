"""FastAPI app with an N+1 query. No Profyle code: run it with `profyle run`.

    profyle run uvicorn main:app --reload
"""

import sqlite3
import time

from fastapi import FastAPI

app = FastAPI()
db = sqlite3.connect(":memory:", check_same_thread=False)
db.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
db.executemany("INSERT INTO customers VALUES (?, ?)", [(i, f"customer {i}") for i in range(100)])


def get_customer(customer_id: int) -> str:
    time.sleep(0.002)  # stands in for the network round trip to a real database
    return db.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()[0]


@app.get("/orders")
def list_orders(limit: int = 50):
    return [{"order": i, "customer": get_customer(i)} for i in range(limit)]
