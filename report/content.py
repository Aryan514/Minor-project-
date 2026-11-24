# report/content.py
# The text of the minor project report as a list of layout blocks consumed by report/build_report.py.
# Every number in this file comes from results/ (scenario summaries, checker self-test, capture summary) or
# docs/progress.md; citations are ⟦key⟧ tokens resolved from report/references.py.
"""Report content."""

from __future__ import annotations

from content_main import chapters_4_to_9, appendices
from content_lit import chapter_3

TITLE = ("Simultaneous SECS/GEM and OPC UA Access to Semiconductor Equipment: A Single-Core Dual-Interface "
         "Architecture with Control-Authority Arbitration and Cross-Interface Consistency Verification")
REPO = "https://github.com/Aryan514/Minor-project-"


def front_matter():
    """Title page (section 1), then roman-numbered front matter (section 2)."""
    b = []
    P = lambda t, **k: b.append(("p", t, k.get("align", "center"), k.get("bold", False), k.get("size"), k.get("after", 6)))
    P("[UNIVERSITY LOGO]", after=18)
    P(TITLE, bold=True, size=16, after=24)
    P("A Minor Project Report", size=13)
    P("submitted in partial fulfilment of the requirements for the award of the degree of", after=0)
    P("[DEGREE, e.g. Bachelor of Technology] in [BRANCH]", bold=True, after=24)
    P("Submitted by", after=0)
    P("[STUDENT NAME 1] ([ROLL NUMBER 1])", bold=True, after=0)
    P("[STUDENT NAME 2] ([ROLL NUMBER 2])", bold=True, after=24)
    P("Under the supervision of", after=0)
    P("[SUPERVISOR NAME]", bold=True, after=0)
    P("[SUPERVISOR DESIGNATION]", after=36)
    P("[DEPARTMENT]", bold=True, after=0)
    P("[UNIVERSITY NAME, CITY]", bold=True, after=0)
    P("[MONTH YEAR]", bold=True, after=0)

    b.append(("new_section", "lowerRoman", 1))
    b.append(("h1", "CERTIFICATE BY SUPERVISOR"))
    b.append(("p", "This is to certify that the minor project report entitled **“" + TITLE + "”**, submitted by "
              "[STUDENT NAME 1] ([ROLL NUMBER 1]) and [STUDENT NAME 2] ([ROLL NUMBER 2]) in partial fulfilment of the "
              "requirements for the award of the degree of [DEGREE] in [BRANCH] at [UNIVERSITY NAME], is a record of "
              "work carried out under my supervision. To the best of my knowledge, the work has not been submitted "
              "elsewhere for the award of any degree or diploma."))
    for t in ["", "", "Signature: ______________________________", "Name: [SUPERVISOR NAME]",
              "Designation: [SUPERVISOR DESIGNATION]", "Department: [DEPARTMENT], [UNIVERSITY NAME]",
              "Date: ____________________"]:
        b.append(("p", t, "left", False, None, 0))

    b.append(("h1", "DECLARATION"))
    b.append(("p", "We hereby declare that the work presented in this report, entitled **“" + TITLE + "”**, is our "
              "own work carried out at [DEPARTMENT], [UNIVERSITY NAME], under the supervision of [SUPERVISOR NAME]. "
              "Wherever the work of others has been used, it has been acknowledged and cited. The results reported here "
              "were produced by the software described in this report, and the measured values are reported as "
              "obtained. This work has not been submitted elsewhere for the award of any degree or diploma."))
    for name, roll in (("[STUDENT NAME 1]", "[ROLL NUMBER 1]"), ("[STUDENT NAME 2]", "[ROLL NUMBER 2]")):
        for t in ["", "Signature: ______________________________", f"Name: {name}", f"Roll number: {roll}",
                  "Date: ____________________"]:
            b.append(("p", t, "left", False, None, 0))

    b.append(("h1", "ACKNOWLEDGEMENT"))
    b.append(("p", "We are grateful to our supervisor, [SUPERVISOR NAME], [SUPERVISOR DESIGNATION], for guidance on the "
              "scope and direction of this project and for constructive feedback throughout. We thank the Head of "
              "[DEPARTMENT] and the faculty members of the department for the facilities and support provided."))
    b.append(("p", "The testbed is built on open-source software. We acknowledge the maintainers of the `secsgem` and "
              "`asyncua` Python libraries, whose source code and documentation made it possible to implement and examine "
              "both protocol interfaces in detail, and the Wireshark project for its protocol dissectors. We also "
              "acknowledge the authors of the published work reviewed in Chapter 3, which shaped the questions this "
              "project set out to answer."))
    b.append(("p", "[STUDENT NAME 1]     [STUDENT NAME 2]", "right"))

    b.append(("h1_plain", "TABLE OF CONTENTS"))
    b.append(("field", 'TOC \\o "1-3" \\h \\z \\u', "Right-click and choose Update Field (or press F9) to build the table of contents."))
    b.append(("h1", "LIST OF FIGURES"))
    b.append(("field", 'TOC \\h \\z \\c "Figure"', "Update the field (F9) to build the list of figures."))
    b.append(("h1", "LIST OF TABLES"))
    b.append(("field", 'TOC \\h \\z \\c "Table"', "Update the field (F9) to build the list of tables."))

    b.append(("h1", "LIST OF ABBREVIATIONS AND SYMBOLS"))
    abbr = [("A&C", "Alarms and Conditions (OPC UA Part 9)"), ("ALCD", "Alarm code (SECS-II data item)"),
            ("ALID", "Alarm identifier"), ("ALTX", "Alarm text"), ("API", "Application programming interface"),
            ("CEID", "Collection event identifier"), ("DATAID", "Data identifier of an S6F11 event report"),
            ("DVID", "Data variable identifier"), ("EAC", "Equipment acknowledge code (S2F16)"),
            ("EC / ECID", "Equipment constant / equipment constant identifier"),
            ("EDA", "Equipment Data Acquisition (SEMI Interface A)"), ("GEM", "Generic Equipment Model (SEMI E30)"),
            ("HCACK", "Host command acknowledge code (S2F42)"), ("HSMS", "High-Speed SECS Message Services (SEMI E37)"),
            ("I1–I6", "Consistency invariants defined in Chapter 7"), ("IIoT", "Industrial Internet of Things"),
            ("JSON / JSONL", "JavaScript Object Notation / one JSON record per line"),
            ("MES", "Manufacturing execution system"), ("OPC UA", "OPC Unified Architecture (IEC 62541)"),
            ("p50 / p95", "50th / 95th percentile"), ("RCMD", "Remote command (S2F41)"),
            ("SECS-II", "SEMI Equipment Communications Standard 2, message content (SEMI E5)"),
            ("SEMI", "Semiconductor Equipment and Materials International"),
            ("seq", "Global, strictly increasing sequence number assigned by the equipment core"),
            ("SML", "SECS Message Language (text notation of SECS-II messages)"), ("SV / SVID", "Status variable / identifier"),
            ("TCP", "Transmission Control Protocol"), ("T", "State-convergence bound of invariant I4 (500 ms)"),
            ("ε", "Floating-point tolerance of invariant I3 (10⁻³)"), ("°C", "Degree Celsius")]
    b.append(("abbrev", abbr))

    b.append(("h1", "ABSTRACT"))
    b.append(("p", "Semiconductor process tools have long been integrated with factory host systems through SEMI SECS/GEM, "
              "while newer plant-wide consumers such as maintenance, analytics, energy and facility systems increasingly "
              "expect OPC UA. A tool that offers both interfaces at the same time has two potential masters. To our knowledge, the "
              "published mappings and gateways we reviewed do not report what happens when both are used simultaneously. This "
              "report presents a testbed in which one simulated heated-chamber tool keeps its entire state in a single "
              "equipment core and serves it concurrently over SECS/GEM (HSMS) and OPC UA. Every command, from either "
              "protocol or from the operator console, passes through one control-authority arbiter, and decision and state "
              "change are applied atomically under one lock. A GEM-derived draft OPC UA information model exposes the GEM "
              "identity of every mapped variable. A cross-interface consistency method uses the core's sequence-numbered "
              "audit log as an oracle and evaluates six invariants (completeness, order, value agreement, state convergence, "
              "single winner and loss attribution) from send-side and receive-side logs."))
    b.append(("p", "In six scenarios run on one laptop over loopback, all applicable invariants passed on both interfaces. "
              "In 50 simultaneous START conflicts, exactly one command won each time, and in 3 of the 50 rounds the losing "
              "OPC UA request had reached the core first, which shows that the outcome follows the policy rather than "
              "arrival order. A checker self-test confirmed that five deliberate corruptions of a real run are each detected. "
              "The scenarios also exposed four semantic mismatches under simultaneous use: events produced while the GEM "
              "host was disconnected were lost (11 events in the disconnect scenario, each attributed to a missing link); a "
              "same-value equipment-constant write was visible as an event on GEM but not on OPC UA; alarm acknowledgement "
              "has different meanings on the two sides; and GEM report definitions are global while OPC UA event filters "
              "are per subscription. The testbed, results and documentation are openly available."))
    b.append(("p", "**Keywords:** SECS/GEM, HSMS, OPC UA, semiconductor equipment, information model, control authority, "
              "consistency verification, Industry 4.0"))
    return b


def chapter_1():
    b = [("new_section", "decimal", 1), ("h1", "CHAPTER 1: INTRODUCTION")]
    b += [("h2", "1.1 Fabs, tools and hosts"),
          ("p", "A semiconductor fabrication plant (fab) runs hundreds of process and metrology tools, each controlled by its "
                "own equipment controller. Above the tools, a factory host, usually part of the manufacturing execution system "
                "(MES), starts and stops processing, collects events and alarms, and keeps a record of what happened to every "
                "wafer. The communication between host and tool has been standardised by SEMI for decades: SECS-II defines "
                "the messages ⟦e5⟧, HSMS carries them over TCP/IP ⟦e37⟧, and the Generic Equipment Model (GEM) defines the "
                "behaviour that a host can rely on, such as control states, collection events, alarms and remote commands "
                "⟦e30⟧. Fig. 1.1 shows this arrangement together with the newer plant-wide systems discussed below."),
          ("figure", "report/figures/fig_1_1_fab_context.png", "Fab context: one SECS/GEM host per tool and several plant-wide "
                "OPC UA consumers, all on the fab's on-premises network", 15.5),
          ("h2", "1.2 Why tools are asked to offer OPC UA as well"),
          ("p", "SECS/GEM was designed for a single host. An HSMS connection is a point-to-point session between one host "
                "and one tool, and GEM assumes that one host owns the reports, the alarm enablement and the remote commands. "
                "Modern fabs, however, have more consumers of equipment data than the MES alone: predictive-maintenance "
                "systems, analytics and digital-twin applications, energy monitoring, facility and sub-fab systems, and "
                "tools from adjacent industries that never adopted SECS/GEM. OPC UA is the interoperability standard that many "
                "of these systems already speak ⟦opcua1⟧. It offers several properties that matter in this setting:"),
          ("bullets", ["**Many clients.** An OPC UA server accepts many concurrent sessions, each with its own subscriptions, "
                       "so plant-wide consumers do not have to share or proxy the single HSMS host session.",
                       "**Self-description.** A client can browse the address space and discover variables, types, engineering "
                       "units and methods at run time ⟦opcua3⟧, whereas a GEM host must know variable identifiers in advance "
                       "from the equipment's documentation.",
                       "**Built-in security model.** OPC UA defines authentication, signing and encryption as part of the "
                       "standard ⟦opcua1⟧; HSMS itself has none.",
                       "**On-premises operation.** OPC UA is a client–server (and publish–subscribe) protocol that runs "
                       "entirely on the plant network. No cloud service is involved, which suits fabs that keep process data "
                       "inside the site."]),
          ("p", "For these reasons, equipment suppliers are increasingly asked to offer OPC UA alongside SECS/GEM, not instead "
                "of it: the MES continues to control production through GEM, and the other systems read equipment data "
                "through OPC UA."),
          ("h2", "1.3 The dual-master problem"),
          ("p", "Once a tool serves two protocols at the same time, it has two potential masters. A GEM host may start "
                "processing while an OPC UA client changes a set-point; a plant system may issue a command that the host does "
                "not know about; the two interfaces may report different states; and an event delivered to one side may be lost "
                "on the other without anyone noticing. SECS/GEM answers the question “who may command the tool?” for one "
                "host through its ONLINE_REMOTE and ONLINE_LOCAL control states. OPC UA leaves command authority to the "
                "application. A tool with both interfaces therefore needs an explicit, testable rule for command authority, and "
                "a way to check that both sides observe the same truth."),
          ("p", "Published work has mapped GEM concepts to OPC UA information models and has built translators and gateways "
                "between the two protocols (Chapter 3). To our knowledge, based on our literature search, the behaviour of "
                "a tool that serves both interfaces natively and simultaneously, including who may command it and whether "
                "both interfaces stay consistent, has not been studied experimentally."),
          ("h2", "1.4 Aim and objectives"),
          ("p", "The aim of this project is to design, implement and verify a simulated semiconductor tool that serves "
                "SECS/GEM and OPC UA simultaneously from one authoritative equipment core, with an explicit control-authority "
                "policy and a measurable notion of cross-interface consistency. The objectives are:"),
          ("bullets", ["to build one equipment core that owns all equipment state, with both protocol interfaces as thin "
                       "adapters that own no state;",
                       "to route every command from every origin through one arbiter and apply decision and state change "
                       "atomically;",
                       "to design a GEM-derived draft OPC UA information model that keeps the GEM identity of every mapped "
                       "variable visible to OPC UA clients;",
                       "to define formal consistency invariants and a checker that evaluates them from logs on both sides; and",
                       "to run normal, alarm, conflict, disconnect and report-scope scenarios and record the semantic mismatches "
                       "that appear when both interfaces are used at once."], True),
          ("h2", "1.5 Contributions"),
          ("p", "The work makes three contributions, referred to as N1–N3 throughout the report:"),
          ("bullets", ["**N1: Single-core dual-interface architecture with a control-authority arbiter.** One authoritative core, "
                       "two protocol adapters as thin “doors”, and one arbiter for every command from any origin, with "
                       "decision and state change applied atomically. The policy is explicit, covered by a full truth-table test, "
                       "and exercised under concurrent conflicts over both real protocols.",
                       "**N2: A GEM-derived draft OPC UA information model and documented semantic mismatches.** Types are "
                       "defined before the instance; every GEM-mapped variable carries its GEM identifier, kind and format; "
                       "events carry the core's sequence number. Four mismatches observed under simultaneous use are "
                       "documented with measurements: spooling, same-value writes, alarm acknowledgement and report scope.",
                       "**N3: A cross-interface consistency test method.** A global sequence-numbered audit log serves as the "
                       "oracle; send-side and receive-side logs on both protocols are joined on the sequence number; a checker "
                       "evaluates six formal invariants under normal, conflict and fault scenarios, and a self-test shows that the "
                       "checker detects deliberate corruptions."], True),
          ("h2", "1.6 Scope"),
          ("p", "The testbed models one heated chamber with five status variables, one equipment constant, seven collection "
                "events, one alarm and two remote commands. It runs on one laptop over the loopback interface with a simulated "
                "temperature sensor (an optional serial sensor is supported). The GEM control-state model is simplified to "
                "three states, OPC UA runs without security for the demonstration, and spooling is not implemented by the GEM "
                "library used. The results describe this setup; they are not a fab-scale validation, a GEM compliance claim or "
                "a comparison of protocol speed. Limitations are discussed in Chapter 8."),
          ("h2", "1.7 Source code and data"),
          ("p", f"The complete source code, scenario logs, results, documentation and the dashboard user guide are available "
                f"at {REPO}. Appendix D explains how to run the testbed and reproduce the results."),
          ("h2", "1.8 Organisation of the report"),
          ("p", "Chapter 2 introduces SECS/GEM and OPC UA. Chapter 3 reviews related work and identifies the research gap. "
                "Chapter 4 analyses the dual-master problem and states the requirements. Chapter 5 presents the architecture, "
                "the arbiter, the information model and the protocol mappings. Chapter 6 describes the implementation and the "
                "test suite. Chapter 7 defines the invariants and reports the results of six scenarios, including the semantic "
                "mismatches found. Chapter 8 discusses limitations and future work, and Chapter 9 concludes. The appendices "
                "contain the full arbitration truth table, the demonstration procedure, selected dashboard figures and run "
                "instructions.")]
    return b


def chapter_2():
    b = [("h1", "CHAPTER 2: BACKGROUND")]
    b += [("h2", "2.1 SECS-II and HSMS"),
          ("p", "SECS-II (SEMI E5) defines the content of messages exchanged between equipment and host ⟦e5⟧. Each message "
                "is identified by a stream and a function, written SxFy: odd functions are primary messages and even functions "
                "are replies. A W-bit marks a primary message that expects a reply. The body is a tree of typed items: lists "
                "(L), ASCII strings (A), binary (B), booleans, signed and unsigned integers (I1–I8, U1–U8) and floating-point "
                "numbers (F4, F8). In text form, messages are written in the SECS Message Language (SML)."),
          ("p", "HSMS (SEMI E37) transports SECS-II messages over TCP/IP ⟦e37⟧. A host opens a TCP connection to the "
                "equipment (or the reverse, depending on the active and passive roles), selects a session with a control "
                "message, and then exchanges data messages, each prefixed by a ten-byte header that carries the session "
                "identifier, stream, function, W-bit and a system byte matching a reply to its request. Linktest messages "
                "check that the connection is alive, and reply timeouts (T3) bound how long a sender waits for an answer. In "
                "the single-session variant, the equipment accepts one host connection at a time."),
          ("h2", "2.2 The Generic Equipment Model (GEM) and GEM300"),
          ("p", "GEM (SEMI E30) specifies which SECS-II messages an equipment supports and how it behaves ⟦e30⟧. Its main "
                "capabilities are: status variables (SVIDs) readable with S1F3; equipment constants (ECIDs) read with S2F13 "
                "and written with S2F15; collection events (CEIDs) reported with S6F11 using reports that the host defines, "
                "links to events and enables with S2F33, S2F35 and S2F37; data variables (DVIDs) that are valid only inside an "
                "event report; alarms reported with S5F1; remote commands sent with S2F41; and spooling, which buffers messages "
                "while the host is unreachable. The 300 mm extensions, commonly called GEM300, add standards for carrier, "
                "substrate and process-job management on top of GEM; they are outside the scope of this project."),
          ("p", "GEM defines a control-state model. In EQUIPMENT_OFFLINE the host cannot operate the tool. In ONLINE_LOCAL "
                "the operator at the tool has control and the host may read data but may not issue commands that change the "
                "process. In ONLINE_REMOTE the host has control. This model is the only notion of command authority in "
                "SECS/GEM, and it assumes a single host. Listing 2.1 shows four messages captured from the testbed's own "
                "equipment-side log during a demonstration run."),
          ("code", """S1F3 W                      (host → equipment: read SVIDs 1-5)
  <L [5] <U1 1> <U1 2> <U1 3> <U1 4> <U1 5> > .
S1F4                        (reply)
  <L [5] <F4 25.014> <U1 4> <U1 0> <A "OPERATOR"> <U4 2> > .
S2F41 W                     (host → equipment: remote command)
  <L [2] <A "START"> <L> > .
S2F42                       (reply: HCACK 0 = accepted)
  <L [2] <B 0x0> <L> > .
S5F1                        (equipment → host: alarm set, ALID 5001)
  <L [3] <B 0x84> <U2 5001> <A "ChamberOverTemp SET T=40.21 seq=103"> > .
S6F11 W                     (equipment → host: event report CEID 1007)
  <L [3] <U1 6> <U2 1007>
    <L [1] <L [2] <U2 1007> <L [2] <U4 6> <F4 24.978> > > > > ."""),
          ("p", "*Listing 2.1: SECS-II messages in SML, taken from the testbed's equipment-side wire log (layout condensed). "
                "In the S6F11, DATAID and the first report value (DVID 101) both carry the core's sequence number.*", "center"),
          ("h2", "2.3 OPC UA"),
          ("p", "OPC Unified Architecture (OPC UA, IEC 62541) is a platform-independent standard for industrial "
                "communication ⟦opcua1⟧. A server exposes an **address space** of nodes (objects, variables, methods, object "
                "types, variable types and reference types) connected by references ⟦opcua3⟧. Clients use services to browse "
                "the address space, read and write attributes, call methods and create subscriptions ⟦opcua4⟧. A subscription "
                "contains monitored items: data-change items report new values of variables, and event items deliver events "
                "that match an event filter selecting the fields the client wants. Notifications are sent in batches at the "
                "subscription's publishing interval."),
          ("p", "Types are first-class: a server can define its own object, variable and event types and instantiate them, "
                "so that a client can recognise the same structure on different servers ⟦opcua5⟧. Alarms and Conditions "
                "(Part 9) defines condition types such as AlarmConditionType and OffNormalAlarmType with active, acknowledged "
                "and confirmed states and methods such as Acknowledge ⟦opcua9⟧. **Companion specifications** are information "
                "models agreed by an industry group and published with the OPC Foundation for a class of devices; as of 2020 there "
                "was none for the semiconductor (SEMI) domain ⟦opcf20⟧."),
          ("h2", "2.4 SEMI EDA / Interface A"),
          ("p", "SEMI has its own route for high-volume data collection: Equipment Data Acquisition (EDA), also called "
                "Interface A, a set of standards for a separate, web-services-based data channel with an equipment metadata "
                "model ⟦eda⟧. EDA is designed for detailed process data to fab applications and coexists with the GEM "
                "control interface. OPC UA addresses a broader, cross-industry audience, which is why plant systems outside "
                "the semiconductor domain tend to ask for it."),
          ("h2", "2.5 Comparison of SECS/GEM and OPC UA"),
          ("p", "Table 2.1 compares the two technologies on the aspects that matter for this project. The comparison is "
                "qualitative; it does not rank the two, because they were designed for different purposes."),
          ("table", "Comparison of SECS/GEM and OPC UA for equipment integration",
           ["Aspect", "SECS/GEM (E5, E37, E30)", "OPC UA (IEC 62541)"],
           [["Connections", "One host session per tool (HSMS single-session)", "Many concurrent client sessions"],
            ["Discovery", "Identifiers known in advance from documentation", "Browse of a typed address space at run time"],
            ["Data delivery", "Host-defined reports linked to events (S2F33/35/37), S6F11 per event",
             "Per-client subscriptions with data-change and event monitored items"],
            ["Types and units", "SECS-II formats (U1, F4, A …); units as text", "Information model types, EngineeringUnits, ranges"],
            ["Semiconductor behaviour", "Control states, alarms, remote commands, spooling defined by GEM",
             "Generic; domain behaviour comes from information models"],
            ["Command authority", "ONLINE_REMOTE / ONLINE_LOCAL for one host", "Left to the application"],
            ["Security", "None in HSMS itself", "Authentication, signing and encryption defined by the standard"],
            ["High-rate data", "Limited; EDA/Interface A is SEMI's data-collection path", "Subscriptions; rate set by sampling and publishing intervals"],
            ["Ecosystem", "Semiconductor fabs and suppliers", "Cross-industry: automation, process, energy, building"],
            ["Deployment", "On-premises", "On-premises (client–server and publish–subscribe)"]],
           [3.2, 6.4, 6.4])]
    return b


def blocks():
    """All blocks in document order."""
    return front_matter() + chapter_1() + chapter_2() + chapter_3() + chapters_4_to_9() + appendices()
