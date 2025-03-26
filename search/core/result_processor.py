"""
Module result_processor - Classes pour le traitement des résultats de recherche
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger('ITS_HELP.result_processor')

class AbstractResultProcessor(ABC):
    """
    Interface abstraite pour les processeurs de résultats de recherche.
    Définit les méthodes que tout processeur doit implémenter.
    """
    
    @abstractmethod
    def extract_score(self, result: Any) -> float:
        """
        Extrait le score de pertinence d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            Score de pertinence (0.0-1.0)
        """
        pass
        
    @abstractmethod
    def extract_title(self, result: Any) -> Optional[str]:
        """
        Extrait le titre d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            Titre ou None si non disponible
        """
        pass
        
    @abstractmethod
    def extract_url(self, result: Any) -> Optional[str]:
        """
        Extrait l'URL d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            URL ou None si non disponible
        """
        pass
        
    @abstractmethod
    def deduplicate_results(self, results: List[Any]) -> List[Any]:
        """
        Déduplique une liste de résultats.
        
        Args:
            results: Liste de résultats à dédupliquer
            
        Returns:
            Liste de résultats dédupliqués
        """
        pass
        
    @abstractmethod
    def filter_by_date(self, results: List[Any], date_debut: Optional[datetime], date_fin: Optional[datetime]) -> List[Any]:
        """
        Filtre les résultats par date.
        
        Args:
            results: Liste de résultats à filtrer
            date_debut: Date de début (optionnel)
            date_fin: Date de fin (optionnel)
            
        Returns:
            Liste de résultats filtrés
        """
        pass


class DefaultResultProcessor(AbstractResultProcessor):
    """
    Implémentation par défaut d'un processeur de résultats.
    Fournit une implémentation générique pour les méthodes abstraites.
    """
    
    def extract_score(self, result: Any) -> float:
        """
        Extrait le score de pertinence d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            Score de pertinence (0.0-1.0)
        """
        if isinstance(result, dict):
            return float(result.get('score', 0.0))
        return float(getattr(result, 'score', 0.0))
    
    def extract_title(self, result: Any) -> Optional[str]:
        """
        Extrait le titre d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            Titre ou None si non disponible
        """
        payload = self.extract_payload(result)
        
        # Recherche dans différents champs possibles
        for field in ['title', 'summary', 'subject', 'key', 'name']:
            if field in payload and payload[field]:
                return str(payload[field])
                
        return None
    
    def extract_url(self, result: Any) -> Optional[str]:
        """
        Extrait l'URL d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            URL ou None si non disponible
        """
        payload = self.extract_payload(result)
        
        # Recherche dans différents champs possibles
        for field in ['url', 'link', 'href']:
            if field in payload and payload[field]:
                return str(payload[field])
                
        return None
    
    def extract_payload(self, result: Any) -> Dict:
        """
        Extrait le payload d'un résultat de recherche.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            Dictionnaire contenant les données du payload ou dictionnaire vide en cas d'erreur
        """
        if isinstance(result, dict):
            if 'payload' in result and isinstance(result['payload'], dict):
                return result['payload']
            return result
        
        if not hasattr(result, 'payload'):
            return {}
            
        payload = result.payload
        if isinstance(payload, dict):
            return payload
        elif hasattr(payload, '__dict__'):
            return payload.__dict__
        
        return {}
    
    def normalize_date(self, date_value: Any) -> str:
        """
        Normalise une date en format string.
        
        Args:
            date_value: Date sous différents formats possibles (timestamp, iso, string)
            
        Returns:
            Date normalisée au format YYYY-MM-DD ou N/A si la date est invalide
        """
        if not date_value:
            return "N/A"
            
        try:
            dt = None
            
            # Convertir en datetime selon le type
            if isinstance(date_value, (int, float)):
                dt = datetime.fromtimestamp(date_value, tz=timezone.utc)
                
            elif isinstance(date_value, str):
                # Tentative avec isoformat
                try:
                    dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                except ValueError:
                    # Tentative avec différents formats
                    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%Y/%m/%d", "%Y%m%d"]:
                        try:
                            dt = datetime.strptime(date_value, fmt)
                            dt = dt.replace(tzinfo=timezone.utc)
                            break
                        except ValueError:
                            continue
            
            elif isinstance(date_value, datetime):
                dt = date_value
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            
            if dt:
                return dt.strftime("%Y-%m-%d")
            
            return "N/A"
            
        except Exception as e:
            logger.warning(f"Erreur normalisation date: {str(e)}")
            return "N/A"
    
    def deduplicate_results(self, results: List[Any]) -> List[Any]:
        """
        Déduplique une liste de résultats par titre.
        
        Args:
            results: Liste de résultats à dédupliquer
            
        Returns:
            Liste de résultats dédupliqués
        """
        if not results:
            return []
            
        # Utiliser à la fois le titre et un hash du contenu
        seen_hashes = {}
        deduplicated = []
        
        for result in results:
            payload = self.extract_payload(result)
            
            # Extraire le contenu pour le hash
            content = ""
            for field in ['content', 'text', 'description', 'summary']:
                if field in payload and payload[field]:
                    content += str(payload[field])
            
            # Créer un hash du contenu
            content_hash = hashlib.md5(content[:500].encode('utf-8', errors='ignore')).hexdigest()
            
            # Vérifier si on a déjà vu ce hash
            if content_hash not in seen_hashes:
                seen_hashes[content_hash] = True
                deduplicated.append(result)
        
        return deduplicated
    
    def filter_by_date(self, results: List[Any], date_debut: Optional[datetime], date_fin: Optional[datetime]) -> List[Any]:
        """
        Filtre les résultats par date.
        
        Args:
            results: Liste de résultats à filtrer
            date_debut: Date de début (optionnel)
            date_fin: Date de fin (optionnel)
            
        Returns:
            Liste de résultats filtrés
        """
        if not results or (not date_debut and not date_fin):
            return results
        
        filtered_results = []
        
        for result in results:
            payload = self.extract_payload(result)
            
            # Extraire la date à partir de différents champs possibles
            result_date = None
            for field in ['created', 'updated', 'created_at', 'updated_at', 'date']:
                if field in payload and payload[field]:
                    normalized_date = self.normalize_date(payload[field])
                    if normalized_date != "N/A":
                        try:
                            result_date = datetime.strptime(normalized_date, "%Y-%m-%d")
                            result_date = result_date.replace(tzinfo=timezone.utc)
                            break
                        except ValueError:
                            pass
            
            # Si aucune date n'est trouvée, conserver le résultat par défaut
            if not result_date:
                filtered_results.append(result)
                continue
                
            # Vérifier les contraintes de date
            if date_debut and result_date < date_debut:
                continue
            if date_fin and result_date > date_fin:
                continue
                
            # Ajouter le résultat s'il passe les contraintes
            filtered_results.append(result)
        
        return filtered_results
