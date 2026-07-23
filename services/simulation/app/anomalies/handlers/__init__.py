"""Import all handler modules to populate the HANDLER_REGISTRY."""

from app.anomalies.handlers import node
from app.anomalies.handlers import gpu
from app.anomalies.handlers import network
from app.anomalies.handlers import pod
from app.anomalies.handlers import traffic
from app.anomalies.handlers import storage
from app.anomalies.handlers import control_plane
from app.anomalies.handlers import config_deploy
from app.anomalies.handlers import security
from app.anomalies.base import HANDLER_REGISTRY

# Merge all domain handler dicts into the global registry
from app.anomalies.handlers.node import NODE_HANDLERS
from app.anomalies.handlers.gpu import GPU_HANDLERS
from app.anomalies.handlers.network import NETWORK_HANDLERS
from app.anomalies.handlers.pod import POD_HANDLERS
from app.anomalies.handlers.traffic import TRAFFIC_HANDLERS
from app.anomalies.handlers.storage import STORAGE_HANDLERS
from app.anomalies.handlers.control_plane import CP_HANDLERS
from app.anomalies.handlers.config_deploy import CONFIG_HANDLERS
from app.anomalies.handlers.security import SECURITY_HANDLERS

HANDLER_REGISTRY.update(NODE_HANDLERS)
HANDLER_REGISTRY.update(GPU_HANDLERS)
HANDLER_REGISTRY.update(NETWORK_HANDLERS)
HANDLER_REGISTRY.update(POD_HANDLERS)
HANDLER_REGISTRY.update(TRAFFIC_HANDLERS)
HANDLER_REGISTRY.update(STORAGE_HANDLERS)
HANDLER_REGISTRY.update(CP_HANDLERS)
HANDLER_REGISTRY.update(CONFIG_HANDLERS)
HANDLER_REGISTRY.update(SECURITY_HANDLERS)
