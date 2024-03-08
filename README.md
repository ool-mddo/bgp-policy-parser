# bgp-policy-parser
ネットワーク機器のコンフィグからBGPポリシーの設定を読み取り、共通のモデルとして出力するためのツールです。

対応しているOSは以下の通りです。
- Juniper Junos OS
- Cisco IOS-XR

# playgroundにおける役割

このツールは[playground](https://github.com/ool-mddo/playground)のシステムにおいて、実機のコンフィグからOS非依存なBGPポリシーのコンフィグデータを生成するために使用しています。

# ツール単体での使用方法

> [!NOTE]
> このツールは[playgroundのシステム](https://github.com/ool-mddo/playground/blob/main/doc/system_architecture.md)に組み込んで使用することを想定しています。
> 以下の手順では、本来はシステムによって生成されるファイルを手動で作成することによって、このツール単体で使用する場合の手順を書いています。

1. 各種ファイルの配置

以下のような構造でコンフィグを配置してください。

```
configs/<network>/<snapshot>/configs/<コンフィグファイル>
```

`network`と`snapshot`は任意の値を指定してください。

例えば`network`に`mddo`、`snapshot`に`original_asis`と指定してコンフィグを配置する場合、以下のようになります。

```
configs
└── mddo
    └── original_asis
        └── configs
            ├── Core-TK01
            ├── Core-TK02
            ├── Edge-TK01
            ├── Edge-TK02
            └── Edge-TK03
```

また、この各種ファイルのOSタイプを示すために`queries/<network>/<snapshot>/node_prop.csv`に、以下のようにノードとOSタイプの対応を記載したファイルを作成してください。

> [!NOTE]
> 本来はBatfishから生成されるものですが、ここでは本ツールの単体実行を想定して手動で作成します。

```csv
Node,Configuration_Format
Core-TK01,JUNIPER
Core-TK02,JUNIPER
Edge-TK01,JUNIPER
Edge-TK02,JUNIPER
Edge-TK03,CISCO_IOS_XR
```

2. スクリプトを実行

コンフィグファイルをOSごとに分けるスクリプトを実行します。ここでは引数に上記で指定した`network`と`snapshot`を指定します。

```sh
$ python src/collect_configs.py --network mddo --snapshot original_asis
```

これによって`configs/mddo/original_asis/configs/`配下にOSタイプごとにコンフィグファイルが配置されます。

次に変換スクリプトを実行します。
```sh
$ python src/parse_bgp_policy.py --network mddo --snapshot original_asis
```

これによってTTPによってパースした結果と共通のポリシーモデルに変換した結果がファイルとして出力されます。

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

# APIによる実行

上記の処理はAPIによる実行も可能です。これは[app.py](./src/app.py)によって提供されます。
配置するファイルは前述のスクリプトの実行時と変わりません。

使用するにはまずAPIサーバを立ち上げます。

```sh
$ python src/app.py
```

次に以下のエンドポイントを叩きます。`network`と`snapshot`は配置したコンフィグの場所によって変更してください。

```
POST /bgp_policy/<network>/<snapshot>/parsed_result
```

たとえば前述のコンフィグファイルをパースする場合は以下の様に実行します。

```
curl -s -X POST -H "Content-Type: application/json" \
    -d '{}' \
    "http://localhost:5000/bgp_policy/mddo/original_asis/parsed_result"
```

これによって、スクリプトを実行したときと同じように、`ttp_output`にはパース結果、`policy_model_output`には変換結果が出力されます。
