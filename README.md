# nucleo-f401re

ST NUCLEO-F401RE を対象とした、ベアメタルのマイコン研修です。受講者自身の
パソコン上で [Renode](https://renode.io) を使ってシミュレーションします。サーバは
不要で、管理者権限も必要ありません。

A bare-metal microcontroller course built on the ST NUCLEO-F401RE, simulated
locally in [Renode](https://renode.io) on the learner's own computer. Nothing is
hosted, and nothing needs administrator rights.

**まず [`SETUP.ja.md`](SETUP.ja.md) から始めてください。**

**Start at [`SETUP.md`](SETUP.md).**

## 収録されているもの / What is here

| | 日本語 | English |
| --- | --- | --- |
| [`SETUP.ja.md`](SETUP.ja.md)<br>[`SETUP.md`](SETUP.md) | 受講者のセットアップ手順。標準であるコンテナ版 | How a learner sets up: the container route, which is the standard one |
| [`NATIVE-SETUP.ja.md`](NATIVE-SETUP.ja.md)<br>[`NATIVE-SETUP.md`](NATIVE-SETUP.md) | コンテナを使わない手順。コンテナが動かないパソコン向け | The route without a container, for machines that cannot run one |
| [`boards/nucleo_f401re.repl`](boards/nucleo_f401re.repl) | ボード定義。Renode はこのボードの定義を同梱していないため、汎用の STM32F4 を実機に合わせて絞り込んでいます | The board. Renode ships no description for it, so this one narrows Renode's generic STM32F4 to the real part |
| [`DIVERGENCES.ja.md`](DIVERGENCES.ja.md)<br>[`DIVERGENCES.md`](DIVERGENCES.md) | シミュレーションが実機と異なる点の一覧（読みやすい形式） | Every known way the simulation differs from real hardware, readable |
| [`divergences.json`](divergences.json) | 同じ内容のデータ。こちらが元で、上の文書は自動生成されます | The same, as data. This is the source; the document above is generated from it |
| [`versions.env`](versions.env) | 動作確認しているツールのバージョン | The tool versions this is verified against |
| [`exercises/`](exercises/) | 4 つの実装課題と、そのビルド・実行方法 | The four exercises, and how to build and run them |
| [`.grade-on-push`](.grade-on-push) | 空のファイル。これがある間は push のたびに採点されます。削除すれば止まり、研修側が戻すことはありません | An empty file. While it is here, every push is graded; delete it and that stops, and the course will not put it back |
| [`lib/`](lib/) | CMSIS ヘッダ、スタートアップコード、リンカスクリプト。全課題で共有 | CMSIS headers, the startup code and the linker script, shared by every exercise |
| [`verify/`](verify/) | コンパイラとシミュレータが組み合わせて動くことを確かめる自己テスト | A self-test proving a learner's compiler and simulator work together |
| [`tools/`](tools/) | 環境チェックとビルドスクリプト。OS ごとに 1 つずつ | The environment check and the build script, one of each per platform |
| [`board.repl`](board.repl) | あなたのボード。標準構成に、パレットから追加した部品が加わります | Your board: the stock one plus anything you add from the palette |
| [`vis/`](vis/) | ボードビュー。ブラウザ上にボードを描き、シミュレータの状態をそのまま映します。部品を追加するパレットもここにあります | The board view: a drawing of the board in a browser, live from the simulator, with the palette you add parts from |
| [`tests/sweep.py`](tests/sweep.py) | 検証スイープ | Verification sweep |

## シミュレーションは実機ではありません / The board is not the hardware

Renode の STM32F4 モデルは F401RE の上位集合です。ボード定義で直せるものは直して
いますが、直せないものは黙って回避せず
[`divergences.json`](divergences.json) に記録しています。

Renode's STM32F4 model is a superset of the F401RE, and the board description
corrects what it can. What it cannot correct is written down in
[`divergences.json`](divergences.json) rather than quietly worked around.

そのうち 2 つは、保守者ではなく受講者に影響します。シミュレータは
**オープンドレインの設定を無視する**ため、ピンの設定が正しくなくても I2C は動作し、
同じコードが実機では失敗します。また**センサーの値は往復しません**。25.00 ℃ を
設定しても firmware は 24.99 ℃ を読みます。そのため値の一致を判定するコードは、
正しいかどうかではなく丸め誤差によって失敗します。

Two of those matter to a learner rather than to a maintainer. The simulator
**ignores the open-drain pin setting**, so an I2C bus works whether or not the
pins were configured correctly and the same code fails on a real board. And
**sensor readings do not round-trip** — set 25.00 °C and the firmware reads
24.99 — so a check comparing for equality fails on a rounding artefact rather
than on whether the code is right.

## チェックの実行 / Running the checks

**Windows**

```
powershell -ExecutionPolicy Bypass -File tools\check-environment.ps1
python tests\sweep.py
```

**macOS ・ Linux / macOS and Linux**

```
./tools/check-environment.sh
python tests/sweep.py
```

環境チェックは自己テストのビルドと実行まで行うため、2 つのツールが「それぞれ
存在する」だけでなく「組み合わせて動く」ことまで確認します。スイープは
divergences.json を検証し、fixed と記録されている主張を実行中のシミュレータに
対して確かめます。どちらも失敗時は 0 以外で終了します。

The environment check builds and runs the self-test, so it proves the tools work
together rather than merely both existing. The sweep validates the divergence
register and asserts every claim it marks as fixed against a running simulator.
Both exit non-zero when they fail.
