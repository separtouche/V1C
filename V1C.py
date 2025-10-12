# -*- coding: utf-8 -*-
"""
Calculette complète (une page) de dose de produit de contraste - Oncologie adulte
Avec gestion de sessions utilisateurs indépendantes
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
USER_LIBS_DIR = "user_sessions"  # Répertoire pour sessions utilisateurs
LOG_FILE = "calc_audit.log"

os.makedirs(USER_LIBS_DIR, exist_ok=True)

# ------------------------
# Valeurs par défaut
# ------------------------
default_config = {
    "charges": {str(kv): val for kv, val in zip([80,90,100,110,120],[0.35,0.38,0.40,0.42,0.45])},
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
            st.warning(f"⚠️ Erreur lecture '{path}' — valeurs par défaut utilisées ({e})")
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

def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ------------------------
# Fonctions métier
# ------------------------
def calculate_bsa(weight, height):
    try:
        return math.sqrt((height * weight)/3600.0)
    except Exception:
        return None

def calculate_volume(weight, height, kv, concentration_mg_ml, imc, calc_mode, charges, volume_cap):
    kv_factors = {80:11,90:13,100:15,110:16.5,120:18.6}
    concentration_g_ml = concentration_mg_ml / 1000.0
    bsa = None
    try:
        if calc_mode=="Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc>=30):
            bsa = calculate_bsa(weight,height)
            factor = kv_factors.get(kv,15)
            volume = bsa * factor / concentration_g_ml
        else:
            charge_iodine = float(charges.get(str(kv),0.4))
            volume = weight * charge_iodine / concentration_g_ml
    except Exception:
        volume = 0.0
    volume = max(0.0,float(volume))
    if volume>volume_cap:
        volume = volume_cap
    return volume,bsa

def calculate_acquisition_start(age, cfg):
    if not cfg.get("auto_acquisition_by_age", True):
        return float(cfg.get("acquisition_start_param",70.0))
    if age<70:
        return float(cfg.get("acquisition_start_param",70.0))
    elif 70<=age<=90:
        return float(age)
    else:
        return 90.0

def adjust_injection_rate(volume,injection_time,max_debit):
    injection_time = float(injection_time) if injection_time>0 else 1.0
    injection_rate = volume/injection_time if injection_time>0 else 0.0
    time_adjusted=False
    if injection_rate>max_debit:
        injection_time=volume/max_debit
        injection_rate=max_debit
        time_adjusted=True
    return float(injection_rate),float(injection_time),bool(time_adjusted)

# ------------------------
# Initialisation Streamlit
# ------------------------
st.set_page_config(page_title="Calculette Contraste Oncologie adulte", page_icon="💉", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }
</style>
""", unsafe_allow_html=True)

if "accepted_legal" not in st.session_state:
    st.session_state["accepted_legal"]=False
if "user_id" not in st.session_state:
    st.session_state["user_id"]=None
if "config" not in st.session_state:
    st.session_state["config"]=default_config.copy()
if "libraries" not in st.session_state:
    st.session_state["libraries"]=load_json_safe(LIB_FILE, {"programs":{}})

# ------------------------
# Étape 1 : Acceptation + sélection session
# ------------------------
if not st.session_state["accepted_legal"]:
    st.markdown("### Mentions légales — acceptation requise")
    st.markdown("Avant utilisation, acceptez la mention légale. Résultats indicatifs à valider par un professionnel de santé.")
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")
    
    st.markdown("### Sélection / Création de session utilisateur")
    col_user_select, col_user_create = st.columns([1,1])
    with col_user_select:
        existing_users = [f.replace(".json","") for f in os.listdir(USER_LIBS_DIR) if f.endswith(".json")]
        selected_user = st.selectbox("Sélectionner un utilisateur existant", [""]+existing_users, key="user_select")
        if selected_user:
            st.session_state["user_id"]=selected_user
            user_libs_file=os.path.join(USER_LIBS_DIR,f"{selected_user}.json")
            st.session_state["user_libraries"]=load_json_safe(user_libs_file, {"programs":{}})
            st.success(f"Session '{selected_user}' chargée ✅")
    with col_user_create:
        new_user = st.text_input("Créer un nouvel identifiant utilisateur")
        if st.button("Créer session"):
            if new_user.strip():
                st.session_state["user_id"]=new_user.strip()
                user_libs_file=os.path.join(USER_LIBS_DIR,f"{new_user.strip()}.json")
                if not os.path.exists(user_libs_file):
                    save_json_atomic(user_libs_file, {"programs":{}})
                st.session_state["user_libraries"]=load_json_safe(user_libs_file, {"programs":{}})
                st.success(f"Session '{new_user.strip()}' créée ✅")
    if st.button("Continuer dans cette session"):
        if st.session_state["user_id"]:
            st.session_state["accepted_legal"]=True
            st.experimental_rerun()
        else:
            st.warning("Veuillez sélectionner ou créer une session utilisateur.")
    st.stop()

# ------------------------
# Chargement config et programmes
# ------------------------
config = st.session_state["config"]
libraries = st.session_state["libraries"]
user_libraries = st.session_state.get("user_libraries", {"programs":{}})

# ------------------------
# Header réduit
# ------------------------
logo_path="guerbet_logo.png"
if os.path.exists(logo_path):
    try:
        img_b64=img_to_base64(logo_path)
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
tab_patient, tab_params, tab_tutorial = st.tabs(["🧍 Patient","⚙️ Paramètres","📘 Tutoriel"])

# ------------------------
# Onglet Paramètres
# ------------------------
with tab_params:
    st.header("⚙️ Paramètres et Bibliothèque")
    config["simultaneous_enabled"]=st.checkbox("Activer l'injection simultanée", value=config.get("simultaneous_enabled",False))
    if config["simultaneous_enabled"]:
        config["target_concentration"]=st.number_input("Concentration cible (mg I/mL)", value=int(config.get("target_concentration",350)), min_value=200,max_value=500,step=10)
    
    st.subheader("📚 Bibliothèque de programmes utilisateur")
    program_choice = st.selectbox("Programme", ["Aucun"]+list(user_libraries.get("programs",{}).keys()), key="prog_params")
    if program_choice!="Aucun":
        prog_conf = user_libraries["programs"].get(program_choice,{})
        for k,v in prog_conf.items():
            config[k]=v
    new_prog_name = st.text_input("Nom du nouveau programme")
    if st.button("💾 Ajouter/Mise à jour programme"):
        if new_prog_name.strip():
            user_libraries["programs"][new_prog_name.strip()] = config.copy()
            user_libs_file=os.path.join(USER_LIBS_DIR,f"{st.session_state['user_id']}.json")
            save_json_atomic(user_libs_file,user_libraries)
            st.success(f"Programme '{new_prog_name.strip()}' ajouté/mis à jour ✅")
    if user_libraries.get("programs"):
        del_prog = st.selectbox("Supprimer un programme", [""]+list(user_libraries["programs"].keys()))
        if st.button("🗑 Supprimer programme"):
            if del_prog in user_libraries["programs"]:
                del user_libraries["programs"][del_prog]
                user_libs_file=os.path.join(USER_LIBS_DIR,f"{st.session_state['user_id']}.json")
                save_json_atomic(user_libs_file,user_libraries)
                st.success(f"Programme '{del_prog}' supprimé ✅")

# ------------------------
# Onglet Patient
# ------------------------
with tab_patient:
    st.header("🧍 Informations patient (adulte en oncologie)")
    col_w,col_h,col_birth,col_prog = st.columns([1,1,1,1.2])
    with col_w:
        weight=st.select_slider("Poids (kg)", options=list(range(20,201)), value=70, key="weight_patient")
    with col_h:
        height=st.select_slider("Taille (cm)", options=list(range(100,221)), value=170, key="height_patient")
    current_year=datetime.now().year
    with col_birth:
        birth_year=st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40, key="birth_patient")
    with col_prog:
        prog_choice_patient=st.selectbox("Programme", ["Sélection d'un programme"]+list(user_libraries.get("programs",{}).keys()), index=0,label_visibility="collapsed", key="prog_patient")
        if prog_choice_patient!="Sélection d'un programme":
            prog_conf=user_libraries["programs"].get(prog_choice_patient,{})
            for k,v in prog_conf.items(): config[k]=v

    # Calculs patient
    age=current_year-birth_year
    imc=weight/((height/100)**2)
    col_kv,col_mode_time=st.columns([1.2,2])
    with col_kv:
        kv_scanner=st.radio("kV du scanner",[80,90,100,110,120],index=4,horizontal=True,key="kv_patient")
    with col_mode_time:
        col_mode,col_times=st.columns([1.2,1])
        with col_mode:
            injection_modes=["Portal","Artériel"]
            if config.get("intermediate_enabled",False): injection_modes.append("Intermédiaire")
            injection_mode=st.radio("Mode d’injection", injection_modes,horizontal=True,key="mode_inj_patient")
        with col_times:
            if injection_mode=="Portal": base_time=float(config.get("portal_time",30.0))
            elif injection_mode=="Artériel": base_time=float(config.get("arterial_time",25.0))
            else: base_time=st.number_input("Temps Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0,max_value=120.0,step=1.0,key="intermediate_time_input")
            st.markdown(f"**Temps {injection_mode} :** {base_time:.0f} s")
            acquisition_start=calculate_acquisition_start(age,config)
            st.markdown(f"**Départ d'acquisition :** {acquisition_start:.1f} s")
            st.markdown(f"**Concentration utilisée :** {int(config.get('concentration_mg_ml',350))} mg I/mL")

    if weight<=0 or height<=0: st.error("Poids et taille doivent être >0"); st.stop()
    if float(config.get("concentration_mg_ml",0))<=0: st.error("La concentration doit être >0 mg I/mL"); st.stop()

    volume,bsa=calculate_volume(weight,height,kv_scanner,float(config.get("concentration_mg_ml",350)),imc,config.get("calc_mode","Charge iodée"),config.get("charges",{}),float(config.get("volume_max_limit",200.0)))
    injection_rate,injection_time,time_adjusted=adjust_injection_rate(volume,float(base_time),float(config.get("max_debit",6.0)))

    if config.get("simultaneous_enabled",False):
        target=float(config.get("target_concentration",350))
        current_conc=float(config.get("concentration_mg_ml",350))
        if target>current_conc:
            st.warning(f"La concentration cible ({target:.0f}) est supérieure à la concentration du flacon ({current_conc:.0f})")
            target=current_conc
        vol_contrast=volume*(target/current_conc) if current_conc>0 else volume
        vol_nacl_dilution=max(0.0,volume-vol_contrast)
        perc_contrast=(vol_contrast/volume*100) if volume>0 else 0
        perc_nacl_dilution=(vol_nacl_dilution/volume*100) if volume>0 else 0
        contrast_text=f"{int(round(vol_contrast))} mL ({int(round(perc_contrast))}%)"
        nacl_rincage_volume=float(config.get("rincage_volume",35.0))
        nacl_rincage_debit=max(0.1,injection_rate-float(config.get("rincage_delta_debit",0.5)))
        nacl_text=f"<div>Dilution : {int(round(vol_nacl_dilution))} mL ({int(round(perc_nacl_dilution))}%)</div>"
        nacl_text+=f"<div>Rinçage : {int(round(nacl_rincage_volume))} mL @ {injection_rate:.1f} mL/s</div>"
    else:
        vol_contrast=volume
        contrast_text=f"{int(round(vol_contrast))} mL"
        nacl_text=f"{int(round(config.get('rincage_volume',35.0)))} mL"

    col_contrast,col_nacl,col_rate=st.columns(3,gap="medium")
    with col_contrast:
        st.markdown(f"""<div style="background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;">
                         <h3>💧 Volume contraste conseillé</h3><h1 style="margin:0">{contrast_text}</h1>
                       </div>""",unsafe_allow_html=True)
    with col_nacl:
        st.markdown(f"""<div style="background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;">
                         <h3>💧 Volume NaCl conseillé</h3><h1 style="margin:0">{nacl_text}</h1>
                       </div>""",unsafe_allow_html=True)
    with col_rate:
        st.markdown(f"""<div style="background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;">
                         <h3>🚀 Débit conseillé</h3><h1 style="margin:0">{injection_rate:.1f} mL/s</h1>
                       </div>""",unsafe_allow_html=True)
    if time_adjusted:
        st.warning(f"⚠️ Temps d’injection ajusté à {injection_time:.1f}s pour respecter le débit maximal de {config.get('max_debit',6.0)} mL/s.")
    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))
    try:
        audit_log(f"calc:age={age},kv={kv_scanner},mode={injection_mode},vol={volume},vol_contrast={vol_contrast},rate={injection_rate:.2f}")
    except Exception:
        pass
    st.markdown("""<div style='background-color:#FCE8E6; color:#6B1A00; padding:10px; border-radius:8px; margin-top:15px; font-size:0.9rem;'>⚠️ <b>Avertissement :</b> Ce logiciel est un outil d’aide à la décision. Les résultats sont <b>indicatifs</b> et doivent être validés par un professionnel de santé. Destiné uniquement aux patients adultes en oncologie.</div>""",unsafe_allow_html=True)

# ------------------------
# Onglet Tutoriel
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
</div>""",unsafe_allow_html=True)
