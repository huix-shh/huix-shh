<div align="center">

<img width="100%" src="./assets/hero.svg" alt="huix-shh — Linux Systems, Virtualization, Cloud Native, and Vibe Coding" />

<samp>Linux systems · Virtualization · Cloud Native · Vibe Coding</samp>

### [Explore the interactive system map →](https://huix-shh.github.io/huix-shh/)

</div>

## What I work on

~~~text
┌──────────────────────────────────────────────┐   ┌──────────────────────┐
│ L3  CLOUD NATIVE                            │   │ VIBE CODING          │
│     Kubernetes · container runtimes · edge  │   │ Build                │
├──────────────────────────────────────────────┤   │   ↓                  │
│ L2  VIRTUALIZATION                          │   │ Human Review         │
│     KVM · QEMU · libvirt · Firecracker      │   │   ↓                  │
├──────────────────────────────────────────────┤   │ Verify               │
│ L1  LINUX SYSTEMS                           │   │ tests · logs · proof │
│     C · Python · Go · Bash · automation     │   └──────────────────────┘
└──────────────────────────────────────────────┘
~~~

I work across the system stack: Linux internals and automation, virtual-machine infrastructure, and cloud-native runtime integration. AI coding tools are part of the workflow, but generated changes still pass through human review and executable verification.

## Selected experience

| Company | Selected work |
| --- | --- |
| **Hygon** | Contributed to a repeatable VM test-environment flow around image preparation, cloud-init, libvirt, boot checks, and Ansible; also handled customer issue diagnosis.<br><sub>Additional validation: comparable CubeSandbox runs and passthrough-network tuning; one single-port, one-way test result reached 130+ Gbps.</sub> |
| **Iluvatar CoreX** | Developed GPU Device Plugin and Container Toolkit components; built a Dify/RAG workflow for compiler-log retrieval and assisted diagnosis. |
| **Intel** | Contributed to ACRN validation, code quality, and upstream changes; implemented infrastructure-provider integrations and Kubernetes-managed edge simulations. |
| **Baidu** | Maintained a libvirt/QEMU platform, diagnosed hot-migration failures, and improved VF permission controls for virtualized SSD I/O paths. |
| **Shannon Systems** | Implemented SSD FTL address translation and metadata handling; participated in distributed-storage feasibility validation involving ZooKeeper, consistent hashing, and RDMA. |

## Vibe Coding, with a gate

~~~text
Claude Code / Codex / Kimi
            ↓
Human review: code review
            ↓
Verification: automated tests · logs · benchmarks
~~~

I use Claude Code, Codex, and Kimi as coding tools. Generated changes go through human review and verification with automated tests, logs, and benchmarks.

## Public work

### ACRN Hypervisor · 8 merged pull requests

Public upstream changes focused on code quality and maintainability:

- [#3342 — Clean up vCPU code for static analysis](https://github.com/projectacrn/acrn-hypervisor/pull/3342)
- [#3373 — Remove dead instruction-emulation code](https://github.com/projectacrn/acrn-hypervisor/pull/3373)
- [#3580 — Fix type-conversion and return-value coding-guideline violations](https://github.com/projectacrn/acrn-hypervisor/pull/3580)

New public contributions will be added here only after the corresponding PR or commit is inspectable.

## Toolbox

code: C · Python · Go · Bash

systems: Linux · KVM · QEMU · libvirt · Firecracker · cloud-init · systemd

cloud_native: Kubernetes · containerd · runc · Ansible

## Connect

[![Email](https://img.shields.io/badge/Email-sfz200809242719%40gmail.com-10251f?style=flat-square&logo=gmail&logoColor=79f2c0)](mailto:sfz200809242719@gmail.com)
[![GitHub](https://img.shields.io/badge/GitHub-huix--shh-10251f?style=flat-square&logo=github&logoColor=79f2c0)](https://github.com/huix-shh)
