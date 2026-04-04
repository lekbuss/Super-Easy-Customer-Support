# Deploy

Azure VM へのデプロイに必要なファイル群です。

## ファイル構成

| ファイル | 説明 |
|---|---|
| `fastapi.service` | FastAPI (uvicorn) の systemd ユニットファイル |
| `streamlit.service` | Streamlit ダッシュボードの systemd ユニットファイル |
| `deploy.sh` | git pull → pip install → サービス再起動を一括実行するスクリプト |

---

## 初回セットアップ（VM で1回だけ手動実行）

```bash
# 1. リポジトリを clone
git clone https://github.com/<owner>/Super-Easy-Customer-Support.git /home/azureuser/Super-Easy-Customer-Support

# 2. venv を作成して依存関係をインストール
cd /home/azureuser/Super-Easy-Customer-Support/project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 環境変数ファイルを配置
#    /home/azureuser/.env に必要な変数を記載する
#    例: OPENAI_API_KEY=sk-...

# 4. systemd にサービスを登録
sudo cp deploy/fastapi.service /etc/systemd/system/fastapi.service
sudo cp deploy/streamlit.service /etc/systemd/system/streamlit.service
sudo systemctl daemon-reload
sudo systemctl enable fastapi streamlit
sudo systemctl start fastapi streamlit

# 5. deploy.sh を azureuser が sudo なしで実行できるよう sudoers を設定
#    /etc/sudoers.d/azureuser-deploy を作成:
echo "azureuser ALL=(ALL) NOPASSWD: /bin/systemctl restart fastapi, /bin/systemctl restart streamlit, /bin/systemctl is-active fastapi, /bin/systemctl is-active streamlit" | sudo tee /etc/sudoers.d/azureuser-deploy
sudo chmod 440 /etc/sudoers.d/azureuser-deploy
```

---

## 以降のデプロイ（自動）

`main` ブランチに `git push` するだけで GitHub Actions が SSH 経由で `deploy.sh` を実行します。

```
git push origin main
# → GitHub Actions が自動でデプロイ
```

---

## GitHub Secrets の設定

リポジトリの **Settings → Secrets and variables → Actions** に以下を登録してください。

| Secret 名 | 値 |
|---|---|
| `AZURE_VM_HOST` | VM のパブリック IP アドレス（例: `20.10.xx.xx`） |
| `AZURE_VM_USER` | SSH ユーザー名（`azureuser`） |
| `AZURE_VM_SSH_KEY` | SSH 秘密鍵の中身（`~/.ssh/id_rsa` の全テキスト） |

### SSH 鍵の取得方法

```bash
# ローカルで秘密鍵を確認（または新規生成）
cat ~/.ssh/id_rsa

# 対応する公開鍵を VM の authorized_keys に追加済みであること
# VM 上で確認:
cat ~/.ssh/authorized_keys
```
