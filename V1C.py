import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime

# --- Couleurs Guerbet ---
GUERBET_BLUE = "#124F7A"
GUERBET_DARK = "#0D334F"
CARD_BG = "#EAF1F8"

# --- Fichier de sauvegarde des charges ---
config_file = "iodine_charges.json"
if os.path.exists(config_file):
    with open(config_file, "r") as f:
        saved_charges = json.load(f)
else:
    saved_charges = {str(kv): val for kv, val in zip([80,90,100,110,120],[0.35,0.38,0.40,0.42,0.45])}

# --- Page ---
st.set_page_config(page_title="Calculette Contraste", page_icon="💉", layout="wide")

# --- Header avec logo à gauche et titre centré ---
col1, col2 = st.columns([1, 5])
with col1:
    st.image("guerbet_logo.png", width=120)
with col2:
    st.markdown(f"""
    <div style='display:flex; align-items:center; height:100%;'>
        <h1 style='color:white; margin:0; font-size:2rem; text-align:center; width:100%; background-color:{GUERBET_BLUE}; padding:15px; border-radius:8px;'>
            Calculette de dose de produit de contraste
        </h1>
    </div>
    """, unsafe_allow_html=True)

# --- Onglets ---
tab_patient, tab_params = st.tabs(["Patient", "Paramètres"])

# --- Onglet Paramètres ---
with tab_params:
    st.header("⚙️ Paramètres")

    # Concentration
    concentration_mg_ml = st.selectbox("Concentration du produit (mg I/mL)", [300,320,350,370,400])
    st.session_state["concentration_mg_ml"] = concentration_mg_ml

    # Méthode de calcul
    calc_mode = st.selectbox("Méthode de calcul", ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 35 → Surface corporelle"])
    st.session_state["calc_mode"] = calc_mode

    # --- Temps d'injection configurables ---
    st.subheader("⏱ Temps d'injection")
    portal_time = st.number_input("Portal (s)", value=30.0, min_value=5.0, max_value=120.0, step=1.0)
    arterial_time = st.number_input("Artériel (s)", value=25.0, min_value=5.0, max_value=120.0, step=1.0)
    
    intermediate_enabled = st.checkbox("Activer temps intermédiaire", value=False)
    if intermediate_enabled:
        intermediate_time = st.number_input("Temps intermédiaire (s)", value=28.0, min_value=5.0, max_value=120.0, step=1.0)
        st.session_state["intermediate_time"] = intermediate_time
    st.session_state["portal_time"] = portal_time
    st.session_state["arterial_time"] = arterial_time
    st.session_state["intermediate_enabled"] = intermediate_enabled

    # --- Départ d'acquisition ---
    acquisition_start_param = st.number_input("Départ d'acquisition par défaut (s)", value=70.0, min_value=0.0, max_value=300.0, step=1.0)
    st.session_state["acquisition_start_param"] = acquisition_start_param

    # Charges en iode par kV
    st.subheader("💊 Charges en iode par kV (g I/kg)")
    df_charges = pd.DataFrame({
        "kV": [80,90,100,110,120],
        "Charge (g I/kg)": [saved_charges.get(str(kv),0.35) for kv in [80,90,100,110,120]]
    })
    edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True)

    if st.button("💾 Sauvegarder les charges en iode", key="save_button"):
        new_charges = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for idx,row in edited_df.iterrows()}
        with open(config_file,"w") as f:
            json.dump(new_charges,f)
        st.success("✅ Charges sauvegardées !")

# --- Onglet Patient ---
with tab_patient:
    st.header("🧍 Informations patient")
    
    weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70)
    height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170)
    
    current_year = datetime.now().year
    birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40)
    age = current_year - birth_year

    if age < 18:
        st.warning("⚠️ Patient mineur (<18 ans) : le calcul n'est pas autorisé.")
    else:
        imc = weight / (height/100)**2
        
        # --- Mode d'injection dynamique ---
        injection_options = ["Portal", "Artériel"]
        if st.session_state.get("intermediate_enabled", False):
            injection_options.append("Intermédiaire")
        
        injection_mode = st.radio("Mode d'injection", injection_options, horizontal=True)

        # Récupération du temps correspondant
        if injection_mode == "Portal":
            injection_time = st.session_state["portal_time"]
        elif injection_mode == "Artériel":
            injection_time = st.session_state["arterial_time"]
        else:  # Intermédiaire
            injection_time = st.session_state["intermediate_time"]

        st.info(f"⏱ Temps d'injection sélectionné : {injection_time:.1f} s")

        # --- Départ d'acquisition dynamique selon âge ---
        acquisition_start_param = st.session_state.get("acquisition_start_param", 70.0)
        if 70 <= age <= 90:
            acquisition_start = 70 + (age - 70)  # 70 ans = 70s, 90 ans = 90s
        elif age > 90:
            acquisition_start = 90
        else:
            acquisition_start = acquisition_start_param  # valeur par défaut ou modifiée dans Paramètres
        st.info(f"🚀 Départ d'acquisition utilisé : {acquisition_start:.1f} s")

        # --- Calcul du volume ---
        concentration_mg_ml = st.session_state.get("concentration_mg_ml", 350)
        calc_mode = st.session_state.get("calc_mode", "Charge iodée sauf IMC > 35 → Surface corporelle")
        kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True)
        charge_iodine = float(saved_charges.get(str(kv_scanner),0.40))

        if calc_mode == "Surface corporelle" or (calc_mode == "Charge iodée sauf IMC > 35 → Surface corporelle" and imc >= 35):
            bsa = 0.007184 * (weight**0.425) * (height**0.725)
            applied_volume = bsa * 15 / (concentration_mg_ml / 1000)
        else:
            applied_volume = weight * charge_iodine / (concentration_mg_ml / 1000)

        applied_volume = min(applied_volume,200)
        injection_rate = applied_volume / injection_time

        # --- Affichage résultats ---
        st.subheader("💡 Résultats")
        col1, col2 = st.columns(2)
        col1.markdown(f"""
            <div style="background-color:{CARD_BG}; border-radius:10px; padding:20px; text-align:center;">
                <h3 style="color:{GUERBET_BLUE};">Volume appliqué</h3>
                <h2 style="color:{GUERBET_DARK};">{applied_volume:.1f} mL</h2>
            </div>
            """, unsafe_allow_html=True)
        col2.markdown(f"""
            <div style="background-color:{CARD_BG}; border-radius:10px; padding:20px; text-align:center;">
                <h3 style="color:{GUERBET_BLUE};">Débit recommandé</h3>
                <h2 style="color:{GUERBET_DARK};">{injection_rate:.1f} mL/s</h2>
            </div>
            """, unsafe_allow_html=True)
