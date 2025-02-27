# tests/test_configuration.py
import pytest
import os
from unittest.mock import patch, MagicMock
from configuration import validate_initial_setup, init_config, Config

@pytest.mark.asyncio
async def test_validate_initial_setup_missing_env():
    # Test avec variables d'environnement manquantes
    with patch.dict(os.environ, {}, clear=True):
        result = await validate_initial_setup()
        assert result["openai"] is False
        assert result["slack"] is False
        assert result["qdrant"] is False

@pytest.mark.asyncio
async def test_validate_initial_setup_partial_env():
    # Test avec seulement certaines variables définies
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}, clear=True):
        result = await validate_initial_setup()
        assert result["openai"] is True
        assert result["slack"] is False
        assert result["qdrant"] is False

@pytest.mark.asyncio
async def test_init_config():
    # Test d'initialisation de la configuration
    with patch('configuration.validate_initial_setup', return_value={"openai": True, "slack": True, "qdrant": True}):
        with patch('configuration.get_clients') as mock_get_clients:
            mock_clients = MagicMock()
            mock_get_clients.return_value.__aenter__.return_value = mock_clients
            result = await init_config()
            assert result is mock_clients