"""
Exemple de création d'un poste réglementaire via Python
"""
import requests
import json

# Configuration
API_URL = "http://localhost:8000"
TOKEN = "votre_token_ici"  # Remplacer par votre token d'authentification

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# ========== EXEMPLE 1 : Poste feuille simple avec un GL code ==========
def exemple_1_poste_simple():
    """Créer un poste avec un seul GL code"""
    data = {
        "code": "ACTIF_001",
        "libelle": "Trésorerie et équivalents de trésorerie",
        "type": "bilan_actif",
        "niveau": 2,
        "ordre": 10,
        "gl_codes": [
            {
                "code": "101011",
                "signe": "+",
                "basis": "NET"
            }
        ],
        "formule": "somme",
        "is_active": True
    }
    
    response = requests.post(
        f"{API_URL}/api/pcb/postes",
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        print("✅ Poste créé avec succès !")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ Erreur: {response.status_code}")
        print(response.text)


# ========== EXEMPLE 2 : Poste avec pattern wildcard ==========
def exemple_2_poste_avec_pattern():
    """Créer un poste avec un pattern wildcard"""
    data = {
        "code": "ACTIF_002",
        "libelle": "Créances clients",
        "type": "bilan_actif",
        "niveau": 2,
        "ordre": 20,
        "gl_codes": [
            {
                "code": "411*",  # Tous les codes commençant par 411
                "signe": "+",
                "basis": "DEBIT"
            }
        ],
        "formule": "somme",
        "is_active": True
    }
    
    response = requests.post(
        f"{API_URL}/api/pcb/postes",
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        print("✅ Poste créé avec succès !")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ Erreur: {response.status_code}")
        print(response.text)


# ========== EXEMPLE 3 : Poste avec plusieurs GL codes ==========
def exemple_3_poste_multiple_gl():
    """Créer un poste avec plusieurs GL codes"""
    data = {
        "code": "ACTIF_003",
        "libelle": "Immobilisations",
        "type": "bilan_actif",
        "niveau": 2,
        "ordre": 30,
        "gl_codes": [
            {
                "code": "211*",
                "signe": "+",
                "basis": "NET"
            },
            {
                "code": "213*",
                "signe": "+",
                "basis": "NET"
            },
            {
                "code": "2181-2189",  # Plage de codes
                "signe": "+",
                "basis": "DEBIT"
            }
        ],
        "formule": "somme",
        "is_active": True
    }
    
    response = requests.post(
        f"{API_URL}/api/pcb/postes",
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        print("✅ Poste créé avec succès !")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ Erreur: {response.status_code}")
        print(response.text)


# ========== EXEMPLE 4 : Poste parent (sans GL codes) ==========
def exemple_4_poste_parent():
    """Créer un poste parent qui sera calculé comme somme de ses enfants"""
    data = {
        "code": "ACTIF_000",
        "libelle": "ACTIF TOTAL",
        "type": "bilan_actif",
        "niveau": 1,
        "ordre": 1,
        "gl_codes": [],  # Vide - sera calculé comme somme des enfants
        "formule": "somme",
        "is_active": True
    }
    
    response = requests.post(
        f"{API_URL}/api/pcb/postes",
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        print("✅ Poste parent créé avec succès !")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ Erreur: {response.status_code}")
        print(response.text)


# ========== EXEMPLE 5 : Poste avec classe de comptes ==========
def exemple_5_poste_avec_classe():
    """Créer un poste qui utilise toute une classe de comptes"""
    data = {
        "code": "PASSIF_001",
        "libelle": "Capitaux propres",
        "type": "bilan_passif",
        "niveau": 2,
        "ordre": 10,
        "gl_codes": [
            {
                "code": "Classe 1",  # Tous les comptes de la classe 1
                "signe": "+",
                "basis": "CREDIT"
            }
        ],
        "formule": "somme",
        "is_active": True
    }
    
    response = requests.post(
        f"{API_URL}/api/pcb/postes",
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        print("✅ Poste créé avec succès !")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ Erreur: {response.status_code}")
        print(response.text)


# ========== EXEMPLE 6 : Poste compte de résultat (Produit) ==========
def exemple_6_poste_produit():
    """Créer un poste de produit du compte de résultat"""
    data = {
        "code": "CR_PROD_001",
        "libelle": "Produits d'exploitation",
        "type": "cr_produit",
        "niveau": 1,
        "ordre": 10,
        "gl_codes": [
            {
                "code": "701*",
                "signe": "+",
                "basis": "CREDIT"
            },
            {
                "code": "702*",
                "signe": "+",
                "basis": "CREDIT"
            }
        ],
        "formule": "somme",
        "is_active": True
    }
    
    response = requests.post(
        f"{API_URL}/api/pcb/postes",
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        print("✅ Poste produit créé avec succès !")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ Erreur: {response.status_code}")
        print(response.text)


# ========== EXEMPLE 7 : Poste hiérarchique (avec parent) ==========
def exemple_7_poste_avec_parent():
    """Créer un poste enfant avec un parent"""
    # D'abord, récupérer l'ID du parent (supposons qu'il existe)
    # Vous devez remplacer PARENT_ID par l'ID réel du poste parent
    PARENT_ID = "507f1f77bcf86cd799439011"  # À remplacer
    
    data = {
        "code": "ACTIF_001_001",
        "libelle": "Caisse",
        "type": "bilan_actif",
        "niveau": 3,
        "parent_id": PARENT_ID,
        "parent_code": "ACTIF_001",
        "ordre": 1,
        "gl_codes": [
            {
                "code": "101011",
                "signe": "+",
                "basis": "DEBIT"
            }
        ],
        "formule": "somme",
        "is_active": True
    }
    
    response = requests.post(
        f"{API_URL}/api/pcb/postes",
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        print("✅ Poste enfant créé avec succès !")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ Erreur: {response.status_code}")
        print(response.text)


# ========== EXEMPLE 8 : Poste avec liste CSV de codes GL ==========
def exemple_8_poste_liste_csv():
    """Créer un poste avec une liste CSV de codes GL"""
    data = {
        "code": "ACTIF_004",
        "libelle": "Divers actifs",
        "type": "bilan_actif",
        "niveau": 2,
        "ordre": 40,
        "gl_codes": [
            {
                "code": "471,472,473",  # Liste CSV de codes
                "signe": "+",
                "basis": "NET"
            }
        ],
        "formule": "somme",
        "is_active": True
    }
    
    response = requests.post(
        f"{API_URL}/api/pcb/postes",
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        print("✅ Poste créé avec succès !")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ Erreur: {response.status_code}")
        print(response.text)


# ========== EXEMPLE 9 : Récupérer tous les postes ==========
def exemple_9_liste_postes():
    """Récupérer la liste de tous les postes"""
    response = requests.get(
        f"{API_URL}/api/pcb/postes",
        headers=headers
    )
    
    if response.status_code == 200:
        postes = response.json()
        print(f"✅ {len(postes)} poste(s) trouvé(s)")
        for poste in postes:
            print(f"  - {poste['code']}: {poste['libelle']} ({poste['type']})")
    else:
        print(f"❌ Erreur: {response.status_code}")
        print(response.text)


# ========== EXEMPLE 10 : Calculer le solde d'un poste ==========
def exemple_10_calculer_solde(poste_id: str, date_solde: str = None):
    """Calculer le solde d'un poste pour une date donnée"""
    url = f"{API_URL}/api/pcb/postes/{poste_id}/calculer"
    if date_solde:
        url += f"?date_solde={date_solde}"
    
    response = requests.post(
        url,
        headers=headers
    )
    
    if response.status_code == 200:
        result = response.json()
        print("✅ Calcul réussi !")
        print(f"  Solde brut: {result.get('solde_brut', 0)}")
        print(f"  Solde affiché: {result.get('solde_affiche', 0)}")
        print(f"  Warning signe: {result.get('warning_signe', False)}")
        if result.get('gl_details'):
            print(f"  Détails GL: {len(result['gl_details'])} GL(s) trouvé(s)")
    else:
        print(f"❌ Erreur: {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    print("=" * 60)
    print("EXEMPLES DE CRÉATION DE POSTES RÉGLEMENTAIRES")
    print("=" * 60)
    print()
    
    # Décommenter l'exemple que vous voulez tester
    # exemple_1_poste_simple()
    # exemple_2_poste_avec_pattern()
    # exemple_3_poste_multiple_gl()
    # exemple_4_poste_parent()
    # exemple_5_poste_avec_classe()
    # exemple_6_poste_produit()
    # exemple_7_poste_avec_parent()
    # exemple_8_poste_liste_csv()
    # exemple_9_liste_postes()
    # exemple_10_calculer_solde("POSTE_ID_ICI", "2024-01-15")
    
    print("\n⚠️  N'oubliez pas de remplacer TOKEN par votre token d'authentification !")

