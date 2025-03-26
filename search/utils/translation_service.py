"""
Module translation_service - Service de traduction pour les requêtes
"""

import logging
import os

logger = logging.getLogger('ITS_HELP.translation')

class TranslationService:
    """
    Service de traduction utilisant diverses APIs.
    Permet de traduire des requêtes entre différentes langues.
    """
    
    def __init__(self, openai_client=None, model="gpt-3.5-turbo-16k", cache=None):
        """
        Initialise le service de traduction.
        
        Args:
            openai_client: Client OpenAI à utiliser
            model: Modèle à utiliser
            cache: Cache pour stocker les traductions
        """
        self.openai_client = openai_client
        self.model = model
        self.cache = cache
        self.logger = logger
        
        # Activer/désactiver la traduction
        self.enabled = os.getenv("ENABLE_TRANSLATION", "false").lower() in ["true", "1", "yes"]
        
        # Nombre d'appels effectués
        self.call_count = 0
        self.error_count = 0
        
    async def translate(self, text: str, source_lang: str = "auto", target_lang: str = "fr") -> str:
        """
        Traduit un texte d'une langue source vers une langue cible.
        
        Args:
            text: Texte à traduire
            source_lang: Langue source (ou "auto" pour détection)
            target_lang: Langue cible
            
        Returns:
            Texte traduit
        """
        if not text:
            return ""
            
        if not self.enabled:
            self.logger.debug("Traduction désactivée - texte original retourné")
            return text
            
        # Vérifier si les langues sont identiques
        if source_lang != "auto" and source_lang == target_lang:
            return text
            
        # Normaliser le texte
        text = self._normalize_text(text)
        
        # Vérifier dans le cache si disponible
        if self.cache:
            cache_key = f"translation:{source_lang}:{target_lang}:{text}"
            cached_translation = self.cache.get(cache_key)
            if cached_translation:
                return cached_translation
                
        # Traduire avec le client configuré
        try:
            if self.openai_client:
                translation = await self._translate_with_openai(text, source_lang, target_lang)
                
                # Mettre en cache si disponible
                if self.cache:
                    self.cache.set(cache_key, translation)
                    
                return translation
            else:
                self.logger.warning("Aucun client configuré pour la traduction")
                return text
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"Erreur lors de la traduction: {str(e)}")
            return text
            
    def _normalize_text(self, text: str) -> str:
        """
        Normalise un texte pour la traduction.
        
        Args:
            text: Texte à normaliser
            
        Returns:
            Texte normalisé
        """
        # Tronquer si trop long
        max_chars = 4000
        if len(text) > max_chars:
            self.logger.warning(f"Texte tronqué pour traduction: {len(text)} > {max_chars}")
            text = text[:max_chars]
            
        # Supprimer les caractères spéciaux problématiques
        text = text.replace('\x00', ' ')
        
        # Normaliser les espaces
        text = ' '.join(text.split())
        
        return text
        
    async def _translate_with_openai(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Traduit un texte avec l'API OpenAI.
        
        Args:
            text: Texte à traduire
            source_lang: Langue source
            target_lang: Langue cible
            
        Returns:
            Texte traduit
        """
        self.call_count += 1
        
        # Construire le prompt
        source_lang_prompt = f"de {source_lang}" if source_lang != "auto" else ""
        prompt = f"Traduire le texte suivant {source_lang_prompt} vers {target_lang}. Retourner uniquement le texte traduit, sans commentaires ni explications:\n\n{text}"
        
        try:
            # Vérifier si c'est l'ancienne ou nouvelle API OpenAI
            if hasattr(self.openai_client, 'chat'):
                # Nouvelle API
                response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "Tu es un traducteur professionnel. Traduire le texte fidèlement, dans le même format, sans ajouter d'explications ou de commentaires."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=2048
                )
                
                return response.choices[0].message.content.strip()
                
            else:
                # Ancienne API
                response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "Tu es un traducteur professionnel. Traduire le texte fidèlement, dans le même format, sans ajouter d'explications ou de commentaires."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=2048
                )
                
                return response.choices[0].message.content.strip()
                
        except Exception as e:
            self.logger.error(f"Erreur API OpenAI pour traduction: {str(e)}")
            raise
            
    async def detect_language(self, text: str) -> str:
        """
        Détecte la langue d'un texte.
        
        Args:
            text: Texte à analyser
            
        Returns:
            Code de langue détecté (ex: 'fr', 'en')
        """
        if not text or not self.enabled:
            return "fr"  # Défaut: français
            
        # Normaliser le texte
        text = self._normalize_text(text)[:500]  # Limiter à 500 caractères pour la détection
        
        try:
            if self.openai_client:
                prompt = f"Détecte la langue du texte suivant et réponds uniquement par le code ISO 639-1 de la langue (ex: 'fr', 'en', 'es', 'de', etc.):\n\n{text}"
                
                # Vérifier si c'est l'ancienne ou nouvelle API OpenAI
                if hasattr(self.openai_client, 'chat'):
                    # Nouvelle API
                    response = self.openai_client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "Tu es un système de détection de langue. Réponds uniquement par le code ISO 639-1 de la langue."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.3,
                        max_tokens=10
                    )
                    
                    lang_code = response.choices[0].message.content.strip().lower()
                    
                else:
                    # Ancienne API
                    response = self.openai_client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "Tu es un système de détection de langue. Réponds uniquement par le code ISO 639-1 de la langue."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.3,
                        max_tokens=10
                    )
                    
                    lang_code = response.choices[0].message.content.strip().lower()
                
                # Nettoyer le code de langue
                lang_code = lang_code.replace('"', '').replace("'", '').strip()
                
                # Si le code n'est pas un code ISO 639-1 valide, retourner le défaut
                if len(lang_code) != 2:
                    return "fr"
                    
                return lang_code
                
            else:
                self.logger.warning("Aucun client configuré pour la détection de langue")
                return "fr"
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la détection de langue: {str(e)}")
            return "fr"
            
    def get_stats(self):
        """
        Retourne des statistiques sur l'utilisation du service.
        
        Returns:
            Dictionnaire de statistiques
        """
        return {
            "enabled": self.enabled,
            "calls": self.call_count,
            "errors": self.error_count,
            "error_rate": f"{(self.error_count / self.call_count * 100) if self.call_count > 0 else 0:.2f}%",
            "model": self.model,
            "cache_enabled": self.cache is not None
        }
