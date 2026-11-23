# Wireshark capture of the panel demo

File: `results/demo_capture.pcapng`. Size 509 996 bytes (509 kB), 3837 packets, capture duration 97.9 s
(`capinfos`). Recorded on 2026-11-24 with TShark (Wireshark) 4.6.10 and Npcap loopback support, while
`python -m harness.demo --web --auto` ran (demo verdict: overall PASS; run `runs/DEMO_20261124-023204`).

## What this capture is for, and what it is not for

- **For:** showing that both interfaces are real protocols on real sockets. HSMS/SECS-II on TCP 5000 and OPC UA
  Binary on TCP 4840 are decoded by Wireshark's own dissectors, independently of our code.
- **Not for:** overhead, bandwidth or speed comparisons between the protocols. It is one short demo on loopback, and
  the message mix depends entirely on what the demo does (the `--browse` step alone produces hundreds of
  Read/Browse requests).
- The demo runs OPC UA with **no security** (`NoSecurity`, anonymous; see `docs/limitations.md`). Both payloads are
  therefore readable in plain text. A production setup would sign/encrypt OPC UA, and HSMS has no built-in
  encryption at all.

## How it was captured

```
D:\Wireshark\tshark.exe -i \Device\NPF_Loopback -f "tcp port 5000 or tcp port 4840" -w results\demo_capture.pcapng
```

Interface `\Device\NPF_Loopback` = "Adapter for loopback traffic capture" (`tshark -D`, entry 8 on this laptop).
tshark was started before the demo and stopped with Ctrl+Break afterwards (exit code 0, "3837 packets captured").
No Administrator rights were needed.

## HSMS (TCP 5000)

Wireshark 4.6.10 has an HSMS dissector ("High-speed SECS Message Service Protocol", filter `hsms`), but it does
**not** decode port 5000 automatically: `tshark -r … -Y hsms` returned 0 frames. With decode-as it returned 300
frames:

```
tshark -r results\demo_capture.pcapng -d tcp.port==5000,hsms -Y hsms
```

(In the Wireshark GUI: *Analyze → Decode As…*, field `TCP port`, value `5000`, current `HSMS`.)

| Message | Count | Meaning in the demo |
|---|---|---|
| S1F13 / S1F14 | 4 / 4 | establish communication (both sides send S1F13; two host sessions: before and after the kill) |
| S1F3 / S1F4 | 2 / 2 | host reads SVIDs 1–5 (start snapshot of each session) |
| S2F13 / S2F14 | 2 / 2 | host reads ECID 201 |
| S2F33 / S2F34 | 16 / 16 | define reports |
| S2F35 / S2F36 | 14 / 14 | link reports to CEIDs |
| S2F37 / S2F38 | 16 / 16 | enable/disable event reports |
| S2F41 / S2F42 | 5 / 5 | remote commands START/STOP and their HCACK |
| S5F3 / S5F4 | 2 / 2 | enable alarm 5001 |
| S5F1 / S5F2 | 2 / 2 | alarm 5001 set and clear |
| S6F11 / S6F12 | 82 / 82 | event reports and their acknowledgements |
| SType 1 / 2 (Select req/rsp) | 2 / 2 | HSMS session selection |
| SType 5 / 6 (Linktest req/rsp) | 2 / 2 | link test |
| SType 9 (Separate) | 2 | host closes the session |
| **Total** | **300** | 290 data messages + 10 control messages = 300 decoded frames |

Counting command: `-Y "hsms.header.stype==0" -T fields -e hsms.header.stream -e hsms.header.function` (data
messages) and `-Y "hsms.header.stype!=0" -e hsms.header.stype` (control messages).

### Example: one decoded S6F11 (frame 924)

```
High-speed SECS Message Service Protocol
    Packet length: 41
    Header (S06F11)
        Session ID: 0
        Stream 6, Response requested: Yes
        Function: 11
        PType (Presentation type): SECS (0)
        SType (Session type): Data message (0)
    List (3 items)
        U1 (1 items)  Value: 18          <- DATAID = event seq (decision D16)
        U2 (1 items)  Value: 1007        <- CEID 1007 TempSample
        List (1 items)
            List (2 items)
                U2 (1 items)  Value: 1007    <- RPTID
                List (2 items)
                    U4 (1 items)  Value: 18      <- DVID 101 EventSeq
                    F4 (1 items)  Value: 24.972  <- DVID 102 EventTemp
```

(The dissector prints each item's format bytes too. They are omitted here.) The GEM host logged the same event as
`{"kind": "event", "id": 1007, "seq": 18, "data": {"101": 18, "102": 24.972000122070312}}`.

## OPC UA (TCP 4840)

Decoded automatically: `tshark -r results\demo_capture.pcapng -Y opcua` → 1596 frames.

| Service / message | Requests | Responses |
|---|---|---|
| Read | 286 | 285 |
| Publish (subscription notifications) | 230 | 229 |
| Browse | 200 | 200 |
| TranslateBrowsePathsToNodeIds | 64 | 64 |
| CreateSession / ActivateSession | 3 / 3 | 3 / 3 |
| CreateSubscription | 1 | 1 |
| CreateMonitoredItems | 2 | 2 |
| **Call** | **1** | **1** |
| CloseSession | 2 | 2 |
| Hello / Acknowledge / OpenSecureChannel / CloseSecureChannel | 3 / 3 / 6 / 2 | — |

Counting command: `-Y opcua -T fields -e _ws.col.Info`, grouped by service name. The three sessions are the
listening UA client, the `--browse` client and the harness's session for the simultaneous START. The listening
client was not closed gracefully (the demo stops it), so there are only 2 CloseSession requests. The one request
without a response in Read and Publish was outstanding when the capture stopped.

### Example: the decoded OPC UA Call (frames 2838 → 2844)

```
CallRequest
    MethodsToCall: Array of CallMethodRequest
        [0]: CallMethodRequest
            ObjectId: NodeId   Namespace Index: 2  Identifier String: Chamber1Tool
            MethodId: NodeId   Namespace Index: 2  Identifier String: Chamber1Tool.Start
            InputArguments: Array of Variant  ArraySize: 0
CallResponse
    ResponseHeader
        ServiceResult: 0x00000000 [Good]
    Results: Array of CallMethodResult
        [0]: CallMethodResult
            StatusCode: 0x801f0000 [BadUserAccessDenied]
```

The service itself succeeded, and the method's own result carries the arbiter's refusal as a per-call StatusCode
(decision D10).

### The simultaneous START on the wire

| Frame | Time (IST) | Direction | Message | Decoded value |
|---|---|---|---|---|
| 2828 | 02:33:00.905177 | host → equipment :5000 | S2F41 | RCMD `START` |
| 2832 | 02:33:00.907704 | equipment → host | S2F42 | HCACK `00` (accepted) |
| 2838 | 02:33:00.908690 | UA client → equipment :4840 | CallRequest | `Chamber1Tool.Start` |
| 2844 | 02:33:00.910839 | equipment → UA client | CallResponse | `BadUserAccessDenied` |

Both requests were released by one barrier in the harness. On the wire the UA request follows the GEM request by
3.5 ms. The winner is decided by the arbiter's policy (REMOTE gives GEM authority), not by this ordering: in S3, 3 of
50 rounds had the UA request first and it still lost (`results/S3_summary.md`). These timestamps only show order
on this machine. They are not a protocol speed comparison.
