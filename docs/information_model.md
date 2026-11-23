# GEM-derived draft OPC UA information model (N2)

Namespace URI `urn:minor-project:semi-equipment-mini`. The model is built in code (`equipment/opcua_model.py`), **types
first, then one instance created by instantiating the type**, so it is a reusable model and not a set of ad-hoc nodes.
This is a draft information model for this project. It is not an OPC UA companion specification.

## Types

| Type | Kind | Base | Content |
|---|---|---|---|
| `GemMappedVariableType` | VariableType | BaseDataVariableType | Mandatory properties `GemId` (UInt32), `GemKind` ("SVID"/"ECID"), `GemFormat` (SECS-II format, e.g. "F4") |
| `ChamberType` | ObjectType | BaseObjectType | `Temperature` (GemMappedVariableType, Double, EngineeringUnits °C, EURange 0..100, GemId 1 / SVID / F4) |
| `SemiEquipmentType` | ObjectType | BaseObjectType | `Identification`, `GemInterface`, `ProcessingState(+Id)`, `Chamber1` (ChamberType), `EquipmentConstants`, `Alarms`, methods `Start`, `Stop`, `SetTempHighLimit(value: Double)` |
| `GemCollectionEventType` | EventType | BaseEventType | `CEID` UInt32, `EventSeq` UInt32, `Origin` String, `Payload` String (JSON of the report values by VID) |
| `GemOffNormalAlarmType` | EventType | **OffNormalAlarmType** (Alarms & Conditions) | + `ALID` UInt32, `EventSeq` UInt32 |
| `GemAlarmEventType` | EventType | BaseEventType | documented fallback: `ALID`, `Active`, `EventSeq`, `Text` (not used; A&C works) |

## Instance tree (as printed by `python -m clients.ua_client --browse`)

```
Chamber1Tool [Object] type=SemiEquipmentType  ns=2
  Identification          Manufacturer, Model='CHAMBER-SIM', SoftwareRevision='0.1'
  GemInterface
    ControlState          String  'ONLINE_LOCAL'
    ControlStateId        Byte    <-> GEM SVID 2 (U1)   type=GemMappedVariableType
    Authority             String  <-> GEM SVID 4 (A)
    CommunicationState    String  GEM link COMMUNICATING / NOT_COMMUNICATING
    LastEventSeq          UInt32  <-> GEM SVID 5 (U4)
  ProcessingState         String  'IDLE'
  ProcessingStateId       Byte    <-> GEM SVID 3 (U1)
  Chamber1                type=ChamberType
    Temperature           Double  <-> GEM SVID 1 (F4)   EngineeringUnits °C, EURange 0..100
  EquipmentConstants
    TempHighLimit         Double  <-> GEM ECID 201 (F4) EURange 20..80, READ-ONLY (write via SetTempHighLimit)
  Alarms
    ChamberOverTemp       ALID=5001, AlarmText, Active (Boolean)
  Start()  Stop()  SetTempHighLimit(value)
```

Node ids are strings that mirror the browse path (`ns=2;s=Chamber1Tool.Chamber1.Temperature`) because asyncua
derives instance child ids from the parent's string id. All events are emitted with `EmittingNode = Chamber1Tool`;
the alarm's `SourceNode` is `Alarms/ChamberOverTemp`.

## Design decisions

1. **UA node ↔ GEM ID navigation by property.** Every GEM-mapped variable has `HasProperty` children `GemId`,
   `GemKind`, `GemFormat`. A client navigates node → `GemId` to find the GEM identity. In the other direction, a
   browse that filters on `GemId` finds the node for a GEM ID. We chose properties over a custom non-hierarchical
   reference type because they appear in every generic client (UaExpert) without type knowledge.
2. **Two variables per enumerated GEM state** (`ControlState` String + `ControlStateId` Byte). The numeric one is the
   GEM mapping (SVID 2 values 1/4/5); the string one is for people (decision D13).
3. **DVIDs are not variables.** They are only meaningful at event time, so they appear only inside the event
   (`EventSeq` as a field, the rest in `Payload`).
4. **Event payload as JSON string.** One event type covers all seven CEIDs. A per-CEID event type would let UA
   clients filter individual DVs. That is listed as future work.
5. **Every value carries the core's timestamp** as `SourceTimestamp`. The checker joins UA data changes to audit records
   by that timestamp (I4).
6. **TempHighLimit is read-only**; `SetTempHighLimit(value)` returns a per-call StatusCode from the arbiter (D10).
7. **Alarm as Alarms & Conditions events**: `GemOffNormalAlarmType` with ActiveState/Id, Retain, ConditionName,
   ConditionId (`NodeId`), Severity 700, Message; ConditionRefresh replays it. asyncua 1.1.8 provides no server-side
   Acknowledge/Confirm, so acknowledgement is not modelled (see `mapping.md`, `limitations.md`).
8. **Security**: NoSecurity + anonymous, for the loopback demo only.
