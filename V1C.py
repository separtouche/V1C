
# -# -*- coding: utf-8 -*-
"""
Calculette complète (une page) de dose de produit de contraste - Oncologie adulte
Adaptée pour Sébastien Partouche — version consolidée optimisée
Usage : streamlit run calculatrice_contraste_oncologie.py
"""

import streamlit as st
import json
import os
import math
import base64
from datetime import datetime
import pandas as pd

# ------------------------
# Fichiers de config
# ------------------------
CONFIG_FILE = "iodine_config.json"
LIB_FILE = "libraries.json"
USER_SESSIONS_FILE = "user_sessions.json"
LOG_FILE = "calc_audit.log"

# ------------------------
# Valeurs par défaut
# ------------------------
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

# ------------------------
# Utils I/O sécurisées
# ------------------------
def load_json_safe(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"⚠️ Erreur lecture '{path}' — valeurs par défaut utilisées. Détail: {e}")
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
    except Exception:
        pass

# ------------------------
# Charger config & libs
# ------------------------
config = load_json_safe(CONFIG_FILE, default_config)
libraries = load_json_safe(LIB_FILE, {"programs": {}})
user_sessions = load_json_safe(USER_SESSIONS_FILE, {})

# ------------------------
# Fonctions métier
# ------------------------
def save_config(cfg): save_json_atomic(CONFIG_FILE, cfg)
def save_libraries(lib): save_json_atomic(LIB_FILE, lib)
def save_user_sessions(sessions): save_json_atomic(USER_SESSIONS_FILE, sessions)

def calculate_bsa(weight, height):
    try:
        return math.sqrt((height * weight) / 3600.0)
    except Exception:
        return None

def calculate_volume(weight, height, kv, concentration_mg_ml, imc, calc_mode, charges, volume_cap):
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
    concentration_g_ml = concentration_mg_ml / 1000.0
    bsa = None
    try:
        if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
            bsa = calculate_bsa(weight, height)
            factor = kv_factors.get(kv, 15)
            volume = bsa * factor / concentration_g_ml
        else:
            charge_iodine = float(charges.get(str(kv), 0.4))
            volume = weight * charge_iodine / concentration_g_ml
    except Exception:
        volume = 0.0
    volume = max(0.0, float(volume))
    if volume > volume_cap:
        volume = volume_cap
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
    injection_time = float(injection_time) if injection_time > 0 else 1.0
    injection_rate = volume / injection_time
    time_adjusted = False
    if injection_rate > max_debit:
        injection_time = volume / max_debit
        injection_rate = max_debit
        time_adjusted = True
    return float(injection_rate), float(injection_time), bool(time_adjusted)

def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ------------------------
# Streamlit UI init
# ------------------------
st.set_page_config(page_title="Calculette Contraste Oncologie adulte", page_icon="💉", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }
</style>
""", unsafe_allow_html=True)

if "accepted_legal" not in st.session_state: st.session_state["accepted_legal"] = False
if "user_id" not in st.session_state: st.session_state["user_id"] = None
if "selected_program" not in st.session_state: st.session_state["selected_program"] = None

# ------------------------
# Page d'accueil : Mentions légales + session utilisateur
# ------------------------
if not st.session_state["accepted_legal"] or st.session_state["user_id"] is None:
    st.markdown("### ⚠️ Mentions légales — acceptation requise")
    st.markdown("Avant utilisation, acceptez la mention légale et créez ou sélectionnez votre identifiant utilisateur.")
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")

    existing_ids = list(user_sessions.keys())
    user_id_input = st.selectbox("Sélectionner un identifiant existant :", [""] + existing_ids)
    new_user_id = st.text_input("Ou créez un nouvel identifiant")

    if st.button("Entrer dans la session"):
        if not accept:
            st.warning("Vous devez accepter les mentions légales.")
        else:
            chosen_id = new_user_id.strip() if new_user_id.strip() else user_id_input
            if not chosen_id:
                st.warning("Veuillez saisir ou sélectionner un identifiant.")
            else:
                st.session_state["accepted_legal"] = True
                st.session_state["user_id"] = chosen_id
                if chosen_id not in user_sessions:
                    user_sessions[chosen_id] = {"programs": {}}
                    save_user_sessions(user_sessions)
    st.stop()

# ------------------------
# Header (sans identifiant)
# ------------------------
logo_path = "guerbet_logo.png"
if os.path.exists(logo_path):
    img_b64 = img_to_base64(logo_path)
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:8px; background:#124F7A; padding:8px; border-radius:8px">
        <img src="data:image/png;base64,{img_b64}" style="height:60px"/>
        <h2 style="color:white; margin:0;">Calculette de dose de produit de contraste — Oncologie adulte</h2>
    </div>
    """, unsafe_allow_html=True)
else:
    st.title("Calculette de dose de produit de contraste — Oncologie adulte")

# ------------------------
# Tabs
# ------------------------
tab_patient, tab_params, tab_tutorial = st.tabs(["🧍 Patient", "⚙️ Paramètres", "📘 Tutoriel"])

# ------------------------
# Onglet Paramètres
# ------------------------
with tab_params:
    st.header("⚙️ Paramètres et Bibliothèque")
    st.markdown(f"**Identifiant utilisateur actif :** `{st.session_state['user_id']}`")

    st.subheader("👤 Gestion des sessions utilisateurs")
    existing_sessions = list(user_sessions.keys())
    session_to_delete = st.selectbox("Sélectionner une session à supprimer", [""] + existing_sessions)
    if session_to_delete:
        if session_to_delete == st.session_state["user_id"]:
            st.warning("⚠️ Impossible de supprimer l'identifiant actuellement utilisé.")
        else:
            confirm_delete = st.checkbox(f"Confirmer la suppression de la session '{session_to_delete}'")
            if st.button("🗑 Supprimer la session"):
                if confirm_delete:
                    if session_to_delete in user_sessions:
                        del user_sessions[session_to_delete]
                        save_user_sessions(user_sessions)
                        st.success(f"Session '{session_to_delete}' supprimée !")
                        st.experimental_rerun()
                    else:
                        st.warning("Session introuvable.")
                else:
                    st.warning("Veuillez cocher la case avant suppression.")

    st.markdown("---")
    config["simultaneous_enabled"] = st.checkbox("Activer l'injection simultanée", value=config.get("simultaneous_enabled", False))
    if config["simultaneous_enabled"]:
        config["target_concentration"] = st.number_input("Concentration cible (mg I/mL)", value=int(config.get("target_concentration", 350)), min_value=200, max_value=500, step=10)
    st.subheader("📚 Bibliothèque de programmes")
    program_choice = st.selectbox("Programme", ["Aucun"] + list(libraries.get("programs", {}).keys()), key="prog_params")
    if program_choice != "Aucun":
        prog_conf = libraries["programs"].get(program_choice, {})
        for key, val in prog_conf.items():
            config[key] = val
    new_prog_name = st.text_input("Nom du nouveau programme")
    if st.button("💾 Ajouter/Mise à jour programme"):
        if new_prog_name.strip():
            libraries["programs"][new_prog_name.strip()] = config.copy()
            save_libraries(libraries)
            st.success(f"Programme '{new_prog_name}' ajouté/mis à jour !")
    if libraries.get("programs"):
        del_prog = st.selectbox("Supprimer un programme", [""] + list(libraries["programs"].keys()))
        if st.button("🗑 Supprimer programme"):
            if del_prog in libraries["programs"]:
                del libraries["programs"][del_prog]
                save_libraries(libraries)
                st.success(f"Programme '{del_prog}' supprimé !")

# ------------------------
# Onglet Patient
# ------------------------
with tab_patient:
    st.header("🧍 Informations patient (adulte en oncologie)")

    # Sélection programme patient
    st.markdown("### 📋 Programme d’injection")
    program_names = ["Aucun"] + list(libraries.get("programs", {}).keys())
    selected_prog = st.selectbox("Programme", program_names, index=0, key="prog_patient")
    if selected_prog != "Aucun":
        st.session_state["selected_program"] = selected_prog
        for key, val in libraries["programs"][selected_prog].items():
            config[key] = val
        st.info(f"Programme **{selected_prog}** chargé ✅")

    # Données patient
    col_w, col_h, col_birth = st.columns(3)
    with col_w: weight = st.number_input("Poids (kg)", min_value=20.0, max_value=200.0, value=70.0)
    with col_h: height = st.number_input("Taille (cm)", min_value=100.0, max_value=220.0, value=170.0)
    with col_birth: birth_year = st.number_input("Année de naissance", min_value=1900, max_value=datetime.now().year, value=datetime.now().year - 40)
    current_year = datetime.now().year
    age = current_year - birth_year
    imc = weight / ((height / 100) ** 2)

    kv = st.radio("kV du scanner", [80, 90, 100, 110, 120], index=4, horizontal=True)
    injection_modes = ["Portal", "Artériel"]
    if config.get("intermediate_enabled", False): injection_modes.append("Intermédiaire")
    injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True)

    if injection_mode == "Portal":
        base_time = config.get("portal_time", 30.0)
    elif injection_mode == "Artériel":
        base_time = config.get("arterial_time", 25.0)
    else:
        base_time = config.get("intermediate_time", 28.0)

    acquisition_start = calculate_acquisition_start(age, config)
    st.markdown(f"**Temps d’injection :** {base_time:.1f} s — **Début acquisition :** {acquisition_start:.1f} s")

    volume, bsa = calculate_volume(weight, height, kv, config["concentration_mg_ml"], imc, config["calc_mode"], config["charges"], config["volume_max_limit"])
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume, base_time, config["max_debit"])

    st.success(f"💧 Volume conseillé : {volume:.1f} mL — 🚀 Débit : {injection_rate:.1f} mL/s")
    if bsa: st.info(f"📏 IMC : {imc:.1f} | Surface corporelle : {bsa:.2f} m²")
    if time_adjusted:
        st.warning(f"⚠️ Temps ajusté à {injection_time:.1f}s (débit max {config['max_debit']} mL/s).")

# ------------------------
# Tutoriel
# ------------------------
with tab_tutorial:
    st.title("📘 Tutoriel — Mode d'emploi et principes cliniques")
    st.markdown("Bienvenue dans le tutoriel. Cette section explique **comment utiliser** la calculette et **pourquoi** chaque calcul est effectué.")
    st.header("🔧 Guide pas à pas — Utilisation")
    st.markdown("""
    1. **Patient** : saisissez poids, taille et année de naissance.
    2. **kV du scanner** : choisissez la valeur correspondant à votre machine.
    3. **Mode d’injection** : Portal / Artériel / Intermédiaire.
    4. **Paramètres** : vérifiez la concentration, le débit max et les temps.
    5. **Injection simultanée** : si activée, définissez la concentration cible.
    6. **Validation** : relisez les résultats (volume contraste, NaCl, débit).
    """)
    st.header("🧠 Explications techniques et cliniques")
    st.markdown("""
    - **Charge iodée** : dose proportionnelle au poids.
    - **Surface corporelle (BSA)** : dose selon m².
    - **IMC>30** : règle “Charge iodée sauf IMC>30 → Surface corporelle”.
    - **Débit** = volume / temps; ajusté si dépasse max.
    - **Injection simultanée** : dilution pour atteindre concentration cible.
    """)
    st.header("🔬 Bases — recommandations spécifiques en oncologie hépatique")
    st.markdown("""
    Objectif : standardiser le rehaussement hépatique.
    - Foie sain : ≥110 UH
    - Foie stéatosique : ≥120 UH
    ⚠️ Valeurs indicatives selon protocole local.
    """)
    st.header("🩺 Exemple de workflow clinique")
    st.markdown("""
    Patient 75 kg, 170 cm, kV=120, charge iodée 0.5, mode Portal, concentration 350 mg I/mL.
    Exemple volume : (75x0.5)/0.35 ≈ 107 mL
    """)

# ------------------------
# Footer
# ------------------------
st.markdown(f"""<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Calculette de dose de produit de contraste en oncologie adulte.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
</div>""", unsafe_allow_html=True)
