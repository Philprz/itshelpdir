
# Configuration pour les clients de recherche
# G�n�r� automatiquement par solution_finale.py


# Cl�s API
OPENAI_API_KEY = "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"
QDRANT_URL = "https://b361537d-20a3-4a84-b96f-9efb19837c15.us-east4-0.gcp.cloud.qdrant.io"
QDRANT_API_KEY = "_Pk-nDWDB9DmAENADTuUuacAlegjcjBn4pJ7QjQ35Cz7bIAjp2vCsw"

# Collections pour chaque type de client
COLLECTIONS = {
    "jira": "jira",
    "zendesk": "zendesk", 
    "confluence": "confluence",
    "netsuite": "netsuite",
    "netsuite_dummies": "netsuite_dummies",
    "sap": "sap"
}

# Mapping des clients sp�cifiques
CLIENT_MAPPING = {
    "RONDOT": ["jira", "zendesk", "confluence"]
}
