#gestion_clients.py
import os
import csv

from datetime import datetime   
from fuzzywuzzy import fuzz, process
from sqlalchemy import delete, func, select
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Tuple

from base_de_donnees import SessionLocal, Client, init_db, update_db_structure, Intention, normalize_string
from configuration import logger

def detect_csv_dialect(file_path):
    try:
        with open(file_path, 'r', newline='', encoding='utf-8-sig') as file:
            sample = file.read(1024)
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample)
            file.seek(0)
            return dialect
    except Exception as e:
        logger.error(f"Error detecting CSV dialect: {str(e)}")
        return None

async def importer_clients_csv(session: AsyncSession, fichier: str = "ListeClients.csv") -> Dict[str, any]:
    """
    Importe les clients depuis un fichier CSV avec gestion améliorée des erreurs et validation
    """
    rapport = {
        "status": "success",
        "total_processed": 0,
        "valid_clients": 0,
        "invalid_clients": 0,
        "errors": []
    }

    try:
        if not os.path.exists(fichier):
            rapport["status"] = "error"
            rapport["errors"].append(f"Fichier {fichier} introuvable")
            return rapport

        # Détection automatique du dialecte CSV
        dialect = detect_csv_dialect(fichier)
        if not dialect:
            dialect = csv.excel
            dialect.delimiter = ';'

        clients_importes = []
        # Tentative avec différents encodages
        encodings = ['utf-8-sig', 'latin-1', 'utf-8', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(fichier, 'r', encoding=encoding) as f:
                    content = f.read()
                    break
            except UnicodeDecodeError:
                continue
        else:
            rapport["status"] = "error"
            rapport["errors"].append("Impossible de lire le fichier avec les encodages supportés")
            return rapport

        # Réinitialisation du pointeur de fichier
        with open(fichier, 'r', encoding=encoding) as f:
            lecteur = csv.DictReader(f, delimiter=dialect.delimiter)
            
            for ligne in lecteur:
                rapport["total_processed"] += 1
                try:
                    # Nettoyage et validation des données
                    client_data = {
                        'Client': ligne.get('Client', '').strip(),
                        'Consultant': ligne.get('Consultant', '').strip(),
                        'Statut': ligne.get('Statut', 'En cours').strip(),
                        'JIRA': ligne.get('JIRA', '').strip(),
                        'ZENDESK': ligne.get('ZENDESK', '').strip(),
                        'CONFLUENCE': ligne.get('CONFLUENCE', '').strip(),
                        'ERP': ligne.get('ERP', 'Non spécifié').strip()
                    }

                    # Validation des données
                    is_valid, message = await validate_client_data(client_data)
                    if not is_valid:
                        rapport["invalid_clients"] += 1
                        rapport["errors"].append(f"Ligne {rapport['total_processed']}: {message}")
                        continue

                    # Création du client avec valeurs par défaut si nécessaire
                    client = Client(
                        client=client_data['Client'],
                        consultant=client_data['Consultant'],
                        statut=client_data['Statut'],
                        jira=client_data['JIRA'] or client_data['Client'],
                        zendesk=client_data['ZENDESK'] or client_data['Client'],
                        confluence=client_data['CONFLUENCE'] or client_data['Client'],
                        erp=client_data['ERP']
                    )
                    
                    clients_importes.append(client)
                    rapport["valid_clients"] += 1
                    
                except Exception as e:
                    rapport["invalid_clients"] += 1
                    rapport["errors"].append(f"Erreur ligne {rapport['total_processed']}: {str(e)}")

        if clients_importes:
            # Suppression des données existantes
            await session.execute(delete(Client))
            # Ajout des nouveaux clients
            session.add_all(clients_importes)
            await session.commit()
            logger.info(f"Import réussi: {len(clients_importes)} clients")
        else:
            rapport["status"] = "error"
            rapport["errors"].append("Aucun client valide à importer")

    except Exception as e:
        rapport["status"] = "error"
        rapport["errors"].append(f"Erreur globale: {str(e)}")
        await session.rollback()
        logger.error(f"Échec import clients: {str(e)}")

    return rapport

async def initialiser_base_clients():
    """
    Initialise la base de données avec les clients depuis le CSV.
    À appeler lors du démarrage de l'application.
    """
    async with SessionLocal() as session:
        rapport = await importer_clients_csv(session)
        logger.info(f"Rapport d'import: {rapport}")
        return rapport            
async def afficher_clients():
    async with SessionLocal() as session:
        result = await session.execute(select(Client.client))
        clients = [row[0] for row in result.fetchall()]
        logger.info(f"Liste des clients : {clients}")
        return clients

async def get_all_clients() -> List[Client]:
    async with SessionLocal() as session:
        result = await session.execute(select(Client))
        clients = result.scalars().all()
        logger.info(f"Retrieved {len(clients)} clients from the database.")
        return clients
async def get_client_by_name(client_name: str) -> Optional[Client]:
    async with SessionLocal() as session:
        normalized_name = normalize_string(client_name)
        # Recherche plus permissive pour "rondot" dans "client rondot" par exemple
        exact_matches = []
        result = await session.execute(
            select(Client).filter(
                func.upper(Client.client).contains(normalized_name)
            )
        )
        exact_matches = result.scalars().all()

def client_exists(client_name: str) -> bool:
    return get_client_by_name(client_name) is not None

async def extract_client_name(message: str) -> Tuple[Optional[str], float, Dict[str, str]]:
    async with SessionLocal() as session:
        try:
            if not message or len(message.strip()) < 2:
                logger.warning("Message trop court ou vide")
                return None, 0.0, {}

            # Normalisation du message pour éviter les problèmes de casse ou d'espaces superflus
            message_clean = normalize_string(message)
            logger.info(f"Message normalisé: {message_clean}")

            # Récupération de tous les clients depuis la base de données
            stmt = select(Client)
            result = await session.execute(stmt)
            all_clients = result.scalars().all()
            logger.info(f"Nombre de clients uniques en base: {len(all_clients)}")

            # Recherche exacte : comparer le message avec toutes les variations + le nom principal
            exact_matches = set()
            for client in all_clients:
                # Créer la liste des variations à tester en incluant le nom principal
                variations = list(client.variations.copy() if client.variations else [])
                variations.append(client.client)
                for variation in variations:
                    norm_variation = normalize_string(variation)
                    # Ajouter des espaces pour matcher le mot complet (évite les faux positifs)
                    if f" {norm_variation} " in f" {message_clean} ":
                        logger.info(f"Match exact trouvé: {client.client} via variation: {variation}")
                        exact_matches.add(client)
                        break

            exact_matches = list(exact_matches)
            if len(exact_matches) == 1:
                client = exact_matches[0]
                logger.info(f"Un seul match exact: {client.client}")
                return client.client, 100.0, {"source": client.client}
            elif len(exact_matches) > 1:
                logger.warning(f"Matches multiples trouvés: {[c.client for c in exact_matches]}")
                return None, 0.0, {"ambiguous": True, "possibilities": [c.client for c in exact_matches]}

            # Si aucune correspondance exacte, effectuer une recherche floue
            logger.info("=== Début recherche floue ===")
            best_match = None
            best_score = 0
            for client in all_clients:
                variations = client.variations.copy() if client.variations else []
                variations.append(client.client)
                for variation in variations:
                    norm_variation = normalize_string(variation)
                    ratio_score = fuzz.ratio(message_clean, norm_variation)
                    partial_score = fuzz.partial_ratio(message_clean, norm_variation)
                    token_sort_score = fuzz.token_sort_ratio(message_clean, norm_variation)
                    score = max(ratio_score, partial_score, token_sort_score)
                    logger.debug(f"Score fuzzy pour {client.client} via '{variation}': {score}")
                    if score > best_score:
                        best_score = score
                        best_match = client

            if best_match and best_score >= 70:
                logger.info(f"Meilleur match fuzzy: {best_match.client} ({best_score}%)")
                return best_match.client, best_score, {"source": best_match.client}
            else:
                logger.warning("Aucun match trouvé")
                return None, 0.0, {}

        except Exception as e:
            logger.error(f"Erreur dans extract_client_name: {str(e)}", exc_info=True)
            return None, 0.0, {}


async def validate_message(message: str) -> bool:
    try:
        if not message or not isinstance(message, str):
            logger.warning("Message invalide ou non string")
            return False
            
        message = message.strip()
        if len(message) < 3:
            logger.warning("Message trop court")
            return False
            
        if not any(c.isalnum() for c in message):
            logger.warning("Message sans caractères alphanumériques")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Erreur de validation du message: {str(e)}")
        return False
async def get_all_client_names() -> List[str]:
    async with SessionLocal() as session:
        result = await session.execute(select(Client.client))  # au lieu de Client.nom
        return [row[0] for row in result.fetchall()]

async def find_similar_client(message: str, threshold: int = 80) -> Optional[str]:
    all_clients = await get_all_client_names()
    best_match = process.extractOne(message, all_clients)
    if best_match and best_match[1] >= threshold:
        return best_match[0]
    return None

async def initialize_clients():
    await init_db()
    await update_db_structure()
    await afficher_clients()
    await initialize_intentions()

async def initialize_intentions():
    intentions = [
        "Résolution rapide de problèmes",
        "Recherche d'informations techniques",
        "Amélioration de la connaissance produit",
        "Analyse des tendances et problèmes récurrents",
        "Formation et développement personnel",
        "Préparation de réunions ou présentations",
        "Support à la décision",
        "Optimisation des processus internes",
        "Personnalisation du service client",
        "Collaboration inter-équipes"
    ]

    async with SessionLocal() as session:
        async with session.begin():  # Ajout du context manager begin()
            for intention in intentions:
                result = await session.execute(
                    select(Intention).filter(Intention.name == intention)
                )
                existing_intention = result.scalar_one_or_none()
                if not existing_intention:
                    new_intention = Intention(name=intention)
                    session.add(new_intention)
            await session.commit()  # Ajout du commit explicite
async def validate_client_data(client_data: dict) -> tuple[bool, str]:
    """Valide les données d'un client avec des valeurs par défaut."""
    required_fields = ['Client', 'Consultant'] # Seuls champs vraiment requis
    
    # Vérification des champs obligatoires
    missing_fields = [field for field in required_fields if not client_data.get(field)]
    if missing_fields:
        return False, f"Champs obligatoires manquants: {', '.join(missing_fields)}"
    
    # Nettoyage et validation des champs
    client = client_data['Client'].strip()
    consultant = client_data['Consultant'].strip()
    
    if not client or not consultant:
        return False, "Le nom du client et le consultant ne peuvent pas être vides"

    # Valeurs par défaut pour les champs optionnels    
    default_values = {
        'Statut': 'En cours',
        'JIRA': client,
        'ZENDESK': client, 
        'CONFLUENCE': client,
        'ERP': 'Non spécifié'
    }

    # Application des valeurs par défaut si manquantes
    for field, default in default_values.items():
        if not client_data.get(field):
            client_data[field] = default
            
    return True, "Données valides"


async def display_client_report(rapport: dict):
    """
    Affiche un rapport détaillé du chargement des clients.
    """
    logger.info("=== Rapport de chargement des clients ===")
    logger.info(f"Status: {rapport['status']}")
    logger.info(f"Clients traités: {rapport['total_processed']}")
    logger.info(f"Clients valides: {rapport['valid_clients']}")
    logger.info(f"Clients invalides: {rapport['invalid_clients']}")
    
    if rapport["errors"]:
        logger.info("\nErreurs rencontrées:")
        for error in rapport["errors"]:
            logger.error(error)

    logger.info("=====================================")

async def initialize_clients_with_validation():
    """
    Initialisation des clients avec validation et rapport.
    Returns:
        dict: Rapport d'initialisation avec statut et messages
    """
    await init_db()
    await update_db_structure()
    await initialize_intentions()
    
    try:
        async with SessionLocal() as session:
            # Import des clients depuis le CSV
            rapport = await importer_clients_csv(session)
            logger.info(f"Rapport import: {rapport}")
            
            if rapport["status"] != "success":
                logger.error(f"Échec import clients: {rapport['errors']}")
                return rapport
            
            # Vérification finale du nombre de clients
            result = await session.execute(select(func.count()).select_from(Client))
            count = result.scalar()
            
            if count == 0:
                logger.error("Base de données clients vide après import")
                return {
                    "status": "error",
                    "message": "Base de données clients vide après import",
                    "errors": rapport.get("errors", ["Aucun client importé"])
                }
                
            logger.info(f"Base de données initialisée avec {count} clients")
            return {
                "status": "success",
                "message": f"Base de données initialisée avec {count} clients",
                "total_imported": count,
                "details": rapport
            }
                
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation : {str(e)}")
        return {
            "status": "error",
            "message": f"Erreur lors de l'initialisation : {str(e)}",
            "errors": [str(e)]
        }
class ClientResolver:
    def __init__(self):
        self.erp_keywords = {
            'netsuite': ['netsuite', 'ns', 'oracle'],
            'sap': ['sap', 'hana', 'business one']
        }
        
    async def resolve_client(self, text: str) -> Optional[Dict]:
        # Détection ERP
        for erp, keywords in self.erp_keywords.items():
            if any(k in text.lower() for k in keywords):
                return {
                    'type': 'erp',
                    'system': erp,
                    'client': None  # Pas de filtrage client pour les requêtes ERP générales
                }
                
        # Détection client standard
        return await extract_client_name(text)