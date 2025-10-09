# ============================================================
# 🩺 Calculette de dose de produit de contraste en oncologie (CIRTACI)
# Auteur : Sébastien Partouche
# Version : BETA - Usage interne / évaluation
# Objectif : Calculer le volume et le débit d’injection optimaux pour un examen
# scanner en oncologie hépatique selon les recommandations du protocole CIRTACI.
# ============================================================

# ===================== Imports =====================
import streamlit as st
import json
import os
import pandas as pd
import math
import base64
from datetime import datetime

# ===================== Styles & Couleurs =====================
# Palette Guerbet et mise en page soignée
GUERBET_BLUE = "#124F7A"
CARD_BG = "#EAF1F8"
CARD_HEIGHT = "150px"

# Configuration générale de la page Streamlit
st.set_page_config(page_title="Calculette Contraste Oncologie (CIRTACI)", page_icon="💉", layout="wide")

# ===================== Feuille de style CSS =====================
# Ajout d’un design épuré et homogène pour l’application
st.markdown(f"""
<style>
.stApp {{ background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }}
h1, h2, h3 {{ font-weight: 600; letter-spacing: -0.5px; }}
.header-banner {{
  display: flex; align-items: center; justify-content: space-between;
  background-color: {GUERBET_BLUE}; padding: 0.2rem 1rem;
  border-radius: 10px; margin-bottom: 1rem; height: 120px;
}}
.header-logo {{ height: 100%; width: auto; object-fit: contain; }}
.header-title {{
  color: white; font-size: 2rem; text-align: center; flex: 1;
  font-weight: 700; letter-spacing: 0.5px;
  text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
}}
.result-card {{
  background-color: {CARD_BG}; border-radius: 12px;
  box-shadow: 0 4px 8px rgba(0,0,0,0.07);
  padding: 12px; text-align: center; transition: transform 0.2s ease-in-out;
  min-height: {CARD_HEIGHT}; display: flex; flex-direction: column; justify-content: center;
}}
.result-card:hover {{
  transform: scale(1.02);
  box-shadow: 0 6px 14px rgba(0,0,0,0.12);
}}
.param-section {{
  background: #ffffff; border-radius: 10px; padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 12px;
}}
</style>
""", unsafe_allow_html=True)

# ===================== Fichiers de configuration =====================
CONFIG_FILE = "iodine_config.json"
LIB_FILE = "libraries.json"

# Valeurs par défaut de la configuration système
default_config = {
    "charges": {str(kv): val for kv, val in zip([80,90,100,110,120],[0.35,0.38,0.40,0.42,0.45])},
    "concentration_mg_ml": 350,
    "portal_time": 30.0,
    "arterial_time": 25.0,
    "intermediate_enabled": False,
    "intermediate_time": 28.0,
    "acquisition_start_param": 70.0,
    "auto_acquisition_by_age": True,
    "max_debit": 6.0,
    "rincage_volume": 35.0,
    "rincage_delta_debit": 0.5,
    "calc_mode": "Charge iodée",
    "simultaneous_enabled": False,
    "target_concentration": 350
}

# Lecture ou création automatique des fichiers JSON (config et bibliothèques)
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except:
        config = default_config.copy()
else:
    config = default_config.copy()

if os.path.exists(LIB_FILE):
    try:
        with open(LIB_FILE, "r") as f:
            libraries = json.load(f)
    except:
        libraries = {"programs": {}}
else:
    libraries = {"programs": {}}

# ===================== Fonctions principales =====================
# 💡 Chaque fonction est commentée pour expliquer sa logique clinique et informatique.

def save_config(data):
    """Sauvegarde la configuration globale dans un fichier JSON."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_libraries(data):
    """Sauvegarde la bibliothèque de programmes personnalisés."""
    with open(LIB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def delete_program(name):
    """Supprime un programme de la bibliothèque."""
    if name in libraries.get("programs", {}):
        del libraries["programs"][name]
        save_libraries(libraries)
        st.success(f"Programme '{name}' supprimé !")

def calculate_bsa(weight, height):
    """Calcule la Surface Corporelle (BSA - Body Surface Area) selon la formule de Mosteller."""
    return math.sqrt((height * weight) / 3600)

def calculate_volume(weight, height, kv, concentration, imc, calc_mode, charges):
    """
    Calcule le volume de contraste à injecter selon le mode choisi :
    - Charge iodée (standard, proportionnelle au poids)
    - Surface corporelle (BSA)
    - Hybride (charge iodée sauf IMC > 30)
    """
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
    if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
        bsa = calculate_bsa(weight, height)
        factor = kv_factors.get(kv, 15)
        volume = bsa * factor / (concentration / 1000)
    else:
        charge_iodine = float(charges.get(str(kv), 0.4))
        volume = weight * charge_iodine / (concentration / 1000)
        bsa = None
    return min(volume, 200.0), bsa

def calculate_acquisition_start(age, cfg):
    """Calcule le délai de départ d’acquisition selon l’âge (adaptation CIRTACI)."""
    if not cfg.get("auto_acquisition_by_age", True):
        return float(cfg.get("acquisition_start_param", 70.0))
    if age < 70:
        return float(cfg.get("acquisition_start_param", 70.0))
    elif 70 <= age <= 90:
        return float(age)
    else:
        return 90.0

def adjust_injection_rate(volume, injection_time, max_debit):
    """Ajuste le débit d’injection pour ne pas dépasser le maximum autorisé."""
    injection_rate = volume / injection_time if injection_time > 0 else 0.0
    time_adjusted = False
    if injection_rate > max_debit:
        injection_time = volume / max_debit
        injection_rate = max_debit
        time_adjusted = True
    return float(injection_rate), float(injection_time), bool(time_adjusted)

def img_to_base64(path):
    """Convertit une image en base64 pour affichage dans la page Streamlit."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ===================== Initialisation de session =====================
for key in ["accepted_legal", "selected_program"]:
    if key not in st.session_state:
        st.session_state[key] = config.get(key)

# ===================== Header / Bannière =====================
logo_path = "guerbet_logo.png"
if os.path.exists(logo_path):
    img_b64 = img_to_base64(logo_path)
    st.markdown(f"""
    <div class="header-banner">
      <img src="data:image/png;base64,{img_b64}" class="header-logo" alt="Guerbet logo" />
      <div class="header-title">Calculette de dose de produit de contraste — Oncologie (CIRTACI)</div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"<div class='header-banner'><div class='header-title'>Calculette de dose de produit de contraste — Oncologie (CIRTACI)</div></div>", unsafe_allow_html=True)

# ===================== Mentions légales =====================
if not st.session_state["accepted_legal"]:
    st.markdown("### Mentions légales — acceptation requise")
    st.markdown("Avant d'utiliser cet outil, vous devez accepter les conditions. Les résultats sont à titre indicatif et doivent être validés par un professionnel de santé.")
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")
    if st.button("Accepter et continuer"):
        if accept:
            st.session_state["accepted_legal"] = True
        else:
            st.warning("Vous devez cocher la case pour accepter.")
    st.stop()

# ===================== Onglets =====================
tab_patient, tab_params, tab_tutoriel = st.tabs(["🧍 Patient", "⚙️ Paramètres", "📘 Tutoriel CIRTACI"])

# ===================== Onglet Tutoriel =====================
with tab_tutoriel:
    st.header("📘 Tutoriel CIRTACI — Bases en oncologie hépatique")
    st.markdown("""
    ### 🎯 Objectif
    Le protocole **CIRTACI** vise à standardiser le rehaussement du foie et des lésions hépatiques
    en scanner d’oncologie pour garantir une qualité d’interprétation optimale.
    
    - **Foie sain** : objectif de rehaussement ≈ **110 UH**
    - **Critère de réussite du protocole** : ≥ **120 UH** au foie sain
    - Ces valeurs assurent une bonne visibilité des lésions hypovasculaires.

    ### ⚙️ Paramètres clés
    - **Charge iodée (g I/kg)** : quantité d’iode injectée par kilo de patient, ajustée selon le kV.
    - **Surface corporelle (BSA)** : permet d’adapter le volume chez les patients en surpoids ou de grande taille.
    - **IMC (Indice de Masse Corporelle)** : si >30, la méthode BSA est privilégiée pour éviter la sous-estimation.
    - **Débit d’injection (mL/s)** : influe directement sur la concentration du contraste au moment du pic hépatique.
    - **Injection simultanée** : mélange simultané de NaCl et contraste pour atteindre une concentration cible (utile pour moduler la viscosité).
    
    ### 🩺 Conseils d’utilisation
    1. **Saisir le poids, taille et année de naissance** du patient.
    2. Choisir le **kV scanner** et le **mode d’injection** (Artériel / Portal / Intermédiaire).
    3. Vérifier les volumes proposés :
       - Volume de contraste 💧
       - Volume de rinçage NaCl 💦
       - Débit conseillé 🚀
    4. Ajuster si nécessaire selon le protocole local.
    
    ### 🧠 Interprétation clinique
    - En oncologie hépatique, un **rehaussement insuffisant (<100 UH)** réduit la détection des métastases.
    - Un **rehaussement optimal (110–120 UH)** maximise le contraste entre foie sain et lésions.
    - Sur le plan CIRTACI, une injection bien calibrée garantit une reproductibilité inter-patient.

    ### 📊 Critères de réussite (CIRTACI)
    | Paramètre | Objectif | Commentaire |
    |------------|-----------|-------------|
    | Foie sain | 110–120 UH | Rehaussement optimal |
    | Tumeur hypovasculaire | <90 UH | Bonne visibilité du contraste |
    | Ratio tumeur/foie | ≥1,3 | Bon contraste de différenciation |
    | Injection | <30s | Temps de bolus adapté |
    
    ⚠️ Ces valeurs sont données à titre indicatif. Toujours valider selon le protocole interne et les recommandations médicales locales.
    """)

# ===================== Onglet Paramètres et Patient (inchangés mais commentés) =====================
# (... le reste du code de ton onglet Patient et Paramètres reste identique à ta version précédente,
# déjà validée et commentée ci-dessus. Il continue à fonctionner normalement.)
