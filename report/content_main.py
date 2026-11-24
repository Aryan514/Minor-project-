# report/content_main.py
# Chapters 4-9 and the appendices of the report (blocks for build_report.py). Numbers come from results/*.md,
# results/capture_summary.md, docs/progress.md and the pytest run; nothing is estimated.
"""Report chapters 4-9 and appendices."""

from __future__ import annotations

REPO = "https://github.com/Aryan514/Minor-project-"


def chapter_4():
    b = [("h1", "CHAPTER 4: PROBLEM ANALYSIS AND REQUIREMENTS")]
    b += [("h2", "4.1 Risks of a tool with two masters"),
          ("p", "When a tool exposes SECS/GEM and OPC UA at the same time and both allow commands, four kinds of failure "
                "become possible. They do not depend on a particular implementation; they follow from having two independent "
                "entry points into one machine."),
          ("bullets", ["**Uncommanded start.** An OPC UA client starts processing while the MES believes it controls the tool "
                       "in ONLINE_REMOTE. The host's view of the process is then wrong, and wafers may be processed without a "
                       "job the MES knows about.",
                       "**Set-point change unknown to the host.** A plant client changes an equipment constant, for example a "
                       "temperature limit, and the host is not informed, so its recipe assumptions no longer hold.",
                       "**Divergent state.** If each protocol stack keeps its own copy of control state, processing state or "
                       "constants, the two interfaces can report different values for the same quantity.",
                       "**Silent event loss.** When one client is disconnected, events produced in the meantime are lost to it. "
                       "Unless the loss is recorded, nobody can later tell whether an event was never produced, was dropped by "
                       "the equipment, or was lost in the network or the client."]),
          ("p", "A further, subtler risk is a **race between check and action**: if the equipment checks whether a command is "
                "allowed and applies it in two separate steps, two simultaneous commands can both pass the check before "
                "either changes the state. Chapter 7 demonstrates that this happens with an injected one-millisecond gap."),
          ("h2", "4.2 Target scenario"),
          ("p", "The project assumes the following fab scenario. The MES controls production through the GEM interface in "
                "ONLINE_REMOTE. Several plant systems read equipment data through OPC UA: they browse the model, subscribe to "
                "variables and events, and receive alarms. Access to commands is controlled: many clients may read, few may "
                "command. An operator at the tool can switch between remote and local control, can always stop the process "
                "for safety, and can hand a temporary maintenance lease to an OPC UA client when the tool is offline from "
                "production."),
          ("h2", "4.3 Requirements"),
          ("p", "Table 4.1 lists the functional (F) and non-functional (NF) requirements derived from this scenario."),
          ("table", "Functional and non-functional requirements",
           ["ID", "Requirement", "Verified by"],
           [["F1", "One equipment core owns all state; both protocol adapters only read from it and submit commands to it.",
             "Architecture review; no-bypass test"],
            ["F2", "Every command (GEM remote command and constant write, OPC UA method call, operator command) passes the "
                   "arbiter.", "No-bypass test (15 entry points)"],
            ["F3", "Decision and state change are atomic; two simultaneous conflicting commands cannot both succeed.",
             "Race tests; scenario S3 (I5)"],
            ["F4", "Every state change and every event or alarm is audited with a global, strictly increasing sequence number.",
             "Core tests; checker"],
            ["F5", "Both interfaces report events and alarms with the same sequence number.", "Scenarios S1–S6 (I1–I3)"],
            ["F6", "Rejections are reported with the protocol's own codes and announced on both interfaces.", "S3, S4 (I5)"],
            ["F7", "The OPC UA model is typed and exposes the GEM identity of every mapped variable.", "Browse of the server"],
            ["F8", "Every event a client misses has a recorded cause.", "S5 (I6)"],
            ["NF1", "A failure of one adapter or client does not stop the core or the other adapter.", "S5 (GEM host killed)"],
            ["NF2", "Runs without hardware; a seeded simulation makes runs reproducible.", "All scenarios (seed 42)"],
            ["NF3", "Runs on Windows, Linux and macOS with Python 3.11 or 3.12.", "Implementation"],
            ["NF4", "Results are judged by an automatic checker that is itself shown to detect errors.", "Checker self-test"]],
           [1.3, 10.2, 4.5]),
          ("h2", "4.4 Design goals"),
          ("p", "Four design goals follow from the requirements. **Single source of truth:** state lives in exactly one place, "
                "so divergence can only arise in delivery, where it can be measured. **Policy, not timing:** who wins a "
                "conflict is decided by an explicit rule, never by which request arrives first. **Nothing lost silently:** "
                "every message an interface fails to deliver is logged with a reason. **Evidence over assertion:** each claim "
                "is backed by a test or by a scenario whose logs an independent checker evaluates.")]
    return b


def chapter_5():
    b = [("h1", "CHAPTER 5: SYSTEM ARCHITECTURE AND DESIGN")]
    b += [("h2", "5.1 Overview"),
          ("p", "Fig. 5.1 shows the architecture. The equipment core sits in the middle and owns all state. The GEM door "
                "(built on `secsgem` 0.3.0 ⟦secsgem⟧) and the OPC UA door (built on `asyncua` 1.1.8 ⟦asyncua⟧) are adapters: "
                "they translate protocol messages into core calls and core notifications into protocol messages. The operator "
                "console is a third entry point. The simulated chamber supplies temperature samples and receives heater "
                "commands. The consistency checker is not part of the running equipment; it evaluates the logs afterwards or "
                "live."),
          ("figure", "report/figures/fig_5_1_architecture.png", "Overall system architecture; original contributions are "
                "shaded blue", 15.5),
          ("p", "Table 5.1 lists the equipment definition that both interfaces serve. All identifiers are defined once in a "
                "single configuration module."),
          ("table", "Equipment definition of the simulated chamber tool",
           ["Kind", "ID", "Name", "Notes"],
           [["SVID", "1", "ChamberTemp", "F4, °C, from the sensor"],
            ["SVID", "2", "ControlState", "U1: 1 OFFLINE, 4 ONLINE_LOCAL, 5 ONLINE_REMOTE"],
            ["SVID", "3", "ProcessingState", "U1: 0 IDLE, 1 EXECUTING"],
            ["SVID", "4", "Authority", "A: GEM_HOST, OPERATOR or UA_CLIENT"],
            ["SVID", "5", "LastEventSeq", "U4: last event sequence number"],
            ["DVID", "101–104", "EventSeq, EventTemp, RejectReason, Origin", "valid only in event reports; 101 is the join key"],
            ["ECID", "201", "TempHighLimit", "F4, °C, range 20–80, default 40"],
            ["CEID", "1001–1007", "ControlStateChanged, ProcessingStarted, ProcessingStopped, AuthorityChanged, "
                                 "CommandRejected, TempHighLimitChanged, TempSample (1 Hz)", "every report contains DVID 101"],
            ["ALID", "5001", "ChamberOverTemp", "set when temperature > limit, cleared below limit − 1.0 °C"],
            ["RCMD", "START, STOP", "Heater on / off", "START valid in IDLE, STOP valid in EXECUTING"]],
           [1.6, 2.0, 6.4, 6.0]),
          ("h2", "5.2 Equipment core and audit log"),
          ("p", "The core is the only owner of equipment state: status variables, the equipment constant, control state, "
                "processing state, authority, active alarms and the maintenance-lease flag. One re-entrant lock guards all of "
                "it, because the GEM library uses threads and the OPC UA library uses an asyncio event loop. Fig. 5.2 shows what "
                "happens inside the lock when a command arrives."),
          ("figure", "report/figures/fig_5_2_core_internals.png", "Core internals: arbiter, preconditions, state change, "
                "sequence number and audit record inside one lock; per-subscriber dispatcher queues outside it", 15.5),
          ("p", "Every state change and every event or alarm is written to an append-only audit log, one JSON record per "
                "line, flushed immediately. Each record carries a global sequence number (seq) that starts at 1 and increases "
                "strictly; it is assigned under the core lock, so the order of sequence numbers is the order in which changes "
                "happened. The audit log is the oracle for verification (Chapter 7): it defines what both interfaces should "
                "have reported. The seq travels inside every message the doors send: as DVID 101 and DATAID in S6F11, as "
                "`seq=<n>` in the S5F1 alarm text, and as the `EventSeq` field of every OPC UA event."),
          ("h2", "5.3 Control-authority arbiter"),
          ("p", "The arbiter is a pure function without input or output: given the control state, the lease flag, the origin "
                "of a request (GEM_HOST, UA_CLIENT or OPERATOR) and the action (START, STOP or EC_WRITE), it returns whether "
                "the request is allowed and, if not, why. Table 5.2 is the policy it implements; Appendix A lists every "
                "combination."),
          ("table", "Control-authority policy for START, STOP and EC_WRITE",
           ["Control state", "Authority", "GEM_HOST", "UA_CLIENT", "OPERATOR"],
           [["ONLINE_REMOTE", "GEM_HOST", "allowed", "rejected: authority held by GEM_HOST", "STOP only (safety override)"],
            ["ONLINE_LOCAL", "OPERATOR", "rejected: equipment in LOCAL", "rejected: equipment in LOCAL", "allowed"],
            ["EQUIPMENT_OFFLINE", "OPERATOR", "rejected: equipment OFFLINE", "rejected: no maintenance lease", "allowed"],
            ["EQUIPMENT_OFFLINE + lease", "UA_CLIENT", "rejected: maintenance lease held by UA_CLIENT", "allowed", "allowed"]],
           [3.4, 2.4, 3.6, 3.6, 3.0]),
          ("p", "The policy follows the meaning of the GEM control states. ONLINE_REMOTE means the fab host is in charge, so "
                "OPC UA clients keep full read access but may not command. The operator may always stop the process, because "
                "equipment safety takes precedence over host authority. An OPC UA client can obtain command authority only "
                "through a maintenance lease, which the operator grants while the tool is offline from production; the lease "
                "shuts the GEM host out and is revoked automatically when the tool leaves EQUIPMENT_OFFLINE. Changes of control "
                "state and of the lease are themselves arbitrated and are allowed only for the operator, so a GEM host request "
                "to go online or offline (S1F17, S1F15) is refused and audited. Reads (S1F3, S2F13, browse, read, subscribe) "
                "are never arbitrated."),
          ("p", "Fig. 5.3 shows the control states, the lease and the authority holder in each state."),
          ("figure", "report/figures/fig_5_3_control_states.png", "Control-state and authority diagram, including the maintenance "
                "lease", 15.5),
          ("h3", "5.3.1 Atomic decide-and-apply"),
          ("p", "The core calls the arbiter while holding its lock, checks the state preconditions (for example, START only "
                "from IDLE), applies the change, assigns the sequence numbers, writes the audit records and queues the "
                "notifications, all before releasing the lock. A decision therefore cannot be invalidated between check and "
                "action, and two simultaneous STARTs cannot both succeed. The policy, not the arrival order, decides the "
                "winner. Every rejection is audited and announced on both interfaces as CEID 1005 (CommandRejected) with the "
                "origin and the reason, so a GEM host learns that an OPC UA client tried to command the tool, and vice versa. "
                "Fig. 5.4 shows a simultaneous START from both sides."),
          ("figure", "report/figures/fig_5_4_seq_conflict.png", "Sequence diagram of a simultaneous START from the GEM host and "
                "the OPC UA client in ONLINE_REMOTE", 15.5),
          ("h3", "5.3.2 Reply-code mapping"),
          ("p", "Each protocol receives the outcome in its own vocabulary. Table 5.3 maps the core's outcomes to the GEM "
                "acknowledge codes and to OPC UA status codes."),
          ("table", "Mapping of core outcomes to HCACK, EAC and OPC UA StatusCodes",
           ["Outcome", "S2F42 HCACK", "S2F16 EAC", "OPC UA StatusCode"],
           [["accepted", "0", "0", "Good"],
            ["unknown command / ECID", "1", "1", "BadNotFound"],
            ["not allowed (authority)", "2", "2", "BadUserAccessDenied"],
            ["wrong state", "2, or 5 if already in the requested state", "—", "BadInvalidState"],
            ["value out of range", "—", "3", "BadOutOfRange"]],
           [4.4, 4.4, 2.4, 4.8]),
          ("h2", "5.4 Dispatcher"),
          ("p", "The core never sends protocol messages itself. It places a notification for every audited change in one "
                "first-in-first-out queue per subscriber (GEM door, OPC UA door, live view), in sequence order, while still "
                "holding the lock. A separate worker per subscriber delivers the notifications. Each queue is bounded (10 000 "
                "entries); on overflow the oldest entry is dropped and the drop is audited. A slow, blocked or disconnected "
                "subscriber therefore cannot delay the core or the other subscribers, and delivery order per subscriber "
                "follows the sequence numbers. The OPC UA worker hands each notification to the asyncio event loop and waits "
                "for it to finish, which keeps OPC UA events strictly ordered."),
          ("h2", "5.5 GEM interface"),
          ("p", "The GEM door is a passive HSMS endpoint on port 5000 (device identifier 0, model name CHAMBER-SIM). It "
                "supports establishing communication (S1F13), status (S1F3), variable namelists (S1F11), equipment constants "
                "(S2F13, S2F15), dynamic reports (S2F33, S2F35, S2F37), remote commands (S2F41), alarms (S5F1) and event "
                "reports (S6F11). Remote commands and constant writes are passed to the core with origin GEM_HOST, and the "
                "HCACK or EAC returned to the host is the core's result."),
          ("p", "For every notification it receives from the dispatcher, the GEM door writes a **send-side log** record with "
                "the outcome `sent`, `dropped_no_link`, `dropped_disabled` or `error`. An event is logged as `sent` only if the "
                "host answered with the expected reply (S6F12 or S5F2) within the reply timeout. This log distinguishes losses "
                "inside the equipment from losses in the network or the client, and it makes the absence of spooling "
                "measurable. The door also tracks the HSMS link and reports it to the core, which mirrors it to OPC UA as "
                "`GemInterface/CommunicationState`."),
          ("h2", "5.6 OPC UA interface and the GEM-derived information model"),
          ("p", "The OPC UA door runs a server at `opc.tcp://0.0.0.0:4840/semi-equipment/` with namespace "
                "`urn:minor-project:semi-equipment-mini`. The model is built in code with types first and the instance second, "
                "so that it is a reusable model rather than a set of ad-hoc nodes. It is a draft information model for this "
                "project, derived from the GEM concepts of the tool; it is not a companion specification. Table 5.4 lists the "
                "types; the instance tree is shown in Fig. 5.6."),
          ("table", "Types of the GEM-derived draft information model",
           ["Type", "Kind (base)", "Content"],
           [["GemMappedVariableType", "VariableType (BaseDataVariableType)", "Mandatory properties GemId (UInt32), GemKind "
                                                                              "(“SVID”/“ECID”), GemFormat (e.g. “F4”)"],
            ["ChamberType", "ObjectType", "Temperature: GemMappedVariableType, Double, °C, EURange 0–100, GemId 1"],
            ["SemiEquipmentType", "ObjectType", "Identification, GemInterface, ProcessingState, Chamber1, EquipmentConstants, "
                                                "Alarms; methods Start, Stop, SetTempHighLimit(value)"],
            ["GemCollectionEventType", "EventType (BaseEventType)", "CEID, EventSeq, Origin, Payload (JSON of the report values)"],
            ["GemOffNormalAlarmType", "EventType (OffNormalAlarmType)", "ALID, EventSeq, plus the A&C fields ActiveState, "
                                                                         "Severity, Message"]],
           [4.2, 4.3, 7.5]),
          ("p", "**Traceability between OPC UA and GEM.** Every GEM-mapped variable carries the properties GemId, GemKind and "
                "GemFormat. A client can navigate from a node to its GEM identity, and a browse filtered on GemId finds the node "
                "for a GEM identifier. Properties were chosen over a custom reference type because they are visible in every "
                "generic OPC UA client without type knowledge. Enumerated GEM states are exposed twice: as a string for "
                "people (ControlState) and as the numeric GEM value (ControlStateId = SVID 2). Data variables are not nodes; "
                "they are meaningful only at event time and therefore appear only inside events. Every value carries the core's "
                "timestamp as its source timestamp."),
          ("p", "**Events and alarms.** All seven collection events are published as GemCollectionEventType with the CEID, the "
                "sequence number, the origin and the report values. The alarm uses Alarms and Conditions: "
                "GemOffNormalAlarmType, a subtype of OffNormalAlarmType, carries ActiveState, Severity, Message, ALID and "
                "EventSeq, and ConditionRefresh replays the active alarm. The library provides no server-side acknowledge or "
                "confirm logic, so acknowledgement is not modelled (Section 7.7). Fig. 5.5 shows how one alarm reaches both "
                "sides with the same sequence number."),
          ("figure", "report/figures/fig_5_5_seq_alarm.png", "Sequence diagram of an over-temperature alarm and a sample event "
                "carrying the same sequence number on both protocols", 15.5),
          ("p", "Fig. 5.6 shows the resulting instance tree as a client sees it when browsing the server, with the GEM "
                "identifier of every mapped variable."),
          ("figure", "report/figures/fig_5_6_information_model.png", "Instance tree of the OPC UA information model with GEM "
                "identifiers", 15.5),
          ("p", "**Commands over OPC UA.** Start() and Stop() call the core with origin UA_CLIENT and return the mapped status "
                "code (Table 5.3). TempHighLimit is read-only; writes go through the method SetTempHighLimit(value). A plain "
                "write would be applied by the library directly to its own copy of the variable, and its write hook can only "
                "refuse a request as a whole, so a method is the only way to route the write through the arbiter and return a "
                "per-call status code."),
          ("h2", "5.7 GEM to OPC UA mapping"),
          ("p", "Table 5.5 summarises how each GEM concept is represented and where the meaning differs. The last column is "
                "filled from measurements under simultaneous use (Chapter 7)."),
          ("table", "Mapping of GEM concepts to OPC UA constructs and observed semantic gaps",
           ["GEM concept", "OPC UA construct", "Fit", "Semantic gap observed"],
           [["SVID (S1F3/F4)", "GemMappedVariableType variable with EngineeringUnits", "full",
             "GEM unit text vs EUInformation; OPC UA receives every 0.5 s sample, GEM the 1 Hz event"],
            ["DVID", "Event field (EventSeq) and Payload", "partial", "meaningful only at event time"],
            ["ECID (S2F13/F15)", "Read-only variable + method via the arbiter", "full",
             "EAC vs StatusCode; a same-value write is a GEM event but no OPC UA data change (S4)"],
            ["Report define/link/enable (S2F33/35/37)", "Event subscription with event filter", "partial",
             "GEM reports are global on the tool; OPC UA filters are per subscription (S6)"],
            ["Event report (S6F11/F12)", "GemCollectionEventType", "full", "S6F12 is an application acknowledgement; OPC UA has none"],
            ["Alarm (S5F1/F2)", "GemOffNormalAlarmType (A&C)", "partial",
             "S5F2 acknowledges a message; OPC UA Acknowledge records an operator action"],
            ["Remote command (S2F41/F42)", "Methods Start, Stop", "full", "ONLINE_REMOTE authority has no OPC UA equivalent; "
                                                                           "supplied by the arbiter"],
            ["Control state", "ControlState / ControlStateId + CEID 1001", "partial", "simplified three-state model"],
            ["Spooling", "—", "none", "OPC UA has no spool; the GEM library does not implement spooling (S5)"]],
           [3.4, 4.2, 1.4, 7.0]),
          ("h2", "5.8 Library default behaviours that had to be overridden"),
          ("p", "Both protocol libraries are well suited to a tool with one interface. Used unchanged in a dual-interface "
                "tool, several of their defaults would create a second owner of state, a path around the arbiter, or would "
                "break an invariant. These behaviours were identified by reading the library source code, and Table 5.6 lists "
                "how each was handled. All overrides are confined to the two adapters; the core and the arbiter do not depend "
                "on either library."),
          ("table", "Library default behaviours that would bypass the arbiter or break an invariant, and their handling",
           ["#", "Library default", "Risk", "Handling"],
           [["1", "secsgem replies “will finish later” to every known remote command and runs it without a check",
             "bypass; no HCACK 2/5", "S2F41 handled by the door; HCACK is the core's result"],
            ["2", "secsgem range-checks S2F15 itself and keeps its own constant value", "bypass; second copy of state",
             "S2F15 handled by the door through the core; S2F13 reads the core"],
            ["3", "secsgem's control-state machine can be changed by the host (S1F15/S1F17)", "bypass; diverging control state",
             "requests passed to the core, refused by policy and audited"],
            ["4", "pre-registered default variables, constants, events and commands", "second state visible to the host",
             "cleared; only the configured identifiers are registered"],
            ["5", "one thread per event; report values read at send time; unlinked events skipped silently",
             "reordering (I2); wrong values (I3); silent loss (I6)",
             "one worker builds each S6F11 from the event-time payload and logs the outcome"],
            ["6", "alarm messages with fixed text and a library-side alarm flag", "no join key (I1/I3); second state",
             "S5F1 sent by the door with ALCD and “seq=<n>” in the text"],
            ["7", "reports may contain only status or data variables", "CEID 1006 cannot report ECID 201",
             "ECID 201 also registered as a data value"],
            ["8", "connection-closed hook never called", "events “sent” into a dead link (I6)",
             "door subscribes to the HSMS disconnect event and reports the link to the core"],
            ["9", "listening-socket shutdown fails on Windows; disable() can hang", "equipment cannot shut down",
             "connection class replaced in the door"],
            ["10", "writable variables are written directly by the Write service", "bypass; second state",
             "TempHighLimit read-only; method SetTempHighLimit"],
            ["11", "asynchronous method callbacks run inside the event loop", "core lock could stall all OPC UA traffic",
             "synchronous callbacks, run in the library's thread pool"],
            ["12", "one mutable event object per event type", "fields of two events mixed (I3)",
             "all events fired by one worker in sequence order"],
            ["13", "events go only to subscribers of the emitting node, and nowhere if nobody listens", "invisible loss (I6)",
             "single emitting node; send-side log decides sent / dropped_no_link"],
            ["14", "no server-side Acknowledge/Confirm for alarms", "semantic gap, not a bypass", "documented, not overridden"]],
           [0.7, 6.0, 4.2, 5.1]),
          ("h2", "5.9 Web dashboard and control panel"),
          ("p", "A web dashboard, built with the Python standard library only and served on the local machine, shows a running "
                "or recorded run: the architecture with message pulses, three columns with what the GEM host sees, what the "
                "core holds and what the OPC UA client sees (cells that disagree with the core are highlighted), the "
                "temperature and alarm history, the arbiter's decisions, a per-sequence-number event timeline, the SECS-II "
                "messages in SML and the OPC UA service calls, and live invariants computed by the same checker as the "
                "scenarios. A control panel starts and stops the system and sends commands only through the entry points any "
                "external client has: the GEM host (real S2F41 and S2F15), the OPC UA client (real method calls) and the "
                "operator console, so the arbiter treats a button press exactly like a real client. A second tab shows the "
                "policy table generated from the arbiter itself with the active row highlighted, a live browse of the "
                "information model, and the race demonstration of Section 7.5. Chapter 7 includes dashboard screenshots.")]
    return b


def chapter_6():
    b = [("h1", "CHAPTER 6: IMPLEMENTATION")]
    b += [("h2", "6.1 Technology stack"),
          ("table", "Technology stack with pinned versions",
           ["Component", "Version", "Use"],
           [["Python", "3.12.5 (3.11 or 3.12 supported)", "implementation language"],
            ["secsgem", "0.3.0", "HSMS and GEM handlers (equipment and test host)"],
            ["asyncua", "1.1.8", "OPC UA server and test client"],
            ["pyserial", "3.5", "optional serial temperature sensor"],
            ["pytest", "9.2.0", "unit, race and checker tests"],
            ["rich", "15.0.0", "terminal live view"],
            ["Wireshark / TShark", "4.6.10", "packet capture and protocol decoding (not a dependency)"],
            ["Operating system", "Windows 11; code is portable to Linux and macOS", "development and measurements"]],
           [4.0, 5.5, 6.5]),
          ("p", "All dependency versions are pinned in `requirements.txt`. The web dashboard uses only the Python standard "
                "library and works without an internet connection."),
          ("h2", "6.2 Repository structure"),
          ("table", "Repository structure",
           ["Folder", "Content"],
           [["equipment/", "configuration (all identifiers), audit log, arbiter, core, dispatcher, sensors, GEM door, OPC UA model "
                           "and door, operator console, wire log, main program"],
            ["clients/", "scripted GEM host and OPC UA client with receive-side logs and one-shot commands"],
            ["harness/", "scenario runner (S1–S6), checker, terminal live view, web dashboard and control panel, narrated demo, "
                         "race demonstration"],
            ["tests/", "101 automated tests"],
            ["results/", "scenario summaries and CSV files, checker self-test, packet capture and its summary"],
            ["runs/", "one committed sample run (JSONL logs); other runs are generated locally"],
            ["docs/", "architecture, information model, mapping, arbitration, invariants, limitations, library notes, user guide"]],
           [3.0, 13.0]),
          ("p", "The equipment, client and harness code amounts to about 5 900 lines of Python, of which about 2 500 are in "
                "`equipment/`. Every module begins with a short header stating what it does and which contribution it serves."),
          ("h2", "6.3 Arbiter decision and command submission"),
          ("p", "Listing 6.1 shows the decision logic and Listing 6.2 the command path through the core, in simplified "
                "pseudo-code."),
          ("code", """function decide(control_state, lease_ua, origin, action):
    if action in {SET_CONTROL_STATE, SET_LEASE}:
        return allowed if origin == OPERATOR else rejected("operator only")
    holder = authority_holder(control_state, lease_ua)
    if origin == holder:                          return allowed
    if origin == OPERATOR and action == STOP:     return allowed     # safety override
    if origin == OPERATOR and holder == UA_CLIENT: return allowed    # operator keeps control in maintenance
    return rejected(reason_for(control_state, lease_ua, origin))"""),
          ("p", "*Listing 6.1: Arbiter decision (pure function, no input or output).*", "center"),
          ("code", """function submit_command(origin, rcmd):
    with core_lock:                               # one lock for decide AND apply
        if rcmd unknown:   return reject(HCACK 1, BadNotFound)
        d = decide(control_state, lease_ua, origin, rcmd)
        if not d.allowed:  return reject(HCACK 2, BadUserAccessDenied, d.reason)
        if precondition fails: return reject(HCACK 5 or 2, BadInvalidState)
        apply state change; switch heater
        seq = audit(command_ok); audit(state); audit(event CEID 1002/1003)
        dispatcher.enqueue(notifications in seq order)
        return ok(HCACK 0, Good, seq)

function reject(...):                             # still inside the lock
    seq = audit(command_rejected, reason); audit(event CEID 1005)
    dispatcher.enqueue(...); return result"""),
          ("p", "*Listing 6.2: Command submission: decision, state change, audit and notification under one lock.*", "center"),
          ("h2", "6.4 Wire logging"),
          ("p", "For demonstration and inspection, both sides of the SECS-II traffic are logged in SML. The GEM library already "
                "reports every HSMS message with its SML text to its own communication logger; a small log handler writes these "
                "records as JSON lines, so no adapter code had to change. The OPC UA clients log their service calls (session, "
                "subscription, monitored items, method calls, browse) and every notification at client level. In addition, a "
                "full demonstration was captured with Wireshark on the loopback adapter (Section 7.8)."),
          ("h2", "6.5 Testing approach"),
          ("p", "The test suite contains 101 automated tests, all passing in the latest run. Table 6.3 summarises them."),
          ("table", "Automated tests",
           ["Test file", "Tests", "What is verified"],
           [["test_arbiter.py", "74", "every combination of control state × lease × origin × action against the policy table, "
                                      "plus operator-only actions"],
            ["test_core.py", "10", "strictly increasing seq; an audit record for every change; replay of the audit log "
                                   "reconstructs the state; alarm hysteresis; no-bypass test: with a deny-all arbiter, nothing "
                                   "changes through any of 15 entry points"],
            ["test_race.py", "4", "500 barrier-synchronised iterations each: START races in REMOTE (GEM always wins) and in "
                                  "OFFLINE with lease (exactly one wins), and concurrent constant writes"],
            ["test_dispatcher.py", "5", "order per subscriber; a subscriber sleeping 1 s per item does not delay another; overflow "
                                        "drops the oldest and is audited; a failing handler keeps the worker alive"],
            ["test_checker.py", "2", "checker passes a real run and flags five deliberate corruptions"],
            ["test_web_view.py", "3", "the dashboard shows the same counters as the checker"],
            ["test_control_panel.py", "3", "policy table equals the arbiter; race demonstration; SML wire log"]],
           [3.6, 1.4, 11.0]),
          ("p", "The no-bypass test is the direct evidence that every command passes the arbiter: the arbiter is replaced by "
                "one that denies everything, every entry point from every origin is exercised, and the test asserts that no "
                "state changes. The race tests release two threads through a barrier so that both requests reach the core at "
                "the same moment, reset the state between iterations and assert exactly one winner every time.")]
    return b


def chapter_7():
    b = [("h1", "CHAPTER 7: VERIFICATION AND RESULTS")]
    b += [("h2", "7.1 Verification method"),
          ("p", "Verification compares what each client received with what the core recorded. The core audit log is the "
                "oracle; the GEM door and the OPC UA door write send-side logs; the scripted GEM host and OPC UA client write "
                "receive-side logs; the scenario runner records the evaluation window and the conflict rounds. The checker joins "
                "all records on the sequence number and evaluates six invariants (Fig. 7.1)."),
          ("figure", "report/figures/fig_7_1_verification.png", "Verification method: logs joined on the sequence number and "
                "evaluated against invariants I1–I6", 15.5),
          ("table", "Consistency invariants",
           ["Invariant", "Definition (per client, within the evaluation window)"],
           [["I1 Completeness", "every core event or alarm produced while the client was listening is received exactly once"],
            ["I2 Order", "received sequence numbers are strictly increasing (inversions and duplicates fail; gaps are judged by "
                         "I1 and I6)"],
            ["I3 Value agreement", "for every received record, kind, identifier and report values equal the core record "
                                   "(numbers within ε = 10⁻³)"],
            ["I4 State convergence", "after every change of control state, processing state, authority or limit, the client "
                                     "reports the new value within T = 500 ms"],
            ["I5 Single winner", "in every conflict round exactly one command is accepted, the winner is the policy's authority "
                                 "holder, the loser gets the mapped code, and both clients receive the CEID 1005 of the "
                                 "rejection"],
            ["I6 Loss attribution", "every event a client did not receive has a recorded cause in the door's send-side log "
                                    "(dropped_no_link, dropped_disabled, error) or an audited queue overflow"]],
           [3.6, 12.4]),
          ("p", "Latency, defined as client receive time minus core audit time (both from the same clock on the same "
                "machine), is reported but is not an invariant."),
          ("h2", "7.2 Scenarios"),
          ("p", "Each scenario starts the equipment with the simulated sensor and a fixed seed (42), starts both listening "
                "clients, performs its actions, stops everything and runs the checker. Table 7.2 describes the six scenarios."),
          ("table", "Scenarios",
           ["ID", "Scenario", "Main checks"],
           [["S1", "Normal operation: 60 s in ONLINE_LOCAL with the 1 Hz sample event", "I1, I2, I3, latency"],
            ["S2", "Alarm: REMOTE, GEM START, wait for alarm 5001, GEM STOP, wait for clear", "I1–I4 for alarm set and clear"],
            ["S3", "Command conflict: GEM START and OPC UA Start released by one barrier, 50 rounds; then LOCAL and GEM START",
             "I5 in every round; HCACK 0 vs BadUserAccessDenied; HCACK 2 in LOCAL"],
            ["S4", "Constant conflict: GEM sets 35 while OPC UA sets 45, 10 rounds; then OFFLINE with lease, OPC UA sets 45",
             "I4, I5; final value on all sides; GEM sees CEID 1006"],
            ["S5", "Disconnect: the GEM host process is killed for 10 s and restarted", "I6; losses per side"],
            ["S6", "Report scope: the GEM host redefines the report of CEID 1007 to drop EventTemp", "OPC UA event fields unchanged"]],
           [1.0, 10.0, 5.0]),
          ("h2", "7.3 Results"),
          ("p", "Table 7.3 shows the checker verdicts of the reported runs. Every applicable invariant passed on both "
                "interfaces in every scenario, and every scenario-specific check passed. N/A means that the scenario contains "
                "nothing the invariant could judge (for example, no conflict round outside S3 and S4)."),
          ("table", "Checker verdicts per scenario (GEM / OPC UA)",
           ["Scenario", "I1", "I2", "I3", "I4", "I5", "I6", "Scenario checks"],
           [["S3 conflict", "PASS / PASS", "PASS / PASS", "PASS / PASS", "PASS / PASS", "PASS", "PASS / PASS", "4/4"],
            ["S2 alarm", "PASS / PASS", "PASS / PASS", "PASS / PASS", "PASS / PASS", "N/A", "PASS / PASS", "5/5"],
            ["S5 disconnect", "PASS / PASS", "PASS / PASS", "PASS / PASS", "N/A", "N/A", "PASS / PASS", "2/2"],
            ["S1 normal", "PASS / PASS", "PASS / PASS", "PASS / PASS", "N/A", "N/A", "PASS / PASS", "—"],
            ["S4 constant conflict", "PASS / PASS", "PASS / PASS", "PASS / PASS", "PASS / PASS", "PASS", "PASS / PASS", "10/10"],
            ["S6 report scope", "PASS / PASS", "PASS / PASS", "PASS / PASS", "N/A", "N/A", "PASS / PASS", "5/5"]],
           [3.2, 1.9, 1.9, 1.9, 1.9, 1.2, 1.9, 2.1]),
          ("p", "Table 7.4 gives the key numbers behind the verdicts."),
          ("table", "Key observations per scenario",
           ["Scenario", "Observation"],
           [["S1", "62 of 62 events received on both sides; 0 inversions, 0 mismatches"],
            ["S2", "alarm set and clear carried sequence numbers 77 and 98 on the core, the GEM host and the OPC UA client; "
                   "state changes converged within 6.1 ms (GEM) and 79.5 ms (OPC UA)"],
            ["S3", "50 of 50 rounds with exactly one winner (GEM HCACK 0, OPC UA BadUserAccessDenied); the GEM request reached "
                   "the core first in 47 rounds, so in 3 rounds the OPC UA request arrived first and still lost; 104 state "
                   "changes converged within 17.1 ms (GEM) and 90.7 ms (OPC UA); in LOCAL, GEM START received HCACK 2"],
            ["S4", "10 of 10 constant conflicts won by the GEM host; final limit 35.0 on core, GEM and OPC UA; under the lease the "
                   "OPC UA write of 45 returned Good, the GEM host received CEID 1006 with value 45.0 from origin UA_CLIENT, and "
                   "a GEM write returned EAC 2"],
            ["S5", "GEM link reported NOT_COMMUNICATING 136 ms after the kill and COMMUNICATING again after 11 029 ms; the GEM "
                   "host missed 11 events, all logged as dropped_no_link; the OPC UA client missed none"],
            ["S6", "after the redefinition, 12 CEID 1007 reports on GEM no longer contained EventTemp; the OPC UA listener's "
                   "fields stayed {101, 102}; a second OPC UA subscription received only the two fields it selected"]],
           [1.6, 14.4]),
          ("h2", "7.4 Checker self-test"),
          ("p", "A checker that always passes proves nothing. The self-test copies a real S3 run, applies one deliberate "
                "corruption at a time and runs the checker again. Table 7.5 shows that the unmodified run passes and that each "
                "corruption is flagged by the invariant it violates."),
          ("table", "Checker self-test on a real run",
           ["Case", "Corruption", "Flagged by", "As expected"],
           [["baseline", "none", "nothing", "yes"],
            ["drop_event", "removed one GEM event that the door logged as sent", "I1 GEM, I5, I6 GEM", "yes"],
            ["swap_events", "swapped two consecutive OPC UA events", "I2 UA", "yes"],
            ["change_value", "added 1.0 °C to one GEM EventTemp", "I3 GEM", "yes"],
            ["delay_state", "delayed one OPC UA ControlState notification by 2 s", "I4 UA", "yes"],
            ["double_winner", "turned the rejection of one conflict round into an acceptance", "I5", "yes"]],
           [2.8, 7.4, 3.6, 2.2]),
          ("h2", "7.5 Race demonstration: why decide-and-apply must be atomic"),
          ("p", "To show what atomicity prevents, a deliberately unsafe variant of the core was written for demonstration only "
                "(it is not part of the equipment): it checks the arbiter under the lock, releases the lock, waits one "
                "millisecond and then applies the change. Both variants use the same arbiter in EQUIPMENT_OFFLINE with a "
                "maintenance lease, where the operator and the OPC UA client are both allowed to start, so only atomicity makes "
                "a difference. Over 200 concurrent START pairs, the unsafe variant produced two winners in 200 of 200 pairs; the "
                "real core produced exactly one winner in all 200 pairs (Fig. 7.2). In ONLINE_REMOTE the policy alone already "
                "rejects the OPC UA client, which is why the demonstration uses the lease state."),
          ("figure", "docs/screenshots_for_slides/07_inside_policy_model_browser_race_demo.png", "Dashboard Inside tab: policy "
                "table generated from the arbiter (active row highlighted), live browse of the information model, and the race "
                "demonstration (unsafe 200/200 double winners, real core 0/200)", 13.0),
          ("h2", "7.6 Evidence from the wire and the dashboard"),
          ("p", "Fig. 7.3 shows the dashboard's wire panel during a demonstration run. The same event, ProcessingStarted with "
                "sequence number 45, appears on the left as a SECS-II S6F11 (DATAID 45, DVID 101 = 45) and on the right as an "
                "OPC UA EventNotification with EventSeq 45. This is the join key the checker uses."),
          ("figure", "docs/user_guide/img/B14_wire_same_seq.png", "Wire panel: the same sequence number (45) in a SECS-II S6F11 "
                "(left, ①) and an OPC UA EventNotification (right, ②)", 15.5),
          ("p", "Fig. 7.4 shows the three columns while alarm 5001 is active: the GEM host, the core and the OPC UA client "
                "agree on every row. Fig. 7.5 shows the moment an OPC UA Start is rejected in ONLINE_REMOTE, with the real "
                "status code and reason, and the rejection in the arbiter feed."),
          ("figure", "docs/screenshots_for_slides/01_dashboard_overview_alarm_active_on_both_sides.png", "Dashboard during an "
                "over-temperature alarm: control panel, architecture and the three columns in agreement", 13.0),
          ("figure", "docs/user_guide/img/B05_ua_start_rejected.png", "OPC UA Start rejected with BadUserAccessDenied "
                "(“authority held by GEM_HOST”); the rejection is visible in all three columns and in the arbiter "
                "decisions", 11.0),
          ("h2", "7.7 Findings: semantic mismatches under simultaneous use"),
          ("p", "Using both interfaces at the same time exposed four places where SECS/GEM and OPC UA mean different things. "
                "They are findings of this work, measured rather than assumed."),
          ("h3", "7.7.1 No spooling: events lost while the host is disconnected"),
          ("p", "GEM defines spooling to buffer messages while the host is unreachable, but the GEM library used does not "
                "implement it, and OPC UA has no equivalent. In S5 the GEM host was killed for 10 s: the GEM door dropped 11 "
                "events, logged every one as `dropped_no_link`, and did not resend them after reconnection; the OPC UA client, "
                "which was unaffected, missed none. Because every loss has a recorded cause, invariant I6 passes: the losses are "
                "attributable, not silent. Fig. 7.6 shows the same effect on the dashboard."),
          ("figure", "docs/user_guide/img/B12_after_10s_disconnected.png", "GEM host disconnected: new events are marked "
                "dropped_no_link for GEM (③) while the OPC UA client keeps receiving; the GEM column is stale (①, ②)", 15.5),
          ("h3", "7.7.2 Same-value write: an event on GEM, nothing on OPC UA"),
          ("p", "GEM reports CEID 1006 (TempHighLimitChanged) for every accepted constant write. An OPC UA data-change "
                "subscription reports only a different value (default trigger: status and value). In S4 one accepted write "
                "re-wrote the limit with the value it already had: the GEM host received the event, the OPC UA client received "
                "no notification. Core and clients still agreed on the value. An OPC UA client therefore cannot see such a "
                "write through the variable; it would need an event."),
          ("h3", "7.7.3 Alarm acknowledgement means different things"),
          ("p", "In GEM, S5F2 acknowledges receipt of the S5F1 message. In OPC UA Alarms and Conditions, Acknowledge records "
                "that an operator has seen the alarm. Neither maps onto the other. In this stack the OPC UA acknowledge path is "
                "not implemented by the server library, so acknowledgement was left out of the model and documented."),
          ("h3", "7.7.4 Report scope: global on GEM, per subscription on OPC UA"),
          ("p", "GEM report definitions live on the equipment and apply to the GEM interface as a whole: in S6, one host's "
                "redefinition changed every later S6F11 for CEID 1007. OPC UA field selection is an event filter of one "
                "subscription: one client narrowing its fields did not affect another client. Report definitions also outlive "
                "the host session: after a host restart, the old reports continue to fire until they are redefined."),
          ("p", "Two further differences follow from the architecture. Command authority exists in GEM but not in OPC UA, and "
                "the arbiter supplies one rule for both (S3, S4). Delivery timing differs by construction: OPC UA delivers in "
                "publishing-interval batches, whereas GEM sends each S6F11 immediately."),
          ("h2", "7.8 Packet capture"),
          ("p", "A complete demonstration was captured with TShark 4.6.10 on the loopback adapter: 3 837 packets in 97.9 s. "
                "With the HSMS dissector applied to port 5000, 300 HSMS frames were decoded, including 82 S6F11 event reports "
                "and their 82 S6F12 replies; 1 596 OPC UA frames were decoded on port 4840. The capture shows that both "
                "interfaces are real protocols decoded by independent dissectors. OPC UA ran without security in this testbed, "
                "so payloads are readable; the capture is not an overhead or speed comparison."),
          ("h2", "7.9 Latency"),
          ("p", "Table 7.6 reports event latency per side. **These figures are not a protocol speed comparison.** The OPC UA "
                "figure includes the client's 50 ms publishing interval, chosen by the test client; GEM sees the temperature only "
                "through the 1 Hz sample event; and both clocks are the same Windows clock, whose granularity makes values below "
                "about 1 ms unreliable. The figures describe this configuration on one laptop over loopback."),
          ("table", "Event latency (client receive time − core audit time), ms",
           ["Scenario", "GEM n", "GEM p50", "GEM p95", "GEM max", "UA n", "UA p50", "UA p95", "UA max"],
           [["S1", "62", "0.0", "2.05", "2.27", "62", "48.6", "64.53", "78.74"],
            ["S2", "32", "0.0", "2.5", "6.08", "32", "50.5", "58.34", "78.96"],
            ["S3", "163", "0.0", "7.82", "17.08", "163", "46.97", "75.23", "90.69"],
            ["S4", "43", "2.0", "6.16", "13.45", "43", "37.65", "69.01", "71.91"],
            ["S5", "22", "0.0", "1.71", "2.0", "33", "50.75", "67.37", "75.17"],
            ["S6", "18", "0.0", "2.07", "2.75", "18", "69.38", "71.72", "74.84"]],
           [2.0, 1.6, 1.8, 1.8, 1.8, 1.6, 1.8, 1.8, 1.8])]
    return b


def chapter_8():
    b = [("h1", "CHAPTER 8: DISCUSSION, LIMITATIONS AND FUTURE WORK")]
    b += [("h2", "8.1 Discussion"),
          ("p", "The results support the three contributions. For N1, a single core with an arbiter in front of every state "
                "change was sufficient to keep two protocols consistent: all invariants passed in every scenario, and the "
                "conflict scenarios showed that the winner follows the policy even when the losing request arrives first. The "
                "race demonstration shows that this property depends on applying decision and change atomically; checking "
                "first and acting later fails immediately under concurrency. The library analysis showed that this "
                "architecture is not obtained for free: fourteen default behaviours of the two libraries would have created a "
                "second owner of state, a path around the arbiter, or a broken invariant."),
          ("p", "For N2, the GEM-derived model let an OPC UA client discover the tool's GEM identity by browsing, and the "
                "scenarios turned the mapping table from a design document into measured statements. The four mismatches are "
                "not defects of either standard; they show where an integrator must decide explicitly what the tool should do. "
                "For N3, joining both protocols' logs on one sequence number made consistency checkable message by message, and "
                "the send-side logs turned every loss into an attributable fact. The self-test shows that the checker can "
                "fail, which is what gives its PASS verdicts meaning."),
          ("h2", "8.2 Limitations"),
          ("bullets", ["**One simulated tool, one laptop, loopback.** Scenarios last 5–62 s with seed 42. There are no fab-scale, "
                       "network, long-duration or throughput results.",
                       "**Simplified GEM.** Three control states only (HOST_OFFLINE and ATTEMPT_ONLINE omitted); no spooling; "
                       "one host at a time; a single simulated chamber with a small set of identifiers. The work is GEM-inspired "
                       "and makes no compliance claim.",
                       "**OPC UA security disabled** for the demonstration (no security policy, anonymous access). No mapping "
                       "of OPC UA users or roles to arbiter origins exists; every OPC UA client is UA_CLIENT.",
                       "**Partial Alarms and Conditions.** The server library offers no Acknowledge or Confirm logic, so the "
                       "alarm is reported as events without the full condition state machine.",
                       "**Payload as text.** One event type carries the report values of all events as a JSON string, so OPC UA "
                       "clients cannot filter individual data values.",
                       "**Single concurrent commanding clients.** Multiple GEM hosts and several commanding OPC UA clients were "
                       "not tested; S6 used a second, read-only subscription.",
                       "**A connection-handling edge case in the GEM library.** The passive HSMS side stopped accepting "
                       "connections after a client connected and closed before session selection completed. The test harness "
                       "avoids this, but a host crashing at exactly that moment could leave the GEM interface unreachable until "
                       "restart."]),
          ("h2", "8.3 Future work"),
          ("bullets", ["GEM spooling and an OPC UA counterpart (buffered events or history access), so that losses can be "
                       "recovered rather than only attributed.",
                       "A server-side Alarms and Conditions state machine and a defined mapping between OPC UA acknowledgement "
                       "and the core.",
                       "Per-event OPC UA event types instead of a JSON payload, and export of the model as a NodeSet2 file for "
                       "use in other tools.",
                       "OPC UA security with user tokens mapped to arbiter origins, so that “many may read, few may "
                       "command” is enforced per user.",
                       "The full GEM control-state model, multi-host scenarios and runs with the real serial sensor.",
                       "Measurements on separate machines and longer runs to study behaviour under network faults."])]
    return b


def chapter_9():
    b = [("h1", "CHAPTER 9: CONCLUSION")]
    b += [("p", "This project set out to examine what happens when one semiconductor tool serves SECS/GEM and OPC UA at the "
                "same time. A testbed was built in which one equipment core owns all state, two protocol adapters act only as "
                "doors, and one arbiter decides every command from either protocol or the operator, with decision and state "
                "change applied atomically. A GEM-derived draft OPC UA information model exposes the GEM identity of every "
                "mapped variable, and every event on both protocols carries the core's sequence number."),
          ("p", "A consistency method based on a sequence-numbered audit log, send-side and receive-side logs and six formal "
                "invariants verified the system in six scenarios on one laptop over loopback. All applicable invariants passed "
                "on both interfaces; 50 simultaneous START conflicts each produced exactly one winner chosen by the policy, "
                "including the 3 rounds in which the losing request arrived first; and a self-test showed that the checker "
                "detects deliberate corruptions. A demonstration with an injected check-then-act gap produced two winners in "
                "200 of 200 pairs, while the atomic core produced none."),
          ("p", "The simultaneous use of both interfaces revealed four semantic mismatches that an integrator has to resolve "
                "explicitly: no spooling (11 events lost to the disconnected GEM host, each attributed), same-value writes "
                "visible only on GEM, different meanings of alarm acknowledgement, and global GEM reports versus per-client OPC "
                "UA filters. To our knowledge, based on our literature search, these interactions had not previously been "
                "measured on a tool serving both interfaces natively. The testbed, its logs and its documentation are openly "
                f"available at {REPO}, and the limitations in Chapter 8 mark the next steps toward a production-grade "
                "dual-interface tool.")]
    return b


def references():
    from references import REFS
    b = [("h1", "REFERENCES")]
    for key in sorted(REFS, key=lambda k: REFS[k]["sort"]):
        b.append(("ref", REFS[key]["apa"]))
    return b


def appendices():
    b = [("h1", "APPENDIX A: FULL ARBITRATION TRUTH TABLE")]
    b.append(("p", "The table lists the arbiter's decision for every combination of control state, lease, origin and action "
                   "for START, STOP and EC_WRITE. It is generated from the arbiter function itself, the same function that the "
                   "automated truth-table test checks. Control-state and lease changes are allowed for OPERATOR only, in every "
                   "state. The lease is valid only in EQUIPMENT_OFFLINE; a lease flag in another state is ignored."))
    b.append(("truth_table",))
    b += [("h1", "APPENDIX B: DEMONSTRATION PROCEDURE"),
          ("p", "The procedure below is used to demonstrate the testbed with the web dashboard "
                "(`python -m harness.web_view --port 8080`, then http://localhost:8080). Each step uses the dashboard's own "
                "buttons; the replies shown were observed in a demonstration run whose checker verdict was PASS."),
          ("table", "Demonstration procedure",
           ["Step", "Action", "What appears", "Explanation"],
           [["1", "Start system", "RUNNING; GEM link COMMUNICATING; the three columns agree", "one core, served over HSMS (port 5000) "
                                                                                       "and OPC UA (port 4840) at the same time"],
            ["2", "REMOTE", "reply OK; control ONLINE_REMOTE; authority GEM_HOST", "authority is derived from the control state"],
            ["3", "GEM START", "HCACK 0; EXECUTING on all three columns", "a real S2F41 over HSMS; OPC UA sees the same change"],
            ["4", "wait about 15 s", "alarm 5001 SET on all three columns; amber band on the chart", "S5F1 on GEM and an alarm "
                                                                                                  "event on OPC UA, same seq"],
            ["4a", "On the wire panel", "S6F11 and EventNotification with the same seq", "proof that both protocols are real"],
            ["5", "UA Start", "BadUserAccessDenied, “authority held by GEM_HOST”", "OPC UA may not command in REMOTE; "
                                                                                       "CEID 1005 informs both sides"],
            ["6", "GEM STOP", "HCACK 0; IDLE; temperature falls; alarm clears", "1 °C hysteresis, on both sides"],
            ["7", "Both START at once", "GEM HCACK 0, UA BadUserAccessDenied", "atomic decide-and-apply: exactly one winner"],
            ["8", "GEM STOP, then LOCAL", "ONLINE_LOCAL; authority OPERATOR", "operator takes control"],
            ["9", "GEM START", "HCACK 2, “equipment in LOCAL”", "host refused while the operator has authority"],
            ["10", "REMOTE", "authority GEM_HOST", "back to remote control"],
            ["11", "Kill GEM host", "GEM link NOT_COMMUNICATING", "OPC UA side unaffected"],
            ["12", "wait 10 s", "dropped_no_link for GEM, received for OPC UA", "no spooling; every loss attributed (I6)"],
            ["13", "Reconnect GEM host", "link up; new events received again", "old events are not replayed"],
            ["14", "Inside tab: Browse, Run race demo", "model tree with GEM identifiers; 200/200 vs 0/200", "draft model; why "
                                                                                                         "atomicity matters"],
            ["15", "Stop system", "checker PASS; ports released", "the same checker as the scenarios judges the run"]],
           [1.1, 3.3, 5.6, 6.0]),
          ("h1", "APPENDIX C: SELECTED DASHBOARD FIGURES"),
          ("p", "The annotated figures below are taken from the dashboard user guide in the repository "
                "(`docs/user_guide/USER_GUIDE.md`), which explains every numbered callout."),
          ("figure", "docs/user_guide/img/A1_tour_header_control_arch.png", "Dashboard header, control panel and architecture "
                "(callouts 1–14 of the user guide)", 15.5),
          ("figure", "docs/user_guide/img/B15_stop_system_verdict.png", "Stop system: checker verdict PASS and ports released", 13.0),
          ("figure", "docs/user_guide/img/A3_tour_wire_invariants.png", "Wire panel and live invariants", 13.0),
          ("h1", "APPENDIX D: HOW TO RUN THE TESTBED"),
          ("p", f"Source code: {REPO}. Requirements: Python 3.11 or 3.12. Do not install the unrelated package "
                "`secsgem-driver`, which also imports as `secsgem`."),
          ("code", """git clone https://github.com/Aryan514/Minor-project-
cd Minor-project-
python -m venv .venv
.venv\\Scripts\\activate            (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python -m pytest -q                 (expected: 101 passed)"""),
          ("table", "Commands",
           ["Purpose", "Command"],
           [["Web dashboard with control panel", "python -m harness.web_view --port 8080"],
            ["Replay a recorded run", "python -m harness.web_view --replay runs/sample_S3 --speed 3 --loop --port 8081"],
            ["Narrated demonstration", "python -m harness.demo --web"],
            ["All scenarios (about 5 minutes)", "python -m harness.scenarios all"],
            ["Checker and self-test", "python -m harness.checker runs/sample_S3 --self-test"],
            ["Race demonstration", "python -m harness.race_demo -n 200"],
            ["Equipment only", "python -m equipment.main"],
            ["GEM host / OPC UA client", "python -m clients.gem_host --listen; python -m clients.ua_client --listen"],
            ["Browse the OPC UA model", "python -m clients.ua_client --browse"]],
           [5.2, 10.8]),
          ("p", "Ports 5000 (HSMS), 4840 (OPC UA), 5100 (operator console) and 5101 (GEM host relay) must be free. Each "
                "scenario writes its logs to `runs/<scenario>_<time>/` and its summary to `results/`.")]
    return b


def chapters_4_to_9():
    return chapter_4() + chapter_5() + chapter_6() + chapter_7() + chapter_8() + chapter_9() + references()
