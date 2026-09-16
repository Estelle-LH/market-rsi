# 历史数据备份：2026-09-10

已完成并校验。这份备份只包括本次Vantage历史数据，不包括整台Linode或实时采集数据。

## S3位置

私有桶：`lh-research`，区域：`us-east-1`。

目录：`self-evolving/market-rsi/backups/20260910-linode-173-255-231-4-01/`

- 数据：`polymarket-recorder-tape-vantage-b-20260603-20260701.db.zst`
- 恢复清单：`restore-manifest.json`
- 备份计划：`backup-plan.json`

数据文件版本：`X6EnKFabjlCOUlxZGtNDxspJL4ko1rFA`。已启用版本记录、AES256加密，
四项禁止公开访问设置均开启。没有将AWS密钥放到Linode。

## 校验值

压缩文件：3,164,694,656字节。

SHA256：`9915c881cd5a598b831652664a1b761629c2c9303997332c9beef2af835d64a4`

解压文件：39,315,099,648字节。

SHA256：`a3f8a9b30126890be55919c72d114a80cd9b545d50e7c0f9140dab0737163986`

完整S3校验在2026-09-10 18:00:54 UTC通过，使用完整SHA256，不把ETag当作校验值。
恢复清单也单独核对了大小和SHA256。原始来源固定为
`oraclemangle/polymarket-canary-tape`，版本`0f09fdb48f703d672a648c562e3f6398f45eb168`。

## 恢复方式

用有权限的AWS账号下载上述数据版本和恢复清单。先核对压缩文件大小与SHA256，
再在空间足够的独立目录解压，保留下载的原文件。可使用Zstandard 1.5.5或兼容版本：

```sh
zstd -d -k --no-progress --no-pass-through -M128MB -o restored.sqlite -- archive.db.zst
```

`restored.sqlite`必须是尚不存在的新文件；不要覆盖已有数据。解压后再核对完整
字节数和SHA256。需要同时容纳压缩包、39.32GB解压文件以及系统保留空间。

Linode原件仍在`173.255.231.4:/opt/market-rsi-historical-20260910-01/`下：
`acquisition/`保存压缩包，`decode/payload.sqlite`保存解压文件，均保留为只读。

这证明备份与原文件一致，不证明行情数据已经干净、可用于验证，或模型有进步。
