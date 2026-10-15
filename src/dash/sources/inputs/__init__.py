from dash.sources.base import InputSource
from dash.sources.inputs.web import Web

INPUTS: dict[str, InputSource] = {cls.kind: cls() for cls in (Web,)}
KINDS = tuple(INPUTS)
