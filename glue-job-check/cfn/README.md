glue-job-check(CloudFormation for IAM)
====

AssumeRole設定を入れるCloudFormationテンプレートファイル

## Description
- Glueジョブチェックを対象AWSアカウントに実施する際に必要なAssumeRole設定を入れるCloudFormationテンプレートファイル

### テンプレートで作成するリソース
- IAM
    - リソース使用状況確認用IAMロール
    - Glueジョブチェック用IAMポリシー
### パラメータ
- PrefixName
    - プレフィックス名
    - デフォルト: is55
- Env
    - 環境名
    - デフォルト: dev
    - プルダウンリスト
        - poc
        - dev
        - stg
        - prod
