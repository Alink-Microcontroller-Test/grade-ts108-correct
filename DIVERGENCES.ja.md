# シミュレータと実機の違い

シミュレーション上のボードが実機の ST NUCLEO-F401RE と異なる点の一覧です。

**このファイルは自動生成されます。** 元データは
[`divergences.json`](divergences.json) です。編集したら
`python tools/gen_divergence_table.py` を実行してください。両者が食い違う
場合、検証スイープが失敗します。

> この文書は [`DIVERGENCES.md`](DIVERGENCES.md) の日本語版です。

全 13 件: 恒久的 7 件、未対応 0 件、対処済み 6 件。

## 誤ったコードが正しく見えてしまう違い

これらは特に危険です。いずれもシミュレータのほうが実機より寛容なため、
誤りがあってもシミュレーションでは動作し、実機では失敗します。しかも
誤った時点では何も知らされません。該当する課題の教材では、これらを必ず
注意喚起してください。

### open-drain-ignored

**Renode の挙動** GPIO モデルは出力タイプレジスタを一切見ません。オープンドレインを選ぶために OTYPER に書き込んでも 'Unhandled write to offset 0x4 ... Tags: OT8 (0x1), OT9 (0x1)' が出るだけで、何も変わりません。バスのピンをオープンドレインに設定してもしなくても、I2C 通信は成功します

**実機の挙動** I2C はワイヤード AND のバスです。SCL と SDA の両方をオープンドレインにしてプルアップする必要があります。デバイスはラインを Low に引くことで信号を送り、離すと High に戻るためです。プッシュプル出力では衝突し、バスは動作しません

**状態** 恒久的

**注意喚起する課題** exercises/04-read-the-sensor/main.c

**出典** Observed in the feasibility spike, 2026-09-25, on Renode 1.16.1. Hardware behaviour: RM0368 section 8.3 'I/O port control registers'; the I2C specification's wired-AND requirement

### pin-configuration-not-enforced

**Renode の挙動** バスコントローラは GPIO のレジスタを一切参照しません。I2C モデルはポートモードも代替機能もクロック有効ビットも読まないため、使うはずのピンを全く設定していなくても通信が成立します。2026-09-25 に確認: GPIOB への書き込みをすべて削除した firmware でも Si7021 を正しく読み取れました

**実機の挙動** 周辺機能がピンに届くのは、そのピンを経由する場合だけです。ポートのクロックを有効にし、ピンを代替機能モードにし、正しい代替機能を選ぶ必要があります。どれか一つでも欠ければ、バスには何も届きません

**状態** 恒久的

**注意喚起する課題** exercises/01-blink-with-a-delay/main.c, exercises/02-blink-from-a-timer/main.c, exercises/03-change-the-interval/main.c, exercises/04-read-the-sensor/main.c

**出典** Observed in the feasibility work, 2026-09-25, on Renode 1.16.1. Renode's STM32F4_I2C model contains no reference to GPIO, pins or alternate functions. Hardware behaviour: RM0368 section 8 'General-purpose I/Os' and the alternate function table in DS10086

### sensor-value-quantisation

**Renode の挙動** SI70xx モデルは温度と湿度を固定小数点に変換して保持するため、読み出した値は設定した値とわずかに異なります。25.00 C を設定して firmware から読むと 24.99 C になりました

**実機の挙動** 実際の Si7021 も量子化しますが、その分解能と誤差は固有のもので、モデルが行う丸めとは一致しません

**状態** 恒久的

**注意喚起する課題** exercises/04-read-the-sensor/main.c

**出典** Observed in the feasibility spike, 2026-09-25: sensor set to 25, firmware printed 'RAW=26796 TEMP_C_X100=2499'. Model source: renode-infrastructure SI70xx.cs, which stores (value + 46.85) * 65536 / 175.72

### superset-peripherals

**Renode の挙動** 汎用の STM32F4 プラットフォームは F401RE が持たない周辺機器を宣言しています。Ethernet MAC、CAN1 と CAN2、GPIO ポート F から K、UART4 と UART5、外部メモリコントローラ、そして TIM6、TIM7、TIM8、TIM12、TIM13、TIM14 です。上書きでは削除できないため、使用できてしまいます

**実機の挙動** STM32F401RE が持つのは GPIO ポート A から E と H、USART 3 系統、タイマー TIM1 から TIM5 と TIM9 から TIM11 です。CAN、Ethernet、外部メモリコントローラはありません

**状態** 恒久的

**注意喚起する課題** exercises/README.md, exercises/README.ja.md

**出典** platforms/cpus/stm32f4.repl peripheral declarations, read 2026-09-25. Hardware: STM32F401xD/xE datasheet DS10086, block diagram and pinout

## その他

### cpu-speed-not-from-the-clock-tree

**Renode の挙動** プロセッサは毎秒 1 億命令という固定速度で実行します。これは PerformanceInMips として宣言された値であり、このボードが示す 84 MHz とは無関係です。パイプラインもフラッシュのウェイトステートもキャッシュもないため、すべての命令が同じ時間で終わります。したがってカウントループで書いた遅延の長さは、クロック設定から導かれません。2026-09-28 に測定: ループはシミュレーション時間で毎秒およそ 1,800 万回進みます。実装課題1 の ABOUT_ONE_SECOND は 18,000,000 であり、実際におよそ 1 秒になります。これはこのシミュレータの固定速度に合わせて選んだ値であり、クロック設定から導かれたものではありません

**実機の挙動** 命令のタイミングはコアクロックに従い、コアクロックは発振器、PLL、プログラムが設定するバスプリスケーラに従います。フラッシュのウェイトステートやコードの配置場所にも影響されるため、実機でもカウントループは正確ではありません。ただし実機では、クロックが決める値の周辺で不正確になります

**状態** 恒久的

**出典** Measured 2026-09-28 on Renode 1.16.1: sysbus.cpu PerformanceInMips reports 0x64 (100). Sampling the LED pin while running the first exercise's reference solution gave a half-cycle of 0.111 s over 1 s of simulated time. Hardware behaviour: RM0368 section 6 and the flash latency table in section 3.4

### peripheral-reads-are-slow-to-simulate

**Renode の挙動** 周辺レジスタの読み出しは、変数の読み出しに比べて大きなコストがかかります。変換済みコードを抜けてシステムバスを経由するためです。そのため、ピンを読むだけのループは、読み出しを含まない同じループの約 100 倍遅く動きます。2026-09-28 に測定: main ループでボタンを詰めてポーリングした場合、ボード時間 1 秒のシミュレーションに実時間 156 秒を要しました。同じ動作を割り込みで書いた場合は 1.4 秒、読み出しの間に短い遅延を入れたポーリングでは 5 秒でした

**実機の挙動** ポートレジスタの読み出しはロード命令ひとつ、数クロックであり、RAM 上の変数を読むのと比べて遅くはありません。詰めたポーリングループは実機では電力の無駄ですが、時間の無駄にはなりません

**状態** 恒久的

**出典** Measured 2026-09-28 on Renode 1.16.1, sampling the LED pin while running three reference implementations of the third exercise: tight polling 156x slower than real time, polling with a delay 2.5x, EXTI 1.4x

### static-timer-clocks

**Renode の挙動** 周辺クロックは RCC と PLL のレジスタから導出されません。各タイマーはプラットフォーム定義に書かれた周波数を持ち、クロックツリーを設定してもカウント速度は変わりません

**実機の挙動** タイマーのクロックはクロックツリーに従います。速度は発振器、PLL の設定、バスのプリスケーラによって決まり、そこを誤ればシステム全体のタイミングが変わります

**状態** 恒久的

**出典** platforms/cpus/stm32f4.repl declares a literal frequency on each Timers.STM32_Timer. Hardware behaviour: RM0368 section 6 'Reset and clock control'

### button-polarity

**Renode の挙動** Miscellaneous.Button は押している間ピンを High にします

**実機の挙動** B1 はアクティブ Low です。プルアップが通常時に PC13 を High に保ち、ノーマルオープンのスイッチが押されると GND に短絡させます

**状態** 対処済み

**対処** boards/nucleo_f401re.repl sets invert: true on the board's button

**出典** UM1724 'STM32 Nucleo-64 boards', user button B1 on PC13. Verified 2026-09-25: firmware read 1 at rest, 0 while pressed

### declared-clock-rate

**Renode の挙動** 汎用の STM32F4 プラットフォームは全タイマーを 10 MHz、SysTick を 72 MHz と宣言しています。本ボード定義では F401RE が持つタイマーと SysTick を 84 MHz に上書きしています

**実機の挙動** 標準的な構成では STM32F401RE は 84 MHz で動作し、汎用タイマーには 84 MHz が供給されます

**状態** 対処済み

**対処** boards/nucleo_f401re.repl declares 84000000 on TIM1-5 and TIM9-11 and on the NVIC's systickFrequency

**出典** Override verified 2026-09-25: sysbus.timer2 Frequency reports 0x501BD00. Hardware behaviour: RM0368 section 6.2, APB1 timer clock doubling

### missing-fpu

**Renode の挙動** 汎用の STM32F4 プラットフォームはコアを cortex-m4 と宣言しており、浮動小数点ユニットがありません

**実機の挙動** STM32F401RE は単精度浮動小数点ユニットを持つ Cortex-M4 です

**状態** 対処済み

**対処** boards/nucleo_f401re.repl sets cpuType to cortex-m4f

**出典** STM32F401xD/xE datasheet DS10086. Verified 2026-09-25: sysbus.cpu Model reports cortex-m4f

### oversized-flash

**Renode の挙動** 汎用の STM32F4 プラットフォームはフラッシュを 2 MB と宣言しています

**実機の挙動** STM32F401RE のフラッシュは 512 KB です

**状態** 対処済み

**対処** boards/nucleo_f401re.repl sets flash size to 0x80000

**出典** STM32F401xD/xE datasheet DS10086. Verified 2026-09-25: sysbus.flash Size reports 0x80000

### oversized-sram

**Renode の挙動** 汎用の STM32F4 プラットフォームは SRAM を 256 KB と宣言しています

**実機の挙動** STM32F401RE の SRAM は 96 KB です

**状態** 対処済み

**対処** boards/nucleo_f401re.repl sets sram size to 0x18000

**出典** STM32F401xD/xE datasheet DS10086. Verified 2026-09-25: sysbus.sram Size reports 0x18000

### si7021-not-fitted

**Renode の挙動** I2C1 には何も接続されていません。センサはボード画面のパレットから受講者が追加する部品で、追加すると自分の board.repl に書き込まれます。追加するまでは、実機と同じくバスを読んでも何も見つかりません

**実機の挙動** 実際の NUCLEO-F401RE にはセンサは搭載されていません。読むには Arduino コネクタの D15 を SCL、D14 を SDA として自分で配線します

**状態** 対処済み

**対処** boards/nucleo_f401re.repl declares nothing on i2c1. The board view's palette offers SI7021 at 0x40, and adding it writes the declaration into the learner's own board.repl. The setup self-test brings its own sensor in verify/sensor.repl, because it runs before the learner has opened the board view.

**出典** UM1724, 'STM32 Nucleo-64 boards', lists the fitted components: two user LEDs, one user button, one reset button and the ST-LINK. No sensor. boards/nucleo_f401re.repl declared si7021: Sensors.SI70xx @ i2c1 0x40 until 2026-09-29 and no longer declares anything on the bus.
