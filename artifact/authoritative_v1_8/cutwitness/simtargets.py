"""Simulated targets for ENGINEERING_SIMULATION mode: the toy IVM engine behind each real target's frozen capability matrix."""
from __future__ import annotations
from .adapters.base import SUPPORTED
from .toyengine import ToyEngine


class SimSession(ToyEngine):
    def __init__(self, schema, views, fault, matrix, version):
        super().__init__(schema, views, fault)
        self.matrix, self.version = matrix, version
        self.caps = {"ops": {k for k, v in matrix["ops"].items() if v == SUPPORTED},
                     "lifecycle": {k for k, v in matrix["lifecycle"].items() if v == SUPPORTED}}

    def probe(self):
        return dict(self.version)

    def capability_matrix(self):
        return self.matrix

    def create_schema(self):
        return None

    def create_views(self):
        return None

    def lifecycle(self, kind):
        from .adapters.base import CapabilityUnsupported
        if kind not in self.caps["lifecycle"]:
            raise CapabilityUnsupported(kind, "simulated target declares it unsupported")
        return super().lifecycle(kind)


def applicable_views(views, matrix):
    """Frozen rule: a view applies to a target iff every stateful operator kind it uses is SUPPORTED."""
    return [v for v in views if all(matrix["ops"].get(op.kind) == SUPPORTED for op in v.ops)]
