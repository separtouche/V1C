
# -*- coding: utf-8 -*-
"""
oncologie_ct_adulte.py
Calculette complète (une page) de dose de produit de contraste - Oncologie CT adulte
Usage : streamlit run oncologie_ct_adulte.py
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
    "volume_max_limit": 200.0,
    # NaCl specific params (user-scoped)
    "nacl_dilution_percent": 0,        # percentage of contrast volume to be NaCl dilution when simultaneous
    "rincage_volume_param": 35.0,      # rinse volume (mL)
    "rincage_rate_param": 3.0,         # rinse rate (mL/s)
    "super_user": "admin"
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
config_global = load_json_safe(CONFIG_FILE, default_config)
libraries = load_json_safe(LIB_FILE, {"programs": {}})
user_sessions = load_json_safe(USER_SESSIONS_FILE, {})

# Normalize user_sessions shape
for uid, data in list(user_sessions.items()):
    if not isinstance(data, dict):
        user_sessions[uid] = {
            "programs": {},
            "config": config_global.copy(),
            "email": None,
            "created": datetime.utcnow().isoformat()
        }
    else:
        if "programs" not in data:
            user_sessions[uid]["programs"] = {}
        if "config" not in data:
            user_sessions[uid]["config"] = config_global.copy()
        if "email" not in data:
            user_sessions[uid]["email"] = None
        if "created" not in data:
            user_sessions[uid]["created"] = datetime.utcnow().isoformat()

# ------------------------
# Fonctions métier
# ------------------------
def save_config_global(cfg):
    save_json_atomic(CONFIG_FILE, cfg)

def save_libraries(lib):
    save_json_atomic(LIB_FILE, lib)

def save_user_sessions(sessions):
    save_json_atomic(USER_SESSIONS_FILE, sessions)

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
    injection_rate = volume / injection_time if injection_time > 0 else 0.0
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
st.set_page_config(page_title="Calculette Contraste Oncologie CT adulte", page_icon="💉", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }
.small-note { font-size:0.82rem; color:#666; margin:4px 0; }
.center-muted { text-align:center; color:#666; font-size:0.9rem; }
.info-block { background:#F6F6F6; padding:8px 10px; border-radius:6px; }
</style>
""", unsafe_allow_html=True)

# ------------------------
# Session state
# ------------------------
if "accepted_legal" not in st.session_state:
    st.session_state["accepted_legal"] = False
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "user_config" not in st.session_state:
    st.session_state["user_config"] = config_global.copy()
if "selected_program" not in st.session_state:
    st.session_state["selected_program"] = None

SUPER_USER = config_global.get("super_user", "admin")

# ------------------------
# Helper functions for config persistence
# ------------------------
def get_cfg():
    return st.session_state.get("user_config", config_global.copy())

def set_cfg_and_persist(user_id, new_cfg):
    st.session_state["user_config"] = new_cfg.copy()
    if user_id not in user_sessions:
        user_sessions[user_id] = {"programs": {}, "config": new_cfg.copy(), "email": None, "created": datetime.utcnow().isoformat()}
    else:
        user_sessions[user_id]["config"] = new_cfg.copy()
    save_user_sessions(user_sessions)

# ------------------------
# Login / création identifiant
# ------------------------
# [Le code login complet, inchangé, doit être ici]

# ------------------------
# Header
# ------------------------
logo_path = "guerbet_logo.png"
if os.path.exists(logo_path):
    try:
        img_b64 = img_to_base64(logo_path)
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:8px; background:#124F7A; padding:8px; border-radius:8px">
            <img src="data:image/png;base64,{img_b64}" style="height:60px"/>
            <h2 style="color:white; margin:0;">Calculette de dose de produit de contraste — Oncologie CT adulte</h2>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.title("Calculette de dose de produit de contraste — Oncologie CT adulte")
else:
    st.title("Calculette de dose de produit de contraste — Oncologie CT adulte")

# ------------------------
# Tabs
# ------------------------
tab_patient, tab_params, tab_tutorial = st.tabs(["🧍 Patient", "⚙️ Paramètres", "📘 Tutoriel"])

# ------------------------
# Paramètres tab (détaillés)
# ------------------------
with tab_params:
    st.header("⚙️ Paramètres et Bibliothèque (personnelle)")
    user_id = st.session_state["user_id"]
    cfg = get_cfg()
    st.markdown(f"**👤 Identifiant connecté :** `{user_id}`")

    # ⚠️ Checkbox forcées activées et persistées
    cfg["auto_acquisition_by_age"] = True
    cfg["simultaneous_enabled"] = True
    st.checkbox(
        "Activer ajustement automatique du départ d'acquisition selon l'âge",
        value=True,
        key="param_auto_age",
        disabled=True
    )
    st.checkbox(
        "Activer l'injection simultanée",
        value=True,
        key="param_simultaneous",
        disabled=True
    )
    set_cfg_and_persist(user_id, cfg)

# ------------------------
# Patient tab
# ------------------------
with tab_patient:
    st.header("🧍 Informations patient")
    col_w, col_h, col_birth, col_prog = st.columns([1,1,1,1.2])
    
    with col_w:
        weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70)
        injection_mode = st.radio("Mode d’injection", ["Portal","Artériel","Intermédiaire"], horizontal=True)
        kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True)

    with col_h:
        height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170)
    with col_birth:
        current_year = datetime.now().year
        birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40)
    with col_prog:
        user_programs = user_sessions.get(user_id, {}).get("programs", {})
        prog_choice_patient = st.selectbox(
            "Programme",
            ["Sélection d'un programme"] + list(user_programs.keys()),
            index=0,
            label_visibility="collapsed"
        )
        if prog_choice_patient != "Sélection d'un programme":
            prog_conf = user_programs.get(prog_choice_patient, {})
            cfg = get_cfg()
            for key, val in prog_conf.items():
                cfg[key] = val
            set_cfg_and_persist(user_id, cfg)

    # Bloc fixe sous taille et naissance
    st.markdown(f"""
**🧮 Méthode utilisée :** {cfg.get('calc_mode','Charge iodée')}  
💊 **Charge iodée appliquée (kV 120) :** {cfg.get('charges', {}).get('120',0.45):.2f} g I/kg  
🕒 **Ajustement automatique du départ d'acquisition selon l'âge activé**  
💧 **Injection simultanée activée**
""")

    # Bloc sous la sélection de programme
    age = current_year - birth_year
    imc = weight / ((height/100)**2)
    if injection_mode == "Portal":
        base_time = float(cfg.get("portal_time",30.0))
    elif injection_mode == "Artériel":
        base_time = float(cfg.get("arterial_time",25.0))
    else:
        base_time = float(cfg.get("intermediate_time",28.0))

    acquisition_start = calculate_acquisition_start(age, cfg)
    concentration_used = int(cfg.get("concentration_mg_ml",350))
    st.markdown(f"""
Temps Intermédiaire (s) : {float(cfg.get('intermediate_time',28.0)):.2f}  
Temps Intermédiaire : {float(cfg.get('intermediate_time',28.0)):.0f} s  
Départ d'acquisition : {acquisition_start:.1f} s  
Concentration utilisée : {concentration_used} mg I/mL
""")

# ------------------------
# Tutoriel tab (référence CIRTACI)
# ------------------------
with tab_tutorial:
    st.title("📘 Tutoriel — Mode d'emploi et principes cliniques")
    st.markdown("Cette section explique **comment utiliser** la calculette et **pourquoi** chaque calcul est effectué. Le contenu peut être adapté localement selon protocole.")
    st.header("🔧 Guide pas à pas — Utilisation")
    st.markdown("""
    1. **Patient** : saisissez poids, taille et année de naissance.
    2. **Mode d'injection** : placé sous le poids.
    3. **kV du scanner** : placé sous le mode d'injection.
    4. **Paramètres** : activez l'injection simultanée et définissez la dilution NaCl si besoin.
    5. **Validation** : relisez les résultats (volume contraste, NaCl, débit).
    """)
    st.header("🔬 Références")
    st.markdown("Ce tutoriel se réfère aux recommandations du CIRTACI 5.3.0 (2020).")
    st.markdown(f"[Consulter le document officiel (CIRTACI 5.3.0 — 2020)](https://www.radiologie.fr/sites/www.radiologie.fr/files/medias/documents/CIRTACI%20Fiche%20Ge%CC%81ne%CC%81ralite%CC%81s%20VASCULAIRE_5_3_1.pdf)")

# ------------------------
# Footer with CIRTACI link
# ------------------------
st.markdown(f"""<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Calculette de dose de produit de contraste — Oncologie CT adulte.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
<br><br>
<a href="https://www.radiologie.fr/sites/www.radiologie.fr/files/medias/documents/CIRTACI%20Fiche%20Ge%CC%81ne%CC%81ralite%CC%81s%20VASCULAIRE_5_3_1.pdf" target="_blank" style="color:#0B67A9; text-decoration:underline;">Consulter le document CIRTACI 5.3.0 (2020)</a>
</div>""", unsafe_allow_html=True)
