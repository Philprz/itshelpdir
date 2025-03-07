# base_de_donnees.py
import asyncio
import logging
import os
import re
import uuid
import weakref

import aiosqlite
import sqlite3

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON, inspect,
    Float, Boolean, Index, select, event, Engine
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

from configuration import config, logger


def normalize_string(s: str) -> str:
    """Normalise une chaîne de caractères en majuscules sans caractères spéciaux"""
    if not s:
        return ""
    # Conversion en majuscules et suppression des espaces en début/fin
    normalized = s.upper().strip()
    # Remplacement des multiples espaces par un seul
    normalized = re.sub(r'\s+', ' ', normalized)
    # Suppression des caractères spéciaux tout en gardant les espaces et tirets
    normalized = ''.join(c for c in normalized if c.isalnum() or c in ' -')
    return normalized.strip()
Base = declarative_base()
logging.basicConfig(
    level=logging.WARNING,  # Passage de DEBUG à WARNING
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# Chemin relatif avec vérification d'existence
db_path = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./data/database.db')
# Extraction du chemin du fichier depuis l'URL
file_path = db_path.replace('sqlite+aiosqlite:///', '')
db_dir = os.path.dirname(file_path)

# Création du répertoire si nécessaire
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# Initialisation de l'engine SQLite asynchrone
engine = create_async_engine(db_path, connect_args={"check_same_thread": False})

class PayloadMapping:
    COMMON_FIELDS = {
        'client', 'erp', 'created', 'updated', 'content', 'source_type', 'id'
    }

    SOURCE_FIELDS = {
        'jira': {
            'required': {'key', 'summary', 'resolution', 'assignee', 'url'},
            'optional': {'time_spent', 'comments', 'attachments_desc'}
        },
        'zendesk': {
            'required': {'ticket_id', 'status', 'priority', 'assignee', 'url'},
            'optional': {'comments', 'attachments_desc'}
        },
        'confluence': {
            'required': {'space_id', 'page_url', 'assignee'},
            'optional': {'space_url', 'attachments_desc'}
        },
        'netsuite': {
            'required': {'title', 'content_hash', 'url', 'last_updated'},
            'optional': {'summary'}
        },
        'netsuite_dummies': {
            'required': {'title', 'text', 'pdf_path'},
            'optional': set()
        },
        'sap': {
            'required': {'title', 'text', 'pdf_path'},
            'optional': set()
        }
    }
class SessionWithUserTracking(AsyncSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_session_id = None

    @asynccontextmanager
    async def session_scope(self, user_id: str):
        self.user_session_id = user_id
        try:
            yield self
        finally:
            self.user_session_id = None

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=SessionWithUserTracking
)

@asynccontextmanager
async def get_session(user_id: str = None, retries: int = 3):
    """
    Gestionnaire de contexte pour la session de BD avec gestion avancée:
    - Retentatives en cas d'erreurs de connexion
    - Délai exponentiel entre les tentatives
    - Traçage des transactions
    - Validation des transactionnalité
    
    Args:
        user_id: Identifiant utilisateur pour le traçage (optionnel)
        retries: Nombre de tentatives en cas d'erreur (défaut: 3)
    """
    session = None
    for attempt in range(retries):
        try:
            # Création de session avec traçage
            session = SessionLocal()
            
            # Ajout d'identifiants de transaction pour le traçage
            transaction_id = f"tx-{uuid.uuid4()}"
            
            # Métadonnées de transaction
            transaction_metadata = {
                'transaction_id': transaction_id,
                'user_id': user_id or 'system',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'attempt': attempt + 1
            }
            
            logger.debug(f"DB Transaction started: {transaction_metadata}")
            
            if user_id:
                async with session.session_scope(user_id):
                    # Passage du contexte pour traçage SQL
                    session.info['transaction_metadata'] = transaction_metadata
                    yield session
            else:
                # Passage du contexte pour traçage SQL
                session.info['transaction_metadata'] = transaction_metadata
                yield session
                
            # Commit avec validation des contraintes
            await session.commit()
            
            logger.debug(f"DB Transaction committed: {transaction_id}")
            break
            
        except (sqlite3.OperationalError, aiosqlite.OperationalError) as e:
            # Gestion spécifique des erreurs SQLite
            if "database is locked" in str(e) and attempt < retries - 1:
                # Délai exponentiel avant nouvelle tentative
                retry_delay = 0.1 * (2 ** attempt)
                logger.warning(f"Database locked, retrying in {retry_delay:.2f}s (attempt {attempt+1}/{retries})")
                
                if session:
                    await session.rollback()
                    await session.close()
                    session = None
                    
                await asyncio.sleep(retry_delay)
                continue
            else:
                # Erreur fatale ou dernière tentative échouée
                logger.error(f"Database operational error: {str(e)}")
                if session:
                    await session.rollback()
                raise
                
        except Exception as e:
            # Autres types d'erreurs
            logger.error(f"Database session error: {str(e)}")
            if session:
                await session.rollback()
            raise
            
        finally:
            # Fermeture propre dans tous les cas
            if session:
                try:
                    await session.close()
                except Exception as close_error:
                    logger.error(f"Error closing session: {str(close_error)}")
class Conversation(Base):
    __tablename__ = 'conversations'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    conversation_id = Column(Integer, unique=True, nullable=True)
    user_name = Column(String, nullable=True)
    context = Column(Text)
    last_updated = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    last_interaction = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    last_search_results = Column(JSON, nullable=True)
class TestResult(Base):
    __tablename__ = 'test_results'
    id = Column(Integer, primary_key=True, autoincrement=True)
    intention_category = Column(String, nullable=False)
    query = Column(Text, nullable=False)
    client_name = Column(String, nullable=True)
    embedding_generated = Column(Boolean, default=False)
    search_successful = Column(Boolean, default=False)
    results_count = Column(Integer, default=0)
    average_relevance_score = Column(Float, nullable=True)
    response_time = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    results_sources = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index('idx_intention_timestamp', 'intention_category', 'timestamp'),
        Index('idx_client_timestamp', 'client_name', 'timestamp'),
    )

class Client(Base):
    __tablename__ = 'clients'
    
    # Colonnes de la table
    id = Column(Integer, primary_key=True, autoincrement=True)
    client = Column(String, nullable=False)
    consultant = Column(String)
    statut = Column(String)
    jira = Column(String)
    zendesk = Column(String)
    confluence = Column(String)
    erp = Column(String)
    
    @property
    def variations(self) -> set:
        """
        Retourne toutes les variations possibles du nom du client.
        Combine le nom principal avec les valeurs des champs jira, zendesk et confluence.
        """
        variations = {self.client}
        for field in [self.jira, self.zendesk, self.confluence]:
            if field and field != self.client:
                variations.add(field)
        return variations

    def matches_variation(self, query: str) -> bool:
        """
        Vérifie si la requête correspond à une variation du nom du client.
        La comparaison se fait après normalisation (suppression d'espaces, majuscules, caractères spéciaux).
        """
        normalized_query = normalize_string(query)
        return any(normalize_string(var) in normalized_query for var in self.variations)


class SatisfactionRating(Base):
    __tablename__ = 'satisfaction_ratings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    rating = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class Intention(Base):
    __tablename__ = 'intentions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)

class LearnedIntention(Base):
    __tablename__ = 'learned_intentions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    intention_name = Column(String(255), nullable=False)
    example_text = Column(Text, nullable=False)
    client_context = Column(String, nullable=True)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

def clean_text(text):
    """Nettoie un texte en ne gardant que les caractères alphanumériques"""
    if text is None:
        return ""
    return re.sub(r'[^a-zA-Z0-9\s]', '', str(text))

async def init_db():
    try:
        # Connexion rapide pour vérifier l'accès à la BD
        try:
            connection = await engine.connect()
            await connection.close()
            logger.info("Database connection successful.")
        except Exception as e:
            logger.warning(f"Database connection check: {str(e)}")
            os.makedirs('data', exist_ok=True)
        # Création des tables avec gestion explicite des erreurs
        async with engine.begin() as conn:
            # Vérification explicite si la table existe déjà
            exists = await conn.run_sync(lambda conn: inspect(conn).has_table('conversations'))
            
            if not exists:
                # Créer les tables uniquement si elles n'existent pas
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Database tables created successfully.")
            else:
                logger.info("Tables already exist, skipping creation.")
                
    except Exception as e:
        logger.error(f"Error during database initialization: {str(e)}")            


def create_sqlite_functions(conn):
    def normalize_string(s):
        if s is None:
            return None
        # Conversion en majuscules et suppression des espaces en début/fin
        normalized = s.upper().strip()
        # Remplacement des multiples espaces par un seul
        normalized = re.sub(r'\s+', ' ', normalized)
        # Suppression des caractères spéciaux tout en gardant les espaces et tirets
        normalized = ''.join(c for c in normalized if c.isalnum() or c in ' -')
        return normalized.strip()
    
    conn.create_function("normalize_string", 1, normalize_string)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    create_sqlite_functions(dbapi_connection)
async def update_db_structure():
    """Vérification et mise à jour de la structure de la base de données"""
    from sqlalchemy import text
    logger.info("Checking and updating database structure...")
    async with engine.begin() as conn:
        def inspect_tables(connection):
            inspector = inspect(connection)
            if not inspector.has_table('clients'):
                return set()
            existing_columns = {column['name'] for column in inspector.get_columns('clients')}
            return existing_columns

        try:
            existing_columns = await conn.run_sync(inspect_tables)
            
            # Si la table n'existe pas encore, on skip
            if not existing_columns:
                logger.info("Table clients n'existe pas encore - skip update")
                return
                
            required_columns = {'id', 'client', 'consultant', 'statut', 'jira', 'zendesk', 'confluence', 'erp'}
            missing_columns = required_columns - existing_columns

            if missing_columns:
                logger.info(f"Ajout des colonnes manquantes: {missing_columns}")
                # Création des commandes ALTER TABLE de manière asynchrone
                for column in missing_columns:
                    sql = f"ALTER TABLE clients ADD COLUMN {column} VARCHAR"
                    await conn.execute(text(sql))
                logger.info("Structure de la base de données mise à jour avec succès.")
            else:
                logger.info("Structure de la base de données à jour.")
                
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la structure: {str(e)}")
            raise



class BaseRepository(ABC):
    def __init__(self, session: AsyncSession):
        # Session asynchrone fournie par le contexte get_session()
        self._session = session

    @abstractmethod
    async def get(self, id: int) -> Optional[Any]:
        # Récupère un enregistrement par son ID
        pass

    @abstractmethod
    async def get_all(self) -> List[Any]:
        # Récupère tous les enregistrements
        pass

    @abstractmethod
    async def add(self, entity: Any) -> Any:
        # Ajoute un nouvel enregistrement et le commit
        pass

    @abstractmethod
    async def update(self, entity: Any) -> Any:
        # Met à jour un enregistrement existant et le commit
        pass

    @abstractmethod
    async def delete(self, id: int) -> bool:
        # Supprime un enregistrement par son ID et commit
        pass

class ConversationRepository(BaseRepository):
    async def get(self, user_id: str) -> Optional[Conversation]:
        # Récupère une conversation par user_id
        stmt = select(Conversation).filter_by(user_id=user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self) -> List[Conversation]:
        # Récupère toutes les conversations
        stmt = select(Conversation)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def add(self, conversation: Conversation) -> Conversation:
        # Ajoute une conversation et commit
        self._session.add(conversation)
        await self._session.commit()
        return conversation

    async def update(self, conversation: Conversation) -> Conversation:
        # Met à jour une conversation existante et commit
        await self._session.merge(conversation)
        await self._session.commit()
        return conversation

    async def delete(self, user_id: str) -> bool:
        # Supprime une conversation par user_id et commit
        conversation = await self.get(user_id)
        if conversation:
            await self._session.delete(conversation)
            await self._session.commit()
            return True
        return False

class ClientRepository(BaseRepository):
    async def get(self, id: int) -> Optional[Client]:
        # Récupère un client par ID
        stmt = select(Client).filter_by(id=id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    
    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Any]:
        pass

    async def get_all(self) -> List[Client]:
        # Récupère tous les clients
        stmt = select(Client)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def add(self, client: Client) -> Client:
        # Ajoute un client et commit
        self._session.add(client)
        await self._session.commit()
        return client

    async def update(self, client: Client) -> Client:
        # Met à jour un client existant et commit
        await self._session.merge(client)
        await self._session.commit()
        return client

    async def delete(self, id: int) -> bool:
        # Supprime un client par ID et commit
        client = await self.get(id)
        if client:
            await self._session.delete(client)
            await self._session.commit()
            return True
        return False
class DBClient(Base):
    __tablename__ = 'clients'
    
    @property
    def variations(self):
        """Retourne toutes les variations possibles du nom du client"""
        variations = {self.client}  # Le nom normalisé
        
        # Ajout des variations depuis JIRA/Zendesk/Confluence si elles existent
        for field in [self.jira, self.zendesk, self.confluence]:
            if field and field != self.client:
                variations.add(field)
                
        return variations

    def matches_variation(self, query: str) -> bool:
        """Vérifie si la requête correspond à une variation du nom"""
        normalized_query = normalize_string(query)
        return any(normalize_string(var) in normalized_query 
                  for var in self.variations)
class ClientContext:
    def __init__(self):
        self._client_info = None
        self._lock = asyncio.Lock()

    async def set_client(self, client_info: dict):
        async with self._lock:
            self._client_info = client_info

    async def get_client(self) -> Optional[dict]:
        async with self._lock:
            return self._client_info.copy() if self._client_info else None
        

class QdrantSessionManager:
    def __init__(self, client):
        self.client = client
        self._active_sessions = weakref.WeakSet()
        self._closed = False
        self._lock = asyncio.Lock()  # Ajout d'un verrou pour les opérations concurrentes

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
        
    def add_session(self, session):
        """Ajoute une session au gestionnaire avec vérification."""
        if not self._closed and session is not None:
            self._active_sessions.add(session)
        
    async def cleanup(self):
        """Nettoyage des sessions actives avec gestion robuste des erreurs."""
        async with self._lock:  # Protection contre les accès concurrents
            self._closed = True
            for session in list(self._active_sessions):  # Copie pour éviter les erreurs de modification pendant l'itération
                try:
                    if session is not None and hasattr(session, 'closed') and not session.closed:
                        await session.close()
                except Exception as e:
                    logger.error(f"Erreur fermeture session: {e}")
            self._active_sessions.clear()