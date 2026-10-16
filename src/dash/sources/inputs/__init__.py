from dash.sources.base import InputSource
from dash.sources.inputs.bushwick import BushwickDaily
from dash.sources.inputs.hackernews import HackerNews
from dash.sources.inputs.web import Web

INPUTS: dict[str, type[InputSource]] = {cls.kind: cls for cls in (Web, HackerNews, BushwickDaily)}
KINDS = tuple(INPUTS)
