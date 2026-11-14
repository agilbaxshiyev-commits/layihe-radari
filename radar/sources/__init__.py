from . import euneighbours, finderasmus, salto, wordpress

SOURCES = {module.NAME: module for module in (finderasmus, salto, euneighbours, wordpress)}
