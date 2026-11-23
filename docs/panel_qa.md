# Likely panel questions, with short honest answers

**1. Why not only OPC UA? Why keep SECS/GEM?**
Fab host systems (MES, EAP) speak SECS/GEM today, and a tool that drops it cannot be integrated in an existing fab.
Newer consumers such as analytics, digital twins, sub-fab systems and non-semiconductor MES prefer OPC UA. So tools are asked for
*both*. The question this project studies is what happens when both are live at the same time on one tool.

**2. Isn't this just a gateway?**
No. A gateway translates one protocol into the other, so one side is always a copy. Here neither interface is a
copy: both doors read the same core and submit commands to the same arbiter. The contribution is not the
translation. It is the single-core architecture with a tested authority policy (N1), the semantic gaps observed under
simultaneous use (N2), and a method to measure consistency (N3).

**3. It is simulated. Is any of this real?**
The protocols are real: genuine HSMS on TCP 5000 (secsgem) and a genuine OPC UA server on TCP 4840 (asyncua). Any
standard client, such as UaExpert or a SECS host, or Wireshark with its HSMS/OPC UA dissectors, can connect. Only the chamber physics is
simulated (seeded, reproducible). An ESP32 + DS18B20 serial sensor class exists in code but has not been tested with
hardware, and its firmware is optional future work. The claims are limited
to "one simulated tool, one laptop, loopback". There are no fab-scale or performance claims.

**4. What is new compared with Golra & Engel 2021?**
To our knowledge they mapped GEM to an OPC UA model but did not study both interfaces in use simultaneously and left out
spooling. We (a) serve both natively from one core, (b) define and test who may command the tool when two interfaces
compete (S3: 50/50 concurrent conflicts with a single, policy-determined winner), and (c) measure consistency against
a seq-numbered oracle, including disconnects (S5) and report-scope differences (S6).

**5. How do you know the two interfaces really agree?**
Every event and alarm has a global sequence number assigned inside the core lock, and that number travels inside every
GEM message (DVID 101, `seq=` in S5F1) and every UA event (`EventSeq`). The checker joins all logs on it and evaluates six
invariants. Across S1–S6: 351 window events per side, 0 value mismatches, 0 order inversions, 0 unexplained losses.

**6. How do you know the checker isn't just always saying PASS?**
The self-test corrupts a copy of a real run in five ways (drop, swap, change a value, delay a state change, make two
winners). Each is flagged by the right invariant (`results/checker_self_test.md`, also a pytest). During development
the checker *did* fail twice, and we investigated both: one was a checker bug (Windows clock granularity), the other a
real semantic mismatch (same-value write, S4) that we recorded as a finding instead of hiding it.

**7. What happens when two clients command the tool at the same moment?**
The arbiter and the state change run under one lock, so there is no check-then-act race. In REMOTE the GEM host
wins *because of the policy*, not because of timing: in 3 of 50 S3 rounds the UA request arrived first and still lost.
The loser gets `BadUserAccessDenied`, and both clients receive a CEID 1005 naming who was refused and why.

**8. Why did you override library behaviour? Isn't that risky?**
Used as-is, secsgem would have let the host change control state itself (S1F15/F17), answered every remote command with
"finish later" before the arbiter decided, kept its own copy of the equipment constant, and sent events from a new
thread each time (possible reordering). Each of these breaks the single-core or invariant guarantees. Each override is
listed with its reason and its verification in `docs/library_overrides.md`. Two overrides fix Windows bugs in secsgem's
accept thread that made the equipment unable to shut down.

**9. What did you measure, and what not?**
Measured: completeness, order, value agreement, state convergence (≤ 500 ms), single winner, loss attribution, and event
latency, on one laptop over loopback. Not measured: throughput or scalability, behaviour on a real network or real
fab host, security (NoSecurity was used), long-duration stability, or multi-host GEM. Latencies are not a protocol
comparison: UA includes our 50 ms publishing interval.

**10. What are the main limitations?**
Simplified 3-state GEM control model; no GEM spooling (secsgem has none); alarm acknowledge over UA not available
(asyncua has no server-side A&C methods); one HSMS session; anonymous OPC UA without security; simulated sensor; the
equipment is not GEM-compliant and the UA model is a draft, not a companion specification. Full list:
`docs/limitations.md`.

**11. What did you find that you did not expect?**
(a) Same-value writes: GEM reports them as an event, while a UA data subscription stays silent (S4). (b) GEM report
definitions are global and outlive the host session: a restarted host first receives reports defined by its
predecessor (S5/D23). (c) secsgem 0.3.0 never notices a host disconnect on its own (`on_connection_closed` is never
called), so we hooked the HSMS event to attribute losses correctly.

**12. Why does UA latency look worse than GEM?**
It is a configuration effect, not a protocol property: UA notifications are delivered in publishing cycles, and our
client asks for 50 ms. GEM sends each S6F11 immediately on loopback. On the other side, UA delivers every 0.5 s
temperature sample, while GEM only sees the 1 Hz report. Each protocol's delivery model has its own trade-off, and
we deliberately make no "faster than" claim.
