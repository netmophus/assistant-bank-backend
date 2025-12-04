"""
Script pour créer une licence active via l'API HTTP.
Usage: python create_license_http.py <organization_id>
"""
import sys
import requests
from datetime import date, timedelta

API_BASE_URL = "http://127.0.0.1:8000"


def create_license(org_id: str):
    """Crée une licence via l'API."""
    today = date.today()
    end_date = today + timedelta(days=365)  # 1 an
    
    license_data = {
        "organization_id": org_id,
        "plan": "Standard",
        "max_users": 50,
        "start_date": str(today),
        "end_date": str(end_date),
        "status": "active",
        "features": ["bank_qa", "letters", "training_modules"]
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/licenses",
            json=license_data
        )
        
        if response.status_code == 200:
            license = response.json()
            print(f"\n✅ Licence créée avec succès!")
            print(f"   ID: {license['id']}")
            print(f"   Organization ID: {license['organization_id']}")
            print(f"   Plan: {license['plan']}")
            print(f"   Date de début: {license['start_date']}")
            print(f"   Date de fin: {license['end_date']}")
            print(f"   Statut: {license['status']}")
            print(f"   Max utilisateurs: {license['max_users']}")
        else:
            print(f"\n❌ Erreur: {response.status_code}")
            print(f"   Détails: {response.text}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Erreur: Impossible de se connecter au serveur.")
        print(f"   Assurez-vous que le serveur backend est démarré sur {API_BASE_URL}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
        sys.exit(1)


def list_organizations():
    """Liste toutes les organisations via l'API."""
    try:
        response = requests.get(f"{API_BASE_URL}/organizations")
        
        if response.status_code == 200:
            orgs = response.json()
            if not orgs:
                print("Aucune organisation trouvée.")
                return
            
            print("\n📋 Organisations disponibles:")
            print("-" * 80)
            for org in orgs:
                print(f"  ID: {org['id']}")
                print(f"  Nom: {org.get('name', 'N/A')}")
                print(f"  Code: {org.get('code', 'N/A')}")
                print("-" * 80)
        else:
            print(f"\n❌ Erreur: {response.status_code}")
            print(f"   Détails: {response.text}")
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Erreur: Impossible de se connecter au serveur.")
        print(f"   Assurez-vous que le serveur backend est démarré sur {API_BASE_URL}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python create_license_http.py <organization_id>")
        print("       python create_license_http.py --list")
        print("\nExemple:")
        print("  python create_license_http.py 693068213995820ec3fad9ce")
        print("  python create_license_http.py --list")
        sys.exit(1)
    
    if sys.argv[1] == "--list":
        list_organizations()
    else:
        org_id = sys.argv[1]
        create_license(org_id)


if __name__ == "__main__":
    main()

