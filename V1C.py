
# -*- coding: utf-8 -*-
"""
Calculette complète (une page) de dose de produit de contraste - Oncologie adulte
Adaptée pour Sébastien Partouche — version consolidée optimisée (corrigée)
Usage : streamlit run calculatrice_contraste_oncologie_corrigee_v2.py
"""

import streamlit as st
import json
import os
import math
import base64
import time
import contextlib
from datetime import datetime
import pandas as pd

# ------------------------
# Fichiers de config
# ------------------------
CONFIG_FILE = "iodine_config.json"
LIB_FILE = "libraries.json"  # conservé si besoin futur, mais programmes globaux désactivés
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
    # super_user configurable ici si besoin
    "super_user": "admin"
}

# ------------------------
# Verrouillage de fichiers (best effort cross-platform)
# ------------------------
@contextlib.contextmanager
def file_lock(lock_path, timeout=5.0, poll=0.05):
    start = time.time()
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if time.time() - start > timeout:
                raise TimeoutError(f"Lock timeout: {lock_path}")
            time.sleep(poll)
    try:
        yield
    finally:
        try:
            os.remove(lock_path)
        except FileNotFoundError:
            pass

# ------------------------
# Utils I/O sécurisées
# ------------------------
def audit_log(msg):
    """Ajoute une ligne d'audit (anonymisé) localement."""
    try:
        ts = datetime.utcnow().isoformat()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts} - {msg}\n")
    except Exception:
        pass

def load_json_safe(path, default):
    lock = path + ".lock"
    if os.path.exists(path):
        try:
            with file_lock(lock):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            audit_log(f"LOAD_ERROR {path}: {e}")
            st.warning(f"⚠️ Erreur lecture '{path}' — valeurs par défaut utilisées.")
            return default.copy()
    return default.copy()

def save_json_atomic(path, data):
    tmp = path + ".tmp"
    lock = path + ".lock"
    try:
        with file_lock(lock):
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            os.replace(tmp, path)
    except Exception as e:
        audit_log(f"SAVE_ERROR {path}: {e}")
        # en cas d'échec, essayer un fallback non atomique minimaliste
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e2:
            audit_log(f"SAVE_FALLBACK_ERROR {path}: {e2}")

def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ------------------------
# Charger config & libs
# ------------------------
config_global = load_json_safe(CONFIG_FILE, default_config)
# libraries left for future but global programs disabled per request
libraries = load_json_safe(LIB_FILE, {"programs": {}})
user_sessions = load_json_safe(USER_SESSIONS_FILE, {})

# Normalize older data shapes: ensure each user has keys
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
    except Exception as e:
        audit_log(f"CALC_VOLUME_ERROR: {e}")
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

# ------------------------
# Helpers divers
# ------------------------
def mask_email(e):
    try:
        if not e:
            return ""
        local, domain = e.split("@", 1)
        if len(local) <= 2:
            local_mask = local[0] + "*"
        else:
            local_mask = local[0] + "*"*(len(local)-2) + local[-1]
        return f"{local_mask}@{domain}"
    except Exception:
        return "****"

# ------------------------
# Streamlit UI init
# ------------------------
st.set_page_config(page_title="Calculette Contraste Oncologie adulte", page_icon="💉", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }
.slider-red .stSlider [data-baseweb="slider"] div[role="slider"] { background-color: #E53935 !important; }
.slider-red .stSlider [data-baseweb="slider"] div[role="slider"]::before { background-color: #E53935 !important; }
.divider { border-left: 1px solid #d9d9d9; height: 100%; margin: 0 20px; }
.info-block { background: #F5F8FC; border-radius: 10px; padding: 15px 20px; text-align: center; color: #123A5F; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.section-title { font-size: 22px; font-weight: 700; color: #123A5F; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

# session state inits
if "accepted_legal" not in st.session_state:
    st.session_state["accepted_legal"] = False
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "selected_program" not in st.session_state:
    st.session_state["selected_program"] = None
if "user_config" not in st.session_state:
    st.session_state["user_config"] = config_global.copy()

# helper: active super user name (configurable in config_global)
SUPER_USER = config_global.get("super_user", "admin")

# ------------------------
# Page d'accueil : Mentions légales + session utilisateur
# ------------------------
if not st.session_state["accepted_legal"] or st.session_state["user_id"] is None:
    st.markdown("### ⚠️ Mentions légales — acceptation requise")
    st.markdown("Avant utilisation, acceptez la mention légale et créez ou entrez votre identifiant utilisateur. Résultats indicatifs à valider par un professionnel de santé.")
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")
    
    # Connexion : entrer IDENTIFIANT EXISTANT uniquement
    st.markdown("**Se connecter**")
    existing_id_input = st.text_input("Entrez un identifiant existant (si vous le connaissez)", key="existing_id_input")
    st.markdown("— ou —")
    st.markdown("**Créer un nouvel identifiant**")
    new_user_id = st.text_input("Créez un nouvel identifiant", key="new_id_input")
    new_user_email = st.text_input("(Facultatif) Email pour récupération d'identifiant", key="new_user_email")
    st.caption("Astuce : si vous oubliez votre identifiant, utilisez 'Identifiant oublié ?' pour le retrouver via votre email (si ajouté).")
    
    # Identification oubliée (affichée dans la page d'accueil)
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

            # 1) If user filled both, prefer explicit creation? We'll disallow: require only one action
            if chosen_existing and chosen_new:
                st.warning("Veuillez soit entrer un identifiant existant, soit créer un nouvel identifiant, pas les deux.")
            elif chosen_existing:
                # Connecting to existing id only allowed
                if chosen_existing not in user_sessions:
                    st.error("❌ Identifiant introuvable. Veuillez saisir un identifiant existant ou créer un nouvel identifiant.")
                else:
                    st.session_state["accepted_legal"] = True
                    st.session_state["user_id"] = chosen_existing
                    # load user's config into session
                    st.session_state["user_config"] = user_sessions[chosen_existing].get("config", config_global.copy()).copy()
            elif chosen_new:
                # Creating new id: must not already exist, email maybe provided but must be unique
                if chosen_new in user_sessions:
                    st.error("❌ Cet identifiant existe déjà. Choisissez un autre nom.")
                else:
                    # if email provided, ensure unique
                    if email_new:
                        emails = [info.get("email") for info in user_sessions.values() if info.get("email")]
                        if email_new in emails:
                            st.error("❌ Cet email est déjà associé à un autre identifiant.")
                            st.stop()
                    # create
                    ts = datetime.utcnow().isoformat()
                    user_sessions[chosen_new] = {
                        "programs": {},
                        "config": config_global.copy(),
                        "email": email_new,
                        "created": ts,
                        "last_selected_program": None
                    }
                    save_user_sessions(user_sessions)
                    st.session_state["accepted_legal"] = True
                    st.session_state["user_id"] = chosen_new
                    st.session_state["user_config"] = config_global.copy()
                    st.success(f"Identifiant '{chosen_new}' créé. Vous êtes connecté.")
            else:
                st.warning("Veuillez saisir un identifiant existant ou créer un nouvel identifiant.")
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
            <img src="data:image/png;base64,{img_b64}" style="height:55px"/>
            <h2 style="color:white; margin:0; font-size:26px;">
                Aide au calcul de dose de produit de contraste en CT — Oncologie adulte
            </h2>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.title("Aide au calcul de dose de produit de contraste en CT — Oncologie adulte")
else:
    st.title("Aide au calcul de dose de produit de contraste en CT — Oncologie adulte")


# ------------------------
# Tabs
# ------------------------
tab_patient, tab_params, tab_tutorial = st.tabs(["🧍 Patient", "⚙️ Paramètres", "📘 Tutoriel"])

# Use working config that refers to the logged-in user's config (kept in session_state)
def get_cfg():
    return st.session_state.get("user_config", config_global.copy())

def set_cfg_and_persist(user_id, new_cfg):
    st.session_state["user_config"] = new_cfg.copy()
    # persist in user_sessions
    if user_id not in user_sessions:
        user_sessions[user_id] = {"programs": {}, "config": new_cfg.copy(), "email": None, "created": datetime.utcnow().isoformat()}
    else:
        user_sessions[user_id]["config"] = new_cfg.copy()
    save_user_sessions(user_sessions)

# ------------------------
# Onglet Paramètres (version finale complète avec départ artériel)
# ------------------------
with tab_params:
    st.header("⚙️ Paramètres et Bibliothèque (personnelle)")

    # ✅ On récupère l'identifiant utilisateur actif
    user_id = st.session_state.get("user_id", None)
    if not user_id:
        st.error("⚠️ Aucun identifiant utilisateur actif. Veuillez vous reconnecter.")
        st.stop()

    cfg = get_cfg()

    # ----------------------------------------------------------------------
    # 📚 SECTION 1 — Vos programmes personnels
    # ----------------------------------------------------------------------
    st.subheader("📚 Vos programmes personnels")

    personal_programs = user_sessions.get(user_id, {}).get("programs", {})
    program_choice = st.selectbox(
        "Programme (Personnel)",
        ["Aucun"] + list(personal_programs.keys()),
        key="prog_params_personal"
    )

    program_locked = False
    unlock_granted = False

    if program_choice != "Aucun":
        prog_conf = personal_programs.get(program_choice, {})
        for key, val in prog_conf.items():
            cfg[key] = val

        st.info(f"🔒 Programme sélectionné : **{program_choice}** — protégé contre les modifications directes.")
        pwd_input = st.text_input("Entrez votre identifiant pour déverrouiller ce programme", type="password")

        if st.button("🔓 Déverrouiller le programme"):
            if pwd_input.strip() == user_id:
                unlock_granted = True
                st.success(f"✅ Programme '{program_choice}' déverrouillé pour modification.")
            else:
                st.error("❌ Identifiant incorrect. Modifications interdites.")
                program_locked = True
        else:
            program_locked = True
    else:
        st.info("Aucun programme sélectionné — vous pouvez librement ajuster les paramètres et créer un nouveau programme.")

    # Nom du nouveau programme
    new_prog_name = st.text_input("Nom du nouveau programme (sera enregistré dans vos programmes personnels)")

    # ✅ Création ou mise à jour d’un programme
    if st.button("💾 Ajouter/Mise à jour programme"):
        if program_locked and not unlock_granted:
            st.warning("⚠️ Programme protégé — entrez votre identifiant pour le modifier ou créez un nouveau programme.")
        elif not new_prog_name.strip():
            st.warning("Veuillez donner un nom au programme avant d’enregistrer.")
        else:
            current_values = {
                "simultaneous_enabled": cfg.get("simultaneous_enabled", False),
                "target_concentration": cfg.get("target_concentration", 350),
                "concentration_mg_ml": cfg.get("concentration_mg_ml", 350),
                "calc_mode": cfg.get("calc_mode", "Charge iodée"),
                "max_debit": cfg.get("max_debit", 6.0),
                "auto_acquisition_by_age": cfg.get("auto_acquisition_by_age", True),
                "acquisition_start_param": cfg.get("acquisition_start_param", 70.0),
                "portal_time": cfg.get("portal_time", 30.0),
                "arterial_time": cfg.get("arterial_time", 25.0),
                "arterial_acq_enabled": cfg.get("arterial_acq_enabled", True),
                "arterial_acq_time": cfg.get("arterial_acq_time", 25.0),
                "intermediate_enabled": cfg.get("intermediate_enabled", False),
                "intermediate_time": cfg.get("intermediate_time", 28.0),
                "rincage_volume": cfg.get("rincage_volume", 35.0),
                "rincage_delta_debit": cfg.get("rincage_delta_debit", 0.5),
                "volume_max_limit": cfg.get("volume_max_limit", 200.0),
                "charges": cfg.get("charges", {})
            }
            cfg.update(current_values)
            user_sessions.setdefault(user_id, {}).setdefault("programs", {})[new_prog_name.strip()] = cfg.copy()
            user_sessions[user_id]["config"] = cfg.copy()
            save_user_sessions(user_sessions)
            st.success(f"✅ Programme personnel '{new_prog_name}' sauvegardé avec tous les paramètres !")

    # 🗑 Gestion des programmes personnels
    st.markdown("**Gérer mes programmes personnels**")
    personal_prog_list = list(user_sessions.get(user_id, {}).get("programs", {}).keys())
    if personal_prog_list:
        del_prog_personal = st.selectbox(
            "Supprimer un programme personnel",
            [""] + personal_prog_list,
            key="del_prog_personal"
        )
        if st.button("🗑 Supprimer programme (Personnel)"):
            if del_prog_personal and del_prog_personal in user_sessions[user_id]["programs"]:
                del user_sessions[user_id]["programs"][del_prog_personal]
                save_user_sessions(user_sessions)
                st.success(f"Programme personnel '{del_prog_personal}' supprimé pour l'identifiant '{user_id}'.")
            else:
                st.error("Programme introuvable.")
    else:
        st.info("Vous n'avez pas encore de programmes personnels enregistrés.")

    # ----------------------------------------------------------------------
    # 💉 SECTION 2 — Paramètres d’injection
    # ----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("💉 Paramètres d’injection et calculs")

    disabled = program_locked and not unlock_granted

    cfg["simultaneous_enabled"] = st.checkbox(
        "Activer l'injection simultanée",
        value=cfg.get("simultaneous_enabled", False),
        disabled=disabled
    )
    if cfg["simultaneous_enabled"]:
        cfg["target_concentration"] = st.number_input(
            "Concentration cible (mg I/mL)",
            value=int(cfg.get("target_concentration", 350)),
            min_value=200,
            max_value=500,
            step=10,
            disabled=disabled
        )

    cfg["concentration_mg_ml"] = st.selectbox(
        "Concentration (mg I/mL)",
        [300, 320, 350, 370, 400],
        index=[300, 320, 350, 370, 400].index(int(cfg.get("concentration_mg_ml", 350))),
        disabled=disabled
    )
    cfg["calc_mode"] = st.selectbox(
        "Méthode de calcul",
        ["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"],
        index=["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"].index(cfg.get("calc_mode", "Charge iodée")),
        disabled=disabled
    )
    cfg["max_debit"] = st.number_input(
        "Débit maximal autorisé (mL/s)",
        value=float(cfg.get("max_debit", 6.0)),
        min_value=1.0,
        max_value=20.0,
        step=0.1,
        disabled=disabled
    )

    # ----------------------------------------------------------------------
    # 🕒 SECTION 3 — Acquisition et temps
    # ----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("⏱ Départ d’acquisition et temps d’injection")

    cfg["auto_acquisition_by_age"] = st.checkbox(
        "Ajuster automatiquement le départ d’acquisition selon l’âge",
        value=bool(cfg.get("auto_acquisition_by_age", True)),
        disabled=disabled
    )

    if not cfg["auto_acquisition_by_age"]:
        cfg["acquisition_start_param"] = st.number_input(
            "Départ d’acquisition manuel (s)",
            value=float(cfg.get("acquisition_start_param", 70.0)),
            min_value=30.0,
            max_value=120.0,
            step=1.0,
            disabled=disabled
        )

    # ✅ Ajout : départ artériel activable + modifiable
    cfg["arterial_acq_enabled"] = st.checkbox(
        "Activer départ acquisition artériel",
        value=bool(cfg.get("arterial_acq_enabled", True)),
        disabled=disabled
    )

    if cfg["arterial_acq_enabled"]:
        cfg["arterial_acq_time"] = st.number_input(
            "Départ d’acquisition artériel (s)",
            value=float(cfg.get("arterial_acq_time", 25.0)),
            min_value=10.0,
            max_value=120.0,
            step=0.5,
            disabled=disabled
        )

    cfg["portal_time"] = st.number_input(
        "Portal (s)",
        value=float(cfg.get("portal_time", 30.0)),
        min_value=5.0,
        max_value=120.0,
        step=1.0,
        disabled=disabled
    )
    cfg["arterial_time"] = st.number_input(
        "Artériel (s)",
        value=float(cfg.get("arterial_time", 25.0)),
        min_value=5.0,
        max_value=120.0,
        step=1.0,
        disabled=disabled
    )

    cfg["intermediate_enabled"] = st.checkbox(
        "Activer temps intermédiaire",
        value=bool(cfg.get("intermediate_enabled", False)),
        disabled=disabled
    )
    if cfg["intermediate_enabled"]:
        cfg["intermediate_time"] = st.number_input(
            "Intermédiaire (s)",
            value=float(cfg.get("intermediate_time", 28.0)),
            min_value=5.0,
            max_value=120.0,
            step=1.0,
            disabled=disabled
        )

    # ----------------------------------------------------------------------
    # ⚗️ SECTION 4 — Rinçage et volumes
    # ----------------------------------------------------------------------
    cfg["rincage_volume"] = st.number_input(
        "Volume rinçage (mL)",
        value=float(cfg.get("rincage_volume", 35.0)),
        min_value=10.0,
        max_value=100.0,
        step=1.0,
        disabled=disabled
    )
    cfg["rincage_delta_debit"] = st.number_input(
        "Δ débit NaCl vs contraste (mL/s)",
        value=float(cfg.get("rincage_delta_debit", 0.5)),
        min_value=0.1,
        max_value=5.0,
        step=0.1,
        disabled=disabled
    )
    cfg["volume_max_limit"] = st.number_input(
        "Plafond volume (mL) - seringue",
        value=float(cfg.get("volume_max_limit", 200.0)),
        min_value=50.0,
        max_value=500.0,
        step=10.0,
        disabled=disabled
    )

    # ----------------------------------------------------------------------
    # 💊 SECTION 5 — Charges iodées
    # ----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("💊 Charges en iode par kV (g I/kg)")
    df_charges = pd.DataFrame({
        "kV": [80, 90, 100, 110, 120],
        "Charge (g I/kg)": [float(cfg["charges"].get(str(kv), 0.35)) for kv in [80, 90, 100, 110, 120]]
    })
    edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True, disabled=disabled)

    if st.button("💾 Sauvegarder les paramètres", disabled=disabled):
        try:
            cfg["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _, row in edited_df.iterrows()}
            set_cfg_and_persist(user_id, cfg)
            st.success("✅ Paramètres sauvegardés dans votre espace utilisateur !")
        except Exception as e:
            st.error(f"Erreur lors de la sauvegarde : {e}")

    # ----------------------------------------------------------------------
    # 👤 SECTION 6 — Gestion des identifiants
    # ----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("🗂 Gestion des sessions / identifiants")
    st.markdown("Les identifiants sont indépendants. Vos programmes et paramètres personnels ne sont accessibles qu'avec votre identifiant.")

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
                save_user_sessions(user_sessions)
                st.success(f"Identifiant '{target}' supprimé par le super-utilisateur.")
    else:
        st.markdown("Seul le super-utilisateur peut lister tous les identifiants.")
        del_input_self = st.text_input("Confirmez votre identifiant pour supprimer votre compte (exact)", key="del_input_self")
        if st.button("🗑 Supprimer MON identifiant"):
            target = del_input_self.strip()
            if not target:
                st.warning("Veuillez saisir votre identifiant exact pour confirmer.")
            elif target != user_id:
                st.error("Le nom saisi ne correspond pas à l'identifiant connecté.")
            else:
                try:
                    if user_id in user_sessions:
                        del user_sessions[user_id]
                        save_user_sessions(user_sessions)
                    st.session_state["accepted_legal"] = False
                    st.session_state["user_id"] = None
                    st.session_state["user_config"] = config_global.copy()
                    st.success("Votre identifiant a été supprimé. Vous avez été déconnecté.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur suppression identifiant : {e}")
                    
# ------------------------
# Onglet Patient — version stable finale (fixe, sans scroll, 120kV visible)
# ------------------------
with tab_patient:
    st.markdown("""
        <style>
        .section-title {
            font-size:22px; font-weight:700; color:#123A5F;
            margin-bottom:12px; text-align:center;
        }
        .block-title {
            text-align:center; font-weight:700; color:#123A5F;
            font-size:16px; margin-bottom:6px;
        }
        /* ✅ largeur figée, visuel stable */
        .main, .block-container {
            width: 92% !important;
            max-width: 1150px !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }
        [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            justify-content: space-between !important;
        }
        /* ✅ radios : taille ajustée, pas de scroll ni wrap */
        div[role="radiogroup"] {
            display:flex !important;
            justify-content:center !important;
            align-items:center !important;
            flex-wrap:nowrap !important;
            white-space:nowrap !important;
            gap:14px !important;
        }
        div[role="radiogroup"] label {
            font-size:14px !important;
            padding:3px 8px !important;
            border-radius:6px !important;
            background:#F8FAFD !important;
            border:1px solid #DCE4EC !important;
            transition:all 0.15s ease-in-out;
        }
        div[role="radiogroup"] label:hover {
            background:#E7EEF9 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # --- titre ---
    st.markdown("<div class='section-title'>🧍 Informations patient</div>", unsafe_allow_html=True)
    current_year = datetime.now().year

    # === Ligne 1 : sliders + entrée numérique ===
    col_poids, col_taille, col_annee, col_prog = st.columns([1, 1, 1, 1.3])

    with col_poids:
        st.markdown("<div class='block-title'>Poids (kg)</div>", unsafe_allow_html=True)
        col_num, col_slide = st.columns([0.35, 0.65])
        with col_num:
            poids_num = st.number_input("", 20, 200, 70, step=1, key="poids_num", label_visibility="collapsed")
        with col_slide:
            poids_slider = st.slider(" ", 20, 200, poids_num, label_visibility="collapsed", key="poids_slider")
        weight = poids_slider

    with col_taille:
        st.markdown("<div class='block-title'>Taille (cm)</div>", unsafe_allow_html=True)
        col_num, col_slide = st.columns([0.35, 0.65])
        with col_num:
            taille_num = st.number_input("", 100, 220, 170, step=1, key="taille_num", label_visibility="collapsed")
        with col_slide:
            taille_slider = st.slider(" ", 100, 220, taille_num, label_visibility="collapsed", key="taille_slider")
        height = taille_slider

    with col_annee:
        st.markdown("<div class='block-title'>Année de naissance</div>", unsafe_allow_html=True)
        col_num, col_slide = st.columns([0.45, 0.55])
        with col_num:
            annee_num = st.number_input("", current_year - 120, current_year, 1985, step=1,
                                        key="annee_num", label_visibility="collapsed")
        with col_slide:
            annee_slider = st.slider(" ", current_year - 120, current_year, annee_num,
                                     label_visibility="collapsed", key="annee_slider")
        birth_year = annee_slider

    with col_prog:
        st.markdown("<div class='block-title'>Programme</div>", unsafe_allow_html=True)
        user_id = st.session_state["user_id"]
        user_programs = user_sessions.get(user_id, {}).get("programs", {})
        prog_choice_patient = st.selectbox(" ", ["Sélection d'un programme"] + list(user_programs.keys()),
                                           index=0, label_visibility="collapsed")
        if prog_choice_patient != "Sélection d'un programme":
            prog_conf = user_programs.get(prog_choice_patient, {})
            cfg = get_cfg()
            for key, val in prog_conf.items():
                cfg[key] = val
            set_cfg_and_persist(user_id, cfg)
            user_sessions[user_id]["last_selected_program"] = prog_choice_patient
            save_user_sessions(user_sessions)

    # === Variables patient ===
    cfg = get_cfg()
    age = current_year - birth_year
    imc = weight / ((height / 100) ** 2)

    # === Ligne 2 : 3 blocs ===
    col_left, col_div1, col_center, col_div2, col_right = st.columns([1.2, 0.05, 1.2, 0.05, 1.2])

    # --- Bloc gauche ---
    with col_left:
        st.markdown("<div class='block-title'>Choix de la tension du tube (en kV)</div>", unsafe_allow_html=True)
        kv_scanner = st.radio("kV", [80, 90, 100, 110, 120],
                              horizontal=True, index=4, key="kv_scanner_patient",
                              label_visibility="collapsed")
        charge_iod = float(cfg.get("charges", {}).get(str(kv_scanner), 0.45))
        concentration = int(cfg.get("concentration_mg_ml", 350))
        calc_mode_label = cfg.get("calc_mode", "Charge iodée")
        st.markdown(
            f"<div style='text-align:center; font-size:15px; color:#123A5F;'>"
            f"<b>Charge iodée :</b> {charge_iod:.2f} g I/kg<br>"
            f"<b>Concentration :</b> {concentration} mg I/mL<br>"
            f"<b>Méthode :</b> {calc_mode_label}</div>",
            unsafe_allow_html=True
        )

    with col_div1:
        st.markdown("<div style='border-left:1px solid #ccc; height:100%;'></div>", unsafe_allow_html=True)

    # --- Bloc centre ---
    with col_center:
        st.markdown("<div class='block-title'>Choix du temps d’injection (en s)</div>", unsafe_allow_html=True)
        injection_modes = ["Portal", "Artériel"]
        if cfg.get("intermediate_enabled", False):
            injection_modes.append("Intermédiaire")

        injection_mode = st.radio("Mode d'injection", injection_modes,
                                  horizontal=True, index=0, key="injection_mode_patient",
                                  label_visibility="collapsed")

        # Gestion des temps selon mode
        if injection_mode == "Portal":
            base_time = float(cfg.get("portal_time", 30.0))
        elif injection_mode == "Artériel":
            base_time = float(cfg.get("arterial_time", 25.0))
        else:
            base_time = st.number_input("⏱ Temps intermédiaire (s)",
                                        min_value=5.0, max_value=120.0, step=0.5,
                                        value=float(cfg.get("intermediate_time", 28.0)),
                                        key="inter_input")
            st.warning("⚠️ Attention : adaptez votre départ d’acquisition.")

        acquisition_start = calculate_acquisition_start(age, cfg)
        arterial_line = (
            f"<br><b>Départ acquisition en artériel :</b> {cfg.get('arterial_acq_time', 25.0):.1f} s"
            if cfg.get('arterial_acq_enabled', True) else ""
        )
        st.markdown(
            f"<div style='text-align:center; font-size:15px; color:#123A5F;'>"
            f"<b>Temps {injection_mode.lower()} :</b> {base_time:.1f} s<br>"
            f"<b>Départ acquisition en portal :</b> {acquisition_start:.1f} s"
            f"{arterial_line}</div>",
            unsafe_allow_html=True
        )

    with col_div2:
        st.markdown("<div style='border-left:1px solid #ccc; height:100%;'></div>", unsafe_allow_html=True)

    # --- Bloc droit ---
    with col_right:
        st.markdown("<div class='block-title'>Options avancées</div>", unsafe_allow_html=True)
        auto_age = bool(cfg.get("auto_acquisition_by_age", True))
        st.markdown(
            f"<div style='text-align:center; font-size:15px; color:#123A5F;'>"
            f"<b>Ajustement automatique selon l'âge :</b><br>"
            f"{'✅ activé' if auto_age else '❌ désactivé'}</div>",
            unsafe_allow_html=True
        )
    # === Calculs volumes et débits ===
    volume, bsa = calculate_volume(
        weight, height, kv_scanner,
        float(cfg.get("concentration_mg_ml", 350)),
        imc, cfg.get("calc_mode", "Charge iodée"),
        cfg.get("charges", {}),
        float(cfg.get("volume_max_limit", 200.0))
    )
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(
        volume, float(base_time), float(cfg.get("max_debit", 6.0))
    )

    st.markdown("---")

    sim_enabled = bool(cfg.get("simultaneous_enabled", False))
    delta_debit = float(cfg.get("rincage_delta_debit", 0.5))
    vol_rincage = float(cfg.get("rincage_volume", 35.0))
    debit_rincage = max(0.1, injection_rate - delta_debit)

    concentration = float(cfg.get("concentration_mg_ml", 350))
    target_concentration = float(cfg.get("target_concentration", concentration))

    if sim_enabled and target_concentration < concentration:
        pct_contrast = round((target_concentration / concentration) * 100, 1)
        pct_nacl = round(100 - pct_contrast, 1)
        vol_contrast_effectif = round(volume * pct_contrast / 100)
        vol_dilution_nacl = round(volume * pct_nacl / 100)
        st.info(
            f"🧪 Injection simultanée activée — "
            f"{pct_contrast:.1f}% contraste + {pct_nacl:.1f}% NaCl pour atteindre {target_concentration:.0f} mg I/mL."
        )
    else:
        pct_contrast = 100
        pct_nacl = 0
        vol_contrast_effectif = round(volume)
        vol_dilution_nacl = 0

    green_drop = "<svg width='20' height='20' viewBox='0 0 24 24' fill='#2E7D32'><path d='M12 2C12 2 5 10 5 15.5C5 19.09 8.13 22 12 22C15.87 22 19 19.09 19 15.5C19 10 12 2 12 2Z'/></svg>"
    blue_drop = "<svg width='20' height='20' viewBox='0 0 24 24' fill='#1565C0'><path d='M12 2C12 2 5 10 5 15.5C5 19.09 8.13 22 12 22C15.87 22 19 19.09 19 15.5C19 10 12 2 12 2Z'/></svg>"

    col_contrast, col_nacl = st.columns(2)

    with col_contrast:
        st.markdown(f"""
            <div style='background-color:#E8F5E9;
                        border-left:6px solid #2E7D32;
                        border-radius:12px;
                        padding:18px;
                        text-align:center;
                        box-shadow:0 1px 4px rgba(0,0,0,0.08);'>
                <h4 style='margin-top:0; color:#1B5E20; font-weight:700; display:flex; justify-content:center; align-items:center; gap:6px;'>
                    {green_drop} Volume et Débit de contraste conseillé
                </h4>
                <div style='font-size:22px; color:#1B5E20; font-weight:600; margin-top:8px;'>
                    {vol_contrast_effectif} mL — {injection_rate:.1f} mL/s
                </div>
                {"<div style='font-size:18px; color:#1B5E20; margin-top:6px;'>→ " +
                 f"{pct_contrast:.1f}% du mélange total" + "</div>" if sim_enabled else ""}
            </div>
        """, unsafe_allow_html=True)

    with col_nacl:
        if sim_enabled:
            st.markdown(f"""
                <div style='background-color:#E3F2FD;
                            border-left:6px solid #1565C0;
                            border-radius:12px;
                            padding:18px;
                            text-align:center;
                            box-shadow:0 1px 4px rgba(0,0,0,0.08);'>
                    <h4 style='margin-top:0; color:#0D47A1; font-weight:700; display:flex; justify-content:center; align-items:center; gap:6px;'>
                        {blue_drop} Volume et Débit de NaCl conseillé
                    </h4>
                    <div style='font-size:18px; color:#0D47A1; font-weight:600; margin-top:8px;'>
                        Dilution : <b>{pct_nacl:.1f}%</b> — {vol_dilution_nacl} mL
                    </div>
                    <div style='font-size:18px; color:#0D47A1; font-weight:600; margin-top:8px;'>
                        Rinçage : <b>{int(vol_rincage)}</b> mL — {debit_rincage:.1f} mL/s
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
                <div style='background-color:#E3F2FD;
                            border-left:6px solid #1565C0;
                            border-radius:12px;
                            padding:18px;
                            text-align:center;
                            box-shadow:0 1px 4px rgba(0,0,0,0.08);'>
                    <h4 style='margin-top:0; color:#0D47A1; font-weight:700; display:flex; justify-content:center; align-items:center; gap:6px;'>
                        {blue_drop} Volume et Débit de NaCl conseillé
                    </h4>
                    <div style='font-size:22px; color:#0D47A1; font-weight:600; margin-top:8px;'>
                        {int(vol_rincage)} mL — {debit_rincage:.1f} mL/s
                    </div>
                </div>
            """, unsafe_allow_html=True)

    if time_adjusted:
        st.warning(f"⚠️ Temps ajusté à {injection_time:.1f}s (max {float(cfg.get('max_debit',6.0)):.1f} mL/s).")

    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

    concentration_mg_ml = float(cfg.get("concentration_mg_ml", 350))
    concentration_g_ml = concentration_mg_ml / 1000.0
    calc_mode = cfg.get("calc_mode", "Charge iodée")
    charge_iod = float(cfg.get("charges", {}).get(str(kv_scanner), 0.45))

    if calc_mode == "Charge iodée":
        calc_str = f"({weight} × {charge_iod:.2f}) ÷ ({concentration_mg_ml}/1000)"
        volume_calc = weight * charge_iod / concentration_g_ml
    elif calc_mode.startswith("Charge iodée sauf") and imc >= 30:
        kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
        factor = kv_factors.get(kv_scanner, 15)
        calc_str = f"({bsa:.2f} × {factor}) ÷ ({concentration_mg_ml}/1000)"
        volume_calc = bsa * factor / concentration_g_ml
    elif calc_mode == "Surface corporelle" and bsa:
        kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
        factor = kv_factors.get(kv_scanner, 15)
        calc_str = f"({bsa:.2f} × {factor}) ÷ ({concentration_mg_ml}/1000)"
        volume_calc = bsa * factor / concentration_g_ml
    else:
        calc_str = f"({weight} × {charge_iod:.2f}) ÷ ({concentration_mg_ml}/1000)"
        volume_calc = weight * charge_iod / concentration_g_ml

    debit_calc = volume_calc / float(base_time)
    debit_str = f"{volume_calc:.1f} ÷ {base_time:.1f}"

    st.markdown(f"""
        <div style='text-align:center; margin-top:12px;
                    font-size:15px; color:#123A5F; line-height:1.6;'>
            <b>🧮 Volume contraste :</b> {calc_str} = <b>{volume_calc:.1f} mL</b><br>
            <b>🚀 Débit contraste :</b> {debit_str} = <b>{debit_calc:.2f} mL/s</b>
        </div>
    """, unsafe_allow_html=True)
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
        # === Référence officielle ===
    st.markdown("---")
    st.header("📚 Référence officielle")
    st.markdown("""
    Les calculs de volume, de débit et de concentration utilisés dans cette calculette 
    sont basés sur les recommandations du **CIRTACI – version 5_3_0** (Groupe de Travail de la SFR).

    🔗 [Consulter la fiche officielle du CIRTACI – Généralités ONCO (PDF)](https://www.radiologie.fr/sites/www.radiologie.fr/files/medias/documents/CIRTACI%20Fiche%20Généralités%20ONCO_5_3_0.pdf)
    """)
    st.header("🩺 Exemple de workflow clinique")
    st.markdown("""
    Patient 75 kg, 170 cm, kV=120, charge iodée 0.5, mode Portal, concentration 350 mg I/mL.
    Exemple volume : (75x0.5)/0.35 ≈ 107 mL
    """)
# ------------------------
# Footer
# ------------------------
st.markdown(f"""
<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Calculette de dose de produit de contraste en oncologie adulte.<br>
Basée sur les recommandations du 
<a href="https://www.radiologie.fr/sites/www.radiologie.fr/files/medias/documents/CIRTACI%20Fiche%20Généralités%20ONCO_5_3_0.pdf" target="_blank">
<b>CIRTACI – version 5_3_0</b></a>.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>
🧪 Version BETA TEST – Usage interne / évaluation
</div>
</div>
""", unsafe_allow_html=True)
