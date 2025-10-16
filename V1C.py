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
    "nacl_dilution_percent": 0,
    "rincage_volume_param": 35.0,
    "rincage_rate_param": 3.0,
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

# ------------------------
# Fonctions principales
# ------------------------
def iodine_charge(weight, iodine_conc, dose_per_kg):
    total_dose = dose_per_kg * weight
    volume_ml = (total_dose * 1000) / iodine_conc
    return round(volume_ml, 1)

# ------------------------
# Interface principale
# ------------------------
st.set_page_config(page_title="V1C - Calcul de charge iodée", layout="centered")

st.title("📘 Calculateur de Charge Iodée - Scanner Oncologie Adulte")
st.divider()

config = load_json_safe(CONFIG_FILE, default_config)

tab1, tab2, tab3 = st.tabs(["🏥 Patient", "⚙️ Paramètres", "📊 Résultats"])

with tab1:
    st.subheader("Informations du patient")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Nom du patient")
        birth_year = st.number_input("Année de naissance", min_value=1900, max_value=2025, value=1980)
    with col2:
        height = st.number_input("Taille (cm)", min_value=30, max_value=250, value=170)
        weight = st.number_input("Poids (kg)", min_value=1.0, max_value=300.0, value=70.0)

    st.markdown("---")

    # ✅ Bloc ajouté sous "taille et naissance"
    st.markdown("🧮 **Méthode utilisée :** Charge iodée")
    st.markdown("💊 **Charge iodée appliquée (kV 120) :** 0.45 g I/kg")
    st.markdown("🕒 **Ajustement automatique du départ d'acquisition selon l'âge activé**")
    st.markdown("💧 **Injection simultanée activée**")

    st.markdown("---")

    # ✅ Bloc ajouté : Sélectionnez un programme
    st.subheader("🎯 Sélectionnez un programme")
    st.markdown("**Temps Intermédiaire (s) : 28,00**")
    st.markdown("**Temps Intermédiaire :** 28 s")
    st.markdown("**Départ d'acquisition :** 70.0 s")
    st.markdown("**Concentration utilisée :** 350 mg I/mL")

with tab2:
    st.subheader("⚙️ Paramètres techniques")

    col1, col2 = st.columns(2)
    with col1:
        conc = st.number_input("Concentration (mg I/mL)", min_value=100, max_value=400, value=config["concentration_mg_ml"])
        dose = st.number_input("Dose (g I/kg)", min_value=0.1, max_value=1.0, step=0.05, value=config["charges"]["120"])
    with col2:
        auto = st.checkbox("Activer départ acquisition automatique selon l'âge", value=config["auto_acquisition_by_age"])
        simult = st.checkbox("Activer injection simultanée", value=True)

    st.markdown("**Injection simultanée : activée**")
    st.markdown("**Départ d'acquisition automatique : activé**")

    if st.button("💾 Enregistrer les paramètres"):
        config["concentration_mg_ml"] = conc
        config["charges"]["120"] = dose
        config["auto_acquisition_by_age"] = auto
        config["simultaneous_enabled"] = simult
        save_json_atomic(CONFIG_FILE, config)
        st.success("Paramètres enregistrés ✅")

with tab3:
    st.subheader("📊 Résultats du calcul")

    iodine_conc = config["concentration_mg_ml"]
    dose_per_kg = config["charges"]["120"]
    volume = iodine_charge(weight, iodine_conc, dose_per_kg)

    st.markdown(f"💉 **Volume total à injecter :** {volume} mL")
    st.markdown(f"💊 **Concentration utilisée :** {iodine_conc} mg I/mL")
    st.markdown(f"🕒 **Départ d'acquisition :** {config['acquisition_start_param']} s")
    st.markdown(f"⏱️ **Temps intermédiaire :** {config['intermediate_time']} s")
    st.markdown(f"💧 **Injection simultanée :** {'activée' if config['simultaneous_enabled'] else 'désactivée'}")
    st.markdown(f"🧠 **Départ acquisition automatique :** {'activé' if config['auto_acquisition_by_age'] else 'désactivé'}")

