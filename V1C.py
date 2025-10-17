# ------------------------
# Onglet Patient (version réorganisée finale)
# ------------------------
with tab_patient:
    import datetime
    st.markdown("""
        <style>
        /* === STYLE GÉNÉRAL === */
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
        st.markdown(f"<p style='text-align:center;color:#E53935;font-weight:600;font-size:18px'>{weight}</p>", unsafe_allow_html=True)

    with col_taille:
        height = st.slider("Taille (cm)", 100, 220, 170)
        st.markdown(f"<p style='text-align:center;color:#E53935;font-weight:600;font-size:18px'>{height}</p>", unsafe_allow_html=True)

    current_year = datetime.datetime.now().year
    with col_annee:
        birth_year = st.slider("Année de naissance", current_year - 120, current_year, 1985)
        st.markdown(f"<p style='text-align:center;color:#E53935;font-weight:600;font-size:18px'>{birth_year}</p>", unsafe_allow_html=True)

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

    # === LIGNE 2 : Trois blocs (séparés par lignes grises) ===
    col_left, col_div1, col_center, col_div2, col_right = st.columns([1.2, 0.05, 1.2, 0.05, 1.2])

    # Bloc gauche : Mode d’injection + kV
    with col_left:
        st.markdown("### Mode d’injection")
        injection_modes = ["Portal", "Artériel", "Intermédiaire"]
        injection_mode = st.radio("", injection_modes, horizontal=True, index=2)

        st.markdown("### kV du scanner")
        kv_scanner = st.radio("", [80, 90, 100, 110, 120], horizontal=True, index=4)

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
