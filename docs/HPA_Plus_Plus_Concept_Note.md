# AI INNOVATION HACKATHON 2026
## CONCEPT NOTE
### HPA++: AI-Powered Predictive Auto Scaling & GPU Scheduling for Kubernetes Clusters
**Risk-Aware Forecasting to Enable Proactive, Cost-Efficient Cluster Scaling**

| Field | Details |
| :--- | :--- |
| **Hackathon** | AI Innovation Hackathon 2026 |
| **Track** | AI for Cluster Intelligence |
| **Phase** | Phase-1 Online Preliminary |

---

## 1. Team Details

* **Team Name:** Team Falah

### Team Members
1. **Sanzida Chowdhury Dristee** - Team Leader (ID: 222-15-6281, Alumni)
2. **Daiyaan Muhammad Fardeen** - Team Member (ID: 222-15-6531, Alumni)
3. **Ahmed Farhanur Rashid** - Team Member (ID: 0242310005101839)
4. **Md. Shahriar Shakil (Mentor)** - Lecturer (Daffodil International University)

### Team Summary
Team Falah is composed of Daffodil International University (DIU) alumni and students building HPA++ end-to-end from the forecasting model to the Kubernetes controller to the live dashboard. Delivering that scope draws directly on Python development, applied machine learning and time-series forecasting, and hands-on Kubernetes/cloud-native systems work, which together map onto the four components the project needed. The team's shared motivation is the everyday cost-versus-reliability trade-off that reactive autoscaling forces on any cluster operator, and the goal of building a practical, forecast-driven alternative rather than a purely theoretical one.

---

## 2. Core Idea

### Main Concept
HPA++ is an AI-powered predictive and GPU-aware autoscaler for Kubernetes. Instead of waiting for CPU or memory usage to cross a threshold, it forecasts incoming traffic a few minutes ahead using time-series modeling (Prophet), then proactively adjusts the number of running pods before a spike hits and scales back down the moment the forecast shows demand falling. Data flows in a closed loop: traffic metrics feed the forecasting engine, the forecast feeds a decision controller, the controller patches the Kubernetes API, and the resulting pod/GPU scaling is reported back on a live monitoring dashboard that closes the cycle.

### Problem Addressed
Kubernetes' default autoscaler (HPA) is purely reactive — it only adds pods after usage has already crossed a threshold, creating a lag window during which real users experience slow responses, timeouts, or dropped requests. This is both a reliability and a cost problem: over-provisioning to avoid the lag wastes compute spend around the clock, while under-provisioning risks outages at exactly the moments that matter most. Every organization running containerized workloads on Kubernetes faces this trade-off, and it is felt most acutely by e-commerce platforms during flash sales, university admission and result portals, streaming platforms during live events, and online examination systems with large synchronized login waves.

### Proposed Solution
HPA++ replaces reactive thresholds with forecast-driven, risk-aware scaling decisions, delivered through four cooperating components:

* **Forecasting Engine:** A Prophet-based time-series model trained continuously on recent traffic metrics (requests/sec, CPU, memory), producing point forecasts with confidence intervals.
* **Predictive Controller:** A lightweight Python service that converts the forecast into a target pod count using confidence-aware scaling logic, issuing commands to the Kubernetes API ahead of demand.
* **GPU Scheduling Layer:** Intelligently assigns GPU resources across deployments to maximize cluster-wide utilization and minimize contention.
* **Live Monitoring Dashboard:** A real-time view of actual vs. predicted traffic, current vs. recommended pod count, confidence bands, and a full log of every scaling decision.

Standard HPA remains active underneath the predictive layer as a reactive safety net, so unpredictable spikes with no historical pattern still get a response — they just don't get proactive lead time.

### Unique / Innovative Aspect
* **Confidence-Aware Scaling:** Uses Prophet's native confidence intervals to scale conservatively when a forecast is uncertain and proactively when it is reliable.
* **Risk-Aware Policies:** Factors in forecast error magnitude, historical miss rates, and the cost asymmetry between under- and over-provisioning.
* **Hybrid Predictive + Reactive Design:** The predictive layer and standard HPA work together rather than competing.
* **GPU-Aware Cluster Scheduling:** A capability absent from standard HPA and most existing predictive scalers.
* **Full Explainability:** Every scaling action is logged with its forecast value, confidence bounds, risk score, and the exact formula that triggered it.

Judges should care because this is not a forecasting demo bolted onto HPA — it is a decision layer that knows when to trust its own predictions, which is the difference between a research prototype and a system that is safe to run in production.

---

## 3. Feasibility & Growth Potential

### Realistic Implementation
**Yes.** Every component is built on lightweight, open-source, CPU-only tooling: Python, Prophet, the official Kubernetes client, Streamlit/Plotly, and Locust for load generation. Minikube provides a full local cluster for development and demo at zero cloud cost, and because it stays fully API-compatible with production Kubernetes, the controller code needs no changes to run on a real cluster afterward.

*Resources required:* A development machine able to run Minikube, a Python 3.x environment, and standard open-source libraries — no GPUs, paid APIs, or proprietary infrastructure are needed to build and demonstrate the system within the hackathon timeline.

### Practicality
**Yes.** Because HPA++ is built entirely on standard Kubernetes APIs and open-source tooling, it requires no vendor-specific infrastructure and can be adopted incrementally alongside an existing HPA configuration rather than replacing it outright — teams can run it in parallel with their current setup, which makes real-world deployment realistic rather than purely theoretical.

### Market Differentiation
The table below summarizes how HPA++ compares with the Kubernetes Horizontal Pod Autoscaler that most clusters run today:

| Feature | Traditional HPA | HPA++ (Proposed) |
| :--- | :--- | :--- |
| **Reactive Scaling** | Yes | Yes (Safety Net) |
| **Predictive Scaling** | No | Yes |
| **Confidence-Aware Decisions** | No | Yes |
| **Risk-Aware Scaling Policies** | No | Yes |
| **GPU-Aware Scheduling** | No | Yes |
| **Cost Optimization** | Limited | Proactive |
| **Explainable / Auditable Decisions** | No | Yes |

### Growth Potential
* **Multi-deployment cluster intelligence:** Aggregating forecasts across all deployments to predict cluster-level demand and prevent node-level saturation before it occurs.
* **Multi-metric forecasting:** Extending beyond request rate to combine CPU, memory, queue depth, and GPU utilization for richer predictions.
* **Anomaly-aware scaling:** Flagging abnormally uncertain forecasts before acting, to avoid aggressive pre-scaling on unreliable signals.
* **Real cloud-cost API integration:** Reporting actual currency savings rather than pod-minute proxies, making ROI directly measurable.
* **Production observability:** Prometheus + Grafana as a polish layer beyond the hackathon dashboard.

---

## 4. Technology Stack & AI Tools

* **Programming Languages:** Python 3.x
* **Frameworks & APIs:** Kubernetes API via the official `kubernetes` Python client; Streamlit and Plotly for the live dashboard; pandas and NumPy for data handling
* **AI Tools:** Facebook Prophet for time-series forecasting. Evaluated against LSTM, XGBoost Time-Series, and ARIMA; Prophet was selected for its native confidence intervals (enabling risk-aware scaling), fast CPU-only retraining on rolling windows, and interpretable seasonality decomposition
* **Cloud Tools:** Kubernetes with Minikube for local development (fully API-compatible with production clusters); NVIDIA DCGM Exporter for GPU metrics; Locust for reproducible load testing; Prometheus and Grafana planned as a production-grade monitoring extension

### Security Protocols
The Predictive Controller and GPU Scheduling Layer act on the cluster exclusively through the official Kubernetes client, so every scaling action inherits standard Kubernetes security rather than introducing a new attack surface: authentication via service-account tokens and authorization scoped through Kubernetes RBAC, limited to the minimum permissions needed to read metrics and patch replica or resource counts. No new external endpoints are exposed beyond the existing cluster API. Dedicated hardening network policies and secrets management for any external forecast store is scoped as a future refinement beyond the hackathon prototype.

---

## 5. Projected Impact

### Target Users
* **E-commerce platforms** during flash sales, where a short traffic surge can cause significant lost revenue if pods aren't pre-scaled.
* **University admission and result portals**, with highly predictable seasonal spikes such as exam days and result releases.
* **Streaming platforms** during live events — sudden concurrent viewer spikes around sporting events, concerts, or award ceremonies.
* **Online examination systems**, with large synchronized login waves at exam start times.
* **ML inference and AI workloads** sharing GPU nodes, which benefit directly from the GPU scheduling layer.

### Impact Metrics

| Metric | Expected Improvement |
| :--- | :--- |
| **Scaling Response Speed** | 30-50% faster than reactive HPA |
| **Request Latency During Spikes** | 20-30% lower in the spike window |
| **Unnecessary Resource Usage** | 15-25% reduction in idle pod-minutes |
| **Pod Readiness Lead-Time** | 3-5 minutes before predicted demand peak |
| **Scale-Down Speed** | 40-60% faster than HPA cooldown-delay |

*These are evaluation targets, to be confirmed through head-to-head Locust benchmark runs against standard HPA under identical traffic profiles.*

### Social & Economic Impact
HPA++ addresses two costs every organization running containerized infrastructure faces at once: the cost of downtime during unexpected spikes, and the cost of idle, over-provisioned compute during quiet periods. For essential public services such as university result portals and online exams, reliable scaling is not just a cost question — it directly affects whether students can reach time-critical systems exactly when it matters. By making forecast-driven, GPU-aware scaling achievable on open-source, vendor-neutral tooling, HPA++ lowers the barrier for smaller organizations and institutions — not only large cloud-native companies — to run infrastructure that is both cost-efficient and reliable.
