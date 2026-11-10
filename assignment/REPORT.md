# Week 5 assignment — Put a limit on the tunnel

Student ID (last 4 digits only): **5019**

Draft in progress: C1–C4 complete; C5 evaluation and final review are pending.
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
after the original four-byte tunnel header. The mixed rollout will test this.

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

<!-- a) The mixed rollout (mixed.txt): what did you predict before running s1 with your new
        program and s2 with tunnel_v1.p4? What actually happened to delivery, and to the loop?
        Explain every difference from your prediction, byte by byte if you need to.
     b) Propose a safe way to roll out a header change across a network of switches that can't
        all be upgraded at once. Compare at least two options (for example a version field, a
        new EtherType, or ordering fields so old switches still parse them).
     c) Loop protection in the data plane (this hop limit) versus the control plane (Week 3's
        check_paths()): what can each catch that the other can't? Why do real networks use both?
     d) What would this change cost on a hardware switch running at line rate? -->

## AI use

Codex read the assignment and repository, explained the C1 experiment, ran it,
recorded commands and actual outputs, preserved the logs, identified log rotation,
and drafted the C1 analysis. It proposed the C2 design, explained zero-budget
handling and unsigned wraparound, and implemented the design I accepted in
the P4 program and both host scripts. It ran local compilation, offline header
checks, C4 delivery and boundary tests, and the bounded loop test, then drafted
the results from their outputs. It also automated milestone commits. I completed
the guided lab, restored and verified baseline tunnel delivery, and preserved
the original program on `hop-limit` before this session. During the discussion,
I identified that an exhausted budget should cause a drop and accepted the
recommended field layout, default and forwarding rule. My review of this draft
and the remaining experiments are still pending.

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
