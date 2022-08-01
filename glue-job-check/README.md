Glueジョブ実行履歴取得スクリプト
====
Glueの各ジョブの1日分の実行履歴をCSVファイルに保存するスクリプト

## Description
- Glueジョブ一覧取得し、各ジョブに対して1日分の実行履歴をCSV出力する
- LambdaはアカウントAから実行し、それ以外のアカウントの情報はクロスアカウントで取得する。
- 全アカウント分の情報を1つのCSVファイルに書き出し、S3に保存する
- Lambda実行を前提とし、実行した前日の0:00から、実行した当日の0:00までのジョブ実行履歴を対象とする
- Lambdaトリガーにて1日1回定期実行されるよう設定する

### 注意事項
- ジョブを削除した場合、ジョブ実行履歴を取得することはできない
    - 対象とするジョブの選定は、boto3の `get_jobs` を使用して取得できるジョブとするため(削除したジョブは `get_jobs` で取得できない)
- そのため、ジョブを削除した場合は、スクリプト実行状況次第で請求書の料金と合わない可能性が出てくる。

## Requirement
- Lambdaの外部モジュールとして以下をLambdaにZIPアップロードする
    - pytz
- Glueジョブチェックを対象AWSアカウントに実施する際に必要なAssumeRole設定を入れる必要がある
    - 各アカウントに容易に展開できるようにAssumeRoleの設定はCloudFormationで実行する

### CSV出力する項目

| 項目 | 内容 |
| ---------------------- | -------------------------------------------------------------------------------------------- |
| JobId | GlueジョブID |
| JobName | Glueジョブ名 |
| StartedOn | Glueジョブ開始時間 |
| CompletedOn | Glueジョブ完了時間 |
| ExecutionTime(s) | Glueジョブの実行でリソースを消費した時間(秒) |
| ExecutionTimeRollup(s) | 最小課金処理を実施したExecutionTime |
| MaxCapacity | Glueジョブの実行に割り当てられるGlueデータ処理ユニット(DPU)の数 |
| Cost | 料金(MaxCapacity × ExecutionTimeRollup(s) / 3600 × 0.44 ) <br>https://aws.amazon.com/jp/glue/pricing/ |
| Job_Type | ジョブタイプ(SparkジョブまたはPython Shellジョブ) |
| GlueVersion | Glueのバージョン(バージョンによりGlue がサポートするSparkとPythonのバージョンを決定する) |
| Timestamp | スクリプト開始時刻 |

### 出力先S3
- 出力パス: aws/usage/yyyy/mmdd/Glue-UsageReport-YYYYMMDDhhmm.csv

### データ取得について
- スクリプト内でboto3の `get_job_runs` を使用するが、最大データ取得可能数が各Glueジョブ200個までとなっている(`MaxResults` の最大が200)
- `NextToken` を使うことで、再帰処理をして過去全てのジョブ履歴を対象にすることは可能。
    - ただし、ジョブ履歴が増えていくたびにスクリプト実行時間も延びていくこととなる。
    - Glueジョブチェックスクリプト(日付指定バージョン)として作成。

## 処理の流れ
以下の処理の流れで実行する

1. 各アカウントで以下の処理を実行する
    a. Glueジョブ一覧取得
    b. 各Glueジョブに対して、1日分の実行履歴をCSVに出力(追記)する
2. 出力されたCSVファイルをS3へアップロードする

## Lambda設定
- 環境変数

| 項目             | 内容                                                      |
| ---------------- | --------------------------------------------------------- |
| account_list     | 取得対象とするAWSアカウントを、カンマ区切りで複数指定可能 |
| assume_role_name | AssumeRole名を、全アカウントで共通で指定                  |
| s3_bucket_name   | CSVファイルを出力するS3バケット名                         |
