from src.data.gateway import DataGateway
from src.data.guards import install_default_guards

# Auto-install point-in-time guards on every provider method that returns a
# dated DataFrame. No-op outside `point_in_time(...)` blocks, so importing the
# data layer in non-backtest paths (api/, dashboards) costs nothing.
install_default_guards()

__all__ = ["DataGateway", "install_default_guards"]
