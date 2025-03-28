"""
Package core - Modules centraux pour l'orchestration et le traitement des requêtes

Ce package contient les composants d'orchestration centraux pour ITS Help:
- pipeline.py: Orchestration générale du flux de traitement
- query_engine.py: Analyse et recherche à travers les différentes sources
- response_builder.py: Construction et formatage des réponses

Ces modules utilisent les adaptateurs spécialisés pour interagir avec les différents services.
"""

from src.core.pipeline import Pipeline, PipelineConfig
from src.core.query_engine import QueryEngine, QueryResult
from src.core.response_builder import ResponseBuilder

__all__ = [
    'Pipeline', 'PipelineConfig',
    'QueryEngine', 'QueryResult',
    'ResponseBuilder'
]
