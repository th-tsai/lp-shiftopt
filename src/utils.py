"""Result formatting and printing for ShiftOpt."""

from .model import DAYS
from .solution import MIPSolution


def _section(lines: list[str], title: str) -> None:
    lines.append(f"\n{title}")
    lines.append("-" * len(title))


def print_results(solution: MIPSolution, label: str = "ShiftOpt") -> str:
    lines: list[str] = []
    lines.append(f"{label} — Producti-Co Weekly Production Plan")
    lines.append("=" * (len(label) + 38))
    lines.append(f"Status:   {solution.meta.status}")
    if solution.meta.objective is not None:
        lines.append(f"Profit:   £{solution.meta.objective:,.2f}")
    lines.append(f"Runtime:  {solution.meta.runtime_seconds:.3f} s")

    if not solution.is_optimal:
        lines.append("No optimal solution found, skipping details.")
        result = "\n".join(lines)
        print(result)
        return result

    # --- Production plan ---
    _section(lines, "Production Plan")
    prod = solution.get_primal("production").reset_index()
    active = prod[prod["units"] > 0.5].copy()

    if active.empty:
        lines.append("  (no products produced)")
    else:
        pivot = active.pivot(index="product", columns="day", values="units").fillna(0)
        day_order = [d for d in DAYS if d in pivot.columns]
        pivot = pivot[day_order]
        pivot["Total"] = pivot.sum(axis=1)
        pivot.index.name = None
        pivot.columns.name = None
        lines.append(pivot.to_string(float_format=lambda x: f"{x:,.0f}"))

    # --- Worker schedule ---
    _section(lines, "Worker Schedule")
    workers = solution.get_primal("workers").copy()
    start_cols = [c for c in workers.columns if c.endswith("_starts")]

    display = workers[start_cols].copy()
    display.columns = [c.replace("_starts", " starts") for c in start_cols]
    day_order = [d for d in DAYS if d in display.index]
    display = display.loc[day_order]
    display["Total"] = display.sum(axis=1)
    display_T = display.T
    display_T.index.name = None
    display_T.columns.name = None
    lines.append(display_T.to_string(float_format=lambda x: f"{x:,.0f}"))

    # Workers on duty row (no meaningful total across days)
    duty_row = workers.loc[day_order, "on_duty"]
    duty_str = "   ".join(f"{int(v):>5}" for v in duty_row.values)
    lines.append(f"\nWorkers on Duty   {duty_str}")

    # --- Profit breakdown ---
    _section(lines, "Profit Breakdown")
    pb = solution.get_primal("profit_breakdown").iloc[0]
    lines.append(f"  Revenue:      £{pb['revenue']:>14,.2f}")
    lines.append(f"  Fixed costs:  £{pb['fixed_cost']:>14,.2f}")
    lines.append(f"  Labour cost:  £{pb['labour_cost']:>14,.2f}")
    lines.append(f"  Net profit:   £{pb['profit']:>14,.2f}")

    result = "\n".join(lines)
    print(result)
    return result
