# Proposal: blindspot_detector 周期性盲区检测

## Why
temporal_blindspots 无法区分真正盲区和规律性模式（如周末无报道）。

## What
- 新增 `_periodic_gap_detection`：检测大间隔的规律性，低方差=周期性模式
