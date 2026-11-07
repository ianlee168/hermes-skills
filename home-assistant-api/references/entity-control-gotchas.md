# 实体与物理开关排查避坑指南

## 1. 镜前灯 / 镜子灯
- `light.mijia_group3_0048_light`（镜前灯组，灯）
- `light.lemesh_wy0c15_f38e_light`（泛光灯镜子，灯光）
- `light.lemesh_wy0d02_74d6_light`（浴室镜灯，灯）
- 关/开镜前灯时需核对这组实体。

## 2. 无独立智能灯具的区域（如厨房/玄关）
- 厨房等区域可能没有 `light.kitchen_*` 实体，而是由 Mesh 墙壁智能开关控制（如 `switch.bean_bl02_a2ea_*` 双键开关、`switch.giot_v53ksm_e4dc_*` 三键开关）。
- 若用户指示“关闭/打开厨房灯”，不要仅在 `light` 域搜索后报无设备，应排查当前处于开启状态的 `switch.*_switch_service` 并进行控制。

## 3. 智能门锁（如 Xiaomi Smart Door Lock 4 Pro）
- 门锁在 HA 中通常仅暴露只读状态传感器（`sensor.xiaomi_s1_4a37_door_state`、`sensor.xiaomi_s1_4a37_lock` 等）及电量传感器，**不提供远程下发开锁指令的执行器**。若用户发出开锁指令，应明确提示实体为只读监控。
