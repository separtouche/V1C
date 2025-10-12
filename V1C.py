# -*- coding: utf-8 -*-
"""
Calculette complète de dose de produit de contraste - Oncologie
Version optimisée et structurée (Streamlit)
Volumes affichés en entier
Usage : streamlit run calculatrice_contraste_oncologie.py
"""

import streamlit as st
import json, os, math, base64
from datetime import datetime
import pandas as pd

# ------------------------
# Fichiers de config
# ------------------------
CONFIG_FILE = "iodine_config.json"
LIB_FILE = "libraries.json"
LOG_FILE = "calc_audit.log"

# ------------------------
# Valeurs par défaut
# ------------------------
def default_config():
    return {
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
            with open(path,"r",encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"⚠️ Erreur de lecture '{path}' — valeurs par défaut utilisées ({e})")
            return default()
    return default()

def save_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(data,f,indent=4,ensure_ascii=False)
    os.replace(tmp, path)

def audit_log(msg):
    try:
        ts = datetime.utcnow().isoformat()
        with open(LOG_FILE,"a",encoding="utf-8") as f:
            f.write(f"{ts} - {msg}\n")
    except Exception:
        pass

# ------------------------
# Fonctions métier
# ------------------------
def calculate_bsa(weight, height):
    try:
        if weight<=0 or height<=0: return None
        return math.sqrt((height*weight)/3600.0)
    except Exception:
        return None

def calculate_volume(weight, height, kv, concentration_mg_ml, imc, calc_mode, charges, volume_cap):
    kv_factors={80:11,90:13,100:15,110:16.5,120:18.6}
    concentration_g_ml = max(concentration_mg_ml,1)/1000.0
    bsa=None
    try:
        if calc_mode=="Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc>=30):
            bsa=calculate_bsa(weight,height)
            factor=kv_factors.get(kv,15)
            volume = bsa*factor/concentration_g_ml if bsa else 0.0
        else:
            charge_iodine=float(charges.get(str(kv),0.4))
            volume = weight*charge_iodine/concentration_g_ml
    except Exception:
        volume=0.0
    volume=max(0.0,min(volume,volume_cap))
    return volume,bsa

def calculate_acquisition_start(age,cfg):
    if not cfg.get("auto_acquisition_by_age",True):
        return float(cfg.get("acquisition_start_param",70.0))
    if age<70: return float(cfg.get("acquisition_start_param",70.0))
    elif 70<=age<=90: return float(age)
    else: return 90.0

def adjust_injection_rate(volume, injection_time, max_debit):
    injection_time = float(injection_time) if injection_time>0 else 1.0
    rate = volume/injection_time if injection_time>0 else 0.0
    time_adjusted=False
    if rate>max_debit:
        injection_time=volume/max_debit
        rate=max_debit
        time_adjusted=True
    return rate, injection_time, time_adjusted

def img_to_base64(path):
    try:
        with open(path,"rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None

# ------------------------
# Charger config & libs
# ------------------------
config = load_json_safe(CONFIG_FILE, default_config)
libraries = load_json_safe(LIB_FILE, lambda:{"programs":{}})
if "programs" not in libraries: libraries["programs"]={}

# ------------------------
# Streamlit UI
# ------------------------
st.set_page_config(page_title="Calculette Contraste Oncologie", page_icon="💉", layout="wide")

# Header logo
logo_path="guerbet_logo.png"
if os.path.exists(logo_path):
    img_b64=img_to_base64(logo_path)
    if img_b64:
        st.markdown(f"""
        <div style='display:flex;align-items:center;gap:12px;background:#124F7A;padding:12px;border-radius:10px'>
        <img src='data:image/png;base64,{img_b64}' style='height:80px'/>
        <h1 style='color:white;margin:0;'>Calculette de dose de produit de contraste — Oncologie</h1>
        </div>
        """,unsafe_allow_html=True)
    else:
        st.title("Calculette de dose de produit de contraste — Oncologie")
else:
    st.title("Calculette de dose de produit de contraste — Oncologie")

# Session_state
if "accepted_legal" not in st.session_state: st.session_state["accepted_legal"]=False
if "selected_program" not in st.session_state: st.session_state["selected_program"]=None

# Mentions légales
if not st.session_state["accepted_legal"]:
    st.markdown("### Mentions légales — acceptation requise")
    st.markdown(
        "Avant d'utiliser cet outil, vous devez accepter les mentions légales. "
        "Les données et résultats sont à titre indicatif et doivent être validés par un professionnel de santé."
    )
    accept = st.checkbox("✅ J’accepte les mentions légales.")
    if st.button("Accepter et continuer"):
        if accept: st.session_state["accepted_legal"]=True
        else: st.warning("Cochez la case pour accepter.")
    st.stop()

# ------------------------
# Onglets
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

    st.subheader("📚 Bibliothèque de programmes")
    program_choice=st.selectbox("Programme", ["Aucun"] + list(libraries.get("programs",{}).keys()))
    if program_choice!="Aucun":
        prog_conf=libraries["programs"].get(program_choice,{})
        for key,val in prog_conf.items(): config[key]=val

    new_prog_name=st.text_input("Nom du nouveau programme")
    if st.button("💾 Ajouter/Mise à jour programme"):
        if new_prog_name.strip():
            to_save={k: config[k] for k in config}
            libraries["programs"][new_prog_name.strip()]=to_save
            try:
                save_json_atomic(LIB_FILE,libraries)
                st.success(f"Programme '{new_prog_name}' ajouté/mis à jour !")
            except Exception as e: st.error(f"Erreur sauvegarde bibliothèque : {e}")

    if libraries.get("programs"):
        del_prog=st.selectbox("Supprimer un programme", [""] + list(libraries["programs"].keys()))
        if st.button("🗑 Supprimer programme"):
            if del_prog and del_prog in libraries["programs"]:
                del libraries["programs"][del_prog]
                save_json_atomic(LIB_FILE,libraries)
                st.success(f"Programme '{del_prog}' supprimé !")
            else: st.error("Programme introuvable.")

    st.subheader("⚙️ Paramètres globaux")
    config["concentration_mg_ml"]=st.selectbox("Concentration (mg I/mL)", [300,320,350,370,400], index=[300,320,350,370,400].index(int(config.get("concentration_mg_ml",350))))
    config["calc_mode"]=st.selectbox("Méthode de calcul", ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config.get("calc_mode","Charge iodée")))
    config["max_debit"]=st.number_input("Débit maximal autorisé (mL/s)", value=float(config.get("max_debit",6.0)), min_value=1.0,max_value=20.0,step=0.1)
    config["portal_time"]=st.number_input("Portal (s)", value=float(config.get("portal_time",30.0)), min_value=5.0,max_value=120.0,step=1.0)
    config["arterial_time"]=st.number_input("Artériel (s)", value=float(config.get("arterial_time",25.0)), min_value=5.0,max_value=120.0,step=1.0)
    config["intermediate_enabled"]=st.checkbox("Activer temps intermédiaire", value=bool(config.get("intermediate_enabled",False)))
    if config["intermediate_enabled"]:
        config["intermediate_time"]=st.number_input("Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0,max_value=120.0,step=1.0)
    config["rincage_volume"]=st.number_input("Volume rinçage (mL)", value=float(config.get("rincage_volume",35.0)), min_value=10.0,max_value=100.0,step=1.0)
    config["rincage_delta_debit"]=st.number_input("Δ débit NaCl vs contraste (mL/s)", value=float(config.get("rincage_delta_debit",0.5)), min_value=0.1,max_value=5.0,step=0.1)
    config["volume_max_limit"]=st.number_input("Plafond volume (mL) - seringue", value=float(config.get("volume_max_limit",200.0)), min_value=50.0,max_value=500.0,step=10.0)

    st.markdown("**Charges en iode par kV (g I/kg)**")
    df_charges=pd.DataFrame({
        "kV":[80,90,100,110,120],
        "Charge (g I/kg)":[float(config["charges"].get(str(kv),0.35)) for kv in [80,90,100,110,120]]
    })
    edited_df=st.data_editor(df_charges, num_rows="fixed", use_container_width=True)
    if st.button("💾 Sauvegarder les paramètres"):
        try:
            config["charges"]={str(int(row.kV)): float(row["Charge (g I/kg)"]) for _,row in edited_df.iterrows()}
            save_json_atomic(CONFIG_FILE,config)
            st.success("✅ Paramètres sauvegardés !")
        except Exception as e: st.error(f"Erreur lors de la sauvegarde : {e}")

# ------------------------
# Onglet Patient
# ------------------------
with tab_patient:
    st.header("🧍 Informations patient (adulte en oncologie)")
    col_w,col_h,col_birth=st.columns([1,1,1])
    with col_w: weight=st.select_slider("Poids (kg)", options=list(range(20,201)), value=70)
    with col_h: height=st.select_slider("Taille (cm)", options=list(range(100,221)), value=170)
    with col_birth:
        current_year=datetime.now().year
        birth_year=st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40)
    age=current_year-birth_year
    imc=weight/((height/100)**2)

    col_kv,col_mode_time=st.columns([1.2,2])
    with col_kv: kv_scanner=st.radio("kV du scanner",[80,90,100,110,120], index=4,horizontal=True)
    with col_mode_time:
        col_mode,col_times=st.columns([1.2,1])
        with col_mode:
            injection_modes=["Portal","Artériel"]
            if config.get("intermediate_enabled",False): injection_modes.append("Intermédiaire")
            injection_mode=st.radio("Mode d’injection",injection_modes,horizontal=True)
        with col_times:
            if injection_mode=="Portal": base_time=float(config.get("portal_time",30.0))
            elif injection_mode=="Artériel": base_time=float(config.get("arterial_time",25.0))
            else: base_time=st.number_input("Temps Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0,max_value=120.0,step=1.0)
            st.markdown(f"**Temps {injection_mode} :** {base_time:.0f} s")
            acquisition_start=calculate_acquisition_start(age,config)
            st.markdown(f"**Départ d'acquisition :** {acquisition_start:.1f} s")
            st.markdown(f"**Concentration utilisée :** {int(config.get('concentration_mg_ml',350))} mg I/mL")

    volume,bsa=calculate_volume(weight,height,kv_scanner,float(config.get("concentration_mg_ml",350)),imc,config.get("calc_mode","Charge iodée"),config.get("charges",{}),float(config.get("volume_max_limit",200.0)))
    injection_rate,injection_time,time_adjusted=adjust_injection_rate(volume,float(base_time),float(config.get("max_debit",6.0)))

    # --- Arrondir volumes ---
    if config.get("simultaneous_enabled",False):
        target=float(config.get("target_concentration",350))
        current_conc=float(config.get("concentration_mg_ml",350))
        if target>current_conc: target=current_conc
        vol_contrast=volume*(target/current_conc) if current_conc>0 else volume
        vol_nacl=max(0.0,volume-vol_contrast)
        perc_contrast=(vol_contrast/volume*100) if volume>0 else 0
        perc_nacl=(vol_nacl/volume*100) if volume>0 else 0
        vol_contrast_rounded=int(round(vol_contrast))
        vol_nacl_rounded=int(round(vol_nacl))
        nacl_rincage_volume_rounded=int(round(float(config.get("rincage_volume",35.0))))
        nacl_rincage_debit=max(0.1,injection_rate-float(config.get("rincage_delta_debit",0.5)))
        contrast_text=f"{vol_contrast_rounded} mL ({int(perc_contrast)}%)"
        nacl_text=f"<div class='sub-item-large'>Dilution : {vol_nacl_rounded} mL ({int(perc_nacl)}%)</div>"
        nacl_text+=f"<div class='sub-item-large'>Rinçage : {nacl_rincage_volume_rounded} mL @ {nacl_rincage_debit:.1f} mL/s</div>"
    else:
        vol_contrast_rounded=int(round(volume))
        contrast_text=f"{vol_contrast_rounded} mL"
        nacl_text=f"{int(config.get('rincage_volume',35.0))} mL"

    col_contrast,col_nacl,col_rate=st.columns(3,gap="medium")
    with col_contrast: st.markdown(f"<div style='background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;'><h3>💧 Volume contraste conseillé</h3><h1 style='margin:0'>{contrast_text}</h1></div>",unsafe_allow_html=True)
    with col_nacl: st.markdown(f"<div style='background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;'><h3>💧 Volume NaCl conseillé</h3><h1 style='margin:0'>{nacl_text}</h1></div>",unsafe_allow_html=True)
    with col_rate: st.markdown(f"<div style='background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;'><h3>🚀 Débit conseillé</h3><h1 style='margin:0'>{injection_rate:.1f} mL/s</h1></div>",unsafe_allow_html=True)

    if time_adjusted: st.warning(f"⚠️ Temps d’injection ajusté à {injection_time:.1f}s pour respecter débit max {config.get('max_debit',6.0)} mL/s.")
    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))
    try: audit_log(f"calc:age={age},kv={kv_scanner},mode={injection_mode},vol={volume:.1f},vol_contrast={vol_contrast:.1f},rate={injection_rate:.2f}")
    except Exception: pass

# ------------------------
# Onglet Tutoriel
# ------------------------
with tab_tutorial:
    st.title("📘 Tutoriel — Mode d'emploi et principes cliniques")
    st.markdown("Bienvenue dans le tutoriel. Cette section explique **comment utiliser** la calculette et **pourquoi** chaque calcul est effectué.")

    st.header("🔧 Guide pas à pas — Utilisation")
    st.markdown("""
    1. Saisir poids, taille, année de naissance.
    2. Choisir kV du scanner.
    3. Sélectionner mode d’injection (Portal/Artériel/Intermédiaire).
    4. Vérifier concentration produit, débit max, temps.
    5. Injection simultanée : définir concentration cible pour dilution.
    6. Vérifier volumes et débit proposés (indicatif).
    """)

    st.header("🧠 Explications techniques")
    st.markdown("""
    - Charge iodée (g I/kg) : dose proportionnelle au poids.
    - Surface corporelle (BSA) : dose selon m².
    - IMC>30 : switch automatique sur BSA si configuré.
    - Débit = volume / temps; ajusté si > max.
    - Injection simultanée : dilution contraste/NaCl.
    """)

# ------------------------
# Footer
# ------------------------
st.markdown(f"""
<div style='text-align:center;margin-top:20px;font-size:0.8rem;color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Calculette dose contraste — usage adulte<br>
<div style='display:inline-block;background-color:#FCE8B2;border:1px solid #F5B800;padding:8px 15px;border-radius:10px;color:#5A4500;font-weight:600;margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
</div>
""",unsafe_allow_html=True)
