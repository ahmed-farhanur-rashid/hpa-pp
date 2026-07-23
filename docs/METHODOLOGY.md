# HPA++ Synthetic Telemetry Generation Methodology

## 1. Executive Summary & Mathematical Architecture

The **HPA++ Synthetic Telemetry Benchmark Suite** models multi-tenant Kubernetes cluster traffic and resource utilization over a 365-day period at 5-minute intervals ($105,120$ steps per cluster). 

Rather than using naive Gaussian noise or static sine waves, the generation engine combines **empirical parameters extracted from 4 real-world production traces** with **stochastic process equations** and **domain-specific failure injection models**.

```
                           +-------------------------------------+
                           | 4 Reference Datasets                |
                           +-------------------------------------+
                                              |
                                              v (1. Statistical Parameter Extraction)
                           +-------------------------------------+
                           | Extracted Parameters JSON           |
                           |  - Wiki Seasonality (Fs = 0.965)    |
                           |  - AR(1) Volatility (phi5 = 0.9957) |
                           |  - Pareto Job Churn (b = 2.05)      |
                           +-------------------------------------+
                                              |
                                              v (2. Mathematical Synthesis & Simulation)
    +-------------------------------------------------------------------------------------+
    | SYNTHETIC GENERATION ENGINE                                                         |
    |                                                                                     |
    |  1. Macro Seasonality + Weekly Amplitude Jitter (±10%) + Phase Drift                |
    |  2. Stationary Mean-Reverting Ornstein-Uhlenbeck AR(1) Noise + Student-t Heavy Tail |
    |  3. Dual Spike Generators: Background Job Churn (Pareto) + Flash Sales (Gaussian)   |
    |  4. Operational Anomaly Injection: Outages + Memory Leaks + Overload Plateaus       |
    |  5. Non-Linear Logistic CPU/Mem/GPU Saturation Equations                            |
    |  6. Kubernetes Reactive HPA Pod Scaling Simulation (Max Pods = 120)                 |
    +-------------------------------------------------------------------------------------+
                                              |
                                              v
                             +-----------------------------------+
                             | Final Dataset Suite (data/)       |
                             |  - 5 Cluster Profiles (365d)      |
                             |  - 1 Combined Benchmark (525.6k)  |
                             |  - 1 Shifted Test Set (30d)       |
                             +-----------------------------------+
```

---

## 2. Algorithmic Parameter Extraction Pipeline

To ensure mathematical realism, model parameters are not assumed but strictly derived from reference telemetry through the following computational steps:

### A. Diurnal & Weekly Seasonality (Wikipedia Trace)
The extraction pipeline isolates the `en.wikipedia.org` pageview series (803 days) from `train_by_site.csv`, interpolates missing gaps, and computes the mean traffic grouped by day-of-week. By dividing each day's mean by the overall weekday average, it produces a 7-element array of day-of-week multipliers. It then calculates the weekly seasonality strength ($F_S$) by comparing the variance of the 7-day rolling mean to the total series variance. In the generation phase, these multipliers are applied as:
$$\text{BaseRPS}_t = \text{QPS}_{\text{base}} \times S_{\text{daily}}(t) \times S_{\text{weekly}}(t) \times S_{\text{yearly}}(t)$$
* **Seasonality Strength Guarantee**: Extracted daily seasonality strength $F_S = 0.965 \ge 0.65$.

### B. Stationary Mean-Reverting AR(1) Volatility (Microsoft OpenPAI Trace)
To capture per-minute correlation ($\phi_1 = 0.9975$) without causing unbounded random-walk drift over 365 days, volatility is formulated as a stationary mean-reverting **Ornstein-Uhlenbeck AR(1) process**:
$$x_t = \phi_{5\text{min}} x_{t-1} + \epsilon_t, \quad \epsilon_t \sim \mathcal{N}(0, \sigma_{\text{white}})$$
$$\text{Volatility}_t = \exp\left(\text{clip}(x_t + \text{Student-}t(\nu=2.93), -0.25, 0.25)\right)$$
* **Extracted Parameters**: $\phi_{5\text{min}} = 0.9957$, $\sigma_{\text{white}} = 0.0182$, degrees of freedom $\nu = 2.93$.

### C. GPU Utilization Normalization (OpenPAI GPU Trace)
Because raw GPU metrics in multi-tenant trace logs often represent cluster aggregate sums ($>100\%$), the pipeline divides the aggregate `gpu_util_mean` by the active `gpu_active_mean` count across the trace timeline. This yields the normalized per-GPU mean utilization that grounds the synthetic cluster baselines:
$$\text{GPU}_{\text{normalized}} = \frac{\text{gpu\_util\_mean}}{\max(1, \text{gpu\_active\_mean})} \approx 71.02\% \quad (\sigma = 3.34\%)$$

---

## 3. Workload Profiling & Seasonal Jitter

To evaluate predictive autoscalers across diverse production environments, the engine synthesizes 5 cluster profiles:

| Workload Profile | Base QPS | CPU Weight | GPU Weight | Job Churn ($\lambda$/day) | Flash Events ($\lambda$/day) | Jitter Amplitude |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`ecommerce`** | 600.0 | 0.85 | 0.25 | 15.0 | 0.35 (1-2h) | $\pm 10\%$ |
| **`university_portal`** | 250.0 | 0.95 | 0.05 | 8.0 | 0.08 (2-4h) | $\pm 5\%$ |
| **`streaming`** | 800.0 | 0.70 | 0.60 | 20.0 | 0.15 (1.5-3h) | $\pm 12\%$ |
| **`exam_system`** | 300.0 | 1.00 | 0.02 | 10.0 | 0.50 (1-2h) | $\pm 8\%$ |
| **`genai_inference`** | 450.0 | 0.60 | 1.00 | 25.0 | 0.20 (1-3h) | $\pm 15\%$ |

### Seasonal Jitter Implementation
To prevent models from overfitting to static, repeating mathematical curves, two jitter components are injected:
1. **Weekly Amplitude Jitter**: Smooth random-walk multiplier ($\pm 10\%$) applied week-to-week.
2. **Diurnal Peak Phase Drift**: Phase drift ($\pm 15$ minutes) applied week-to-week to simulate shift in daily peak usage times.

---

## 4. Operational Failure Injection System

The generation engine simulates 365-day timelines ($105,120$ rows of 5-minute intervals) for each cluster profile. During this synthesis, it uses exponential distributions to determine the inter-arrival times of specific anomaly events, injecting 5 labeled anomaly flags to benchmark predictive failure handling:

1. **Background Job Churn Spikes (`is_job_churn_spike`)**: High-frequency per-minute batch job bursts fitted from OpenPAI submission logs using a Pareto distribution ($b = 2.05$).
2. **Flash Demand Surges (`is_flash_event_spike`)**: Asymmetric demand surges (15-min Gaussian rise, exponential decay) with peak multipliers $2.5\times - 5.0\times$.
3. **Partial Outages (`is_outage_event`)**: Partial service failures causing RPS and load to drop sharply to $10-30\%$ of normal baseline, followed by a linear recovery ramp.
4. **Memory Leaks (`is_memleak_event` / `memory_leak_active`)**: Steady un-garbage-collected memory climb ($+50\%$) over 2 to 6 hours until a simulated container restart.
5. **Sustained Overloads (`is_overload_event`)**: Traffic demand exceeding cluster capacity ($4.5\times$), pinning CPU/GPU at $100\%$ utilization and `active_pods` at `max_pods=120`.

---

## 5. System Dynamics & Reactive HPA Pod Simulation

### Multivariate Saturation Curves
System resource metrics are generated from request rates ($\text{RPS}_t$) using non-linear logistic saturation curves:
$$\text{ConcurrentUsers}_t = \max(10, \text{RPS}_t \times 1.80 + \mathcal{N}(0, 20))$$
$$\text{CPU}_t = \text{clip}\left(\frac{100}{1 + \exp(-(\text{Load}_t - 50)/12)} + \mathcal{N}(0, 1.0), \, 5.0, \, 99.5\right)$$
$$\text{GPU}_t = \text{clip}\left(20.0 + 55.0 \times \frac{\text{RPS}_t}{\text{MeanRPS} \times 1.8} \times w_{\text{gpu}} + \mathcal{N}(0, 1.8), \, 5.0, \, 98.5\right)$$

### Reactive HPA Pod Scaling Engine
The generation pipeline simulates a sequential, stateful Kubernetes Horizontal Pod Autoscaler (HPA). For each 5-minute timestep $t$, the reactive HPA pod count ($P_t$) scales based on the previous step's CPU utilization ($T_{\text{cpu}} = 70\%$ target):
$$P_{\text{desired}} = \left\lceil P_{t-1} \times \left(\frac{\text{CPU}_{t-1}}{70.0}\right) \right\rceil$$
$$P_t = \text{clip}\left(\begin{cases} P_{\text{desired}} & \text{if } P_{\text{desired}} > P_{t-1} \quad \text{(Scale Up)} \\ \max(P_{\text{desired}}, P_{t-1} - 2) & \text{if } P_{\text{desired}} \le P_{t-1} \quad \text{(Scale Down)} \end{cases}, \, 5, \, 120\right)$$
* **Reactive Lag Simulation**: By calculating $P_{\text{desired}}$ strictly from $t-1$ utilization, and enforcing a maximum step-down rate, the engine natively generates a realistic **+3 step (+15 minute) lag delay** between load spikes and pod provision completion.

---

## 6. Validation Suite Criteria & Pass Rate

Every generated file must pass 100% of the following statistical criteria in the validation suite:

* **Autocorrelation (ACF)**: $\rho_1 \in [0.85, 0.98]$, $\rho_{12} > 0.50$, $\rho_{288} \ge 0.65$.
* **Seasonality Strength ($F_S$)**: Daily $F_S \ge 0.65$.
* **Cross-Correlation**: Pearson $\text{Corr}(\text{RPS}, \text{Users}) \ge 0.90$, $\text{Corr}(\text{RPS}, \text{CPU}) \ge 0.80$, $\text{Corr}(\text{RPS}, \text{Mem}) \ge 0.50$.
* **HPA Lag**: Peak correlation lag at $+15$ minutes.
* **Pod Distribution Cap**: $\max(P_t) \le 120$.
