"""
Service de traitement des impayés
"""
from typing import List, Tuple, Optional
from datetime import datetime
import uuid
from app.schemas.impayes import (
    LigneImpayeImport,
    ErreurImport,
    ArrearsSnapshot,
    OutboundMessage,
    StatutMessageEnum,
)
from app.models.impayes_config import get_impayes_config
from app.models.impayes import (
    save_arrears_snapshot,
    save_outbound_message,
)


async def valider_fichier_import(lignes: List[LigneImpayeImport]) -> List[ErreurImport]:
    """
    Valide le fichier Excel importé
    """
    errors = []
    ref_credits_vus = {}  # Utiliser un dict pour stocker la première occurrence
    
    for index, ligne in enumerate(lignes, start=2):  # Ligne 1 = en-têtes
        # Nettoyer et normaliser la référence de crédit
        ref_credit = str(ligne.refCredit).strip() if ligne.refCredit else ""
        
        # Vérifier refCredit unique
        if ref_credit in ref_credits_vus:
            # Afficher la référence complète et la ligne où elle a été vue pour la première fois
            premiere_ligne = ref_credits_vus[ref_credit]
            # Vérifier si la référence semble tronquée (trop courte ou identique pour plusieurs lignes)
            message = f"Référence crédit dupliquée (vue d'abord ligne {premiere_ligne}): '{ref_credit}'"
            if len(ref_credit) <= 15:
                message += f" (ATTENTION: La référence semble tronquée à {len(ref_credit)} caractères. Assurez-vous que la colonne 'refCredit' est formatée comme TEXTE dans Excel, pas comme NOMBRE)"
            errors.append(ErreurImport(
                ligne=index,
                champ="refCredit",
                message=message
            ))
            # Debug: afficher les valeurs pour comprendre le problème
            print(f"[DEBUG] Référence dupliquée détectée - Ligne {index}: '{ref_credit}' (longueur: {len(ref_credit)})")
            print(f"[DEBUG] Première occurrence ligne {premiere_ligne}: '{ref_credit}' (longueur: {len(ref_credit)})")
        else:
            ref_credits_vus[ref_credit] = index
            # Debug pour les premières références
            if index <= 5:
                print(f"[DEBUG] Ligne {index}: refCredit='{ref_credit}' (longueur: {len(ref_credit)}, type: {type(ligne.refCredit).__name__})")
        
        # Vérifier téléphone si nécessaire (on vérifiera plus tard si SMS requis)
        # Pour l'instant, on accepte les téléphones vides
        
        # Vérifier formats numériques
        if ligne.montantInitial < 0:
            errors.append(ErreurImport(
                ligne=index,
                champ="montantInitial",
                message="Le montant initial doit être positif"
            ))
        
        if ligne.encoursPrincipal < 0:
            errors.append(ErreurImport(
                ligne=index,
                champ="encoursPrincipal",
                message="L'encours principal doit être positif"
            ))
        
        if ligne.joursRetard < 0:
            errors.append(ErreurImport(
                ligne=index,
                champ="joursRetard",
                message="Les jours de retard doivent être positifs"
            ))
    
    return errors


async def calculer_indicateurs(
    ligne: LigneImpayeImport,
    organization_id: str
) -> Tuple[dict, str]:
    """
    Calcule les indicateurs pour une ligne d'impayé
    Retourne: (donnees_calculees, bucket_retard)
    """
    # Récupérer la configuration
    config = await get_impayes_config(organization_id)
    if not config:
        raise ValueError("Configuration des impayés non trouvée")
    
    # Calculer montant total impayé
    montant_total_impaye = (
        ligne.principalImpaye +
        ligne.interetsImpayes +
        ligne.penalitesImpayees
    )
    
    # Déterminer la tranche (bucket)
    bucket_retard = "Non défini"
    tranches = config.get("tranches_retard", [])
    for tranche in tranches:
        min_jours = tranche.get("min_jours", 0) if isinstance(tranche, dict) else getattr(tranche, "min_jours", 0)
        max_jours = tranche.get("max_jours") if isinstance(tranche, dict) else getattr(tranche, "max_jours", None)
        libelle = tranche.get("libelle", "Non défini") if isinstance(tranche, dict) else getattr(tranche, "libelle", "Non défini")
        
        if ligne.joursRetard >= min_jours:
            if max_jours is None or ligne.joursRetard <= max_jours:
                bucket_retard = libelle
                break
    
    # Calculer ratio impayé / encours
    ratio_impaye_encours = 0.0
    if ligne.encoursPrincipal > 0:
        ratio_impaye_encours = (montant_total_impaye / ligne.encoursPrincipal) * 100
        # Limiter le ratio à un maximum raisonnable (ex: 1000%) pour éviter les valeurs aberrantes
        # Si l'encours est très petit, le ratio peut être très élevé
        if ratio_impaye_encours > 1000:
            print(f"[WARNING] Ratio impayé/encours très élevé ({ratio_impaye_encours:.2f}%) pour crédit {ligne.refCredit} - encours: {ligne.encoursPrincipal}, impayé: {montant_total_impaye}")
            # Garder le ratio mais le limiter pour éviter les valeurs aberrantes dans les statistiques
            ratio_impaye_encours = min(ratio_impaye_encours, 1000.0)
    
    # Déterminer statut réglementaire (utilise le statut de la tranche)
    statut_reglementaire = bucket_retard
    
    # Vérifier candidat à restructuration
    regle = config.get("regle_restructuration", {})
    if isinstance(regle, dict):
        jours_min = regle.get("jours_retard_min", 60)
        pourcentage_min = regle.get("pourcentage_impaye_min", 30.0)
    else:
        jours_min = getattr(regle, "jours_retard_min", 60)
        pourcentage_min = getattr(regle, "pourcentage_impaye_min", 30.0)
    
    # Debug: afficher les valeurs pour comprendre
    print(f"[DEBUG] Restructuration - Crédit: {ligne.refCredit}, Jours retard: {ligne.joursRetard} (min: {jours_min}), Ratio: {ratio_impaye_encours:.2f}% (min: {pourcentage_min}%)")
    
    candidat_restructuration = (
        ligne.joursRetard >= jours_min and
        ratio_impaye_encours > pourcentage_min
    )
    
    if candidat_restructuration:
        print(f"[DEBUG] ✅ Candidat à restructuration détecté pour {ligne.refCredit}")
    
    return {
        "montant_total_impaye": montant_total_impaye,
        "bucket_retard": bucket_retard,
        "ratio_impaye_encours": ratio_impaye_encours,
        "statut_reglementaire": statut_reglementaire,
        "candidat_restructuration": candidat_restructuration
    }, bucket_retard


async def _generer_sms_fallback(
    snapshot: ArrearsSnapshot,
    bucket_retard: str
) -> Optional[OutboundMessage]:
    """
    Génère un SMS de fallback pour la prévisualisation quand il n'y a pas de configuration
    """
    if not snapshot.telephone_client:
        return None
    
    def _fmt_sms(n: float) -> str:
        """Formate un montant pour SMS avec espace normal comme séparateur de milliers"""
        return '{:,.0f}'.format(n).replace(',', ' ')

    montant_fmt = _fmt_sms(snapshot.montant_total_impaye)

    # Messages par défaut selon la tranche de retard
    messages_fallback = {
        "0-30 jours": f"Cher client {snapshot.nom_client}, votre credit {snapshot.ref_credit} presente un retard de {snapshot.jours_retard} jours pour un montant de {montant_fmt} FCFA. Merci de regulariser votre situation au plus vite.",
        "31-60 jours": f"Cher client {snapshot.nom_client}, votre credit {snapshot.ref_credit} presente un retard important de {snapshot.jours_retard} jours. Montant du: {montant_fmt} FCFA. Veuillez contacter votre agence {snapshot.agence} rapidement.",
        "61-90 jours": f"URGENT - Cher client {snapshot.nom_client}, votre credit {snapshot.ref_credit} presente un retard critique de {snapshot.jours_retard} jours. Montant du: {montant_fmt} FCFA. Contactez immediatement votre agence {snapshot.agence}.",
        "90+ jours": f"ALERTE FINALE - Cher client {snapshot.nom_client}, votre credit {snapshot.ref_credit} presente un retard de {snapshot.jours_retard} jours. Montant du: {montant_fmt} FCFA. Des procedures de recouvrement pourraient etre engagees. Contactez votre agence {snapshot.agence} SVP.",
    }
    
    # Message par défaut si la tranche n'est pas dans la liste
    texte = messages_fallback.get(bucket_retard, 
        f"Cher client {snapshot.nom_client}, votre credit {snapshot.ref_credit} presente un retard de {snapshot.jours_retard} jours. Montant: {montant_fmt} FCFA. Merci de contacter votre agence.")
    
    # Créer le message
    message = OutboundMessage(
        message_id=str(uuid.uuid4()),
        organization_id=snapshot.organization_id,
        snapshot_id=snapshot.snapshot_id,
        periode_suivi=snapshot.periode_suivi,
        type="SMS",
        to=snapshot.telephone_client,
        body=texte,
        status=StatutMessageEnum.PENDING,
        linked_credit=snapshot.ref_credit,
        tranche_id=bucket_retard or "",
        created_at=datetime.utcnow(),
    )
    
    print(f"[DEBUG] Fallback SMS généré pour {snapshot.ref_credit} -> {snapshot.telephone_client} (tranche: {bucket_retard})")
    return message


async def generer_sms(
    snapshot: ArrearsSnapshot,
    bucket_retard: str,
    organization_id: str,
    fallback_mode: bool = False
) -> Optional[OutboundMessage]:
    """
    Génère un message SMS pour un snapshot si nécessaire
    
    Args:
        snapshot: Le snapshot du crédit
        bucket_retard: La tranche de retard
        organization_id: ID de l'organisation
        fallback_mode: Si True, génère un SMS même sans configuration (pour prévisualisation)
    """
    # Récupérer la configuration
    config = await get_impayes_config(organization_id)
    if not config:
        if fallback_mode:
            print(f"[DEBUG] Fallback SMS généré pour {snapshot.ref_credit}: configuration introuvable")
            return await _generer_sms_fallback(snapshot, bucket_retard)
        else:
            print(f"[DEBUG] SMS non généré pour {snapshot.ref_credit}: configuration introuvable")
            return None
    
    print(f"[DEBUG] generer_sms pour {snapshot.ref_credit}: bucket_retard='{bucket_retard}', telephone='{snapshot.telephone_client}'")
    
    # Trouver le modèle SMS pour cette tranche
    modeles_sms = config.get("modeles_sms", [])
    modele = None
    tranche_id = None
    
    print(f"[DEBUG] Nombre de modèles SMS configurés: {len(modeles_sms)}")
    
    tranches = config.get("tranches_retard", [])
    print(f"[DEBUG] Nombre de tranches configurées: {len(tranches)}")
    print(f"[DEBUG] Tranches disponibles: {[t.get('libelle', '') if isinstance(t, dict) else getattr(t, 'libelle', '') for t in tranches]}")
    
    for idx, tranche in enumerate(tranches):
        libelle = tranche.get("libelle") if isinstance(tranche, dict) else getattr(tranche, "libelle", "")
        if libelle == bucket_retard:
            tranche_id = str(idx)  # Utiliser l'index comme ID
            print(f"[DEBUG] Tranche trouvée: '{bucket_retard}' -> tranche_id={tranche_id}")
            # Chercher le modèle SMS pour cette tranche
            for m in modeles_sms:
                m_tranche_id = m.get("tranche_id") if isinstance(m, dict) else getattr(m, "tranche_id", "")
                m_actif = m.get("actif", True) if isinstance(m, dict) else getattr(m, "actif", True)
                print(f"[DEBUG] Modèle SMS: tranche_id={m_tranche_id}, actif={m_actif}")
                if m_tranche_id == tranche_id and m_actif:
                    modele = m
                    print(f"[DEBUG] Modèle SMS trouvé pour tranche_id={tranche_id}")
                    break
            break
    
    if not bucket_retard or bucket_retard == "Non défini":
        print(f"[DEBUG] SMS non généré pour {snapshot.ref_credit}: bucket_retard invalide ou non défini ('{bucket_retard}')")
        return None
    
    if not snapshot.telephone_client:
        print(f"[DEBUG] SMS non généré pour {snapshot.ref_credit}: pas de téléphone")
        return None
    
    if not modele:
        if fallback_mode:
            print(f"[DEBUG] Fallback SMS généré pour {snapshot.ref_credit}: aucun modèle SMS trouvé")
            return await _generer_sms_fallback(snapshot, bucket_retard)
        else:
            print(f"[DEBUG] SMS non généré pour {snapshot.ref_credit}: aucun modèle SMS actif trouvé pour la tranche '{bucket_retard}'")
            return None
    
    # Remplir les variables du modèle
    texte = modele.get("texte", "") if isinstance(modele, dict) else getattr(modele, "texte", "")
    
    # Variables disponibles
    variables = {
        "NOM_CLIENT": snapshot.nom_client,
        "MONTANT": f"{snapshot.montant_total_impaye:,.0f}",
        "MONTANT_IMPAYE": f"{snapshot.montant_total_impaye:,.0f}",
        "DATE_ECHEANCE": snapshot.date_derniere_echeance_impayee or "N/A",
        "AGENCE": snapshot.agence,
        "CANAL_PAIEMENT": "votre agence",
        "REF_CREDIT": snapshot.ref_credit,
        "JOURS_RETARD": str(snapshot.jours_retard),
        "NUMERO_AGENCE": snapshot.agence,
        "CONSEILLER_TEL": "votre conseiller",
        "ENCOURS": f"{snapshot.encours_principal:,.0f}",
        "NB_ECHEANCES_IMPAYEES": str(snapshot.nb_echeances_impayees),
    }
    
    # Remplacer les variables
    for var, value in variables.items():
        texte = texte.replace(f"{{{var}}}", str(value))
    
    # Créer le message
    message = OutboundMessage(
        message_id=str(uuid.uuid4()),
        organization_id=snapshot.organization_id,
        snapshot_id=snapshot.snapshot_id,
        periode_suivi=snapshot.periode_suivi,  # Ajouter la période de suivi
        type="SMS",
        to=snapshot.telephone_client,
        body=texte,
        status=StatutMessageEnum.PENDING,
        linked_credit=snapshot.ref_credit,
        tranche_id=tranche_id or "",
        created_at=datetime.utcnow(),
    )
    
    print(f"[DEBUG] SMS généré pour {snapshot.ref_credit} -> {snapshot.telephone_client} (tranche: {bucket_retard})")
    return message


async def traiter_import_impayes(
    lignes: List[LigneImpayeImport],
    date_situation: str,
    organization_id: str,
    created_by: str
) -> Tuple[List[ArrearsSnapshot], List[OutboundMessage]]:
    """
    Traite un import d'impayés : calcule les indicateurs et génère les SMS
    
    Cette fonction :
    1. Génère un snapshot_id unique (UUID) qui identifie ce batch/fichier importé
    2. Pour chaque ligne du fichier :
       - Calcule les indicateurs (montant total, tranche de retard, ratio, candidat restructuration)
       - Crée un snapshot avec ce snapshot_id et la date_situation fournie
       - Génère un SMS si nécessaire selon la configuration
    3. Retourne tous les snapshots et messages générés
    
    IMPORTANT : Tous les snapshots d'un même fichier partagent le même snapshot_id.
    Cela permet d'identifier facilement tous les crédits d'un même import.
    
    Args:
        lignes: Liste des lignes d'impayés à traiter
        date_situation: Date de situation économique (format YYYY-MM-DD)
        organization_id: ID de l'organisation
        created_by: ID de l'utilisateur qui effectue l'import
        
    Returns:
        Tuple contenant :
        - Liste des snapshots créés (tous avec le même snapshot_id)
        - Liste des messages SMS générés
    """
    snapshots = []
    messages = []

    # Normaliser date_situation: accepter aussi JJ/MM/AAAA et convertir en YYYY-MM-DD
    if date_situation and "/" in date_situation and "-" not in date_situation:
        from datetime import datetime

        try:
            date_situation = datetime.strptime(date_situation, "%d/%m/%Y").strftime("%Y-%m-%d")
        except Exception:
            pass

    # Générer un snapshot_id unique pour ce batch/fichier
    # Tous les snapshots de ce fichier auront le même snapshot_id
    batch_id = f"batch_{date_situation.replace('-', '_')}_{str(uuid.uuid4())[:8]}"
    
    for ligne in lignes:
        # Calculer les indicateurs
        donnees_calculees, bucket_retard = await calculer_indicateurs(ligne, organization_id)
        
        # Créer le snapshot avec batch_id unique
        snapshot_id = str(uuid.uuid4())
        
        snapshot = ArrearsSnapshot(
            snapshot_id=snapshot_id,
            batch_id=batch_id,  # Ajouter le batch_id
            organization_id=organization_id,
            date_situation=date_situation,
            periode_suivi=date_situation[:7],  # Calcul automatique YYYY-MM
            created_by=created_by,
            created_at=datetime.utcnow(),
            is_active=True,  # Les nouveaux snapshots sont actifs par défaut
            ref_credit=ligne.refCredit,
            id_client=ligne.idClient,
            nom_client=ligne.nomClient,
            telephone_client=ligne.telephoneClient,
            segment=ligne.segment.value,
            agence=ligne.agence,
            gestionnaire=ligne.gestionnaire,
            produit=ligne.produit.value,
            montant_initial=ligne.montantInitial,
            encours_principal=ligne.encoursPrincipal,
            principal_impaye=ligne.principalImpaye,
            interets_impayes=ligne.interetsImpayes,
            penalites_impayees=ligne.penalitesImpayees,
            nb_echeances_impayees=ligne.nbEcheancesImpayees,
            jours_retard=ligne.joursRetard,
            date_derniere_echeance_impayee=ligne.dateDerniereEcheanceImpayee,
            statut_interne=ligne.statutInterne.value,
            garanties=ligne.garanties,
            revenu_mensuel=ligne.revenuMensuel,
            commentaire=ligne.commentaire,
            montant_total_impaye=donnees_calculees["montant_total_impaye"],
            bucket_retard=bucket_retard,
            ratio_impaye_encours=donnees_calculees["ratio_impaye_encours"],
            statut_reglementaire=donnees_calculees["statut_reglementaire"],
            candidat_restructuration=donnees_calculees["candidat_restructuration"],
        )
        
        snapshots.append(snapshot)
        
        # Générer le SMS si nécessaire (avec fallback pour prévisualisation)
        message = await generer_sms(snapshot, bucket_retard, organization_id, fallback_mode=True)
        if message:
            messages.append(message)
        elif len(messages) == 0 and len(snapshots) <= 5:  # Log les 5 premiers pour déboguer
            print(f"[DEBUG] Aucun SMS généré pour le crédit {snapshot.ref_credit} (snapshot #{len(snapshots)})")
    
    print(f"[DEBUG] ========== FIN GÉNÉRATION SMS ==========")
    print(f"[DEBUG] Snapshots créés: {len(snapshots)}, SMS générés: {len(messages)}")
    
    return snapshots, messages


async def regenerer_sms_pour_date_situation(
    organization_id: str,
    date_situation: str
) -> Tuple[int, int]:
    """
    Régénère les SMS pour une date de situation donnée à partir des snapshots existants
    Retourne: (nombre_sms_generes, nombre_snapshots_traites)
    """
    from app.models.impayes import get_snapshots_by_filters, save_outbound_message
    from app.schemas.impayes import FiltresImpayes, ArrearsSnapshot
    
    # Récupérer tous les snapshots pour cette date de situation
    filtres = FiltresImpayes(date_situation=date_situation)
    snapshots = await get_snapshots_by_filters(organization_id, filtres, limit=10000)
    
    if not snapshots:
        return 0, 0
    
    # Vérifier les SMS existants pour éviter les doublons
    from app.models.impayes import get_all_messages
    existing_messages = await get_all_messages(organization_id, limit=10000)
    existing_snapshot_ids = {msg.get("snapshot_id") for msg in existing_messages if msg.get("snapshot_id")}
    
    sms_generes = 0
    snapshots_traites = 0
    
    for snapshot_dict in snapshots:
        try:
            # Convertir le dict en ArrearsSnapshot
            # Gérer la conversion de created_at si c'est une string
            created_at = snapshot_dict.get("created_at")
            if isinstance(created_at, str):
                try:
                    # Essayer de parser avec fromisoformat (Python 3.7+)
                    if "T" in created_at or "+" in created_at or "Z" in created_at:
                        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    else:
                        # Format simple YYYY-MM-DD
                        created_at = datetime.strptime(created_at, "%Y-%m-%d")
                except:
                    created_at = datetime.utcnow()
            elif created_at is None:
                created_at = datetime.utcnow()
            
            # Gérer revenu_mensuel qui peut être une string dans le dict
            revenu_mensuel = snapshot_dict.get("revenu_mensuel")
            if revenu_mensuel:
                try:
                    if isinstance(revenu_mensuel, str):
                        revenu_mensuel = float(revenu_mensuel) if revenu_mensuel.strip() else None
                    else:
                        revenu_mensuel = float(revenu_mensuel)
                except:
                    revenu_mensuel = None
            else:
                revenu_mensuel = None
            
            snapshot = ArrearsSnapshot(
                snapshot_id=snapshot_dict.get("snapshot_id", ""),
                organization_id=str(snapshot_dict.get("organization_id", "")),
                date_situation=snapshot_dict.get("date_situation", ""),
                periode_suivi=snapshot_dict.get("date_situation", "")[:7],  # Calcul automatique YYYY-MM
                created_by=str(snapshot_dict.get("created_by", "")),
                created_at=created_at,
                ref_credit=snapshot_dict.get("ref_credit", ""),
                id_client=snapshot_dict.get("id_client", ""),
                nom_client=snapshot_dict.get("nom_client", ""),
                telephone_client=snapshot_dict.get("telephone_client"),
                segment=snapshot_dict.get("segment", ""),
                agence=snapshot_dict.get("agence", ""),
                produit=snapshot_dict.get("produit", ""),
                montant_initial=float(snapshot_dict.get("montant_initial", 0) or 0),
                encours_principal=float(snapshot_dict.get("encours_principal", 0) or 0),
                principal_impaye=float(snapshot_dict.get("principal_impaye", 0) or 0),
                interets_impayes=float(snapshot_dict.get("interets_impayes", 0) or 0),
                penalites_impayees=float(snapshot_dict.get("penalites_impayees", 0) or 0),
                nb_echeances_impayees=int(snapshot_dict.get("nb_echeances_impayees", 0) or 0),
                jours_retard=int(snapshot_dict.get("jours_retard", 0) or 0),
                date_derniere_echeance_impayee=snapshot_dict.get("date_derniere_echeance_impayee"),
                statut_interne=snapshot_dict.get("statut_interne", ""),
                garanties=snapshot_dict.get("garanties"),
                revenu_mensuel=revenu_mensuel,
                commentaire=snapshot_dict.get("commentaire"),
                montant_total_impaye=float(snapshot_dict.get("montant_total_impaye", 0) or 0),
                bucket_retard=snapshot_dict.get("bucket_retard", ""),
                ratio_impaye_encours=float(snapshot_dict.get("ratio_impaye_encours", 0) or 0),
                statut_reglementaire=snapshot_dict.get("statut_reglementaire", ""),
                candidat_restructuration=bool(snapshot_dict.get("candidat_restructuration", False)),
            )
            
            # Vérifier si un SMS existe déjà pour ce snapshot
            if snapshot.snapshot_id in existing_snapshot_ids:
                continue
            
            # Générer le SMS
            bucket_retard = snapshot.bucket_retard or ""
            message = await generer_sms(snapshot, bucket_retard, organization_id)
            
            if message:
                # Sauvegarder le message
                await save_outbound_message(message)
                sms_generes += 1
            
            snapshots_traites += 1
            
        except Exception as e:
            print(f"Erreur lors de la régénération du SMS pour le snapshot {snapshot_dict.get('ref_credit', 'unknown')}: {str(e)}")
            continue
    
    return sms_generes, snapshots_traites



