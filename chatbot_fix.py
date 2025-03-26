
# Correctif pour chatbot.py

# Fonctions � ajouter au d�but du fichier
def collections_par_client(client_name, question):
    '''D�termine les collections � interroger en fonction du client et de la question'''
    # Importer la configuration si disponible
    try:
        from config import CLIENT_MAPPING
        if client_name in CLIENT_MAPPING:
            return CLIENT_MAPPING[client_name]
    except ImportError:
        pass
    
    # Logique par d�faut
    if client_name == "RONDOT":
        return ["jira", "zendesk", "confluence"]
    
    # Pour des questions sur NetSuite ou ERP
    if any(term in question.lower() for term in ["netsuite", "erp", "compte", "fournisseur"]):
        return ["netsuite", "netsuite_dummies", "sap"]
    
    # Par d�faut, chercher dans toutes les collections
    return ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]

async def extract_client_name_robust(text):
    '''Extraction robuste du nom du client avec gestion des erreurs'''
    # Import ici pour �viter les probl�mes de circularit�
    from gestion_clients import extract_client_name
    
    try:
        # V�rifier si la fonction est asynchrone ou synchrone
        if asyncio.iscoroutinefunction(extract_client_name):
            # Si async, l'appeler avec await
            client_info = await extract_client_name(text)
        else:
            # Sinon, l'appeler directement
            client_info = extract_client_name(text)
        
        # V�rifier le r�sultat
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

# Remplacer la m�thode process_web_message par cette version
async def process_web_message(self, text: str, conversation: Any, user_id: str, mode: str = "detail"):
    '''Traite un message web avec une gestion robuste des erreurs'''
    self.logger.info(f"Traitement du message: {text}")
    
    try:
        # 1. Analyser la question
        analysis = await asyncio.wait_for(self.analyze_question(text), timeout=60)
        self.logger.info(f"Analyse termin�e")
        
        # 2. D�terminer le client avec la m�thode robuste
        client_info = await extract_client_name_robust(text)
        client_name = client_info.get('source') if client_info else 'Non sp�cifi�'
        self.logger.info(f"Client trouv�: {client_name}")
        
        # 3. D�terminer les collections � interroger
        collections = collections_par_client(client_name, text)
        self.logger.info(f"Collections s�lectionn�es: {collections}")
        
        # 4. Effectuer la recherche
        self.logger.info(f"Lancement de la recherche pour: {text}")
        
        # Appel � recherche_coordonnee avec la bonne signature
        resultats = await self.recherche_coordonnee(
            collections=collections,
            question=text,
            client_info=client_info
        )
        
        # 5. V�rifier si des r�sultats ont �t� trouv�s
        if not resultats or len(resultats) == 0:
            self.logger.warning(f"Aucun r�sultat trouv� pour: {text}")
            return {
                "text": "D�sol�, je n'ai trouv� aucun r�sultat pertinent pour votre question.",
                "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "D�sol�, je n'ai trouv� aucun r�sultat pertinent pour votre question."}}],
                "metadata": {"client": client_name}
            }
        
        # 6. G�n�rer la r�ponse avec les r�sultats trouv�s
        self.logger.info(f"{len(resultats)} r�sultats trouv�s, g�n�ration de la r�ponse...")
        
        # Appel � generate_response avec la bonne signature
        response = await self.generate_response(text, resultats, client_info, mode)
        return response
        
    except Exception as e:
        self.logger.error(f"Erreur lors du traitement du message: {str(e)}")
        return {
            "text": f"D�sol�, une erreur s'est produite lors du traitement de votre demande: {str(e)}",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"D�sol�, une erreur s'est produite lors du traitement de votre demande: {str(e)}"}}],
            "metadata": {"client": client_name if 'client_name' in locals() else 'Non sp�cifi�', "error": str(e)}
        }
