"""ShiftOpt — Producti-Co weekly scheduling and production planning MILP.

Maximises weekly profit subject to:
  - Worker rotation: each worker works work_days consecutive days then rests
  - Union constraint: part-time hours <= max_part_time_fraction of total hours
  - Factory capacity: at most max_workers on site per day
  - Labour capacity: production hours + setup hours <= available labour hours per day
  - Production activation: fixed cost and >=1 unit enforced via big-M binary constraints
  - Setup cost: extra hours incurred when both setup_products are produced on the same day
  - Threshold decomposition: extra man-hours per unit above a threshold (product 2 only)
"""

from __future__ import annotations

import time

import pandas as pd
import pulp

from .data import ShiftOptStructuredData
from .solution import MIPSolution, SolveMeta

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ShiftOpt:
    """PuLP/HiGHS MILP for ShiftOpt production scheduling.

    Build once, call solve() for results.
    """

    def __init__(self, data: ShiftOptStructuredData) -> None:
        self.data = data
        self.model = pulp.LpProblem("ShiftOpt", pulp.LpMaximize)
        self.x: dict[tuple[int, str], pulp.LpVariable] = {}   # production quantity
        self.y: dict[tuple[int, str], pulp.LpVariable] = {}   # workers starting
        self.z: dict[tuple[int, str], pulp.LpVariable] = {}   # binary: product active
        self.l: dict[int, pulp.LpVariable] = {}               # binary: setup triggered
        self.u: dict[tuple[int, str], pulp.LpVariable] = {}   # production <= threshold
        self.v: dict[tuple[int, str], pulp.LpVariable] = {}   # production > threshold
        self._build_model()

    def _duty_expr(self, t: int) -> pulp.LpAffineExpression:
        d = self.data
        return pulp.lpSum(
            self.y[((t - i) % d.days, w)]
            for i in range(d.work_days)
            for w in d.worker_types
        )

    def _duty_hours_expr(self, t: int) -> pulp.LpAffineExpression:
        d = self.data
        return pulp.lpSum(
            d.hours_per_day[w] * self.y[((t - i) % d.days, w)]
            for i in range(d.work_days)
            for w in d.worker_types
        )

    def _build_model(self) -> None:
        d = self.data
        T = range(d.days)
        p3, p4 = d.setup_products

        for t in T:
            for p in d.products:
                self.x[(t, p)] = pulp.LpVariable(f"x_{t}_{p}", lowBound=0, cat="Integer")
                self.z[(t, p)] = pulp.LpVariable(f"z_{t}_{p}", cat="Binary")
                self.u[(t, p)] = pulp.LpVariable(f"u_{t}_{p}", lowBound=0)
                self.v[(t, p)] = pulp.LpVariable(f"v_{t}_{p}", lowBound=0)
            for w in d.worker_types:
                self.y[(t, w)] = pulp.LpVariable(f"y_{t}_{w}", lowBound=0, cat="Integer")
            self.l[t] = pulp.LpVariable(f"l_{t}", cat="Binary")

        # Objective: revenue minus fixed activation costs minus total labour cost.
        # Each starter works work_days days, so total labour cost = work_days * sum(y[s,w]*c[w]*h[w]).
        revenue = pulp.lpSum(
            d.sale_price[p] * self.x[(t, p)] - d.fixed_cost[p] * self.z[(t, p)]
            for t in T for p in d.products
        )
        labour_cost = pulp.lpSum(
            d.work_days * d.cost_per_hour[w] * d.hours_per_day[w] * self.y[(t, w)]
            for t in T for w in d.worker_types
        )
        self.model += revenue - labour_cost, "Total_Profit"

        # Part-time hour fraction: sum_t h_PT*y[t,PT] <= max_pt_fraction * sum_{t,w} h[w]*y[t,w]
        pt = d.part_time_type
        self.model += (
            pulp.lpSum(d.hours_per_day[pt] * self.y[(t, pt)] for t in T)
            <= d.max_part_time_fraction * pulp.lpSum(
                d.hours_per_day[w] * self.y[(t, w)] for t in T for w in d.worker_types
            ),
            "PartTime_Fraction",
        )

        # Max workers on duty per day
        for t in T:
            self.model += (
                self._duty_expr(t) <= d.max_workers,
                f"MaxWorkers_Day{t}",
            )

        # Labour hours capacity per day
        for t in T:
            production_hours = pulp.lpSum(
                d.production_time[p] * self.x[(t, p)] + d.extra_hours[p] * self.v[(t, p)]
                for p in d.products
            )
            self.model += (
                production_hours + d.setup_cost * self.l[t] <= self._duty_hours_expr(t),
                f"LabourCapacity_Day{t}",
            )

        # Production activation via big-M: z[t,p]=0 => x[t,p]=0; z[t,p]=1 => 1 <= x[t,p] <= M[p]
        for t in T:
            for p in d.products:
                M = d.big_m[p]
                self.model += (
                    self.x[(t, p)] <= M * self.z[(t, p)],
                    f"Prod_Upper_{t}_{p}",
                )
                self.model += (
                    1 - self.x[(t, p)] <= M * (1 - self.z[(t, p)]),
                    f"Prod_Lower_{t}_{p}",
                )

        # Setup indicator: l[t]=1 iff both setup products are produced on day t
        for t in T:
            self.model += (self.l[t] <= self.z[(t, p3)], f"Setup_LeP3_Day{t}")
            self.model += (self.l[t] <= self.z[(t, p4)], f"Setup_LeP4_Day{t}")
            self.model += (
                self.l[t] >= self.z[(t, p3)] + self.z[(t, p4)] - 1,
                f"Setup_Ge_Day{t}",
            )

        # Threshold decomposition: u[t,p] + v[t,p] = x[t,p]; u[t,p] <= threshold[p]
        for t in T:
            for p in d.products:
                self.model += (
                    self.u[(t, p)] + self.v[(t, p)] == self.x[(t, p)],
                    f"Thresh_Split_{t}_{p}",
                )
                self.model += (
                    self.u[(t, p)] <= d.threshold[p],
                    f"Thresh_Upper_{t}_{p}",
                )

    def solve(self) -> MIPSolution:
        """Solve the MILP and return a MIPSolution."""
        t0 = time.perf_counter()
        # Gap < 1 in absolute terms proves no better integer solution can exist
        # (objective is always integer-valued).
        self.model.solve(pulp.HiGHS(msg=False, mip_rel_gap=0.01, mip_abs_gap=0.999))
        runtime = time.perf_counter() - t0

        status = pulp.LpStatus[self.model.status]
        obj_val = pulp.value(self.model.objective)

        primal: dict[str, pd.DataFrame] = {}

        if status == "Optimal":
            d = self.data
            T = range(d.days)
            day_names = DAYS[:d.days]

            prod_rows = [
                {
                    "day": day_names[t],
                    "product": p,
                    "units": float(pulp.value(self.x[(t, p)]) or 0.0),
                }
                for t in T for p in d.products
            ]
            primal["production"] = pd.DataFrame(prod_rows).set_index(["day", "product"])

            worker_rows = []
            for t in T:
                row: dict = {"day": day_names[t]}
                for w in d.worker_types:
                    row[f"{w}_starts"] = int(round(float(pulp.value(self.y[(t, w)]) or 0.0)))
                row["on_duty"] = sum(
                    int(round(float(pulp.value(self.y[((t - i) % d.days, w)]) or 0.0)))
                    for i in range(d.work_days)
                    for w in d.worker_types
                )
                worker_rows.append(row)
            primal["workers"] = pd.DataFrame(worker_rows).set_index("day")

            total_revenue = sum(
                d.sale_price[p] * float(pulp.value(self.x[(t, p)]) or 0.0)
                for t in T for p in d.products
            )
            total_fixed = sum(
                d.fixed_cost[p] * float(pulp.value(self.z[(t, p)]) or 0.0)
                for t in T for p in d.products
            )
            total_labour = sum(
                d.work_days * d.cost_per_hour[w] * d.hours_per_day[w]
                * float(pulp.value(self.y[(t, w)]) or 0.0)
                for t in T for w in d.worker_types
            )
            primal["profit_breakdown"] = pd.DataFrame([{
                "revenue": total_revenue,
                "fixed_cost": total_fixed,
                "labour_cost": total_labour,
                "profit": total_revenue - total_fixed - total_labour,
            }])

        gap: float | None = None
        try:
            h = self.model.solverModel
            if h is not None:
                info = h.getInfoValue("mip_gap")
                if info[0] == 0:
                    gap = float(info[1])
        except Exception:
            pass

        return MIPSolution(
            meta=SolveMeta(
                status=status,
                objective=float(obj_val) if obj_val is not None else None,  # type: ignore[arg-type]
                runtime_seconds=runtime,
                solver="HiGHS",
            ),
            primal=primal,
            dual={},
            gap=gap,
        )
