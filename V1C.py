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
# Onglet Paramètres (gestion sessions + programmes personnels uniquement)
# ------------------------
with tab_params:
    st.header("⚙️ Paramètres et Bibliothèque (personnelle)")
    user_id = st.session_state["user_id"]
    cfg = get_cfg()

    cfg["simultaneous_enabled"] = st.checkbox("Activer l'injection simultanée", value=cfg.get("simultaneous_enabled", False))
    if cfg["simultaneous_enabled"]:
        cfg["target_concentration"] = st.number_input("Concentration cible (mg I/mL)", value=int(cfg.get("target_concentration", 350)), min_value=200, max_value=500, step=10)

    st.subheader("📚 Vos programmes personnels")
    personal_programs = user_sessions.get(user_id, {}).get("programs", {})
    program_choice = st.selectbox("Programme (Personnel)", ["Aucun"] + list(personal_programs.keys()), key="prog_params_personal")
    if program_choice != "Aucun":
        prog_conf = personal_programs.get(program_choice, {})
        for key, val in prog_conf.items():
            cfg[key] = val

    new_prog_name = st.text_input("Nom du nouveau programme (sera enregistré dans vos programmes personnels)")
    if st.button("💾 Ajouter/Mise à jour programme"):
        if new_prog_name.strip():
            to_save = {k: cfg[k] for k in cfg}
            user_sessions.setdefault(user_id, {}).setdefault("programs", {})[new_prog_name.strip()] = to_save
            user_sessions.setdefault(user_id, {})["config"] = cfg.copy()
            save_user_sessions(user_sessions)
            st.success(f"Programme personnel '{new_prog_name}' ajouté/mis à jour pour l'identifiant '{user_id}' !")
        else:
            st.warning("Donnez un nom au programme.")

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

    st.markdown("---")
    st.subheader("Paramètres (enregistrés dans votre espace personnel)")
    cfg["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)", [300, 320, 350, 370, 400], index=[300, 320, 350, 370, 400].index(int(cfg.get("concentration_mg_ml", 350))))
    cfg["calc_mode"] = st.selectbox("Méthode de calcul", ["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"].index(cfg.get("calc_mode", "Charge iodée")))
    cfg["max_debit"] = st.number_input("Débit maximal autorisé (mL/s)", value=float(cfg.get("max_debit", 6.0)), min_value=1.0, max_value=20.0, step=0.1)
    cfg["portal_time"] = st.number_input("Portal (s)", value=float(cfg.get("portal_time", 30.0)), min_value=5.0, max_value=120.0, step=1.0)
    cfg["arterial_time"] = st.number_input("Artériel (s)", value=float(cfg.get("arterial_time", 25.0)), min_value=5.0, max_value=120.0, step=1.0)
    cfg["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=bool(cfg.get("intermediate_enabled", False)))
    if cfg["intermediate_enabled"]:
        cfg["intermediate_time"] = st.number_input("Intermédiaire (s)", value=float(cfg.get("intermediate_time", 28.0)), min_value=5.0, max_value=120.0, step=1.0)
    cfg["rincage_volume"] = st.number_input("Volume rinçage (mL)", value=float(cfg.get("rincage_volume", 35.0)), min_value=10.0, max_value=100.0, step=1.0)
    cfg["rincage_delta_debit"] = st.number_input("Δ débit NaCl vs contraste (mL/s)", value=float(cfg.get("rincage_delta_debit", 0.5)), min_value=0.1, max_value=5.0, step=0.1)
    cfg["volume_max_limit"] = st.number_input("Plafond volume (mL) - seringue", value=float(cfg.get("volume_max_limit", 200.0)), min_value=50.0, max_value=500.0, step=10.0)

    st.markdown("**Charges en iode par kV (g I/kg)**")
    df_charges = pd.DataFrame({
        "kV": [80, 90, 100, 110, 120],
        "Charge (g I/kg)": [float(cfg["charges"].get(str(kv), 0.35)) for kv in [80, 90, 100, 110, 120]]
    })
    edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True)
    if st.button("💾 Sauvegarder les paramètres"):
        try:
            cfg["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _, row in edited_df.iterrows()}
            # Persister dans l'espace utilisateur (indépendant)
            set_cfg_and_persist(user_id, cfg)
            st.success("✅ Paramètres sauvegardés dans votre espace utilisateur !")
        except Exception as e:
            st.error(f"Erreur lors de la sauvegarde : {e}")

    # gestion des sessions / suppression (ici dans Paramètres)
    st.markdown("---")
    st.subheader("🗂 Gestion des sessions / identifiants")
    st.markdown("Les identifiants sont indépendants. Vos programmes et paramètres personnels ne sont accessibles qu'avec votre identifiant.")

    all_user_ids = sorted(list(user_sessions.keys()))

    # Si super user : voir tout, supprimer tout (sauf protection suppression identifiant en cours d'utilisation)
    if user_id == SUPER_USER:
        st.markdown("**Super-utilisateur : accès à tous les identifiants**")
        st.write("Liste des identifiants existants :")
        # display with optional email column
        df_users = pd.DataFrame([{"identifiant": uid, "email": user_sessions[uid].get("email")} for uid in all_user_ids])
        st.dataframe(df_users, use_container_width=True)
        st.markdown("**Supprimer un identifiant** — saisissez le nom exact de l'identifiant à supprimer")
        del_input = st.text_input("Identifiant à supprimer (exact)", key="del_input_admin")
        if st.button("🗑 Supprimer identifiant (super-utilisateur)"):
            target = del_input.strip()
            if not target:
                st.warning("Veuillez saisir l'identifiant à supprimer.")
            elif target == user_id:
                st.error("⚠️ Impossible de supprimer l'identifiant en cours (super-utilateur connecté).")
            elif target not in user_sessions:
                st.error("Identifiant introuvable.")
            else:
                del user_sessions[target]
                save_user_sessions(user_sessions)
                st.success(f"Identifiant '{target}' supprimé par le super-utilisateur.")
    else:
        st.markdown("Seul le super-utilisateur peut lister tous les identifiants.")
        st.markdown("**Supprimer VOTRE identifiant** — saisissez EXACTEMENT votre identifiant pour confirmer.")
        del_input_self = st.text_input("Confirmez votre identifiant pour supprimer votre compte (exact)", key="del_input_self")
        if st.button("🗑 Supprimer MON identifiant"):
            target = del_input_self.strip()
            if not target:
                st.warning("Veuillez saisir votre identifiant exact pour confirmer.")
            elif target != user_id:
                st.error("Le nom saisi ne correspond pas à l'identifiant connecté.")
            else:
                # suppression autorisée — supprimer puis déconnecter
                try:
                    if user_id in user_sessions:
                        del user_sessions[user_id]
                        save_user_sessions(user_sessions)
                    st.session_state["accepted_legal"] = False
                    st.session_state["user_id"] = None
                    st.session_state["user_config"] = config_global.copy()
                    st.success("Votre identifiant a été supprimé. Vous avez été déconnecté.")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Erreur suppression identifiant : {e}")

# ------------------------
# Onglet Patient (version finale réorganisée avec largeur équilibrée)
# ------------------------
with tab_patient:
    import datetime
    st.markdown("""
        <style>
        /* === STYLE === */
        .slider-red .stSlider [data-baseweb="slider"] div[role="slider"] {
            background-color: #E53935 !important;
        }
        .slider-red .stSlider [data-baseweb="slider"] div[role="slider"]::before {
            background-color: #E53935 !important;
        }
        .divider {
            border-left: 1px solid #d9d9d9;
            height: 100%;
            margin: 0 20px;
        }
        .info-block {
            background: #F5F8FC;
            border-radius: 10px;
            padding: 15px 20px;
            text-align: center;
            color: #123A5F;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        .section-title {
            font-size: 22px;
            font-weight: 700;
            color: #123A5F;
            margin-bottom: 15px;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='section-title'>🧍 Informations patient (adulte en oncologie)</div>", unsafe_allow_html=True)

    # === LIGNE 1 : Poids / Taille / Année / Programme ===
    st.markdown("<div class='slider-red'>", unsafe_allow_html=True)
    col_poids, col_taille, col_annee, col_prog = st.columns([1, 1, 1, 1.3])

    with col_poids:
        weight = st.slider("Poids (kg)", 20, 200, 70)

    with col_taille:
        height = st.slider("Taille (cm)", 100, 220, 170)

    current_year = datetime.datetime.now().year
    with col_annee:
        birth_year = st.slider("Année de naissance", current_year - 120, current_year, 1985)

    with col_prog:
        user_id = st.session_state["user_id"]
        user_programs = user_sessions.get(user_id, {}).get("programs", {})
        prog_choice_patient = st.selectbox(
            "Sélection d'un programme",
            ["Sélection d'un programme"] + list(user_programs.keys()),
            index=0
        )
        if prog_choice_patient != "Sélection d'un programme":
            prog_conf = user_programs.get(prog_choice_patient, {})
            cfg = get_cfg()
            for key, val in prog_conf.items():
                cfg[key] = val
            set_cfg_and_persist(user_id, cfg)
            user_sessions[user_id]["last_selected_program"] = prog_choice_patient
            save_user_sessions(user_sessions)
    st.markdown("</div>", unsafe_allow_html=True)

    # Variables de base
    cfg = get_cfg()
    age = current_year - birth_year
    imc = weight / ((height / 100) ** 2)

    # === LIGNE 2 : Trois blocs avec lignes de séparation ===
    col_left, col_div1, col_center, col_div2, col_right = st.columns([1.2, 0.05, 1.2, 0.05, 1.2])

   
# Bloc gauche : Mode d’injection + kV du scanner dans le même encart
with col_left:
    st.markdown("""
        <style>
        .left-panel {
            background-color: #EAF1F8;
            padding: 15px 20px;
            border-radius: 10px;
            min-height: 230px; /* même hauteur que le bloc du milieu */
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .left-panel h3 {
            font-size: 1rem;
            color: #123A5F;
            text-align: center;
            margin-bottom: 0.5rem;
        }
        .left-panel hr {
            border: 0;
            border-top: 1px solid rgba(0,0,0,0.08);
            margin: 10px 0;
        }
        .compact-radio label {
            font-size: 0.85rem !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # --- Bloc visuel homogène ---
    st.markdown("<div class='left-panel'>", unsafe_allow_html=True)

    # ---- Mode d’injection ----
    st.markdown("<h3>Mode d’injection</h3>", unsafe_allow_html=True)
    injection_modes = ["Portal", "Artériel"]
    if cfg.get("intermediate_enabled", False):
        injection_modes.append("Intermédiaire")

    st.markdown("<div class='compact-radio'>", unsafe_allow_html=True)
    injection_mode = st.radio("", injection_modes, horizontal=True, label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

    # ---- Séparateur visuel ----
    st.markdown("<hr>", unsafe_allow_html=True)

    # ---- kV du scanner ----
    st.markdown("<h3>kV du scanner</h3>", unsafe_allow_html=True)
    st.markdown("<div class='compact-radio'>", unsafe_allow_html=True)
    kv_scanner = st.radio("", [80, 90, 100, 110, 120], horizontal=True, index=4, label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


    # Ligne de séparation
    with col_div1:
        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    # Bloc central : Méthode utilisée
    with col_center:
        charge_iod = float(cfg.get("charges", {}).get(str(kv_scanner), 0.45))
        st.markdown(f"""
            <div class='info-block'>
                <b>Méthode utilisée :</b> Charge iodée<br>
                Charge iodée appliquée (kV {kv_scanner}) : {charge_iod:.2f} g I/kg<br>
                <span style='color:#555;'>Ajustement automatique du départ d'acquisition selon l'âge activé</span><br>
                <span style='color:#555;'>Injection simultanée activée</span>
            </div>
        """, unsafe_allow_html=True)

    # Ligne de séparation
    with col_div2:
        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    # Bloc droit : Temps / Concentration
    with col_right:
        if injection_mode == "Portal":
            base_time = float(cfg.get("portal_time", 30.0))
        elif injection_mode == "Artériel":
            base_time = float(cfg.get("arterial_time", 25.0))
        else:
            base_time = float(cfg.get("intermediate_time", 28.0))

        acquisition_start = calculate_acquisition_start(age, cfg)
        concentration = int(cfg.get("concentration_mg_ml", 350))

        st.markdown(f"""
            <div class='info-block'>
                <b>Temps {injection_mode.lower()} :</b> {base_time:.0f} s<br>
                <b>Départ d'acquisition :</b> {acquisition_start:.1f} s<br>
                <b>Concentration utilisée :</b> {concentration} mg I/mL
            </div>
        """, unsafe_allow_html=True)


    # --- Calculs inchangés ---
    volume, bsa = calculate_volume(weight, height, kv_scanner, float(cfg.get("concentration_mg_ml", 350)), imc, cfg.get("calc_mode", "Charge iodée"), cfg.get("charges", {}), float(cfg.get("volume_max_limit", 200.0)))
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume, float(base_time), float(cfg.get("max_debit", 6.0)))

    if cfg.get("simultaneous_enabled", False):
        target = float(cfg.get("target_concentration", 350))
        current_conc = float(cfg.get("concentration_mg_ml", 350))
        if target > current_conc:
            target = current_conc
        vol_contrast = volume * (target/current_conc) if current_conc > 0 else volume
        vol_nacl_dilution = max(0.0, volume - vol_contrast)
        contrast_text = f"{int(round(vol_contrast))} mL"
        nacl_text = f"{int(round(vol_nacl_dilution + cfg.get('rincage_volume', 35.0)))} mL"
    else:
        vol_contrast = volume
        contrast_text = f"{int(round(vol_contrast))} mL"
        nacl_text = f"{int(round(cfg.get('rincage_volume', 35.0)))} mL"

    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"<div class='info-block'><h4>💧 Volume contraste conseillé</h4><h2>{contrast_text}</h2></div>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<div class='info-block'><h4>💧 Volume NaCl conseillé</h4><h2>{nacl_text}</h2></div>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<div class='info-block'><h4>🚀 Débit conseillé</h4><h2>{injection_rate:.1f} mL/s</h2></div>", unsafe_allow_html=True)

    if time_adjusted:
        st.warning(f"⚠️ Temps d’injection ajusté à {injection_time:.1f}s pour respecter le débit maximal de {cfg.get('max_debit',6.0)} mL/s.")

    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

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
