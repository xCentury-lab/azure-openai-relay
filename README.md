# Azure OpenAI Proxy Server

このプロジェクトは、Azure OpenAI Service へのアクセスを中継するプロキシサーバーです。
オンプレミスネットワーク内のクライアントPCから、Azure上の仮想マシンを経由して OpenAI の機能を利用するために使用します。

## 概要と役割

### 役割
このサーバーは「中継役（プロキシ）」として機能します。
- **クライアント側 (オンプレミスPC)**: Azure の認証情報（APIキーなど）を持つ必要がありません。このサーバーのエンドポイントを叩くだけで利用できます。
- **サーバー側 (Azure VM)**: Azure OpenAI の認証情報を一元管理し、クライアントからのリクエストを Azure OpenAI に転送します。

### メリット
- **セキュリティ**: 各クライアントPCに Azure の API キーを配布する必要がありません。
- **ネットワーク**: Azure プライベートネットワークへの接続権限を持つ VM 上で動かすことで、オンプレミスネットワークからのアクセスを一元化できます。

## 必要要件

- Python 3.9 以上
- Azure OpenAI Service のリソース（エンドポイント、APIキー、デプロイ名）

## セットアップ方法

1. **リポジトリのクローンまたはファイルの配置**
   ソースコードをサーバー（Azure VM）上に配置します。

2. **仮想環境の作成と依存ライブラリのインストール (uvを使用)**
   
   高速なパッケージマネージャー `uv` を使用して環境を構築することを推奨します。

   ```bash
   # uv のインストール (未インストールの場合)
   pip install uv

   # 仮想環境の作成 (Pythonバージョンを指定する例)
   uv venv --python 3.12

   # 仮想環境の有効化
   # Mac/Linux:
   source .venv/bin/activate
   # Windows:
   # .venv\Scripts\activate

   # 依存ライブラリのインストール
   uv pip install -r requirements.txt
   ```

3. **環境変数の設定**
   `.env.example` を `.env` にコピーし、Azure OpenAI の情報を設定してください。
   ```bash
   cp .env.example .env
   vi .env
   ```
   
   **設定項目:**
   - `AZURE_OPENAI_API_KEY`: Azure OpenAI の API キー
   - `AZURE_OPENAI_ENDPOINT`: エンドポイント URL (例: `https://my-resource.openai.azure.com/`)
   - `AZURE_OPENAI_API_VERSION`: API バージョン (例: `2023-05-15`)
   - `AZURE_MODEL_MAP`: OpenAIのモデル名とAzureデプロイ名のマッピング (JSON形式)
     - 例: `{"gpt-3.5-turbo": "my-gpt35-deployment", "gpt-4": "my-gpt4-deployment"}`
     - クライアントから `model="gpt-3.5-turbo"` を指定すると、Azure上の `my-gpt35-deployment` にリクエストが飛びます。
     - マッピングにないモデル名が指定された場合は、その名前がそのままデプロイ名として使用されます。

## 起動方法

以下のコマンドでサーバーを起動します。

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

これで、`http://<サーバーのIP>:8000` でリクエストを受け付けるようになります。

## デーモン化（Ubuntu/systemd による自動起動設定）

サーバー再起動時などに自動的にアプリが起動するように、systemd のサービスとして登録する手順です。

1. **サービスファイルの作成**
   `/etc/systemd/system/azure-openai-proxy.service` というファイルを作成します。
   
   ※ 以下の `User`, `WorkingDirectory`, `ExecStart` のパスは環境に合わせて書き換えてください。
   （例: ユーザー名が `xxxuser`、アプリの配置場所が `/home/xxxuser/azure-openai-proxy` の場合）

   ```ini
   [Unit]
   Description=Azure OpenAI Proxy Server
   After=network.target

   [Service]
   User=xxxuser
   Group=xxxuser
   WorkingDirectory=/home/xxxuser/azure-openai-proxy
   # uv で作成した仮想環境内の uvicorn を指定
   ExecStart=/home/xxxuser/azure-openai-proxy/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

2. **サービスの有効化と起動**

   ```bash
   # systemd の設定読み込み
   sudo systemctl daemon-reload

   # 自動起動の有効化
   sudo systemctl enable azure-openai-proxy

   # サービスの起動
   sudo systemctl start azure-openai-proxy

   # ステータスの確認
   sudo systemctl status azure-openai-proxy
   ```

## 使い方（クライアント側）

オンプレミスのPCからこのサーバーを利用する例です。

### Python (OpenAI SDK) を使う場合

`base_url` にこのプロキシサーバーのアドレスを指定し、`api_key` はダミーの値を入れます（認証はプロキシサーバーが行うため）。

```python
from openai import OpenAI

# プロキシサーバーのIPアドレスを指定
PROXY_URL = "http://<Azure-VM-IP>:8000/v1"

client = OpenAI(
    base_url=PROXY_URL,
    api_key="dummy"  # プロキシ側で認証するため、クライアント側はダミーでOK
)

response = client.chat.completions.create(
    # クライアント側でモデル名を指定可能
    # AZURE_MODEL_MAP で定義されたマッピングに従って Azure のデプロイ名に変換されます
    model="gpt-3.5-turbo", 
    messages=[
        {"role": "user", "content": "こんにちは、元気ですか？"}
    ]
)

print(response.choices[0].message.content)
```

### Curl コマンドを使う場合

```bash
curl -X POST "http://<Azure-VM-IP>:8000/v1/chat/completions" \
     -H "Content-Type: application/json" \
     -d '{
           "messages": [{"role": "user", "content": "こんにちは"}]
         }'
```

## 注意事項

- 現在の構成では、プロキシサーバー自体への認証（Basic認証など）は実装されていません。オンプレミスネットワークなど、信頼できるネットワーク内での利用を想定しています。
- 必要に応じて、ファイアウォール（NSG）でポート 8000 へのアクセスを許可してください。
