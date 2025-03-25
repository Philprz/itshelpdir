from typing import Dict, Optional, Any
from search_base import AbstractSearchClient, DefaultResultProcessor
from configuration import logger


class JiraSearchClient(AbstractSearchClient):
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
            score = self.processor.extract_score(result)

            # Validation des champs essentiels
            if not all(payload.get(field) for field in ['key', 'summary']):
                return None

            # Calcul de la fiabilité basée sur le score
            score_percent = round(score * 100)
            fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"

            # Récupération des dates
            created_date, updated_date = self._format_dates(payload)

            # Troncature du contenu
            content = str(payload.get('content', ''))
            content = (content[:497] + "...") if len(content) > 500 else content

            # Construction du message formaté
            message = (
                f"*JIRA-{payload.get('key')}* - {payload.get('summary')}\n"
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
                date = self.processor.normalize_date(date_str)
                return date.strftime("%Y-%m-%d") if date else 'N/A'

            return format_date(created), format_date(updated)

        except Exception as e:
            logger.error(f"Erreur formatage dates: {str(e)}")
            return 'N/A', 'N/A'


# =======================
# AUTRES CLIENTS À AJOUTER
# =======================

class ZendeskSearchClient(AbstractSearchClient):
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
            score = self.processor.extract_score(result)
            
            # Validation des champs essentiels
            if not all(field in payload for field in ['ticket_id', 'content']):
                logger.warning(f"Champs requis manquants dans le ticket Zendesk: {list(payload.keys())}")
                return None
                
            # Calcul de la fiabilité basée sur le score
            score_percent = round(score * 100)
            fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"
            
            # Formatage des dates
            created_date, updated_date = self._format_dates(payload)
            
            # Récupération des champs spécifiques à Zendesk
            ticket_id = payload.get('ticket_id', payload.get('id', 'N/A'))
            summary = payload.get('summary', 'Sans titre')
            
            # Troncature du contenu
            content = str(payload.get('content', ''))
            content = (content[:497] + "...") if len(content) > 500 else content
            
            # Construction du message formaté
            message = (
                f"*ZENDESK-{ticket_id}* - {fiabilite} {score_percent}%\n"
                f"*ID:* {ticket_id} - *Client:* {payload.get('client', 'N/A')}\n"
                f"*Titre:* {summary}\n"
                f"*Status:* {payload.get('status', '')} - *Assigné à:* {payload.get('assignee', 'Non assigné')}\n"
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
            created = payload.get('created')
            updated = payload.get('updated')

            def format_date(date_str):
                if not date_str:
                    return 'N/A'
                date = self.processor.normalize_date(date_str)
                return date.strftime("%Y-%m-%d") if date else 'N/A'

            return format_date(created), format_date(updated)

        except Exception as e:
            logger.error(f"Erreur formatage dates: {str(e)}")
            return 'N/A', 'N/A'

class ERPSearchClient(AbstractSearchClient):
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
                f"*{self.get_source_prefix()}* - {fiabilite} {score_percent}%\n"
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

class NetsuiteSearchClient(ERPSearchClient):
    """Client de recherche spécialisé pour les documents NetSuite."""

    def __init__(self, collection_name, qdrant_client, embedding_service, translation_service=None):
        super().__init__(collection_name, qdrant_client, embedding_service, translation_service)
        
    def get_source_prefix(self) -> str:
        return "NETSUITE"


class SapSearchClient(ERPSearchClient):
    """Client de recherche spécialisé pour les documents SAP."""

    def __init__(self, collection_name, qdrant_client, embedding_service, translation_service=None):
        super().__init__(collection_name, qdrant_client, embedding_service, translation_service)
        
    def get_source_prefix(self) -> str:
        return "SAP"
class ConfluenceSearchClient(AbstractSearchClient):
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
            score = self.processor.extract_score(result)

            # Validation des champs essentiels
            if not all(payload.get(field) for field in ['id', 'summary', 'content']):
                return None

            # Calcul de la fiabilité basée sur le score
            score_percent = round(score * 100)
            fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"

            # Récupération des dates
            created_str, updated_str = self._format_dates(payload)

            # Troncature du contenu
            content = str(payload.get('content', ''))
            content = (content[:497] + "...") if len(content) > 500 else content

            # Construction du message formaté
            message = (
                f"*CONFLUENCE-{payload.get('id')}* - {payload.get('summary')}\n"
                f"Client: {payload.get('client', 'N/A')} - {fiabilite} {score_percent}%\n"
                f"Espace: {payload.get('space_id', 'N/A')}\n"
                f"Créé le: {created_str} - Maj: {updated_str}\n"
                f"Description: {content}\n"
                f"URL: {payload.get('page_url', 'N/A')}"
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
            created = payload.get('created')
            updated = payload.get('updated')

            def format_date(date_str):
                if not date_str:
                    return 'N/A'
                date = self.processor.normalize_date(date_str)
                return date.strftime("%Y-%m-%d") if date else 'N/A'

            return format_date(created), format_date(updated)

        except Exception as e:
            logger.error(f"Erreur formatage dates: {str(e)}")
            return 'N/A', 'N/A'
        
class NetsuiteDummiesSearchClient(AbstractSearchClient):
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

            # Traduction du contenu si service disponible
            title = payload.get('title', 'Sans titre')
            content = str(payload.get('text', 'Pas de contenu'))
            
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
                f"*NETSUITE DUMMIES* - {fiabilite} {score_percent}%\n"
                f"*Titre:* {title_fr}\n"
                f"*Contenu:* {content_fr}\n"
                f"*Document:* {payload.get('pdf_path', 'N/A')}"
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
