import streamlit as st
import json
import os
import pandas as pd
import math
from datetime import datetime

# ===================== Styles =====================
GUERBET_BLUE = "#124F7A"
GUERBET_DARK = "#0D334F"
CARD_BG = "#EAF1F8"

st.set_page_config(page_title="Calculette Contraste", page_icon="💉", layout="wide")

st.markdown(f"""
<style>
/* Global */
.stApp {{ background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }}
h1, h2, h3 {{ font-weight: 600; letter-spacing: -0.5px; }}

/* Header banner */
.header-banner {{
  display: flex;
  align-items: center;
  gap: 1rem;
  background-color: {GUERBET_BLUE};
  padding: 0.2rem 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
}}
.header-logo {{
  height: 84px;              /* banner height */
  width: auto;
  max-height:84px;
  object-fit: contain;
}}
.header-title {{
  color: white;
  font-size: 1.9rem;
  text-align: center;
  flex: 1;
  margin-right: 2rem; /* spacing to keep title centered visually */
}}
.header-right {{ width: 84px; }} /* placeholder to help centering */

/* Result cards */
.result-card {{
    background-color: {CARD_BG};
    border-radius: 12px;
    box-shadow: 0 4px 10px rgba(0,0,0,0.06);
    padding: 18px;
    text-align: center;
}}
.small-note {{ font-size:0.9rem; color:#333; }}

/* Big overlay (not used here as we use blocking form) */
</style>
""", unsafe_allow_html=True)

# ===================== Config =====================
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
    """Mosteller simplified BSA"""
    return math.sqrt((height * weight) / 3600)

def calculate_volume(weight, height, kv, concentration, imc, calc_mode, charges):
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
    if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
        bsa = calculate_bsa(weight, height)
        factor = kv_factors.get(kv, 15)  # fallback
        volume = bsa * factor / (concentration / 1000)
    else:
        charge_iodine = float(charges.get(str(kv), 0.4))
        volume = weight * charge_iodine / (concentration / 1000)
        bsa = None
    return min(volume, 200.0), bsa

def calculate_acquisition_start(age, cfg):
    if not cfg.get("auto_acquisition_by_age", True):
        return float(cfg.get("acquisition_start_param", 70.0))
    if age < 70:
        return float(cfg.get("acquisition_start_param", 70.0))
    elif 70 <= age <= 90:
        # linear mapping 70->70, 90->90 (simple identity)
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

# ===================== Session init =====================
if "accepted_legal" not in st.session_state:
    st.session_state["accepted_legal"] = False

# ===================== Header (logo left, title centered) =====================
# Use an HTML block to get perfect alignment and image sizing
logo_path = "guerbet_logo.png"  # ensure this file exists in app folder
logo_html = f"<img src='{logo_path}' class='header-logo' alt='Guerbet logo' />"
st.markdown(f"""
<div class="header-banner">
  <div style="display:flex; align-items:center;">{logo_html}</div>
  <div class="header-title">Calculette de dose de produit de contraste</div>
  <div class="header-right"></div>
</div>
""", unsafe_allow_html=True)

# ===================== Acceptance (blocking at launch) =====================
if not st.session_state["accepted_legal"]:
    st.markdown("### Mentions légales — acceptation requise")
    st.markdown("Avant d'utiliser cet outil, vous devez accepter la mention légale et les conditions d'utilisation. Ce logiciel est un outil d'aide à la décision ; il ne remplace pas le jugement d'un professionnel de santé.")
    col_a, col_b, col_c = st.columns([1,2,1])
    with col_b:
        accept = st.checkbox("✅ Je reconnais avoir lu et j'accepte la mention légale et les conditions d'utilisation.", key="accept_checkbox")
        if st.button("Accepter et continuer"):
            if accept:
                st.session_state["accepted_legal"] = True
                st.experimental_rerun()
            else:
                st.warning("Vous devez cocher la case pour accepter les mentions légales.")
    # stop rendering the rest until accepted
    st.stop()

# ===================== Patient section (single page) =====================
st.header("🧍 Informations patient")

# --- Inputs ---
col_w, col_h, col_birth = st.columns([1,1,1])
with col_w:
    weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70, key="patient_weight")
with col_h:
    height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170, key="patient_height")
with col_birth:
    current_year = datetime.now().year
    birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40, key="patient_birth_year")

age = current_year - birth_year
imc = weight / ((height / 100) ** 2)

# --- KV / concentration / acquisition row ---
col_kv, col_info = st.columns([2,3])
with col_kv:
    kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True, key="patient_kv")
with col_info:
    # compute acquisition start (read-only) and show concentration (read-only)
    acquisition_start = calculate_acquisition_start(age, config)
    # Show as two small metrics or text blocks for readability
    st.markdown("**Paramètres dérivés**")
    c1, c2 = st.columns([1,1])
    with c1:
        st.markdown(f"<div class='small-note'><b>Concentration (mg I/mL)</b><br/>{int(config['concentration_mg_ml'])} mg/mL</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='small-note'><b>Départ d'acquisition (s)</b><br/>{float(acquisition_start):.1f} s</div>", unsafe_allow_html=True)

# --- Acceptance already done earlier, so show calculation controls ---
# Injection mode and times: arrange tidy
injection_modes = ["Portal", "Artériel"]
if config.get("intermediate_enabled", False):
    injection_modes.append("Intermédiaire")

col_mode, col_time = st.columns([2,2])
with col_mode:
    injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True, key="patient_injection_mode")
with col_time:
    if injection_mode == "Portal":
        base_time = float(config.get("portal_time", 30.0))
        st.markdown(f"**Temps sélectionné :** {base_time:.0f} s")
    elif injection_mode == "Artériel":
        base_time = float(config.get("arterial_time", 25.0))
        st.markdown(f"**Temps sélectionné :** {base_time:.0f} s")
    else:
        # allow user to modify intermediate on patient page
        base_time = st.number_input("Temps intermédiaire (s)", value=float(config.get("intermediate_time", 28.0)), min_value=5.0, max_value=120.0, step=1.0, key="patient_intermediate_time")

# --- Volume & Rate calculation ---
concentration_mg_ml = float(config["concentration_mg_ml"])
volume, bsa = calculate_volume(weight, height, kv_scanner, concentration_mg_ml, imc, config["calc_mode"], config["charges"])
injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume, float(base_time), float(config.get("max_debit", 6.0)))

# --- Results display (aligned, professional) ---
res_col1, res_col2 = st.columns([1,1])
with res_col1:
    st.markdown(f"""<div class="result-card"><h3 style="color:{GUERBET_BLUE}; margin-bottom:6px;">💧 Volume appliqué</h3><h1 style="color:{GUERBET_DARK}; margin:0;">{volume:.1f} mL</h1><div style="margin-top:8px;" class="small-note">Limité à 200 mL si applicable</div></div>""", unsafe_allow_html=True)
with res_col2:
    st.markdown(f"""<div class="result-card"><h3 style="color:{GUERBET_BLUE}; margin-bottom:6px;">🚀 Débit recommandé</h3><h1 style="color:{GUERBET_DARK}; margin:0;">{injection_rate:.1f} mL/s</h1><div style="margin-top:8px;" class="small-note">Temps effectif : {injection_time:.1f} s</div></div>""", unsafe_allow_html=True)

if time_adjusted:
    st.warning(f"⚠️ Le temps d’injection a été ajusté automatiquement à {injection_time:.1f} s pour respecter le débit maximal de {config.get('max_debit', 6.0)} mL/s.")

st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

# --- Legal note and footer ---
st.markdown("""<div style='background-color:#FCE8E6; color:#6B1A00; padding:10px; border-radius:8px; margin-top:16px; font-size:0.9rem;'>⚠️ <b>Avertissement :</b> Ce logiciel est un outil d’aide à la décision. Les résultats sont <b>indicatifs</b> et doivent être validés par un professionnel de santé.</div>""", unsafe_allow_html=True)

st.markdown(f"""<div style='margin-top:14px; text-align:center; color:#666; font-size:0.9rem;'>© 2025 Guerbet | Développé par <b>Sébastien Partouche</b> — Version BETA TEST</div>""", unsafe_allow_html=True)
