# -*- coding: utf-8 -*-
"""
Calculette de dose de produit de contraste — Oncologie CT adulte
"""

import streamlit as st
import json
import os
import math
import base64
from datetime import datetime
import pandas as pd

CONFIG_FILE = "iodine_config.json"
USER_SESSIONS_FILE = "user_sessions.json"
LOG_FILE = "calc_audit.log"

default_config = {
    "charges": {str(kv): val for kv, val in zip([80, 90, 100, 110, 120], [0.35, 0.38, 0.40, 0.42, 0.45])},
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
    "target_concentration": 350,
    "volume_max_limit": 200.0
}

def load_json_safe(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default.copy()
    return default.copy()

def save_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(tmp, path)

def audit_log(msg):
    try:
        ts = datetime.utcnow().isoformat()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts} - {msg}\n")
    except:
        pass

config = load_json_safe(CONFIG_FILE, default_config)
user_sessions = load_json_safe(USER_SESSIONS_FILE, {})

def save_config(cfg):
    save_json_atomic(CONFIG_FILE, cfg)

def save_user_sessions(sessions):
    save_json_atomic(USER_SESSIONS_FILE, sessions)

def calculate_bsa(weight, height):
    return math.sqrt((height * weight) / 3600.0)

def calculate_volume(weight, height, kv, concentration_mg_ml, imc, calc_mode, charges, volume_cap):
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
    concentration_g_ml = concentration_mg_ml / 1000.0
    if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
        bsa = calculate_bsa(weight, height)
        factor = kv_factors.get(kv, 15)
        volume = bsa * factor / concentration_g_ml
    else:
        charge_iodine = float(charges.get(str(kv), 0.4))
        volume = weight * charge_iodine / concentration_g_ml
        bsa = None
    volume = min(volume, volume_cap)
    return volume, bsa

def calculate_acquisition_start(age, cfg):
    if not cfg.get("auto_acquisition_by_age", True):
        return cfg.get("acquisition_start_param", 70.0)
    if age < 70:
        return cfg.get("acquisition_start_param", 70.0)
    elif 70 <= age <= 90:
        return float(age)
    else:
        return 90.0

def adjust_injection_rate(volume, injection_time, max_debit):
    rate = volume / injection_time
    if rate > max_debit:
        injection_time = volume / max_debit
        rate = max_debit
    return rate, injection_time

st.set_page_config(page_title="Calculette Contraste — Oncologie CT adulte", page_icon="💉", layout="wide")

if "user_id" not in st.session_state:
    st.session_state["user_id"] = None

# --- Auth simple
if st.session_state["user_id"] is None:
    st.markdown("### 🧑 Connexion utilisateur")
    existing_ids = list(user_sessions.keys())
    chosen_id = st.selectbox("Sélectionner un identifiant :", [""] + existing_ids)
    new_id = st.text_input("Créer un nouvel identifiant")
    if st.button("Entrer"):
        if new_id.strip():
            if new_id in existing_ids:
                st.error("⚠️ Cet identifiant existe déjà.")
            else:
                user_sessions[new_id] = {"programs": {}, "email": ""}
                save_user_sessions(user_sessions)
                st.session_state["user_id"] = new_id
        elif chosen_id:
            st.session_state["user_id"] = chosen_id
        else:
            st.warning("Veuillez choisir ou créer un identifiant.")
    st.stop()

user_id = st.session_state["user_id"]
if user_id not in user_sessions:
    user_sessions[user_id] = {"programs": {}, "email": ""}
    save_user_sessions(user_sessions)

# --- Header
st.markdown(f"""
<div style="background:#124F7A;color:white;padding:10px;border-radius:10px;">
<h2>💉 Calculette de dose de produit de contraste — Oncologie CT adulte</h2>
</div>
""", unsafe_allow_html=True)

tab_patient, tab_params, tab_tutorial = st.tabs(["🧍 Patient", "⚙️ Paramètres", "📘 Tutoriel"])

# --- Onglet PARAMÈTRES
with tab_params:
    st.header("⚙️ Paramètres — Enregistrés dans votre espace personnel")
    st.markdown(f"**Identifiant connecté :** `{user_id}`")

    st.subheader("Paramètres techniques")
    config["auto_acquisition_by_age"] = st.checkbox("Activer l’ajustement automatique du départ d’acquisition selon l’âge", value=config.get("auto_acquisition_by_age", True))
    config["simultaneous_enabled"] = st.checkbox("Activer l’injection simultanée", value=config.get("simultaneous_enabled", False))
    if config["simultaneous_enabled"]:
        config["target_concentration"] = st.number_input("Concentration cible (mg I/mL)", value=int(config.get("target_concentration", 350)), min_value=200, max_value=500, step=10)

    st.subheader("Autres paramètres")
    config["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)", [300, 320, 350, 370, 400], index=[300,320,350,370,400].index(int(config.get("concentration_mg_ml",350))))
    config["calc_mode"] = st.selectbox("Méthode de calcul", ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config.get("calc_mode","Charge iodée")))
    config["max_debit"] = st.number_input("Débit max (mL/s)", value=float(config.get("max_debit",6.0)), min_value=1.0, max_value=20.0, step=0.1)
    config["portal_time"] = st.number_input("Temps Portal (s)", value=float(config.get("portal_time",30.0)))
    config["arterial_time"] = st.number_input("Temps Artériel (s)", value=float(config.get("arterial_time",25.0)))
    config["intermediate_enabled"] = st.checkbox("Activer le temps intermédiaire", value=config.get("intermediate_enabled", False))
    if config["intermediate_enabled"]:
        config["intermediate_time"] = st.number_input("Temps Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)))
    config["rincage_volume"] = st.number_input("Volume de rinçage (mL)", value=float(config.get("rincage_volume",35.0)))
    config["rincage_delta_debit"] = st.number_input("Δ Débit NaCl vs contraste (mL/s)", value=float(config.get("rincage_delta_debit",0.5)))
    if st.button("💾 Sauvegarder paramètres"):
        save_config(config)
        st.success("✅ Paramètres enregistrés !")

# --- Onglet PATIENT
with tab_patient:
    st.header("🧍 Informations patient")

    col_w, col_h, col_birth, col_prog = st.columns([1,1,1,1.2])
    with col_w:
        weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70)
    with col_h:
        height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170)
    with col_birth:
        birth_year = st.select_slider("Année de naissance", options=list(range(datetime.now().year-120, datetime.now().year+1)), value=datetime.now().year-40)
    with col_prog:
        prog_choice = st.selectbox("Programme", ["Sélection d'un programme"] + list(user_sessions[user_id].get("programs", {}).keys()))

    # --- Affichage infos sous taille/naissance
    kv_current = 120
    st.markdown(f"""
    🧮 **Méthode utilisée :** {config.get("calc_mode","Charge iodée")}  
    💊 **Charge iodée appliquée (kV {kv_current}) :** {config["charges"].get(str(kv_current),0.45)} g I/kg  
    🕒 {"Ajustement automatique du départ d'acquisition selon l'âge activé" if config.get("auto_acquisition_by_age") else "Ajustement automatique du départ d'acquisition désactivé"}  
    💧 {"Injection simultanée activée" if config.get("simultaneous_enabled") else "Injection simultanée désactivée"}  
    """)

    # --- Mode d'injection et kV sous poids
    st.subheader("Mode d’injection")
    injection_modes = ["Portal","Artériel"]
    if config.get("intermediate_enabled", False):
        injection_modes.append("Intermédiaire")
    injection_mode = st.radio("", injection_modes, horizontal=True)
    kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], horizontal=True, index=4)

    # --- Calculs
    age = datetime.now().year - birth_year
    imc = weight / ((height/100)**2)
    base_time = config["portal_time"] if injection_mode=="Portal" else config["arterial_time"]
    if injection_mode=="Intermédiaire":
        base_time = config["intermediate_time"]
        st.markdown("<span style='color:#E67E22'>⚠️ Pensez à ajuster votre départ d’acquisition manuellement.</span>", unsafe_allow_html=True)

    acquisition_start = calculate_acquisition_start(age, config)
    st.markdown(f"""
    **Temps {injection_mode} :** {base_time:.0f} s  
    **Départ d'acquisition :** {acquisition_start:.1f} s  
    **Concentration utilisée :** {int(config.get("concentration_mg_ml",350))} mg I/mL  
    """)

    volume, bsa = calculate_volume(weight, height, kv_scanner, config["concentration_mg_ml"], imc, config["calc_mode"], config["charges"], config["volume_max_limit"])
    rate, time = adjust_injection_rate(volume, base_time, config["max_debit"])

    # --- Bloc résultats
    st.markdown("---")
    col_contrast, col_nacl = st.columns(2)
    with col_contrast:
        st.markdown(f"""
        <div style="background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;">
        <h3>🟢 Volume et Débit de contraste conseillés</h3>
        <h1>{int(round(volume))} mL @ {rate:.1f} mL/s</h1>
        </div>
        """, unsafe_allow_html=True)
    with col_nacl:
        if config.get("simultaneous_enabled", False):
            dilution_vol = max(0.0, volume * (config["target_concentration"]/config["concentration_mg_ml"]))
            rinç_vol = config["rincage_volume"]
            rinç_rate = max(0.1, rate - config["rincage_delta_debit"])
            st.markdown(f"""
            <div style="background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;">
            <h3>🔵 Volume et Débit de NaCl conseillés</h3>
            💧 Dilution NaCl : {int(round(dilution_vol))} mL<br>
            💧 Rinçage : {int(round(rinç_vol))} mL @ {rinç_rate:.1f} mL/s
            </div>
            """, unsafe_allow_html=True)
        else:
            rinç_vol = config["rincage_volume"]
            rinç_rate = max(0.1, rate - config["rincage_delta_debit"])
            st.markdown(f"""
            <div style="background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;">
            <h3>🔵 Volume et Débit de NaCl conseillés</h3>
            💧 Volume : {int(round(rinç_vol))} mL<br>
            💧 Débit : {rinç_rate:.1f} mL/s
            </div>
            """, unsafe_allow_html=True)

# --- Onglet TUTORIEL
with tab_tutorial:
    st.header("📘 Tutoriel — basé sur le CIRTACI 5.3.0 (2020)")
    st.markdown("""
    Ce module de calcul est conçu selon les principes de la fiche CIRTACI VASCULAIRE (version 5.3.0, 2020).
    - Calcul des volumes selon charge iodée / BSA.
    - Ajustement automatique possible selon l’âge.
    - Injection simultanée configurable.
    [📄 Consulter les recommandations officielles CIRTACI](https://www.radiologie.fr/sites/www.radiologie.fr/files/medias/documents/CIRTACI%20Fiche%20Généralités%20VASCULAIRE_5_3_1.pdf)
    """)

# --- Footer
st.markdown("""
<div style='text-align:center;margin-top:20px;font-size:0.8rem;color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Calculette de dose de produit de contraste en oncologie CT adulte.<br>
<a href='https://www.radiologie.fr/sites/www.radiologie.fr/files/medias/documents/CIRTACI%20Fiche%20Généralités%20VASCULAIRE_5_3_1.pdf' target='_blank'>
🔗 Recommandations CIRTACI 5.3.0 (2020)
</a>
</div>
""", unsafe_allow_html=True)
