
# Correctif pour chatbot.py

# Fonctions à ajouter au début du fichier
def collections_par_client(client_name, question):
    '''Détermine les collections à interroger en fonction du client et de la question'''
    # Importer la configuration si disponible
    try:
        from config import CLIENT_MAPPING
        if client_name in CLIENT_MAPPING:
            return CLIENT_MAPPING[client_name]
    except ImportError:
        pass
    
    # Logique par défaut
    if client_name == "RONDOT":
        return ["jira", "zendesk", "confluence"]
    
    # Pour des questions sur NetSuite ou ERP
    if any(term in question.lower() for term in ["netsuite", "erp", "compte", "fournisseur"]):
        return ["netsuite", "netsuite_dummies", "sap"]
    
    # Par défaut, chercher dans toutes les collections
    return ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]

async def extract_client_name_robust(text):
    '''Extraction robuste du nom du client avec gestion des erreurs'''
    # Import ici pour éviter les problèmes de circularité
    from gestion_clients import extract_client_name
    
    try:
        # Vérifier si la fonction est asynchrone ou synchrone
        if asyncio.iscoroutinefunction(extract_client_name):
            # Si async, l'appeler avec await
            client_info = await extract_client_name(text)
        else:
            # Sinon, l'appeler directement
            client_info = extract_client_name(text)
        
        # Vérifier le résultat
        if isinstance(client_info, dict) and 'source' in client_info:
            return client_info
        
        # Recherche explicite de RONDOT dans le texte comme fallback
        if "RONDOT" in text.upper():
            return {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
        
        return None
    except Exception as e:
        # En cas d'erreur, logger et retourner None
        logger.error(f"Erreur lors de l'extraction du client: {str(e)}")
        
        # Recherche explicite de RONDOT dans le texte comme fallback
        if "RONDOT" in text.upper():
            return {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
        
        return None

# Remplacer la méthode process_web_message par cette version
async def process_web_message(self, text: str, conversation: Any, user_id: str, mode: str = "detail"):
    '''Traite un message web avec une gestion robuste des erreurs'''
    self.logger.info(f"Traitement du message: {text}")
    
    try:
        # 1. Analyser la question
        analysis = await asyncio.wait_for(self.analyze_question(text), timeout=60)
        self.logger.info(f"Analyse terminée")
        
        # 2. Déterminer le client avec la méthode robuste
        client_info = await extract_client_name_robust(text)
        client_name = client_info.get('source') if client_info else 'Non spécifié'
        self.logger.info(f"Client trouvé: {client_name}")
        
        # 3. Déterminer les collections à interroger
        collections = collections_par_client(client_name, text)
        self.logger.info(f"Collections sélectionnées: {collections}")
        
        # 4. Effectuer la recherche
        self.logger.info(f"Lancement de la recherche pour: {text}")
        
        # Appel à recherche_coordonnee avec la bonne signature
        resultats = await self.recherche_coordonnee(
            collections=collections,
            question=text,
            client_info=client_info
        )
        
        # 5. Vérifier si des résultats ont été trouvés
        if not resultats or len(resultats) == 0:
            self.logger.warning(f"Aucun résultat trouvé pour: {text}")
            return {
                "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question.",
                "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question."}}],
                "metadata": {"client": client_name}
            }
        
        # 6. Générer la réponse avec les résultats trouvés
        self.logger.info(f"{len(resultats)} résultats trouvés, génération de la réponse...")
        
        # Appel à generate_response avec la bonne signature
        response = await self.generate_response(text, resultats, client_info, mode)
        return response
        
    except Exception as e:
        self.logger.error(f"Erreur lors du traitement du message: {str(e)}")
        return {
            "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}"}}],
            "metadata": {"client": client_name if 'client_name' in locals() else 'Non spécifié', "error": str(e)}
        }
