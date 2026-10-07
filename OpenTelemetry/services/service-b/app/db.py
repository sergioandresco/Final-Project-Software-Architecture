import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./inventory.db")

_engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs.update(pool_size=int(os.getenv("DB_POOL_SIZE", "20")), max_overflow=20)

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    order_ref: Mapped[str] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def init_db(seed_products: int = 50) -> None:
    """Crea el esquema y siembra productos con stock alto (para el benchmark)."""
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if session.query(Product).count() == 0:
            # Si otra réplica sembró al mismo tiempo, el commit falla por PK duplicada
            # y el caller reintenta: en el segundo intento count() > 0.
            session.add_all(
                Product(
                    id=i,
                    sku=f"SKU-{i:04d}",
                    name=f"Producto {i}",
                    price=round(10 + i * 1.75, 2),
                    stock=1_000_000_000,
                )
                for i in range(1, seed_products + 1)
            )
            session.commit()
