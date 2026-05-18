"""Data schema and loading for ShiftOpt."""

from __future__ import annotations

import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pandas as pd


@dataclass
class ShiftOptRawData:
    """Raw input data loaded from CSV/TOML.

    - products: DataFrame indexed by product name, columns:
        [sale_price, production_time, fixed_cost, threshold, extra_hours]
    - workers: DataFrame indexed by worker type name, columns:
        [cost_per_hour, hours_per_day]
    - max_workers: maximum workers on site at any one time
    - max_part_time_fraction: union limit on part-time share of total labour hours
    - setup_products: pair of product names that incur setup hours when both produced same day
    - setup_cost: extra labour hours for the setup
    - days: length of planning horizon in days (7 for a week)
    - work_days: consecutive days each worker works before resting
    """

    products: pd.DataFrame
    workers: pd.DataFrame
    max_workers: int
    max_part_time_fraction: float
    setup_products: tuple[str, str]
    setup_cost: float
    days: int
    work_days: int
    result: Path | None = None
    description: str | None = None

    @classmethod
    def load_from_toml(cls, path: Path) -> "ShiftOptRawData":
        with open(path, "rb") as f:
            data: dict[str, Any] = tomllib.load(f)

        sc = data["scalar"]
        base = path.parent
        tp = data["table_path"]

        result_path: Path | None = None
        description: str | None = None
        if "result" in data:
            result_path = Path(data["result"]["result"])
            description = data["result"].get("description")

        return cls(
            products=pd.read_csv(base / tp["product"], index_col="product"),
            workers=pd.read_csv(base / tp["worker"], index_col="worker_type"),
            max_workers=int(sc["max_workers"]),
            max_part_time_fraction=float(sc["max_part_time_fraction"]),
            setup_products=tuple(str(p) for p in sc["setup_products"]),
            setup_cost=float(sc["setup_cost"]),
            days=int(sc["days"]),
            work_days=int(sc["work_days"]),
            result=result_path,
            description=description,
        )

    def structured(self) -> "ShiftOptStructuredData":
        return ShiftOptStructuredData.from_raw(self)


@dataclass(frozen=True)
class ShiftOptStructuredData:
    """Validated, immutable data for ShiftOpt model construction.

    big_m is computed from max_workers and production_time so it always
    stays consistent with the actual data. Use from_raw() to construct.
    """

    # Index sets
    products: tuple[str, ...]
    worker_types: tuple[str, ...]
    days: int
    work_days: int

    # Product parameters
    sale_price: Mapping[str, float]
    production_time: Mapping[str, float]
    fixed_cost: Mapping[str, float]
    threshold: Mapping[str, float]
    extra_hours: Mapping[str, float]
    big_m: Mapping[str, float]  # computed: ceil(max_workers * max_hours / prod_time)

    # Worker parameters
    cost_per_hour: Mapping[str, float]
    hours_per_day: Mapping[str, float]

    # Scalar parameters
    max_workers: int
    max_part_time_fraction: float
    setup_products: tuple[str, str]
    setup_cost: float

    # Part-time worker type identifier (last worker type in order)
    part_time_type: str

    @classmethod
    def from_raw(cls, raw: ShiftOptRawData) -> "ShiftOptStructuredData":
        products = tuple(raw.products.index.astype(str))
        worker_types = tuple(raw.workers.index.astype(str))

        max_hours = max(float(raw.workers.at[w, "hours_per_day"]) for w in worker_types)  # type: ignore[arg-type]
        computed_big_m = {
            p: math.ceil(raw.max_workers * max_hours / float(raw.products.at[p, "production_time"]))  # type: ignore[arg-type]
            for p in products
        }

        return cls(
            products=products,
            worker_types=worker_types,
            days=raw.days,
            work_days=raw.work_days,
            sale_price=MappingProxyType({p: float(raw.products.at[p, "sale_price"]) for p in products}),  # type: ignore[arg-type]
            production_time=MappingProxyType({p: float(raw.products.at[p, "production_time"]) for p in products}),  # type: ignore[arg-type]
            fixed_cost=MappingProxyType({p: float(raw.products.at[p, "fixed_cost"]) for p in products}),  # type: ignore[arg-type]
            threshold=MappingProxyType({p: float(raw.products.at[p, "threshold"]) for p in products}),  # type: ignore[arg-type]
            extra_hours=MappingProxyType({p: float(raw.products.at[p, "extra_hours"]) for p in products}),  # type: ignore[arg-type]
            big_m=MappingProxyType(computed_big_m),
            cost_per_hour=MappingProxyType({w: float(raw.workers.at[w, "cost_per_hour"]) for w in worker_types}),  # type: ignore[arg-type]
            hours_per_day=MappingProxyType({w: float(raw.workers.at[w, "hours_per_day"]) for w in worker_types}),  # type: ignore[arg-type]
            max_workers=raw.max_workers,
            max_part_time_fraction=raw.max_part_time_fraction,
            setup_products=raw.setup_products,
            setup_cost=raw.setup_cost,
            part_time_type=worker_types[-1],
        )
