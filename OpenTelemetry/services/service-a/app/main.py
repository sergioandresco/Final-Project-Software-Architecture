"""service-a — Orders API.

Punto de entrada del flujo: recibe la orden, valida, reserva stock en service-b
(HTTP, propagando W3C traceparent), calcula el total y persiste la orden.

Traza resultante de POST /api/orders:

  service-a  POST /api/orders                      (SERVER, auto)
  ├── orders.validate                              (custom)
  ├── orders.reserve_inventory                     (custom)
  │   └── POST                                     (CLIENT, auto httpx)
  │       └── service-b POST /api/products/{id}/reserve  (SERVER, auto)
  │           └── inventory.reserve_stock          (custom)
  │               ├── SELECT ... FOR UPDATE        (DB, auto)
  │               ├── UPDATE products              (DB, auto)
  │               └── INSERT stock_movements       (DB, auto)
  ├── orders.calculate_total                       (custom)
  └── INSERT orders                                (DB, auto)
"""

import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "shared"))  # ejecución local sin Docker

from telemetry import (  # noqa: E402
    FASTAPI_NATIVE_TELEMETRY_OFF,
    current_trace_id,
    instrument_fastapi,
    instrument_httpx_client,
    instrument_sqlalchemy,
    setup_telemetry,
    shutdown_telemetry,
    untraced,
)

setup_telemetry()

import httpx  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from opentelemetry import baggage, context, metrics, trace  # noqa: E402
from opentelemetry.trace import Status, StatusCode  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from .db import Order, SessionLocal, engine, init_db  # noqa: E402

log = logging.getLogger("service-a")
tracer = trace.get_tracer("service-a.orders")
meter = metrics.get_meter("service-a.orders")

orders_counter = meter.create_counter("orders.created", unit="{order}", description="Órdenes procesadas por estado")
order_value = meter.create_histogram("orders.value", unit="USD", description="Valor total de cada orden")
inventory_latency = meter.create_histogram(
    "orders.inventory.call.duration", unit="s", description="Latencia de la llamada a service-b"
)

SERVICE_B_URL = os.getenv("SERVICE_B_URL", "http://localhost:8001")
http_client = httpx.Client(
    base_url=SERVICE_B_URL,
    timeout=httpx.Timeout(5.0),
    limits=httpx.Limits(max_connections=200, max_keepalive_connections=100),
)
instrument_httpx_client(http_client)


class OrderRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=64)
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100)


def _init_db_with_retry(attempts: int = 30) -> None:
    for attempt in range(1, attempts + 1):
        try:
            init_db()
            return
        except DBAPIError as exc:  # BD no lista o carrera de inicialización entre réplicas
            log.warning("Base de datos no disponible, reintentando", extra={"attempt": attempt, "error": str(exc)})
            time.sleep(2)
    raise RuntimeError("No fue posible inicializar la base de datos")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _init_db_with_retry()
    log.info("service-a listo", extra={"service_b_url": SERVICE_B_URL})
    yield
    http_client.close()
    shutdown_telemetry()


app = FastAPI(
    title="service-a (orders)", version="1.0.0", lifespan=lifespan, telemetry=FASTAPI_NATIVE_TELEMETRY_OFF
)
instrument_fastapi(app)
instrument_sqlalchemy(engine)


@app.middleware("http")
async def trace_id_header(request: Request, call_next):
    """Devuelve el trace_id al cliente: facilita buscar la traza en Jaeger/Grafana."""
    response = await call_next(request)
    trace_id = current_trace_id()
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return response


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    with untraced(), engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ready"}


def _order_dto(o: Order) -> dict:
    return {
        "id": o.id,
        "customer_id": o.customer_id,
        "product_id": o.product_id,
        "quantity": o.quantity,
        "unit_price": float(o.unit_price),
        "discount": float(o.discount),
        "total": float(o.total),
        "status": o.status,
        "trace_id": o.trace_id,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def _calculate_total(unit_price: float, quantity: int) -> tuple[float, float]:
    """Regla de negocio: 5% de descuento desde 10 unidades, 10% desde 50."""
    with tracer.start_as_current_span("orders.calculate_total") as span:
        subtotal = unit_price * quantity
        rate = 0.10 if quantity >= 50 else 0.05 if quantity >= 10 else 0.0
        discount = round(subtotal * rate, 2)
        total = round(subtotal - discount, 2)
        span.set_attributes({"order.subtotal": subtotal, "order.discount_rate": rate, "order.total": total})
        return discount, total


def _reserve_inventory(order_id: str, body: OrderRequest) -> dict:
    with tracer.start_as_current_span("orders.reserve_inventory") as span:
        span.set_attribute("peer.service", "service-b")
        started = time.perf_counter()
        try:
            resp = http_client.post(
                f"/api/products/{body.product_id}/reserve",
                json={"quantity": body.quantity, "order_ref": order_id},
            )
        except httpx.HTTPError as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "service-b no disponible"))
            log.error("Error de red llamando a service-b", extra={"order_id": order_id, "error": str(exc)})
            raise HTTPException(status_code=502, detail="Inventario no disponible") from exc
        finally:
            inventory_latency.record(time.perf_counter() - started)

        span.set_attribute("inventory.response_status", resp.status_code)
        if resp.status_code == 409:
            raise HTTPException(status_code=409, detail="Stock insuficiente")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        if resp.status_code >= 500:
            span.set_status(Status(StatusCode.ERROR, f"service-b respondió {resp.status_code}"))
            log.error("service-b respondió con error", extra={"order_id": order_id, "status": resp.status_code})
            raise HTTPException(status_code=502, detail="Error en el servicio de inventario")
        return resp.json()


@app.post("/api/orders", status_code=201)
def create_order(body: OrderRequest):
    order_id = str(uuid.uuid4())
    # Baggage: viaja junto al traceparent y queda disponible en service-b.
    token = context.attach(baggage.set_baggage("customer.id", body.customer_id))
    try:
        span = trace.get_current_span()
        span.set_attributes({"order.id": order_id, "customer.id": body.customer_id})

        with tracer.start_as_current_span("orders.validate") as vspan:
            vspan.set_attributes({"order.product_id": body.product_id, "order.quantity": body.quantity})
            if body.customer_id.startswith("blocked-"):
                vspan.set_status(Status(StatusCode.ERROR, "cliente bloqueado"))
                orders_counter.add(1, {"status": "rejected"})
                raise HTTPException(status_code=422, detail="Cliente bloqueado")

        try:
            reservation = _reserve_inventory(order_id, body)
        except HTTPException as exc:
            orders_counter.add(1, {"status": "failed" if exc.status_code >= 500 else "rejected"})
            raise

        discount, total = _calculate_total(reservation["unit_price"], body.quantity)

        order = Order(
            id=order_id,
            customer_id=body.customer_id,
            product_id=body.product_id,
            quantity=body.quantity,
            unit_price=reservation["unit_price"],
            discount=discount,
            total=total,
            status="CONFIRMED",
            trace_id=current_trace_id(),
        )
        with SessionLocal() as session, session.begin():
            session.add(order)

        orders_counter.add(1, {"status": "confirmed"})
        order_value.record(total)
        log.info(
            "Orden creada",
            extra={"order_id": order_id, "customer_id": body.customer_id, "product_id": body.product_id, "total": total},
        )
        return _order_dto(order)
    finally:
        context.detach(token)


@app.get("/api/orders/{order_id}")
def get_order(order_id: str):
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        return _order_dto(order)


@app.get("/api/orders")
def list_orders(limit: int = 20):
    with SessionLocal() as session:
        orders = session.scalars(select(Order).order_by(Order.created_at.desc()).limit(min(limit, 100))).all()
        return [_order_dto(o) for o in orders]


@app.get("/api/catalog")
def catalog(limit: int = 20):
    """Consulta el catálogo en service-b (segunda ruta de propagación de contexto)."""
    try:
        resp = http_client.get("/api/products", params={"limit": limit})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.error("No fue posible consultar el catálogo", extra={"error": str(exc)})
        raise HTTPException(status_code=502, detail="Catálogo no disponible") from exc
    return resp.json()
