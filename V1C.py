# -*- coding: utf-8 -*-
"""
oncologie_ct_adulte.py
Calculette complète — Oncologie CT adulte
Usage: streamlit run oncologie_ct_adulte.py
Remarque : ce fichier intègre les demandes de placement des infos :
 - bloc d'informations (méthode, charge, auto-ajust age, injection simultanée)
   affiché juste sous les champs Taille et Année de naissance sur la page Patient.
 - bloc d'informations (Temps intermédiaire, Départ d'acquisition, Concentration)
   affiché juste sous le sélecteur "Sélectionnez un programme".
 - les cases "Activer l'ajustement automatique du départ d'acquisition selon l'âge"
   et "Activer l'injection simultanée" sont dans l'onglet Paramètres → Paramètres techniques,
   et sont enregistrées dans l'espace utilisateur (non cochées par défaut).
Le reste de la logique et du visuel est préservé.
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
USER_SESSIONS_FILE = "user_sessions.json"
LOG_FILE = "calc_audit.log"

# ------------------------
# Valeurs par défaut globales
# ------------------------
default_config = {
    "charges": {str(kv): val for kv, val in zip([80, 90, 100, 110, 120], [0.35, 0.38, 0.40, 0.42, 0.45])},
    "concentration_mg_ml": 350,
    "portal_time": 30.0,
    "arterial_time": 25.0,
    "intermediate_enabled": False,
    "intermediate_time": 28.0,
    "acquisition_start_param": 70.0,
    "auto_acquisition_by_age": False,   # NON coché par défaut
    "max_debit": 6.0,
    "rincage_volume": 35.0,
    "rincage_delta_debit": 0.5,
    "calc_mode": "Charge iodée",
    "simultaneous_enabled": False,     # NON coché par défaut
    "target_concentration": 350,
    "volume_max_limit": 200.0,
    "nacl_dilution_percent": 0,
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
        except Exception:
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
# Charger config & sessions
# ------------------------
config_global = load_json_safe(CONFIG_FILE, default_config)
user_sessions = load_json_safe(USER_SESSIONS_FILE, {})

# Normalisation simple des sessions existantes
for uid, data in list(user_sessions.items()):
    if not isinstance(data, dict):
        user_sessions[uid] = {"programs": {}, "config": config_global.copy(), "email": None, "created": datetime.utcnow().isoformat()}
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
    if not cfg.get("auto_acquisition_by_age", False):
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

# ------------------------
# Streamlit UI init
# ------------------------
st.set_page_config(page_title="Calculette Contraste Oncologie CT adulte", page_icon="💉", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }
.small-note { font-size:0.86rem; color:#666; margin:4px 0; }
.center-muted { text-align:center; color:#666; font-size:0.9rem; }
.card-title { font-size:1.05rem; margin:0 0 6px 0; }
.result-large { font-size:1.4rem; font-weight:700; }
</style>
""", unsafe_allow_html=True)

# session state
if "accepted_legal" not in st.session_state:
    st.session_state["accepted_legal"] = False
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "user_cfg" not in st.session_state:
    st.session_state["user_cfg"] = config_global.copy()

SUPER_USER = config_global.get("super_user", "admin")

# ------------------------
# Page d'accueil : Mentions légales + session utilisateur
# ------------------------
if not st.session_state["accepted_legal"] or st.session_state["user_id"] is None:
    st.markdown("### ⚠️ Mentions légales — acceptation requise")
    st.markdown("Avant utilisation, acceptez la mention légale et créez ou entrez votre identifiant utilisateur. Résultats indicatifs à valider par un professionnel de santé.")
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")
    
    # Confidentialité : entrée libre (existants non listés sauf super-user)
    existing_id_input = st.text_input("Entrez un identifiant existant (si vous le connaissez)", key="existing_id_input")
    st.markdown("— ou —")
    new_user_id = st.text_input("Créez un nouvel identifiant", key="new_id_input")
    new_user_email = st.text_input("(Facultatif) Email pour récupération d'identifiant", key="new_user_email")
    st.caption("Astuce : si vous oubliez votre identifiant, utilisez 'Identifiant oublié ?' pour le retrouver via votre email (si ajouté).")

    with st.expander("🔑 Identifiant oublié ?"):
        forget_email = st.text_input("Entrez l'email associé à votre identifiant", key="forget_email")
        if st.button("🔍 Rechercher identifiant par email"):
            email = forget_email.strip()
            if not email:
                st.warning("Veuillez saisir un email.")
            else:
                found = [uid for uid, info in user_sessions.items() if info.get("email") == email]
                if found:
                    st.success(f"Identifiant(s) associé(s) à {email} : {', '.join(found)}")
                else:
                    st.error("Aucun identifiant n'est associé à cet email.")

    if st.button("Entrer dans la session"):
        if not accept:
            st.warning("Vous devez accepter les mentions légales.")
        else:
            chosen_existing = existing_id_input.strip()
            chosen_new = new_user_id.strip()
            email_new = new_user_email.strip() if new_user_email else None

            if chosen_existing and chosen_new:
                st.warning("Veuillez soit entrer un identifiant existant, soit créer un nouvel identifiant, pas les deux.")
            elif chosen_existing:
                if chosen_existing not in user_sessions:
                    st.error("❌ Identifiant introuvable. Veuillez saisir un identifiant existant ou créer un nouvel identifiant.")
                else:
                    st.session_state["accepted_legal"] = True
                    st.session_state["user_id"] = chosen_existing
                    st.session_state["user_cfg"] = user_sessions[chosen_existing].get("config", config_global.copy()).copy()
            elif chosen_new:
                if chosen_new in user_sessions:
                    st.error("❌ Cet identifiant existe déjà. Choisissez un autre nom.")
                else:
                    ts = datetime.utcnow().isoformat()
                    user_sessions[chosen_new] = {
                        "programs": {},
                        "config": config_global.copy(),
                        "email": email_new,
                        "created": ts,
                        "last_selected_program": None
                    }
                    save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                    st.session_state["accepted_legal"] = True
                    st.session_state["user_id"] = chosen_new
                    st.session_state["user_cfg"] = config_global.copy()
                    st.success(f"Identifiant '{chosen_new}' créé et sélectionné.")
            else:
                st.warning("Veuillez saisir un identifiant existant ou créer un nouvel identifiant.")
    st.stop()

# ------------------------
# Header (visuel conservé)
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

# Helper persistence functions
def get_user_cfg():
    return st.session_state.get("user_cfg", config_global.copy())

def set_user_cfg_and_persist(user_id, new_cfg):
    st.session_state["user_cfg"] = new_cfg.copy()
    if user_id not in user_sessions:
        user_sessions[user_id] = {"programs": {}, "config": new_cfg.copy(), "email": None, "created": datetime.utcnow().isoformat()}
    else:
        user_sessions[user_id]["config"] = new_cfg.copy()
    save_json_atomic(USER_SESSIONS_FILE, user_sessions)

# ------------------------
# Onglet Paramètres (tech & perso)
# ------------------------
with tab_params:
    st.header("⚙️ Paramètres et Bibliothèque (personnelle)")
    user_id = st.session_state["user_id"]
    cfg = get_user_cfg()

    st.markdown(f"**👤 Identifiant connecté :** `{user_id}`")

    st.subheader("Paramètres techniques")
    # These options are in Paramètres techniques and default to False per your request
    new_auto_age = st.checkbox("Activer l’ajustement automatique du départ d’acquisition selon l’âge", value=bool(cfg.get("auto_acquisition_by_age", False)))
    if new_auto_age != cfg.get("auto_acquisition_by_age", False):
        cfg["auto_acquisition_by_age"] = bool(new_auto_age)
        set_user_cfg_and_persist(user_id, cfg)

    new_simul = st.checkbox("Activer l’injection simultanée", value=bool(cfg.get("simultaneous_enabled", False)))
    if new_simul != cfg.get("simultaneous_enabled", False):
        cfg["simultaneous_enabled"] = bool(new_simul)
        set_user_cfg_and_persist(user_id, cfg)

    if cfg.get("simultaneous_enabled", False):
        new_target = st.number_input("Concentration cible (mg I/mL)", value=int(cfg.get("target_concentration", 350)), min_value=200, max_value=500, step=10)
        if new_target != cfg.get("target_concentration", 350):
            cfg["target_concentration"] = int(new_target)
            set_user_cfg_and_persist(user_id, cfg)

    st.markdown("---")
    st.subheader("Paramètres NaCl (personnels)")
    new_nacl_pct = st.number_input("Pourcentage de NaCl de dilution (entier %)", value=int(cfg.get("nacl_dilution_percent", 0)), min_value=0, max_value=100, step=1)
    if new_nacl_pct != cfg.get("nacl_dilution_percent", 0):
        cfg["nacl_dilution_percent"] = int(new_nacl_pct)
        set_user_cfg_and_persist(user_id, cfg)

    new_rincage_vol = st.number_input("Volume de rinçage (mL)", value=float(cfg.get("rincage_volume", 35.0)), min_value=0.0, max_value=1000.0, step=1.0)
    if new_rincage_vol != cfg.get("rincage_volume", 35.0):
        cfg["rincage_volume"] = float(new_rincage_vol)
        set_user_cfg_and_persist(user_id, cfg)

    new_rincage_rate = st.number_input("Débit de rinçage (mL/s)", value=float(cfg.get("rincage_rate_param", 3.0)), min_value=0.1, max_value=50.0, step=0.1)
    if new_rincage_rate != cfg.get("rincage_rate_param", 3.0):
        cfg["rincage_rate_param"] = float(new_rincage_rate)
        set_user_cfg_and_persist(user_id, cfg)

    st.markdown("---")
    st.subheader("Paramètres avancés (personnels)")
    new_conc = st.selectbox("Concentration (mg I/mL)", [300, 320, 350, 370, 400], index=[300,320,350,370,400].index(int(cfg.get("concentration_mg_ml", 350))))
    if new_conc != cfg.get("concentration_mg_ml", 350):
        cfg["concentration_mg_ml"] = int(new_conc)
        set_user_cfg_and_persist(user_id, cfg)

    new_calc_mode = st.selectbox("Méthode de calcul", ["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"].index(cfg.get("calc_mode", "Charge iodée")))
    if new_calc_mode != cfg.get("calc_mode", "Charge iodée"):
        cfg["calc_mode"] = new_calc_mode
        set_user_cfg_and_persist(user_id, cfg)

    new_max_debit = st.number_input("Débit maximal autorisé (mL/s)", value=float(cfg.get("max_debit", 6.0)), min_value=1.0, max_value=20.0, step=0.1)
    if new_max_debit != cfg.get("max_debit", 6.0):
        cfg["max_debit"] = float(new_max_debit)
        set_user_cfg_and_persist(user_id, cfg)

    new_portal = st.number_input("Portal (s)", value=float(cfg.get("portal_time", 30.0)), min_value=5.0, max_value=120.0, step=1.0)
    if new_portal != cfg.get("portal_time", 30.0):
        cfg["portal_time"] = float(new_portal)
        set_user_cfg_and_persist(user_id, cfg)

    new_arterial = st.number_input("Artériel (s)", value=float(cfg.get("arterial_time", 25.0)), min_value=5.0, max_value=120.0, step=1.0)
    if new_arterial != cfg.get("arterial_time", 25.0):
        cfg["arterial_time"] = float(new_arterial)
        set_user_cfg_and_persist(user_id, cfg)

    new_intermediate_enabled = st.checkbox("Activer temps intermédiaire (paramètre personnel)", value=bool(cfg.get("intermediate_enabled", False)))
    if new_intermediate_enabled != cfg.get("intermediate_enabled", False):
        cfg["intermediate_enabled"] = bool(new_intermediate_enabled)
        set_user_cfg_and_persist(user_id, cfg)

    if cfg.get("intermediate_enabled", False):
        new_inter_time = st.number_input("Intermédiaire (s)", value=float(cfg.get("intermediate_time", 28.0)), min_value=5.0, max_value=120.0, step=1.0)
        if new_inter_time != cfg.get("intermediate_time", 28.0):
            cfg["intermediate_time"] = float(new_inter_time)
            set_user_cfg_and_persist(user_id, cfg)

    if st.button("💾 Sauvegarder les paramètres"):
        set_user_cfg_and_persist(user_id, cfg)
        st.success("Paramètres sauvegardés dans votre espace personnel !")

    # Management of personal programs (unchanged semantics)
    st.markdown("---")
    st.subheader("Gérer programmes personnels")
    programs = user_sessions.get(user_id, {}).get("programs", {})
    prog_choice = st.selectbox("Programme (Personnel)", ["Aucun"] + list(programs.keys()))
    new_prog_name = st.text_input("Nom du nouveau programme")
    if st.button("💾 Ajouter/Mise à jour programme"):
        if new_prog_name.strip():
            to_save = cfg.copy()
            user_sessions.setdefault(user_id, {}).setdefault("programs", {})[new_prog_name.strip()] = to_save
            save_json_atomic(USER_SESSIONS_FILE, user_sessions)
            st.success(f"Programme '{new_prog_name}' enregistré pour {user_id}")
        else:
            st.warning("Donnez un nom au programme.")

    if programs:
        del_prog = st.selectbox("Supprimer un programme personnel", [""] + list(programs.keys()))
        if st.button("🗑 Supprimer programme personnel"):
            if del_prog and del_prog in user_sessions[user_id].get("programs", {}):
                del user_sessions[user_id]["programs"][del_prog]
                save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                st.success(f"Programme '{del_prog}' supprimé.")
            else:
                st.error("Programme introuvable.")

    # Management of user ids (kept)
    st.markdown("---")
    st.subheader("Gestion identifiants")
    all_user_ids = sorted(list(user_sessions.keys()))
    if user_id == SUPER_USER:
        st.markdown("**Super-utilisateur : accès à tous les identifiants**")
        df_users = pd.DataFrame([{"identifiant": uid, "email": user_sessions[uid].get("email")} for uid in all_user_ids])
        st.dataframe(df_users, use_container_width=True)
        del_input = st.text_input("Identifiant à supprimer (exact)", key="del_input_admin")
        if st.button("🗑 Supprimer identifiant (super-utilisateur)"):
            target = del_input.strip()
            if not target:
                st.warning("Veuillez saisir l'identifiant à supprimer.")
            elif target == user_id:
                st.error("⚠️ Impossible de supprimer l'identifiant en cours (super-utilisateur connecté).")
            elif target not in user_sessions:
                st.error("Identifiant introuvable.")
            else:
                del user_sessions[target]
                save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                st.success(f"Identifiant '{target}' supprimé.")
    else:
        st.markdown("**Supprimer VOTRE identifiant**")
        del_input_self = st.text_input("Confirmez votre identifiant exact pour suppression", key="del_input_self")
        if st.button("🗑 Supprimer MON identifiant"):
            target = del_input_self.strip()
            if not target:
                st.warning("Veuillez saisir votre identifiant exact.")
            elif target != user_id:
                st.error("Le nom saisi ne correspond pas à l'identifiant connecté.")
            else:
                try:
                    if user_id in user_sessions:
                        del user_sessions[user_id]
                        save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                    st.session_state["accepted_legal"] = False
                    st.session_state["user_id"] = None
                    st.session_state["user_cfg"] = config_global.copy()
                    st.success("Votre identifiant a été supprimé. Déconnexion.")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Erreur suppression : {e}")

# ------------------------
# Onglet Patient
# ------------------------
with tab_patient:
    st.header("🧍 Informations patient")
    # Layout: weight -> mode -> kV in left column as requested
    col_w, col_h, col_birth, col_prog = st.columns([1,1,1,1.2])

    with col_w:
        weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70, key="weight_patient")
        # mode injection under weight
        cfg = get_user_cfg()
        injection_modes = ["Portal","Artériel"]
        if cfg.get("intermediate_enabled", False):
            injection_modes.append("Intermédiaire")
        injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True, key="mode_inj_patient")
        # kv under mode
        kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True, key="kv_patient")

    with col_h:
        height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170, key="height_patient")
    with col_birth:
        current_year = datetime.now().year
        birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40, key="birth_patient")
    with col_prog:
        user_id = st.session_state["user_id"]
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
            cfg = get_user_cfg()
            for key, val in prog_conf.items():
                cfg[key] = val
            set_user_cfg_and_persist(user_id, cfg)
            user_sessions[user_id]["last_selected_program"] = prog_choice_patient
            save_json_atomic(USER_SESSIONS_FILE, user_sessions)

    # ------------------------
    # AFFICHAGE DEMANDÉ : sous Taille & Naissance
    # ------------------------
    cfg = get_user_cfg()
    method = cfg.get("calc_mode", "Charge iodée")
    charge_used = float(cfg.get("charges", {}).get(str(kv_scanner), 0.0))
    st.markdown(f"🧮 **Méthode utilisée :** {method}")
    st.markdown(f"💊 **Charge iodée appliquée (kV {kv_scanner}) :** {charge_used:.2f} g I/kg")
    # show status lines depending on user settings (these options live in Paramètres techniques)
    if cfg.get("auto_acquisition_by_age", False):
        st.markdown("<div class='small-note'>🕒 Ajustement automatique du départ d'acquisition selon l'âge activé</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='small-note'>🕒 Ajustement automatique du départ d'acquisition désactivé</div>", unsafe_allow_html=True)
    if cfg.get("simultaneous_enabled", False):
        st.markdown("<div class='small-note'>💧 Injection simultanée activée</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='small-note'>💧 Injection simultanée désactivée</div>", unsafe_allow_html=True)

    # ------------------------
    # Sous le sélecteur "Sélectionnez un programme" afficher les temps & concentration demandés
    # ------------------------
    st.markdown("---")
    st.markdown("**Informations temps & acquisition (sélection du programme)**")
    st.markdown(f"Temps Intermédiaire (s) : {cfg.get('intermediate_time', 28.0):.2f}")
    st.markdown(f"Temps Intermédiaire : {int(cfg.get('intermediate_time', 28.0))} s")
    acquisition_start = calculate_acquisition_start(datetime.now().year - birth_year, cfg)
    st.markdown(f"Départ d'acquisition : {acquisition_start:.1f} s")
    st.markdown(f"Concentration utilisée : {int(cfg.get('concentration_mg_ml',350))} mg I/mL")
    if injection_mode == "Intermédiaire":
        st.markdown("<div class='small-note'>⚠️⚠️ Pensez à ajuster votre départ d'acquisition manuellement.</div>", unsafe_allow_html=True)

    # ------------------------
    # Calculs (inchangés)
    # ------------------------
    age = datetime.now().year - birth_year
    imc = weight / ((height/100)**2)
    volume, bsa = calculate_volume(weight, height, kv_scanner, float(cfg.get("concentration_mg_ml",350)), imc, cfg.get("calc_mode","Charge iodée"), cfg.get("charges",{}), float(cfg.get("volume_max_limit",200.0)))
    # decide injection time based on mode
    if injection_mode == "Portal":
        inj_time = float(cfg.get("portal_time", 30.0))
    elif injection_mode == "Artériel":
        inj_time = float(cfg.get("arterial_time", 25.0))
    else:
        inj_time = float(cfg.get("intermediate_time", 28.0))
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume, inj_time, float(cfg.get("max_debit",6.0)))

    # simultaneous behavior and nacl breakdown
    if cfg.get("simultaneous_enabled", False):
        target = float(cfg.get("target_concentration", 350))
        current_conc = float(cfg.get("concentration_mg_ml", 350))
        if current_conc <= 0:
            current_conc = target
        if target > current_conc:
            st.warning(f"La concentration cible ({target:.0f}) est supérieure à la concentration du flacon ({current_conc:.0f}). Utilisation de la concentration du flacon.")
            target = current_conc
        vol_contrast = volume * (target/current_conc) if current_conc > 0 else volume
        nacl_pct = int(cfg.get("nacl_dilution_percent", 0))
        nacl_dilution_volume = int(round(vol_contrast * (nacl_pct / 100.0)))
        rincage_vol = int(round(cfg.get("rincage_volume", 35.0)))
        total_nacl_volume = nacl_dilution_volume + rincage_vol
        rincage_rate = float(cfg.get("rincage_rate_param", 3.0))
        contrast_text = f"{int(round(vol_contrast))} mL"
    else:
        vol_contrast = volume
        contrast_text = f"{int(round(vol_contrast))} mL"
        nacl_dilution_volume = 0
        rincage_vol = int(round(cfg.get("rincage_volume", 35.0)))
        total_nacl_volume = int(round(rincage_vol))
        rincage_rate = float(cfg.get("rincage_rate_param", 3.0))

    # ------------------------
    # Bas de page : deux cartes (contraste = goutte verte SVG, NaCl = goutte bleue SVG)
    # ------------------------
    green_drop_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 2C12 2 18 8 18 13.5C18 18.1944 14.4183 21.7761 9.724 21.9999C9.488 22.0199 9.259 22.0299 9.038 22.0299C8.813 22.0299 8.588 22.0199 8.361 21.9999C3.663 21.7759 0 18.1534 0 13.5C0 8 6 2 12 2Z" fill="#2ECC71"/></svg>"""
    blue_drop_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 2C12 2 18 8 18 13.5C18 18.1944 14.4183 21.7761 9.724 21.9999C9.488 22.0199 9.259 22.0299 9.038 22.0299C8.813 22.0299 8.588 22.0199 8.361 21.9999C3.663 21.7759 0 18.1534 0 13.5C0 8 6 2 12 2Z" fill="#3E8ED0"/></svg>"""

    col_c, col_n = st.columns(2, gap="medium")
    with col_c:
        st.markdown(f"""<div style="background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;">
            <div style="display:flex; align-items:center; justify-content:center; gap:8px;">
                <div>{green_drop_svg}</div>
                <div class="card-title">Volume et Débit de contraste conseillé</div>
            </div>
            <div style="margin-top:10px;" class="result-large">{contrast_text} — Débit : <b>{injection_rate:.1f} mL/s</b></div>
        </div>""", unsafe_allow_html=True)

    with col_n:
        if cfg.get("simultaneous_enabled", False):
            st.markdown(f"""<div style="background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;">
                <div style="display:flex; align-items:center; justify-content:center; gap:8px;">
                    <div>{blue_drop_svg}</div>
                    <div class="card-title">Volume et Débit de NaCl conseillé</div>
                </div>
                <div style="margin-top:10px;">
                    <div><b>Volume dilution :</b> {nacl_dilution_volume} mL</div>
                    <div style="margin-top:6px;"><b>Volume rinçage :</b> {rincage_vol} mL</div>
                    <div style="margin-top:6px;"><b>Volume total NaCl :</b> {total_nacl_volume} mL</div>
                    <div style="margin-top:6px;"><b>Débit de rinçage :</b> {rincage_rate:.1f} mL/s</div>
                    <div style="margin-top:6px; font-size:0.95rem; color:#444;">(Débit contraste : {injection_rate:.1f} mL/s)</div>
                </div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style="background:#EAF1F8;padding:12px;border-radius:10px;text-align:center;">
                <div style="display:flex; align-items:center; justify-content:center; gap:8px;">
                    <div>{blue_drop_svg}</div>
                    <div class="card-title">Volume et Débit de NaCl conseillé</div>
                </div>
                <div style="margin-top:10px;" class="result-large">{total_nacl_volume} mL — Débit : <b>{rincage_rate:.1f} mL/s</b></div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<div class='center-muted'>Résultats indicatifs — à valider par un professionnel de santé.</div>", unsafe_allow_html=True)

    if time_adjusted:
        st.warning(f"⚠️ Temps d’injection ajusté à {injection_time:.1f}s pour respecter le débit maximal de {cfg.get('max_debit',6.0)} mL/s.")

    st.markdown("<div class='small-note'>⚠️⚠️ Pensez à ajuster votre départ d'acquisition manuellement si nécessaire.</div>", unsafe_allow_html=True)

    try:
        audit_log(f"calc:user={user_id},age={age},kv={kv_scanner},mode={injection_mode},vol={volume},vol_contrast={vol_contrast},rate={injection_rate:.2f}")
    except:
        pass

# ------------------------
# Onglet Tutoriel
# ------------------------
with tab_tutorial:
    st.title("📘 Tutoriel — Mode d'emploi et principes cliniques")
    st.markdown("Cette section explique **comment utiliser** la calculette et **pourquoi** chaque calcul est effectué.")
    st.markdown("Ce tutoriel se réfère aux recommandations du CIRTACI 5.3.0 (2020).")
    st.markdown(f"[Consulter le document officiel (CIRTACI 5.3.0 — 2020)](https://www.radiologie.fr/sites/www.radiologie.fr/files/medias/documents/CIRTACI%20Fiche%20Ge%CC%81ne%CC%81ralite%CC%81s%20VASCULAIRE_5_3_1.pdf)")

# ------------------------
# Footer
# ------------------------
st.markdown(f"""<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Calculette de dose de produit de contraste — Oncologie CT adulte.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
<br><br>
<a href="https://www.radiologie.fr/sites/www.radiologie.fr/files/medias/documents/CIRTACI%20Fiche%20Ge%CC%81ne%CC%81ralite%CC%81s%20VASCULAIRE_5_3_1.pdf" target="_blank" style="color:#0B67A9; text-decoration:underline;">Consulter le document CIRTACI 5.3.0 (2020)</a>
</div>""", unsafe_allow_html=True)
