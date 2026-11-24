# report/content_lit.py
# Chapter 3 (literature review) of the report. Each summary states only what could be verified from the publisher
# record, abstract or page of the cited work; where only the abstract was available, the text says so or limits itself
# to what the abstract states. Statements about what a work does not cover are phrased as "not reported in the
# material we reviewed", never as a claim made by its authors.
"""Report chapter 3."""

from __future__ import annotations


def chapter_3():
    b = [("h1", "CHAPTER 3: LITERATURE REVIEW")]
    b += [("p", "The review covers three groups of work: OPC UA information models for the semiconductor domain, translators "
                "and gateways between SECS/GEM and OPC UA, and adjacent work on equipment integration, security and model "
                "generation. For each work we summarise what it established and what, in the material we could review, it "
                "leaves open with respect to the questions of this project. Several papers were accessible to us only "
                "through their publisher abstracts; in those cases our summary is limited to what the abstract states."),
          ("h2", "3.1 OPC UA information models for the semiconductor domain"),
          ("h3", "3.1.1 Azaiez et al. (2019)"),
          ("p", "⟦azaiez19|n⟧ compared SECS/GEM with OPC UA and concluded that the two are complementary rather than competing. "
                "They proposed a model-driven route from the SECS/GEM specification stack to OPC UA in three steps: describing "
                "the standards as UML models, generating the services that host and equipment interfaces must expose, and "
                "generating a SECS/GEM-specific OPC UA address space that can be deployed on OPC UA servers. The work "
                "established that GEM concepts can be expressed systematically in an OPC UA information model and framed this "
                "as a step towards companion specifications for the semiconductor domain. The abstract does not address a tool "
                "that serves both interfaces at the same time, command authority between the two, or spooling."),
          ("h3", "3.1.2 Golra et al. (2020)"),
          ("p", "⟦golra20|n⟧ pursued two goals: a comprehensive metamodel of the SEMI communication interfaces, built with "
                "multi-level modelling, and a preliminary experiment using OPC UA as the communication architecture in "
                "semiconductor manufacturing while remaining as compliant with SEMI standards as possible. The work extended "
                "the model-driven approach towards migrating semiconductor manufacturing to Industry 4.0 architectures. In the "
                "material we reviewed, it does not report simultaneous operation of a native GEM interface and an OPC UA "
                "interface on one tool."),
          ("h3", "3.1.3 Golra and Engel (2021)"),
          ("p", "⟦golra21|n⟧ give industrial feedback on using OPC UA for the vertical integration of semiconductor front-end "
                "equipment. They note that OPC UA is becoming the leading interoperability architecture for Industry 4.0 while "
                "equipment makers must continue to follow SEMI standards, and that no OPC UA companion specification exists for "
                "the semiconductor domain. They compare architectural choices for building a semiconductor information model "
                "and report lessons learned from implementing OPC UA models in this domain. Their work is the closest to ours in "
                "subject. In the material we were able to review, the behaviour of a tool used through both interfaces "
                "simultaneously, the question of command authority between a GEM host and OPC UA clients, and the treatment of "
                "spooling are not reported; our work addresses these questions experimentally."),
          ("h3", "3.1.4 OPC Foundation (2020)"),
          ("p", "In the published questions and answers of its OPC Day 2020, the ⟦opcf20|n⟧ stated that there were at that time no "
                "OPC UA companion specifications for SEMI, and mentioned an initiative, then in a preparation phase, towards an "
                "OPC UA companion specification for SECS/GEM. This confirms that, at least as of 2020, an integrator offering "
                "OPC UA on a semiconductor tool had to define its own information model, which is the situation our draft model "
                "(N2) responds to. We make no claim about the status of such an initiative after 2020."),
          ("h2", "3.2 Translators and gateways between SECS/GEM and OPC UA"),
          ("h3", "3.2.1 Agileo Automation (2020)"),
          ("p", "⟦agileo20|n⟧ published a demonstration bridging a SECS/GEM process tool to an OPC UA-based MES. It uses a generic "
                "information model derived from SEMI E5, developed with CEA List within the Productive 4.0 project, and is built "
                "on the company's GEM library and the OPC Foundation .NET Standard stack. The MES polls variables such as "
                "temperature and pressure, sends remote commands (process-program select and start), and receives event "
                "reports configured dynamically. The demonstration shows that a practical bridge is feasible with industrial "
                "components. The page does not discuss simultaneous use of the native GEM interface and the OPC UA interface, "
                "command authority or spooling, which is consistent with its purpose as a bridge."),
          ("h3", "3.2.2 ErgoTech TransSECS"),
          ("p", "⟦ergotech|n⟧ offers TransSECS, a tool for building SECS/GEM equipment interfaces; its user guide describes how "
                "to create a SECS/GEM tool interface that is exposed as an OPC UA server for factory automation software. It "
                "represents the commercial availability of combined SECS/GEM and OPC UA interfaces. Product documentation does "
                "not, and need not, report experimental studies of authority or consistency between the two interfaces."),
          ("h3", "3.2.3 Sun et al. (2021)"),
          ("p", "⟦sun21|n⟧ describe the design and implementation of an OPC UA server based on the SECS/GEM protocol, intended to "
                "resolve data incompatibility between semiconductor manufacturing and other automation sectors. According to the "
                "abstract, which is the only part we could verify, the server was tested with third-party SECS/GEM equipment "
                "simulation software and an OPC UA client and achieved real-time communication with both. The work is a "
                "translation design; the abstract does not report an authority policy, consistency measurements or the "
                "handling of disconnections."),
          ("h2", "3.3 Adjacent work"),
          ("h3", "3.3.1 Stoop et al. (2019)"),
          ("p", "⟦stoop19|n⟧ present a generic method for integrating equipment with an MES through OPC UA and ISA-95, combining a "
                "companion specification, a dynamic address space and an OPC UA client characterisation process. The "
                "implementation was first developed for semiconductor back-end equipment and validated on a final-test unit for "
                "high-power laser diodes. The work shows how equipment-specific information models and companion specifications "
                "can be combined in practice; it does not involve SECS/GEM."),
          ("h3", "3.3.2 Matischek and Bara (2019)"),
          ("p", "⟦matischek19|n⟧ report an application study of secured communication between current and future stationary "
                "industrial devices using OPC UA, partly strengthened with hardware-based security. It is relevant to this project "
                "because OPC UA's security model is one of the reasons plant systems prefer it; our testbed runs OPC UA without "
                "security for the demonstration, which is listed as a limitation."),
          ("h3", "3.3.3 Laghari et al. (2021, 2023)"),
          ("p", "⟦laghari21|n⟧ proposed SECS/GEMsec, a digital-signature mechanism that adds authentication and integrity to "
                "SECS/GEM, blocks untrusted entities and discards forged messages, and showed resistance to denial-of-service, "
                "replay and false-data-injection attacks. ⟦laghari23|n⟧ followed with ES-SECS/GEM, a lightweight mechanism that "
                "allows only authorised equipment to connect and rejects forged messages with low processing time and control "
                "overhead. Both works start from the observation that SECS/GEM has no built-in security, which supports the "
                "comparison in Table 2.1. They do not consider OPC UA."),
          ("h3", "3.3.4 Fitri et al. (2025)"),
          ("p", "⟦fitri25|n⟧ propose a modular software framework that adds SECS/GEM to legacy machines without major hardware "
                "changes, using a Raspberry Pi and an Arduino as an intermediary between the machine and the factory network. "
                "The work illustrates that SECS/GEM remains the integration requirement for equipment on the fab floor, even "
                "for older machines; it does not involve OPC UA."),
          ("h3", "3.3.5 Busboom (2024)"),
          ("p", "⟦busboom24|n⟧ reviews approaches for generating OPC UA information models automatically from other models and "
                "gives an outlook on the field. It is relevant to future work on this project: our draft model is built in code, "
                "and exporting or generating it from a model description (for example as a NodeSet file) is listed as future "
                "work."),
          ("h2", "3.4 Gap analysis"),
          ("p", "Table 3.1 summarises the reviewed works against the questions this project addresses. An entry “not "
                "reported” means that the question is not addressed in the material we could review; it is not a "
                "statement that the authors excluded it."),
          ("table", "Gap analysis of the reviewed work",
           ["Work", "Main contribution", "Both interfaces natively from one core", "Command authority", "Consistency measured",
            "Loss on disconnect"],
           [["Azaiez et al. (2019)", "SECS/GEM to OPC UA model-driven translation", "not reported", "not reported",
             "not reported", "not reported"],
            ["Golra et al. (2020)", "metamodel of SEMI interfaces; OPC UA experiment", "not reported", "not reported",
             "not reported", "not reported"],
            ["Golra & Engel (2021)", "industrial feedback; semiconductor information model choices", "not reported",
             "not reported", "not reported", "not reported"],
            ["Agileo Automation (2020)", "SECS/GEM tool bridged to an OPC UA MES", "bridge", "not reported", "not reported",
             "not reported"],
            ["ErgoTech (n.d.)", "SECS/GEM interface exposed as an OPC UA server", "product", "not reported", "not reported",
             "not reported"],
            ["Sun et al. (2021)", "OPC UA server based on SECS/GEM", "translation", "not reported", "not reported",
             "not reported"],
            ["This work", "single core, arbiter, draft model, invariants", "yes", "explicit policy, tested", "six invariants",
             "attributed per event"]],
           [2.9, 3.6, 2.4, 2.3, 2.5, 2.3]),
          ("h2", "3.5 Research gap"),
          ("p", "The reviewed work has established that GEM concepts can be expressed in OPC UA information models, that a "
                "semiconductor companion specification did not exist as of 2020, and that bridges and combined interfaces can be "
                "built with research and commercial components. To our knowledge, based on our literature search, no published "
                "work studies a tool that serves SECS/GEM and OPC UA natively and simultaneously from one authoritative core, "
                "defines and tests which side may command the tool, and measures whether both interfaces observe the same "
                "events, values and states, including what is lost when one client disconnects. This project addresses that "
                "gap with the architecture of Chapter 5 and the verification method of Chapter 7.")]
    return b
