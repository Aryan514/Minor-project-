# report/references.py
# APA 7th-edition reference list of the report. Bibliographic details were checked against publisher / DOI records
# (Crossref, IEEE, Inderscience, Elsevier, BEEI, IJACSA, PyPI, opcfoundation.org, semi.org). Where an edition year
# could not be confirmed (SEMI standards, vendor pages), "n.d." is used rather than a guessed year.
"""Reference data: key -> in-text citation, narrative form, sort key, full APA entry (*italic* markup)."""

REFS = {
    "agileo20": dict(cite="Agileo Automation, 2020", narrative="Agileo Automation (2020)", sort="agileo",
                     apa="Agileo Automation. (2020, December). *Addressing interoperability issues in factories using SECS/GEM "
                         "and OPC-UA*. https://www.agileo.com/en/resources/addressing-interoperability-issues-factories-using-secsgem-and-opc-ua"),
    "azaiez19": dict(cite="Azaiez et al., 2019", narrative="Azaiez et al. (2019)", sort="azaiez",
                     apa="Azaiez, S., Tanguy, F., & Engel, M. (2019). Towards building OPC-UA companions for semi-conductor "
                         "domain. In *2019 24th IEEE International Conference on Emerging Technologies and Factory Automation "
                         "(ETFA)* (pp. 142–149). IEEE. https://doi.org/10.1109/ETFA.2019.8869171"),
    "busboom24": dict(cite="Busboom, 2024", narrative="Busboom (2024)", sort="busboom",
                      apa="Busboom, A. (2024). Automated generation of OPC UA information models — A review and outlook. "
                          "*Journal of Industrial Information Integration, 39*, Article 100602. https://doi.org/10.1016/j.jii.2024.100602"),
    "ergotech": dict(cite="ErgoTech Systems, n.d.", narrative="ErgoTech Systems (n.d.)", sort="ergotech",
                     apa="ErgoTech Systems. (n.d.). *TransSECS for an OPCUA server: Using TransSECS to create an OPCUA SECS/GEM "
                         "tool interface* [User guide]. https://ergotech.com/docs/TransSECSOPCUAServerGuide.pdf"),
    "fitri25": dict(cite="Fitri et al., 2025", narrative="Fitri et al. (2025)", sort="fitri",
                    apa="Fitri, M. S. K., Manickam, S., Laghari, S. U. A., Chia, S. K., Ishak, M. K., & Karuppayah, S. (2025). "
                        "Enabling SECS/GEM in legacy equipment: A proof of concept. *Bulletin of Electrical Engineering and "
                        "Informatics, 14*(5), 3439–3451. https://doi.org/10.11591/eei.v14i5.9516"),
    "asyncua": dict(cite="FreeOpcUa, 2025", narrative="FreeOpcUa (2025)", sort="freeopcua",
                    apa="FreeOpcUa. (2025). *asyncua (opcua-asyncio)* (Version 1.1.8) [Computer software]. "
                        "https://github.com/FreeOpcUa/opcua-asyncio"),
    "golra20": dict(cite="Golra et al., 2020", narrative="Golra et al. (2020)", sort="golra 1 azaiez",
                    apa="Golra, F. R., Azaiez, S., & Engel, M. (2020). Multi-level modeling to OPC UA for migrating to "
                        "Industry 4.0 in semiconductor manufacturing. In *2020 IEEE Conference on Industrial Cyberphysical "
                        "Systems (ICPS)* (pp. 589–595). IEEE. https://doi.org/10.1109/ICPS48405.2020.9274791"),
    "golra21": dict(cite="Golra & Engel, 2021", narrative="Golra and Engel (2021)", sort="golra 2 engel",
                    apa="Golra, F. R., & Engel, M. (2021). An industrial feedback on the use of OPC UA for the vertical "
                        "integration of semiconductor front-ends. In *2021 26th IEEE International Conference on Emerging "
                        "Technologies and Factory Automation (ETFA)* (pp. 1–4). IEEE. https://doi.org/10.1109/ETFA45728.2021.9613384"),
    "laghari21": dict(cite="Laghari et al., 2021", narrative="Laghari et al. (2021)", sort="laghari 2021",
                      apa="Laghari, S. U. A., Manickam, S., Al-Ani, A. K., Ul Rehman, S., & Karuppayah, S. (2021). SECS/GEMsec: "
                          "A mechanism for detection and prevention of cyber-attacks on SECS/GEM communications in Industry 4.0 "
                          "landscape. *IEEE Access, 9*, 154380–154394. https://doi.org/10.1109/ACCESS.2021.3127515"),
    "laghari23": dict(cite="Laghari et al., 2023", narrative="Laghari et al. (2023)", sort="laghari 2023",
                      apa="Laghari, S. U. A., Manickam, S., Al-Ani, A. K., Al-Shareeda, M. A., & Karuppayah, S. (2023). "
                          "ES-SECS/GEM: An efficient security mechanism for SECS/GEM communications. *IEEE Access, 11*, "
                          "31813–31828. https://doi.org/10.1109/ACCESS.2023.3262310"),
    "matischek19": dict(cite="Matischek & Bara, 2019", narrative="Matischek and Bara (2019)", sort="matischek",
                        apa="Matischek, R., & Bara, B. (2019). Application study of hardware-based security for future "
                            "industrial IoT. In *2019 22nd Euromicro Conference on Digital System Design (DSD)* (pp. 246–252). "
                            "IEEE. https://doi.org/10.1109/DSD.2019.00044"),
    "opcf20": dict(cite="OPC Foundation, 2020", narrative="OPC Foundation (2020)", sort="opc foundation 2020",
                   apa="OPC Foundation. (2020). *OPC Day 2020: Questions & answers* [PDF]. "
                       "https://opcfoundation.org/wp-content/uploads/2020/09/OPC-Day-2020-QuestionAnswers.pdf"),
    "opcua1": dict(cite="OPC Foundation, 2025a", narrative="OPC Foundation (2025a)", sort="opc foundation 2025a",
                   apa="OPC Foundation. (2025a). *OPC 10000-1: OPC Unified Architecture – Part 1: Overview and concepts* "
                       "(Version 1.05.06). https://reference.opcfoundation.org/specs/OPC-10000-1"),
    "opcua3": dict(cite="OPC Foundation, 2025b", narrative="OPC Foundation (2025b)", sort="opc foundation 2025b",
                   apa="OPC Foundation. (2025b). *OPC 10000-3: OPC Unified Architecture – Part 3: Address space model* "
                       "(Version 1.05.06). https://reference.opcfoundation.org/specs/OPC-10000-3"),
    "opcua5": dict(cite="OPC Foundation, 2025c", narrative="OPC Foundation (2025c)", sort="opc foundation 2025c",
                   apa="OPC Foundation. (2025c). *OPC 10000-5: OPC Unified Architecture – Part 5: Information model* "
                       "(Version 1.05.06). https://reference.opcfoundation.org/specs/OPC-10000-5"),
    "opcua9": dict(cite="OPC Foundation, 2025d", narrative="OPC Foundation (2025d)", sort="opc foundation 2025d",
                   apa="OPC Foundation. (2025d). *OPC 10000-9: OPC Unified Architecture – Part 9: Alarms & conditions* "
                       "(Version 1.05.06). https://reference.opcfoundation.org/specs/OPC-10000-9"),
    "opcua4": dict(cite="OPC Foundation, 2026", narrative="OPC Foundation (2026)", sort="opc foundation 2026",
                   apa="OPC Foundation. (2026). *OPC 10000-4: OPC Unified Architecture – Part 4: Services* (Version 1.05.07). "
                       "https://reference.opcfoundation.org/specs/OPC-10000-4"),
    "secsgem": dict(cite="Parzella, 2024", narrative="Parzella (2024)", sort="parzella",
                    apa="Parzella, B. (2024). *secsgem* (Version 0.3.0) [Computer software]. https://github.com/bparzella/secsgem"),
    "e30": dict(cite="SEMI, n.d.-a", narrative="SEMI (n.d.-a)", sort="semi a",
                apa="SEMI. (n.d.-a). *SEMI E30 – Specification for the generic model for communications and control of "
                    "manufacturing equipment (GEM)*. https://store-us.semi.org/products/e03000-semi-e30-specification-for-the-generic-model-for-communications-and-control-of-manufacturing-equipment-gem"),
    "e37": dict(cite="SEMI, n.d.-b", narrative="SEMI (n.d.-b)", sort="semi b",
                apa="SEMI. (n.d.-b). *SEMI E37 – Specification for High-Speed SECS Message Services (HSMS) generic services*. "
                    "https://store-us.semi.org/products/e03700-semi-e37-high-speed-secs-message-services-hsms-generic-services"),
    "e5": dict(cite="SEMI, n.d.-c", narrative="SEMI (n.d.-c)", sort="semi c",
               apa="SEMI. (n.d.-c). *SEMI E5 – Specification for SEMI Equipment Communications Standard 2 message content "
                   "(SECS-II)*. https://store-us.semi.org/products/e00500-semi-e5-specification-for-semi-equipment-communications-standard-2-message-content-secs-ii"),
    "eda": dict(cite="SEMI, n.d.-d", narrative="SEMI (n.d.-d)", sort="semi d",
                apa="SEMI. (n.d.-d). *Smart manufacturing standards* (including SEMI E120, E125, E132 and E134). "
                    "https://www.semi.org/en/industry-groups/smart-manufacturing/standards"),
    "stoop19": dict(cite="Stoop et al., 2019", narrative="Stoop et al. (2019)", sort="stoop",
                    apa="Stoop, F., Ely, G., Menna, R., Charache, G., Gittler, T., & Wegener, K. (2019). Smart factory "
                        "equipment integration through standardised OPC UA communication with companion specifications and "
                        "equipment specific information models. *International Journal of Mechatronics and Manufacturing "
                        "Systems, 12*(3/4), 344–364. https://doi.org/10.1504/IJMMS.2019.103499"),
    "sun21": dict(cite="Sun et al., 2021", narrative="Sun et al. (2021)", sort="sun",
                  apa="Sun, Y., Peng, X., Zhu, M., Jiao, D., & Fuyang, S. (2021). Design and implementation of OPC UA server "
                      "based on SECS/GEM protocol. In *2021 International Conference on Wireless Communications and Smart Grid "
                      "(ICWCSG)* (pp. 38–42). IEEE. https://doi.org/10.1109/ICWCSG53609.2021.00015"),
}
