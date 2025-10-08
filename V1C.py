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
    background-color: {CARD_BG};
    border-radius: 12px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.07);
    padding: 12px; text-align: center;
    min-height: 130px; display: flex; flex-direction: column; justify-content: center;
}}
</style>
""", unsafe_allow_html=True)

# ===================== Config =====================
CONFIG_FILE = "iodine_config.json"
default_config = {
    "charges": {str(kv): val for kv, val in zip([80,90,100,110,120],[0.35,0.38,0.40,0.42,0.45])},
    "concentration_mg_ml": 350,
    "portal_time": 30.0, "arterial_time": 25.0,
    "intermediate_enabled": False, "intermediate_time": 28.0,
    "acquisition_start_param": 70.0, "auto_acquisition_by_age": True,
    "max_debit": 6.0, "rinçage_volume": 35.0, "rinçage_delta_debit": 0.5,
    "calc_mode": "Charge iodée",
    "dilution_enabled": False, "target_concentration": 300
}

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r") as f: config = json.load(f)
    except: config = default_config.copy()
else:
    config = default_config.copy()

def save_config(data):
    with open(CONFIG_FILE, "w") as f: json.dump(data, f, indent=4)

# ===================== Fonctions =====================
def calculate_bsa(weight, height): return math.sqrt((height * weight) / 3600)

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
    return min(volume, 200.0), bsa

def calculate_acquisition_start(age, cfg):
    if not cfg.get("auto_acquisition_by_age", True): return float(cfg.get("acquisition_start_param", 70.0))
    if age < 70: return float(cfg.get("acquisition_start_param", 70.0))
    elif 70 <= age <= 90: return float(age)
    else: return 90.0

def adjust_injection_rate(volume, injection_time, max_debit):
    injection_rate = volume / injection_time if injection_time > 0 else 0.0
    time_adjusted = False
    if injection_rate > max_debit:
        injection_time = volume / max_debit
        injection_rate = max_debit
        time_adjusted = True
    return float(injection_rate), float(injection_time), bool(time_adjusted)

# ===================== Mentions légales =====================
if "accepted_legal" not in st.session_state:
    st.session_state["accepted_legal"] = False

logo_path = "guerbet_logo.png"
if os.path.exists(logo_path):
    img_b64 = base64.b64encode(open(logo_path, "rb").read()).decode()
    st.markdown(f"""
    <div class="header-banner">
      <img src="data:image/png;base64,{img_b64}" class="header-logo" alt="Guerbet logo" />
      <div class="header-title">Calculette de dose de produit de contraste</div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("<h2 style='text-align:center;'>Calculette de dose de produit de contraste</h2>", unsafe_allow_html=True)

if not st.session_state["accepted_legal"]:
    st.markdown("### Mentions légales — acceptation requise")
    st.markdown("Avant d'utiliser cet outil, vous devez accepter la mention légale et les conditions d'utilisation. "
                "Les données proposées sont à titre indicatif et doivent être validées par un professionnel de santé.")
    if st.checkbox("✅ J’accepte les mentions légales."):
        st.session_state["accepted_legal"] = True
    else:
        st.stop()

# ===================== Interface =====================
tab_patient, tab_params = st.tabs(["🧍 Patient", "⚙️ Paramètres"])

# -------- Paramètres --------
with tab_params:
    st.header("⚙️ Paramètres globaux")
    with st.expander("💊 Configuration du calcul", expanded=True):
        config["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)", [300,320,350,370,400],
                                                     index=[300,320,350,370,400].index(int(config.get("concentration_mg_ml",350))))
        config["calc_mode"] = st.selectbox("Méthode de calcul",
                                           ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"],
                                           index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config.get("calc_mode","Charge iodée")))
        config["max_debit"] = st.number_input("Débit maximal (mL/s)", value=float(config.get("max_debit",6.0)), step=0.1)
        config["dilution_enabled"] = st.checkbox("Activer la dilution (concentration cible)", value=bool(config.get("dilution_enabled", False)))
        if config["dilution_enabled"]:
            config["target_concentration"] = st.number_input("Concentration cible (mg I/mL)", value=float(config.get("target_concentration",300)),
                                                             min_value=200.0, max_value=400.0, step=10.0)
    with st.expander("🚰 Rinçage au NaCl"):
        config["rinçage_volume"] = st.number_input("Volume de rinçage (mL)", value=float(config.get("rinçage_volume",35.0)))
        config["rinçage_delta_debit"] = st.number_input("Différence de débit NaCl vs contraste (mL/s)", value=float(config.get("rinçage_delta_debit",0.5)))
    if st.button("💾 Sauvegarder les paramètres"): save_config(config); st.success("✅ Paramètres sauvegardés")

# -------- Patient --------
with tab_patient:
    st.header("🧍 Informations patient")
    col1, col2, col3 = st.columns(3)
    with col1: weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70)
    with col2: height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170)
    with col3:
        birth_year = st.number_input("Année de naissance", min_value=1900, max_value=datetime.now().year, value=1985)
    age = datetime.now().year - birth_year
    imc = weight / ((height/100)**2)

    kv = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True)
    mode = st.radio("Mode d’injection", ["Portal","Artériel"], horizontal=True)
    base_time = config["portal_time"] if mode=="Portal" else config["arterial_time"]

    # ----- Calcul du volume -----
    concentration_init = float(config["concentration_mg_ml"])
    concentration_target = float(config["target_concentration"]) if config.get("dilution_enabled", False) else concentration_init

    volume_total, bsa = calculate_volume(weight, height, kv, concentration_target, imc,
                                         config.get("calc_mode","Charge iodée"), config.get("charges",{}))

    # Si dilution active → ajustement des volumes
    if config.get("dilution_enabled", False):
        pct_contrast = (concentration_target / concentration_init)
        pct_nacl = 1 - pct_contrast
        volume_contrast_pur = volume_total * pct_contrast
        volume_nacl_dilution = volume_total * pct_nacl
    else:
        pct_contrast = 1.0
        pct_nacl = 0.0
        volume_contrast_pur = volume_total
        volume_nacl_dilution = 0.0

    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume_total, base_time, config["max_debit"])
    nacl_debit = max(0.1, injection_rate - config.get("rinçage_delta_debit",0.5))

    col_c1, col_c2, col_c3 = st.columns(3)
    col_c1.markdown(f"<div class='result-card'><h3>💧 Volume total injecté</h3><h1>{volume_total:.1f} mL</h1></div>", unsafe_allow_html=True)
    col_c2.markdown(f"<div class='result-card'><h3>💧 Volume NaCl (rinçage)</h3><h1>{config['rinçage_volume']:.0f} mL @ {nacl_debit:.1f} mL/s</h1></div>", unsafe_allow_html=True)
    col_c3.markdown(f"<div class='result-card'><h3>🚀 Débit conseillé</h3><h1>{injection_rate:.1f} mL/s</h1></div>", unsafe_allow_html=True)

    st.info(f"⚠️ Sans rinçage, il aurait fallu injecter {volume_total + 15:.0f} mL de contraste total.")

    if config.get("dilution_enabled", False):
        st.markdown(f"""
        🧪 **Dilution active :**
        - Concentration cible : **{concentration_target:.0f} mg I/mL** (depuis {concentration_init:.0f})
        - Mélange à programmer : **{pct_contrast*100:.1f}% contraste / {pct_nacl*100:.1f}% NaCl**
        - Volume de produit pur : **{volume_contrast_pur:.1f} mL**
        - Volume de NaCl pour dilution : **{volume_nacl_dilution:.1f} mL**
        """)

    if time_adjusted:
        st.warning(f"⚠️ Temps ajusté à {injection_time:.1f}s (débit max {config['max_debit']:.1f} mL/s)")

    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

    st.markdown("""<div style='background-color:#FCE8E6; color:#6B1A00; padding:10px; border-radius:8px; margin-top:15px;'>
    ⚠️ <b>Avertissement :</b> Ce logiciel est un outil d’aide à la décision. Les résultats sont <b>indicatifs</b> et doivent être validés par un professionnel de santé.</div>""", unsafe_allow_html=True)

# -------- Footer --------
st.markdown(f"""<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Les valeurs proposées doivent être validées par un professionnel de santé.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>🧪 Version BETA TEST – Usage interne</div>
</div>""", unsafe_allow_html=True)
