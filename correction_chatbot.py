
# Correction pour chatbot.py

# 1. Fonction pour déterminer les collections en fonction du client et de la question
def collections_par_client_et_question(client_name, question):
    """
    Détermine les collections à interroger en fonction du client et de la question
    """
    # Pour RONDOT, on sait qu'on veut chercher dans JIRA, ZENDESK et CONFLUENCE
    if client_name == "RONDOT":
        return ["jira", "zendesk", "confluence"]
    
    # Pour des questions sur NetSuite, on cherche dans les collections ERP
    if any(term in question.lower() for term in ["netsuite", "erp", "compte", "fournisseur"]):
        return ["netsuite", "netsuite_dummies", "sap"]
    
    # Par défaut, on cherche dans toutes les collections
    return ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]

# 2. Appliquer cette modification dans process_web_message:
# Dans la méthode process_web_message, remplacer l'appel à recherche_coordonnee par:
"""
client_info = await self.determiner_client(text)
client_name = client_info.get('source') if client_info else 'Non spécifié'
self.logger.info(f"Client trouvé: {client_name}")

# Déterminer les collections à interroger en fonction du client et de la question
collections = collections_par_client_et_question(client_name, text)
self.logger.info(f"Collections sélectionnées: {collections}")

# Effectuer la recherche coordonnée
resultats = await self.recherche_coordonnee(
    collections=collections,
    question=text,
    client_info=client_info
)
"""
