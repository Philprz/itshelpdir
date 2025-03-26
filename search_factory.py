# search_factory.py

import os
import logging
import time
from typing import Optional, Callable
import asyncio
from datetime import datetime

from configuration import logger, global_cache

class CircuitBreaker:
    """
    Implémentation du pattern Circuit Breaker pour protéger contre les erreurs répétées.
    Permet d'éviter d'appeler des services défaillants et de récupérer automatiquement.
    """
    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.logger = logging.getLogger(f'ITS_HELP.circuit_breaker.{name}')
        
    def record_success(self):
        """Enregistre un succès et réinitialise le compteur d'échec"""
        self.failure_count = 0
        if self.state == "HALF-OPEN":
            self.state = "CLOSED"
            self.logger.info(f"Circuit {self.name} fermé après succès en état half-open")
            
    def record_failure(self):
        """Enregistre un échec et ouvre le circuit si le seuil est atteint"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != "OPEN":
                self.logger.warning(f"Circuit {self.name} ouvert après {self.failure_count} échecs")
                self.state = "OPEN"
            
    def can_execute(self):
        """Vérifie si une opération peut être exécutée selon l'état du circuit"""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            # Vérifier si le temps de réinitialisation est écoulé
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF-OPEN"
                self.logger.info(f"Circuit {self.name} passé en half-open après {self.reset_timeout}s")
                return True
            return False
        elif self.state == "HALF-OPEN":
            return True
        return False
        
    def reset(self):
        """Réinitialise le circuit à son état fermé"""
        self.failure_count = 0
        self.state = "CLOSED"
        self.logger.info(f"Circuit {self.name} réinitialisé manuellement")
        
    def get_status(self):
        """Retourne l'état actuel du circuit pour monitoring"""
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time,
            "threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout
        }

async def with_circuit_breaker(circuit: CircuitBreaker, operation: Callable, 
                               fallback: Optional[Callable] = None, *args, **kwargs):
    """
    Exécute une opération avec protection par circuit breaker.
    
    Args:
        circuit: Instance de CircuitBreaker
        operation: Fonction/coroutine à exécuter
        fallback: Fonction/coroutine de repli en cas d'échec
        args, kwargs: Arguments à passer à l'opération
    """
    if not circuit.can_execute():
        if fallback:
            return await fallback(*args, **kwargs)
        raise RuntimeError(f"Circuit {circuit.name} ouvert, opération non exécutée")
        
    try:
        result = await operation(*args, **kwargs)
        circuit.record_success()
        return result
    except Exception as e:
        circuit.record_failure()
        logger.error(f"Erreur dans circuit {circuit.name}: {str(e)}")
        if fallback:
            return await fallback(*args, **kwargs)
        raise

class SearchClientFactory:
    """
    Factory pour la création et la gestion des clients de recherche.
    Centralise la gestion des dépendances et des instances.
    """

    def __init__(self):
        self.clients = {}
        self.qdrant_client = None
        self.openai_client = None
        self.embedding_service = None
        self.translation_service = None
        self.initialized = False
        self.logger = logging.getLogger('ITS_HELP.search.factory')
        
        # Circuit breakers pour les différents services
        self.circuit_breakers = {
            "qdrant": CircuitBreaker("qdrant", failure_threshold=3, reset_timeout=30),
            "openai": CircuitBreaker("openai", failure_threshold=3, reset_timeout=60),
            "client_creation": CircuitBreaker("client_creation", failure_threshold=5, reset_timeout=120),
            "client_import": CircuitBreaker("client_import", failure_threshold=2, reset_timeout=300)
        }

        # Collections par défaut
        self.default_collections = {
            'jira': os.getenv('QDRANT_COLLECTION_JIRA', 'JIRA'),
            'zendesk': os.getenv('QDRANT_COLLECTION_ZENDESK', 'ZENDESK'),
            'confluence': os.getenv('QDRANT_COLLECTION_CONFLUENCE', 'CONFLUENCE'),
            'netsuite': os.getenv('QDRANT_COLLECTION_NETSUITE', 'NETSUITE'),
            'netsuite_dummies': os.getenv('QDRANT_COLLECTION_NETSUITE_DUMMIES', 'NETSUITE_DUMMIES'),
            'sap': os.getenv('QDRANT_COLLECTION_SAP', 'SAP'),
            'erp': os.getenv('QDRANT_COLLECTION_ERP', 'ERP')
        }

    async def initialize(self):
        """Initialise tous les clients et services nécessaires avec gestion des erreurs"""
        if self.initialized:
            self.logger.info("Factory déjà initialisée - ignoré")
            return
            
        self.logger.info("Initialisation des clients et services...")
        
        # Initialisation des composants de base avec gestion des erreurs
        await self._initialize_qdrant_client()
        await self._initialize_openai_client()
        await self._initialize_services()
        
        # Garde-fou: si les composants de base ne sont pas initialisés correctement,
        # utiliser des composants de fallback pour permettre un fonctionnement dégradé
        if not self.qdrant_client:
            self.logger.warning("QdrantClient non initialisé - création d'un fallback")
            self.qdrant_client = self._create_fallback_qdrant_client()
            
        if not self.openai_client:
            self.logger.warning("OpenAI client non initialisé - création d'un fallback")
            self.openai_client = self._create_fallback_openai_client()
            
        if not self.embedding_service:
            self.logger.warning("EmbeddingService non initialisé - création d'un fallback")
            self.embedding_service = self._create_fallback_embedding_service()
            
        if not self.translation_service:
            self.logger.warning("TranslationService non initialisé - création d'un fallback")
            self.translation_service = self._create_fallback_translation_service()
        
        # Création des clients de recherche spécialisés en utilisant les nouvelles méthodes
        # avec fallback automatique en cas d'erreur
        results = await asyncio.gather(
            self._initialize_client("jira", "jira"),
            self._initialize_client("zendesk", "zendesk"),
            self._initialize_client("erp", "erp"),
            self._initialize_client("netsuite", "netsuite"),
            self._initialize_client("netsuite_dummies", "netsuite_dummies"),
            self._initialize_client("sap", "sap"),
            self._initialize_client("confluence", "confluence"),
            return_exceptions=True
        )
        
        # Traitement des résultats
        client_names = ["jira", "zendesk", "erp", "netsuite", "netsuite_dummies", "sap", "confluence"]
        for i, result in enumerate(results):
            client_name = client_names[i] if i < len(client_names) else f"client_{i}"
            
            if isinstance(result, Exception):
                self.logger.error(f"Erreur initialisation {client_name}: {str(result)}")
                # Créer un client de fallback en cas d'erreur
                try:
                    self.clients[client_name] = self._create_fallback_client(client_name, client_name)
                except Exception as e:
                    self.logger.error(f"Erreur critique sur fallback {client_name}: {str(e)}")
            else:
                if result:
                    self.clients[client_name] = result
                else:
                    # Créer un client de fallback si le résultat est None
                    self.clients[client_name] = self._create_fallback_client(client_name, client_name)
        
        # Mise à jour du statut d'initialisation
        success_count = sum(1 for client in self.clients.values() if not isinstance(client, Exception))
        self.logger.info(f"Factory initialisée: {success_count}/{len(client_names)} clients OK")
        
        self.initialized = True
        return

    async def get_client(self, client_type: str, collection_name: str = None, fallback_enabled: bool = True):
        """
        Récupère un client de recherche initialisé.
        
        Args:
            client_type: Type de client demandé (jira, zendesk, etc.)
            collection_name: Nom de collection spécifique (optionnel)
            fallback_enabled: Si True, retourne un client de fallback en cas d'erreur
            
        Returns:
            Client de recherche ou None
        """
        # Standardisation des noms
        client_type = client_type.lower().strip()
        
        # Utilisation du cache
        cache_key = f"client:{client_type}:{collection_name or 'default'}"
        
        # Si présent en cache, retourner directement
        if cache_key in self.clients:
            client = self.clients[cache_key]
            self.logger.debug(f"Client {client_type} récupéré depuis le cache")
            return client
            
        # Déterminer le nom de collection adapté
        # Si collection_name n'est pas spécifié, utiliser la valeur par défaut basée sur client_type
        if not collection_name:
            # Majuscules pour le nom de collection par convention
            collection_name = client_type.upper()
            
        # Cas spéciaux pour certains types de clients
        if client_type == 'erp':
            # Pour ERP, on utilise généralement NETSUITE comme collection
            collection_name = "NETSUITE"
        elif client_type == 'netsuite_dummies':
            # Pour les documents fictifs NetSuite
            collection_name = "NETSUITE_DUMMIES"
        
        self.logger.info(f"Recherche client {client_type} (collection: {collection_name})")
        
        try:
            # 1. Essayer d'obtenir un client déjà initialisé depuis le cache
            if client_type in self.clients and self.clients[client_type]:
                client = self.clients[client_type]
                self.logger.info(f"Client {client_type} trouvé dans le cache")
                return client
            
            # 2. Essayer via les classes standards
            client_types = await self._get_client_types_safe()
            client_class = client_types.get(client_type)
            
            if client_class:
                self.logger.info(f"Classe client standard trouvée pour {client_type}")
                # Initialiser le client
                client = await self._initialize_client(client_type, collection_name, fallback_enabled)
                return client
            
            # 3. Essayer l'import dynamique depuis les modules qdrant_*
            client_class = await self._try_dynamic_import_client(client_type)
            
            if client_class:
                self.logger.info(f"Classe client dynamique trouvée pour {client_type}")
                
                # Créer et initialiser le client
                try:
                    client = client_class(
                        collection_name=collection_name.upper(),
                        qdrant_client=self.qdrant_client,
                        embedding_service=self.embedding_service,
                        translation_service=self.translation_service
                    )
                    
                    # Mettre en cache
                    self.clients[cache_key] = client
                    
                    return client
                    
                except Exception as e:
                    self.logger.error(f"Erreur lors de l'initialisation du client dynamique {client_type}: {str(e)}")
                    if fallback_enabled:
                        return self._create_fallback_client(client_type, collection_name)
                    return None
            
            # 4. Si tout échoue et que le fallback est activé, créer un client de fallback
            if fallback_enabled:
                self.logger.warning(f"Aucun client disponible pour {client_type}, création d'un fallback")
                return self._create_fallback_client(client_type, collection_name)
            
            # Sinon, retourner None
            self.logger.error(f"Aucun client disponible pour {client_type} et fallback désactivé")
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération du client {client_type}: {str(e)}")
            
            # Si le fallback est activé, retourner un client de fallback
            if fallback_enabled:
                return self._create_fallback_client(client_type, collection_name)
            
            return None

    async def _initialize_client(self, client_type: str, collection_name: str, fallback_enabled: bool = True):
        """
        Initialise un client de recherche spécifique avec gestion des erreurs.
        
        Args:
            client_type: Type de client à initialiser (jira, zendesk, etc.)
            collection_name: Nom de la collection à utiliser
            fallback_enabled: Si True, un client de fallback sera créé en cas d'erreur
            
        Returns:
            Le client initialisé ou None en cas d'échec
        """
        # Vérifications de base
        if not self.qdrant_client or not self.embedding_service:
            self.logger.error(f"Impossible d'initialiser le client {client_type}: dépendances manquantes")
            return None
            
        try:
            client_types = await self._get_client_types_safe()
            
            # Obtenir la classe du client
            client_class = client_types.get(client_type)
            if not client_class:
                self.logger.error(f"Type de client inconnu: {client_type}")
                return None
            
            # Convertir le nom de collection en majuscules pour correspondre aux collections réelles
            collection_name_upper = collection_name.upper()
            self.logger.info(f"Conversion du nom de collection '{collection_name}' en '{collection_name_upper}'")
                
            # Créer l'instance avec les paramètres appropriés
            # NOTE: Nouvelle interface standardisée - aucun besoin d'adaptateur
            client = client_class(
                collection_name=collection_name_upper,
                qdrant_client=self.qdrant_client,
                embedding_service=self.embedding_service,
                translation_service=self.translation_service
            )
            
            # Vérifier que le client implémente l'interface requise
            required_methods = ['recherche_intelligente', 'valider_resultat', 'get_source_name', 'format_for_message']
            for method in required_methods:
                if not hasattr(client, method):
                    raise AttributeError(f"Client {client_type} sans méthode requise {method}")
            
            self.logger.info(f"Client {client_type} initialisé avec succès")
            return client
        except ImportError as e:
            self.logger.error(f"Erreur d'importation pour le client {client_type}: {str(e)}")
            self.circuit_breakers["client_import"].record_failure()
            if fallback_enabled:
                return self._create_fallback_client(client_type, collection_name)
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation du client {client_type}: {str(e)}")
            self.circuit_breakers["client_creation"].record_failure()
            if fallback_enabled:
                return self._create_fallback_client(client_type, collection_name)
            return None
    
    def _create_fallback_client(self, client_type: str, collection_name: str):
        """
        Crée un client de fallback en cas d'erreur lors de l'initialisation du vrai client.
        Utilise une implémentation simplifiée qui enregistre les erreurs mais ne bloque pas l'exécution.
        
        Args:
            client_type: Type de client pour lequel créer un fallback
            collection_name: Nom de la collection
            
        Returns:
            Un client de fallback minimal
        """
        # Import local pour éviter les cycles d'importation
        from search.core.client_base import GenericSearchClient
        
        class FallbackSearchClient(GenericSearchClient):
            def __init__(self, client_type, original_error, logger):
                self.client_type = client_type
                self.original_error = original_error
                self.logger = logger
                self.error_logged = False
                
            def get_source_name(self) -> str:
                return f"FALLBACK_{self.client_type.upper()}"
                
            async def recherche_intelligente(self, *args, **kwargs):
                if not self.error_logged:
                    self.logger.warning(f"Utilisation du client de fallback pour {self.client_type}")
                    self.error_logged = True
                return []
                
            def valider_resultat(self, result):
                return False
                
            async def format_for_message(self, results):
                return f"Aucun résultat disponible pour {self.client_type.upper()} (client en mode dégradé)."
        
        error_msg = f"Client {client_type} non disponible - utilisation du fallback"
        self.logger.warning(error_msg)
        
        fallback = FallbackSearchClient(client_type, error_msg, self.logger)
        self.logger.info(f"Client de fallback créé pour {client_type}")
        return fallback
    
    def adapt_legacy_client(self, client, client_type=None):
        """
        Adapte un client provenant d'un module externe à l'interface standard.
        Détecte le type de client et applique l'adaptateur approprié si nécessaire.
        
        Args:
            client: Le client à adapter
            client_type: Type de client (optionnel, pour le logging)
            
        Returns:
            Client adapté ou le client original s'il est déjà compatible
        """
        # Si le client est None, retourner None
        if client is None:
            return None
            
        # Si le client a déjà la méthode recherche_intelligente avec une signature compatible,
        # vérifier s'il a besoin d'être adapté
        if hasattr(client, 'recherche_intelligente'):
            try:
                # Vérifier la signature de la méthode recherche_intelligente
                import inspect
                sig = inspect.signature(client.recherche_intelligente)
                params = list(sig.parameters.keys())
                
                # Si la méthode a les paramètres standards (sans query_vector), on peut l'utiliser directement
                if len(params) >= 2 and 'question' in sig.parameters and 'query_vector' not in sig.parameters:
                    self.logger.info(f"Client {client_type or type(client).__name__} déjà compatible, pas besoin d'adaptateur")
                    return client
            except (ValueError, TypeError, AttributeError) as e:
                self.logger.debug(f"Erreur lors de l'inspection de la signature: {str(e)}")
        
        # Vérifier si c'est un client Qdrant (a les méthodes recherche_similaire ou recherche_avec_filtres)
        needs_adapter = (
            hasattr(client, 'recherche_similaire') or 
            hasattr(client, 'recherche_avec_filtres') or
            not hasattr(client, 'recherche_intelligente')
        )
        
        if needs_adapter:
            self.logger.info(f"Adaptation du client {client_type or type(client).__name__} avec QdrantSearchClientAdapter")
            return self.QdrantSearchClientAdapter(
                wrapped_client=client,
                embedding_service=self.embedding_service,
                logger=self.logger
            )
        
        # Si le client ne correspond à aucun cas, le retourner tel quel
        return client

    class QdrantSearchClientAdapter:
        """
        Adaptateur pour standardiser l'interface entre les clients Qdrant spécifiques
        et l'interface AbstractSearchClient.
        
        Cette version traite le problème fondamental: l'erreur 'Unknown arguments: ['query_vector']'
        en redirigeant correctement les appels aux bonnes méthodes.
        """
        def __init__(self, wrapped_client, embedding_service, logger):
            # Le client réel est la classe client (JiraSearchClient, etc.)
            self.client = wrapped_client
            # Nous extrayons le client Qdrant et le stockons séparément
            self.qdrant_client = getattr(wrapped_client, 'client', None)
            self.embedding_service = embedding_service
            self.logger = logger
            
            # Copier les attributs essentiels du client original
            self.collection_name = getattr(wrapped_client, 'collection_name', None)
            self.processor = getattr(wrapped_client, 'processor', None)
            self.required_fields = getattr(wrapped_client, 'required_fields', [])
        
        def get_source_name(self):
            """Délègue au client encapsulé"""
            if hasattr(self.client, 'get_source_name'):
                return self.client.get_source_name()
            elif hasattr(self.client, 'get_source_prefix'):
                return self.client.get_source_prefix()
            return "UNKNOWN"
            
        def valider_resultat(self, result):
            """Délègue la validation au client encapsulé"""
            if hasattr(self.client, 'valider_resultat'):
                return self.client.valider_resultat(result)
            return True
            
        async def format_for_slack(self, result):
            """Délègue le formatage au client encapsulé"""
            if hasattr(self.client, 'format_for_slack'):
                return await self.client.format_for_slack(result)
            return None
        
        async def recherche_intelligente(self, 
                                         question: str, 
                                         client_name: Optional[str] = None, 
                                         date_debut: Optional[datetime] = None, 
                                         date_fin: Optional[datetime] = None,
                                         limit: int = 10,
                                         score_threshold: float = 0.0,
                                         vector_field: str = "vector"):
            """
            Méthode standardisée de recherche intelligente qui résout le problème 
            fondamental des appels 'query_vector' incorrects.
            
            1. Nous obtenons l'embedding avec le service approprié
            2. Nous construisons le filtre si nécessaire
            3. IMPORTANT: Nous appelons la méthode recherche_similaire ou recherche_avec_filtres
               du BaseQdrantSearch sous-jacent avec les bons arguments
            """
            self.logger.info(f"Recherche intelligente via QdrantSearchClientAdapter pour {self.get_source_name()}")
            
            try:
                # Étape 1: Générer l'embedding pour la question
                vector = None
                if self.embedding_service:
                    try:
                        vector = await self.embedding_service.get_embedding(question)
                    except Exception as e:
                        self.logger.error(f"Erreur génération embedding: {str(e)}")
                
                # Vecteur de secours si l'embedding échoue
                if not vector:
                    self.logger.warning("Utilisation d'un vecteur factice")
                    vector = [0.1] * 1536  # Dimension standard OpenAI
                
                # Étape 2: Construction des filtres si nécessaire
                filtres = {}
                if client_name:
                    filtres['client'] = client_name
                if date_debut or date_fin:
                    filtres['dates'] = {'debut': date_debut, 'fin': date_fin}
                
                results = []
                
                # Étape 3: Recherche via les méthodes spécifiques du client
                # Note critique: NE PAS appeler directement les méthodes du client Qdrant!
                
                # Stratégie 1: Essayer la méthode recherche_intelligente native
                if hasattr(self.client, 'recherche_intelligente'):
                    try:
                        self.logger.info(f"Utilisation de la recherche_intelligente native pour {self.get_source_name()}")
                        return await self.client.recherche_intelligente(
                            question=question,
                            client_name=client_name,
                            date_debut=date_debut,
                            date_fin=date_fin,
                            limit=limit,
                            score_threshold=score_threshold,
                            vector_field=vector_field
                        )
                    except Exception as e:
                        self.logger.warning(f"Échec recherche_intelligente native: {str(e)}")
                
                # Stratégie 2: Vérifier si nous avons besoin d'utiliser un filtre
                if filtres and hasattr(self.client, 'recherche_avec_filtres'):
                    try:
                        self.logger.info(f"Utilisation de recherche_avec_filtres pour {self.get_source_name()}")
                        # MODIFICATION CRITIQUE: Remplacer les appels directs au client Qdrant
                        # par des appels à la méthode du client emballé
                        results = self.client.recherche_avec_filtres(
                            query_vector=vector,
                            filtres=filtres,
                            limit=limit
                        )
                        if results:
                            return results
                    except Exception as e:
                        self.logger.error(f"Erreur recherche avec filtres: {str(e)}")
                
                # Stratégie 3: Recherche similaire simple en dernier recours
                if hasattr(self.client, 'recherche_similaire'):
                    try:
                        self.logger.info(f"Utilisation de recherche_similaire pour {self.get_source_name()}")
                        # MODIFICATION CRITIQUE: Remplacer les appels directs au client Qdrant
                        # par des appels à la méthode du client emballé
                        results = self.client.recherche_similaire(
                            query_vector=vector,
                            limit=limit
                        )
                    except Exception as e:
                        self.logger.error(f"Erreur recherche similaire: {str(e)}")
                
                # Filtrage par score si nécessaire
                if score_threshold > 0 and results:
                    results = [r for r in results if getattr(r, 'score', 0) >= score_threshold]
                
                return results
                
            except Exception as e:
                self.logger.error(f"Erreur globale dans recherche_intelligente pour {self.get_source_name()}: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                return []

        # Méthodes utilitaires supplémentaires pour compatibilité

        def __getattr__(self, name):
            """
            Méthode de fallback pour déléguer les appels inconnus au client encapsulé
            
            Args:
                name: Nom de l'attribut ou de la méthode recherchée
                
            Returns:
                L'attribut ou la méthode du client encapsulé
                
            Raises:
                AttributeError: Si l'attribut n'existe pas
            """
            # Déléguer aux attributs du client
            if hasattr(self.client, name):
                return getattr(self.client, name)
            
            # Lever une exception pour les attributs inconnus
            raise AttributeError(f"L'attribut '{name}' n'existe ni dans l'adaptateur ni dans le client")
    
    def _get_client_types(self):
        """Import dynamique des types de clients pour éviter les imports circulaires"""
        from search_clients import (
            JiraSearchClient,
            ZendeskSearchClient,
            ConfluenceSearchClient,
            NetsuiteSearchClient,
            NetsuiteDummiesSearchClient,
            SapSearchClient,
            ERPSearchClient
        )

        # Création des mappings vers les classes
        return {
            'jira': JiraSearchClient,
            'zendesk': ZendeskSearchClient,
            'confluence': ConfluenceSearchClient,
            'netsuite': NetsuiteSearchClient,
            'netsuite_dummies': NetsuiteDummiesSearchClient,
            'sap': SapSearchClient,
            'erp': ERPSearchClient
        }
    
    async def _get_client_types_safe(self):
        """Méthode sûre pour obtenir les types de clients avec gestion des erreurs."""
        try:
            return self._get_client_types()
        except Exception as e:
            self.logger.error(f"Erreur lors de l'obtention des types de clients: {str(e)}")
            return {
                'jira': None,
                'zendesk': None,
                'confluence': None,
                'netsuite': None,
                'netsuite_dummies': None,
                'sap': None,
                'erp': None
            }
            
    async def _try_dynamic_import_client(self, client_type):
        """
        Tente d'importer un client dynamiquement à partir de fichiers qdrant_*.py.
        Utilisé comme fallback si les clients standards ne sont pas disponibles.
        
        Args:
            client_type: Type de client à importer (e.g. 'jira', 'zendesk')
            
        Returns:
            Classe du client ou None si non trouvée
        """
        try:
            # Tenter d'importer depuis un module qdrant_*
            module_name = f"qdrant_{client_type}"
            self.logger.info(f"Tentative d'import dynamique depuis {module_name}")
            
            # Import dynamique du module
            import importlib
            module = importlib.import_module(module_name)
            
            # Chercher la classe QdrantClient dans le module
            class_name = f"Qdrant{client_type.capitalize()}Client"
            if hasattr(module, class_name):
                client_class = getattr(module, class_name)
                self.logger.info(f"Client {class_name} trouvé dans {module_name}")
                return client_class
                
            # Si on ne trouve pas la classe spécifique, chercher QdrantClient
            if hasattr(module, "QdrantClient"):
                client_class = getattr(module, "QdrantClient")
                self.logger.info(f"Client générique QdrantClient trouvé dans {module_name}")
                return client_class
                
            self.logger.warning(f"Aucune classe client trouvée dans {module_name}")
            return None
            
        except ImportError as e:
            self.logger.debug(f"Module {module_name} non trouvé: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Erreur lors de l'import dynamique de {client_type}: {str(e)}")
            return None
    
    def _get_fallback_client_types(self):
        """Crée des types de clients de repli en cas d'erreur d'import"""
        from search_base import AbstractSearchClient

        class DummySearchClient(AbstractSearchClient):
            async def format_for_slack(self, result):
                return {}

            def valider_resultat(self, result):
                return False
                
            async def search(self, *args, **kwargs):
                return []

        dummy_types = {source: DummySearchClient for source in self.default_collections.keys()}
        return dummy_types
    
    def get_circuit_breaker_status(self):
        """Retourne l'état de tous les circuit breakers pour monitoring"""
        return {name: cb.get_status() for name, cb in self.circuit_breakers.items()}
    
    def reset_circuit_breakers(self):
        """Réinitialise tous les circuit breakers"""
        for cb in self.circuit_breakers.values():
            cb.reset()
        return {"status": "reset", "count": len(self.circuit_breakers)}

    async def _initialize_qdrant_client(self):
        """Initialise le client Qdrant avec gestion d'erreurs robuste."""
        try:
            # Vérifier si le circuit qdrant est fermé
            if self.circuit_breakers["qdrant"].can_execute():
                try:
                    # Configuration complète du client
                    from qdrant_client import QdrantClient
                    qdrant_url = os.getenv('QDRANT_URL')
                    qdrant_api_key = os.getenv('QDRANT_API_KEY')
                    
                    if not qdrant_url:
                        raise ValueError("Variable d'environnement QDRANT_URL non définie")
                    
                    self.logger.info(f"Connexion à Qdrant: {qdrant_url}")
                    self.qdrant_client = QdrantClient(
                        url=qdrant_url,
                        api_key=qdrant_api_key,
                        timeout=30  # Timeout augmenté
                    )
                    
                    # Test de connexion
                    collections = self.qdrant_client.get_collections()
                    self.logger.info(f"Connexion Qdrant réussie. Collections disponibles: {len(collections.collections) if hasattr(collections, 'collections') else 'inconnu'}")
                    self.circuit_breakers["qdrant"].record_success()
                    
                except Exception as e:
                    self.circuit_breakers["qdrant"].record_failure()
                    self.logger.error(f"Erreur connexion Qdrant: {str(e)}")
                    raise
            else:
                self.logger.warning("Circuit Qdrant ouvert, utilisation du client minimal")
                
        except Exception as e:
            self.logger.error(f"Erreur d'initialisation Qdrant, création d'un client minimal: {str(e)}")
            
        # Créer un client minimal en cas d'échec (toujours, pour garantir un fallback)
        if not self.qdrant_client:
            self.logger.warning("Utilisation d'un client Qdrant minimal (fallback)")
            # Création d'un objet qui implémente les méthodes minimales requises
            from types import SimpleNamespace
            self.qdrant_client = SimpleNamespace()
            self.qdrant_client.get_collections = lambda: SimpleNamespace(collections=[])
            self.qdrant_client.search = lambda **kwargs: []
            
    async def _initialize_openai_client(self):
        """Initialise le client OpenAI avec gestion d'erreurs robuste."""
        try:
            # Vérifier si le circuit openai est fermé
            if self.circuit_breakers["openai"].can_execute():
                try:
                    # Configuration complète du client
                    from openai import AsyncOpenAI
                    openai_api_key = os.getenv('OPENAI_API_KEY')
                    
                    if not openai_api_key:
                        raise ValueError("Variable d'environnement OPENAI_API_KEY non définie")
                    
                    self.logger.info("Initialisation du client OpenAI")
                    self.openai_client = AsyncOpenAI(
                        api_key=openai_api_key,
                        timeout=30.0  # Timeout explicite
                    )
                    
                    # Un test simple serait idéal ici, mais nous le ferons lors de la première utilisation
                    self.circuit_breakers["openai"].record_success()
                    
                except Exception as e:
                    self.circuit_breakers["openai"].record_failure()
                    self.logger.error(f"Erreur initialisation OpenAI client: {str(e)}")
                    raise
            else:
                self.logger.warning("Circuit OpenAI ouvert, utilisation du client minimal")
                
        except Exception as e:
            self.logger.error(f"Erreur d'initialisation OpenAI, création d'un client minimal: {str(e)}")
            
        # Créer un client minimal en cas d'échec (toujours, pour garantir un fallback)
        if not self.openai_client:
            self.logger.warning("Utilisation d'un client OpenAI minimal (fallback)")
            # Création d'un client avec une clé factice
            self.openai_client = AsyncOpenAI(api_key="dummy-key-for-fallback-initialization")
            
    async def _initialize_services(self):
        """Initialise les services d'embedding et de traduction."""
        try:
            # Import des classes en local pour éviter les problèmes d'import circulaire
            from embedding_service import EmbeddingService
            from translation_service import TranslationService
                
            if not self.embedding_service:
                self.embedding_service = EmbeddingService(
                    openai_client=self.openai_client,
                    model='text-embedding-ada-002',
                    l2_cache=global_cache
                )
                
            if not self.translation_service:
                self.translation_service = TranslationService(
                    openai_client=self.openai_client,
                    cache=global_cache
                )
                
        except Exception as e:
            self.logger.error(f"Erreur initialisation des services: {str(e)}")
            # Création de services minimaux en cas d'échec
            if not self.embedding_service:
                self.embedding_service = self._create_fallback_embedding_service()
            if not self.translation_service:
                self.translation_service = self._create_fallback_translation_service()
                
    def _create_fallback_qdrant_client(self):
        """
        Crée un client Qdrant de fallback qui implémente l'interface minimale requise.
        Ce client simule les réponses sans effectuer de vraies requêtes pour permettre
        un fonctionnement dégradé de l'application.
        
        Returns:
            Un objet qui implémente l'interface minimale de QdrantClient
        """
        class FallbackQdrantClient:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                
            async def search(self, collection_name, **kwargs):
                if not self.error_logged:
                    self.logger.warning(f"Utilisation du client Qdrant de fallback pour {collection_name}")
                    self.error_logged = True
                return []
                
            def get_collections(self):
                return []
                
            def get_collection(self, collection_name):
                return {"status": "fallback"}
                
            async def create_payload_index(self, *args, **kwargs):
                return None
                
            async def upload_collection(self, *args, **kwargs):
                return None
                
            async def upload_points(self, *args, **kwargs):
                return None
                
            async def scroll(self, *args, **kwargs):
                return ([], None)
                
            def close(self):
                pass
                
        self.logger.info("Création d'un client Qdrant de fallback")
        return FallbackQdrantClient(self.logger)
        
    def _create_fallback_openai_client(self):
        """
        Crée un client OpenAI de fallback qui implémente l'interface minimale requise.
        Ce client simule les réponses sans effectuer de vraies requêtes API pour permettre
        un fonctionnement dégradé de l'application.
        
        Returns:
            Un objet qui implémente l'interface minimale d'AsyncOpenAI
        """
        class FallbackEmbeddingsClient:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                
            async def create(self, *args, **kwargs):
                if not self.error_logged:
                    self.logger.warning("Utilisation du client Embeddings de fallback")
                    self.error_logged = True
                return {"data": [{"embedding": [0.0] * 384}], "model": "fallback-model"}
                
        class FallbackChatClient:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                
            async def create(self, *args, **kwargs):
                if not self.error_logged:
                    self.logger.warning("Utilisation du client Chat de fallback")
                    self.error_logged = True
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "Je ne peux pas répondre pour le moment car le service est indisponible."
                            },
                            "finish_reason": "fallback"
                        }
                    ],
                    "model": "fallback-model"
                }
        
        class FallbackOpenAIClient:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                self.embeddings = FallbackEmbeddingsClient(logger)
                self.chat = FallbackChatClient(logger)
                
        self.logger.info("Création d'un client OpenAI de fallback")
        return FallbackOpenAIClient(self.logger)
        
    def _create_fallback_embedding_service(self):
        """
        Crée un service d'embedding de fallback qui implémente l'interface minimale requise.
        
        Returns:
            Un objet qui implémente l'interface minimale d'EmbeddingService
        """
        class FallbackEmbeddingService:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                self.metrics = {
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "api_calls": 0,
                    "errors": 0,
                    "total_requests": 0
                }
                self.circuit_breaker = CircuitBreaker("embedding_fallback")
                
            async def get_embedding(self, text, force_refresh=False):
                if not self.error_logged:
                    self.logger.warning("Utilisation du service Embedding de fallback")
                    self.error_logged = True
                
                self.metrics["total_requests"] += 1
                self.metrics["cache_hits"] += 1  # Simuler un hit de cache
                
                return [0.0] * 384  # Vecteur d'embedding nul de dimension 384
                
            def _get_cache_key(self, text):
                return hash(text)
            
            def get_metrics(self):
                """Retourne les métriques du service."""
                return self.metrics
            
            def reset_metrics(self):
                """Réinitialise les métriques."""
                self.metrics = {
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "api_calls": 0,
                    "errors": 0,
                    "total_requests": 0
                }
                
            async def warm_cache(self, texts):
                """Simule un préchauffage du cache."""
                self.logger.info(f"Simulation de préchauffage du cache pour {len(texts)} textes")
                return len(texts)
                
        self.logger.info("Création d'un service Embedding de fallback")
        return FallbackEmbeddingService(self.logger)
        
    def _create_fallback_translation_service(self):
        """
        Crée un service de traduction de fallback qui implémente l'interface minimale requise.
        
        Returns:
            Un objet qui implémente l'interface minimale de TranslationService
        """
        class FallbackTranslationService:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                
            async def detect_language(self, text):
                return "fr"
                
            async def translate(self, text, target_lang="en"):
                if not self.error_logged:
                    self.logger.warning("Utilisation du service Translation de fallback")
                    self.error_logged = True
                return text  # On retourne le texte tel quel
                
        self.logger.info("Création d'un service Translation de fallback")
        return FallbackTranslationService(self.logger)
    
# Instance globale
search_factory = SearchClientFactory()