"""service-b — Inventory API.

Dueño de los productos y del stock. service-a lo invoca por HTTP para reservar
unidades; cada reserva bloquea la fila (SELECT ... FOR UPDATE), descuenta stock
y registra un movimiento, todo dentro de la misma transacción.
"""

import logging
import os
import random
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "shared"))  # ejecución local sin Docker

from telemetry import (  # noqa: E402
    FASTAPI_NATIVE_TELEMETRY_OFF,
    current_trace_id,
    instrument_fastapi,
    instrument_sqlalchemy,
    setup_telemetry,
    shutdown_telemetry,
    untraced,
)

setup_telemetry()

from fastapi import FastAPI, HTTPException  # noqa: E402
from opentelemetry import baggage, metrics, trace  # noqa: E402
from opentelemetry.trace import Status, StatusCode  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from .db import Product, SessionLocal, StockMovement, engine, init_db  # noqa: E402

log = logging.getLogger("service-b")
tracer = trace.get_tracer("service-b.inventory")
meter = metrics.get_meter("service-b.inventory")

reservations_counter = meter.create_counter(
    "inventory.reservations", unit="{reservation}", description="Reservas de stock por resultado"
)
reserved_units = meter.create_histogram(
    "inventory.reserved.units", unit="{unit}", description="Unidades reservadas por solicitud"
)

# Inyección de fallas para poblar los paneles de errores (0 por defecto).
CHAOS_FAILURE_RATE = float(os.getenv("CHAOS_FAILURE_RATE", "0"))
CHAOS_LATENCY_MS = int(os.getenv("CHAOS_LATENCY_MS", "0"))


class ReserveRequest(BaseModel):
    quantity: int = Field(gt=0, le=100)
    order_ref: str = Field(min_length=1, max_length=64)


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
    log.info("service-b listo")
    yield
    shutdown_telemetry()


app = FastAPI(
    title="service-b (inventory)", version="1.0.0", lifespan=lifespan, telemetry=FASTAPI_NATIVE_TELEMETRY_OFF
)
instrument_fastapi(app)
instrument_sqlalchemy(engine)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    with untraced(), engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ready"}


def _product_dto(p: Product) -> dict:
    return {"id": p.id, "sku": p.sku, "name": p.name, "price": float(p.price), "stock": p.stock}


@app.get("/api/products")
def list_products(limit: int = 20):
    with SessionLocal() as session:
        products = session.scalars(select(Product).order_by(Product.id).limit(min(limit, 100))).all()
        return [_product_dto(p) for p in products]


@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    with SessionLocal() as session:
        product = session.get(Product, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        return _product_dto(product)


@app.post("/api/products/{product_id}/reserve")
def reserve_stock(product_id: int, body: ReserveRequest):
    # Custom span: lógica de negocio crítica (los spans HTTP y SQL hijos son automáticos).
    with tracer.start_as_current_span("inventory.reserve_stock") as span:
        span.set_attribute("inventory.product_id", product_id)
        span.set_attribute("inventory.quantity", body.quantity)
        span.set_attribute("order.ref", body.order_ref)
        # Baggage propagado desde service-a junto con el traceparent.
        customer_id = baggage.get_baggage("customer.id")
        if customer_id:
            span.set_attribute("customer.id", str(customer_id))

        if CHAOS_LATENCY_MS:
            time.sleep(random.uniform(0, CHAOS_LATENCY_MS) / 1000)
        if CHAOS_FAILURE_RATE and random.random() < CHAOS_FAILURE_RATE:
            span.set_status(Status(StatusCode.ERROR, "chaos: falla inyectada"))
            span.add_event("chaos.injected_failure")
            reservations_counter.add(1, {"outcome": "error"})
            log.error("Falla inyectada al reservar stock", extra={"product_id": product_id, "order_ref": body.order_ref})
            raise HTTPException(status_code=503, detail="Inventario temporalmente no disponible")

        with SessionLocal() as session, session.begin():
            product = session.scalars(
                select(Product).where(Product.id == product_id).with_for_update()
            ).one_or_none()

            if product is None:
                reservations_counter.add(1, {"outcome": "not_found"})
                span.set_status(Status(StatusCode.ERROR, "producto no encontrado"))
                log.warning("Producto no encontrado", extra={"product_id": product_id})
                raise HTTPException(status_code=404, detail="Producto no encontrado")

            if product.stock < body.quantity:
                reservations_counter.add(1, {"outcome": "insufficient_stock"})
                span.add_event("inventory.insufficient_stock", {"inventory.available": product.stock})
                log.warning(
                    "Stock insuficiente",
                    extra={"product_id": product_id, "requested": body.quantity, "available": product.stock},
                )
                raise HTTPException(status_code=409, detail="Stock insuficiente")

            product.stock -= body.quantity
            session.add(
                StockMovement(
                    product_id=product_id,
                    quantity=-body.quantity,
                    order_ref=body.order_ref,
                    trace_id=current_trace_id(),
                )
            )
            remaining, unit_price = product.stock, float(product.price)

        span.set_attribute("inventory.remaining", remaining)
        reservations_counter.add(1, {"outcome": "reserved"})
        reserved_units.record(body.quantity)
        log.info(
            "Stock reservado",
            extra={"product_id": product_id, "quantity": body.quantity, "order_ref": body.order_ref, "remaining": remaining},
        )
        return {"product_id": product_id, "reserved": body.quantity, "unit_price": unit_price, "remaining": remaining}
