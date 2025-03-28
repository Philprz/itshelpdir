"""
Module metrics.py - Collecte et analyse des métriques de performance

Ce module fournit une infrastructure pour collecter, analyser et exporter
des métriques de performance du système, notamment concernant la consommation
de tokens, les temps de réponse et les taux de succès.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
import json
import os
from datetime import datetime, timezone

# Configuration du logging
logger = logging.getLogger("ITS_HELP.infrastructure.metrics")

class MetricsCollector:
    """
    Collecteur de métriques pour l'analyse de performance
    
    Cette classe:
    1. Collecte des métriques sur les requêtes, recherches et réponses
    2. Calcule des statistiques agrégées (moyenne, médiane, percentiles)
    3. Exporte les données pour visualisation et analyse
    """
    
    def __init__(self, export_dir: Optional[str] = None):
        """
        Initialise le collecteur de métriques
        
        Args:
            export_dir: Répertoire d'export des métriques (optionnel)
        """
        self.metrics = {
            "requests": {},  # Métriques par requête
            "aggregated": {  # Métriques agrégées
                "total_requests": 0,
                "total_cache_hits": 0,
                "total_tokens": {
                    "prompt": 0,
                    "completion": 0,
                    "total": 0
                },
                "total_tokens_saved": 0,
                "latency": {
                    "avg_ms": 0,
                    "p50_ms": 0,
                    "p90_ms": 0,
                    "p99_ms": 0
                },
                "sources": {}  # Statistiques par source
            },
            "hourly": {},  # Métriques par heure
            "daily": {}    # Métriques par jour
        }
        
        self.export_dir = export_dir or os.path.join(os.getcwd(), "metrics")
        self._ensure_export_dir()
        
        # État interne
        self._initialized = False
        self._durations_ms = []  # Pour calculer les percentiles
        self._export_task = None
    
    def _ensure_export_dir(self):
        """Crée le répertoire d'export s'il n'existe pas"""
        if not os.path.exists(self.export_dir):
            try:
                os.makedirs(self.export_dir, exist_ok=True)
                logger.info(f"Répertoire d'export des métriques créé: {self.export_dir}")
            except Exception as e:
                logger.error(f"Erreur lors de la création du répertoire d'export: {str(e)}")
    
    async def initialize(self):
        """Initialise le collecteur de métriques"""
        if self._initialized:
            return
            
        logger.info("Initialisation du collecteur de métriques...")
        
        # Chargement des métriques précédentes si elles existent
        await self._load_previous_metrics()
        
        # Démarrage de la tâche d'export périodique
        self._export_task = asyncio.create_task(self._periodic_export())
        
        self._initialized = True
        logger.info("Collecteur de métriques initialisé avec succès")
    
    async def _load_previous_metrics(self):
        """Charge les métriques agrégées précédentes si elles existent"""
        aggregated_file = os.path.join(self.export_dir, "aggregated_metrics.json")
        
        if os.path.exists(aggregated_file):
            try:
                with open(aggregated_file, 'r', encoding='utf-8') as f:
                    previous = json.load(f)
                    
                # Mise à jour des métriques agrégées
                if "aggregated" in previous:
                    self.metrics["aggregated"] = previous["aggregated"]
                    logger.info(f"Métriques agrégées chargées: {self.metrics['aggregated']['total_requests']} requêtes")
            except Exception as e:
                logger.error(f"Erreur lors du chargement des métriques précédentes: {str(e)}")
    
    async def _periodic_export(self):
        """Exporte périodiquement les métriques"""
        export_interval = 3600  # 1 heure
        
        while True:
            try:
                await asyncio.sleep(export_interval)
                await self.export_metrics()
                logger.debug("Export périodique des métriques effectué")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur lors de l'export périodique des métriques: {str(e)}")
                await asyncio.sleep(300)  # Attendre 5 minutes en cas d'erreur
    
    def start_request(self, request_id: str, query: str, user_id: Optional[str] = None):
        """
        Enregistre le début d'une requête
        
        Args:
            request_id: Identifiant de la requête
            query: Texte de la requête
            user_id: Identifiant de l'utilisateur (optionnel)
        """
        now = time.time()
        
        self.metrics["requests"][request_id] = {
            "query": query,
            "start_time": now,
            "user_id": user_id,
            "sources": set(),
            "cache_hit": False,
            "tokens": {
                "prompt": 0,
                "completion": 0,
                "total": 0
            },
            "response_size": 0,
            "end_time": None,
            "duration_ms": None
        }
    
    def record_cache_hit(self, request_id: str):
        """
        Enregistre un hit de cache pour une requête
        
        Args:
            request_id: Identifiant de la requête
        """
        if request_id in self.metrics["requests"]:
            self.metrics["requests"][request_id]["cache_hit"] = True
            self.metrics["aggregated"]["total_cache_hits"] += 1
            
            # Estimation des tokens économisés (moyenne des requêtes précédentes)
            avg_tokens = 0
            if self.metrics["aggregated"]["total_requests"] > 0:
                avg_tokens = self.metrics["aggregated"]["total_tokens"]["total"] / self.metrics["aggregated"]["total_requests"]
            
            self.metrics["aggregated"]["total_tokens_saved"] += avg_tokens
    
    def record_search_completed(self, request_id: str, total_results: int, sources: List[str]):
        """
        Enregistre la complétion d'une recherche
        
        Args:
            request_id: Identifiant de la requête
            total_results: Nombre total de résultats
            sources: Sources utilisées
        """
        if request_id in self.metrics["requests"]:
            req_metrics = self.metrics["requests"][request_id]
            req_metrics["total_results"] = total_results
            req_metrics["sources"] = set(sources)
            
            # Mise à jour des statistiques par source
            for source in sources:
                if source not in self.metrics["aggregated"]["sources"]:
                    self.metrics["aggregated"]["sources"][source] = {
                        "count": 0,
                        "results": 0
                    }
                
                self.metrics["aggregated"]["sources"][source]["count"] += 1
                self.metrics["aggregated"]["sources"][source]["results"] += total_results
    
    def record_token_usage(self, request_id: str, prompt_tokens: int, completion_tokens: int):
        """
        Enregistre l'utilisation de tokens pour une requête
        
        Args:
            request_id: Identifiant de la requête
            prompt_tokens: Nombre de tokens pour le prompt
            completion_tokens: Nombre de tokens pour la complétion
        """
        if request_id in self.metrics["requests"]:
            req_metrics = self.metrics["requests"][request_id]
            req_metrics["tokens"]["prompt"] = prompt_tokens
            req_metrics["tokens"]["completion"] = completion_tokens
            req_metrics["tokens"]["total"] = prompt_tokens + completion_tokens
            
            # Mise à jour des totaux agrégés
            self.metrics["aggregated"]["total_tokens"]["prompt"] += prompt_tokens
            self.metrics["aggregated"]["total_tokens"]["completion"] += completion_tokens
            self.metrics["aggregated"]["total_tokens"]["total"] += (prompt_tokens + completion_tokens)
    
    def record_response_size(self, request_id: str, size: int):
        """
        Enregistre la taille de la réponse pour une requête
        
        Args:
            request_id: Identifiant de la requête
            size: Taille de la réponse en caractères
        """
        if request_id in self.metrics["requests"]:
            self.metrics["requests"][request_id]["response_size"] = size
    
    def end_request(self, request_id: str, duration: Optional[float] = None):
        """
        Enregistre la fin d'une requête
        
        Args:
            request_id: Identifiant de la requête
            duration: Durée en secondes (optionnel, calculée si non fournie)
        """
        if request_id not in self.metrics["requests"]:
            return
            
        now = time.time()
        req_metrics = self.metrics["requests"][request_id]
        req_metrics["end_time"] = now
        
        # Calcul de la durée si non fournie
        if duration is None:
            if req_metrics["start_time"] is not None:
                duration = now - req_metrics["start_time"]
            else:
                duration = 0
        
        # Conversion en millisecondes
        duration_ms = int(duration * 1000)
        req_metrics["duration_ms"] = duration_ms
        
        # Mise à jour des statistiques de latence
        self._durations_ms.append(duration_ms)
        self._update_latency_stats()
        
        # Mise à jour des compteurs
        self.metrics["aggregated"]["total_requests"] += 1
        
        # Mise à jour des métriques horaires et journalières
        self._update_time_based_metrics(req_metrics)
    
    def _update_latency_stats(self):
        """Met à jour les statistiques de latence"""
        if not self._durations_ms:
            return
            
        # Calcul de la moyenne
        avg_ms = sum(self._durations_ms) / len(self._durations_ms)
        self.metrics["aggregated"]["latency"]["avg_ms"] = avg_ms
        
        # Calcul des percentiles
        sorted_durations = sorted(self._durations_ms)
        n = len(sorted_durations)
        
        self.metrics["aggregated"]["latency"]["p50_ms"] = sorted_durations[int(n * 0.5)]
        self.metrics["aggregated"]["latency"]["p90_ms"] = sorted_durations[int(n * 0.9)]
        self.metrics["aggregated"]["latency"]["p99_ms"] = sorted_durations[int(n * 0.99)]
        
        # Limiter le nombre de durées conservées (pour la mémoire)
        if len(self._durations_ms) > 10000:
            self._durations_ms = self._durations_ms[-10000:]
    
    def _update_time_based_metrics(self, req_metrics: Dict[str, Any]):
        """
        Met à jour les métriques basées sur le temps
        
        Args:
            req_metrics: Métriques de la requête
        """
        if "end_time" not in req_metrics:
            return
            
        # Déterminer l'heure et le jour
        dt = datetime.fromtimestamp(req_metrics["end_time"], tz=timezone.utc)
        hour_key = dt.strftime("%Y-%m-%d %H:00")
        day_key = dt.strftime("%Y-%m-%d")
        
        # Mise à jour des métriques horaires
        if hour_key not in self.metrics["hourly"]:
            self.metrics["hourly"][hour_key] = {
                "count": 0,
                "cache_hits": 0,
                "avg_duration_ms": 0,
                "total_tokens": 0
            }
        
        hourly = self.metrics["hourly"][hour_key]
        hourly["count"] += 1
        
        if req_metrics.get("cache_hit", False):
            hourly["cache_hits"] += 1
            
        if "duration_ms" in req_metrics:
            # Mise à jour de la moyenne glissante
            n = hourly["count"]
            new_avg = hourly["avg_duration_ms"] * (n - 1) / n + req_metrics["duration_ms"] / n
            hourly["avg_duration_ms"] = new_avg
            
        if "tokens" in req_metrics and "total" in req_metrics["tokens"]:
            hourly["total_tokens"] += req_metrics["tokens"]["total"]
        
        # Mise à jour des métriques journalières (similaire aux horaires)
        if day_key not in self.metrics["daily"]:
            self.metrics["daily"][day_key] = {
                "count": 0,
                "cache_hits": 0,
                "avg_duration_ms": 0,
                "total_tokens": 0
            }
        
        daily = self.metrics["daily"][day_key]
        daily["count"] += 1
        
        if req_metrics.get("cache_hit", False):
            daily["cache_hits"] += 1
            
        if "duration_ms" in req_metrics:
            # Mise à jour de la moyenne glissante
            n = daily["count"]
            new_avg = daily["avg_duration_ms"] * (n - 1) / n + req_metrics["duration_ms"] / n
            daily["avg_duration_ms"] = new_avg
            
        if "tokens" in req_metrics and "total" in req_metrics["tokens"]:
            daily["total_tokens"] += req_metrics["tokens"]["total"]
    
    async def export_metrics(self):
        """Exporte les métriques dans des fichiers JSON"""
        try:
            # Conversion des sets en listes pour la sérialisation JSON
            export_metrics = self._prepare_metrics_for_export()
            
            # Export des métriques agrégées
            aggregated_file = os.path.join(self.export_dir, "aggregated_metrics.json")
            with open(aggregated_file, 'w', encoding='utf-8') as f:
                json.dump(export_metrics, f, indent=2)
                
            # Export des métriques temporelles
            timestamp = int(time.time())
            timeseries_file = os.path.join(self.export_dir, f"timeseries_{timestamp}.json")
            with open(timeseries_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "hourly": export_metrics["hourly"],
                    "daily": export_metrics["daily"]
                }, f, indent=2)
                
            logger.info(f"Métriques exportées avec succès: {self.metrics['aggregated']['total_requests']} requêtes au total")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'export des métriques: {str(e)}")
            return False
    
    def _prepare_metrics_for_export(self) -> Dict[str, Any]:
        """
        Prépare les métriques pour l'export en JSON
        
        Returns:
            Métriques préparées pour l'export
        """
        export_metrics = {
            "aggregated": self.metrics["aggregated"].copy(),
            "hourly": self.metrics["hourly"].copy(),
            "daily": self.metrics["daily"].copy(),
            "timestamp": time.time()
        }
        
        # Convertir les sets en listes
        for req_id, req_data in self.metrics["requests"].items():
            if isinstance(req_data.get("sources"), set):
                req_data["sources"] = list(req_data["sources"])
        
        return export_metrics
    
    def get_status(self) -> Dict[str, Any]:
        """
        Renvoie l'état actuel du collecteur de métriques
        
        Returns:
            Dictionnaire avec les informations d'état
        """
        status = {
            "initialized": self._initialized,
            "total_requests": self.metrics["aggregated"]["total_requests"],
            "total_cache_hits": self.metrics["aggregated"]["total_cache_hits"],
            "total_tokens": self.metrics["aggregated"]["total_tokens"]["total"],
            "avg_latency_ms": self.metrics["aggregated"]["latency"]["avg_ms"],
            "export_dir": self.export_dir
        }
        
        return status
    
    async def shutdown(self):
        """Arrête proprement le collecteur de métriques"""
        logger.info("Arrêt du collecteur de métriques...")
        
        # Exporter les métriques avant l'arrêt
        await self.export_metrics()
        
        # Annuler la tâche d'export périodique
        if self._export_task:
            self._export_task.cancel()
            try:
                await self._export_task
            except asyncio.CancelledError:
                pass
            
        logger.info("Collecteur de métriques arrêté avec succès")
