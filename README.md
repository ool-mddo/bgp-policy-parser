# 使い方

1. configsディレクトリにデバイスのコンフィグを配置
- junosのコンフィグ -> configs/junos/
- xrのコンフィグ -> configs/xr/

2. pythonスクリプトを実行

```
python main.py
```

3. ttp_outputディレクトリにTTPでパースした結果が出力される
- junos -> ttp_output/junos/
- xr -> ttp_output/xr/

4. policy_model_outputディレクトリに標準化したポリシーモデルが出力される
- junos -> policy_model_output/  
※xrはまだ未実装です
