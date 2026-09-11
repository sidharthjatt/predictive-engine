# RETIRED UNIVERSES -- the 58 and the 74

**Deleted 2026-09-11.** This file is the terminal record. Nothing in this
repository can regenerate what it describes: the universes' raw data, their
code and their registry entries are gone, and their artefacts were never
tracked in git. Every number below is transcribed from
`forensic_snapshot_20260911T0100/`, which is held in two copies on external
media and whose SHA-256 manifest is reproduced in full at the end.

If you are reading this because a document cites a 58 or 74 figure: the figure
is here, and it is the last one those universes ever produced.

---

## 1. What they were, and why each existed

### The 58

**A 58-name directory-defined basket -- 47 Nifty 100 constituents, 8 MidCap150
constituents and 3 in neither -- assembled as a development set, not as an
index.**

That sentence is the honest one and it is deliberately not the flattering one.
The 58 was described for most of this project's life as the large-cap proving
ground. It was not. Checking its symbol list (recovered from
`results/metrics/per_stock_returns.csv` in the snapshot, 58 rows) against this
repository's own index file sets:

```
58 symbols                       58
  in data/raw/nifty100_benchmark 47
  in data/raw/MidCap150/clean     8   HEROMOTOCO, INDUSINDBK, ITCHOTELS, LICI,
                                      LTF, LTTS, M&MFIN, NTPCGREEN
  in neither                      3   BELRISE, LTFOODS, LTIM
```

**THE 58 AND mid OVERLAPPED BY 8 SYMBOLS, so the 58 was never an independent
large-cap comparison against mid.** Wherever a document reads a 58-vs-mid
result as a cross-universe check, that reading is weaker than it looks: 14% of
the 58 is inside mid. This was not known when those comparisons were made.

It had no authoritative symbol list -- `symbols()` returned None for it, and
the directory was the definition. `config.SYMBOLS` holds five names, is
vestigial, and was never the 58.

### The 74

**The `Development_data_files` vendor set: 74 symbols, 2016-01-01 to
2025-12-23, a shorter and denser history than the 58's.** 72 of its 74 are
Nifty 100 constituents. Its two apparent singletons were spelling variants,
not distinct names: `MM.csv` is the Nifty 100's `M&M.csv` (2,475 overlapping
sessions, 93.6% of closes identical to 1e-6, median relative difference
0.000000) and `BAJAJAUTO.csv` is `BAJAJ-AUTO.csv` (2,476 sessions, 96.5%).
Deleting it lost no symbol history.

### Why they were retired

Not because they were wrong. Because every axis of this pipeline -- universe,
arm, cadence, profile -- had to become a thing the registry defines and the
selection drives, and two frozen universes whose numbers must not move are two
permanent exceptions to that. They pinned a defective `purge_mode="calendar"`,
a superseded `value_at_open=False`, a year-cut window, a single cadence and a
two-arm subset, each of which had to be special-cased somewhere.

They also held the older `FINAL_*` / `v2FINAL_*` naming scheme. Retiring them
removed the older of the two schemes entirely.

---

## 2. The headline figures, at full precision

Transcribed verbatim from the snapshot CSVs. These are the last numbers these
universes produced and they cannot be recomputed.

### 58 -- `results/metrics/v2FINAL_comparison.csv`

| Config | CAGR% | Sharpe | Sortino | MaxDD% | Calmar | Trades | TC_Rs |
|---|---|---|---|---|---|---|---|
| + breadth scaling (v2 FINAL) | 17.01 | 1.39 | 1.85 | -14.34 | 1.19 | 929 | 166386.0 |
| Inverse-vol, 100% invested (v1 final) | 24.62 | 1.27 | 1.59 | -33.79 | 0.73 | 738 | 324482.0 |
| Equal-weight buy & hold (58) | 18.02 | 1.03 | 1.18 | -39.8 | 0.45 | 0 | 0.0 |

### 58 -- `results/metrics/FINAL_comparison.csv` (validation engine)

| Config | CAGR% | Sharpe | Sortino | MaxDD% | Calmar | Trades | TC_Rs |
|---|---|---|---|---|---|---|---|
| Equal-rupee (validation engine) | 26.18 | 1.23 | 1.55 | -36.05 | 0.73 | 706 | 339631.0 |
| Inverse-vol (validation engine, cash-based sizing) | 26.42 | 1.3 | 1.64 | -34.46 | 0.77 | 706 | 356515.0 |
| Equal-weight buy & hold (58) | 18.02 | 1.03 | 1.18 | -39.8 | 0.45 | 0 | 0.0 |

### 74 -- `results74/metrics/v2FINAL_comparison.csv`

| Config | CAGR% | Sharpe | Sortino | MaxDD% | Calmar | Trades | TC_Rs |
|---|---|---|---|---|---|---|---|
| + breadth scaling (v2 FINAL) | 16.25 | 1.43 | 1.93 | -17.85 | 0.91 | 883 | 126688.0 |
| Inverse-vol, 100% invested (v1 final) | 20.76 | 1.17 | 1.49 | -35.41 | 0.59 | 708 | 186781.0 |
| Equal-weight buy & hold (74) | 23.78 | 1.28 | 1.45 | -38.3 | 0.62 | 0 | 0.0 |

### The four figures every document cites

```
58 v2   CAGR 17.01   Sharpe 1.39   MaxDD -14.34   929 trades   TC Rs 166,386
58 v1   CAGR 24.62   Sharpe 1.27   MaxDD -33.79   738 trades   TC Rs 324,482
74 v2   CAGR 16.25   Sharpe 1.43   MaxDD -17.85   883 trades   TC Rs 126,688
74 v1   CAGR 20.76   Sharpe 1.17   MaxDD -35.41   708 trades   TC Rs 186,781
```

Both universes ran TOP_N=8, BUFFER=16, rebalance 20, 10-seed LightGBM on 17
features with a 32-day purge. Average exposure 56% (58) and 57% (74).

**These two are the only universes in this project whose published figures are
independently anchored in tracked prose.** `EXPERIMENTS.md:1456-57` records
17.01 / 1.39 / -14.34 / 929 and 16.25 / 1.43 / -17.85 / 883, and both match the
snapshot exactly. mid and n100 have no such anchor: the figures in prose for
them predate the adj_close and interior-gap corrections and have moved. That
is the reverse of what you would want, and it is why this file exists.

### Two constants that survive nowhere else

`results/test_v1_v2_blend.py` was deleted with these universes. Its blend
slider finding is recorded at `EXPERIMENTS.md:3920`, but its two mean-invested
constants are not recorded anywhere else:

```
58 v2 mean invested   0.646
74 v2 mean invested   0.645
```

---

## 3. Artefact inventory

**171 files, 35.5 MB, all untracked, all gitignored** (`.gitignore:36-39`
excludes `results/metrics/` and `results74/metrics/`). They exist in exactly
one place: `forensic_snapshot_20260911T0100/`, held in two copies on external
media (`/Volumes/T7/mac/...` and `/Volumes/T7/HFT/...`), verified byte-identical
to the working copy by SHA-256 on 2026-09-11.

```
58  157 files  28.8 MB   41 top-level (32 CSV/JSON/TXT + 9 PNG)
                        116 in per_stock_charts/ and combined_charts/
74   14 files   6.7 MB   13 CSV/JSON/TXT + 1 PNG
```

The earlier survey said "43 + 14". That counted only top-level files and was
wrong on both halves; the real figure is 157 + 14, and the difference is 116
per-stock charts.

**What the snapshot does NOT contain:** `*_cache.csv` (the score and raw
panels, ~540 MB) and `SEEDNOISE_*.npy`, excluded when it was taken. Those were
derived from `data/raw/nifty50` and `data/raw/Development_data_files`, which
are now deleted, so they can never be rebuilt either. Nothing in the tables
above depends on them.

### SHA-256 manifest

Paths are relative to `forensic_snapshot_20260911T0100/`. Verify with:

```bash
cd /Volumes/T7/mac/algo_trading_project/forensic_snapshot_20260911T0100
shasum -a 256 -c <(grep -oE '^[0-9a-f]{64}  \S+' RETIRED_UNIVERSES-manifest.txt)
```

```
6bdb5d5404e47b537055555275ad3fd8d685fb8d41cff9a522dd8af962bfe295  results/metrics/DAILY_LOG_58.txt
80846b48b6c744ef2c4961247f471c72eb524d016b83732d7f744e5cc4ddf695  results/metrics/FINAL_SUMMARY_TABLE.csv
ef1631da7b6e21fc6bbce9a73cdfc1eb0b59abf5af1faaa2abe394fabb9b786c  results/metrics/FINAL_comparison.csv
a705720bb6141d26bb4b81f185e4a5a32a5ff8cfee983aa841b12d8a3271cb7e  results/metrics/FINAL_equity.csv
d81210ee0b6d40cd26d9b603761e08b7865d6fe263de4c961015131b6e5b9f88  results/metrics/FINAL_params.json
85e86755998e7bfb2e2932f0180dafd51ba980c832228c963b713a650d58ddef  results/metrics/FINAL_trades.csv
0f91a5d04828061ead1ad2d15d16cc7e842e4b381532155054d70f60c74bd050  results/metrics/FINAL_val_periods.csv
ffefa94f592a95d070eb7ff884b9af6397578d5e0e0d860bb3a7b9df3e09ab44  results/metrics/FINAL_val_seeds.csv
39ced145b790dfab8b4c0d90ddf8de09ec5f546802da33c1d08a0acfd015c814  results/metrics/FINAL_val_volwin.csv
ed4f74c3ab5fdc0ef1c321b1854fae1f432852b7becebe21152ec59ba7b919f7  results/metrics/FINAL_yearly.csv
0dc69d0dddb8a669be0953937fa8ff3659c1967fdc88f72141b756b01c0fb0a7  results/metrics/breadth_val_periods.csv
68d38078b58d11d8b3dab926f0346233a5a7e2951949f05a0af36df1c039000e  results/metrics/breadth_val_seeds.csv
54f888bfdf783330085ea59e2fb1e44f063e969a77f44dae5461fa4564d9fe99  results/metrics/cash_series_58.csv
7349d98a2b45fb7add58829377e9ba9f27fa6a072a1ed83965e7296eac4b7b05  results/metrics/chart_FINAL.png
510e02f225758e404fb51b920d145da0056b90c950df79cb5ccfc47f7cc30ba3  results/metrics/chart_FINAL_58_74_N100.png
67cf50ee5e9eb5643971f10397ec99e1e8c3e328e13d965a94e6fca3109a2690  results/metrics/chart_FINAL_58_74_N100_matched.png
afbebf8345531a270c50af38b57883ea621d9b735c3056bccb992dd09014a7a3  results/metrics/chart_FINAL_table.png
3fac7a286e90e079f30c52c6f95e8412ffd9ad223cf2208dacb63b3307bee2cf  results/metrics/chart_all_stocks.png
fdb8a7837aabc5eb8529ecdf4714c5cd78d5c824464041f04785b79a023d6959  results/metrics/chart_decay.png
282fd13c3f2e842865aed40ad286d9aa42f270e2815afa89f8cad54194a3bacc  results/metrics/chart_equity.png
1779901e7d25ca90b211cb73b7f75359034c1c8d025f99963d1d066a4747ec3c  results/metrics/chart_v2FINAL.png
8a4221298cd455fde902d7f71e27d5467de821120da83f566a975e837101c664  results/metrics/combined_PORTFOLIO.png
fafb8aa79fa14fa9b9af5824e8476268de640465dbf724673289a67840a39baf  results/metrics/combined_charts/ADANIENT.png
f96dae17dc709304d0bfae29ef4a459bc1386c29587aaff9f3621223395a0c27  results/metrics/combined_charts/ADANIPORTS.png
606b0ebdf216272bf65e9c2488a07c9f0181e3cc18b77759578f06ec66bec20b  results/metrics/combined_charts/APOLLOHOSP.png
4c09df59a9ffb5b7b20272033926ba60600ea08b4a09f89d7072b7fdf803b0c2  results/metrics/combined_charts/ASIANPAINT.png
0bddfd73a9cba82f2e6c23b5dd2ca05cdc4a8dafab8293f81b795a5d8b35d02c  results/metrics/combined_charts/AXISBANK.png
b2637c07b9168282eeb04c41fd4d486218c09c9ca71b32f447873560fa1f2e92  results/metrics/combined_charts/BAJAJ-AUTO.png
8db0438047dbea424306bdc91a5642c10d22d9ffa009e2dfbf3f256c2d867119  results/metrics/combined_charts/BAJAJFINSV.png
f69948df18031558ad35ad1877852a599ae40bee6dc2b7c35f35c40207b776bf  results/metrics/combined_charts/BAJFINANCE.png
69a0c8eb32c6cc78f9417a6e5c1cf61414e3cb031c857d3fce1ff8969baf0571  results/metrics/combined_charts/BEL.png
020bfbd247a1c85e91f279c9ca327bf8f672125cbbafbd56ccb885e568d2c759  results/metrics/combined_charts/BELRISE.png
4bbff8200b085d9c1cff0577282ce464a64017e2f2779e0d3dc464c00b8d9baf  results/metrics/combined_charts/BHARTIARTL.png
2bae3a436fdde333aa252de46ff9c3db20cc05307156ee83476cf8a32db6d991  results/metrics/combined_charts/BPCL.png
f233c6932284724f5c5136baa9c783125efd59ce9ebad3cb7b3b5d1ae8b8e5d1  results/metrics/combined_charts/BRITANNIA.png
da532ff2e2de07e13385856d90569b92621f7f930688f68f367cfa5d2ca21ee8  results/metrics/combined_charts/CIPLA.png
9d02431c347d31ae7aded4766d1bb5083e49bb4f70ea26fad16de22d8ec8af5e  results/metrics/combined_charts/COALINDIA.png
3f5f9c2d7e715ed223ef5822ea0b6de6c10c9f8f06fd5a5aacbf73fd95da6fac  results/metrics/combined_charts/DRREDDY.png
f79b1d7315bd3bdeff8d169c76a2a2aeea3d735d18d38b2d93c70cc24a894832  results/metrics/combined_charts/EICHERMOT.png
fa7827305cb59560f42cf04519e4b0d5315275d68ccb0415ad5f404558a85617  results/metrics/combined_charts/ETERNAL.png
0db7789c97cd2f98264a1d9d883812b358a0a71d9acac58bb9183ffbcd1a2f72  results/metrics/combined_charts/GRASIM.png
100686e20b8999c3178d6ad64c4deb5e27403d9f8b20d0c15efa9834236bc81c  results/metrics/combined_charts/HCLTECH.png
de72036e700c212e8ec8c3c92dec746d2522ec6d2091d61573a584559aba2357  results/metrics/combined_charts/HDFCBANK.png
aa8367e29673a8b82d7fa7d75438b856942dec7f103229592c330d4ad154c8e1  results/metrics/combined_charts/HDFCLIFE.png
418f2f56f24afe1eb3048cfad0a155c5325431a7d3dc0cf01a283746f65dd6c0  results/metrics/combined_charts/HEROMOTOCO.png
3953b5dc5255427c44be4334e2f53ba8e57a93e81cb26af5c492668f8ddb2973  results/metrics/combined_charts/HINDALCO.png
b8343a4a7e90638d5555600a3d4ae1c0dae443f07524c6743bf10e28b76a05aa  results/metrics/combined_charts/HINDUNILVR.png
9dc41851b0c8138dd51aa8ee2f61101422c772af70a0cb5061a4d55c5a273491  results/metrics/combined_charts/ICICIBANK.png
273f4bd7d25e4a86361712cbd581b109ed5da8eeb00aa185232fb325205b4db8  results/metrics/combined_charts/INDUSINDBK.png
e9cc488f76da46e6eb45bb3246ecc5994a8704565a9bad3441ace14bdb55e468  results/metrics/combined_charts/INFY.png
81530efc9462fa4b5dd0071260ad8852a3e3dcb471dae8b6ef9f9fc80bae82d5  results/metrics/combined_charts/ITC.png
d44ac4361ba6fe0075579a6a76554653f52c9340fb84bda3b7812ea40190e74c  results/metrics/combined_charts/ITCHOTELS.png
f885131d4749fd5a3406ff91b12d1abbc37fe74f3175bdfb938d2478befa3bcd  results/metrics/combined_charts/JSWSTEEL.png
b27f201f89ce88e88fecdf9548ab9b63d0c0eeabe688cae425ea98cd098c2107  results/metrics/combined_charts/KOTAKBANK.png
27382832e2743f0772f8eac2929ebb87d46f96872ad89fd396fcd8f0b9ec5899  results/metrics/combined_charts/LICI.png
a5ad72c97406448dd7d6bfa0998e4f487a37a0eb364861e9558d5b9784bbdbfb  results/metrics/combined_charts/LT.png
f157dbebe79a9ff573d59d225811b5b69db315be71fe59bed16a893e3a352207  results/metrics/combined_charts/LTF.png
dfa7c8c11ea831137149e3a0f2a68d5331e00b10c84f53ad520470148959b2bf  results/metrics/combined_charts/LTFOODS.png
228ddc41397dcc44b867ddb0bace515dc442f73d902f55a7d1b5e03cf8aa6829  results/metrics/combined_charts/LTIM.png
8e836d5541af2cfdc38c7b81d182425d86a6db48897778881846898ab24132e7  results/metrics/combined_charts/LTTS.png
1031a04dafbb9fab1857ef6068320c48cd16741b47b605f20889eee27cc46b0d  results/metrics/combined_charts/M&M.png
2fff1c5a7023c61598b33e5188c5b77b1f0c6bfa43e4fedc0a1f8eb24f053c2b  results/metrics/combined_charts/M&MFIN.png
ada5dc45c8180e5dfb01bc45e3e6949b479886ec016b14e2076c2a007ad8a268  results/metrics/combined_charts/MARUTI.png
3cd13fbc0731c119554a444c32215738518462d4e6cddef14faee7de51d0076b  results/metrics/combined_charts/NESTLEIND.png
569f528e67df831361706bf00ea3ae8f7d7281d4d9c7b96f100bb0cd7fc2d030  results/metrics/combined_charts/NTPC.png
ab5f4e17b4fc3f05ea9052e3ed0f8716243d37c7862bcc13e4cd0077b72df046  results/metrics/combined_charts/NTPCGREEN.png
c1ae443cfdfa39ba4408b6a582f45c858a4c86b8b4d0f4ff9edf88040f09bd3b  results/metrics/combined_charts/ONGC.png
4477635f01295578deebbd0a7d64b2251d1280147fb9da4b21966a2796ce0771  results/metrics/combined_charts/POWERGRID.png
5dd2be1bc1807e375e52553e058a7147da9da93b1863fb76b3e9415aa46e95d5  results/metrics/combined_charts/RELIANCE.png
09ca1848b630a27c36500d931292289c97d192a2b1987d64011dcc8503c6f724  results/metrics/combined_charts/SBILIFE.png
165518dae560f28a4960a63937656f089a180f88c91ea82d20345c6fbc87ebe2  results/metrics/combined_charts/SBIN.png
7ecb80a65d38417265d17323991880fd6021631f0ec97703a91c1b3d5792bf55  results/metrics/combined_charts/SHRIRAMFIN.png
be2d821866b33556ff54c9890d3516fd8a2571be3ac5312a690b55faad86d5ee  results/metrics/combined_charts/SUNPHARMA.png
058a9b1abfb8ea88eb4c44ae6925cc21f18b94132f10fe3452263960ac18433a  results/metrics/combined_charts/TATACONSUM.png
72e228d18dc26aa11ad36ef1b50f7849d42b8f46a1f4e7fdbd99b7668f9b4237  results/metrics/combined_charts/TATASTEEL.png
4fe8a1122e2075fd97813633bf8d78899a3d58ae930a120cc67618141d3dd556  results/metrics/combined_charts/TCS.png
8ed1e0b00373432baab99b8c0bf5082ec164d8d3e4e86b784466c4ea0e2c5c87  results/metrics/combined_charts/TECHM.png
9953913d6a800533c7b34cdff992246043f9d9821b3e0c3c3addb06fb50ed30d  results/metrics/combined_charts/TITAN.png
353ef3c6b921fe219d930a152447911569240e04da477959f260c9c29771b192  results/metrics/combined_charts/ULTRACEMCO.png
754563c06f9a8a859d2d319120536a5ba107a3d8db53063bfe783a95cb8c85d2  results/metrics/combined_charts/WIPRO.png
8c59f1a56cf1e25704d8a65bd018b84ca3d8d1ff027b3f56d0c82b1a06e2a90a  results/metrics/daily_decisions_58.csv
395af05970be949fbd5b927c7b1a28cacf0a4a67b6426b6e178c2b10817e2c64  results/metrics/daily_holdings_58.csv
ff3b8d7a2c1bd3a9932f0c31dc2769be5843b105db87d063ea9bc9bf67bc664c  results/metrics/daily_ranking_58.csv
d353f6f6e3f5b42cacb52b9e962028e3a8929ec711d440bb039a04872234b03e  results/metrics/daily_skipped_58.csv
c4c9eeb72261270b9253e0860ad9d347c699f6e25991029f087441697d50909f  results/metrics/daily_summary_58.csv
c1e2c723e933540f4e52bf6df7e6dbcfd4e26aed00e0849af03222422487ba69  results/metrics/daily_trades_58.csv
0b72fb5a43acc2d6ce520ab51c77e9e4c7dec67fda50485f889c7da1276eb3ae  results/metrics/daily_trades_v1_58.csv
70fb3ac7d756b8b46d750ca1b525cc68df383b0812ba295293f88dd1e22eff7f  results/metrics/decay_factor_ic.csv
ac9d6c7f794eda0924262e4bd54cfe30c3233ab0a3b227be81a5dddbc779947d  results/metrics/fair_comparison_table.csv
36dc1fc7ae99282a3fb61df93cf6e069a48c11bf79d393a5f1807b25405d1a08  results/metrics/feature_dictionary.csv
3fc40b50fb3584d3de6051db0366a48dea63ac706b12e3ee3fe0903edd73c99c  results/metrics/panel_sample.csv
6653d416f36fd505b0df6fda5e45e92ba6871cb4be929e877036af5ba1866036  results/metrics/panel_summary.csv
276bd802458820b8e633c219a2dc14545464c0725e3231c514a27f65dce2ccd9  results/metrics/per_stock_charts/ADANIENT.png
1d8756d3b08160845b4689e95152f86568a9dfd772ba1f885ce4d36b03646540  results/metrics/per_stock_charts/ADANIPORTS.png
7b0c625ec03c5e7eb4edba3805b158c9a6eea9e3fc41c9223cebb64da757d779  results/metrics/per_stock_charts/APOLLOHOSP.png
cfe1805ad76a6c423cf3e519c64644b319f219def7ac5a76ae618aff54aa0a17  results/metrics/per_stock_charts/ASIANPAINT.png
cdad0958bda7f86d13233c89487b3a3e740cbc199bd4907db04b7056a12684a0  results/metrics/per_stock_charts/AXISBANK.png
1aa329eafb71e75213a41a95b39250df7bc574998c0a10cca28913e7440acbc8  results/metrics/per_stock_charts/BAJAJ-AUTO.png
1220a763b13e76543f9addc6be56b721722510435b8afb0980982956185cf4ad  results/metrics/per_stock_charts/BAJAJFINSV.png
9dc6036596dc8b0c5e43136071ffcd6f38c0d0e9d6e19483ce4e4c94e5d0b3c4  results/metrics/per_stock_charts/BAJFINANCE.png
3eeb13be599f2a7d146c6fcc5ed0306a858161b83261911f662e8b16077a446a  results/metrics/per_stock_charts/BEL.png
d67165dd01700b3ceda0dc18375082e78eed25d3e987fa770d370b50086fb693  results/metrics/per_stock_charts/BELRISE.png
277f904809b74a128b2745dbc6d74bfb42d0cda301d1ca1b71106dcd7799d6c5  results/metrics/per_stock_charts/BHARTIARTL.png
3fe07594071e108bb41c79e0908fa6b7ed9b201309fbe63824ca8010086510d5  results/metrics/per_stock_charts/BPCL.png
605e9e4718693bd7a1652992e8a1de88249838f6ffcc5c938d4c26595b89b479  results/metrics/per_stock_charts/BRITANNIA.png
fa949fcc04e9b21699e553d8e54ce2b6be9197fb866dbba84b57bd3d009c9e4a  results/metrics/per_stock_charts/CIPLA.png
3e5db238ad43429482373e422484bdb9f95c0ee716dedeca676afe34db8d7362  results/metrics/per_stock_charts/COALINDIA.png
6ec9cbffd8e6b8933b26e6d4a34a46d34b5e78fcee01731883bf0ac29d88b3af  results/metrics/per_stock_charts/DRREDDY.png
88e24a135e0672bdea4e566cb8f94533b48d8e7683c25ebf259b1ce3b990c1b2  results/metrics/per_stock_charts/EICHERMOT.png
779bd36ba548a61dbca38ebd4a3930f5cd45c885571bf8379580b26856fdd91d  results/metrics/per_stock_charts/ETERNAL.png
5c392dd1eb79a4ff58e4b6694188b76f274398df6ced9a50d71f38e3006a789b  results/metrics/per_stock_charts/GRASIM.png
831e1177d284704272a89c04dc972e287ab4d23628f1b16dd4f6bad2fef9a2fd  results/metrics/per_stock_charts/HCLTECH.png
bb063f595abfd56c48a382950eca730dfb85500245d709b3928edf813e5f00d1  results/metrics/per_stock_charts/HDFCBANK.png
feecace4f09ecee60cdbb76ca3cf768157a5f73ac9288c7ca4168d197cb137c6  results/metrics/per_stock_charts/HDFCLIFE.png
983bbdcebe08f39a37b5868749ef2f747d1fa75cfbe6baf85dca7e6542cc5668  results/metrics/per_stock_charts/HEROMOTOCO.png
a57e9011d3c57c4f50c86255de5ab9604fd6880f04ccbfafe39486433e6b9e7d  results/metrics/per_stock_charts/HINDALCO.png
aa8ec736f61a2af0c48e75cad8055983c63ee15caf3382be5eb7f648783feeaf  results/metrics/per_stock_charts/HINDUNILVR.png
e7df087591d7ff76a01d911ac15e82650459a679419b6bb15b0beb599f1fbe87  results/metrics/per_stock_charts/ICICIBANK.png
ff3d120ed46a475ad466ee0d01b4d79a43e577fd1e5cf0f20f5371bb6cc96a62  results/metrics/per_stock_charts/INDUSINDBK.png
9c967467c112174fc4f271b0c5ca2494561379ad0b58ff4d3eba77054fd7e620  results/metrics/per_stock_charts/INFY.png
9230c995a29771eea9109b47b4c2a74ac73ffe2e0a90819c506ce922dfb22c20  results/metrics/per_stock_charts/ITC.png
6f3a678e610cbd9137c8762f94298b8be4a32548863fc9e2a232423234e69d7f  results/metrics/per_stock_charts/ITCHOTELS.png
dc56da8dea8b3de08b0fbf68aa1ad1a28c417ba9d41244f4607f98e26b6d5855  results/metrics/per_stock_charts/JSWSTEEL.png
34fdb6ad791944615cf0c0bb1dbfcf60a7f1ae5e8121a6894ce3a3944b6edde8  results/metrics/per_stock_charts/KOTAKBANK.png
718b858ad41603ef19f920cb453e1d57898d66115c76adefab84f516b8758ba8  results/metrics/per_stock_charts/LICI.png
a7bb08d3b439cee51ec44237a1fd3ca3fcae412f9271df8d2c1dffbd57398f3d  results/metrics/per_stock_charts/LT.png
fbd471a3b6052239c14b09d48676c2cbb6f72fa9ca180a9822db1b61378501a4  results/metrics/per_stock_charts/LTF.png
e25c431bffd419801b9c2cfc131adac89a7a376ff7bc042925d55371c89cdde7  results/metrics/per_stock_charts/LTFOODS.png
9535bd91509a6fd0cf2d057044fa1848e046627103282032f8e5959af1841773  results/metrics/per_stock_charts/LTIM.png
57132e918e35a1403e4428e1dcab30dc87ca98dabeeccc1e97c81ae7fe12d340  results/metrics/per_stock_charts/LTTS.png
f30cd646289f36009779a93c3c77e25dc0749e139a9d0971bbd497708cdf96ac  results/metrics/per_stock_charts/M&M.png
ba16f4a72b0006ccf5dab5ad4234185424f86d5b90d0bd3cbd5bd411fc5ca1c7  results/metrics/per_stock_charts/M&MFIN.png
63d33db9bb9b612c32fed8c3e138681cf41ecb9a5ae617472898e515a9a05665  results/metrics/per_stock_charts/MARUTI.png
8a920faa686a528ca211d4a984b9cb5bd1487c405a4065b88974e55ac9764580  results/metrics/per_stock_charts/NESTLEIND.png
b990ba8451571355f388fd1745cd3081d9089d80a254083350607def3ec9b23f  results/metrics/per_stock_charts/NTPC.png
a90cfa8dace90e3cc83799eeea246835b1bb1ea52541f90d5fef3e25909623d3  results/metrics/per_stock_charts/NTPCGREEN.png
5502ac845673d23098d0b242e079f523e998738e9bed9173974268287d620b0b  results/metrics/per_stock_charts/ONGC.png
baaedd3a0053f120eef10e51de6fcb0ecaff6c54810c4ecd0c98aaafe18b2ec1  results/metrics/per_stock_charts/POWERGRID.png
edeb7c864f31766cefdb678cb10efb8c309417dd9fc3e1d210f4130f87dbaadf  results/metrics/per_stock_charts/RELIANCE.png
917c38d93973c39fbe0d48df030c2a61da6da924ffc4dd8cfe0ac1b1e27ca1e3  results/metrics/per_stock_charts/SBILIFE.png
d238a39004b0dc878f708d5026e1e4eeaf0982f376af2da56665d752bb4587ac  results/metrics/per_stock_charts/SBIN.png
36de12e07688240632daaf4a845b166784a83fddf21f2c4e7edd79c824637249  results/metrics/per_stock_charts/SHRIRAMFIN.png
0bc55b48f32f7c59c7c1ccbca843cb68bb7972c82189004b73bc72e9a1fc9619  results/metrics/per_stock_charts/SUNPHARMA.png
0a233f36455e166ea802443f81aec9dbd8e9b0f409941129ea736dbff36cd5f5  results/metrics/per_stock_charts/TATACONSUM.png
feb0f9ac43ff65e9850fb99aa3dc049a7516c12f8e374f89607db3ab9a67a777  results/metrics/per_stock_charts/TATASTEEL.png
ee4938eeceffc8289ed47e16aeab1585116e3fe7935f2e83cc09c8d3b8ac8330  results/metrics/per_stock_charts/TCS.png
1f8368b9546693cb56772014a61381a823bc3d4e8812c55e001bb38f4e1bcdeb  results/metrics/per_stock_charts/TECHM.png
e9483066f7faea8bef6a808a958cef6fe4fb614d43265222e7e0e3b1c6184da8  results/metrics/per_stock_charts/TITAN.png
d0e8ed0b2ed1b268b9b63fb8d86ef391a11ff03a58d08a9fca55889e5cfc7be4  results/metrics/per_stock_charts/ULTRACEMCO.png
2d02a6b2cc409f995d33a05ab3c214060fadde2f7f07452860ea9c00b1624cd0  results/metrics/per_stock_charts/WIPRO.png
e1caf2ac7636e9e49a893184b0d2e3bc4ed29aa8bd8c6839a73cf78f3f47e757  results/metrics/per_stock_charts_summary.csv
5e06eb04c1ac2f4897f1e18348d58cb46590e0f8b7cd601cc1e46e494191040b  results/metrics/per_stock_returns.csv
67ced3e46002e81ba13fb0b6be9645b7937dd2322c7b5b5f4c9b4fddd11f00df  results/metrics/reality_per_stock_pnl.csv
88b8a23007da3722134b5f855b98470d3b8fdfe993415250afceb248c6b1b63e  results/metrics/v2FINAL_comparison.csv
e9f0ad8c00882b463ba572ceac3e6969a034e0da4edad107b712f6d87ce9a930  results/metrics/v2FINAL_equity.csv
39a7d310db233d9bbb0a6339466d142b702a3cfa65de24041874faa06ea8c2e0  results/metrics/v2FINAL_params.json
f8a93138494657d37e2067a2f5fe7df0735c5610f82e9ace241e81e40ab5187d  results/metrics/v2FINAL_yearly.csv
56d921c0f7d95dd5c0aec3d99226a8f51d59b2650341ca35b30562683811c2b0  results74/metrics/DAILY_LOG_74.txt
c9d356c66771f9df0708fff8d102f1c1a446aaf35de97eb27de78c72ead4260a  results74/metrics/cash_series_74.csv
d737f25a4121f86c6b70d595ab55b07cc6b0be7dab3dde94f651519c8367af72  results74/metrics/chart_v2FINAL.png
b2934022570f1c38aaccada5083a41c1266a783929b1658834a51daeb9ffac54  results74/metrics/daily_decisions_74.csv
7dea1606b4282488b8dbc3305767c1dd7e0148156ff6a4fab333a160771ea53c  results74/metrics/daily_holdings_74.csv
5e0528c845350cbfa55cc43023ab1b0f5dc5d43c78537e0627facf7f1acedfa1  results74/metrics/daily_ranking_74.csv
ec721d17f3ecf91300e9691be8bb32032ac188556eb7796f4b9abb88f68dc63c  results74/metrics/daily_skipped_74.csv
9e298e71e462064b3d383f430483095fb12f42396d5969238aa2d5e3823c1213  results74/metrics/daily_summary_74.csv
e16da51499664883958092da562d50cab242713de2bb9bf51ddf7802bb643e2c  results74/metrics/daily_trades_74.csv
5054986ab070956276da026fbfd0eccb639b7e8ac69e41c1a21a8c1cae55c1fa  results74/metrics/daily_trades_v1_74.csv
656fe9e08eec9d5f8efb8a526233b4eeb2bccdd09d33d0874185b607e4cee7bb  results74/metrics/v2FINAL_comparison.csv
426cbbac86e088da85130731489dbac76a89229a51285b7ee00f0a179748436b  results74/metrics/v2FINAL_equity.csv
7860cbaddced40991dd1439f6a3d371233b3d98019998f48840c2be74e32496b  results74/metrics/v2FINAL_params.json
bd56d38e83b16997f44db034dc366a32ff083804b527f3f1c2fa695ddca20cb3  results74/metrics/v2FINAL_yearly.csv
```

---

## 4. The naming scheme, and a rule about it

These universes owned `FINAL_*` and `v2FINAL_*`. The surviving universes use
`v34_*`. With the 58 and the 74 deleted, **`FINAL_*` and `v2FINAL_*` are dead
naming schemes and no live code may emit them again.**

This is enforced, not merely stated. `run.py`'s pre-flight refuses to start a
run when `results/metrics/` contains a universe-tagged artefact -- `FINAL_*`,
`v2FINAL_*`, `v34_*`, `DAILY_LOG_*`, `daily_trades_*`, `daily_summary_*`,
`cash_series_*`, or any name ending `_<tag>.<ext>` for a registered tag -- and
names every offending file. The refusal message cites this document.

## 5. results/metrics is no longer any universe's output home

`results/` was always two things at once: the shared engine directory, and the
58's metrics directory (`config.METRICS_DIR = results/metrics`). That
collision is why `results/` could not be deleted with the 58.

`config.METRICS_DIR` is unchanged and still points at `results/metrics`. What
changed is what may be written there: **shared, non-universe output only.** A
universe's artefacts belong in its own metrics directory, which the registry
holds (`u.metrics_dir`), and the pre-flight above enforces the boundary.

Repointing it to `results/shared/` was considered and rejected for this pass:
five modules bind `M = config.METRICS_DIR` at module level, including
`engine_core` and `test_exposure`, and moving them in the same commit as a
deletion would make a breakage impossible to attribute.

**This declaration is currently half hollow, and the record should say so.**
The only shared non-universe artefacts this project has ever produced are
`stability_raw.csv` and `stability_summary.csv`, written by
`results/stability_test.py` -- which cannot run, because it imports
`results/engine_v2.py` and that file has been absent since before this
retirement. So `results/metrics` is now a directory with a rule and no
legitimate occupant. See `KNOWN_ISSUES.md`.

## 6. The trading calendar

`data/nse_trading_calendar.csv` was derived from the 58 and is now **tracked
source data**, not a derived artefact. `results/make_trading_calendar.py` was
deleted with the universe it read.

```
sha256 of the last 58-derived build:
  84365a97ca316000ba992e07e2b32de889006e9fcd419ef34893bbbeb5fed74e
days: 6574    range: 2000-01-03 to 2026-06-08
```

The dates are byte-identical to that build; only the header has changed.

**Why it was not reparented onto mid u n100.** Coverage was never the problem --
mid u n100 covers every session in the file. Contamination is: those two
universes' raw files carry rows on market holidays, and they carry the SAME
ones. 279 phantom dates, 247 of them present in BOTH, so cross-checking one
against the other removes nothing. The 58's files carried no holiday rows,
which is the single property it was chosen for. The best available quorum rule
(listed-fraction >= 0.40) removes all 279 phantoms at the cost of 3 GENUINE
sessions -- 2003-03-22, 2017-04-04 and 2017-12-02, two of them NSE Saturday
special sessions. That is a weaker form of the bug that got
`trading_calendar.yaml` rejected.

**The end date is a data boundary, not a market one.** 2026-06-08 is the last
date in `data/raw/nifty50`. The surviving raw data already runs past it -- n100
to 2026-06-22, mid to 2026-08-06 -- and those sessions are absent from the
calendar, so `build_panel` drops them. Widening `config.BT_END_DATE` past
2026-06-08 meets `engine_core._check_calendar`'s RANGE assertion, which is the
intended behaviour. No append-only extension tool exists yet; building one is
its own decision.

## 7. Three price files that outlived the universes

`BELRISE`, `LTFOODS` and `LTIM` exist in no surviving universe -- established
by comparing all three against all 249 surviving raw files on overlapping
dates, not by name. They are in `data/raw/retired_singletons/` with the
evidence. `LTFOODS` alone is 4,812 sessions back to 2006. Nothing reads that
directory.

## 8. The feature documentation was 58-derived

`results/export_feature_docs.py` called `build_panel` without `data_dir`, which
defaulted to the 58. So `feature_dictionary.csv`, `panel_sample.csv` and
`panel_summary.csv` in `results/metrics` described **the 58's panel**, under
names that read as universal.

| artefact | tracked in git? | disposition |
|---|---|---|
| `feature_dictionary.csv` | **no** | 58-derived; exists only in the snapshot |
| `panel_sample.csv` | **no** | 58-derived; exists only in the snapshot |
| `panel_summary.csv` | **no** | 58-derived; exists only in the snapshot |

All three are untracked, absent from the working tree, and present in
`forensic_snapshot_20260911T0100/results/metrics/`. Nothing tracked was
deleted. The script is deleted and **no surviving code produces a feature
dictionary for mid or n100.** See `KNOWN_ISSUES.md`.

---

## 9. Disposition of every prose citation

### The census, re-measured

The survey that authorised this pass said "59 citations: KNOWN_ISSUES 33,
EXPERIMENTS 24, NAUTILUS_STATUS 2, README 2". That count was produced by a
loose grep and it was wrong in both directions. Measured properly against the
restored documents:

| document | lines naming 58/74 | citing a figure | naming a deleted file |
|---|---:|---:|---:|
| `KNOWN_ISSUES.md` | 84 | 1 | 57 |
| `experiments/EXPERIMENTS.md` | 141 | 18 | 8 |
| `nautilus/NAUTILUS_STATUS.md` | 18 | 0 | 0 |
| `README.md` | 6 | 0 | 1 |
| `docs/README.md` | 2 | 0 | 1 |
| **total** | **251** | **19** | **67** |

### The rule applied

**A reference that describes what a file DID is not a dangling pointer.** Most
of the 67 are of this kind -- `"make_final_chart_fair.py read daily_trades_58.csv,
which was produced two steps later"` is a bug report about a pipeline that
existed, and rewriting it would falsify the record rather than repair it. Those
are left exactly as written.

**A reference that asserts a file is CURRENT is a dangling pointer**, and every
one was rewritten. Those are listed individually below -- there are eight, and
that is the whole set.

Each of the three long documents also carries a notice under its title stating
that the universes and their scripts are deleted and that every reference below
is historical, so a reader meeting a past-tense passage cannot mistake it for
something runnable.

### The eight rewritten citations

| location | was | now |
|---|---|---|
| `README.md:104` | "Two universes are retired ... and are kept" | deleted 2026-09-11, pointer to this file |
| `README.md:108-109` | "58 (retired)" / "74 (retired)" table rows | "58 (deleted 2026-09-11)" / "74 (deleted 2026-09-11)" |
| `README.md:185` | "`diagnose_decay.py`, which runs on the 58 only" | ran on the 58; script and universe deleted, **chart cannot be regenerated** |
| `README.md:287` | "those runs build the 58 and the 74 only ... current pipeline builds four universes" | built, both since deleted; current pipeline builds mid and n100 |
| `docs/README.md:10` | "`chart_decay.png` generated by `diagnose_decay.py` (STEP 4)" | marked deleted; chart cannot be regenerated |
| `docs/README.md:15,20` | "`--universe all` writes `chart_COMBINED_n100_mid_58_74.png`" | `--universe all` is now the pair; filename corrected |
| `EXPERIMENTS.md:1937, 3951` | `sizing_test.py` "(kept)", "the only artefact of that experiment" | deleted 2026-09-11; the accept rule quoted in entry 26 is now the only copy |
| `EXPERIMENTS.md:3926` | "`results/test_v1_v2_blend.py` is kept for that reason" | deleted; the two mean-invested constants transcribed into section 2 above |
| `KNOWN_ISSUES.md:2079` | "`make_final_chart_fair.py` runs only on the retired 58 and 74" | ran only on them; both deleted, the script with them |

### Artefacts named in prose that no longer have a producer

| artefact | cited in | disposition |
|---|---|---|
| `diagnostics/task2_ic_decay.txt` | tracked; holds 58 IC-decay numbers | **kept as history.** Its producer `diagnostics/task2_ic_decay.py` read `results/metrics/raw_panel_cache.csv` -- the 58's raw panel -- and was deleted 2026-09-11. The numbers in it are the last IC-decay measurement of the 58 and cannot be reproduced; there is no mid or n100 equivalent |
| `docs/chart_decay.png` | tracked; embedded in README | **kept as history**, marked in `docs/README.md` as unregenerable |
| `feature_dictionary.csv`, `panel_sample.csv`, `panel_summary.csv` | untracked, snapshot only | 58-derived; see section 8 and `KNOWN_ISSUES.md` |
| `diagnostics/seed_noise.txt` | tracked | **kept.** It reports a MISMATCH on both live universes and no spread, so it never established a noise floor. Unaffected by this retirement, but it is the anchor every sigma claim leans on and it does not hold |

### Two entries in KNOWN_ISSUES.md added by this pass

- **`results/engine_v2.py` is absent, and two modules still import it** --
  `audit_leakage.py` and `stability_test.py` fail at import, and have since
  before this retirement. It also records that `results/metrics`'s demotion to
  shared output is half hollow, because `stability_*.csv` are its only
  legitimate occupants and cannot be produced.
- **The feature documentation was generated from the 58, and has no replacement.**

---

## 10. What this pass did NOT do

Recorded so the next reader does not mistake silence for completion.

- **No clean-room reproduction was run with the 58 and 74 present.** The agreed
  order had one before retirement; it was dropped. Those two universes were the
  only ones whose figures were anchored in both the snapshot and tracked prose,
  so that three-way check is no longer possible for anything.
- **`year_range` survives on `Universe` with no setter.** Every universe now cuts
  by date; the year-cut branch in `window()` is unreachable. It is NOT the same as
  the `frozen` flag this pass deleted -- `frozen` had no reader left, while
  `year_range` is read by `window()` on every panel construction, so it is a
  default nobody chose sitting in the path of every run. Recorded as its own
  entry in `KNOWN_ISSUES.md`, at the severity of the others.
- **The panels were rebuilt on 2026-09-12 and the numbers did not move.** A cold
  `--universe all --arm v2 --steps all` run reproduced both universes' v2 rows
  byte-identically against this snapshot, on every field. The pipeline crashed
  afterwards at STEP 10h on a pre-existing defect unrelated to the retirement
  (`make_n100_chart.py` was never made arm-aware); `save_caches_step` therefore
  did not run, so the permanent panel caches come from that run's `/tmp` copies.
