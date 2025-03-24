#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_analyze_question.py
Script pour tester directement les fonctions du chatbot et afficher les résultats dans la console.
Permet de visualiser le processus complet : analyse, recherche, et génération de réponse.
"""

import os
import sys
import json
import asyncio
import argparse
import logging
from dotenv import load_dotenv

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)
print("Variables d'environnement chargées :")
print(f"OPENAI_API_KEY: {'Définie' if os.getenv('OPENAI_API_KEY') else 'Non définie'}")
print(f"QDRANT_URL: {'Définie' if os.getenv('QDRANT_URL') else 'Non définie'}")
print(f"QDRANT_API_KEY: {'Définie' if os.getenv('QDRANT_API_KEY') else 'Non définie'}")
print(f"LOG_LEVEL: {'Définie' if os.getenv('LOG_LEVEL') else 'Non définie'}")
print(f"ENVIRONMENT: {'Définie' if os.getenv('ENVIRONMENT') else 'Non définie'}")

# Configuration du logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Import des modules après chargement des variables d'environnement
from chatbot import ChatBot  # noqa: E402

async def test_chatbot_direct(question: str, format_json: bool = False, verbose: bool = False, 
                             only_final_answer: bool = False, skip_formatting: bool = False, raw: bool = False,
                             debug_zendesk: bool = False, timeout: int = 30, progressive: bool = False):
    """
    Test direct des fonctions du chatbot avec visualisation du processus complet.
    
    Args:
        question: Question à analyser et traiter
        format_json: Si True, affiche les résultats au format JSON
        verbose: Si True, affiche plus de détails sur les étapes intermédiaires
        only_final_answer: Si True, affiche uniquement la réponse finale du chatbot
        skip_formatting: Si True, contourne le formatage des réponses et affiche directement les résultats bruts
        raw: Si True, affiche uniquement les requêtes/réponses API brutes sans formatage
        debug_zendesk: Mode de débogage spécifique pour les résultats Zendesk
        timeout: Temps maximum en secondes pour le formatage des réponses (défaut: 30)
        progressive: Formater les résultats progressivement pour éviter les timeouts
    """
    try:
        # Récupération des variables d'environnement
        openai_key = os.getenv("OPENAI_API_KEY")
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        
        if not openai_key or not qdrant_url:
            print("Erreur: Clés API manquantes!")
            print("Veuillez définir les variables d'environnement suivantes dans le fichier .env :")
            print("- OPENAI_API_KEY")
            print("- QDRANT_URL")
            print("- QDRANT_API_KEY (optionnelle)")
            return
        
        # Initialisation du chatbot
        if not only_final_answer:
            print("\nInitialisation du ChatBot...")
        
        chatbot = ChatBot(openai_key, qdrant_url, qdrant_api_key)
        
        # ------------ ÉTAPE 1: ANALYSE DE LA QUESTION ------------
        if not only_final_answer:
            print(f"Analyse de la question: '{question}'")
            print("Veuillez patienter pendant le traitement...\n")
        else:
            print(f"Traitement complet de la question: '{question}'")
            print("Veuillez patienter pendant le traitement...\n")
        
        analysis = await chatbot.analyze_question(question)
        
        if not only_final_answer:
            print("\n" + "=" * 80)
            print("1. RÉSULTAT DE L'ANALYSE")
            print("=" * 80)
            
            if format_json:
                print(json.dumps(analysis, indent=2, ensure_ascii=False))
            else:
                # Affichage structuré des parties principales
                for key, value in analysis.items():
                    if isinstance(value, dict):
                        print(f"\n{key.upper()}:")
                        for subkey, subvalue in value.items():
                            if isinstance(subvalue, dict):
                                print(f"  {subkey}:")
                                for subsubkey, subsubvalue in subvalue.items():
                                    print(f"    {subsubkey}: {subsubvalue}")
                            else:
                                print(f"  {subkey}: {subvalue}")
                    else:
                        print(f"\n{key}: {value}")
        
        # ------------ ÉTAPE 2: DÉTERMINATION DES COLLECTIONS ------------
        collections = chatbot.determine_collections(analysis)
        
        if not only_final_answer:
            print("\n" + "=" * 80)
            print("2. COLLECTIONS À INTERROGER")
            print("=" * 80)
            print(f"Collections: {collections}")
        
        # ------------ ÉTAPE 3: EXTRACTION DU CONTEXTE CLIENT ET DATES ------------
        # Préparation des paramètres pour la recherche
        search_context = analysis.get('SEARCH_CONTEXT', {})
        client_info = None
        if search_context.get('has_client', False):
            client_name = search_context.get('client_name')
            if client_name:
                client_info = {"name": client_name}
                if not only_final_answer:
                    print(f"Client identifié: {client_name}")
        
        # Extraction des dates pour filtrage temporel
        date_debut = None
        date_fin = None
        if search_context.get('has_temporal', False):
            temporal_info = search_context.get('temporal_info', {})
            date_debut = temporal_info.get('start_timestamp')
            date_fin = temporal_info.get('end_timestamp')
            if not only_final_answer and (date_debut or date_fin):
                if verbose:
                    print(f"Filtrage temporel: du {date_debut or 'N/A'} au {date_fin or 'N/A'}")
        
        # Utilisation de la question reformulée si disponible
        query_info = analysis.get('QUERY', {})
        search_query = query_info.get('reformulated', question)
        
        if not only_final_answer:
            print(f"Question reformulée pour la recherche: '{search_query}'")
        
        # ------------ ÉTAPE 4: RECHERCHE DANS LES COLLECTIONS ------------
        if not only_final_answer:
            print("\n" + "=" * 80)
            print("3. EXÉCUTION DE LA RECHERCHE")
            print("=" * 80)
            print(f"Exécution de la recherche pour: '{search_query}'")
        
        search_results = await chatbot.recherche_coordonnee(
            collections, 
            search_query, 
            client_info=client_info,
            date_debut=date_debut,
            date_fin=date_fin
        )
        
        if not only_final_answer:
            print(f"\nNombre de résultats trouvés: {len(search_results)}")
            
            if verbose:
                for i, result in enumerate(search_results[:5], 1):  # Afficher max 5 résultats
                    print(f"\nRésultat #{i}:")
                    
                    # Détection du type de source
                    source_type = getattr(result, 'source', '')
                    print(f"Source: {source_type}")
                    
                    # Extraction du score
                    score = getattr(result, 'score', 0)
                    print(f"Score: {score:.2f}")
                    
                    # Extraction du titre
                    title = getattr(result, 'title', 'Sans titre')
                    print(f"Titre: {title}")
                    
                    # Extraction du contenu
                    content = getattr(result, 'content', 'Pas de contenu')
                    # Tronquer le contenu s'il est trop long
                    if len(content) > 200:
                        content = content[:200] + "..."
                    print(f"Contenu: {content}")
                    
                    # Extraction du payload
                    payload = getattr(result, 'payload', {})
                    if not isinstance(payload, dict):
                        try:
                            payload = payload.__dict__
                        except AttributeError:
                            payload = {"error": "Impossible d'extraire le payload"}
                    
                    # Extraction des champs communs
                    for key in ['url', 'client', 'date', 'id', 'key']:
                        if key in payload:
                            print(f"{key}: {payload[key]}")
                    
                    print('-' * 50)
        
        # ------------ ÉTAPE 5: GÉNÉRATION DE LA RÉPONSE ------------
        if not only_final_answer:
            print("\n" + "=" * 80)
            print("4. GÉNÉRATION DE LA RÉPONSE")
            print("=" * 80 + "\n")
        
        if skip_formatting:
            print("Résultats bruts sans formatage:")
            try:
                # Rendre les résultats sérialisables en JSON et les afficher
                # Cette méthode gère mieux les caractères accentués que print direct
                results_list = []
                for res in search_results:
                    # Convertir chaque résultat en dictionnaire
                    try:
                        result_dict = {
                            "source": getattr(res, "source", ""),
                            "score": getattr(res, "score", 0),
                            "title": getattr(res, "title", "Sans titre"),
                            "content": getattr(res, "content", "Pas de contenu")[:200] + "..." if len(getattr(res, "content", "")) > 200 else getattr(res, "content", ""),
                        }
                        
                        # Ajouter le payload si disponible
                        payload = getattr(res, "payload", {})
                        if not isinstance(payload, dict):
                            try:
                                payload = payload.__dict__
                                print("(Converti de l'objet Python)")
                            except AttributeError:
                                print("(Payload n'est pas un dictionnaire et n'a pas d'attribut __dict__)")
                        
                        # Ajouter les champs communs du payload
                        for key in ["url", "client", "date", "id", "key"]:
                            if key in payload:
                                result_dict[key] = payload[key]
                        
                        results_list.append(result_dict)
                    except Exception as e:
                        results_list.append({"error": f"Erreur lors de la conversion du résultat: {str(e)}"})
                
                # Affichage au format JSON qui gère correctement l'encodage
                print(json.dumps(results_list, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"Erreur lors de l'affichage des résultats bruts: {str(e)}")
                print("Tentative d'affichage simplifié des résultats...")
                for i, res in enumerate(search_results):
                    print(f"Résultat #{i+1}: {type(res).__name__}")
            
            # ------------ ÉTAPE 6: AFFICHAGE DE LA RÉPONSE FINALE ------------
            print("\n" + "=" * 80)
            print("RÉPONSE FINALE DU CHATBOT")
            print("=" * 80 + "\n")
            print("Formatage ignoré, affichage des résultats bruts uniquement")
        else:
            # Mode de débogage spécifique pour Zendesk
            if debug_zendesk:
                print("\n" + "=" * 80)
                print("MODE DÉBOGAGE ZENDESK")
                print("=" * 80)
                
                zendesk_results = [r for r in search_results 
                                   if hasattr(r, 'payload') and 
                                   (getattr(r, 'source', '') == 'zendesk' or
                                    isinstance(r.payload, dict) and r.payload.get('source_type') == 'zendesk' or
                                    hasattr(r.payload, 'url') and 'zendesk.com' in getattr(r.payload, 'url', ''))]
                
                if zendesk_results:
                    print(f"Nombre de résultats Zendesk trouvés: {len(zendesk_results)}\n")
                    
                    for i, res in enumerate(zendesk_results, 1):
                        print(f"[Zendesk Résultat #{i}]")
                        print(f"Type: {type(res).__name__}")
                        
                        try:
                            # Récupération du score
                            score = getattr(res, 'score', 0)
                            print(f"Score: {score:.4f}")
                            
                            # Récupération et affichage des attributs directs
                            for attr in ['id', 'title', 'content', 'source']:
                                if hasattr(res, attr):
                                    value = getattr(res, attr)
                                    print(f"{attr}: {value}")
                            
                            # Récupération et affichage du payload
                            payload = getattr(res, 'payload', None)
                            if payload:
                                print("\nPayload structure:")
                                
                                # Si c'est un objet Python, le convertir en dictionnaire
                                if not isinstance(payload, dict):
                                    try:
                                        payload = payload.__dict__
                                        print("(Converti de l'objet Python)")
                                    except AttributeError:
                                        print("(Payload n'est pas un dictionnaire et n'a pas d'attribut __dict__)")
                                
                                if isinstance(payload, dict):
                                    # Afficher les clés du payload
                                    print(f"Clés: {list(payload.keys())}")
                                    
                                    # Afficher le contenu du payload
                                    for key, value in payload.items():
                                        if isinstance(value, (str, int, float, bool, type(None))):
                                            print(f"  {key}: {value}")
                                        else:
                                            print(f"  {key}: {type(value).__name__} (complexe)")
                            else:
                                print("\nPayload: None")
                            
                            print('-' * 50)
                        except Exception as e:
                            print(f"Erreur pendant l'analyse du résultat Zendesk: {str(e)}")
                            print('-' * 50)
                else:
                    print("Aucun résultat Zendesk trouvé dans les données.")
                
                print("\n")
            
            # Formatage de la réponse
            if progressive:
                # Formatage progressif des résultats
                print("Formatage progressif des résultats...")
                
                # Initialisation d'une structure pour la réponse formatée progressive
                progressive_response = {
                    "text": "Résultats pour: " + (analysis.get("QUERY", {}).get("reformulated", question) if question else "Recherche"),
                    "blocks": [{
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Résultats de recherche ({len(search_results)})",
                            "emoji": True
                        }
                    }]
                }
                
                # Ajout d'un contexte de question si disponible
                if question:
                    progressive_response["blocks"].append({
                        "type": "context",
                        "elements": [{
                            "type": "mrkdwn",
                            "text": f"*Question:* {question}"
                        }]
                    })
                
                # Formatage individuel pour chaque résultat avec timeout plus court
                formatted_results = []
                failed_results = 0
                
                for i, result in enumerate(search_results):
                    try:
                        print(f"Formatage du résultat {i+1}/{len(search_results)}...", end="", flush=True)
                        
                        # Création d'une liste avec un seul résultat pour le formatage
                        single_result = [result]
                        
                        try:
                            # Formatage avec un timeout plus court (5 secondes) par résultat
                            async with asyncio.timeout(5):
                                formatted_single = await chatbot.format_response(
                                    single_result,
                                    question=None  # On ne veut pas les en-têtes, juste le bloc de résultat
                                )
                                
                                # Extraction et ajout des blocs formatés (en ignorant les en-têtes)
                                result_blocks = []
                                for block in formatted_single.get("blocks", []):
                                    # Ignorer les blocs d'en-tête et de contexte
                                    if block.get("type") not in ["header", "context"]:
                                        result_blocks.append(block)
                                
                                if result_blocks:
                                    formatted_results.extend(result_blocks)
                                    print(" Terminé")
                                else:
                                    print(" Aucun bloc formaté généré")
                                    failed_results += 1
                                    
                        except asyncio.TimeoutError:
                            print(" Timeout dépassé")
                            failed_results += 1
                            
                            # Ajout d'un bloc d'erreur
                            formatted_results.append({
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"⚠️ Le formatage du résultat #{i+1} a pris trop de temps (> 5s)"
                                }
                            })
                            
                        except Exception as e:
                            print(f" Erreur: {str(e)}")
                            failed_results += 1
                            
                            # Ajout d'un bloc d'erreur
                            formatted_results.append({
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"⚠️ Erreur lors du formatage du résultat #{i+1}: {str(e)}"
                                }
                            })
                    
                    except Exception as e:
                        print(f"\nErreur lors du traitement du résultat {i+1}: {str(e)}")
                        failed_results += 1
                
                # Résumé du formatage progressif
                print(f"\nFormatage progressif terminé: {len(formatted_results)} blocs générés, {failed_results} échecs")
                
                # Ajout des blocs formatés au résultat final
                progressive_response["blocks"].extend(formatted_results)
                
                # Utilisation de la réponse formatée progressive
                formatted_response = progressive_response
                
            else:
                # Formatage standard avec le timeout global
                try:
                    # La méthode format_response est asynchrone et doit être attendue
                    # Timeout configurable pour éviter de bloquer indéfiniment
                    async with asyncio.timeout(timeout):
                        formatted_response = await chatbot.format_response(
                            search_results, 
                            question=analysis.get("QUERY", {}).get("reformulated", question),
                            debug_zendesk=debug_zendesk,
                            progressive=progressive
                        )
                except asyncio.TimeoutError:
                    logging.error(f"Timeout lors de la génération de la réponse pour: '{question}'")
                    formatted_response = {
                        "text": "Délai d'attente dépassé lors de la génération de la réponse. Problème de performance détecté dans le chatbot.",
                        "blocks": [{
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"⚠️ *Délai d'attente dépassé ({timeout}s)*\n\nLe formatage de la réponse a pris trop de temps. Cela peut indiquer un problème dans le traitement des résultats ou dans l'API utilisée pour la génération du résumé."}
                        }]
                    }
                except Exception as e:
                    logging.error(f"Erreur lors de la génération de la réponse: {str(e)}")
                    formatted_response = {
                        "text": f"Erreur lors de la génération de la réponse: {str(e)}",
                        "blocks": [{
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"Erreur lors de la génération de la réponse: {str(e)}"}
                        }]
                    }
            
            # ------------ ÉTAPE 6: AFFICHAGE DE LA RÉPONSE FINALE ------------
            print("\n" + "=" * 80)
            print("RÉPONSE FINALE DU CHATBOT")
            print("=" * 80 + "\n")
            
            if raw:
                print("Réponse brute sans formatage:")
                print(formatted_response)
            elif format_json:
                print(json.dumps(formatted_response, indent=2, ensure_ascii=False))
            else:
                # Affichage du texte principal
                try:
                    if "text" in formatted_response:
                        # Remplacer les emojis et caractères spéciaux par des alternatives ASCII
                        text = formatted_response["text"]
                        # Remplacer les emoji courants par des équivalents textuels
                        text = text.replace("\U0001f7e2", "[VERT]")  # Cercle vert
                        text = text.replace("\U0001f534", "[ROUGE]")  # Cercle rouge
                        text = text.replace("\U0001f7e0", "[ORANGE]") # Cercle orange
                        text = text.replace("\U0001f7e1", "[JAUNE]")  # Cercle jaune
                        text = text.replace("\U00002705", "[VALIDÉ]") # Marque de validation
                        text = text.replace("\U0000274c", "[ERREUR]") # Croix rouge
                        text = text.replace("•", "-")                 # Puce
                        print(text)
                        print()
                    
                    # Affichage des blocs et attachements
                    if "blocks" in formatted_response:
                        for i, block in enumerate(formatted_response["blocks"]):
                            try:
                                if "text" in block:
                                    block_text = block["text"].get("text", "")
                                    # Même traitement des emojis que pour le texte principal
                                    block_text = block_text.replace("\U0001f7e2", "[VERT]")
                                    block_text = block_text.replace("\U0001f534", "[ROUGE]")
                                    block_text = block_text.replace("\U0001f7e0", "[ORANGE]")
                                    block_text = block_text.replace("\U0001f7e1", "[JAUNE]")
                                    block_text = block_text.replace("\U00002705", "[VALIDÉ]")
                                    block_text = block_text.replace("\U0000274c", "[ERREUR]")
                                    block_text = block_text.replace("•", "-")
                                    print(block_text)
                                
                                if "attachments" in block:
                                    for attachment in block["attachments"]:
                                        if "fields" in attachment:
                                            for field in attachment["fields"]:
                                                field_title = field.get("title", "").replace("\U0001f7e2", "[VERT]").replace("\U0001f534", "[ROUGE]")
                                                field_value = field.get("value", "").replace("\U0001f7e2", "[VERT]").replace("\U0001f534", "[ROUGE]")
                                                print(f"{field_title}: {field_value}")
                                        
                                        if "text" in attachment:
                                            attachment_text = attachment["text"].get("text", "").replace("\U0001f7e2", "[VERT]").replace("\U0001f534", "[ROUGE]")
                                            print(attachment_text)
                            except Exception as e:
                                print(f"Erreur dans l'affichage du bloc {i}: {str(e)}")
                        
                        print('-' * 50)
                except Exception as e:
                    print(f"Erreur lors de l'affichage de la réponse: {str(e)}")
                    print("Affichage simplifié de la réponse:")
                    if "text" in formatted_response:
                        try:
                            print(formatted_response["text"].encode('ascii', 'replace').decode('ascii'))
                        except Exception as e:
                            print(f"[Texte avec caractères spéciaux non affichables: {str(e)}]")
                
                # Affichage des actions disponibles
                if "actions" in formatted_response and not only_final_answer:
                    print("\nActions disponibles:")
                    for action in formatted_response["actions"]:
                        print(f"- {action.get('text', {}).get('text', 'Action')}")
        
        print("\n" + "=" * 80)
    
    except Exception as e:
        logging.error(f"Erreur lors du test: {str(e)}")
        traceback = sys.exc_info()[2]
        print(f"Erreur: {str(e)}")
        print(f"Traceback: {traceback.tb_frame.f_code.co_filename} ligne {traceback.tb_lineno}")

def main():
    parser = argparse.ArgumentParser(description='Test des fonctions du chatbot')
    parser.add_argument('question', nargs='?', default=None, help='Question à analyser')
    parser.add_argument('--json', '-j', action='store_true', help='Format de sortie JSON')
    parser.add_argument('--verbose', '-v', action='store_true', help='Mode verbeux (plus de détails)')
    parser.add_argument('--answer-only', '-a', action='store_true', 
                        help='Afficher uniquement la réponse finale du chatbot')
    parser.add_argument("--skip-formatting", action="store_true", 
                      help="Contourner le formatage des réponses et afficher directement les résultats bruts")
    parser.add_argument("--raw", action="store_true",
                      help="Afficher uniquement les requêtes/réponses API brutes sans formatage")
    parser.add_argument("--debug-zendesk", action="store_true",
                      help="Mode de débogage spécifique pour les résultats Zendesk")
    parser.add_argument("--timeout", type=int, default=30,
                      help="Temps maximum en secondes pour le formatage des réponses (défaut: 30)")
    parser.add_argument("--progressive", action="store_true",
                      help="Formater les résultats progressivement pour éviter les timeouts")
    
    args = parser.parse_args()
    
    # Si la question n'est pas fournie en argument, demander à l'utilisateur de la saisir
    question = args.question
    if not question:
        print("\n" + "=" * 80)
        print("TEST DU CHATBOT - PROCESSUS COMPLET")
        print("=" * 80)
        print("\nVeuillez saisir votre question (tapez 'quit' pour quitter):")
        
        # Boucle pour permettre de poser plusieurs questions successives
        while True:
            try:
                question = input("\n> ")
                if question.lower() in ['quit', 'exit', 'q']:
                    print("Au revoir!")
                    break
                
                if not question.strip():
                    print("Question vide. Veuillez saisir une question valide.")
                    continue
                
                # Exécution de la fonction de test avec la question saisie
                asyncio.run(test_chatbot_direct(
                    question, 
                    format_json=args.json, 
                    verbose=args.verbose,
                    only_final_answer=args.answer_only,
                    skip_formatting=args.skip_formatting,
                    raw=args.raw,
                    debug_zendesk=args.debug_zendesk,
                    timeout=args.timeout,
                    progressive=args.progressive
                ))
                
                # Demander une nouvelle question
                print("\nSaisissez une nouvelle question ou 'quit' pour quitter:")
            
            except KeyboardInterrupt:
                print("\nProgramme interrompu par l'utilisateur.")
                break
                
            except EOFError:
                print("\nFin d'entrée détectée. Arrêt du programme.")
                break
            
            except Exception as e:
                print(f"Erreur: {str(e)}")
                print("Saisissez une nouvelle question ou 'quit' pour quitter (Ctrl+C pour quitter):")
                # Éviter une boucle infinie en cas d'erreur persistante
                try:
                    # Attendre une entrée avec un timeout
                    # Si l'utilisateur ne répond pas, sortir après 3 tentatives
                    for _ in range(3):
                        try:
                            new_input = input("\n> ")
                            if new_input.lower() in ['quit', 'exit', 'q']:
                                print("Au revoir!")
                                return
                            elif new_input.strip():
                                # Si l'utilisateur a saisi quelque chose de valide, continuer normalement
                                break
                        except (EOFError, KeyboardInterrupt):
                            print("\nProgramme terminé.")
                            return
                except Exception as e:
                    # En cas d'erreur persistante, sortir de la boucle
                    print(f"\nTrop d'erreurs successives: {str(e)}. Programme terminé.")
                    break
    else:
        # Si la question est fournie en argument, l'utiliser directement
        asyncio.run(test_chatbot_direct(
            question, 
            format_json=args.json, 
            verbose=args.verbose,
            only_final_answer=args.answer_only,
            skip_formatting=args.skip_formatting,
            raw=args.raw,
            debug_zendesk=args.debug_zendesk,
            timeout=args.timeout,
            progressive=args.progressive
        ))

if __name__ == "__main__":
    main()
