# GPU Codex Skills

This directory stores the repository-managed copies of the Codex skills used
for GPU passthrough and shared virtualization testing in
`/home/mzh/RK3588/gpu`.

Runtime Codex skill files still live under:

```text
/home/mzh/.codex/skills/gpu-passthrough-autotest/SKILL.md
/home/mzh/.codex/skills/gpu-shared-virtualization-autotest/SKILL.md
```

When a skill changes, update both the runtime file and the matching copy here:

```text
docs/skills/gpu-passthrough-autotest/SKILL.md
docs/skills/gpu-shared-virtualization-autotest/SKILL.md
```

Each skill also keeps `agents/openai.yaml` beside `SKILL.md` so the runtime
skill chip/default prompt can be versioned with the workflow. The docs copies
make the GPU workspace self-documenting and keep the testing workflow guidance
versioned with the scripts and artifact layout.
