# -*- coding: utf-8 -*-
"""
Calculette complète (une page) de dose de produit de contraste - Oncologie adulte
Avec sessions isolées par utilisateur et restauration automatique
"""

import streamlit as st
import json
import os
import math
import base64
from datetime import datetime
import pandas as pd

# ------------------------
# Fichiers de logs
# ------------------------
LOG_FILE = "calc_audit.log"

# ------------------------
# Utils
# ------------------------
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

def calculate_bsa(weight, height):
    try:
        return math.sqrt((height * weight) / 3600.0)
    except:
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
    except:
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
# Config par défaut
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

default_libraries = {"programs": {}}

# ------------------------
# Streamlit UI init
# ------------------------
st.set_page_config(page_title="Calculette Contraste Oncologie adulte", page_icon="💉", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }
</style>
""", unsafe_allow_html=True)

# ------------------------
# Choix ou création de session
# ------------------------
st.header("💾 Sélection ou création de session utilisateur")
user_id = st.text_input("Identifiant utilisateur", help="Créez ou sélectionnez votre session")
if not user_id:
    st.warning("Veuillez saisir un identifiant pour continuer")
    st.stop()

safe_id = user_id.replace(" ", "_")
user_config_file = f"user_config_{safe_id}.json"
user_libs_file = f"user_libs_{safe_id}.json"

if "user_config" not in st.session_state:
    st.session_state["user_config"] = load_json_safe(user_config_file, default_config)
if "user_libraries" not in st.session_state:
    st.session_state["user_libraries"] = load_json_safe(user_libs_file, default_libraries)
if "accepted_legal" not in st.session_state:
    st.session_state["accepted_legal"] = False

config = st.session_state["user_config"]
libraries = st.session_state["user_libraries"]

# ------------------------
# Mentions légales
# ------------------------
if not st.session_state["accepted_legal"]:
    st.markdown("### Mentions légales — acceptation requise")
    st.markdown("Avant utilisation, acceptez la mention légale. Résultats indicatifs à valider par un professionnel de santé.")
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")
    if st.button("Accepter et continuer"):
        if accept:
            st.session_state["accepted_legal"] = True
        else:
            st.warning("Vous devez cocher la case pour accepter.")
    st.stop()

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
            <h2 style="color:white; margin:0;">Calculette de dose de produit de contraste — Oncologie adulte</h2>
        </div>
        """, unsafe_allow_html=True)
    except:
        st.title("Calculette de dose de produit de contraste — Oncologie adulte")
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
    config["simultaneous_enabled"] = st.checkbox("Activer l'injection simultanée", value=config.get("simultaneous_enabled", False))
    if config["simultaneous_enabled"]:
        config["target_concentration"] = st.number_input("Concentration cible (mg I/mL)", value=int(config.get("target_concentration", 350)), min_value=200, max_value=500, step=10)
    
    st.subheader("📚 Bibliothèque de programmes")
    # Ajouter un programme
    new_prog_name = st.text_input("Nom du nouveau programme")
    if st.button("💾 Ajouter/Mise à jour programme"):
        if new_prog_name.strip():
            libraries["programs"][new_prog_name.strip()] = config.copy()
            save_json_atomic(user_libs_file, libraries)
            st.success(f"Programme '{new_prog_name}' ajouté/mis à jour !")
    
    # Liste des programmes
    prog_choice = st.selectbox("Programme", ["Sélection d'un programme"] + list(libraries["programs"].keys()), key="prog_params")
    if prog_choice != "Sélection d'un programme":
        prog_conf = libraries["programs"].get(prog_choice, {})
        for key, val in prog_conf.items(): config[key] = val

    st.subheader("⚙️ Paramètres globaux")
    config["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)", [300, 320, 350, 370, 400], index=[300,320,350,370,400].index(int(config.get("concentration_mg_ml",350))))
    config["calc_mode"] = st.selectbox("Méthode de calcul", ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config.get("calc_mode","Charge iodée")))
    config["max_debit"] = st.number_input("Débit maximal autorisé (mL/s)", value=float(config.get("max_debit",6.0)), min_value=1.0, max_value=20.0, step=0.1)
    config["portal_time"] = st.number_input("Portal (s)", value=float(config.get("portal_time",30.0)), min_value=5.0, max_value=120.0, step=1.0)
    config["arterial_time"] = st.number_input("Artériel (s)", value=float(config.get("arterial_time",25.0)), min_value=5.0, max_value=120.0, step=1.0)
    config["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=bool(config.get("intermediate_enabled", False)))
    if config["intermediate_enabled"]:
        config["intermediate_time"] = st.number_input("Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0, max_value=120.0, step=1.0)
    config["rincage_volume"] = st.number_input("Volume rinçage (mL)", value=float(config.get("rincage_volume",35.0)), min_value=10.0, max_value=100.0, step=1.0)
    config["rincage_delta_debit"] = st.number_input("Δ débit NaCl vs contraste (mL/s)", value=float(config.get("rincage_delta_debit",0.5)), min_value=0.1, max_value=5.0, step=0.1)
    config["volume_max_limit"] = st.number_input("Plafond volume (mL) - seringue", value=float(config.get("volume_max_limit",200.0)), min_value=50.0, max_value=500.0, step=10.0)
    
    st.markdown("**Charges en iode par kV (g I/kg)**")
    df_charges = pd.DataFrame({
        "kV": [80, 90, 100, 110, 120],
        "Charge (g I/kg)": [float(config["charges"].get(str(kv),0.35)) for kv in [80,90,100,110,120]]
    })
    edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True)
    if st.button("💾 Sauvegarder les paramètres"):
        try:
            config["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _, row in edited_df.iterrows()}
            save_json_atomic(user_config_file, config)
            st.success("✅ Paramètres sauvegardés !")
        except Exception as e:
            st.error(f"Erreur lors de la sauvegarde : {e}")

# ------------------------
# Onglet Patient
# ------------------------
with tab_patient:
    st.header("🧍 Informations patient (adulte en oncologie)")
    col_w, col_h, col_birth, col_prog = st.columns([1,1,1,1.2])
    with col_w: weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70, key="weight_patient")
    with col_h: height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170, key="height_patient")
    current_year = datetime.now().year
    with col_birth: birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40, key="birth_patient")
    with col_prog:
        prog_choice_patient = st.selectbox("Programme", ["Sélection d'un programme"]+list(libraries.get("programs", {}).keys()), index=0, label_visibility="collapsed", key="prog_patient")
        if prog_choice_patient != "Sélection d'un programme":
            prog_conf = libraries["programs"].get(prog_choice_patient, {})
            for key, val in prog_conf.items(): config[key] = val

    # Calculs patient
    age = current_year - birth_year
    imc = weight / ((height / 100)**2)
    
    col_kv, col_mode_time = st.columns([1.2,2])
    with col_kv: kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True, key="kv_patient")
    with col_mode_time:
        col_mode, col_times = st.columns([1.2,1])
        with col_mode:
            injection_modes = ["Portal","Artériel"]
            if config.get("intermediate_enabled", False): injection_modes.append("Intermédiaire")
            injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True, key="mode_inj_patient")
        with col_times:
            if injection_mode=="Portal": base_time=float(config.get("portal_time",30.0))
            elif injection_mode=="Artériel": base_time=float(config.get("arterial_time",25.0))
            else: base_time=st.number_input("Temps Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0, max_value=120.0, step=1.0, key="intermediate_time_input")
            st.markdown(f"**Temps {injection_mode} :** {base_time:.0f} s")
            acquisition_start = calculate_acquisition_start(age, config)
            st.markdown(f"**Départ d'acquisition :** {acquisition_start:.1f} s")
            st.markdown(f"**Concentration utilisée :** {int(config.get('concentration_mg_ml',350))} mg I/mL")

    if weight<=0 or height<=0: st.error("Poids et taille doivent être >0"); st.stop()
    if float(config.get("concentration_mg_ml",0))<=0: st.error("La concentration doit être >0 mg I/mL"); st.stop()

    volume, bsa = calculate_volume(weight, height, kv_scanner, float(config.get("concentration_mg_ml",350)), imc, config.get("calc_mode","Charge iodée"), config.get("charges",{}), float(config.get("volume_max_limit",200.0)))
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume, float(base_time), float(config.get("max_debit",6.0)))

    if config.get("simultaneous_enabled",False):
        target = float(config.get("target_concentration",350))
        current_conc = float(config.get("concentration_mg_ml",350))
        if target > current_conc:
            st.warning(f"La concentration cible ({target:.0f}) est supérieure à la concentration du flacon ({current_conc:.0f})")
            target = current_conc
        vol_contrast = volume*(target/current_conc) if current_conc>0 else volume
        vol_nacl_dilution = max(0.0, volume-vol_contrast)
        perc_contrast = (vol_contrast/volume*100) if volume>0 else 0
        perc_nacl_dilution = (vol_nacl_dilution/volume*100) if volume>0 else 0
        contrast_text=f"{int(round(vol_contrast))} mL ({int(round(perc_contrast))}%)"
        nacl_rincage_volume=float(config.get("rincage_volume",35.0))
        nacl_rincage_debit=max(0.1,injection_rate-float(config.get("rincage_delta_debit",0.5)))
        nacl_text=f"<div class='sub-item-large'>Dilution : {int(round(vol_nacl_dilution))} mL ({int(round(perc_nacl_dilution))}%)</div>"
        nacl_text+=f"<div class='sub-item-large'>Rinçage : {int(round(nacl_rincage_volume))} mL @ {injection_rate:.1f} mL/s</div>"
    else:
        vol_contrast = volume
        contrast_text = f"{int(round(vol_contrast))} mL"
        nacl_text = f"{int(round(config.get('rincage_volume',35.0)))} mL"

    col_contrast, col_nacl, col_rate = st.columns(3, gap="medium")
    with col_contrast:
        st.markdown(f"""<div style="background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;">
                         <h3>💧 Volume contraste conseillé</h3><h1 style="margin:0">{contrast_text}</h1></div>""", unsafe_allow_html=True)
    with col_nacl:
        st.markdown(f"""<div style="background:#F5F5F5;padding:12px;border-radius:10px;text-align:center;">
                         <h3>💦 Rinçage / dilution</h3>{nacl_text}</div>""", unsafe_allow_html=True)
    with col_rate:
        st.markdown(f"""<div style="background:#FFF4E5;padding:12px;border-radius:10px;text-align:center;">
                         <h3>🚀 Débit injection</h3><h1 style="margin:0">{injection_rate:.1f} mL/s</h1>
                         <p>{'⚠️ Débit ajusté pour respecter le max autorisé' if time_adjusted else ''}</p>
                         <p>Durée : {injection_time:.1f} s</p></div>""", unsafe_allow_html=True)

# ------------------------
# Onglet Tutoriel
# ------------------------
with tab_tutorial:
    st.header("📘 Tutoriel / Aide")
    st.markdown("""
- **Patient** : saisissez vos données et sélectionnez votre programme.
- **Paramètres** : gérez les paramètres globaux et votre bibliothèque de programmes.
- **Injection simultanée** : si activée, le volume de contraste est ajusté pour obtenir la concentration cible, le reste étant dilué par NaCl.
- **Rinçage** : toujours ajouté en volume et débit configurables.
- **Validation** : résultats indicatifs, à valider par un professionnel de santé.
""")
