# Phylogenetics Toolbox — Web Frontend

系統樹推定ツール (GS / PANJEP / SJ) をブラウザから実行するための Flask ウェブアプリです。
ユーザーが投入した FASTA / 距離行列 / 類似度行列に対してツールを起動し、
Newick 出力を SVG で可視化して返します。

## 構成

```
[ Browser ] ──HTTP──> [ nginx :80 ] ──proxy──> [ gunicorn :8000 (Flask app) ]
                                                      │
                                                      ├── /app/gs/gs2
                                                      ├── /app/panjep/panjep
                                                      └── /app/sj/sj
```

`docker-compose.yml` は 2 つのサービスを定義します。

- **app**: `docker/app/Dockerfile` からビルドされる Debian bookworm ベースの
  イメージ。`gs2` / `panjep` / `sj` をソースからビルドし、Python の依存
  (Flask, ete3, PyQt5, gunicorn) を venv に同梱します。
- **nginx**: 1.27-alpine イメージ。リバースプロキシとして app:8000 に転送し、
  `/static/` は直接配信します。

## 必要環境

- Docker Engine 20.10 以降
- Docker Compose v2 (`docker compose` コマンド)
- マルチアーキテクチャ対応 (linux/amd64 と linux/arm64 でビルド済み)

## ビルド

```sh
docker compose build
```

初回ビルドは LAPACK / gs2 / panjep / sj のコンパイルが入るため 5〜15 分
かかります。2 回目以降は Docker のレイヤキャッシュで高速化されます。

## 起動

```sh
docker compose up           # フォアグラウンド
docker compose up -d        # バックグラウンド
```

デフォルトでは `http://localhost:8080` で待ち受けます。
ホスト側のポートを変えたい場合は `BIND_PORT` を指定:

```sh
BIND_PORT=9000 docker compose up -d
# → http://localhost:9000
```

停止:

```sh
docker compose down
```

## 使い方

1. ブラウザで `http://localhost:8080/` を開く
2. ヘッダーから `GS` / `PANJEP` / `SJ` のいずれかを選択
3. Input data 欄に FASTA や距離行列をペースト
   (説明文の右の `(sample)` リンクで例データを読み込めます)
4. オプションを設定して `Run`
5. 計算が終わると Newick の SVG ツリー、ASCII ツリー、保存ファイルの
   ダウンロードリンクが表示されます

各 Run の結果は app コンテナ内 `/app/results/<run_id>/tree.nwk` に保存され、
`/results/<run_id>/<filename>` で再取得できます。

## 環境変数

| 変数 | 既定値 | 用途 |
|---|---|---|
| `BIND_PORT` | `8080` | ホスト側で nginx を公開するポート |
| `FORWARDED_ALLOW_IPS` | `*` | gunicorn が X-Forwarded-* を信頼する送信元 |

## ファイルレイアウト

```
.
├── app.py                  # Flask エントリポイント
├── tools.py                # ツール定義 (GS / PANJEP / SJ)
├── viz.py                  # ete3 による Newick → SVG 変換
├── templates/              # Jinja2 テンプレート
├── static/                 # CSS など
├── samples/                # (sample) リンクから読み込まれる例データ
├── docker-compose.yml
└── docker/
    ├── app/Dockerfile      # Flask アプリ用イメージ
    └── nginx/default.conf  # nginx 設定
```

## アーキテクチャに関する補足

- **gunicorn**: sync worker × 2、`--timeout 600`、`--max-requests 200`
  で長時間の計算と Qt 状態のリフレッシュを両立。
- **nginx**: `client_max_body_size 50M`、`proxy_read_timeout 600s`。
  Flask 側の `MAX_CONTENT_LENGTH` と一致させています。
- **同時実行**: 2 ユーザー以上が同時に重い計算を走らせると 3 人目以降の
  リクエストはキューイングされます。CPU に余裕があれば Dockerfile の
  `--workers` を増やしてください。
- **タイムアウト処理**: 各ツールは `subprocess.Popen(start_new_session=True)`
  で起動するため、タイムアウト時には `mmseqs` / `blastn` などの孫
  プロセスも `killpg` でまとめて停止します。
