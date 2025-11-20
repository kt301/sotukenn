#!/bin/bash
# ★ 1. 実行するスクリプトのリスト ★

SCRIPTS_TO_RUN=(
    "src/sa_out.py"
    "src/sa_out2.py"
    "src/sa_out3.py"
    "src/sa_out4.py"
)

echo ""
echo "=========================================="
echo "SAパラメータ一括実行を開始します (全 ${#SCRIPTS_TO_RUN[@]} 件)"
echo "=========================================="

i=1

# リスト (SCRIPTS_TO_RUN) の中身を1つずつ取り出してループ
for script_path in "${SCRIPTS_TO_RUN[@]}"
do
    script_name=$(basename "$script_path")

    echo ""
    echo "--- ($i/${#SCRIPTS_TO_RUN[@]}) 実行開始: $script_name ---"

    # ★ python3の実行 (出力はそのままターミナルに表示) ★
    python3 $script_path

    # 終了コード($?)だけをチェック
    if [ $? -ne 0 ]; then
        # 失敗した場合
        echo ""
        echo "!!! エラー: $script_name の実行が失敗しました。"
        echo "!!! 後続のスクリプトの実行を中断します。"
        exit 1 # エラーでスクリプトを終了
    else
        # 成功した場合
        echo "--- $script_name 正常に完了 ---"
    fi
    
    i=$((i + 1))
done

echo ""
echo "=========================================="
echo "すべてのスクリプトが正常に完了しました。"
echo "=========================================="