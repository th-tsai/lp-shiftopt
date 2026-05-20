# ShiftOpt — Producti-Co Weekly Scheduling

**Problem class:** Mixed-integer linear programming · production scheduling  
**Solver:** PuLP + HiGHS

---

## The Problem

Producti-Co Ltd runs a 7-day factory with 500 worker slots per day and a catalogue of 7 products ranging from a £100 commodity to a £1,115 premium item. Workers are hired on 5-day rotating shifts; the factory never closes.

The question the model answers: **given these products, workers, and factory rules — what should we make each day, and who should be on the floor?**

The answer turns out to be far simpler than the inputs suggest, and the reasons why are the interesting part.

### Products

| Product | Sale price (£/unit) | Production time (h/unit) | Fixed cost (£/active day) | Threshold (units) | Extra hours above threshold (h/unit) |
| ------- | ------------------: | -----------------------: | ------------------------: | ----------------: | -----------------------------------: |
| P1      |                 100 |                      1.0 |                         0 |                 0 |                                    0 |
| P2      |                 420 |                      2.0 |                         0 |               100 |                                    1 |
| P3      |                 350 |                      2.7 |                         0 |                 0 |                                    0 |
| P4      |                 490 |                      2.4 |                         0 |                 0 |                                    0 |
| P5      |                 550 |                      4.5 |                         0 |                 0 |                                    0 |
| P6      |                 100 |                      0.7 |                         0 |                 0 |                                    0 |
| P7      |               1,115 |                      9.5 |                     2,000 |                 0 |                                    0 |

Three products have complications worth noting:

- **P7** charges a £2,000 daily toll just to switch on the line, regardless of how many units are made.
- **P2** gets more expensive to produce past 100 units/day — the first 100 take 2 h each, anything beyond takes 3 h each.
- **P3 and P4** share a factory configuration: running both on the same day triggers a 75-hour setup changeover that eats directly into available production time.

### Workers

| Type           | Cost (£/h) | Hours/day | Cost per 5-day shift |
| -------------- | ---------: | --------: | -------------------: |
| FT (full-time) |         80 |         8 |               £3,200 |
| PT (part-time) |         35 |         6 |               £1,050 |

Workers commit to 5-day shifts. A union rule caps part-time hours at 25% of total worker-hours per week.

### Factory rules

| Parameter                 | Value  |
| ------------------------- | ------ |
| Maximum workers on site   | 500    |
| Part-time hours limit     | 25 %   |
| Planning horizon          | 7 days |
| Shift length              | 5 days |
| Setup cost (P3 + P4)      | 75 h   |

---

## MILP Formulation

### Sets and indices

| Symbol               | Definition                      |
| -------------------- | ------------------------------- |
| $T = \{0,\ldots,6\}$ | days of the week                |
| $P$                  | products                        |
| $W$                  | worker types (FT, PT)           |
| $p_3, p_4 \in P$     | the two setup products (P3, P4) |

### Parameters

| Symbol     | Meaning                                                          |
| ---------- | ---------------------------------------------------------------- |
| $s_p$      | sale price of product $p$ (£/unit)                               |
| $\tau_p$   | production time of product $p$ (h/unit)                          |
| $f_p$      | fixed cost per day product $p$ is active (£/day)                 |
| $\theta_p$ | threshold quantity for product $p$ (units)                       |
| $e_p$      | extra hours per unit above threshold                             |
| $c_w$      | hourly wage for worker type $w$ (£/h)                            |
| $h_w$      | hours per day for worker type $w$                                |
| $N^{\max}$ | maximum workers on site per day (500)                            |
| $\alpha$   | max part-time fraction of total starter-hours (0.25)             |
| $\kappa$   | setup hours incurred when both setup products are active (75 h)  |
| $D$        | planning horizon in days (7)                                     |
| $D_w$      | shift length in days (5)                                         |
| $M_p$      | big-M bound: $\lceil N^{\max} \cdot \max_w h_w / \tau_p \rceil$ |

### Decision variables

| Symbol    | Domain               | Meaning                                                    |
| --------- | -------------------- | ---------------------------------------------------------- |
| $x_{t,p}$ | $\mathbb{Z}_{\ge 0}$ | units of product $p$ produced on day $t$                   |
| $y_{t,w}$ | $\mathbb{Z}_{\ge 0}$ | workers of type $w$ starting their shift on day $t$        |
| $z_{t,p}$ | $\{0,1\}$            | 1 if product $p$ is active on day $t$                      |
| $l_t$     | $\{0,1\}$            | 1 if setup is triggered on day $t$                         |
| $u_{t,p}$ | $\ge 0$              | production up to threshold on day $t$ (inframarginal part) |
| $v_{t,p}$ | $\ge 0$              | production above threshold on day $t$ (supramarginal part) |

### Derived expressions

Workers on duty and available labour-hours on day $t$ are determined by the 5-day rotation:

$$N_t = \sum_{w \in W}\sum_{i=0}^{D_w-1} y_{(t-i)\bmod D,\,w} \qquad H_t = \sum_{w \in W}\sum_{i=0}^{D_w-1} h_w\, y_{(t-i)\bmod D,\,w}$$

### Objective — maximise weekly profit

$$\max \quad \underbrace{\sum_{t \in T}\sum_{p \in P}\bigl[s_p\,x_{t,p} - f_p\,z_{t,p}\bigr]}_{\text{production revenue net of fixed costs}} - \underbrace{\sum_{t \in T}\sum_{w \in W} D_w \cdot c_w \cdot h_w \cdot y_{t,w}}_{\text{total labour cost}}$$

Labour cost is paid per shift start; a worker starting on day $t$ costs $D_w \cdot c_w \cdot h_w$ in total regardless of production volume.

### Constraints

**C1 — Union limit** (part-time hours capped as a fraction of total hours)

$$\sum_t h_{\text{PT}}\,y_{t,\text{PT}} \le \alpha\!\sum_t\sum_w h_w\,y_{t,w}$$

**C2 — Site capacity** (workers on duty cannot exceed the site maximum)

$$N_t \le N^{\max} \quad \forall t \in T$$

**C3 — Labour hours** (production and setup together cannot exceed available hours)

$$\sum_p \bigl[\tau_p\,x_{t,p} + e_p\,v_{t,p}\bigr] + \kappa\,l_t \le H_t \quad \forall t \in T$$

**C4 — Activation big-M** (production is zero if and only if the binary is off)

$$x_{t,p} \le M_p\,z_{t,p} \quad \forall t \in T, p \in P$$

$$1-x_{t,p} \le M_p(1-z_{t,p}) \quad \forall t \in T, p \in P$$

**C5 — Setup AND gate** ($l_t = 1$ only when both P3 and P4 are active simultaneously)

$$l_t \le z_{t,p_3} \quad \forall t \in T$$

$$l_t \le z_{t,p_4} \quad \forall t \in T$$

$$l_t \ge z_{t,p_3}+z_{t,p_4}-1 \quad \forall t \in T$$

**C6 — Threshold split** (P2 production split into below- and above-threshold components for piecewise labour cost)

$$u_{t,p}+v_{t,p} = x_{t,p} \quad \forall t \in T, p \in P$$

$$u_{t,p} \le \theta_p \quad \forall t \in T, p \in P$$

C3 couples the production and staffing decisions: the 75-hour setup cost is denominated in labour-hours, directly reducing the time available for production on any day both P3 and P4 run. C4 uses a big-M pair to enforce the activation logic: zero production forces the binary off; the binary off forces zero production. C5 is a standard AND-gate linearisation. C6 splits P2 production into a below-threshold and above-threshold component so the piecewise labour cost stays linear.

---

## Results

### Baseline — a factory running 7 products picks just two

**Weekly profit: £3,506,900**  
Revenue £5,284,650 — Labour £1,777,750 — Fixed costs £0

Out of seven available products, the optimal plan produces only **P2 and P4** every day, every week. That is not a coincidence or a simplification — it is the correct answer, and understanding why reveals how the factory really works.

**The key metric is revenue per labour-hour, not revenue per unit.**

When the factory runs at full capacity (500 workers every day), the real constraint is not money or market demand — it is time. Every product competes for the same 4,000 daily worker-hours, so the right question is: which product generates the most money for each hour consumed?

| Product      | Revenue per labour-hour | Verdict                                            |
| ------------ | ----------------------: | -------------------------------------------------- |
| P2 (≤ 100 u) |               £210 / h  | Best in factory — run this first, every day        |
| P4           |               £204 / h  | Second best — fills all remaining hours            |
| P6           |               £143 / h  | Falls well short of P4                             |
| P3           |               £130 / h  | Below P4, and carries a hidden setup penalty       |
| P5           |               £122 / h  | Below P4                                           |
| P7           |  £117 / h + £2,000/day  | Slow and expensive to activate at baseline         |
| P1           |               £100 / h  | Lowest of all                                      |
| P2 (> 100 u) |               £140 / h  | Once past the threshold, P2 drops below P4        |

The plan follows directly: produce exactly **100 units of P2 per day** (capturing the high-rate window), then dedicate every remaining hour to **P4**. Going beyond 100 units of P2 is actively harmful — the production rate drops from £210/h to £140/h, which is worse than P4.

P3 is excluded despite having no fixed cost. Running P3 alongside P4 triggers the 75-hour setup changeover — equivalent to losing roughly 9 workers' worth of daily output — while P3 itself earns £74/h less than P4. The factory is strictly better off ignoring P3 entirely.

P7's £1,115 price tag is misleading. At 9.5 hours per unit, it earns only £117/h — the second worst rate in the catalogue — and then charges an extra £2,000 daily toll just to run the line. The headline price hides a very slow product with a standing charge.

#### Production plan (units/day)

| Product |   Mon |   Tue |   Wed |   Thu |   Fri |   Sat |   Sun | Weekly total |
| ------- | ----: | ----: | ----: | ----: | ----: | ----: | ----: | -----------: |
| P2      |   100 |   100 |   100 |   100 |   100 |   100 |   100 |          700 |
| P4      | 1,404 | 1,404 | 1,404 | 1,487 | 1,570 | 1,500 | 1,416 |       10,185 |

#### Why the union's 25% PT cap is always binding — and why that is actually good news

It is tempting to assume full-time workers are more valuable because they work longer days. The model disagrees, and the arithmetic is clear:

| Worker type | Daily hours | Daily wage | Daily production value | Daily profit per slot |
| ----------- | ----------: | ---------: | ---------------------: | --------------------: |
| FT          |       8 h   |      £640  |               £1,633   |                  £993 |
| PT          |       6 h   |      £210  |               £1,225   |                £1,015 |

A part-time worker generates **£22 more profit per day** than a full-time worker under current production rates. The reason: PT wages are less than half of FT wages, while the PT day is two-thirds as long. The wage discount outpaces the hour reduction, making PT the better deal.

The model therefore hires as many part-time workers as the union allows — exactly 215 PT starters against 485 FT starters, consuming 24.95% of total starter-hours. The 25% cap is binding in every scenario. The Saturday and Sunday PT starters exist to cover weekend shifts without disrupting the weekday FT blocks.

#### Worker schedule (starters/day)

|           | Mon | Tue | Wed | Thu | Fri | Sat | Sun | Total |
| --------- | --: | --: | --: | --: | --: | --: | --: | ----: |
| FT starts |  85 | 100 | 100 | 100 | 100 |   0 |   0 |   485 |
| PT starts |  15 |   0 |   0 |   0 |   0 | 100 | 100 |   215 |

Workers on duty every day: **500**.

---

## Sensitivity Analysis

The baseline plan is built on a set of prices and timings. Eight scenarios ask: how much would any one of those parameters need to change before the plan is no longer optimal? The answers reveal exactly how robust — or fragile — each aspect of the strategy is.

| Case | What changed          | From          | To            | Profit     | vs baseline | Plan shift      |
| ---: | :-------------------- | :------------ | :------------ | ---------: | ----------: | :-------------- |
|    — | Baseline              | —             | —             | £3,506,900 |           — | P4 dominant     |
|    1 | P7 production time    | 9.5 h/unit    | 5.5 h/unit    | £3,506,900 |        0.0% | No change       |
|    2 | P7 production time    | 9.5 h/unit    | 5.44 h/unit   | £3,510,830 |      +0.11% | P4 → P7         |
|    3 | P7 prod. time + price | 9.5 h, £1,115 | 5.5 h, £1,126 | £3,503,942 |      −0.08% | P4 → P7 (loss)  |
|    4 | P7 prod. time + price | 9.5 h, £1,115 | 5.5 h, £1,127 | £3,508,384 |      +0.04% | P4 → P7 (gain)  |
|    5 | P6 sale price         | £100/unit     | £143/unit     | £3,505,288 |      −0.05% | P4 → P6         |
|    6 | P6 sale price         | £100/unit     | £148/unit     | £3,681,914 |      +4.99% | P6 takes all    |
|    7 | P6 production time    | 0.7 h/unit    | 0.45 h/unit   | £3,981,690 |     +13.53% | P6 + FT flip    |
|    8 | P5 production time    | 4.5 h/unit    | 2.6 h/unit    | £3,688,700 |      +5.18% | P5 displaces all|

---

### Cases 1 & 2 — How close is P7 to being worth it?

P7 sells for £1,115 — the most expensive product in the catalogue. Yet at baseline, the factory produces zero units. Why?

The issue is production speed. At 9.5 h/unit, P7 earns only £117/h — far below P4's £204/h. The expensive unit price is undermined by how long it takes to make each one. To compete with P4, P7 would need to earn at least £204/h, which means producing it in no more than £1,115 / £204 ≈ 5.47 h/unit.

**Case 1** tests 5.5 h/unit — just slightly above that threshold. P7 reaches £202.7/h, which is still £1.5/h below P4. The plan is identical to the baseline; the improvement was not quite enough.

**Case 2** tests 5.44 h/unit. P7 reaches £204.96/h — barely edging past P4. The factory immediately switches its entire secondary production from P4 to P7, and profit rises by £3,930. The lesson: the transition between "never produce this" and "always produce this" is a knife-edge. One tenth of an hour per unit separates Cases 1 and 2, yet the factory's weekly plan is completely different.

It is also worth noting that switching to P7 means paying the £2,000/day activation fee seven times over — £14,000 per week in fixed costs that did not exist before. That cost is recovered by the higher revenue per hour, but it has to be earned back first.

---

### Cases 3 & 4 — The price trap: when higher revenue/h still loses money

These two cases reveal a subtlety that pure revenue-per-hour thinking misses.

With P7 production time held at 5.5 h, the factory asks: what sale price makes P7 worth activating? On an hourly basis, P7 needs to beat P4 at £204/h, which means a price above £1,115 (= £204 × 5.5). **Case 3** raises P7 to £1,126 — £204.7/h, above P4. The model activates P7.

But then the weekly profit drops by £2,958 compared to the baseline. The factory is worse off despite switching to the "better" product.

The problem is the £14,000 weekly fixed cost. Switching to P7 adds revenue, but not enough extra revenue to cover the daily tolls. The per-hour metric said "activate P7" — but the fixed cost is not charged per hour, it is charged per day regardless of volume. A product can be more productive per hour and still be a bad deal if it carries a standing charge.

**Case 4** raises P7 by just £1 more, to £1,127. That extra pound across ~4,400 weekly units adds £4,400 in revenue — enough to finally clear the fixed cost and push profit above the baseline. The break-even price for P7 at 5.5 h/unit lies somewhere between £1,126 and £1,127 — a gap of £1 per unit that separates a loss-making switch from a profitable one.

---

### Cases 5 & 6 — P6's hidden potential: the cheapest product takes over

P6 starts the baseline at the very bottom of the revenue-per-hour table — £142.9/h, well behind P4 at £204.2/h. It sells for only £100/unit. At first glance it is an afterthought.

But P6 is extraordinarily fast to make: just 0.7 h/unit. That means every time its price rises by £1, its hourly rate jumps by £1.43. To displace P4, P6 needs to reach £204/h — which requires a price of only £143/unit. That is a 43% price increase, which sounds large, but the hourly rate sensitivity makes it achievable.

**Case 5** raises P6 to exactly £143. The factory immediately drops P4 and switches to P6 for all production beyond the daily P2 allocation. The volume is striking: the factory now makes 34,866 units of P6 per week (versus ~10,000 of P4 in the baseline), because each unit takes so little time. P2 continues unchanged — its £210/h rate still beats P6 at £204.3/h.

**Case 6** raises P6 to £148 (£211.4/h). Now P6 is faster-earning than even the first 100 units of P2. The factory abandons P2 entirely and runs P6 through every available hour. Weekly profit jumps by £174,814 (+4.99%) — the largest gain from any single price change in these scenarios.

The two displacement thresholds for P6's price:
- **≈ £143/unit** — P6 displaces P4 as the main filler product
- **≈ £147/unit** — P6 displaces the daily P2 premium slot

Both transitions are sharp because the factory runs at 100% capacity — there is no gradual substitution. The moment P6 edges above a competitor in revenue/h, the entire plan flips.

---

### Case 7 — Make it faster, not pricier: the biggest profit jump, and an unexpected workforce flip

This is the most dramatic scenario in the analysis. Rather than raising P6's price, Case 7 reduces its production time from 0.7 h/unit to 0.45 h/unit — a 36% speed improvement.

At 0.45 h/unit, P6 earns £222.2/h. That is not just the best rate in this scenario — it is the highest hourly rate of any product across all eight cases. The factory produces 62,177 units of P6 in the week and nearly nothing else. Weekly profit reaches **£3,981,690 — up £474,790 (13.5%) from the baseline**.

This result illustrates a broader principle: making a product faster is a more powerful lever than making it more expensive, because speed multiplies output across the entire labour-hour budget. Raising P6's price by £48/unit (Case 6) added £175k profit. Cutting its cycle time by 36% (Case 7) adds £475k. The same factory, the same workers, the same 4,000 daily hours — three times the gain.

#### The workforce does something unexpected

In every other scenario, the model maximises part-time workers up to the union's 25% ceiling. In Case 7, PT starters drop to **zero**. The factory switches entirely to full-time workers — 700 FT starters across the week, no PT at all.

This is not a modelling quirk. It follows from a precise arithmetic crossover. Whether FT or PT workers generate more daily profit depends on the hourly production value $R$:

- FT profit per worker-day = 8 hours × (£R − £80 wage)
- PT profit per worker-day = 6 hours × (£R − £35 wage)

Below **£215/h**, PT wins — their lower wage more than compensates for their two fewer hours. Above £215/h, FT wins — those extra two hours generate more revenue than the wage difference costs.

At the baseline (£204/h), PT is worth £22/day more per slot. At Case 7's £222/h, FT is worth £15/day more per slot. The crossover sits exactly at £215/h, a threshold the faster P6 crosses cleanly.

The union's 25% cap — binding in every other scenario — becomes irrelevant in Case 7 not because of any rule change, but because the factory would not hire part-time workers even if it could.

---

### Case 8 — P5 overtakes everything by getting faster

The final scenario targets P5, which at baseline earns £122/h — a mediocre rate that keeps it out of the plan entirely. Cutting its production time from 4.5 h to 2.6 h raises it to **£211.5/h**, above both P4 (£204/h) and the P2 inframarginal rate (£210/h).

The factory's response is complete: P2 and P4 both disappear from the plan. P5 fills every available hour, producing 9,939 units across the week for a weekly profit of **£3,688,700 — up £181,800 (+5.2%)**.

The threshold that matters is not the price — P5's £550 price never changed. It is the point at which £550 / production_time exceeds £210/h (the P2 inframarginal rate), which works out to production_time < 2.619 h/unit. At 2.6 h, P5 clears that bar by a hair, and the entire plan reorganises around it.

Notice also what does not change: the worker mix. P5 at £211.5/h falls just below the £215/h FT/PT crossover, so the model keeps the same 485 FT / 215 PT structure as the baseline. The factory floor looks entirely different in terms of what it makes, but the staffing roster is unchanged.

---

## Key Takeaways

**Revenue per hour is the master metric — not price, not margin.**  
The factory's constraint is time, not capital. When every worker-hour is spoken for, the right question is always: which product earns the most money per hour consumed? Products that look attractive on price alone (P7 at £1,115/unit) can be outperformed by ones that look cheap (P4 at £490) simply because they are faster to make.

**Fixed costs are a trap that revenue-per-hour analysis misses.**  
P7 illustrates this precisely. In Cases 3 and 4, P7 beats P4 on hourly rate — yet the factory is worse off with P7 because the £2,000/day activation fee cannot be recovered at the margin. A higher hourly rate only helps if you are producing enough volume to cover the standing charge. This is the classic fixed-cost breakeven problem, and it is easy to get wrong without a model.

**Hidden costs can make an attractive product toxic.**  
P3 is a reasonable product on paper: decent price, no fixed cost. But sharing a floor configuration with P4 means running P3 forces a 75-hour setup, effectively destroying most of the value P3 would add. The model knows this and avoids P3 entirely — a decision that would be easy to miss if evaluated product-by-product rather than as a joint plan.

**Part-time workers are more profitable than full-time — until they suddenly aren't.**  
At current production rates, hiring more PT workers is strictly better for the bottom line, despite their shorter shifts. The union cap is binding in seven of eight scenarios because the model always wants more PT than the contract allows. But there is a precise tipping point at £215/h — above it, the FT worker's extra two daily hours generate more value than their higher wage costs. Case 7 is the only scenario that crosses it, and when it does, the model drops PT workers completely. The lesson: workforce composition should be treated as a strategic variable, not a fixed input.

**Production time improvements dwarf price improvements.**  
The largest profit gains in these scenarios come from speed, not price. Making P6 36% faster (Case 7) delivers a 13.5% profit uplift. Making P5 42% faster (Case 8) delivers 5.2%. By contrast, raising P7's price by £1/unit (Case 4) delivers 0.04%. If Producti-Co has a budget for either a pricing initiative or a process improvement programme, the numbers suggest the process improvement will win by a large margin.

**The plan is stable until it isn't — transitions are sharp, not gradual.**  
In nearly every scenario, the factory either ignores a product completely or dedicates significant capacity to it. There is very little "produce a bit of this alongside a bit of that." This is a feature of running at full capacity: when every hour is committed, a product that edges above a competitor in hourly value immediately takes all that competitor's hours. Small parameter changes can trigger complete plan reorganisations — which is exactly why sensitivity analysis matters.
