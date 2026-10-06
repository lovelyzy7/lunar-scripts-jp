# JP RVA 记录（mod menu 素材，仅记录不制作）

> 由 `tools/gen_rva_records.py` 自动生成：EN dump ↔ JP dump 方法名对照。
> EN = NieR Re[in]carnation 3.7.1（west），JP = 同版本日服构建。
> JP dump: `jp/dump-jp-3.7.1/out/dump.cs`（Il2CppDumper）。

> 运行时地址 = `libil2cpp.so` 基址 + RVA（本 dump 中 RVA = Offset = VA = 文件偏移）。

| # | 类 | 方法 | EN RVA | JP RVA | 备注 |
|---|---|---|---|---|---|
| 1 | ComputerTurnBattleSkillBehaviourAttackPower | OnCompute | 0x33675AC | 0x32D4540 | |
| 2 | FieldComputerSkillBehaviourAttack | FieldTurnBattleComputerSkillBehaviourAttackDamage | 0x3B0C980 | 0x3A79518 | |
| 3 | CalculatorActorStatusDefault | CalculateDamageValue | 0x3247968 | 0x32BD36C | |
| 4 | CalculatorActorStatusDefault | ApplyDamage | 0x32478E4 | 0x32BD2E8 | |
| 5 | FieldSkill | FieldTurnBattleSkillDynamicCurrentCooltime | 0x3B11F10 | 0x3A7EAA8 | |
| 6 | FieldSkill | FieldTurnBattleSkillDynamicMaxCooltime | 0x3B11D5C | 0x3A7E988 | |
| 7 | CalculatorSkill | TryGetCompanionSkillCooltime | 0x2C8CFAC | 0x2CE5130 | |
| 8 | CalculatorSkill | HasUsableCompanionSkill | 0x2C8D350 | 0x2CE54D4 | |
| 9 | CalculatorSkill | HasUsableCompanionSkillMine | 0x2C8D2C8 | 0x2CE544C | |
| 10 | FieldSkill | FieldTurnBattleSkillSkillState | 0x3B122FC | 0x3A7EF28 | |
| 11 | FieldSkill | FieldTurnBattleSkillSkillState | 0x3B12390 | 0x3A7EF28 | |
| 12 | CalculatorTurnBattleCombo | AddComboCount | 0x2C880F4 | 0x2CE0278 | |
| 13 | CalculatorTurnBattleCombo | ResetComboCount | 0x2C8818C | 0x2CE0310 | |
| 14 | CalculatorTurnBattleCombo | GetCurrentComboCount | 0x2C881F8 | 0x2CE037C | |
| 15 | CalculatorTurnBattleCombo | CalculateComboDamageCoefficient | 0x2C880BC | 0x2CE0240 | |
| 16 | FieldTeam | FieldTurnBattleTeamComboCount | 0x3B166CC | 0x3A832F8 | |
| 17 | FieldTeam | FieldTurnBattleTeamComboCount | 0x3B16760 | 0x3A832F8 | |
| 18 | BattleComboView | PlayComboAnimation | 0x3149B94 | 0x31AE6FC | |
| 19 | BattleComboView | PlayBaseIdleCombo | 0x314A764 | 0x31AF2CC | |
| 20 | BattleDamageView | SetStandard | 0x314E6E0 | 0x31B3248 | |
| 21 | BattleDamageView | SetWeak | 0x314E804 | 0x31B336C | |
| 22 | BattleDamageView | SetResist | 0x314E928 | 0x31B3490 | |
| 23 | BattleDamageView | SetRecovery | 0x314EA4C | 0x31B35B4 | |
| 24 | BattleDamageView | SetAbnormal | 0x314EC5C | 0x31B37C4 | |
| 25 | BattleDamageView | SetHpRatioDamage | 0x314EB68 | 0x31B36D0 | |
| 26 | DamageLabelBase | SetEffectDamageText | 0x2F85BE4 | 0x2EA3964 | |
| 27 | FieldActor | FieldTurnBattleActorJoinParty | 0x3E6E3CC | 0x3DAB36C | |
| 28 | FieldComputerSkillBehaviourAttack | FieldTurnBattleComputerSkillBehaviourAttackTargetParameterActor | 0x3B0CD6C | 0x3A79998 | |
| 29 | FieldActor | FieldTurnBattleActorDynamicCurrentHp | 0x3E761B8 | 0x3DB302C | |
| 30 | FieldSkill | FieldTurnBattleSkillFromActor | 0x3B119BC | 0x3A7E5E8 | |
| 31 | FieldTeam | FieldTurnBattleTeamOwnTeamId | 0x3B162A0 | 0x3A82ECC | |
| 32 | FieldActor | FieldTurnBattleActorDynamicHp | 0x3E75C74 | 0x3DB2C14 | |
| 33 | FieldActor | FieldTurnBattleActorDynamicHp | 0x3E75DA0 | 0x3DB2C14 | |
| 34 | FieldActor | FieldTurnBattleActorDynamicCurrentHp | 0x3E7608C | 0x3DB302C | |
| 35 | FieldActor | FieldTurnBattleActorDynamicVitality | 0x3E768BC | 0x3DB385C | |
| 36 | FieldActor | FieldTurnBattleActorDynamicVitality | 0x3E769E8 | 0x3DB385C | |
| 37 | FieldActor | FieldTurnBattleActorParameterParty | 0x3E6EE90 | 0x3DABE30 | |
| 38 | FieldActor | FieldTurnBattleActorParameterParty | 0x3E6EF64 | 0x3DABE30 | |
| 39 | FieldComputerSkillBehaviourAttack | FieldTurnBattleComputerSkillBehaviourAttackOwnParameterActor | 0x3B0CECC | 0x3A79AF8 | |
| 40 | FieldSkill | FieldTurnBattleSkillSkillHash | 0x3B1175C | 0x3A7E388 | |
| 41 | FieldComputerSkillBehaviourAttack | FieldTurnBattleComputerSkillBehaviourAttackDamage | 0x3B0C8EC | 0x3A79518 | |
| 42 | CalculatorActorStatusBigHunt | CalculateDamageValue | 0x32474BC | 0x32BCEC0 | |
| 43 | CalculatorActorStatusBigHunt | ApplyDamage | 0x3247374 | 0x32BCD78 | |
| 44 | CalculatorActorStatusDefault | ctor | 0x3247CAC | 0x32BD6B0 | |
| 45 | CalculatorActorStatusBigHunt | ctor | 0x32478DC | 0x32BD2E0 | |
| 46 | ContainerTurnBattle | SetCalculatorActorStatus | 0x36F2D28 | 0x2B1A7AC | |
| 47 | SkillComponentCooltimeDispatcher | AddCalculateSkill | 0x32C5E94 | 0x3267848 | |
| 48 | SkillComponentCooltimeDispatcher | RemoveCalculateSkill | 0x32C6BD4 | 0x3268588 | |
| 49 | SkillComponentCooltimeDispatcher | UpdateSkillState | 0x32C5FC8 | 0x326797C | |
| 50 | SkillComponentCooltimeDispatcher | OnFrameUpdate | 0x32C6880 | 0x3268234 | |
| 51 | SkillComponentCooltimeDispatcher | OnTurnbaseUpdate | 0x32C6870 | 0x3268224 | |
| 52 | SkillComponentCooltimeDispatcher | CheckCoolTime | 0x32C6A54 | 0x3268408 | |
| 53 | SkillComponentCooltimeDispatcher | OnExecuteActiveSkill | 0x32C70A8 | 0x3268A5C | |
| 54 | SkillComponentCooltimeDispatcher | OnExecuteDefaultSkill | 0x32C7348 | 0x3268CFC | |
| 55 | SkillComponentCooltimeDispatcher | OnExecuteCompanionSkill | 0x32C6E64 | 0x3268818 | |
| 56 | SkillComponentCooltimeDispatcher | OnSkillHit | 0x32C7604 | 0x3268FB8 | |
| 57 | SkillComponentCooltimeDispatcher | DispatchSkillCoolTimeFull | 0x32C6B40 | 0x32684F4 | |
| 58 | SkillComponentCooltimeDispatcher | PauseCooltimeCount | 0x32C6668 | 0x326801C | |
| 59 | SkillComponentCooltimeDispatcher | ResumeCooltimeCount | 0x32C6674 | 0x3268028 | |
| 60 | FieldSkill | FieldTurnBattleSkillStaticMaxCooltime | 0x3B11C3C | 0x3A7E868 | |
| 61 | FieldSkill | FieldTurnBattleSkillDynamicMaxCooltime | 0x3B11DF0 | 0x3A7E988 | |
| 62 | CalculatorActorStatusBase | CalculateAdvanceActiveSkillCooltime | 0x3244144 | 0x32B9B48 | |
| 63 | CalculatorActorStatusBase | CalculateShortenActiveSkillCooltime | 0x3244C7C | 0x32BA680 | |
| 64 | CalculatorActorStatusBase | CalculateAttack | 0x32414E8 | 0x32B6EEC | |
| 65 | CalculatorActorStatusBase | SequenceCalculateDamageValue | 0x3241BD4 | 0x32B75D8 | |
| 66 | CalculatorActorStatusBase | CalculateDamageMultiply | 0x3245190 | 0x32BAB94 | |
| 67 | CalculatorActorStatusBase | CalculateHpRatioDamage | 0x324234C | 0x32B7D50 | |
| 68 | FieldTeam | FieldTurnBattleTeamComboDamageRatio | 0x3B168F4 | 0x3A83494 | |
| 69 | FieldTeam | FieldTurnBattleTeamComboDamageRatio | 0x3B16868 | 0x3A83494 | |
| 70 | CalculatorSkill | GetCompanionSkillSkillState | 0x2C8D48C | 0x2CE5610 | |
| 71 | CalculatorSkill | GetAllCompanionSkillList | 0x2C8D7A4 | 0x2CE5928 | |

## 本工具已应用的补丁点（JP）

| 补丁 | JP RVA | EN 对照 RVA | 写入字节 | 说明 |
|---|---|---|---|---|
| ToNativeCredentials (SSL bypass) | 0x3622514 | - | `mov x0,#0; ret` | 同 EN 脚本 0x35C8670 |
| HandleNet.Encrypt (passthrough) | 0x274AC64 | - | `mov x0,x1; ret` |  |
| HandleNet.Decrypt (passthrough) | 0x274AD64 | - | `mov x0,x1; ret` |  |
| OctoManager.Internal.GetListAes | 0x4B55B5C | - | `mov x0,#0; ret` | 明文 list.bin |
| Purchaser.IsExistProduct | 0x2834E9C | 0x282CE78 | `mov w0,#1; ret` | 免内购 |
| <Initialize>d__16.MoveNext (skip _initialized) | 0x2838858 | 0x2830834 | `nop` | 免内购 |
| <PurchaseRealProductAsync>d__28.MoveNext (IsInitialized cbz) | 0x2839CCC | 0x2831CA8 | `nop` | 免内购 |
| <PurchaseRealProductAsync>d__28.MoveNext (skip alert) | 0x2839CD0 | 0x2831CAC | `b +0x64` | 免内购 |
| <BuyProduct>d__24.MoveNext (null storeController) | 0x283C04C | 0x2834028 | `cbz x21` | 免内购 |
| TitleScreen.InitializeMenuButton | 0x304F32C | 0x2F11900 | `ret` | EOS 菜单 |
| com.adjust.sdk.Adjust.start | 0x3F4A250 | - | `ret` | 屏蔽 Adjust |
| com.adjust.sdk.AdjustAndroid.Start | 0x3F4A574 | - | `ret` | 屏蔽 Adjust |

## 说明 / 注意事项

- JP 与 EN 的 libil2cpp.so **构建不同**（EN `0f9ffec9…` / JP `262bbfb1…`，体积差约 1.1MB），
  EN 的 RVA **不能**直接用于 JP；端口覆盖类补丁（`NetworkConfig.get_ServerPort` 等）在 JP 上无效，
  JP 的 API 端口来自 `assets/bin/Data/deace60a64f3d4398a2db0f3d1a41195`（network_config 资源）。
- 换游戏版本后必须重新用 Il2CppDumper 生成 dump 并更新本表。
- EN RVA 来源：`NieR-Re-In-Carnation-Mod_Menu/docs/MOD制作记录.md` 与本工具补丁表。

_本文档只记录数据，不包含任何作弊/菜单实现。_
