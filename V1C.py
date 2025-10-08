import streamlit as st
import json
import os
import pandas as pd
import math
from datetime import datetime

# === 🎨 Définition des couleurs Guerbet ===
GUERBET_BLUE = "#124F7A"
GUERBET_DARK = "#0D334F"
CARD_BG = "#EAF1F8"

# === 💅 Style CSS personnalisé ===
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
    .beta-banner {{
        background-color: #FCE8B2;
        border: 2px solid #F5B800;
        padding: 10px 15px;
        border-radius: 10px;
        color: #5A4500;
        text-align: center;
        font-weight: 600;
        margin-bottom: 15px;
    }}
</style>
""", unsafe_allow_html=True)

# === 🧾 Chargement / création du fichier de configuration ===
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
    "calc_mode": "Charge iodée sauf IMC > 30 → Surface corporelle"
}

# Si un fichier de configuration existe → le charger
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = default_config.copy()

# === 💾 Fonction pour sauvegarder la configuration ===
def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

# === 🧮 Fonction Surface corporelle (Mosteller) ===
def calculate_bsa(weight, height):
    """Calcule la surface corporelle (m²) selon la formule de Mosteller."""
    return math.sqrt((height * weight) / 3600)

# === 💧 Calcul du volume de contraste ===
def calculate_volume(weight, height, kv, concentration, imc, calc_mode, charges):
    """Calcule le volume (mL) selon le mode de calcul et le kV."""
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

# === ⚡ Calcul du débit d’injection ===
def calculate_injection_rate(volume, time):
    """Retourne le débit (mL/s)."""
    return volume / time if time > 0 else 0

# === ⚙️ Configuration de la page principale ===
st.set_page_config(page_title="Calculette Contraste", page_icon="💉", layout="wide")

# === 🏷️ En-tête avec logo + bandeau version beta ===
col1, col2 = st.columns([1, 5])
with col1:
    st.image("guerbet_logo.png", width=120)
with col2:
    st.markdown(f"""
    <div class='beta-banner'>
        🧪 Version BETA TEST – Développée par <b>Sébastien Partouche</b><br>
        Ce logiciel propose des <b>valeurs indicatives</b> et n’a pas vocation à remplacer le jugement clinique.
    </div>
    <div style='display:flex; align-items:center; justify-content:center;'>
        <h1 style='color:white; background-color:{GUERBET_BLUE}; padding:15px 20px; border-radius:12px; width:100%; text-align:center;'>
            Calculette de dose de produit de contraste
        </h1>
    </div>
    """, unsafe_allow_html=True)

# === 🧭 Création des onglets ===
tab_patient, tab_params = st.tabs(["🧍 Patient", "⚙️ Paramètres"])

# -----------------------------------------------------
# ⚙️ ONGLET PARAMÈTRES
# -----------------------------------------------------
with tab_params:
    st.header("⚙️ Paramètres globaux")

    with st.expander("💊 Configuration du calcul", expanded=True):
        config["concentration_mg_ml"] = st.selectbox(
            "Concentration du produit (mg I/mL)",
            [300,320,350,370,400],
            index=[300,320,350,370,400].index(config["concentration_mg_ml"])
        )
        config["calc_mode"] = st.selectbox(
            "Méthode de calcul",
            ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"],
            index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config["calc_mode"])
        )

    with st.expander("⏱ Temps d'injection"):
        config["portal_time"] = st.number_input("Portal (s)", value=config["portal_time"], min_value=5.0, max_value=120.0, step=1.0)
        config["arterial_time"] = st.number_input("Artériel (s)", value=config["arterial_time"], min_value=5.0, max_value=120.0, step=1.0)
        config["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=config["intermediate_enabled"])
        if config["intermediate_enabled"]:
            config["intermediate_time"] = st.number_input("Intermédiaire (s)", value=config["intermediate_time"], min_value=5.0, max_value=120.0, step=1.0)

    with st.expander("🚀 Départ d’acquisition et charges"):
        config["acquisition_start_param"] = st.number_input("Départ d’acquisition par défaut (s)", value=config["acquisition_start_param"], min_value=0.0, max_value=300.0, step=1.0)
        config["auto_acquisition_by_age"] = st.checkbox("🧮 Calcul automatique selon l’âge", value=config.get("auto_acquisition_by_age", True))

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

# -----------------------------------------------------
# 🧍 ONGLET PATIENT
# -----------------------------------------------------
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
        if config.get("auto_acquisition_by_age", True):
            if 70 <= age <= 90:
                acquisition_start = 70 + (age - 70)
            elif age > 90:
                acquisition_start = 90
            else:
                acquisition_start = config["acquisition_start_param"]
            st.info(f"🚀 Départ d’acquisition auto ({age} ans) : {acquisition_start:.1f} s")
        else:
            acquisition_start = config["acquisition_start_param"]

        acquisition_start = st.number_input("Départ d’acquisition (modifiable) (s)", value=acquisition_start, min_value=0.0, max_value=300.0, step=1.0)

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

    # --- Mention légale dans l'onglet patient ---
    st.markdown("""
    <div style='background-color:#FCE8E6; color:#6B1A00; padding:10px; border-radius:8px; margin-top:15px; font-size:0.9rem;'>
    ⚠️ <b>Avertissement :</b> Ce logiciel est un outil de calcul d’aide à la décision.  
    Les résultats sont <b>indicatifs</b> et doivent être validés par un professionnel de santé.  
    L’auteur, Sébastien Partouche, et Guerbet déclinent toute responsabilité en cas d’erreur ou de mauvaise utilisation.
    </div>
    """, unsafe_allow_html=True)

# --- Pied de page ---
st.markdown(f"""
<div class="footer">
    <p>🧪 Version BETA TEST – Développée par Sébastien Partouche | © 2025 Guerbet<br>
    Ce logiciel fournit des <b>propositions de valeurs</b> et ne remplace en aucun cas le jugement médical.</p>
</div>
""", unsafe_allow_html=True)
