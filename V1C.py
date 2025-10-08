import streamlit as st
import json
import os
import pandas as pd
import math
from datetime import datetime

# =========================================
# Couleurs et styles
# =========================================
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
        padding: 20px;
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
</style>
""", unsafe_allow_html=True)

# =========================================
# Configuration et fichier JSON
# =========================================
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

# =========================================
# Fonctions de calcul
# =========================================
def calculate_bsa(weight, height):
    return math.sqrt((height * weight) / 3600)

def calculate_volume(weight, height, kv, concentration, imc, calc_mode, charges):
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
    if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
        bsa = calculate_bsa(weight, height)
        factor = kv_factors.get(kv, 15)  # fallback 15 si kv non défini
        volume = bsa * factor / (concentration / 1000)
    else:
        charge_iodine = float(charges.get(str(kv), 0.4))
        volume = weight * charge_iodine / (concentration / 1000)
        bsa = None
    return min(volume, 200), bsa

def calculate_injection_rate(volume, time):
    return volume / time if time > 0 else 0

def calculate_acquisition_start(age, config):
    if not config.get("auto_acquisition_by_age", True):
        return float(config["acquisition_start_param"])
    if age < 70:
        return float(config["acquisition_start_param"])
    elif 70 <= age <= 90:
        # linéaire de 70 → 90 ans : 70 → 90 s
        return 70 + (age - 70) * (90 - 70) / (90 - 70)  # simplifie à age
    else:
        return 90.0

# =========================================
# Page Streamlit
# =========================================
st.set_page_config(page_title="Calculette Contraste", page_icon="💉", layout="wide")

# === En-tête ===
col1, col2 = st.columns([1, 5])
with col1:
    st.image("guerbet_logo.png", width=120)
with col2:
    st.markdown(f"""
    <div style='display:flex; align-items:center; justify-content:center;'>
        <h1 style='color:white; background-color:{GUERBET_BLUE}; padding:15px 20px; border-radius:12px; width:100%; text-align:center;'>
            Calculette de dose de produit de contraste
        </h1>
    </div>
    """, unsafe_allow_html=True)

# === Onglets ===
tab_patient, tab_params = st.tabs(["🧍 Patient", "⚙️ Paramètres"])

# -----------------------------------------
# Onglet Paramètres
# -----------------------------------------
with tab_params:
    st.header("⚙️ Paramètres globaux")

    with st.expander("💊 Configuration du calcul", expanded=True):
        config["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)",[300,320,350,370,400], index=[300,320,350,370,400].index(config["concentration_mg_ml"]), key="param_concentration")
        config["calc_mode"] = st.selectbox("Méthode de calcul",["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config["calc_mode"]), key="param_calc_mode")
        config["max_debit"] = st.number_input("Débit maximal autorisé (mL/s)", value=config.get("max_debit",6.0), min_value=1.0, max_value=20.0, step=0.1, key="param_max_debit")

    with st.expander("⏱ Temps d'injection"):
        config["portal_time"] = st.number_input("Portal (s)", value=config["portal_time"], min_value=5.0, max_value=120.0, step=1.0, key="param_portal_time")
        config["arterial_time"] = st.number_input("Artériel (s)", value=config["arterial_time"], min_value=5.0, max_value=120.0, step=1.0, key="param_arterial_time")
        config["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=config["intermediate_enabled"], key="param_intermediate_enabled")
        if config["intermediate_enabled"]:
            config["intermediate_time"] = st.number_input("Intermédiaire (s)", value=config["intermediate_time"], min_value=5.0, max_value=120.0, step=1.0, key="param_intermediate_time")

    with st.expander("🚀 Départ d’acquisition et charges"):
        config["acquisition_start_param"] = st.number_input("Départ d’acquisition par défaut (s)", value=config["acquisition_start_param"], min_value=0.0, max_value=300.0, step=1.0, key="param_acquisition_start")
        config["auto_acquisition_by_age"] = st.checkbox("Calcul automatique selon l’âge", value=config.get("auto_acquisition_by_age", True), key="param_auto_acq_age")
        st.markdown("**Charges en iode par kV (g I/kg)**")
        df_charges = pd.DataFrame({"kV": [80,90,100,110,120],"Charge (g I/kg)": [config["charges"].get(str(kv),0.35) for kv in [80,90,100,110,120]]})
        edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True, key="param_charges_editor")
        if st.button("💾 Sauvegarder les paramètres", key="param_save_button"):
            config["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _,row in edited_df.iterrows()}
            save_config(config)
            st.success("✅ Paramètres sauvegardés avec succès !")

# -----------------------------------------
# Onglet Patient
# -----------------------------------------
with tab_patient:
    st.header("🧍 Informations patient")
    weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70, key="patient_weight")
    height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170, key="patient_height")
    current_year = datetime.now().year
    birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40, key="patient_birth_year")
    age = current_year - birth_year
    imc = weight / ((height / 100) ** 2)

    col1, col2 = st.columns(2)
    with col1:
        concentration_mg_ml = st.selectbox("Concentration (mg I/mL)", [300,320,350,370,400], index=[300,320,350,370,400].index(config["concentration_mg_ml"]), key="patient_concentration")
    with col2:
        acquisition_start = st.number_input(
            "Départ d’acquisition (modifiable) (s)",
            value=calculate_acquisition_start(age, config),
            min_value=0.0,
            max_value=300.0,
            step=1.0,
            key="patient_acquisition_start"
        )

    if config.get("auto_acquisition_by_age", True):
        st.info("ℹ️ Le départ d’acquisition est calculé automatiquement en fonction de l’âge du patient.")
    else:
        st.info("ℹ️ Le départ d’acquisition utilise la valeur par défaut/modifiable.")

    if age < 18:
        st.warning("⚠️ Patient mineur (<18 ans) : le calcul n'est pas autorisé.")
        st.stop()

    injection_modes = ["Portal", "Artériel"]
    if config["intermediate_enabled"]:
        injection_modes.append("Intermédiaire")
    injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True, key="patient_injection_mode")
    if injection_mode == "Portal":
        injection_time = config["portal_time"]
    elif injection_mode == "Artériel":
        injection_time = config["arterial_time"]
    else:
        injection_time = config["intermediate_time"]
    st.info(f"⏱ Temps d’injection sélectionné : {injection_time:.1f} s")

    kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True, key="patient_kv")

    accepted = st.checkbox("✅ J’ai lu et j’accepte la mention légale et les conditions d’utilisation.", key="patient_accept_legal")
    if not accepted:
        st.warning("Vous devez accepter la mention légale pour afficher le calcul.")
        st.stop()

    volume, bsa = calculate_volume(weight, height, kv_scanner, concentration_mg_ml, imc, config["calc_mode"], config["charges"])
    injection_rate = calculate_injection_rate(volume, injection_time)

    MAX_DEBIT = config.get("max_debit", 6.0)
    time_adjusted = False
    if injection_rate > MAX_DEBIT:
        injection_time = volume / MAX_DEBIT
        injection_rate = MAX_DEBIT
        time_adjusted = True

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""<div class="result-card"><h3 style="color:{GUERBET_BLUE};">💧 Volume appliqué</h3><h1 style="color:{GUERBET_DARK};">{volume:.1f} mL</h1></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="result-card"><h3 style="color:{GUERBET_BLUE};">🚀 Débit recommandé</h3><h1 style="color:{GUERBET_DARK};">{injection_rate:.1f} mL/s</h1></div>""", unsafe_allow_html=True)

    if time_adjusted:
        st.warning(f"⚠️ Le temps d’injection a été automatiquement ajusté à {injection_time:.1f}s pour respecter le débit maximal de {MAX_DEBIT} mL/s.")

    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

    st.markdown("""<div style='background-color:#FCE8E6; color:#6B1A00; padding:10px; border-radius:8px; margin-top:15px; font-size:0.9rem;'>⚠️ <b>Avertissement :</b> Ce logiciel est un outil d’aide à la décision. Les résultats sont <b>indicatifs</b> et doivent être validés par un professionnel de santé. L’auteur, Sébastien Partouche, et Guerbet déclinent toute responsabilité en cas d’erreur ou de mauvaise utilisation.</div>""", unsafe_allow_html=True)

# Pied de page / Beta Test
st.markdown(f"""<div class="footer"><p>© 2025 Guerbet | Développé par <b>Sébastien Partouche</b></p><p>Ce logiciel fournit des <b>propositions de valeurs</b> et ne remplace pas le jugement médical.</p><div class="beta-footer">🧪 Version BETA TEST – Usage interne / évaluation</div></div>""", unsafe_allow_html=True)
