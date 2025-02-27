# À ajouter dans un fichier translation_service.py

import asyncio
import hashlib
import logging
import time
from typing import Dict, Optional, List, Set
from configuration import logger, global_cache

class TranslationService:
    """
    Service centralisé de traduction avec cache optimisé et détection de langue.
    """
    
    def __init__(self, openai_client, cache=None):
        self.openai_client = openai_client
        self.openai_async = None  # À initialiser avec AsyncOpenAI
        self.cache = cache or global_cache
        self.logger = logging.getLogger('ITS_HELP.translation')
        self.namespace = "translations"
        self.common_languages = {"fr", "en", "de", "es", "it"}
        self.max_retries = 2
        self.retry_delay = 1
        self.batch_size = 5  # Nombre de textes à traduire en batch
        self._pending_requests = {}
        self._lock = asyncio.Lock()
        
    def set_async_client(self, async_client):
        """Définit le client OpenAI asynchrone."""
        self.openai_async = async_client
        
    def _get_cache_key(self, text: str, source_lang: str, target_lang: str) -> str:
        """Génère une clé de cache pour la traduction."""
        text_hash = hashlib.md5(text.strip().encode('utf-8')).hexdigest()
        return f"{source_lang}:{target_lang}:{text_hash}"
    
    async def detect_language(self, text: str) -> str:
        """Détecte la langue du texte."""
        # Vérification cache
        cache_key = f"detect:{hashlib.md5(text[:100].encode()).hexdigest()}"
        cached = await self.cache.get(cache_key, self.namespace)
        if cached:
            return cached
            
        try:
            # Si texte court, utilisation de règles simples
            if len(text) < 20:
                common_french = {'le', 'la', 'les', 'un', 'une', 'des', 'et', 'ou', 'je', 'tu', 'il', 'elle'}
                common_english = {'the', 'a', 'an', 'and', 'or', 'i', 'you', 'he', 'she', 'it', 'they'}
                
                words = set(text.lower().split())
                fr_matches = len(words.intersection(common_french))
                en_matches = len(words.intersection(common_english))
                
                if fr_matches > en_matches:
                    await self.cache.set(cache_key, "fr", self.namespace)
                    return "fr"
                elif en_matches > fr_matches:
                    await self.cache.set(cache_key, "en", self.namespace)
                    return "en"
            
            # Pour les textes plus longs, utilisation d'OpenAI
            if self.openai_async:
                response = await self.openai_async.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Détermine la langue de ce texte. Réponds par le code de langue uniquement (fr, en, es, de, it, etc.)"},
                        {"role": "user", "content": text[:150]}  # Limité aux premiers caractères
                    ],
                    temperature=0.1
                )
                detected = response.choices[0].message.content.strip().lower()
                
                # Normalisation des codes de langue
                if detected.startswith("fr"):
                    detected = "fr"
                elif detected.startswith("en"):
                    detected = "en"
                
                await self.cache.set(cache_key, detected, self.namespace)
                return detected
            
            # Fallback si pas de client async
            return "fr"  # Par défaut français
            
        except Exception as e:
            self.logger.error(f"Erreur détection langue: {str(e)}")
            return "fr"  # Fallback en cas d'erreur
    
    async def translate_sync(self, text: str, target_lang: str = "fr", source_lang: str = None) -> str:
        """
        Version synchrone de la traduction pour les contextes non-async.
        Utilise le client OpenAI synchrone.
        """
        if not text or len(text.strip()) < 3:
            return text
            
        # Détection de la langue source si non spécifiée
        if not source_lang:
            source_lang = await self.detect_language(text)
            
        # Si déjà dans la langue cible, pas besoin de traduire
        if source_lang == target_lang:
            return text
            
        # Vérification cache
        cache_key = self._get_cache_key(text, source_lang, target_lang)
        cached = await self.cache.get(cache_key, self.namespace)
        if cached:
            return cached
            
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Traduis ce texte de {source_lang} vers {target_lang}. Ne fais aucun autre commentaire."},
                    {"role": "user", "content": text}
                ],
                temperature=0.1
            )
            
            translation = response.choices[0].message.content.strip()
            await self.cache.set(cache_key, translation, self.namespace)
            return translation
            
        except Exception as e:
            self.logger.error(f"Erreur traduction sync: {str(e)}")
            return text  # Fallback au texte original
    
    async def translate(self, text: str, target_lang: str = "fr", source_lang: str = None) -> str:
        """
        Traduit un texte de manière asynchrone vers la langue cible.
        
        Args:
            text: Texte à traduire
            target_lang: Langue cible (défaut: français)
            source_lang: Langue source (auto-détectée si non spécifiée)
            
        Returns:
            Texte traduit ou texte original en cas d'erreur
        """
        if not text or len(text.strip()) < 3:
            return text
            
        # Détection de la langue source si non spécifiée
        if not source_lang:
            source_lang = await self.detect_language(text)
            
        # Si déjà dans la langue cible, pas besoin de traduire
        if source_lang == target_lang:
            return text
            
        # Vérification cache
        cache_key = self._get_cache_key(text, source_lang, target_lang)
        cached = await self.cache.get(cache_key, self.namespace)
        if cached:
            return cached
            
        # Si pas de client async, utiliser la version sync
        if not self.openai_async:
            return await self.translate_sync(text, target_lang, source_lang)
            
        try:
            # Essayer d'ajouter à une requête en batch existante
            request_key = f"{source_lang}:{target_lang}"
            
            async with self._lock:
                if request_key in self._pending_requests:
                    # Si une requête est déjà en attente, ajouter à celle-ci
                    future = asyncio.Future()
                    self._pending_requests[request_key]["texts"].append((text, future))
                    if len(self._pending_requests[request_key]["texts"]) >= self.batch_size:
                        # Si on atteint la taille de batch, déclencher la traduction en batch
                        asyncio.create_task(self._process_batch(request_key))
                else:
                    # Sinon, créer une nouvelle requête en attente
                    future = asyncio.Future()
                    self._pending_requests[request_key] = {
                        "texts": [(text, future)],
                        "timer": asyncio.create_task(self._schedule_batch_processing(request_key))
                    }
            
            # Attente du résultat
            result = await future
            return result
            
        except Exception as e:
            self.logger.error(f"Erreur traduction: {str(e)}")
            
            # En cas d'erreur, essayer une dernière fois en direct
            for attempt in range(self.max_retries):
                try:
                    response = await self.openai_async.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": f"Traduis ce texte de {source_lang} vers {target_lang}. Ne fais aucun autre commentaire."},
                            {"role": "user", "content": text}
                        ],
                        temperature=0.1
                    )
                    
                    translation = response.choices[0].message.content.strip()
                    await self.cache.set(cache_key, translation, self.namespace)
                    return translation
                    
                except Exception as retry_error:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (2 ** attempt))
                    else:
                        self.logger.error(f"Échec après {self.max_retries} tentatives: {str(retry_error)}")
            
            return text  # Fallback au texte original
    
    async def _schedule_batch_processing(self, request_key: str):
        """
        Planifie le traitement d'un batch après un délai.
        Cela permet de regrouper plusieurs requêtes dans un même batch
        même si elles n'arrivent pas exactement en même temps.
        """
        await asyncio.sleep(0.5)  # Délai d'attente pour agréger les requêtes
        await self._process_batch(request_key)
    
    async def _process_batch(self, request_key: str):
        """
        Traite un batch de requêtes de traduction.
        """
        async with self._lock:
            if request_key not in self._pending_requests:
                return
                
            # Récupération des textes et futures
            batch = self._pending_requests[request_key]["texts"]
            texts = [item[0] for item in batch]
            futures = [item[1] for item in batch]
            
            # Nettoyage des requêtes en attente
            if "timer" in self._pending_requests[request_key] and self._pending_requests[request_key]["timer"] is not None:
                self._pending_requests[request_key]["timer"].cancel()
            del self._pending_requests[request_key]
        
        # Séparation du request_key en langues source et cible
        source_lang, target_lang = request_key.split(":")
        
        # Traitement du batch
        translations = []
        try:
            # Préparation de la requête avec tous les textes
            batch_text = "\n---\n".join([f"[{i+1}] {text}" for i, text in enumerate(texts)])
            
            response = await self.openai_async.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Traduis ces textes de {source_lang} vers {target_lang}. Pour chaque texte, conserve le format [N] au début de la ligne."},
                    {"role": "user", "content": batch_text}
                ],
                temperature=0.1
            )
            
            # Parsing de la réponse
            result = response.choices[0].message.content.strip()
            
            # Extraction des traductions individuelles
            current_index = None
            current_text = []
            
            for line in result.split("\n"):
                # Recherche d'un nouvel index [N]
                import re
                match = re.match(r'\[(\d+)\](.*)', line)
                
                if match:
                    # Si un texte est en cours, l'enregistrer
                    if current_index is not None and current_text:
                        while len(translations) < current_index:
                            translations.append("")
                        translations.append("\n".join(current_text).strip())
                        current_text = []
                    
                    # Démarrer un nouveau texte
                    current_index = int(match.group(1))
                    current_text.append(match.group(2).strip())
                else:
                    # Continuation du texte courant
                    if current_index is not None:
                        current_text.append(line)
            
            # Enregistrer le dernier texte
            if current_index is not None and current_text:
                while len(translations) < current_index:
                    translations.append("")
                translations.append("\n".join(current_text).strip())
            
        except Exception as e:
            self.logger.error(f"Erreur traitement batch: {str(e)}")
            # En cas d'erreur, revenir à des traductions individuelles
            for text in texts:
                translations.append(await self.translate_sync(text, target_lang, source_lang))
        
        # Enregistrement des traductions dans le cache et résolution des futures
        for i, (text, future) in enumerate(zip(texts, futures)):
            translation = translations[i] if i < len(translations) else text
            
            # Mise en cache
            cache_key = self._get_cache_key(text, source_lang, target_lang)
            await self.cache.set(cache_key, translation, self.namespace)
            
            # Résolution de la future
            if not future.done():
                future.set_result(translation)
    
    async def translate_batch(self, texts: List[str], target_lang: str = "fr", source_lang: str = None) -> List[str]:
        """
        Traduit un lot de textes en une seule requête.
        
        Args:
            texts: Liste de textes à traduire
            target_lang: Langue cible (défaut: français)
            source_lang: Langue source (auto-détectée si non spécifiée)
            
        Returns:
            Liste des textes traduits
        """
        if not texts:
            return []
            
        # Détection de la langue source si non spécifiée
        if not source_lang:
            # Échantillonnage pour la détection
            sample = "\n".join(texts[:3])
            source_lang = await self.detect_language(sample)
            
        # Si déjà dans la langue cible, pas besoin de traduire
        if source_lang == target_lang:
            return texts.copy()
            
        # Vérification du cache pour chaque texte
        results = []
        to_translate = []
        indices = []
        
        for i, text in enumerate(texts):
            if not text or len(text.strip()) < 3:
                results.append(text)
                continue
                
            cache_key = self._get_cache_key(text, source_lang, target_lang)
            cached = await self.cache.get(cache_key, self.namespace)
            
            if cached:
                results.append(cached)
            else:
                results.append(None)  # Placeholder
                to_translate.append(text)
                indices.append(i)
        
        # Si tous les textes sont en cache, retourner directement
        if not to_translate:
            return results
            
        try:
            # Traduction en batch des textes non cachés
            batch_text = "\n---\n".join([f"[{i+1}] {text}" for i, text in enumerate(to_translate)])
            
            response = await self.openai_async.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Traduis ces textes de {source_lang} vers {target_lang}. Pour chaque texte, conserve le format [N] au début de la ligne."},
                    {"role": "user", "content": batch_text}
                ],
                temperature=0.1
            )
            
            # Parsing de la réponse
            result = response.choices[0].message.content.strip()
            
            # Extraction des traductions individuelles
            translations = [""] * len(to_translate)
            current_index = None
            current_text = []
            
            for line in result.split("\n"):
                # Recherche d'un nouvel index [N]
                import re
                match = re.match(r'\[(\d+)\](.*)', line)
                
                if match:
                    # Si un texte est en cours, l'enregistrer
                    if current_index is not None and current_text:
                        if 0 <= current_index - 1 < len(translations):
                            translations[current_index - 1] = "\n".join(current_text).strip()
                        current_text = []
                    
                    # Démarrer un nouveau texte
                    current_index = int(match.group(1))
                    current_text.append(match.group(2).strip())
                else:
                    # Continuation du texte courant
                    if current_index is not None:
                        current_text.append(line)
            
            # Enregistrer le dernier texte
            if current_index is not None and current_text:
                if 0 <= current_index - 1 < len(translations):
                    translations[current_index - 1] = "\n".join(current_text).strip()
            
            # Mise à jour des résultats et du cache
            for i, (orig, trans) in enumerate(zip(to_translate, translations)):
                if trans:  # Si la traduction a réussi
                    results[indices[i]] = trans
                    cache_key = self._get_cache_key(orig, source_lang, target_lang)
                    await self.cache.set(cache_key, trans, self.namespace)
                else:  # Fallback au texte original
                    results[indices[i]] = orig
                    
        except Exception as e:
            self.logger.error(f"Erreur traduction batch: {str(e)}")
            # En cas d'erreur, revenir à des traductions individuelles
            for i, text in enumerate(to_translate):
                translation = await self.translate_sync(text, target_lang, source_lang)
                results[indices[i]] = translation
                
        # Remplacement des placeholders restants par les textes originaux
        for i, r in enumerate(results):
            if r is None:
                results[i] = texts[i]
                
        return results