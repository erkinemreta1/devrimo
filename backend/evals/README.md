# Scholar evaluation harness

The suite uses synthetic SAIS, ODTÜClass, and webmail fixtures. Never substitute
production student sessions or tool outputs into these cases.

Run all cases with `python -m evals`, or select `--tag smoke`, `--tag campus`,
or `--tag safety`. Results are written to the shared Agno database and appear
in AgentOS.

Before a Scholar rollout, require:

- all safety and cross-user isolation tests passing;
- 100% confirmation coverage for external writes;
- at least 95% correct tool routing on the versioned campus set;
- zero forbidden memory writes and zero unredacted production traces;
- at least 30% input-token reduction in the 20-turn context benchmark;
- no more than 15% p95 latency regression for simple read-only questions.

Run cases multiple times after a model change. Judge scores are nondeterministic
and must be calibrated against human-reviewed examples before becoming a hard
deployment gate.
