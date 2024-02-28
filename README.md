# bgp-policy-parser
ネットワーク機器のコンフィグからBGPポリシーの設定を読み取り、共通のモデルとして出力するためのツールです。

対応しているOSは以下の通りです。
- Juniper Junos OS
- Cisco IOS-XR

# 使用法

1. configsディレクトリにデバイスのコンフィグを配置

以下のディレクトリ構成でパース対象のコンフィグファイルを配置してください。
- Junosのコンフィグ  -> configs/mddo/original_asis/juniper/
- IOS-XRのコンフィグ -> configs/mddo/original_asis/xr/

例として以下のようなファイル配置を取るとします。

```
configs
└── mddo
    └── original_asis
        ├── cisco_ios_xr
        │   └── Edge-TK03
        └── juniper
            ├── Core-TK01
            ├── Core-TK02
            ├── Edge-TK01
            └── Edge-TK02
```

`configs`直下のディレクトリ名は任意の物を使用してください。ここでは`mddo`としています。

2. スクリプトを実行

`--network`という引数には`configs`直下に作成したディレクトリの名前を指定します。

```sh
$ python src/parse_bgp_policy.py --network mddo
```

3. 出力を確認

スクリプトの実行によって複数のディレクトリにファイルが出力されます。

## `ttp_output`

`ttp_output`ディレクトリにはTTPでパースした結果がJSONファイルとして出力されます。ここで出力されるものは単純にコンフィグをパースしたものなので、OSごとに異なる構造を持っています。

```
ttp_output
└── mddo
    └── original_asis
        ├── cisco_ios_xr
        │   └── cisco1.json
        └── juniper
            ├── Core-TK01.json
            ├── Core-TK02.json
            ├── Edge-TK01.json
            └── Edge-TK02.json
```

## `policy_model_output`

`policy_model_output`には上記の出力ファイルからポリシーモデルに変換したものがJSONファイルとして出力されます。これはOS非依存な構造を持っています。

```
policy_model_output
└── mddo
    └── original_asis
        ├── Core-TK01
        ├── Core-TK02
        ├── Edge-TK01
        ├── Edge-TK02
        └── Edge-TK03
```
