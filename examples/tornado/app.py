"""Tornado app with an N+1 query. No Profyle code: run it with `profyle run`.

profyle run python app.py 8888                                  # Tornado's server
profyle run gunicorn -k tornado -b 127.0.0.1:8888 app:app       # gunicorn
"""

import sqlite3
import sys
import time

import tornado.ioloop
import tornado.web

db = sqlite3.connect(":memory:", check_same_thread=False)
db.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
db.executemany("INSERT INTO customers VALUES (?, ?)", [(i, f"customer {i}") for i in range(100)])


def get_customer(customer_id: int) -> str:
    time.sleep(0.002)  # stands in for the network round trip to a real database
    return db.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()[0]


class OrdersHandler(tornado.web.RequestHandler):
    def get(self):
        orders = [{"order": i, "customer": get_customer(i)} for i in range(50)]
        self.write({"orders": orders})


app = tornado.web.Application([(r"/orders", OrdersHandler)])

if __name__ == "__main__":
    app.listen(int(sys.argv[1]) if len(sys.argv) > 1 else 8888, address="127.0.0.1")
    tornado.ioloop.IOLoop.current().start()
