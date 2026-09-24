from .base import Provider, Quote, Trip
from .comfort import ComfortDelGro
from .gojek import Gojek
from .grab import Grab

REGISTRY: dict[str, Provider] = {p.key: p for p in (Grab(), Gojek(), ComfortDelGro())}

__all__ = ["Provider", "Quote", "Trip", "REGISTRY"]
