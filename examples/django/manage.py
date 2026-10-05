"""Single-file Django project with an N+1 query. No Profyle code: run it with
`profyle run`.

    profyle run python manage.py runserver          # WSGI
    profyle run uvicorn manage:application          # ASGI
"""

import sqlite3
import sys
import time

from django.conf import settings

settings.configure(
    DEBUG=True,
    SECRET_KEY="example-only",
    ROOT_URLCONF=__name__,
    ALLOWED_HOSTS=["*"],
    MIDDLEWARE=["django.middleware.common.CommonMiddleware"],
)

from django.core.asgi import get_asgi_application  # noqa: E402
from django.http import JsonResponse  # noqa: E402
from django.urls import path  # noqa: E402

db = sqlite3.connect(":memory:", check_same_thread=False)
db.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
db.executemany("INSERT INTO customers VALUES (?, ?)", [(i, f"customer {i}") for i in range(100)])


def get_customer(customer_id: int) -> str:
    time.sleep(0.002)  # stands in for the network round trip to a real database
    return db.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()[0]


def list_orders(request):
    orders = [{"order": i, "customer": get_customer(i)} for i in range(50)]
    return JsonResponse(orders, safe=False)


urlpatterns = [path("orders", list_orders)]
application = get_asgi_application()

if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
