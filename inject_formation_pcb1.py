"""
Injection — Formation 1 : Maîtriser le cadre conceptuel du PCB révisé de l'UMOA
----------------------------------------------------------------------------------
Injecte directement dans MongoDB Atlas (base Heroku).

Usage :
    python inject_formation_pcb1.py
    python inject_formation_pcb1.py --org-code MIZNAS_TEST
    python inject_formation_pcb1.py --org-id <objectid>
"""

import asyncio
import argparse
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

# ── Connexion MongoDB Atlas ────────────────────────────────────────────────────

MONGO_URI = (
    "mongodb+srv://netmorphus:JWBUl8yYw5BD43Cq"
    "@rag-new-cluster.bsbmqdo.mongodb.net"
    "/assistant_banque_db?appName=rag-new-cluster"
)
DB_NAME = "assistant_banque_db"

# ── Données de la formation ────────────────────────────────────────────────────

FORMATION = {
    "titre": "Maîtriser le cadre conceptuel du PCB révisé de l'UMOA",
    "description": (
        "Principes comptables, hypothèses de base et structure du référentiel "
        "comptable bancaire révisé."
    ),
    "bloc_numero": 1,
    "bloc_titre": "Plan Comptable Bancaire (PCB révisé)",
    "status": "published",
    "modules": [

        # ══════════════════════════════════════════════════════════════════════
        # MODULE 1 — Contexte et objectifs de la révision
        # ══════════════════════════════════════════════════════════════════════
        {
            "titre": "Module 1 — Contexte et objectifs de la révision",
            "chapitres": [
                {
                    "titre": "Historique du PCB 1996 et ses limites",
                    "introduction": (
                        "Ce chapitre retrace l'origine du Plan Comptable Bancaire de 1996, "
                        "ses principes structurants et les raisons qui ont rendu sa révision nécessaire."
                    ),
                    "parties": [
                        {
                            "titre": "Origines du PCB dans l'espace UMOA",
                            "contenu": (
                                "Rédige un contenu pédagogique destiné à des banquiers de l'UEMOA, niveau professionnel, "
                                "sur la naissance du Plan Comptable Bancaire (PCB) de 1996. Explique le contexte économique "
                                "et réglementaire de l'époque, le rôle de l'harmonisation comptable, et les raisons qui ont "
                                "conduit à l'adoption d'un référentiel commun. Le ton doit être pédagogique, précis et orienté métier."
                            ),
                        },
                        {
                            "titre": "Principes structurants du PCB 1996",
                            "contenu": (
                                "Explique, pour un public de banquiers UEMOA de niveau professionnel, les grands principes de "
                                "fonctionnement du PCB 1996. Présente la logique de classement des opérations bancaires, la structure "
                                "des comptes, et l'objectif de normalisation des traitements comptables. Mets l'accent sur les apports "
                                "du référentiel pour la production des états financiers bancaires."
                            ),
                        },
                        {
                            "titre": "Limites techniques et opérationnelles",
                            "contenu": (
                                "Analyse les limites du PCB 1996 pour des banquiers UEMOA, avec un ton pédagogique et précis. "
                                "Traite les insuffisances liées à la transparence financière, à la comparabilité internationale, "
                                "à la prise en compte des nouveaux instruments financiers et à l'évolution des risques bancaires. "
                                "Montre pourquoi une révision est devenue nécessaire."
                            ),
                        },
                    ],
                },
                {
                    "titre": "Influence des normes IFRS",
                    "introduction": (
                        "Ce chapitre explore comment les normes IFRS ont inspiré la modernisation du PCB dans l'espace UEMOA."
                    ),
                    "parties": [
                        {
                            "titre": "Logique générale des normes IFRS",
                            "contenu": (
                                "Présente les normes IFRS à destination de banquiers UEMOA, niveau professionnel, avec un style "
                                "clair et pédagogique. Explique leur philosophie fondée sur l'image fidèle, la substance économique "
                                "des opérations, la juste valeur et la comparabilité des informations financières. Relie ces principes "
                                "aux besoins du secteur bancaire."
                            ),
                        },
                        {
                            "titre": "Apports des IFRS à la comptabilité bancaire",
                            "contenu": (
                                "Développe les principaux apports des IFRS pour la comptabilité bancaire, en visant un public de "
                                "banquiers UEMOA. Insiste sur la qualité de l'information financière, la reconnaissance des instruments "
                                "financiers, la mesure du risque, les dépréciations et la présentation des performances. Garde un ton "
                                "professionnel et précis."
                            ),
                        },
                        {
                            "titre": "Adaptation au contexte UEMOA",
                            "contenu": (
                                "Explique comment l'influence des normes IFRS a inspiré la révision du PCB dans l'UEMOA. "
                                "Adresse-toi à des banquiers de niveau professionnel et montre les points d'alignement possibles, "
                                "mais aussi les adaptations nécessaires au contexte régional, réglementaire et prudentiel. "
                                "Le contenu doit rester pédagogique, structuré et concret."
                            ),
                        },
                    ],
                },
                {
                    "titre": "Objectifs : image fidèle et comparabilité",
                    "introduction": (
                        "Ce chapitre traite des deux objectifs centraux de la révision : garantir une image fidèle "
                        "et améliorer la comparabilité entre établissements bancaires."
                    ),
                    "parties": [
                        {
                            "titre": "Notion d'image fidèle",
                            "contenu": (
                                "Rédige un contenu pédagogique pour banquiers UEMOA expliquant la notion d'image fidèle dans "
                                "la présentation des comptes bancaires. Définis le concept, montre son intérêt pour l'analyse "
                                "financière et la gestion des risques, et précise pourquoi il constitue un objectif central de "
                                "la révision du PCB."
                            ),
                        },
                        {
                            "titre": "Amélioration de la comparabilité",
                            "contenu": (
                                "Explique, pour un public professionnel du secteur bancaire UEMOA, comment la révision du PCB "
                                "vise à améliorer la comparabilité entre établissements. Aborde la standardisation des méthodes "
                                "comptables, la cohérence des états financiers et l'intérêt pour les autorités de supervision, "
                                "les investisseurs et les analystes."
                            ),
                        },
                        {
                            "titre": "Utilité pour le pilotage bancaire",
                            "contenu": (
                                "Développe le lien entre image fidèle, comparabilité et pilotage de la banque. Le contenu doit "
                                "s'adresser à des banquiers UEMOA de niveau professionnel, avec un ton pédagogique et précis. "
                                "Montre comment des états financiers plus fiables facilitent la prise de décision, le contrôle "
                                "interne, la supervision prudentielle et l'évaluation de la performance."
                            ),
                        },
                    ],
                },
                {
                    "titre": "Champ d'application",
                    "introduction": (
                        "Ce chapitre définit les institutions concernées par le PCB révisé, le périmètre des opérations "
                        "couvertes et son articulation avec les autres référentiels."
                    ),
                    "parties": [
                        {
                            "titre": "Institutions concernées",
                            "contenu": (
                                "Présente le champ d'application du PCB révisé de l'UMOA à destination de banquiers UEMOA, "
                                "niveau professionnel. Identifie les catégories d'établissements et d'institutions concernées, "
                                "et explique pourquoi un référentiel comptable bancaire harmonisé est nécessaire pour l'ensemble "
                                "du secteur."
                            ),
                        },
                        {
                            "titre": "Périmètre des opérations visées",
                            "contenu": (
                                "Explique, de façon pédagogique et précise, le périmètre des opérations couvertes par le PCB révisé. "
                                "Le texte doit viser des banquiers UEMOA de niveau professionnel et traiter les principales catégories "
                                "d'opérations bancaires, financières et hors bilan, ainsi que les implications comptables de leur traitement."
                            ),
                        },
                        {
                            "titre": "Articulation avec les autres référentiels",
                            "contenu": (
                                "Analyse l'articulation entre le PCB révisé, les exigences prudentielles et les autres référentiels "
                                "applicables. Adresse-toi à un public de banquiers UEMOA de niveau professionnel et explique les cas "
                                "de complémentarité, de priorité normative et les conséquences pratiques pour la production des comptes."
                            ),
                        },
                    ],
                },
            ],
            "questions_qcm": [
                {"numero": 1, "question": "Quel est l'objectif principal de la révision du PCB de l'UMOA ?", "options": {"A": "Réduire le nombre d'agences bancaires", "B": "Améliorer l'image fidèle et la comparabilité des états financiers", "C": "Supprimer la comptabilité bancaire", "D": "Remplacer toutes les normes prudentielles"}, "reponse_correcte": "B"},
                {"numero": 2, "question": "Le PCB de 1996 a été conçu principalement pour :", "options": {"A": "Les assurances", "B": "Les entreprises industrielles", "C": "Les banques de l'UMOA", "D": "Les microfinances uniquement"}, "reponse_correcte": "C"},
                {"numero": 3, "question": "Parmi les limites du PCB 1996, on retrouve :", "options": {"A": "Une trop grande convergence avec IFRS", "B": "Une absence totale de comptes bancaires", "C": "Des insuffisances face aux instruments financiers complexes", "D": "Une application exclusive aux groupes cotés"}, "reponse_correcte": "C"},
                {"numero": 4, "question": "Les normes IFRS mettent l'accent sur :", "options": {"A": "Le coût historique uniquement", "B": "La substance économique et l'image fidèle", "C": "La suppression des états financiers", "D": "Le secret bancaire absolu"}, "reponse_correcte": "B"},
                {"numero": 5, "question": "La comparabilité des états financiers permet surtout de :", "options": {"A": "Faciliter la comparaison entre établissements", "B": "Empêcher la supervision bancaire", "C": "Remplacer les audits", "D": "Diminuer les dépôts"}, "reponse_correcte": "A"},
                {"numero": 6, "question": "L'image fidèle signifie que les comptes doivent :", "options": {"A": "Être jolis visuellement", "B": "Refléter la réalité économique de la banque", "C": "Contenir le moins d'informations possible", "D": "Être identiques à ceux des concurrents"}, "reponse_correcte": "B"},
                {"numero": 7, "question": "Le champ d'application du PCB révisé concerne principalement :", "options": {"A": "Les établissements bancaires soumis au référentiel UMOA", "B": "Les commerçants de détail", "C": "Les administrations publiques", "D": "Les associations culturelles"}, "reponse_correcte": "A"},
                {"numero": 8, "question": "L'influence des normes IFRS dans la révision du PCB vise notamment à :", "options": {"A": "Rendre la comptabilité moins lisible", "B": "Moderniser les principes de présentation et d'évaluation", "C": "Supprimer la notion de risque", "D": "Interdire les états financiers"}, "reponse_correcte": "B"},
                {"numero": 9, "question": "Pour les superviseurs, une meilleure comparabilité sert à :", "options": {"A": "Simplifier les contrôles et analyses prudentielles", "B": "Remplacer les contrôles sur place", "C": "Éliminer les ratios prudentiels", "D": "Réduire la transparence"}, "reponse_correcte": "A"},
                {"numero": 10, "question": "Pourquoi une révision du PCB était-elle nécessaire ?", "options": {"A": "Parce que la comptabilité bancaire ne servait plus à rien", "B": "Parce que les activités bancaires et les exigences d'information ont évolué", "C": "Parce que les banques ne produisent plus d'états financiers", "D": "Parce que les IFRS interdisent tout référentiel local"}, "reponse_correcte": "B"},
            ],
        },

        # ══════════════════════════════════════════════════════════════════════
        # MODULE 2 — Le cadre conceptuel
        # ══════════════════════════════════════════════════════════════════════
        {
            "titre": "Module 2 — Le cadre conceptuel",
            "chapitres": [
                {
                    "titre": "Hypothèses de base",
                    "introduction": (
                        "Ce chapitre présente les deux hypothèses fondamentales qui sous-tendent "
                        "l'élaboration des états financiers bancaires."
                    ),
                    "parties": [
                        {
                            "titre": "Continuité d'exploitation",
                            "contenu": (
                                "Rédige un contenu pédagogique destiné à des banquiers UEMOA, niveau professionnel, sur l'hypothèse "
                                "de continuité d'exploitation. Explique son sens, son utilité dans la préparation des états financiers "
                                "bancaires et ses conséquences sur l'évaluation des actifs, des passifs et de la performance. "
                                "Le ton doit être pédagogique, précis et orienté métier."
                            ),
                        },
                        {
                            "titre": "Comptabilité d'engagement",
                            "contenu": (
                                "Explique, pour un public de banquiers UEMOA de niveau professionnel, l'hypothèse de la comptabilité "
                                "d'engagement. Présente la différence avec la comptabilité de trésorerie, les implications sur la "
                                "reconnaissance des produits et des charges, ainsi que son importance dans l'analyse de la performance "
                                "bancaire. Ton pédagogique et précis."
                            ),
                        },
                    ],
                },
                {
                    "titre": "Principes comptables fondamentaux",
                    "introduction": (
                        "Ce chapitre expose les grands principes comptables qui encadrent la production "
                        "de l'information financière bancaire."
                    ),
                    "parties": [
                        {
                            "titre": "Prudence et neutralité",
                            "contenu": (
                                "Développe les principes de prudence et de neutralité à destination de banquiers UEMOA, niveau "
                                "professionnel. Explique comment ces principes encadrent la reconnaissance des risques, des pertes "
                                "potentielles et la présentation d'une information financière fiable. Le contenu doit être clair, "
                                "pédagogique et concret."
                            ),
                        },
                        {
                            "titre": "Permanence des méthodes",
                            "contenu": (
                                "Rédige un contenu pédagogique sur le principe de permanence des méthodes pour des banquiers UEMOA. "
                                "Explique pourquoi la stabilité des méthodes comptables est importante pour la comparabilité des comptes, "
                                "et dans quels cas un changement de méthode peut être justifié et encadré."
                            ),
                        },
                        {
                            "titre": "Non-compensation et image fidèle",
                            "contenu": (
                                "Explique, pour un public professionnel bancaire UEMOA, le principe de non-compensation et son lien "
                                "avec l'image fidèle. Montre pourquoi il faut présenter séparément les actifs, passifs, produits et "
                                "charges, et quelles conséquences cela a sur la lisibilité des états financiers et l'analyse du risque."
                            ),
                        },
                    ],
                },
                {
                    "titre": "Caractéristiques qualitatives de l'information",
                    "introduction": (
                        "Ce chapitre décrit les qualités essentielles que doit posséder l'information financière "
                        "pour être utile à ses destinataires."
                    ),
                    "parties": [
                        {
                            "titre": "Pertinence et fiabilité",
                            "contenu": (
                                "Rédige un contenu pédagogique à destination de banquiers UEMOA, niveau professionnel, sur les "
                                "caractéristiques qualitatives pertinentes et fiables de l'information financière. Définis ces notions, "
                                "explique leur utilité pour la décision bancaire et illustre leur rôle dans la qualité des états financiers."
                            ),
                        },
                        {
                            "titre": "Comparabilité et intelligibilité",
                            "contenu": (
                                "Explique, pour des banquiers UEMOA, comment la comparabilité et l'intelligibilité améliorent "
                                "l'exploitation des états financiers. Le contenu doit être précis, pédagogique et orienté métier, "
                                "en montrant l'intérêt pour le pilotage interne, la supervision et l'analyse externe."
                            ),
                        },
                        {
                            "titre": "Opportunité et exhaustivité",
                            "contenu": (
                                "Développe les notions d'opportunité et d'exhaustivité dans le cadre de l'information comptable bancaire. "
                                "Adresse-toi à un public professionnel UEMOA et montre pourquoi la bonne information doit être disponible "
                                "à temps, complète et suffisante pour éclairer la décision."
                            ),
                        },
                    ],
                },
                {
                    "titre": "Éléments des états financiers",
                    "introduction": (
                        "Ce chapitre définit les composantes fondamentales des états financiers bancaires : "
                        "actifs, passifs, produits, charges, capitaux propres et résultat."
                    ),
                    "parties": [
                        {
                            "titre": "Actifs et passifs",
                            "contenu": (
                                "Rédige un contenu pédagogique pour banquiers UEMOA sur la définition des actifs et des passifs dans "
                                "les états financiers bancaires. Explique les critères de reconnaissance, les exemples concrets en banque "
                                "et l'intérêt de ces notions pour l'analyse financière."
                            ),
                        },
                        {
                            "titre": "Produits et charges",
                            "contenu": (
                                "Explique, pour un public de banquiers UEMOA de niveau professionnel, la notion de produits et de charges. "
                                "Présente leur rôle dans la mesure de la performance, les règles de rattachement comptable et les principaux "
                                "cas rencontrés dans l'activité bancaire."
                            ),
                        },
                        {
                            "titre": "Capitaux propres et résultat",
                            "contenu": (
                                "Développe les notions de capitaux propres et de résultat dans le contexte bancaire UEMOA. Le ton doit être "
                                "pédagogique et précis. Explique leur signification, leur place dans l'équilibre financier de la banque et "
                                "leur utilité pour l'analyse de la solvabilité et de la performance."
                            ),
                        },
                    ],
                },
            ],
            "questions_qcm": [
                {"numero": 1, "question": "L'hypothèse de continuité d'exploitation signifie que :", "options": {"A": "La banque cesse bientôt ses activités", "B": "La banque est supposée poursuivre ses activités dans un avenir prévisible", "C": "Les comptes sont établis uniquement en trésorerie", "D": "Les actifs sont toujours vendus immédiatement"}, "reponse_correcte": "B"},
                {"numero": 2, "question": "La comptabilité d'engagement consiste à reconnaître :", "options": {"A": "Uniquement les flux de trésorerie", "B": "Les produits et charges au moment où ils sont générés", "C": "Seulement les opérations de caisse", "D": "Les dettes uniquement à l'échéance"}, "reponse_correcte": "B"},
                {"numero": 3, "question": "Le principe de prudence conduit à :", "options": {"A": "Anticiper les pertes probables sans anticiper les gains incertains", "B": "Toujours surestimer le résultat", "C": "Ignorer les risques", "D": "Compenser les charges et les produits"}, "reponse_correcte": "A"},
                {"numero": 4, "question": "Le principe de permanence des méthodes sert surtout à :", "options": {"A": "Rendre les comptes incomparables", "B": "Assurer la comparabilité des états financiers dans le temps", "C": "Empêcher toute évolution comptable", "D": "Supprimer les notes annexes"}, "reponse_correcte": "B"},
                {"numero": 5, "question": "Le principe de non-compensation impose de :", "options": {"A": "Fusionner actifs et passifs", "B": "Présenter séparément les éléments financiers", "C": "Supprimer les charges", "D": "Masquer les produits exceptionnels"}, "reponse_correcte": "B"},
                {"numero": 6, "question": "Une information financière pertinente est une information qui :", "options": {"A": "Est décorative", "B": "Aide à la prise de décision", "C": "Est toujours longue", "D": "Ne contient que des chiffres historiques"}, "reponse_correcte": "B"},
                {"numero": 7, "question": "Une information fiable doit être :", "options": {"A": "Subjective", "B": "Neutre, vérifiable et fidèle à la réalité", "C": "Floue pour protéger la banque", "D": "Identique à toutes les autres banques"}, "reponse_correcte": "B"},
                {"numero": 8, "question": "L'intelligibilité de l'information financière signifie qu'elle doit être :", "options": {"A": "Difficile à comprendre", "B": "Compréhensible par les utilisateurs", "C": "Réservée aux auditeurs seulement", "D": "Écrite uniquement en langage juridique"}, "reponse_correcte": "B"},
                {"numero": 9, "question": "Les capitaux propres représentent :", "options": {"A": "Les dettes de la banque", "B": "L'intérêt des actionnaires dans l'entreprise", "C": "Les dépôts des clients uniquement", "D": "Les charges d'exploitation"}, "reponse_correcte": "B"},
                {"numero": 10, "question": "Le résultat d'une banque mesure principalement :", "options": {"A": "Sa taille physique", "B": "Sa performance sur une période", "C": "Son nombre d'agences", "D": "Son niveau de trésorerie instantané"}, "reponse_correcte": "B"},
            ],
        },

        # ══════════════════════════════════════════════════════════════════════
        # MODULE 3 — Structure du référentiel
        # ══════════════════════════════════════════════════════════════════════
        {
            "titre": "Module 3 — Structure du référentiel",
            "chapitres": [
                {
                    "titre": "Les trois volumes du PCB",
                    "introduction": (
                        "Ce chapitre présente l'architecture du PCB révisé en trois volumes complémentaires "
                        "et explique le rôle de chacun dans la production de l'information comptable."
                    ),
                    "parties": [
                        {
                            "titre": "Présentation générale de l'architecture du référentiel",
                            "contenu": (
                                "Rédige un contenu pédagogique destiné à des banquiers UEMOA, niveau professionnel, sur l'architecture "
                                "générale du PCB révisé. Explique la logique des trois volumes, leur complémentarité et leur rôle respectif "
                                "dans la production de l'information comptable bancaire. Ton pédagogique, précis et orienté métier."
                            ),
                        },
                        {
                            "titre": "Volume 1 — Dispositions générales et cadre de référence",
                            "contenu": (
                                "Explique, pour un public de banquiers UEMOA de niveau professionnel, le contenu et l'utilité du Volume 1 "
                                "du PCB. Présente les règles de base, les principes structurants et les repères conceptuels qui encadrent "
                                "l'ensemble du référentiel. Le texte doit être clair, structuré et concret."
                            ),
                        },
                        {
                            "titre": "Volume 2 — Plan des comptes et fonctionnement comptable",
                            "contenu": (
                                "Développe le rôle du Volume 2 du PCB à destination de banquiers UEMOA, niveau professionnel. Décris le "
                                "plan des comptes, la logique de classement des opérations, et l'importance de ce volume pour la tenue "
                                "comptable quotidienne, la fiabilité des écritures et la production des états financiers."
                            ),
                        },
                        {
                            "titre": "Volume 3 — États financiers et informations à produire",
                            "contenu": (
                                "Rédige un contenu pédagogique sur le Volume 3 du PCB pour un public de banquiers UEMOA. Explique les "
                                "états financiers attendus, leur structure, leur finalité et leur utilité pour l'analyse financière, "
                                "la supervision et la communication réglementaire. Ton professionnel, précis et pédagogique."
                            ),
                        },
                    ],
                },
                {
                    "titre": "Le guide d'application BCEAO",
                    "introduction": (
                        "Ce chapitre présente le guide d'application BCEAO, son rôle d'interprétation "
                        "du PCB et son utilité pour la conformité des établissements."
                    ),
                    "parties": [
                        {
                            "titre": "Rôle et fonction du guide d'application",
                            "contenu": (
                                "Rédige un contenu pédagogique destiné à des banquiers UEMOA, niveau professionnel, sur le rôle du guide "
                                "d'application BCEAO. Explique pourquoi ce guide est indispensable pour interpréter correctement le PCB "
                                "révisé, sécuriser les pratiques comptables et harmoniser les traitements au sein des établissements."
                            ),
                        },
                        {
                            "titre": "Lecture pratique des règles comptables",
                            "contenu": (
                                "Explique, pour un public de banquiers UEMOA de niveau professionnel, comment le guide d'application BCEAO "
                                "aide à traduire les principes du référentiel en traitements concrets. Montre son utilité dans la résolution "
                                "des cas pratiques, la cohérence des écritures et la réduction des divergences d'interprétation. "
                                "Le ton doit être pédagogique et précis."
                            ),
                        },
                        {
                            "titre": "Apport pour la conformité et le contrôle",
                            "contenu": (
                                "Développe l'intérêt du guide d'application BCEAO pour la conformité comptable et le contrôle interne. "
                                "Adresse-toi à des banquiers UEMOA de niveau professionnel et montre comment ce document renforce la "
                                "qualité des comptes, facilite les contrôles et limite les erreurs de traitement."
                            ),
                        },
                    ],
                },
                {
                    "titre": "Instructions n°022 à n°035",
                    "introduction": (
                        "Ce chapitre présente les instructions réglementaires n°022 à n°035, leur portée "
                        "et leur impact opérationnel sur les établissements bancaires de l'UEMOA."
                    ),
                    "parties": [
                        {
                            "titre": "Présentation des instructions et de leur portée",
                            "contenu": (
                                "Rédige un contenu pédagogique à destination de banquiers UEMOA, niveau professionnel, sur les instructions "
                                "numérotées de n°022 à n°035. Explique leur rôle dans le dispositif réglementaire, leur articulation avec "
                                "le PCB et leur importance pour la mise en œuvre opérationnelle du référentiel. Ton clair, structuré et précis."
                            ),
                        },
                        {
                            "titre": "Typologie des règles couvertes par les instructions",
                            "contenu": (
                                "Explique, pour un public de banquiers UEMOA de niveau professionnel, les grandes catégories de sujets "
                                "traitées par les instructions n°022 à n°035. Présente leur fonction dans l'organisation comptable, la "
                                "production des états financiers et l'encadrement des pratiques bancaires. Le contenu doit rester "
                                "pédagogique et concret."
                            ),
                        },
                        {
                            "titre": "Impact opérationnel sur les établissements bancaires",
                            "contenu": (
                                "Développe l'impact opérationnel des instructions n°022 à n°035 pour les banques UEMOA. Le texte doit "
                                "s'adresser à des professionnels et montrer comment ces instructions influencent les procédures internes, "
                                "la saisie comptable, le reporting réglementaire et le contrôle de conformité."
                            ),
                        },
                        {
                            "titre": "Bonnes pratiques de mise en œuvre",
                            "contenu": (
                                "Rédige un contenu pédagogique sur les bonnes pratiques de mise en œuvre des instructions n°022 à n°035 "
                                "dans une banque UEMOA. Explique les points d'attention, les risques de mauvaise interprétation et les "
                                "réflexes à adopter pour assurer une application homogène, fiable et conforme du référentiel."
                            ),
                        },
                    ],
                },
            ],
            "questions_qcm": [
                {"numero": 1, "question": "Le PCB révisé est généralement structuré en :", "options": {"A": "Un seul document sans annexes", "B": "Trois volumes complémentaires", "C": "Cinq chapitres indépendants", "D": "Deux livres uniquement"}, "reponse_correcte": "B"},
                {"numero": 2, "question": "Le Volume 1 du PCB contient principalement :", "options": {"A": "Les états financiers publiés", "B": "Les dispositions générales et le cadre de référence", "C": "Les opérations de trésorerie", "D": "Les ratios prudentiels uniquement"}, "reponse_correcte": "B"},
                {"numero": 3, "question": "Le Volume 2 est surtout consacré :", "options": {"A": "Au plan des comptes et au fonctionnement comptable", "B": "À la communication commerciale de la banque", "C": "Aux statistiques macroéconomiques", "D": "Aux règles fiscales des entreprises"}, "reponse_correcte": "A"},
                {"numero": 4, "question": "Le Volume 3 porte principalement sur :", "options": {"A": "Les stratégies marketing", "B": "Les états financiers et les informations à produire", "C": "Les sanctions disciplinaires", "D": "Les contrats de travail"}, "reponse_correcte": "B"},
                {"numero": 5, "question": "Le guide d'application BCEAO sert surtout à :", "options": {"A": "Remplacer le PCB", "B": "Donner des interprétations et précisions pratiques", "C": "Supprimer les contrôles internes", "D": "Fixer les taux d'intérêt"}, "reponse_correcte": "B"},
                {"numero": 6, "question": "L'un des rôles du guide d'application est de :", "options": {"A": "Créer de nouvelles banques", "B": "Harmoniser les traitements comptables", "C": "Interdire toute adaptation", "D": "Remplacer les auditeurs"}, "reponse_correcte": "B"},
                {"numero": 7, "question": "Les instructions n°022 à n°035 ont pour fonction de :", "options": {"A": "Régler les modalités opérationnelles du référentiel", "B": "Définir les couleurs des formulaires", "C": "Fixer les politiques monétaires", "D": "Organiser les assemblées générales"}, "reponse_correcte": "A"},
                {"numero": 8, "question": "Une bonne mise en œuvre des instructions suppose :", "options": {"A": "Une interprétation variable selon chaque service", "B": "Des procédures internes claires et homogènes", "C": "L'absence de contrôle", "D": "Une comptabilité uniquement manuelle"}, "reponse_correcte": "B"},
                {"numero": 9, "question": "Le rôle du PCB dans une banque est de :", "options": {"A": "Structurer la comptabilité bancaire", "B": "Gérer les campagnes publicitaires", "C": "Fixer les salaires", "D": "Remplacer le système d'information"}, "reponse_correcte": "A"},
                {"numero": 10, "question": "L'articulation entre PCB, guide d'application et instructions vise à :", "options": {"A": "Multiplier les contradictions", "B": "Assurer cohérence, conformité et lisibilité", "C": "Supprimer la réglementation", "D": "Rendre les comptes secrets"}, "reponse_correcte": "B"},
            ],
        },
    ],
}


# ── Injection ─────────────────────────────────────────────────────────────────

async def build_module(module_data: dict, ordre: int) -> dict:
    chapitres_data = []
    for ch_idx, ch in enumerate(module_data.get("chapitres", [])):
        parties_data = []
        for p_idx, p in enumerate(ch.get("parties", [])):
            parties_data.append({
                "_id": ObjectId(),
                "titre": p["titre"],
                "contenu": p["contenu"],
                "ordre": p_idx + 1,
                "contenu_genere": None,
            })
        chapitres_data.append({
            "_id": ObjectId(),
            "titre": ch["titre"],
            "introduction": ch.get("introduction", ""),
            "nombre_parties": len(parties_data),
            "ordre": ch_idx + 1,
            "parties": parties_data,
            "contenu_genere": None,
        })
    return {
        "_id": ObjectId(),
        "titre": module_data["titre"],
        "nombre_chapitres": len(chapitres_data),
        "ordre": ordre,
        "chapitres": chapitres_data,
        "questions_qcm": module_data.get("questions_qcm", []),
    }


async def get_or_create_catalogue(db) -> tuple:
    """Retourne (org_oid, org_doc) du catalogue global, le crée si besoin."""
    org = await db["organizations"].find_one({"code": "CATALOGUE"})
    if not org:
        result = await db["organizations"].insert_one({
            "name": "Catalogue Global",
            "code": "CATALOGUE",
            "country": "UEMOA",
            "status": "active",
            "is_catalogue": True,
            "created_at": datetime.utcnow(),
        })
        org = await db["organizations"].find_one({"_id": result.inserted_id})
        print(f"✅  Org CATALOGUE créée : {org['_id']}")
    else:
        print(f"✅  Org CATALOGUE existante : {org['_id']}")
    return org["_id"], org


async def inject(org_code: str = None, org_id: str = None):
    client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    db = client[DB_NAME]

    # ── Trouver ou créer l'organisation ───────────────────────────────────────
    if org_id:
        org = await db["organizations"].find_one({"_id": ObjectId(org_id)})
        if not org:
            print("❌  Organisation introuvable.")
            client.close()
            return
        org_oid = org["_id"]
    elif org_code:
        org = await db["organizations"].find_one({"code": org_code})
        if not org:
            print(f"❌  Organisation avec code '{org_code}' introuvable.")
            client.close()
            return
        org_oid = org["_id"]
    else:
        # Par défaut → catalogue global
        org_oid, org = await get_or_create_catalogue(db)

    print(f"   Cible : {org.get('name')} ({org.get('code')}) — {org_oid}")

    # ── Vérifier doublon ───────────────────────────────────────────────────────
    existing = await db["formations"].find_one({
        "titre": FORMATION["titre"],
        "organization_id": org_oid,
    })
    if existing:
        print(f"⚠️   Formation déjà présente (id: {existing['_id']}). Injection annulée.")
        client.close()
        return

    # ── Construire le document ─────────────────────────────────────────────────
    modules_data = []
    for idx, mod in enumerate(FORMATION["modules"]):
        modules_data.append(await build_module(mod, idx + 1))

    doc = {
        "titre": FORMATION["titre"],
        "description": FORMATION["description"],
        "organization_id": org_oid,
        "status": FORMATION["status"],
        "bloc_numero": FORMATION.get("bloc_numero"),
        "bloc_titre": FORMATION.get("bloc_titre"),
        "modules": modules_data,
        "created_at": datetime.utcnow(),
    }

    result = await db["formations"].insert_one(doc)
    print(f"\n✅  Formation injectée avec succès !")
    print(f"   ID        : {result.inserted_id}")
    print(f"   Titre     : {FORMATION['titre']}")
    print(f"   Modules   : {len(modules_data)}")
    total_ch = sum(len(m["chapitres"]) for m in modules_data)
    total_pa = sum(len(ch["parties"]) for m in modules_data for ch in m["chapitres"])
    total_qcm = sum(len(m["questions_qcm"]) for m in modules_data)
    print(f"   Chapitres : {total_ch}")
    print(f"   Parties   : {total_pa}")
    print(f"   Questions QCM : {total_qcm}")

    client.close()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Injection formation PCB 1")
    parser.add_argument("--org-code", default=None, help="Code de l'organisation (ex: MIZNAS_TEST)")
    parser.add_argument("--org-id",   default=None, help="ObjectId de l'organisation")
    args = parser.parse_args()

    asyncio.run(inject(org_code=args.org_code, org_id=args.org_id))
