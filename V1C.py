import streamlit as st
import json
import os
import pandas as pd
import math
from datetime import datetime

# --- Couleurs Guerbet ---
GUERBET_BLUE = "#124F7A"
GUERBET_DARK = "#0D334F"
CARD_BG = "#EAF1F8"

# --- CSS personnalisé ---
st.markdown(f"""
<style>
    .stApp {{
        background-color: #F7FAFC;
        font-family: 'Segoe UI', sans-serif;
    }}
    h1, h2, h3 {{
        font-weight: 600;
        letter-spacing: -0.5px;
    }}
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
    .result-card:hover {{
        transform: scale(1.02);
    }}
    .footer {{
        margin-top: 2em;
        font-size: 0.8rem;
        text-align: center;
        color: #666;
    }}
</style>
""", unsafe_allow_html=True)

# --- Fichier de configuration ---
CONFIG_FILE = "iodine_config.json"
default_config = {
    "charges": {str(kv): val for kv, val in zip([80,90,100,110,120],[0.35,0.38,0.40,0.42,0.45])},
    "concentration_mg_ml": 350,
    "portal_time": 30.0,
    "arterial_time": 25.0,
    "intermediate_enabled": False,
    "intermediate_time": 28.0,
    "acquisition_start_param": 70.0,
    "calc_mode": "Charge iodée sauf IMC > 30 → Surface corporelle"
}

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = default_config.copy()

# --- Fonctions utilitaires ---
def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

def calculate_bsa(weight, height):
    """Formule de Mosteller"""
    return math.sqrt((height * weight) / 3600)

def calculate_volume(weight, height, kv, concentration, imc, calc_mode, charges):
    """Calcule le volume de produit de contraste"""
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}

    if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
        bsa = calculate_bsa(weight, height)
        factor = kv_factors.get(kv, None)
        if factor is None:
            return None, bsa
        volume = bsa * factor / (concentration / 1000)
    else:
        charge_iodine = float(charges.get(str(kv), 0.4))
        volume = weight * charge_iodine / (concentration / 1000)
        bsa = None
    return min(volume, 200), bsa

def calculate_injection_rate(volume, time):
    return volume / time if time > 0 else 0

# --- Page ---
st.set_page_config(page_title="Calculette Contraste", page_icon="💉", layout="wide")

# --- En-tête ---
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

# --- Onglets ---
tab_patient, tab_params = st.tabs(["🧍 Patient", "⚙️ Paramètres"])

# --- Onglet Paramètres ---
with tab_params:
    st.header("⚙️ Paramètres globaux")

    with st.expander("💊 Configuration du calcul", expanded=True):
        config["concentration_mg_ml"] = st.selectbox(
            "Concentration du produit (mg I/mL)", [300,320,350,370,400],
            index=[300,320,350,370,400].index(config["concentration_mg_ml"])
        )

        config["calc_mode"] = st.selectbox(
            "Méthode de calcul",
            ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"],
            index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config["calc_mode"])
        )

    with st.expander("⏱ Temps d'injection", expanded=False):
        config["portal_time"] = st.number_input("Portal (s)", value=config["portal_time"], min_value=5.0, max_value=120.0, step=1.0)
        config["arterial_time"] = st.number_input("Artériel (s)", value=config["arterial_time"], min_value=5.0, max_value=120.0, step=1.0)
        config["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=config["intermediate_enabled"])
        if config["intermediate_enabled"]:
            config["intermediate_time"] = st.number_input("Intermédiaire (s)", value=config["intermediate_time"], min_value=5.0, max_value=120.0, step=1.0)

    with st.expander("🚀 Départ d’acquisition et charges", expanded=False):
        config["acquisition_start_param"] = st.number_input("Départ d’acquisition par défaut (s)", value=config["acquisition_start_param"], min_value=0.0, max_value=300.0, step=1.0)

        st.markdown("**Charges en iode par kV (g I/kg)**")
        df_charges = pd.DataFrame({
            "kV": [80,90,100,110,120],
            "Charge (g I/kg)": [config["charges"].get(str(kv),0.35) for kv in [80,90,100,110,120]]
        })
        edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True)

        col_save, col_reset = st.columns(2)
        with col_save:
            if st.button("💾 Sauvegarder les paramètres", key="save_button"):
                config["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _,row in edited_df.iterrows()}
                save_config(config)
                st.success("✅ Paramètres sauvegardés avec succès !")
        with col_reset:
            if st.button("🔄 Réinitialiser par défaut"):
                config = default_config.copy()
                save_config(config)
                st.warning("⚠️ Paramètres réinitialisés.")

# --- Onglet Patient ---
with tab_patient:
    st.header("🧍 Informations patient")

    weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70)
    height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170)
    current_year = datetime.now().year
    birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40)
    age = current_year - birth_year
    imc = weight / ((height / 100) ** 2)

    col1, col2 = st.columns(2)
    with col1:
        concentration_mg_ml = st.selectbox("Concentration (mg I/mL)", [300,320,350,370,400], index=[300,320,350,370,400].index(config["concentration_mg_ml"]))
    with col2:
        acquisition_start = st.number_input("Départ d’acquisition (s)", value=config["acquisition_start_param"], min_value=0.0, max_value=300.0, step=1.0)

    if age < 18:
        st.warning("⚠️ Patient mineur (<18 ans) : le calcul n'est pas autorisé.")
        st.stop()

    injection_modes = ["Portal", "Artériel"]
    if config["intermediate_enabled"]:
        injection_modes.append("Intermédiaire")

    injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True)

    if injection_mode == "Portal":
        injection_time = config["portal_time"]
    elif injection_mode == "Artériel":
        injection_time = config["arterial_time"]
    else:
        injection_time = config["intermediate_time"]

    st.info(f"⏱ Temps d’injection sélectionné : {injection_time:.1f} s")

    kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True)

    volume, bsa = calculate_volume(weight, height, kv_scanner, concentration_mg_ml, imc, config["calc_mode"], config["charges"])

    injection_rate = calculate_injection_rate(volume, injection_time)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div class="result-card">
            <h3 style="color:{GUERBET_BLUE};">💧 Volume appliqué</h3>
            <h1 style="color:{GUERBET_DARK};">{volume:.1f} mL</h1>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="result-card">
            <h3 style="color:{GUERBET_BLUE};">🚀 Débit recommandé</h3>
            <h1 style="color:{GUERBET_DARK};">{injection_rate:.1f} mL/s</h1>
        </div>
        """, unsafe_allow_html=True)

    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

# --- Footer ---
st.markdown(f"""
<div class="footer">
    <p>© 2025 Guerbet - Outil interne | Version Pro</p>
</div>
""", unsafe_allow_html=True)
