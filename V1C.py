# -*- coding: utf-8 -*-
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
    """Ajoute une ligne d'audit (anonymisé) localement."""
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
def save_config(cfg):
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
st.set_page_config(page_title="Calculette Contraste Oncologie adulte", page_icon="💉", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }
</style>
""", unsafe_allow_html=True)

if "accepted_legal" not in st.session_state:
    st.session_state["accepted_legal"] = False
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "selected_program" not in st.session_state:
    st.session_state["selected_program"] = None

# ------------------------
# Page d'accueil : Mentions légales + session utilisateur
# ------------------------
if not st.session_state["accepted_legal"] or st.session_state["user_id"] is None:
    st.markdown("### ⚠️ Mentions légales — acceptation requise")
    st.markdown("Avant utilisation, acceptez la mention légale et créez ou entrez votre identifiant utilisateur. Résultats indicatifs à valider par un professionnel de santé.")
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")
    
    # NOTE: pour respecter la confidentialité des identifiants, on **n'affiche pas** la liste complète ici.
    # L'utilisateur peut soit entrer un identifiant existant (s'il le connaît), soit en créer un nouveau.
    existing_id_input = st.text_input("Entrez un identifiant existant (si vous le connaissez)", key="existing_id_input")
    new_user_id = st.text_input("Ou créez un nouvel identifiant", key="new_id_input")
    
    if st.button("Entrer dans la session"):
        if not accept:
            st.warning("Vous devez accepter les mentions légales.")
        else:
            chosen_id = new_user_id.strip() if new_user_id.strip() else existing_id_input.strip()
            if not chosen_id:
                st.warning("Veuillez saisir ou entrer un identifiant.")
            else:
                st.session_state["accepted_legal"] = True
                st.session_state["user_id"] = chosen_id
                # Si nouvel identifiant — création et enregistrement automatiques (snapshot des paramètres)
                if chosen_id not in user_sessions:
                    ts = datetime.utcnow().isoformat()
                    user_sessions[chosen_id] = {
                        "programs": {},  # programmes propres à l'identifiant
                        "params": config.copy(),  # snapshot des paramètres au moment de la création
                        "created": ts,
                        "last_selected_program": None
                    }
                    save_user_sessions(user_sessions)
                else:
                    # Mettre à jour le snapshot 'params' si absent (optionnel)
                    if "params" not in user_sessions[chosen_id]:
                        user_sessions[chosen_id]["params"] = config.copy()
                        save_user_sessions(user_sessions)
    st.stop()  # bloque la suite jusqu'à validation

# ------------------------
# Header réduit
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
    except Exception:
        st.title("Calculette de dose de produit de contraste — Oncologie adulte")
else:
    st.title("Calculette de dose de produit de contraste — Oncologie adulte")

# ------------------------
# Tabs
# ------------------------
tab_patient, tab_params, tab_tutorial = st.tabs(["🧍 Patient", "⚙️ Paramètres", "📘 Tutoriel"])

# ------------------------
# Onglet Paramètres (modifié pour gestion sessions + programmes personnels)
# ------------------------
with tab_params:
    st.header("⚙️ Paramètres et Bibliothèque")
    user_id = st.session_state["user_id"]
    # Charger snapshot des paramètres si existant pour affichage personnel
    user_params = user_sessions.get(user_id, {}).get("params", config.copy())
    # Afficher / modifier les paramètres (affecte le config global, mais on sauvegarde snapshot perso)
    config["simultaneous_enabled"] = st.checkbox("Activer l'injection simultanée", value=config.get("simultaneous_enabled", False))
    if config["simultaneous_enabled"]:
        config["target_concentration"] = st.number_input("Concentration cible (mg I/mL)", value=int(config.get("target_concentration", 350)), min_value=200, max_value=500, step=10)
    st.subheader("📚 Bibliothèque de programmes")
    # Choix de portée : programme global (bibliothèque) vs programmes personnels
    prog_scope = st.radio("Portée du programme", ["Personnel", "Global"], index=0, horizontal=True)
    if prog_scope == "Personnel":
        personal_programs = user_sessions.get(user_id, {}).get("programs", {})
        program_choice = st.selectbox("Programme (Personnel)", ["Aucun"] + list(personal_programs.keys()), key="prog_params_personal")
        if program_choice != "Aucun":
            prog_conf = personal_programs.get(program_choice, {})
            for key, val in prog_conf.items():
                config[key] = val
    else:
        program_choice = st.selectbox("Programme (Global)", ["Aucun"] + list(libraries.get("programs", {}).keys()), key="prog_params_global")
        if program_choice != "Aucun":
            prog_conf = libraries["programs"].get(program_choice, {})
            for key, val in prog_conf.items():
                config[key] = val

    new_prog_name = st.text_input("Nom du nouveau programme (sera enregistré dans vos programmes personnels)")
    if st.button("💾 Ajouter/Mise à jour programme"):
        if new_prog_name.strip():
            to_save = {k: config[k] for k in config}
            # Enregistrer dans les programmes personnels de l'utilisateur (indépendants)
            if user_id not in user_sessions:
                user_sessions[user_id] = {"programs": {}, "params": config.copy(), "created": datetime.utcnow().isoformat()}
            user_sessions[user_id].setdefault("programs", {})[new_prog_name.strip()] = to_save
            # mettre à jour snapshot params également
            user_sessions[user_id]["params"] = config.copy()
            save_user_sessions(user_sessions)
            st.success(f"Programme personnel '{new_prog_name}' ajouté/mis à jour pour l'identifiant '{user_id}' !")
        else:
            st.warning("Donnez un nom au programme.")

    # Suppression de programmes : proposer suppression pour programmes personnels (conforme à confidentialité)
    st.markdown("**Gérer mes programmes personnels**")
    personal_prog_list = list(user_sessions.get(user_id, {}).get("programs", {}).keys())
    if personal_prog_list:
        del_prog_personal = st.selectbox("Supprimer un programme personnel", [""] + personal_prog_list, key="del_prog_personal")
        if st.button("🗑 Supprimer programme (Personnel)"):
            if del_prog_personal and del_prog_personal in user_sessions[user_id].get("programs", {}):
                del user_sessions[user_id]["programs"][del_prog_personal]
                save_user_sessions(user_sessions)
                st.success(f"Programme personnel '{del_prog_personal}' supprimé pour l'identifiant '{user_id}'.")
            else:
                st.error("Programme introuvable.")
    else:
        st.info("Vous n'avez pas encore de programmes personnels enregistrés.")

    # Conserver la gestion globale des programmes (lecture/écriture) pour l'administrateur uniquement
    st.markdown("---")
    st.subheader("Paramètres globaux")
    config["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)", [300, 320, 350, 370, 400], index=[300, 320, 350, 370, 400].index(int(config.get("concentration_mg_ml", 350))))
    config["calc_mode"] = st.selectbox("Méthode de calcul", ["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"].index(config.get("calc_mode", "Charge iodée")))
    config["max_debit"] = st.number_input("Débit maximal autorisé (mL/s)", value=float(config.get("max_debit", 6.0)), min_value=1.0, max_value=20.0, step=0.1)
    config["portal_time"] = st.number_input("Portal (s)", value=float(config.get("portal_time", 30.0)), min_value=5.0, max_value=120.0, step=1.0)
    config["arterial_time"] = st.number_input("Artériel (s)", value=float(config.get("arterial_time", 25.0)), min_value=5.0, max_value=120.0, step=1.0)
    config["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=bool(config.get("intermediate_enabled", False)))
    if config["intermediate_enabled"]:
        config["intermediate_time"] = st.number_input("Intermédiaire (s)", value=float(config.get("intermediate_time", 28.0)), min_value=5.0, max_value=120.0, step=1.0)
    config["rincage_volume"] = st.number_input("Volume rinçage (mL)", value=float(config.get("rincage_volume", 35.0)), min_value=10.0, max_value=100.0, step=1.0)
    config["rincage_delta_debit"] = st.number_input("Δ débit NaCl vs contraste (mL/s)", value=float(config.get("rincage_delta_debit", 0.5)), min_value=0.1, max_value=5.0, step=0.1)
    config["volume_max_limit"] = st.number_input("Plafond volume (mL) - seringue", value=float(config.get("volume_max_limit", 200.0)), min_value=50.0, max_value=500.0, step=10.0)

    st.markdown("**Charges en iode par kV (g I/kg)**")
    df_charges = pd.DataFrame({
        "kV": [80, 90, 100, 110, 120],
        "Charge (g I/kg)": [float(config["charges"].get(str(kv), 0.35)) for kv in [80, 90, 100, 110, 120]]
    })
    edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True)
    if st.button("💾 Sauvegarder les paramètres"):
        try:
            config["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _, row in edited_df.iterrows()}
            save_config(config)
            # mettre à jour snapshot params de l'utilisateur (indépendant)
            if user_id in user_sessions:
                user_sessions[user_id]["params"] = config.copy()
                save_user_sessions(user_sessions)
            st.success("✅ Paramètres sauvegardés !")
        except Exception as e:
            st.error(f"Erreur lors de la sauvegarde : {e}")

    # ------------------------
    # Gestion des sessions (déplacée ici)
    # ------------------------
    st.markdown("---")
    st.subheader("🗂 Gestion des sessions / identifiants")
    st.markdown("Les identifiants sont indépendants. Vos programmes et paramètres personnels ne sont accessibles qu'avec votre identifiant.")
    all_user_ids = list(user_sessions.keys())

    # Option suppression : seul 'admin' peut gérer/supprimer d'autres identifiants.
    if user_id == "admin":
        st.markdown("**Admin : suppression d'autres identifiants**")
        delete_id_admin = st.selectbox("Supprimer un autre identifiant", [""] + [uid for uid in all_user_ids if uid != user_id], key="del_id_admin")
        if st.button("🗑 Supprimer identifiant (admin)"):
            if delete_id_admin:
                if delete_id_admin in user_sessions:
                    del user_sessions[delete_id_admin]
                    save_user_sessions(user_sessions)
                    st.success(f"Identifiant '{delete_id_admin}' supprimé.")
                else:
                    st.error("Identifiant introuvable.")
    else:
        st.info("Seul l'administrateur (identifiant 'admin') peut supprimer d'autres identifiants.")
        # Permettre à l'utilisateur de supprimer ses **anciens** identifiants s'il en a (liste filtrée)
        st.markdown("**Supprimer votre identifiant**")
        st.markdown("⚠️ Suppression de votre identifiant supprimera vos programmes et paramètres personnels. Cette action est irréversible.")
        if st.button("🗑 Supprimer MON identifiant"):
            # On n'autorise pas la suppression si c'est la session active (pour éviter incohérences); proposer plutôt de supprimer puis réinitialiser l'app
            try:
                # Supprimer l'identifiant puis réinitialiser la session côté UI
                if user_id in user_sessions:
                    del user_sessions[user_id]
                    save_user_sessions(user_sessions)
                st.session_state["accepted_legal"] = False
                st.session_state["user_id"] = None
                st.success("Votre identifiant a été supprimé. Vous avez été déconnecté.")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Erreur suppression identifiant : {e}")

# ------------------------
# Onglet Patient (corrigé complet)
# ------------------------
with tab_patient:
    st.header("🧍 Informations patient (adulte en oncologie)")
    col_w, col_h, col_birth, col_prog = st.columns([1,1,1,1.2])
    with col_w:
        weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70, key="weight_patient")
    with col_h:
        height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170, key="height_patient")
    current_year = datetime.now().year
    with col_birth:
        birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40, key="birth_patient")
    with col_prog:
        user_id = st.session_state["user_id"]
        # Afficher **uniquement** les programmes associés à l'identifiant connecté
        user_programs = user_sessions.get(user_id, {}).get("programs", {})
        prog_choice_patient = st.selectbox(
            "Programme",
            ["Sélection d'un programme"] + list(user_programs.keys()),
            index=0,
            label_visibility="collapsed",
            key="prog_patient"
        )
        if prog_choice_patient != "Sélection d'un programme":
            prog_conf = user_programs.get(prog_choice_patient, {})
            for key, val in prog_conf.items():
                config[key] = val
            # enregistrement du programme sélectionné dans la session de l'identifiant
            user_sessions.setdefault(user_id, {}).setdefault("last_selected_program", None)
            user_sessions[user_id]["last_selected_program"] = prog_choice_patient
            save_user_sessions(user_sessions)

    # Calculs et affichage identiques à l’original
    age = current_year - birth_year
    imc = weight / ((height/100)**2)
    col_kv, col_mode_time = st.columns([1.2,2])
    with col_kv:
        kv_scanner = st.radio("kV du scanner",[80,90,100,110,120],index=4,horizontal=True,key="kv_patient")
    with col_mode_time:
        col_mode, col_times = st.columns([1.2,1])
        with col_mode:
            injection_modes=["Portal","Artériel"]
            if config.get("intermediate_enabled",False):
                injection_modes.append("Intermédiaire")
            injection_mode = st.radio("Mode d’injection", injection_modes,horizontal=True,key="mode_inj_patient")
        with col_times:
            if injection_mode=="Portal": 
                base_time = float(config.get("portal_time",30.0))
            elif injection_mode=="Artériel": 
                base_time = float(config.get("arterial_time",25.0))
            else:
                base_time = st.number_input("Temps Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0,max_value=120.0,step=1.0,key="intermediate_time_input")
            st.markdown(f"**Temps {injection_mode} :** {base_time:.0f} s")
            acquisition_start = calculate_acquisition_start(age, config)
            st.markdown(f"**Départ d'acquisition :** {acquisition_start:.1f} s")
            st.markdown(f"**Concentration utilisée :** {int(config.get('concentration_mg_ml',350))} mg I/mL")

    if weight <= 0 or height <= 0: 
        st.error("Poids et taille doivent être >0"); st.stop()
    if float(config.get("concentration_mg_ml",0)) <= 0: 
        st.error("La concentration doit être >0 mg I/mL"); st.stop()

    volume, bsa = calculate_volume(weight, height, kv_scanner, float(config.get("concentration_mg_ml",350)), imc, config.get("calc_mode","Charge iodée"), config.get("charges",{}), float(config.get("volume_max_limit",200.0)))
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume, float(base_time), float(config.get("max_debit",6.0)))

    if config.get("simultaneous_enabled",False):
        target = float(config.get("target_concentration",350))
        current_conc = float(config.get("concentration_mg_ml",350))
        if target > current_conc:
            st.warning(f"La concentration cible ({target:.0f}) est supérieure à la concentration du flacon ({current_conc:.0f})")
            target = current_conc
        vol_contrast = volume * (target/current_conc) if current_conc > 0 else volume
        vol_nacl_dilution = max(0.0, volume - vol_contrast)
        perc_contrast = (vol_contrast/volume*100) if volume>0 else 0
        perc_nacl_dilution = (vol_nacl_dilution/volume*100) if volume>0 else 0
        contrast_text = f"{int(round(vol_contrast))} mL ({int(round(perc_contrast))}%)"
        nacl_rincage_volume = float(config.get("rincage_volume",35.0))
        nacl_rincage_debit = max(0.1, injection_rate - float(config.get("rincage_delta_debit",0.5)))
        nacl_text = f"<div class='sub-item-large'>Dilution : {int(round(vol_nacl_dilution))} mL ({int(round(perc_nacl_dilution))}%)</div>"
        nacl_text += f"<div class='sub-item-large'>Rinçage : {int(round(nacl_rincage_volume))} mL @ {injection_rate:.1f} mL/s</div>"
    else:
        vol_contrast = volume
        contrast_text = f"{int(round(vol_contrast))} mL"
        nacl_text = f"{int(round(config.get('rincage_volume',35.0)))} mL"

    col_contrast, col_nacl, col_rate = st.columns(3, gap="medium")
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
        audit_log(f"calc:user={user_id},age={age},kv={kv_scanner},mode={injection_mode},vol={volume},vol_contrast={vol_contrast},rate={injection_rate:.2f}")
    except:
        pass

    # NOTE: gestion de suppression de sessions déplacée dans l'onglet Paramètres pour respecter la confidentialité.

# ------------------------
# Onglet Tutoriel (inchangé)
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
