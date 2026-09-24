"""The transactional web persistence boundary.

:class:`WebRepository` owns every SQL statement for the application. The
implementation is split across the per-domain mixins composed below; shared
record types live in :mod:`.records`, cross-domain SQL helpers in
:mod:`.helpers`.
"""

from __future__ import annotations

from .experiment import ExperimentsMixin
from .baseline import BaselinesMixin
from .preset import LayerPresetsMixin
from .material import MaterialsMixin
from .result import ResultsMixin
from .identity import UsersMixin
from .admin import AdminMixin
from .campaign import CampaignsMixin
from .condition import ConditionsMixin
from .batch import FabricationBatchesMixin
from .base import WebRepositoryBase


class WebRepository(
    ExperimentsMixin,
    BaselinesMixin,
    LayerPresetsMixin,
    MaterialsMixin,
    ResultsMixin,
    UsersMixin,
    AdminMixin,
    CampaignsMixin,
    ConditionsMixin,
    FabricationBatchesMixin,
    WebRepositoryBase,
):
    """Persist web state through one shared transactional database boundary."""
