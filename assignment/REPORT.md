# Week 5 assignment — Put a limit on the tunnel

Student ID (last 4 digits only): **5019**

Draft in progress: C1 measured; design decisions and later experiments are pending.
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

<!-- Your header change and your pipeline change, and the reason for each choice:
     - the field's size, and where in the header you put it (and why there);
     - the starting value send.py uses, and how you chose it;
     - where it's decremented, and what happens when it runs out;
     - what else had to change for every part of the path to agree (parser, deparser, hosts). -->

## 3. Implementation

<!-- Summarise what you changed in tunnel.p4, send.py and receive.py. The pull request shows
     the code itself: here, explain anything a reviewer might not see from the diff alone. -->

## 4. Evidence: it works

<!-- Show, with your evidence files:
     - tunnelled delivery to h2 and h3, and the hop limit the receivers saw (delivery.txt);
     - plain IPv4 still works (delivery.txt);
     - the same loop as in section 1 now ends, and after how many passes — does that match
       your design? (loop-after.txt) -->

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
and drafted the C1 analysis. It also automated the evidence commit. I completed
the guided lab, restored and verified baseline tunnel delivery, and preserved
the original program on `hop-limit` before this session. Design choices and
my review of this draft are still pending.

<!-- Before submission, confirm any separate ChatGPT assistance, update this
     declaration for later work, and describe the decisions and interpretation
     the student contributed. Do not claim review or decisions before they occur. -->

## Evidence files

| File | What it shows |
|---|---|
| `evidence/loop-before.txt` | The loop with your finished lab program: pass counts growing |
| `evidence/delivery.txt` | Tunnelled delivery with the hop limit, and a plain ping |
| `evidence/loop-after.txt` | The same loop with your hop limit: pass counts that stop |
| `evidence/mixed.txt` | The mixed rollout: s1 new, s2 old |
