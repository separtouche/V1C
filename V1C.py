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

st.set_page_config(page_title="Calculette Contraste", page_icon="💉", layout="wide")
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
  padding: 10px; text-align: center;
  min-height: 120px; display: flex; flex-direction: column; justify-content: center;
}}
.result-card h3 {{ margin-bottom:4px; font-size:0.9rem; }}
.result-card h1 {{ margin:0; font-size:1.4rem; }}
</style>
""", unsafe_allow_html=True)

# ===================== Config =====================
CONFIG_FILE = "iodine_config.json"
default_config = {
    "charges": {str(kv): val for kv, val in zip([80,90,100,110,120],[0.35,0.38,0.40,0.42,0.45])},
    "concentration_mg_ml": 350,
    "concentration_cible_mg_ml": 300,
    "use_simultaneous_injection": False,
    "portal_time": 30.0,
    "arterial_time": 25.0,
    "intermediate_enabled": False,
    "intermediate_time": 28.0,
    "acquisition_start_param": 70.0,
    "auto_acquisition_by_age": True,
    "max_debit": 6.0,
    "rinçage_volume": 35.0,
    "rinçage_delta_debit": 0.5
}
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except:
        config = default_config.copy()
else:
    config = default_config.copy()

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ===================== Fonctions =====================
def calculate_bsa(weight, height): return math.sqrt((height * weight) / 3600)
def calculate_volume(weight, height, kv, concentration, imc, calc_mode, charges):
    kv_factors = {80:11,90:13,100:15,110:16.5,120:18.6}
    if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
        bsa = calculate_bsa(weight, height)
        factor = kv_factors.get(kv,15)
        volume = bsa * factor / (concentration / 1000)
    else:
        charge_iodine = float(charges.get(str(kv),0.4))
        volume = weight * charge_iodine / (concentration / 1000)
        bsa = None
    return min(volume, 200.0), bsa
def calculate_acquisition_start(age, cfg):
    if not cfg.get("auto_acquisition_by_age", True): return float(cfg.get("acquisition_start_param",70.0))
    if age < 70: return float(cfg.get("acquisition_start_param",70.0))
    elif 70 <= age <= 90: return float(age)
    else: return 90.0
def adjust_injection_rate(volume, injection_time, max_debit):
    rate = volume / injection_time if injection_time > 0 else 0.0
    adjusted = False
    if rate > max_debit:
        injection_time = volume / max_debit
        rate = max_debit
        adjusted = True
    return float(rate), float(injection_time), bool(adjusted)

# ===================== Session =====================
if "accepted_legal" not in st.session_state: st.session_state["accepted_legal"] = False

# ===================== Header =====================
def img_to_base64(path):
    with open(path, "rb") as f: return base64.b64encode(f.read()).decode()
logo_path = "guerbet_logo.png"
if os.path.exists(logo_path):
    try:
        img_b64 = img_to_base64(logo_path)
        st.markdown(f"<div class='header-banner'><img src='data:image/png;base64,{img_b64}' class='header-logo'/><div class='header-title'>Calculette de dose de produit de contraste</div></div>", unsafe_allow_html=True)
    except: st.markdown(f"<div class='header-banner'><div class='header-title'>Calculette de dose de produit de contraste</div></div>", unsafe_allow_html=True)
else:
    st.markdown(f"<div class='header-banner'><div class='header-title'>Calculette de dose de produit de contraste</div></div>", unsafe_allow_html=True)

# ===================== Mentions légales =====================
if not st.session_state["accepted_legal"]:
    st.markdown("### Mentions légales — acceptation requise")
    st.markdown(
        "Avant d'utiliser cet outil, vous devez accepter la mention légale et les conditions d'utilisation. "
        "Les données et résultats proposés par cette calculette sont à titre indicatif et doivent être validés par un professionnel de santé."
    )
    accept = st.checkbox("✅ J’accepte les mentions légales.")
    if st.button("Accepter et continuer"):
        if accept: st.session_state["accepted_legal"] = True
        else: st.warning("Vous devez cocher la case pour accepter.")
    st.stop()

# ===================== Onglets =====================
tab_patient, tab_params = st.tabs(["🧍 Patient","⚙️ Paramètres"])

# ===================== Paramètres =====================
with tab_params:
    st.header("⚙️ Paramètres globaux")
    with st.expander("💊 Configuration du calcul", expanded=True):
        config["concentration_mg_ml"] = st.selectbox("Concentration réelle (mg I/mL)", [300,320,350,370,400], index=[300,320,350,370,400].index(int(config.get("concentration_mg_ml",350))))
        config["use_simultaneous_injection"] = st.checkbox("💧 Injection simultanée contraste + NaCl", value=bool(config.get("use_simultaneous_injection",False)))
        if config["use_simultaneous_injection"]:
            config["concentration_cible_mg_ml"] = st.selectbox("🎯 Concentration cible (mg I/mL)", [280,300,320,350], index=[280,300,320,350].index(int(config.get("concentration_cible_mg_ml",300))))
        config["calc_mode"] = st.selectbox("Méthode de calcul", ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"], index=0)
        config["max_debit"] = st.number_input("Débit maximal autorisé (mL/s)", value=float(config.get("max_debit",6.0)), min_value=1.0, max_value=20.0, step=0.1)
    with st.expander("⏱ Temps d'injection"):
        config["portal_time"] = st.number_input("Portal (s)", value=float(config.get("portal_time",30.0)))
        config["arterial_time"] = st.number_input("Artériel (s)", value=float(config.get("arterial_time",25.0)))
        config["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=bool(config.get("intermediate_enabled",False)))
        if config["intermediate_enabled"]:
            config["intermediate_time"] = st.number_input("Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)))
    with st.expander("🚰 Rinçage au NaCl"):
        config["rinçage_volume"] = st.number_input("Volume de rinçage (mL)", value=float(config.get("rinçage_volume",35.0)))
        config["rinçage_delta_debit"] = st.number_input("Différence de débit (mL/s)", value=float(config.get("rinçage_delta_debit",0.5)))
    if st.button("💾 Sauvegarder les paramètres"): save_config(config); st.success("✅ Paramètres sauvegardés !")

# ===================== Patient =====================
with tab_patient:
    st.header("🧍 Informations patient")
    col1, col2, col3 = st.columns(3)
    with col1: weight = st.slider("Poids (kg)",20,200,70)
    with col2: height = st.slider("Taille (cm)",100,220,170)
    with col3:
        current_year = datetime.now().year
        birth_year = st.slider("Année de naissance", current_year-120, current_year, current_year-40)
    age = current_year - birth_year
    imc = weight / ((height/100)**2)

    kv_scanner = st.radio("kV du scanner",[80,90,100,110,120], index=4, horizontal=True)
    injection_modes = ["Portal","Artériel"]
    if config.get("intermediate_enabled",False): injection_modes.append("Intermédiaire")
    injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True)
    base_time = config["portal_time"] if injection_mode=="Portal" else config["arterial_time"]
    if injection_mode=="Intermédiaire": base_time = config["intermediate_time"]

    acquisition_start = calculate_acquisition_start(age, config)
    volume, bsa = calculate_volume(weight,height,kv_scanner,float(config["concentration_mg_ml"]),imc,config["calc_mode"],config["charges"])
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume,float(base_time),float(config["max_debit"]))

    # ==== Injection simultanée ====
    if config.get("use_simultaneous_injection", False):
        ratio = config["concentration_cible_mg_ml"] / config["concentration_mg_ml"]
        contrast_rate = injection_rate * ratio
        nacl_rate = injection_rate - contrast_rate
        st.markdown(f"💧 **Injection simultanée activée :** pour une concentration cible de **{config['concentration_cible_mg_ml']} mgI/mL**, injecter **{contrast_rate:.2f} mL/s** de contraste et **{nacl_rate:.2f} mL/s** de NaCl (total {injection_rate:.2f} mL/s).")

    # ==== Cartes ====
    col_contrast, col_nacl, col_rate = st.columns(3)
    with col_contrast:
        st.markdown(f"<div class='result-card'><h3>💧 Quantité de contraste conseillée</h3><h1>{volume:.1f} mL</h1></div>", unsafe_allow_html=True)
    nacl_debit = max(0.1, injection_rate - config["rinçage_delta_debit"])
    with col_nacl:
        st.markdown(f"<div class='result-card'><h3>💧 Volume NaCl conseillé</h3><h1>{config['rinçage_volume']:.0f} mL @ {nacl_debit:.1f} mL/s</h1></div>", unsafe_allow_html=True)
    with col_rate:
        st.markdown(f"<div class='result-card'><h3>🚀 Débit conseillé</h3><h1>{injection_rate:.1f} mL/s</h1></div>", unsafe_allow_html=True)

    st.info(f"⚠️ Sans rinçage, il aurait fallu injecter {volume + 15:.0f} mL de contraste total.")
    if time_adjusted: st.warning(f"⚠️ Temps ajusté à {injection_time:.1f}s (débit max {config['max_debit']} mL/s).")
    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

    st.markdown("""<div style='background-color:#FCE8E6; color:#6B1A00; padding:10px; border-radius:8px; margin-top:15px; font-size:0.9rem;'>
    ⚠️ <b>Avertissement :</b> Ce logiciel est un outil d’aide à la décision. Les résultats sont indicatifs et doivent être validés par un professionnel de santé.</div>""", unsafe_allow_html=True)

# ===================== Footer =====================
st.markdown(f"""<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Ce logiciel fournit des <b>propositions de valeurs</b> et ne remplace pas le jugement médical.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
</div>""", unsafe_allow_html=True)
