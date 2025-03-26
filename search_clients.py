from typing import Dict, Optional, Any
from datetime import datetime
from search_base import AbstractSearchClient, DefaultResultProcessor
from configuration import logger


class GenericSearchClient(AbstractSearchClient):
    """
    Classe générique servant de pont entre AbstractSearchClient et les clients spécifiques.
    Implémente les méthodes communes à tous les clients de recherche.
    """
    
    def recherche_similaire(self, query_vector, limit=5):
        """
        Méthode de recherche par similarité vectorielle simple.
        
        Args:
            query_vector: Vecteur d'embedding pour la recherche
            limit: Nombre maximum de résultats à retourner
            
        Returns:
            Liste des résultats similaires
        """
        try:
            self.logger.info(f"Recherche similaire dans {self.collection_name}")
            resultats = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit
            )
            return resultats
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche similaire: {str(e)}")
            return []
    
    def recherche_avec_filtres(self, query_vector, filtres: dict, limit=5):
        """
        Méthode de recherche par similarité vectorielle avec filtres supplémentaires.
        
        Args:
            query_vector: Vecteur d'embedding pour la recherche
            filtres: Dictionnaire des filtres à appliquer
            limit: Nombre maximum de résultats à retourner
            
        Returns:
            Liste des résultats filtrés
        """
        try:
            self.logger.info(f"Recherche avec filtres: {filtres}")
            # Construire le filtre Qdrant si la méthode existe
            filter_obj = None
            if hasattr(self, 'construire_filtre'):
                filter_obj = self.construire_filtre(filtres)
            
            resultats = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=filter_obj,
                limit=limit
            )
            self.logger.info(f"Résultats trouvés: {len(resultats)}")
            # Filtrer par score si nécessaire (peut être surchargé par les sous-classes)
            min_score = 0.45  # Score minimum par défaut
            return [r for r in resultats if hasattr(r, 'score') and r.score >= min_score]
        except Exception as e:
            self.logger.error(f"Erreur recherche filtrée: {str(e)}")
            return []


class JiraSearchClient(GenericSearchClient):
    """Client de recherche spécialisé pour les tickets Jira."""
    
    def __init__(self, collection_name, qdrant_client, embedding_service, translation_service=None):
        super().__init__(collection_name, qdrant_client, embedding_service)
        self.translation_service = translation_service
        self.required_fields = ['key', 'summary', 'content', 'client']
        self.processor = DefaultResultProcessor()  # Utilisation du processeur par défaut

    def get_source_name(self) -> str:
        """Retourne le nom de la source de données."""
        return "JIRA"

    def valider_resultat(self, result: Any) -> bool:
        """Valide qu'un résultat Jira est exploitable."""
        try:
            payload = self.processor.extract_payload(result)
            score = self.processor.extract_score(result)

            # Vérification des champs requis avec logging détaillé
            missing_fields = [field for field in self.required_fields if not payload.get(field)]
            if missing_fields:
                logger.debug(f"Champs manquants dans le résultat: {missing_fields}")
                return False

            # Vérification du score minimum
            return score >= 0.45

        except Exception as e:
            logger.error(f"Erreur validation résultat Jira: {str(e)}")
            return False

    async def format_for_slack(self, result: Any) -> Optional[Dict]:
        """Formate un résultat Jira pour affichage dans Slack."""
        try:
            payload = self.processor.extract_payload(result)
            if not payload:
                logger.warning("Payload vide ou invalide pour résultat Jira")
                return None
                
            score = self.processor.extract_score(result)

            # Validation des champs recommandés (mais non obligatoires)
            if not any(payload.get(field) for field in ['key', 'summary']):
                logger.warning(f"Champs importants manquants dans le ticket Jira: {list(payload.keys())}")
                # On continue avec des valeurs par défaut plutôt que de retourner None

            # Calcul de la fiabilité basée sur le score
            score_percent = round(score * 100)
            fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"

            try:
                # Récupération des dates de façon sécurisée
                created_date, updated_date = self._format_dates(payload)
            except Exception as date_error:
                logger.warning(f"Erreur formatage dates Jira: {str(date_error)}")
                created_date, updated_date = 'N/A', 'N/A'

            # Troncature du contenu
            content = str(payload.get('content', ''))
            content = (content[:497] + "...") if len(content) > 500 else content

            # Construction du message formaté
            message = (
                f"*JIRA-{payload.get('key', 'N/A')}* - {payload.get('summary', 'Sans titre')}\n"
                f"Client: {payload.get('client', 'N/A')} - {fiabilite} {score_percent}%\n"
                f"Status: {payload.get('resolution', 'En cours')}\n"
                f"Assigné à: {payload.get('assignee', 'Non assigné')}\n"
                f"Créé le: {created_date} - Maj: {updated_date}\n"
                f"Description: {content}\n"
                f"URL: {payload.get('url', 'N/A')}"
            )

            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }
        except Exception as e:
            logger.error(f"Erreur format Jira: {str(e)}")
            return None

    def _format_dates(self, payload: Dict) -> tuple:
        """Formate les dates pour l'affichage."""
        try:
            created = payload.get('created')
            updated = payload.get('updated')

            def format_date(date_str):
                if not date_str:
                    return 'N/A'
                # La méthode normalize_date retourne déjà une chaîne formatée, pas besoin d'appeler strftime
                return self.processor.normalize_date(date_str)

            return format_date(created), format_date(updated)

        except Exception as e:
            logger.error(f"Erreur formatage dates: {str(e)}")
            return 'N/A', 'N/A'

    async def recherche_intelligente(self, 
                                    question: str, 
                                    client_name: Optional[str] = None, 
                                    date_debut: Optional[datetime] = None, 
                                    date_fin: Optional[datetime] = None,
                                    limit: int = 10,
                                    score_threshold: float = 0.0,
                                    vector_field: str = "vector"):
        """
        Implémentation de la méthode de recherche intelligente pour Jira.
        Utilise l'implémentation de la classe abstraite.
        """
        return await super().recherche_intelligente(
            question=question,
            client_name=client_name,
            date_debut=date_debut,
            date_fin=date_fin,
            limit=limit,
            score_threshold=score_threshold,
            vector_field=vector_field
        )


# =======================
# AUTRES CLIENTS À AJOUTER
# =======================

class ZendeskSearchClient(GenericSearchClient):
    """Client de recherche spécialisé pour les tickets Zendesk."""

    def __init__(self, collection_name, qdrant_client, embedding_service, translation_service=None):
        super().__init__(collection_name, qdrant_client, embedding_service)
        self.translation_service = translation_service
        self.required_fields = ['ticket_id', 'summary', 'content', 'client']
        self.processor = DefaultResultProcessor()

    def get_source_name(self) -> str:
        """Retourne le nom de la source de données."""
        return "ZENDESK"

    def valider_resultat(self, result: Any) -> bool:
        """Valide qu'un résultat Zendesk est exploitable."""
        try:
            payload = self.processor.extract_payload(result)
            score = self.processor.extract_score(result)

            # Vérification des champs requis
            if not all(payload.get(field) for field in ['ticket_id', 'content']):
                return False

            return score >= 0.45

        except Exception as e:
            logger.error(f"Erreur validation résultat Zendesk: {str(e)}")
            return False
            
    async def format_for_slack(self, result: Any) -> Optional[Dict]:
        """Formate un résultat Zendesk pour affichage dans Slack."""
        try:
            payload = self.processor.extract_payload(result)
            if not payload:
                logger.warning("Payload vide ou invalide pour résultat Zendesk")
                return None
                
            score = self.processor.extract_score(result)
            
            # Validation des champs recommandés (mais non obligatoires)
            if not any(field in payload for field in ['ticket_id', 'id', 'content']):
                logger.warning(f"Champs importants manquants dans le ticket Zendesk: {list(payload.keys())}")
                # On continue avec des valeurs par défaut plutôt que de retourner None
                
            # Calcul de la fiabilité basée sur le score
            score_percent = round(score * 100)
            fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"
            
            try:
                # Récupération des dates de façon sécurisée
                created_date, updated_date = self._format_dates(payload)
            except Exception as date_error:
                logger.warning(f"Erreur formatage dates Zendesk: {str(date_error)}")
                created_date, updated_date = 'N/A', 'N/A'
            
            # Récupération des champs spécifiques à Zendesk
            ticket_id = payload.get('ticket_id', payload.get('id', 'N/A'))
            summary = payload.get('summary', payload.get('title', 'Sans titre'))
            
            # Troncature du contenu
            content = str(payload.get('content', ''))
            content = (content[:497] + "...") if len(content) > 500 else content
            
            # Construction du message formaté
            message = (
                f"*ZENDESK-{ticket_id}* - {fiabilite} {score_percent}%\n"
                f"*ID:* {ticket_id} - *Client:* {payload.get('client', 'N/A')}\n"
                f"*Titre:* {summary}\n"
                f"*Status:* {payload.get('status', 'N/A')} - *Assigné à:* {payload.get('assignee', 'Non assigné')}\n"
                f"*Créé le:* {created_date} - *Maj:* {updated_date}\n"
                f"*Description:* {content}\n"
                f"*URL:* {payload.get('url', 'N/A')}"
            )
            
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur format Zendesk: {str(e)}")
            return None

    def _format_dates(self, payload: Dict) -> tuple:
        """Formate les dates pour l'affichage."""
        try:
            created = payload.get('created', payload.get('created_at'))
            updated = payload.get('updated', payload.get('updated_at'))
            resolved = payload.get('resolved', payload.get('resolved_at'))

            def format_date(date_str):
                if not date_str:
                    return 'N/A'
                # La méthode normalize_date retourne déjà une chaîne formatée, pas besoin d'appeler strftime
                return self.processor.normalize_date(date_str)

            # Si date de résolution présente, on l'utilise comme date de mise à jour
            if resolved and not updated:
                updated = resolved

            return format_date(created), format_date(updated)

        except Exception as e:
            logger.error(f"Erreur formatage dates Zendesk: {str(e)}")
            return 'N/A', 'N/A'

    async def recherche_intelligente(self, 
                                    question: str, 
                                    client_name: Optional[str] = None, 
                                    date_debut: Optional[datetime] = None, 
                                    date_fin: Optional[datetime] = None,
                                    limit: int = 10,
                                    score_threshold: float = 0.0,
                                    vector_field: str = "vector"):
        """
        Implémentation de la méthode de recherche intelligente pour Zendesk.
        Utilise l'implémentation de la classe abstraite.
        """
        return await super().recherche_intelligente(
            question=question,
            client_name=client_name,
            date_debut=date_debut,
            date_fin=date_fin,
            limit=limit,
            score_threshold=score_threshold,
            vector_field=vector_field
        )

class ERPSearchClient(GenericSearchClient):
    """Client de recherche base pour les sources ERP (NetSuite, SAP)."""

    def __init__(self, collection_name, qdrant_client, embedding_service, translation_service):
        super().__init__(collection_name, qdrant_client, embedding_service)
        self.translation_service = translation_service
        self.required_fields = ['title', 'content']
        self.processor = DefaultResultProcessor()

    def get_source_name(self) -> str:
        """Retourne le nom de la source de données ERP générique."""
        return "ERP"

    def valider_resultat(self, result: Any) -> bool:
        """Valide qu'un résultat ERP est exploitable."""
        try:
            payload = self.processor.extract_payload(result)
            score = self.processor.extract_score(result)

            if not payload.get('title') or not payload.get('content'):
                # Log plus verbeux pour comprendre pourquoi le résultat est invalide
                logger.debug(f"Résultat ERP invalide - champs manquants: {list(payload.keys())}")
                return False

            # Abaissement du seuil à 0.25 pour correspondre à la stratégie globale du chatbot
            min_score = 0.25
            is_valid = score >= min_score
            
            if not is_valid:
                logger.debug(f"Résultat ERP invalide - score trop bas: {score} < {min_score}")
            
            return is_valid

        except Exception as e:
            logger.error(f"Erreur validation résultat ERP: {str(e)}")
            return False

    async def format_for_slack(self, result: Any) -> Optional[Dict]:
        """Formate un résultat ERP générique pour affichage."""
        try:
            payload = self.processor.extract_payload(result)
            score = self.processor.extract_score(result)
            
            # Validation des champs essentiels
            if not all(payload.get(field) for field in self.required_fields):
                return None
                
            # Calcul de la fiabilité basée sur le score
            score_percent = round(score * 100)
            fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"
            
            # Traduction si possible
            title = payload.get('title', 'Sans titre')
            content = str(payload.get('content', '') or payload.get('text', 'Pas de contenu'))
            
            title_fr = title
            content_preview = content[:800]
            content_fr = content_preview
            
            if self.translation_service:
                try:
                    title_fr = await self.translation_service.translate(title, "fr")
                    content_fr = await self.translation_service.translate(content_preview, "fr")
                except Exception as e:
                    logger.error(f"Erreur traduction: {str(e)}")
            
            # Troncature du contenu traduit
            if len(content_fr) > 500:
                content_fr = content_fr[:497] + "..."
                
            # Construction du message formaté
            message = (
                f"*{self.get_source_name()}* - {fiabilite} {score_percent}%\n"
                f"*Titre:* {title_fr}\n"
                f"*Contenu:* {content_fr}\n"
                f"*URL:* {payload.get('url', 'N/A')}"
            )
            
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur format ERP: {str(e)}")
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
        Implémentation de la méthode de recherche intelligente pour ERP.
        Utilise l'implémentation de la classe abstraite.
        """
        return await super().recherche_intelligente(
            question=question,
            client_name=client_name,
            date_debut=date_debut,
            date_fin=date_fin,
            limit=limit,
            score_threshold=score_threshold,
            vector_field=vector_field
        )

class NetsuiteSearchClient(ERPSearchClient):
    """Client de recherche spécialisé pour les documents NetSuite."""
    
    def __init__(self, collection_name, qdrant_client, embedding_service, translation_service=None):
        super().__init__(collection_name, qdrant_client, embedding_service, translation_service)
        
    def get_source_name(self) -> str:
        """Retourne le nom de la source de données."""
        return "NETSUITE"

    async def recherche_intelligente(self, 
                                    question: str, 
                                    client_name: Optional[str] = None, 
                                    date_debut: Optional[datetime] = None, 
                                    date_fin: Optional[datetime] = None,
                                    limit: int = 10,
                                    score_threshold: float = 0.0,
                                    vector_field: str = "vector"):
        """
        Implémentation de la méthode de recherche intelligente pour NetSuite.
        Utilise l'implémentation de la classe abstraite.
        """
        return await super().recherche_intelligente(
            question=question,
            client_name=client_name,
            date_debut=date_debut,
            date_fin=date_fin,
            limit=limit,
            score_threshold=score_threshold,
            vector_field=vector_field
        )

class SapSearchClient(ERPSearchClient):
    """Client de recherche spécialisé pour les documents SAP."""
    
    def __init__(self, collection_name, qdrant_client, embedding_service, translation_service=None):
        super().__init__(collection_name, qdrant_client, embedding_service, translation_service)
        
    def get_source_name(self) -> str:
        """Retourne le nom de la source de données."""
        return "SAP"

    async def recherche_intelligente(self, 
                                    question: str, 
                                    client_name: Optional[str] = None, 
                                    date_debut: Optional[datetime] = None, 
                                    date_fin: Optional[datetime] = None,
                                    limit: int = 10,
                                    score_threshold: float = 0.0,
                                    vector_field: str = "vector"):
        """
        Implémentation de la méthode de recherche intelligente pour SAP.
        Utilise l'implémentation de la classe abstraite.
        """
        return await super().recherche_intelligente(
            question=question,
            client_name=client_name,
            date_debut=date_debut,
            date_fin=date_fin,
            limit=limit,
            score_threshold=score_threshold,
            vector_field=vector_field
        )

class ConfluenceSearchClient(GenericSearchClient):
    """Client de recherche spécialisé pour les pages Confluence."""
    
    def __init__(self, collection_name, qdrant_client, embedding_service, translation_service=None):
        super().__init__(collection_name, qdrant_client, embedding_service)
        self.translation_service = translation_service
        self.required_fields = ['id', 'summary', 'content', 'client', 'space_id']
        self.processor = DefaultResultProcessor()

    def get_source_name(self) -> str:
        """Retourne le nom de la source de données."""
        return "CONFLUENCE"

    def valider_resultat(self, result: Any) -> bool:
        """Valide qu'un résultat Confluence est exploitable."""
        try:
            payload = self.processor.extract_payload(result)
            score = self.processor.extract_score(result)

            # Vérification des champs requis
            if not all(payload.get(field) for field in ['id', 'content']):
                return False

            # Vérification du score minimum
            return score >= 0.4

        except Exception as e:
            logger.error(f"Erreur validation résultat Confluence: {str(e)}")
            return False

    async def format_for_slack(self, result: Any) -> Optional[Dict]:
        """Formate un résultat Confluence pour affichage."""
        try:
            payload = self.processor.extract_payload(result)
            if not payload:
                logger.warning("Payload vide ou invalide pour résultat Confluence")
                return None
                
            score = self.processor.extract_score(result)

            # Validation des champs recommandés (mais non obligatoires)
            if not any(payload.get(field) for field in ['id', 'summary', 'content']):
                logger.warning(f"Champs importants manquants dans le document Confluence: {list(payload.keys())}")
                # On continue avec des valeurs par défaut plutôt que de retourner None

            # Calcul de la fiabilité basée sur le score
            score_percent = round(score * 100)
            fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"

            try:
                # Récupération des dates de façon sécurisée
                created_str, updated_str = self._format_dates(payload)
            except Exception as date_error:
                logger.warning(f"Erreur formatage dates Confluence: {str(date_error)}")
                created_str, updated_str = 'N/A', 'N/A'

            # Troncature du contenu
            content = str(payload.get('content', ''))
            content = (content[:497] + "...") if len(content) > 500 else content

            # Construction du message formaté
            message = (
                f"*CONFLUENCE-{payload.get('id', 'N/A')}* - {payload.get('summary', payload.get('title', 'Sans titre'))}\n"
                f"Client: {payload.get('client', 'N/A')} - {fiabilite} {score_percent}%\n"
                f"Espace: {payload.get('space_id', 'N/A')}\n"
                f"Créé le: {created_str} - Maj: {updated_str}\n"
                f"Description: {content}\n"
                f"URL: {payload.get('page_url', payload.get('url', 'N/A'))}"
            )

            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }
        except Exception as e:
            logger.error(f"Erreur format Confluence: {str(e)}")
            return None

    def _format_dates(self, payload: Dict) -> tuple:
        """Formate les dates pour l'affichage."""
        try:
            created = payload.get('created', payload.get('created_at'))
            updated = payload.get('updated', payload.get('updated_at', payload.get('last_modified')))

            def format_date(date_str):
                if not date_str:
                    return 'N/A'
                # La méthode normalize_date retourne déjà une chaîne formatée, pas besoin d'appeler strftime
                return self.processor.normalize_date(date_str)

            return format_date(created), format_date(updated)

        except Exception as e:
            logger.error(f"Erreur formatage dates Confluence: {str(e)}")
            return 'N/A', 'N/A'

    async def recherche_intelligente(self, 
                                    question: str, 
                                    client_name: Optional[str] = None, 
                                    date_debut: Optional[datetime] = None, 
                                    date_fin: Optional[datetime] = None,
                                    limit: int = 10,
                                    score_threshold: float = 0.0,
                                    vector_field: str = "vector"):
        """
        Implémentation de la méthode de recherche intelligente pour Confluence.
        Utilise l'implémentation de la classe abstraite.
        """
        return await super().recherche_intelligente(
            question=question,
            client_name=client_name,
            date_debut=date_debut,
            date_fin=date_fin,
            limit=limit,
            score_threshold=score_threshold,
            vector_field=vector_field
        )

class NetsuiteDummiesSearchClient(GenericSearchClient):
    """Client de recherche spécialisé pour les documents de démonstration NetSuite."""
    
    def __init__(self, collection_name, qdrant_client, embedding_service, translation_service=None):
        super().__init__(collection_name, qdrant_client, embedding_service)
        self.translation_service = translation_service
        self.required_fields = ['title', 'text', 'pdf_path']
        self.processor = DefaultResultProcessor()
    
    def get_source_name(self) -> str:
        """Retourne le nom de la source de données."""
        return "NETSUITE_DUMMIES"

    def get_source_prefix(self) -> str:
        """Retourne le préfixe pour les sources NetSuite Dummies."""
        return "NS-DEMO"
        
    def valider_resultat(self, result: Any) -> bool:
        """Valide qu'un résultat NetSuite Dummies est exploitable."""
        try:
            payload = self.processor.extract_payload(result)
            score = self.processor.extract_score(result)

            # Vérification des champs requis
            missing_fields = [field for field in self.required_fields if not payload.get(field)]
            if missing_fields:
                logger.debug(f"Champs manquants dans le résultat: {missing_fields}")
                return False

            # Vérification du score minimum
            return score >= 0.5

        except Exception as e:
            logger.error(f"Erreur validation résultat NetSuite Dummies: {str(e)}")
            return False

    async def format_for_slack(self, result: Any) -> Optional[Dict]:
        """Formate un résultat NetSuite Dummies pour affichage."""
        try:
            payload = self.processor.extract_payload(result)
            score = self.processor.extract_score(result)

            # Validation des champs essentiels
            if not all(payload.get(field) for field in ['title', 'text']):
                return None

            # Calcul de la fiabilité basée sur le score
            score_percent = round(score * 100)
            fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"

            try:
                # Récupération des dates de façon sécurisée
                created_str, updated_str = self._format_dates(payload)
            except Exception as date_error:
                logger.warning(f"Erreur formatage dates NetSuite Dummies: {str(date_error)}")
                created_str, updated_str = 'N/A', 'N/A'

            # Troncature du contenu
            content = str(payload.get('text', ''))
            content = (content[:497] + "...") if len(content) > 500 else content

            # Construction du message formaté
            message = (
                f"*{self.get_source_prefix()}* - {fiabilite} {score_percent}%\n"
                f"*Titre:* {payload.get('title', 'Sans titre')}\n"
                f"*Contenu:* {content}\n"
                f"*Document:* {payload.get('pdf_path', 'N/A')}\n"
                f"*Créé le:* {created_str} - *Maj:* {updated_str}"
            )

            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }

        except Exception as e:
            logger.error(f"Erreur format NetSuite Dummies: {str(e)}")
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
        Implémentation de la méthode de recherche intelligente pour NetSuite Dummies.
        Utilise l'implémentation de la classe abstraite.
        """
        return await super().recherche_intelligente(
            question=question,
            client_name=client_name,
            date_debut=date_debut,
            date_fin=date_fin,
            limit=limit,
            score_threshold=score_threshold,
            vector_field=vector_field
        )
