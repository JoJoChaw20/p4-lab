# Week 5 assignment — Put a limit on the tunnel

Student ID (last 4 digits only): **5019**

Draft in progress: C1–C5 experiments complete; rollout choice, AI-use confirmation
and final review are pending.
The student will review the explanations before submission.

## 1. Analysis: the loop

Both switches ran the finished lab program, identical to `tunnel_v1.p4`.
The prediction was that one tunnelled packet would keep circulating because the
tunnel forwarding action has no hop counter or expiry check.

The table dump identified s2's exit-3 entry as handle `0x2`. The command
`sh ./p4cli s2 "table_modify MyIngress.myTunnel_exact MyIngress.myTunnel_forward 2 1"`
changed its output from port 3 (h3) to port 1 (s1). s1 already sent exit 3 out
port 2 towards s2. Then `h1 python3 send.py 10.19.0.3 "loop" --tunnel 3`
injected one packet. The initial processing counts were zero on both switches.

The live counts in [loop-before.txt](evidence/loop-before.txt) rose from
63 on s1 and 62 on s2 to 103 and 102 after `sleep 5`. However, BMv2 rotated
both logs during the interval, so these are counts in the current files, not
cumulative totals. Counting events across the preserved current and rotated
files at the logged timestamp cutoffs gives:

| Log timestamp cutoff (UTC, 10 November 2026) | s1 passes | s2 passes |
|---|---:|---:|
| 09:12:01.109 | 62 | 62 |
| 09:12:06.125 | 1700 | 1699 |

These are reconstructions from millisecond log timestamps. The live `grep`
commands ran just after the printed timestamps, which explains the one-pass
difference at the first observation. The counts show continued circulation
over approximately five seconds, not thousands of separately sent packets.
Neither receiver logged delivery of the test packet. `exit` stopped the network
cleanly; the final archived totals, including passes during shutdown, are
1706 on s1 and 1705 on s2. The receiver warnings about the network going down
were captured after shutdown. Full logs, including rotated files, are in
[loop-before-logs.tar.gz](evidence/loop-before-logs.tar.gz).

The tunnel path selects `myTunnel_exact` and bypasses `ipv4_forward`, so it
does not decrement the inner IPv4 TTL. Even the plain IPv4 path would not
reliably stop a forwarding loop in this program: `ipv4_forward` subtracts one
from the 8-bit TTL but never checks for expiry. A matching packet with TTL 1
is forwarded with TTL 0; on the next forwarding pass, subtraction wraps 0
to 255. This IPv4 conclusion comes from inspecting the code, not from an
additional IPv4-loop experiment.

## 2. Design: the hop limit

After discussing the alternatives with Codex, I accepted an 8-bit `hops` field
after `dst_id`, with a sender default of 4. One byte provides values from 0 to
255. Appending it keeps `proto_id` and `dst_id` at their existing offsets, but
does not guarantee compatibility: an old parser still expects IPv4 immediately
after the original four-byte tunnel header. Section 5 tests this limitation.

The budget means the number of additional switches allowed to forward the
packet. In ingress, a tunnel packet arriving with 0 is dropped before the
tunnel table can forward it. Otherwise, the tunnel forwarding action subtracts
one and sets the output port. An arriving value of 1 therefore permits one
final forwarding operation with 0 on the wire. Checking first prevents unsigned
wraparound. I recognised that a zero budget means the packet must be dropped
because its budget is exhausted.

The default of 4 covers the normal two-switch route and keeps loop experiments
short. The prediction is that a normal receiver will see 2 remaining. In the
loop, there should be four forwards (s1, s2, s1, s2), followed by a drop on the
fifth switch arrival at s1. These predictions were recorded before C4; the
measured results are in section 4.

All three components use the same order: 16-bit `proto_id`, 16-bit `dst_id`,
then 8-bit `hops`. P4's existing whole-header extract and emit statements now
consume and write five tunnel bytes. Both host scripts use the matching Scapy
layout; the sender sets the budget and the receiver prints it.

## 3. Implementation

`tunnel.p4` adds the field and an ingress zero check. The decrement is in
`myTunnel_forward`, so a table miss still drops without consuming a forwarding
budget. The zero branch skips the table entirely, preventing a later forwarding
action from overwriting the drop decision. The plain IPv4 branch is unchanged.

`send.py` provides `--hops`, defaulting to 4, and rejects values outside 0–255
before sending. `receive.py` prints the remaining value and puts its sniffing
startup in `main()` so its header definition can be checked without starting
a capture. `tunnel_v1.p4` remains the original program for C5.

[compile.txt](evidence/compile.txt) records successful local P4 compilation and
Python syntax checks. Offline checks confirmed the five-byte layout and receiver
decoding at budgets 0, 1, 2, 4 and 255, and rejection of -1 and 256 by the sender.
The first Scapy import was blocked by sandbox socket permissions; the same check
passed outside that sandbox. These checks do not establish switch delivery or
the GitHub check status; those require the later experiments and submission.

## 4. Evidence: it works

Both switches ran the new `tunnel.p4`. In [delivery.txt](evidence/delivery.txt),
the default-budget packets reached h2 through exit 2 and h3 through exit 3.
Both receivers printed `hops=2` and inner IPv4 TTL 64, matching two tunnel
forwards from a starting budget of 4. The exit-2 packet deliberately still
had IP destination `10.19.0.3`: reception at h2 shows that the tunnel exit
continues to determine forwarding. Plain `h1 ping -c 2 h3` received both replies
with TTL 62 and 0% loss.

The boundary tests used the normal two-switch route to h3:

| Starting budget | Observed result |
|---|---|
| 0 | No receiver delivery; s1's drop count increased by one |
| 1 | No receiver delivery; s2's drop count increased by one |
| 2 | h3 received `c4-boundary-2` with `hops=0`; no additional drops |

The zero comparisons in the switch logs confirm the first two drops. s1 already
had one unrelated startup drop: the parser identified EtherType `86dd` (IPv6).
The evidence therefore uses changes in the drop counts, not their absolute values.
The full delivery logs are in [delivery-logs.tar.gz](evidence/delivery-logs.tar.gz).

For [loop-after.txt](evidence/loop-after.txt), a fresh network was started and
the same exit-3 entry on s2 was changed to port 1. One packet with budget 4
produced 3 processing events at s1 and 2 at s2, from initial counts of zero.
Both counts stayed unchanged across the five-second observation interval.
The action logs show two tunnel forwards on each switch and then an explicit
ingress drop on s1. This is four successful forwards and a fifth arrival that
is dropped, exactly matching the selected rule. Neither receiver logged the
loop packet. The network was then stopped cleanly, and the full logs are in
[loop-after-logs.tar.gz](evidence/loop-after-logs.tar.gz).

## 5. Evaluation

Before running C5, I predicted that h2 would not receive a correctly decoded
packet. I also predicted that the loop might still stop if the packet returned
to s1, because s1 understands the new budget. The planned configuration for
both mixed tests is s1 running the new `tunnel.p4` and s2 running the preserved
`tunnel_v1.p4`; both host scripts use the new five-byte tunnel header.
These predictions were recorded before sending any mixed-version test packets.

**Mixed-version results.** [mixed.txt](evidence/mixed.txt) records three separate,
fresh-network runs. Every run used s1 new, s2 old, and new host scripts:

| Test | Prediction recorded before that test | Observation |
|---|---|---|
| Exit 2, budget 4 | No correctly decoded delivery | h2 printed `mixed`, `hops=3`, TTL 64 |
| Exit-3 loop, budget 4 | May stop on return to s1 | Eight forwards, then s1 dropped; arrival counts 5/4 stayed fixed for five seconds |
| Diagnostic: exit 2, budget 3 | Frame arrives, but protocol corruption prevents UDP decoding | h2 captured the frame with protocol `0x12`; no receiver delivery line |

The first observation contradicted my delivery prediction. s2 still reads
`proto_id` and `dst_id` correctly, so exit 2 selects h2. It extracts the next
20 bytes as IPv4 without validating its version or length. It then emits its
four-byte tunnel header, those 20 bytes and the remaining payload. This
reconstructs the new packet's layout, although s2's interpretation is wrong.
Only s1 decrements the budget, explaining the received value of 3 rather than 2.

There is also a checksum trap. Ethernet is 14 bytes, so the new tunnel's `hops`
byte is at frame offset 18 and real IPv4 begins at 19 (offsets are zero based).
Old s2 begins IPv4 at 18 instead. Its checksum field therefore occupies offsets
28–29: the real IPv4 protocol byte and the first byte of the real IPv4 checksum.
Its checksum update can corrupt those bytes even though tunnel forwarding
does not change the inner TTL.

For the initial packet, the budget arriving at s2 was 3, equal to the final
byte of destination `10.19.0.3`. s2's 20-byte view was effectively a one-byte
rotation of the real IPv4 header. The checksum calculation happened to return
`0x1166`, the bytes already at offsets 28–29. The h1 and h2 captures differ
only at offset 18 (`04` to `03`); the real IPv4 checksum remains valid.

Before the diagnostic run, the recorded prediction was that changing only the
starting budget from 4 to 3 would break this coincidence and corrupt the real
protocol byte. That is what happened: budget 2 arrived at s2 and its checksum
calculation produced `0x1266`. The h2 capture shows offset 28 changed from
`0x11` (UDP) to `0x12`, while offset 18 changed from 3 to 2. The frame arrived,
but `receive.py` did not recognise a UDP packet, and the real IPv4 checksum
was invalid. [analyze_mixed.py](analyze_mixed.py) reads both archived captures
and reproduces the checksum calculation; its output in `mixed.txt` accounts
for every captured byte. One successful packet therefore did not establish
compatibility. Full logs and captures are in the three `mixed-*-logs.tar.gz`
archives listed below.

My conditional loop prediction was supported. The packet returns to upgraded
s1 on every round trip. s1 forwards four times, consuming 4 → 3 → 2 → 1 → 0;
old s2 forwards each return without consuming the budget. The fifth arrival
at s1 is explicitly dropped. This permits eight forwards instead of the four
with both switches upgraded. The logs show the final drop, not merely stable
counts. This protects this particular cycle; it does not establish protection
for a cycle consisting entirely of old switches, or reliable mixed-version
payload handling.

**Safe rollout options (choice pending).** A new EtherType can distinguish the
new header from the old format. First deploy programs and receivers that support
both formats while senders keep using the old one. Verify all switches on the
intended paths, including alternate paths, before enabling new-format senders.
Keep old-format support until old traffic has drained. An unchanged old switch
in this lab would drop an unfamiliar EtherType, so the identifier prevents
silent misparsing but cannot by itself provide uninterrupted delivery.

A version field is another option: upgraded parsers select the layout using
that field. However, this old header has no reserved version field; simply
inserting one does not teach old switches to recognise it. It still needs a
staged transition with both formats supported and an unambiguous way to identify
them. Keeping old fields at their original offsets, as this implementation
does, preserves tunnel-exit lookup but is insufficient: C5 shows how the inner
header and checksum can still be damaged. The proposed rollout is an evaluation,
not an additional implemented protocol change.

**Data plane and control plane.** Week 3's `check_paths()` follows configured
longest-prefix routes between host pairs and reports loops or missing routes
before applying a configuration. It can explain where a planned path fails
and prevent that configuration from being installed. Its model can miss later
table changes, temporary inconsistent updates or behaviour not represented in
its input. Our C1 loop was introduced by changing a live table entry.
The hop limit bounds each packet on the actual path without needing that global
model, provided the loop crosses a switch that enforces a surviving budget.
It does not diagnose a missing route, repair a loop or distinguish a looping
packet from a legitimate path that exceeds the budget. Both are useful: check
the planned routes before installation and limit damage if actual forwarding
still goes wrong. This comparison follows the
[official Week 3 exercise](https://firdaussahran.github.io/wic2005/weeks/week-03/).

**Hardware cost.** The header gains one byte on the wire and eight logical
bits in the parsed-header representation. Parsing and deparsing handle that
extra byte; ingress needs a zero comparison, conditional drop and an 8-bit
subtraction. The existing tunnel table keeps the same key and entries, and
the design adds no per-flow state or packet-processing loop. Physical allocation
and any extra pipeline stage depend on the target compiler's packing and
dependencies. The extra byte also consumes frame-size/MTU budget. These are
resource costs, not measured hardware throughput results: BMv2 compilation
does not prove that a hardware target fits the change or preserves line rate.

## AI use

Codex read the assignment and repository, explained the C1 experiment, ran it,
recorded commands and actual outputs, preserved the logs, identified log rotation,
and drafted the C1 analysis. It proposed the C2 design, explained zero-budget
handling and unsigned wraparound, and implemented the design I accepted in
the P4 program and both host scripts. It ran local compilation, offline header
checks, C4 delivery and boundary tests, and the bounded loop test. It recorded
my C5 predictions before testing, ran the mixed-version tests, investigated the
unexpected successful delivery with a diagnostic packet and byte analysis,
and drafted the results and evaluation. It also automated milestone commits. I completed
the guided lab, restored and verified baseline tunnel delivery, and preserved
the original program on `hop-limit` before this session. During the discussion,
I identified that an exhausted budget should cause a drop and accepted the
recommended field layout, default and forwarding rule. I predicted no correctly
decoded mixed delivery and possible loop termination on return to s1. My rollout
choice and review of this draft are still pending.

<!-- Before submission, confirm any separate ChatGPT assistance, update this
     declaration for later work, and describe the decisions and interpretation
     the student contributed. Do not claim review or decisions before they occur. -->

## Evidence files

| File | What it shows |
|---|---|
| `evidence/loop-before.txt` | The loop with your finished lab program: pass counts growing |
| `evidence/loop-before-logs.tar.gz` | Original switch and receiver logs, including rotated files |
| `evidence/compile.txt` | Local compilation, Python syntax and offline header checks |
| `evidence/delivery.txt` | Tunnelled delivery with the hop limit, and a plain ping |
| `evidence/delivery-logs.tar.gz` | Full delivery and boundary-test switch and receiver logs |
| `evidence/loop-after.txt` | The same loop with your hop limit: pass counts that stop |
| `evidence/loop-after-logs.tar.gz` | Full switch and receiver logs for the bounded loop |
| `evidence/mixed.txt` | The mixed rollout: s1 new, s2 old |
| `evidence/mixed-delivery-logs.tar.gz` | Original mixed delivery logs and h1/h2 byte captures |
| `evidence/mixed-loop-after-logs.tar.gz` | Mixed loop logs showing the final drop at s1 |
| `evidence/mixed-diagnostic-logs.tar.gz` | Budget-3 diagnostic showing protocol-byte corruption |
