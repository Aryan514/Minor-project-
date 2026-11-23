# equipment/opcua_model.py
# Builds the GEM-derived draft OPC UA information model in code: TYPES first (SemiEquipmentType,
# ChamberType, GemMappedVariableType, GemCollectionEventType, alarm event type), then ONE instance
# Chamber1Tool created by instantiating SemiEquipmentType. Every GEM-mapped variable carries the
# properties GemId / GemKind / GemFormat, so a client can navigate UA node <-> GEM ID.
# Serves N2 (GEM-derived draft information model). Pure model construction: no equipment state here.
"""Address-space construction for the OPC UA door (CLAUDE.md section 8.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from asyncua import Node, Server, ua
from asyncua.common.instantiate_util import instantiate

from equipment import config

# UNECE unit code "CEL" (degree Celsius) as used by OPC UA EUInformation (Part 8).
EU_DEGC = ua.EUInformation(
    NamespaceUri="http://www.opcfoundation.org/UA/units/un/cefact",
    UnitId=4408652,
    DisplayName=ua.LocalizedText("°C"),
    Description=ua.LocalizedText("degree Celsius"),
)

# Browse names of the instance variables the adapter writes, relative to Chamber1Tool.
VAR_PATHS: dict[str, str] = {
    "ControlState": "GemInterface.ControlState",
    "ControlStateId": "GemInterface.ControlStateId",
    "Authority": "GemInterface.Authority",
    "CommunicationState": "GemInterface.CommunicationState",
    "LastEventSeq": "GemInterface.LastEventSeq",
    "ProcessingState": "ProcessingState",
    "ProcessingStateId": "ProcessingStateId",
    "Temperature": "Chamber1.Temperature",
    "TempHighLimit": "EquipmentConstants.TempHighLimit",
    "AlarmActive": "Alarms.ChamberOverTemp.Active",
    "Manufacturer": "Identification.Manufacturer",
    "Model": "Identification.Model",
    "SoftwareRevision": "Identification.SoftwareRevision",
}
METHOD_NAMES: tuple[str, ...] = ("Start", "Stop", "SetTempHighLimit")


@dataclass
class UaModel:
    """Handles to the nodes the OPC UA adapter needs."""

    idx: int
    tool: Node
    variables: dict[str, Node]
    methods: dict[str, Node]
    alarm_node: Node
    collection_event_type: Node
    alarm_event_type: Node
    alarm_fallback_event_type: Node
    types: dict[str, Node] = field(default_factory=dict)


async def _mandatory(node: Node) -> Node:
    """Mark a type child as Mandatory so instantiation copies it (returns the node for chaining)."""
    await node.set_modelling_rule(True)
    return node


async def _mark_tree_mandatory(node: Node) -> None:
    """Mark every hierarchical child below a type node Mandatory.

    asyncua's instantiate() copies children but not their HasModellingRule reference, so nested
    declarations (e.g. GemId under Chamber1.Temperature) would be skipped when the type is
    instantiated again. Walking the finished type tree once fixes that.
    """
    for child in await node.get_children():
        if not await child.get_referenced_nodes(refs=ua.ObjectIds.HasModellingRule):
            await child.set_modelling_rule(True)
        await _mark_tree_mandatory(child)


async def _add_var(parent: Node, idx: int, name: str, value: Any, vtype: ua.VariantType) -> Node:
    """Plain (non-GEM) variable declaration on a type."""
    return await _mandatory(await parent.add_variable(idx, name, ua.Variant(value, vtype)))


async def _add_gem_var(
    parent: Node,
    idx: int,
    gem_var_type: Node,
    name: str,
    value: Any,
    vtype: ua.VariantType,
    gem_id: int,
    gem_kind: str,
    gem_format: str,
    eu_range: Optional[tuple[float, float]] = None,
    degc: bool = False,
) -> Node:
    """Declare a GEM-mapped variable (an instance of GemMappedVariableType) on a type node."""
    node = (await instantiate(parent, gem_var_type, bname=ua.QualifiedName(name, idx), idx=idx))[0]
    await node.write_attribute(
        ua.AttributeIds.DataType, ua.DataValue(ua.Variant(ua.NodeId(int(vtype)), ua.VariantType.NodeId))
    )
    await node.write_value(ua.Variant(value, vtype))
    await (await node.get_child(f"{idx}:GemId")).write_value(ua.Variant(gem_id, ua.VariantType.UInt32))
    await (await node.get_child(f"{idx}:GemKind")).write_value(ua.Variant(gem_kind, ua.VariantType.String))
    await (await node.get_child(f"{idx}:GemFormat")).write_value(ua.Variant(gem_format, ua.VariantType.String))
    if degc:
        await _mandatory(await node.add_property(0, "EngineeringUnits", EU_DEGC))
    if eu_range is not None:
        await _mandatory(await node.add_property(0, "EURange", ua.Range(Low=eu_range[0], High=eu_range[1])))
    return await _mandatory(node)


async def _noop_method(parent: ua.NodeId, *args: Any) -> list[ua.Variant]:
    """Placeholder on the TYPE's method declarations; the adapter links real callbacks on the instance."""
    del parent, args
    return []


async def build_types(server: Server, idx: int) -> dict[str, Node]:
    """Create the reusable types (no instance yet)."""
    types: dict[str, Node] = {}

    # --- GemMappedVariableType: every GEM-mapped variable carries GemId / GemKind / GemFormat ----------
    base_dv = server.get_node(ua.ObjectIds.BaseDataVariableType)
    gem_var_type = await base_dv.add_variable_type(idx, "GemMappedVariableType", ua.ObjectIds.BaseDataType)
    await _mandatory(await gem_var_type.add_property(idx, "GemId", ua.Variant(0, ua.VariantType.UInt32)))
    await _mandatory(await gem_var_type.add_property(idx, "GemKind", ua.Variant("", ua.VariantType.String)))
    await _mandatory(await gem_var_type.add_property(idx, "GemFormat", ua.Variant("", ua.VariantType.String)))
    types["GemMappedVariableType"] = gem_var_type

    base_obj = server.get_node(ua.ObjectIds.BaseObjectType)

    # --- ChamberType: one process chamber with its temperature (SVID 1) ------------------------------
    chamber_type = await base_obj.add_object_type(idx, "ChamberType")
    await _add_gem_var(chamber_type, idx, gem_var_type, "Temperature", config.SIM_AMBIENT_C, ua.VariantType.Double,
                       config.SVID_CHAMBER_TEMP, "SVID", "F4", eu_range=(0.0, 100.0), degc=True)
    await _mark_tree_mandatory(chamber_type)  # before ChamberType is instantiated inside SemiEquipmentType
    types["ChamberType"] = chamber_type

    # --- SemiEquipmentType: the whole tool --------------------------------------------------------
    semi = await base_obj.add_object_type(idx, "SemiEquipmentType")
    ident = await _mandatory(await semi.add_object(idx, "Identification"))
    await _add_var(ident, idx, "Manufacturer", "", ua.VariantType.String)
    await _add_var(ident, idx, "Model", "", ua.VariantType.String)
    await _add_var(ident, idx, "SoftwareRevision", "", ua.VariantType.String)

    gem_if = await _mandatory(await semi.add_object(idx, "GemInterface"))
    await _add_var(gem_if, idx, "ControlState", "", ua.VariantType.String)
    await _add_gem_var(gem_if, idx, gem_var_type, "ControlStateId", 0, ua.VariantType.Byte,
                       config.SVID_CONTROL_STATE, "SVID", "U1")
    await _add_gem_var(gem_if, idx, gem_var_type, "Authority", "", ua.VariantType.String,
                       config.SVID_AUTHORITY, "SVID", "A")
    await _add_var(gem_if, idx, "CommunicationState", "NOT_COMMUNICATING", ua.VariantType.String)
    await _add_gem_var(gem_if, idx, gem_var_type, "LastEventSeq", 0, ua.VariantType.UInt32,
                       config.SVID_LAST_EVENT_SEQ, "SVID", "U4")

    await _add_var(semi, idx, "ProcessingState", "", ua.VariantType.String)
    await _add_gem_var(semi, idx, gem_var_type, "ProcessingStateId", 0, ua.VariantType.Byte,
                       config.SVID_PROCESSING_STATE, "SVID", "U1")

    chamber = (await instantiate(semi, chamber_type, bname=ua.QualifiedName("Chamber1", idx), idx=idx))[0]
    await _mandatory(chamber)

    ecs = await _mandatory(await semi.add_object(idx, "EquipmentConstants"))
    ec = config.equipment_constant(config.ECID_TEMP_HIGH_LIMIT)
    await _add_gem_var(ecs, idx, gem_var_type, "TempHighLimit", ec.default, ua.VariantType.Double,
                       ec.ecid, "ECID", ec.gem_format, eu_range=(ec.min_value, ec.max_value), degc=True)

    alarms = await _mandatory(await semi.add_object(idx, "Alarms"))
    alarm_def = config.ALARMS[0]
    alarm_obj = await _mandatory(await alarms.add_object(idx, alarm_def.name))
    await _mandatory(await alarm_obj.add_property(idx, "ALID", ua.Variant(alarm_def.alid, ua.VariantType.UInt32)))
    await _mandatory(await alarm_obj.add_property(idx, "AlarmText", ua.Variant(alarm_def.text, ua.VariantType.String)))
    await _add_var(alarm_obj, idx, "Active", False, ua.VariantType.Boolean)

    for name in ("Start", "Stop"):
        await _mandatory(await semi.add_method(idx, name, _noop_method, [], []))
    value_arg = ua.Argument(Name="value", DataType=ua.NodeId(ua.ObjectIds.Double), ValueRank=-1,
                            Description=ua.LocalizedText("new TempHighLimit in degC (ECID 201)"))
    set_limit = await _mandatory(await semi.add_method(idx, "SetTempHighLimit", _noop_method, [value_arg], []))
    for prop in await set_limit.get_properties():  # InputArguments must be copied to the instance too
        await _mandatory(prop)
    await _mark_tree_mandatory(semi)
    types["SemiEquipmentType"] = semi

    # --- Event types ------------------------------------------------------------------------------
    types["GemCollectionEventType"] = await server.create_custom_event_type(
        idx, "GemCollectionEventType", ua.ObjectIds.BaseEventType,
        [("CEID", ua.VariantType.UInt32), ("EventSeq", ua.VariantType.UInt32),
         ("Origin", ua.VariantType.String), ("Payload", ua.VariantType.String)],
    )
    # Preferred alarm representation: an OffNormalAlarmType subtype (Alarms & Conditions).
    types["GemOffNormalAlarmType"] = await server.create_custom_event_type(
        idx, "GemOffNormalAlarmType", ua.ObjectIds.OffNormalAlarmType,
        [("ALID", ua.VariantType.UInt32), ("EventSeq", ua.VariantType.UInt32)],
    )
    # Documented fallback (CLAUDE.md 8.1) if the A&C path does not work with asyncua.
    types["GemAlarmEventType"] = await server.create_custom_event_type(
        idx, "GemAlarmEventType", ua.ObjectIds.BaseEventType,
        [("ALID", ua.VariantType.UInt32), ("Active", ua.VariantType.Boolean),
         ("EventSeq", ua.VariantType.UInt32), ("Text", ua.VariantType.String)],
    )
    return types


async def build_model(server: Server, idx: int) -> UaModel:
    """Create the types, then instantiate Objects/Chamber1Tool and return node handles."""
    types = await build_types(server, idx)
    objects = server.nodes.objects
    tool = await objects.add_object(ua.NodeId(config.TOOL_NAME, idx), ua.QualifiedName(config.TOOL_NAME, idx),
                                    objecttype=types["SemiEquipmentType"].nodeid)

    def child(path: str) -> Node:
        return server.get_node(ua.NodeId(f"{config.TOOL_NAME}.{path}", idx))

    variables = {key: child(path) for key, path in VAR_PATHS.items()}
    methods = {name: child(name) for name in METHOD_NAMES}
    # Fail fast if instantiation did not create something we rely on.
    for node in [*variables.values(), *methods.values()]:
        await node.read_browse_name()

    await variables["Manufacturer"].write_value(config.MANUFACTURER)
    await variables["Model"].write_value(config.MDLN)
    await variables["SoftwareRevision"].write_value(config.SOFTREV)

    return UaModel(
        idx=idx,
        tool=tool,
        variables=variables,
        methods=methods,
        alarm_node=child(f"Alarms.{config.ALARMS[0].name}"),
        collection_event_type=types["GemCollectionEventType"],
        alarm_event_type=types["GemOffNormalAlarmType"],
        alarm_fallback_event_type=types["GemAlarmEventType"],
        types=types,
    )
