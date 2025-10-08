import streamlit as st
import json
import os
import pandas as pd
import math
from datetime import datetime

# ===================== Couleurs et styles =====================
GUERBET_BLUE = "#124F7A"
GUERBET_DARK = "#0D334F"
CARD_BG = "#EAF1F8"

st.markdown(f"""
<style>
.stApp {{ background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }}
h1, h2, h3 {{ font-weight: 600; letter-spacing: -0.5px; }}
div.stButton > button {{
    background-color: {GUERBET_BLUE};
    color: white;
    border: none;
    border-radius: 10px;
    padding: 0.6em 1.2em;
    font-size: 1rem;
    transition: 0.2s ease-in-out;
}}
div.stButton > button:hover {{
    background-color: {GUERBET_DARK};
    transform: scale(1.03);
}}
.result-card {{
    background-color: {CARD_BG};
    border-radius: 16px;
    box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    padding: 25px;
    text-align: center;
    transition: 0.2s ease-in-out;
}}
.result-card:hover {{ transform: scale(1.02); }}
.footer {{ margin-top: 2em; font-size: 0.8rem; text-align: center; color: #666; }}
.beta-footer {{
    background-color: #FCE8B2;
    border: 1px solid #F5B800;
    padding: 8px 15px;
    border-radius: 10px;
    color: #5A4500;
    text-align: center;
    font-weight: 600;
    margin-top: 10px;
    display: inline-block;
}}
.header-title {{
    color:white; 
    background-color:{GUERBET_BLUE}; 
    padding:25px; 
    border-radius:12px; 
    width:100%; 
    text-align:center; 
    font-size:2.2rem;
}}
</style>
""", unsafe_allow_html=True)

# ===================== Configuration =====================
CONFIG_FILE = "iodine_config.json"
default_config = {
    "charges": {str(kv): val for kv, val in zip([80,90,100,110,120],[0.35,0.38,0.40,0.42,0.45])},
    "concentration_mg_ml": 350,
    "portal_time": 30.0,
    "arterial_time": 25.0,
    "intermediate_enabled": False,
    "intermediate_time": 28.0,
    "acquisition_start_param": 70.0,
    "auto_acquisition_by_age": True,
    "calc_mode": "Charge iodée sauf IMC > 30 → Surface corporelle",
    "max_debit": 6.0
}
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = default_config.copy()

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ===================== Fonctions =====================
def calculate_bsa(weight, height):
    return math.sqrt((height * weight) / 3600)

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
    return min(volume, 200), bsa

def calculate_acquisition_start(age, config):
    if not config.get("auto_acquisition_by_age", True):
        return float(config["acquisition_start_param"])
    if age < 70:
        return float(config["acquisition_start_param"])
    elif 70 <= age <= 90:
        return float(70 + (age - 70))
    else:
        return 90.0

def adjust_injection_rate(volume, injection_time, max_debit):
    injection_rate = volume / injection_time
    time_adjusted = False
    if injection_rate > max_debit:
        injection_time = volume / max_debit
        injection_rate = max_debit
        time_adjusted = True
    return injection_rate, injection_time, time_adjusted

# ===================== Page =====================
st.set_page_config(page_title="Calculette Contraste", page_icon="💉", layout="wide")

# === Header ===
col1, col2 = st.columns([1,5])
with col1:
    st.image("guerbet_logo.png", width=200)
with col2:
    st.markdown(f"<div class='header-title'>Calculette de dose de produit de contraste</div>", unsafe_allow_html=True)

# ===================== Page Patient =====================
st.header("🧍 Informations patient")
weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70)
height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170)
current_year = datetime.now().year
birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40)
age = current_year - birth_year
imc = weight / ((height / 100) ** 2)

# Affichage lecture seule
acquisition_start = calculate_acquisition_start(age, config)
st.number_input("Départ d’acquisition (s)", value=float(acquisition_start), disabled=True)
st.number_input("Concentration (mg I/mL)", value=config["concentration_mg_ml"], disabled=True)

# KV selection
kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True)

# Checkbox d'acceptation
accepted = st.checkbox("✅ J’ai lu et j’accepte la mention légale et les conditions d’utilisation.")

if accepted:
    # Temps d'injection
    injection_modes = ["Portal", "Artériel"]
    if config.get("intermediate_enabled", False):
        injection_modes.append("Intermédiaire")
    
    col_mode, col_time = st.columns([2,2])
    with col_mode:
        injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True)
    with col_time:
        if injection_mode == "Portal":
            base_time = float(config["portal_time"])
        elif injection_mode == "Artériel":
            base_time = float(config["arterial_time"])
        else:
            base_time = st.number_input("Temps intermédiaire (s)", value=float(config["intermediate_time"]), min_value=5.0, max_value=120.0, step=1.0)

    # Calcul volume et débit
    volume, bsa = calculate_volume(weight, height, kv_scanner, config["concentration_mg_ml"], imc, config["calc_mode"], config["charges"])
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume, base_time, float(config["max_debit"]))

    # Affichage résultats alignés
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""<div class="result-card"><h3 style="color:{GUERBET_BLUE};">💧 Volume appliqué</h3><h1 style="color:{GUERBET_DARK};">{volume:.1f} mL</h1></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="result-card"><h3 style="color:{GUERBET_BLUE};">🚀 Débit recommandé</h3><h1 style="color:{GUERBET_DARK};">{injection_rate:.1f} mL/s</h1></div>""", unsafe_allow_html=True)

    if time_adjusted:
        st.warning(f"⚠️ Le temps d’injection a été ajusté à {injection_time:.1f}s pour respecter le débit maximal de {config['max_debit']} mL/s.")

    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

# Avertissement légal
st.markdown("""<div style='background-color:#FCE8E6; color:#6B1A00; padding:10px; border-radius:8px; margin-top:15px; font-size:0.9rem;'>⚠️ <b>Avertissement :</b> Ce logiciel est un outil d’aide à la décision. Les résultats sont <b>indicatifs</b> et doivent être validés par un professionnel de santé.</div>""", unsafe_allow_html=True)

# Pied de page
st.markdown(f"""<div class="footer"><p>© 2025 Guerbet | Développé par <b>Sébastien Partouche</b></p><div class="beta-footer">🧪 Version BETA TEST – Usage interne / évaluation</div></div>""", unsafe_allow_html=True)
