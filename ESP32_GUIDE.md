# ESP32車体開発者向けガイド

## システム概要

このシステムは、**4駅3車両の循環型レール**を管理するサーバーです。
スマホなどから車両を呼び出すと、サーバーが最適な移動計画を立て、ESP32に指示を出します。

```
┌─────────────────────────────────────┐
│         円形レール（4駅）            │
│                                     │
│    駅1 → 駅2 → 駅3 → 駅4 → 駅1      │
│     ↑    ↑    ↑    ↑              │
│   車両a 車両b 車両c  (空き)         │
└─────────────────────────────────────┘
```

### 設計思想

- **駅数（4） > 車両数（3）** なので、常に1駅は空いている
- この特性により、デッドロックなしで車両を自由に移動できる
- サーバーが集中管理、ESP32はステートレスに動作

## 通信プロトコル

### 基本フロー

```
ESP32                           サーバー
  │                                │
  │  1秒ごとにポーリング              │
  ├─ GET /vehicles/a/command ────→│
  │                                │
  │  次の行動を取得                  │
  │←─ {"action": "forward"} ───────┤
  │                                │
  │  モーター起動、前進              │
  │  ↓                             │
  │  黒線検知、停止                  │
  │                                │
  │  到着報告                        │
  ├─ POST /vehicles/a/report ─────→│
  │                                │
  │  次のコマンドを待つ              │
  ├─ GET /vehicles/a/command ────→│
  │                                │
```

### エンドポイント

#### 1. コマンド取得（ポーリング）

**ESP32 → サーバー**

```http
GET https://mono.kiyo.dev/api/v1/vehicles/{car_id}/command
```

**レスポンス例**

```json
{
  "command_id": 123,
  "action": "forward",
  "expected_station": 2
}
```

| フィールド | 型 | 説明 |
|-----------|---|------|
| `command_id` | int | コマンドの一意ID（重複実行防止用） |
| `action` | string | 行動指示（`"forward"`, `"stop"`） |
| `expected_station` | int | 次に到着するはずの駅番号（1-4） |

**actionの種類**

- `"forward"`: 次の駅に進む → モーター起動
- `"stop"`: 停止 → 何もしない（待機）

#### 2. 到着報告

**ESP32 → サーバー**

```http
POST https://mono.kiyo.dev/api/v1/vehicles/{car_id}/report
Content-Type: application/json

{
  "command_id": 123,
  "event": "arrived",
  "expected_station": 2,
  "detected_station": 2,
  "pattern_confident": true,
  "mismatch": false
}
```

| フィールド | 型 | 説明 |
|-----------|---|------|
| `command_id` | int | 実行したコマンドのID |
| `event` | string | 常に `"arrived"` |
| `expected_station` | int | サーバーから指示された駅番号 |
| `detected_station` | int | パターン認識で検出した駅番号 |
| `pattern_confident` | bool | パターン認識の信頼度（高い=true） |
| `mismatch` | bool | expected != detected の場合 true |

**レスポンス**

```json
{
  "status": "ok",
  "message": "Report received"
}
```

## ESP32実装ガイド

### 必要なライブラリ

- `WiFi.h`（ESP32標準）
- `HTTPClient.h`（ESP32標準）
- `ArduinoJson.h`（ライブラリマネージャーでインストール）

### 基本コード

```cpp
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// 設定
const char* CAR_ID = "a";  // 車両ID: "a", "b", "c"
const char* SERVER_URL = "https://mono.kiyo.dev";
const char* WIFI_SSID = "your_ssid";
const char* WIFI_PASSWORD = "your_password";

// 状態管理
int currentCommandId = -1;
int expectedNextStation = 0;
unsigned long lastPoll = 0;

void setup() {
  Serial.begin(115200);

  // WiFi接続
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  // モータードライバーのピン設定
  pinMode(MOTOR_PIN1, OUTPUT);
  pinMode(MOTOR_PIN2, OUTPUT);
  pinMode(PWM_PIN, OUTPUT);

  // フォトリフレクタのピン設定
  pinMode(PHOTO_SENSOR_PIN, INPUT);
}

void loop() {
  // 1秒ごとにコマンドをポーリング
  if (millis() - lastPoll > 1000) {
    pollCommand();
    lastPoll = millis();
  }

  // 移動中かつ黒線検知
  if (isMoving() && detectBlackLine()) {
    stopMotor();
    reportArrival();
  }
}
```

### コマンドポーリング

```cpp
void pollCommand() {
  HTTPClient http;
  String url = String(SERVER_URL) + "/api/v1/vehicles/" + CAR_ID + "/command";

  http.begin(url);
  int httpCode = http.GET();

  if (httpCode == 200) {
    String payload = http.getString();
    DynamicJsonDocument doc(256);
    deserializeJson(doc, payload);

    int commandId = doc["command_id"];
    const char* action = doc["action"];
    int expectedStation = doc["expected_station"] | 0;

    // 新しいコマンドの場合のみ実行
    if (commandId != currentCommandId) {
      currentCommandId = commandId;
      expectedNextStation = expectedStation;

      Serial.printf("Command #%d: %s -> Station %d\n",
                    commandId, action, expectedStation);

      executeCommand(action);
    }
  } else {
    Serial.printf("HTTP Error: %d\n", httpCode);
  }

  http.end();
}

void executeCommand(const char* action) {
  if (strcmp(action, "forward") == 0) {
    moveForward();
  } else if (strcmp(action, "stop") == 0) {
    stopMotor();
  }
}
```

### 到着報告

```cpp
void reportArrival() {
  int detectedStation = detectStationNumber();
  bool confident = isPatternConfident();
  bool mismatch = (expectedNextStation != detectedStation);

  HTTPClient http;
  String url = String(SERVER_URL) + "/api/v1/vehicles/" + CAR_ID + "/report";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  DynamicJsonDocument doc(512);
  doc["command_id"] = currentCommandId;
  doc["event"] = "arrived";
  doc["expected_station"] = expectedNextStation;
  doc["detected_station"] = detectedStation;
  doc["pattern_confident"] = confident;
  doc["mismatch"] = mismatch;

  String jsonStr;
  serializeJson(doc, jsonStr);

  int httpCode = http.POST(jsonStr);

  if (httpCode == 200) {
    Serial.printf("✓ Arrived at Station %d (expected: %d)\n",
                  detectedStation, expectedNextStation);
  } else {
    Serial.printf("✗ Report failed: %d\n", httpCode);
  }

  http.end();
}
```

### モーター制御

```cpp
// ピン定義（例）
#define MOTOR_PIN1 25
#define MOTOR_PIN2 26
#define PWM_PIN 27

bool moving = false;

void moveForward() {
  digitalWrite(MOTOR_PIN1, HIGH);
  digitalWrite(MOTOR_PIN2, LOW);
  analogWrite(PWM_PIN, 200);  // 速度調整（0-255）
  moving = true;
  Serial.println("Motor: FORWARD");
}

void stopMotor() {
  digitalWrite(MOTOR_PIN1, LOW);
  digitalWrite(MOTOR_PIN2, LOW);
  analogWrite(PWM_PIN, 0);
  moving = false;
  Serial.println("Motor: STOP");
}

bool isMoving() {
  return moving;
}
```

### 駅検知（フォトリフレクタ）

```cpp
#define PHOTO_SENSOR_PIN 34
#define BLACK_LINE_THRESHOLD 2000  // 調整が必要

bool detectBlackLine() {
  int value = analogRead(PHOTO_SENSOR_PIN);
  return (value < BLACK_LINE_THRESHOLD);
}

// 駅番号の判定（パターン認識）
int detectStationNumber() {
  // 実装例1: 黒線の本数をカウント
  int lineCount = countBlackLines();
  return lineCount;

  // 実装例2: expected_stationをそのまま返す（簡易版）
  // return expectedNextStation;
}

bool isPatternConfident() {
  // パターン認識が確実な場合 true
  // 簡易実装では常に false でもOK
  return false;
}

int countBlackLines() {
  // 実装例: 停止後に少し動いて黒線をカウント
  int count = 0;
  for (int i = 0; i < 10; i++) {
    if (detectBlackLine()) {
      count++;
      delay(100);  // チャタリング防止
      while (detectBlackLine()) delay(10);  // 黒線を抜けるまで待つ
    }
    // 少し前進（モーターを短時間パルス）
    pulseFoward(50);
  }
  return count;
}
```

## 駅パターン設計例

### 案1: 黒線の本数で識別

```
駅1:  ─  (1本)
駅2:  ─ ─  (2本)
駅3:  ─ ─ ─  (3本)
駅4:  ─ ─ ─ ─  (4本)
```

黒線の間隔: 5mm、線幅: 3mm

### 案2: サーバー依存（パターン認識なし）

サーバーの `expected_station` をそのまま信頼する最もシンプルな方法。
駅判定は全て「白→黒の立ち下がり検知」のみ。

```cpp
int detectStationNumber() {
  return expectedNextStation;  // サーバーを信頼
}

bool isPatternConfident() {
  return false;  // パターン認識は使わない
}
```

## デバッグ方法

### シリアルモニタで状態確認

```
WiFi Connected!
IP: 192.168.1.50
Command #1: forward -> Station 2
Motor: FORWARD
✓ Arrived at Station 2 (expected: 2)
Command #2: forward -> Station 3
Motor: FORWARD
✓ Arrived at Station 3 (expected: 3)
Command #3: stop -> Station 3
Motor: STOP
```

### サーバーの状態確認

ブラウザで https://mono.kiyo.dev を開くと、リアルタイムダッシュボードが表示されます。

```json
// または curl でステータス取得
curl https://mono.kiyo.dev/api/v1/status
```

### よくあるエラー

| エラー | 原因 | 解決方法 |
|--------|------|---------|
| `HTTP Error: -1` | WiFi切断 | WiFi接続を確認 |
| `HTTP Error: 404` | URL間違い | URLとCAR_IDを確認 |
| `HTTP Error: 422` | JSONフォーマット不正 | フィールド名とデータ型を確認 |
| 同じコマンドが繰り返される | 到着報告が届いていない | reportArrival()が実行されているか確認 |
| 駅番号がずれる | パターン認識エラー | expected_stationを信頼する実装に変更 |

## テスト手順

### 1. WiFi接続テスト

```cpp
void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected!");
  Serial.println(WiFi.localIP());
}
```

### 2. HTTP通信テスト

```cpp
void loop() {
  HTTPClient http;
  http.begin("https://mono.kiyo.dev/health");
  int code = http.GET();
  Serial.printf("Health check: %d\n", code);
  Serial.println(http.getString());
  http.end();
  delay(5000);
}
```

期待される出力:
```
Health check: 200
{"status":"healthy","initialized":true}
```

### 3. モーター動作テスト

```cpp
void loop() {
  moveForward();
  delay(2000);
  stopMotor();
  delay(2000);
}
```

### 4. フォトリフレクタテスト

```cpp
void loop() {
  int value = analogRead(PHOTO_SENSOR_PIN);
  Serial.printf("Sensor: %d %s\n", value,
                value < BLACK_LINE_THRESHOLD ? "[BLACK]" : "[WHITE]");
  delay(100);
}
```

白い場所で高い値（例: 3500）、黒い線で低い値（例: 500）が出ることを確認。

### 5. 統合テスト

1. サーバーのダッシュボードで初期化: 車両aを駅1に配置
2. ESP32を起動
3. ダッシュボードで「車両aを駅3に呼ぶ」
4. ESP32が自動的に移動 → 駅2で停止 → 駅3で停止

## トラブルシューティング

### 車両が動かない

```cpp
// デバッグ用: サーバーレスポンスを全て表示
if (httpCode == 200) {
  String payload = http.getString();
  Serial.println("Response:");
  Serial.println(payload);
}
```

チェックポイント:
- サーバーが初期化されているか（ダッシュボードで確認）
- 車両が呼び出されているか
- WiFiが接続されているか
- `action` が `"forward"` になっているか

### 位置がずれた

ダッシュボードの「Reset System」ボタンを押して、再度初期化。

### 黒線を検知しない

1. センサーの高さを調整（5-10mm推奨）
2. 閾値を調整（シリアルモニタで値を見ながら）
3. 照明の影響を確認（蛍光灯のちらつきなど）

## 参考情報

- ダッシュボード: https://mono.kiyo.dev
- API仕様書: https://mono.kiyo.dev/docs
- 詳細なREADME: `README.md`

## ライセンス

MIT
