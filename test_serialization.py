import json
from embedding_service_compat import EmbeddingService, SafeCacheProxy, JSONSerializableEncoder

# Créer un objet cache simple pour tester
class DummyCache:
    pass

# Initialiser les objets
cache = DummyCache()
proxy = SafeCacheProxy(cache)
service = EmbeddingService(cache=cache)

# Test 1: Sérialisation du proxy de cache
print('Test 1: SafeCacheProxy serialization')
print(json.dumps(proxy.__getstate__()))

# Test 2: Sérialisation du service d'embedding avec l'encodeur personnalisé
print('Test 2: EmbeddingService serialization with custom encoder')
try:
    print(json.dumps(service, cls=JSONSerializableEncoder))
except Exception as e:
    print(f"Error: {e.__class__.__name__} - {str(e)}")
    
# Test 3: Sérialisation manuelle en utilisant getstate directement
print('Test 3: Manual safe serialization')
try:
    state = service.__getstate__()
    # Convertir tous les objets non-sérialisables en chaînes
    for key in list(state.keys()):
        try:
            json.dumps(state[key])
        except:
            state[key] = str(state[key])
    print(json.dumps(state))
except Exception as e:
    print(f"Error: {e.__class__.__name__} - {str(e)}")
