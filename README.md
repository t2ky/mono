# Circular Rail Vehicle Management System

循環型レールシステムの車両管理用FastAPIサーバー

## 概要

このシステムは、円形レール上に4つの駅があり、3台の車両（a, b, c）が循環運行するシステムを管理します。
スマホなどから特定の車両を指定の駅に呼び出すことができ、車両は自動的に目的地まで移動します。

## システム構成

- **サーバー**: FastAPI (Python)
- **車両**: ESP32 + モータードライバー
- **通信方式**: REST API (ポーリング)
- **駅**: 4箇所 (1, 2, 3, 4)
- **車両**: 3台 (a, b, c)

## セットアップ

### 1. 仮想環境の有効化

```bash
source venv/bin/activate
```

### 2. 依存関係のインストール（既に完了している場合はスキップ）

```bash
pip install -r requirements.txt
```

### 3. サーバーの起動

```bash
# 開発モード（自動リロード有効）
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# または
python main.py
```

サーバーが起動すると、以下のURLでアクセスできます：
- API: http://localhost:8000
- ドキュメント: http://localhost:8000/docs
- 別のドキュメント: http://localhost:8000/redoc

## API エンドポイント

### 1. システム初期化

**POST** `/api/v1/initialize`

車両の初期位置を設定します。システム起動後、最初に呼び出す必要があります。

```bash
curl -X POST "http://localhost:8000/api/v1/initialize" \
  -H "Content-Type: application/json" \
  -d '{"positions": {"a": 1, "b": 2, "c": 3}}'
```

レスポンス:
```json
{
  "status": "ok",
  "message": "System initialized successfully",
  "positions": {"a": 1, "b": 2, "c": 3}
}
```

### 2. 車両を呼び出す

**POST** `/api/v1/call`

指定した車両を指定した駅に呼び出します。

```bash
curl -X POST "http://localhost:8000/api/v1/call" \
  -H "Content-Type: application/json" \
  -d '{"vehicle": "a", "station": 4}'
```

レスポンス:
```json
{
  "status": "ok",
  "message": "Vehicle a called to station 4",
  "vehicle": "a",
  "target_station": 4
}
```

### 3. 車両コマンド取得（ESP32用）

**GET** `/api/v1/vehicles/{car_id}/command`

車両が定期的にポーリングして、次の行動を取得します。

```bash
curl "http://localhost:8000/api/v1/vehicles/a/command"
```

レスポンス:
```json
{
  "command_id": 123,
  "action": "forward",
  "expected_station": 2
}
```

`action` の値:
- `"forward"`: 次の駅に進む
- `"backward"`: 前の駅に戻る（現在未使用）
- `"stop"`: 停止

### 4. 車両ステータス報告（ESP32用）

**POST** `/api/v1/vehicles/{car_id}/report`

車両が駅に到着したときに報告します。

```bash
curl -X POST "http://localhost:8000/api/v1/vehicles/a/report" \
  -H "Content-Type: application/json" \
  -d '{
    "command_id": 123,
    "event": "arrived",
    "expected_station": 2,
    "detected_station": 2,
    "pattern_confident": true,
    "mismatch": false
  }'
```

### 5. システム状態確認

**GET** `/api/v1/status`

現在のシステム状態を取得します（デバッグ用）。

```bash
curl "http://localhost:8000/api/v1/status"
```

レスポンス例:
```json
{
  "initialized": true,
  "vehicles": {
    "a": {
      "current_station": 1,
      "status": "idle",
      "current_command_id": null
    },
    "b": {
      "current_station": 2,
      "status": "idle",
      "current_command_id": null
    },
    "c": {
      "current_station": 3,
      "status": "idle",
      "current_command_id": null
    }
  },
  "stations": {
    "1": {"occupied_by": "a"},
    "2": {"occupied_by": "b"},
    "3": {"occupied_by": "c"},
    "4": {"occupied_by": null}
  },
  "pending_calls": [],
  "next_command_id": 1
}
```

### 6. 車両位置取得（管理画面用）

**GET** `/api/v1/positions`

全車両の現在位置を取得します（初期化と同じフォーマット）。

```bash
curl "http://localhost:8000/api/v1/positions"
```

レスポンス例:
```json
{
  "positions": {"a": 1, "b": 2, "c": 3},
  "initialized": true
}
```

### 7. 移動シーケンス取得（管理画面用）

**GET** `/api/v1/sequences`

各車両の予定移動経路を取得します。

```bash
curl "http://localhost:8000/api/v1/sequences"
```

レスポンス例:
```json
{
  "sequences": {
    "a": [2, 3, 4],
    "b": [],
    "c": []
  },
  "pending_calls": [
    {"vehicle": "a", "target_station": 4}
  ]
}
```

- `sequences`: 各車両が目的地まで訪れる駅の順序
- `pending_calls`: 待機中の呼び出しリスト

### 8. ダッシュボードデータ取得（管理画面用）

**GET** `/api/v1/dashboard`

管理画面用の包括的なデータを取得します。

```bash
curl "http://localhost:8000/api/v1/dashboard"
```

レスポンス例:
```json
{
  "initialized": true,
  "vehicles": {
    "a": {
      "current_station": 1,
      "status": "idle",
      "target_station": 4,
      "next_station": null,
      "sequence": [2, 3, 4]
    },
    "b": {
      "current_station": 2,
      "status": "idle",
      "target_station": null,
      "next_station": null,
      "sequence": []
    },
    "c": {
      "current_station": 3,
      "status": "idle",
      "target_station": null,
      "next_station": null,
      "sequence": []
    }
  },
  "stations": {
    "1": {"occupied_by": "a"},
    "2": {"occupied_by": "b"},
    "3": {"occupied_by": "c"},
    "4": {"occupied_by": null}
  },
  "pending_calls": [
    {"vehicle": "a", "target_station": 4}
  ],
  "movement_plan": [
    {"step": 1, "vehicle": "c", "from_station": 3, "to_station": 4, "reason": "making_space"},
    {"step": 2, "vehicle": "b", "from_station": 2, "to_station": 3, "reason": "making_space"},
    {"step": 3, "vehicle": "a", "from_station": 1, "to_station": 2, "reason": "moving_to_target"}
  ]
}
```

**フィールド説明:**

- `vehicles`: 各車両の詳細情報
  - `current_station`: 現在いる駅（1-4）
  - `status`: 状態（`"idle"`: 停止中、`"moving"`: 移動中）
  - `target_station`: 目的地の駅（ない場合は`null`）
  - `next_station`: 次に向かう駅（移動中の場合）
  - `sequence`: 目的地までに通過する駅のリスト
- `stations`: 各駅の占有状況
- `pending_calls`: 待機中の呼び出しリスト
- `movement_plan`: 次の10ステップの移動計画
  - `step`: ステップ番号
  - `vehicle`: 移動する車両ID
  - `from_station`: 出発駅
  - `to_station`: 到着駅
  - `reason`: 移動理由（`"moving_to_target"`: 目的地へ移動、`"making_space"`: スペース確保）

### 9. システムリセット

**POST** `/api/v1/reset`

システムを初期状態にリセットします。

```bash
curl -X POST "http://localhost:8000/api/v1/reset"
```

### 10. ヘルスチェック

**GET** `/health`

サーバーの稼働状態を確認します。

```bash
curl "http://localhost:8000/health"
```

## ESP32 実装例

以下は、ESP32側の実装例です：

```cpp
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* CAR_ID = "a";
const char* SERVER_URL = "http://192.168.1.100:8000";
unsigned long lastPoll = 0;
int currentCommandId = -1;

void setup() {
  Serial.begin(115200);
  WiFi.begin("your_ssid", "your_password");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected");
}

void loop() {
  // 1秒ごとにコマンドをポーリング
  if (millis() - lastPoll > 1000) {
    checkCommand();
    lastPoll = millis();
  }

  // フォトリフレクタで駅検知
  if (detectStation()) {
    stopMotor();
    reportArrival();
  }
}

void checkCommand() {
  HTTPClient http;
  String url = String(SERVER_URL) + "/api/v1/vehicles/" + CAR_ID + "/command";
  http.begin(url);

  int httpCode = http.GET();
  if (httpCode == 200) {
    DynamicJsonDocument doc(256);
    deserializeJson(doc, http.getString());

    int commandId = doc["command_id"];
    String action = doc["action"];
    int expectedStation = doc["expected_station"] | 0;

    // 新しいコマンドの場合のみ実行
    if (commandId != currentCommandId) {
      currentCommandId = commandId;
      Serial.printf("New command: %s to station %d\n", action.c_str(), expectedStation);
      executeCommand(action);
    }
  }
  http.end();
}

void reportArrival() {
  HTTPClient http;
  String url = String(SERVER_URL) + "/api/v1/vehicles/" + CAR_ID + "/report";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  DynamicJsonDocument doc(512);
  doc["command_id"] = currentCommandId;
  doc["event"] = "arrived";
  doc["expected_station"] = expectedNextStation;
  doc["detected_station"] = detectStationNumber();
  doc["pattern_confident"] = isPatternConfident();
  doc["mismatch"] = (expectedNextStation != detectStationNumber());

  String json;
  serializeJson(doc, json);

  int httpCode = http.POST(json);
  Serial.printf("Report sent: %d\n", httpCode);
  http.end();
}

bool detectStation() {
  // フォトリフレクタで黒線検知
  int value = analogRead(PHOTO_REFLECTOR_PIN);
  return value < THRESHOLD;
}

int detectStationNumber() {
  // 黒線のパターンから駅番号を判定
  // 実装は駅のパターン設計に依存
  return countBlackLines();
}

void executeCommand(String action) {
  if (action == "forward") {
    moveForward();
  } else if (action == "stop") {
    stopMotor();
  }
}
```

## 使用フロー

1. **初期化**
   ```bash
   POST /api/v1/initialize
   # 車両の初期位置を設定
   ```

2. **車両呼び出し**
   ```bash
   POST /api/v1/call
   # 例: 車両aを駅4に呼び出す
   ```

3. **ESP32のポーリングループ**
   - 1秒ごとに `GET /api/v1/vehicles/{car_id}/command` をポーリング
   - `action` が `"forward"` なら次の駅に移動開始
   - 駅（黒線）を検知したら停止
   - `POST /api/v1/vehicles/{car_id}/report` で到着を報告
   - 目的地に到達するまで繰り返し

## 動作原理

### 移動ロジック

1. 車両呼び出しリクエストが来ると、`pending_calls` キューに追加
2. サーバーは順番に処理し、次に移動すべき車両を決定
3. 目的の車両が次の駅に進む際、その駅が塞がっている場合：
   - 塞いでいる車両を先に移動させる
   - 再帰的に空きスペースを作る
4. 各車両は一度に1駅だけ移動
5. 到着報告を受けたら、次の移動を計算

### 状態同期

- **サーバー側**: 全体の状態を集中管理
- **ESP32側**: ステートレスにコマンドを実行
- **駅番号の判定**:
  - メイン: サーバーが `expected_station` で指示
  - 補助: ESP32がパターン認識で検証
  - 不一致時: サーバーに報告して修正

## トラブルシューティング

### 車両が動かない

1. システムが初期化されているか確認
   ```bash
   curl http://localhost:8000/api/v1/status
   ```

2. `pending_calls` にリクエストがあるか確認

3. 車両が正しくポーリングしているか確認

### 位置がずれた

1. リセットして再初期化
   ```bash
   curl -X POST http://localhost:8000/api/v1/reset
   curl -X POST http://localhost:8000/api/v1/initialize \
     -H "Content-Type: application/json" \
     -d '{"positions": {"a": 1, "b": 2, "c": 3}}'
   ```

2. パターン認識が動作していれば、次の移動時に自動修正される

## ファイル構成

```
mono_server/
├── venv/                  # Python仮想環境
├── .claude/
│   └── claude.md         # Claude設定
├── main.py               # FastAPIアプリケーション
├── models.py             # データモデル定義
├── state_manager.py      # 状態管理ロジック
├── requirements.txt      # Python依存関係
└── README.md            # このファイル
```

## 開発メモ

- ポーリング間隔: 1秒（ESP32側で調整可能）
- コマンドの重複実行防止: `command_id` で管理
- 循環ロジック: 駅4の次は駅1に戻る
- 車両数: 3台固定（a, b, c）
- 駅数: 4箇所固定（1, 2, 3, 4）

## ライセンス

MIT
