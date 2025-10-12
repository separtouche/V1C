# -*- coding: utf-8 -*-
# ============================================================
# 🩺 Calculette de dose de produit de contraste en oncologie
# Auteur : Sébastien Partouche (adapté)
# Version : BETA - Usage interne / évaluation
# ============================================================

import streamlit as st
import json
import os
import pandas as pd
import math
import base64
from datetime import datetime

# ===================== Styles =====================
GUERBET_BLUE = "#124F7A"
CARD_BG = "#EAF1F8"
CARD_HEIGHT = "150px"

st.set_page_config(page_title="Calculette Contraste Oncologie", page_icon="💉", layout="wide")

st.markdown(f"""
<style>
.stApp {{ background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }}
h1, h2, h3 {{ font-weight: 600; letter-spacing: -0.5px; }}
.header-banner {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: {GUERBET_BLUE};
  padding: 0.2rem 1rem;
  border-radius: 10px;
  margin-bottom: 1rem;
  height: 120px;
}}
.header-logo {{ height: 100%; width: auto; object-fit: contain; }}
.header-title {{
  color: white;
  font-size: 2rem;
  text-align: center;
  flex: 1;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
}}
.result-card {{
    background-color: {CARD_BG};
    border-radius: 12px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.07);
    padding: 12px;
    text-align: center;
    transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
    min-height: {CARD_HEIGHT};
    display: flex;
    flex-direction: column;
    justify-content: center;
}}
.result-card:hover {{
    transform: scale(1.02);
    box-shadow: 0 6px 14px rgba(0,0,0,0.12);
}}
.result-card h3 {{ margin-bottom:4px; font-size:0.95rem; }}
.result-card h1 {{ margin:0; font-size:1.5rem; }}
.result-card div.sub-item {{ margin-top:4px; font-size:0.9rem; }}
.result-card div.sub-item-large {{ margin-top:6px; font-size:1.1rem; font-weight:600; }}
.param-section {{
    background: #ffffff;
    border-radius: 10px;
    padding: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    margin-bottom: 12px;
}}
</style>
""", unsafe_allow_html=True)

# ===================== Fichiers =====================
CONFIG_FILE = "iodine_config.json"
LIB_FILE = "libraries.json"

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
if "programs" not in libraries:
    libraries["programs"] = {}

# ===================== Fonctions =====================
def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_libraries(data):
    with open(LIB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def delete_program(name):
    if name in libraries.get("programs", {}):
        del libraries["programs"][name]
        save_libraries(libraries)
        st.success(f"Programme '{name}' supprimé !")

def calculate_bsa(weight, height):
    return math.sqrt((height * weight) / 3600)

def round_to_third(x):
    return round(x * 3) / 3

def calculate_volume(weight, height, kv, concentration, imc, calc_mode, charges):
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
    if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
        bsa = calculate_bsa(weight, height)
        factor = kv_factors.get(kv, 15)
        volume = bsa * factor / (concentration / 1000)
    else:
        charge_iodine = float(charges.get(str(kv), 0.4))
        volume = weight * charge_iodine / (concentration / 1000)
        bsa = None
    volume = min(volume, 200.0)
    volume = round_to_third(volume)
    return volume, bsa

def calculate_acquisition_start(age, cfg):
    if not cfg.get("auto_acquisition_by_age", True):
        return float(cfg.get("acquisition_start_param", 70.0))
    if age < 70:
        return float(cfg.get("acquisition_start_param", 70.0))
    elif 70 <= age <= 90:
        return float(age)
    else:
        return 90.0

def adjust_injection_rate(volume, injection_time, max_debit):
    injection_rate = volume / injection_time if injection_time > 0 else 0.0
    time_adjusted = False
    if injection_rate > max_debit:
        injection_time = volume / max_debit
        injection_rate = max_debit
        time_adjusted = True
    return float(injection_rate), float(injection_time), bool(time_adjusted)

def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ===================== Session =====================
for key in ["accepted_legal", "selected_program"]:
    if key not in st.session_state:
        st.session_state[key] = config.get(key)

# ===================== Header =====================
logo_path = "guerbet_logo.png"
if os.path.exists(logo_path):
    img_b64 = img_to_base64(logo_path)
    st.markdown(f"""
    <div class="header-banner">
      <img src="data:image/png;base64,{img_b64}" class="header-logo" alt="Guerbet logo" />
      <div class="header-title">Calculette de dose de produit de contraste — Oncologie </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"<div class='header-banner'><div class='header-title'>Calculette de dose de produit de contraste — Oncologie </div></div>", unsafe_allow_html=True)

# ===================== Mentions légales =====================
if not st.session_state["accepted_legal"]:
    if st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox"):
        st.session_state["accepted_legal"] = True
        st.experimental_rerun()
    st.stop()

# ===================== Onglets =====================
tab_patient, tab_params, tab_tutorial = st.tabs(["🧍 Patient", "⚙️ Paramètres", "📘 Tutoriel"])

# ===================== Onglet Paramètres =====================
with tab_params:
    st.header("⚙️ Paramètres et Bibliothèque")
    st.subheader("💉 Injection simultanée")
    config["simultaneous_enabled"] = st.checkbox("Activer l'injection simultanée", value=config.get("simultaneous_enabled", False))
    if config["simultaneous_enabled"]:
        config["target_concentration"] = st.number_input("Concentration cible (mg I/mL)", value=config.get("target_concentration",350), min_value=300, max_value=400, step=10)

    st.subheader("📚 Bibliothèque de programmes")
    program_choice = st.selectbox("Programme", ["Aucun"] + list(libraries.get("programs", {}).keys()))
    if program_choice != "Aucun":
        prog_conf = libraries["programs"].get(program_choice, {})
        for key, val in prog_conf.items():
            config[key] = val
    new_prog_name = st.text_input("Nom du nouveau programme")
    if st.button("💾 Ajouter/Mise à jour programme"):
        if new_prog_name.strip():
            libraries["programs"][new_prog_name.strip()] = {k: config[k] for k in config if k not in ["simultaneous_enabled","target_concentration"]}
            save_libraries(libraries)
            st.success(f"Programme '{new_prog_name}' ajouté/mis à jour !")
    if libraries.get("programs"):
        del_prog = st.selectbox("Supprimer un programme", [""] + list(libraries["programs"].keys()))
        if st.button("🗑 Supprimer programme") and del_prog:
            delete_program(del_prog)

    st.subheader("⚙️ Paramètres globaux")
    config["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)", [300,320,350,370,400], index=[300,320,350,370,400].index(int(config.get("concentration_mg_ml",350))))
    config["calc_mode"] = st.selectbox("Méthode de calcul", ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config.get("calc_mode","Charge iodée")))
    config["max_debit"] = st.number_input("Débit maximal autorisé (mL/s)", value=float(config.get("max_debit",6.0)), min_value=1.0, max_value=20.0, step=0.1)
    config["portal_time"] = st.number_input("Portal (s)", value=float(config.get("portal_time",30.0)), min_value=5.0, max_value=120.0, step=1.0)
    config["arterial_time"] = st.number_input("Artériel (s)", value=float(config.get("arterial_time",25.0)), min_value=5.0, max_value=120.0, step=1.0)
    config["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=bool(config.get("intermediate_enabled",False)))
    if config["intermediate_enabled"]:
        config["intermediate_time"] = st.number_input("Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0, max_value=120.0, step=1.0)
    config["rincage_volume"] = st.number_input("Volume de rinçage (mL)", value=float(config.get("rincage_volume",35.0)), min_value=10.0, max_value=100.0, step=1.0)
    config["rincage_delta_debit"] = st.number_input("Différence débit NaCl vs contraste (mL/s)", value=float(config.get("rincage_delta_debit",0.5)), min_value=0.1, max_value=5.0, step=0.1)

    st.markdown("**Charges en iode par kV (g I/kg)**")
    df_charges = pd.DataFrame({
        "kV":[80,90,100,110,120],
        "Charge (g I/kg)":[float(config["charges"].get(str(kv),0.35)) for kv in [80,90,100,110,120]]
    })
    edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True)
    if st.button("💾 Sauvegarder les paramètres"):
        try:
            config["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _,row in edited_df.iterrows()}
            save_config(config)
            st.success("✅ Paramètres sauvegardés !")
        except Exception as e:
            st.error(f"Erreur lors de la sauvegarde : {e}")

# ===================== Onglet Patient =====================
with tab_patient:
    st.header("🧍 Informations patient (adulte en oncologie)")

    # Sélection programme
    selected_prog = st.selectbox("Choisir un programme enregistré", ["Aucun"] + list(libraries.get("programs", {}).keys()))
    if selected_prog != "Aucun":
        prog_conf = libraries["programs"].get(selected_prog, {})
        for key, val in prog_conf.items():
            config[key] = val

    col_w, col_h, col_birth = st.columns([1,1,1])
    with col_w: weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70)
    with col_h: height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170)
    with col_birth:
        current_year = datetime.now().year
        birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40)

    age = current_year - birth_year
    imc = weight / ((height/100)**2)

    col_kv, col_mode_time = st.columns([1.2,2])
    with col_kv:
        kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True)
    with col_mode_time:
        col_mode, col_times = st.columns([1.2,1])
        with col_mode:
            injection_modes = ["Portal","Artériel"]
            if config.get("intermediate_enabled",False):
                injection_modes.append("Intermédiaire")
            injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True)
        with col_times:
            if injection_mode == "Portal":
                base_time = float(config.get("portal_time",30.0))
            elif injection_mode == "Artériel":
                base_time = float(config.get("arterial_time",25.0))
            else:
                base_time = st.number_input("Temps Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0, max_value=120.0, step=1.0)
            st.markdown(f"**Temps {injection_mode} :** {base_time:.0f} s")
            acquisition_start = calculate_acquisition_start(age, config)
            st.markdown(f"**Départ d'acquisition :** {acquisition_start:.1f} s")
            st.markdown(f"**Concentration :** {int(config.get('concentration_mg_ml',350))} mg I/mL")

    volume, bsa = calculate_volume(weight, height, kv_scanner, float(config.get("concentration_mg_ml",350)), imc, config.get("calc_mode","Charge iodée"), config.get("charges",{}))
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume, float(base_time), float(config.get("max_debit",6.0)))

    if config.get("simultaneous_enabled", False):
        target = config.get("target_concentration", 350)
        vol_contrast = round_to_third(volume * target / config.get("concentration_mg_ml",350))
        vol_nacl_dilution = round_to_third(volume - vol_contrast)
        perc_contrast = vol_contrast / volume * 100
        perc_nacl_dilution = vol_nacl_dilution / volume * 100
        contrast_text = f"{vol_contrast:.1f} mL ({perc_contrast:.0f}%)"
        nacl_rincage_volume = config.get("rincage_volume",35.0)
        nacl_rincage_debit = max(0.1, injection_rate - config.get("rincage_delta_debit",0.5))
        nacl_text = f"<div class='sub-item-large'>Dilution : {vol_nacl_dilution:.1f} mL ({perc_nacl_dilution:.0f}%)</div>"
        nacl_text += f"<div class='sub-item-large'>Rinçage : {nacl_rincage_volume:.1f} mL @ {nacl_rincage_debit:.1f} mL/s</div>"
    else:
        vol_contrast = volume
        contrast_text = f"{vol_contrast:.1f} mL"
        nacl_text = f"{config.get('rincage_volume',35.0):.0f} mL"

    col_contrast, col_nacl, col_rate = st.columns(3, gap="medium")
    with col_contrast:
        st.markdown(f"""<div class="result-card"><h3>💧 Volume contraste conseillé</h3><h1>{contrast_text}</h1></div>""", unsafe_allow_html=True)
    with col_nacl:
        st.markdown(f"""<div class="result-card"><h3>💧 Volume NaCl conseillé</h3><h1>{nacl_text}</h1></div>""", unsafe_allow_html=True)
    with col_rate:
        st.markdown(f"""<div class="result-card"><h3>🚀 Débit conseillé</h3><h1>{injection_rate:.1f} mL/s</h1><div class="sub-item">Durée : {injection_time:.1f} s</div></div>""", unsafe_allow_html=True)


# ===================== Onglet Tutoriel (mixte) =====================
with tab_tutorial:
    st.title("📘 Tutoriel — Mode d'emploi et principes cliniques")
    st.markdown("Bienvenue dans le tutoriel. Cette section explique **comment utiliser** la calculette (pas-à-pas) et **pourquoi** chaque calcul est effectué (explication technique et clinique).")

    # Section 1 : Guide pas à pas (utilisation)
    st.header("🔧 Guide pas à pas — Utilisation")
    st.markdown("""
    1. **Patient** : saisissez le poids (kg), la taille (cm) et l'année de naissance. L'IMC et l'âge sont calculés automatiquement.  
    2. **kV du scanner** : choisissez la valeur correspondant à votre machine (80–120 kV).  
    3. **Mode d’injection** : choisissez `Portal`, `Artériel` ou `Intermédiaire`. Seul le temps correspondant est affiché et utilisé pour le calcul.  
    4. **Paramètres** : vérifiez la concentration du produit (mg I/mL), le débit max autorisé et les temps (Paramètres → ⚙️).  
    5. **Injection simultanée** : si activée, définissez la concentration cible — l'outil calcule la dilution contraste/NaCl et les volumes de rinçage.  
    6. **Validation** : relisez les résultats (volume contraste, volume NaCl, débit). Les valeurs sont indicatives : **validez toujours cliniquement** avant administration.
    """)

    # Section 2 : Explications techniques / cliniques
    st.header("🧠 Explications techniques et principes cliniques")
    st.markdown("#### A. Charge iodée vs Surface corporelle")
    st.markdown("""
    - **Charge iodée (g I/kg)** : méthode classique où la dose d'iode est proportionnelle au poids du patient.  
      Exemple : 0.4 g I/kg => volume = poids * 0.4 / (concentration g I/mL).  
      Utile pour standardiser la quantité d'iode administrée.
    - **Surface corporelle (BSA)** : utilisée lorsque l'on veut doser selon la surface corporelle (m²) plutôt que le poids, souvent plus pertinente pour certains protocoles oncologiques.  
      BSA est calculée approximativement par : `racine carée( (taille_cm * poids_kg) / 3600 )`.
    - **Règle IMC** : l'option « Charge iodée sauf IMC > 30 → Surface corporelle » permet d'éviter la surdose chez les patients obèses en utilisant la BSA si IMC ≥ 30.
    """)

    st.markdown("#### B. Débit d'injection et temps")
    st.markdown("""
    - **Débit (mL/s)** = volume total / temps d'injection (s).  
    - **Limite du débit** : si le débit calculé dépasse le débit maximal autorisé (matériel / sécurité), l'outil **augmente le temps** d'injection pour respecter le débit maximal.  
    - **Choix du temps** : la calculette affiche **uniquement** le temps correspondant au mode d'injection sélectionné (Portal / Artériel / Intermédiaire).
    """)

    st.markdown("#### C. Injection simultanée (Dilution avec NaCl)")
    st.markdown("""
    - Lorsque l'injection simultanée est activée, on vise une **concentration cible** (mg I/mL) finale.  
    - Avantages cliniques : permet de réduire la viscosité du bolus, optimiser la concentration d'iode, ou adapter à des seringues/contrainte d'administration.
    - Pensez au **rinçage NaCl** pour pousser le contraste dans la veine et limiter les résidus dans la ligne intraveineuse.
    """)

    st.markdown("#### D. Points de sécurité et bonnes pratiques")
    st.markdown("""
    - **Toujours** vérifier l'identité du patient et les antécédents (insuffisance rénale, allergies, antécédents de réactions au produit de contraste).  
    - Vérifier la **concentration réelle** du flacon de contraste (mg I/mL) et la correspondre dans l'outil.  
    - Ne dépassez pas le **volume de seringue** et la capacité d'administration du matériel.  
    - Cette calculette ne remplace pas le jugement clinique : les résultats sont **indicatifs**.
    """)

    # Section 3 : Bases spécifiques (demandées)
    st.header("🔬 Bases — recommandations spécifiques en oncologie hépatique")
    st.markdown("""
    Le protocole (Critères d’Intensité du Rehaussement Tumoral en Imagerie du foie) vise à standardiser le rehaussement hépatique pour une interprétation fiable.

    **Valeurs de référence (indiquées)** :
    - **Foie sain (objectif)** : ≥ **110 UH en périphérie du foie** (unités Hounsfield) au pic de rehaussement.
    - **Foie non sain (stéatosique)** : ≥ **120 UH dans la rate **.
    

    ⚠️ Ces valeurs et seuils sont proposées à titre indicatif — adaptez-les selon les protocoles locaux, dispositifs et recommandations nationales.
    """)

    # Section 4 : Exemples et workflows (cas pratique)
    st.header("🩺 Exemple de workflow clinique (cas pratique)")
    st.markdown("""
    **Exemple** : patient 75 kg, 170 cm, kV=120, charge en iode 0.5,mode Portal, concentration 350 mg I/mL.
    1. Saisir poids/taille/année de naissance.  
    2. Choisir kV = 120 et mode Portal (temps 30 s par défaut).  
    3. Vérifier volume contraste et débit proposé.  
    4. Si l'objectif est 110 UH, vérifier que le protocole (charge iodée / débit) est compatible pour atteindre cette plage ; sinon ajuster via charges/kV/débit selon protocole local.  
    5. Documenter la valeur UH obtenue après examen pour audit qualité.
    6. Ex : (75x0,4)/0,35=86 ml
    """)
    

# ===================== Footer =====================
# Footer global avec copyright et info version
st.markdown(f"""<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Calculette de dose de produit de contraste en oncologie — usage adulte.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
</div>""", unsafe_allow_html=True)

