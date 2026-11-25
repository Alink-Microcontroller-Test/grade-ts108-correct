# コンテナを使わないセットアップ

標準の手順はコンテナです（[`SETUP.ja.md`](SETUP.ja.md)）。こちらは、それが
使えない場合の手順です。

**Docker も管理者権限もファームウェアの設定もライセンスも不要です。**
アーカイブを 2 つダウンロードして展開し、`PATH` に追加するだけです。システムには
何もインストールされないため、コンテナが使えない管理された業務用パソコンでも
動作します。

ただし、この手順が使えないパソコンが 1 種類あります。
[Intel Mac](#intel-mac) を参照してください。

所要時間はおよそ 15 分です。

> この文書は [`NATIVE-SETUP.md`](NATIVE-SETUP.md) の日本語版です。両方を
> 同時に更新してください。

---

## 1. コードを取得する

```
git clone https://github.com/<組織名>/<リポジトリ名>.git
cd <リポジトリ名>
```

clone の前に、教員へ伝えたのと同じ GitHub アカウントでログインした状態で
招待を承認してください。

**clone は次の手順より先に行ってください。** 手順 4 のチェックは、この
リポジトリの中にあるスクリプトだからです。

## 2. コンパイラを取得する

[Arm のダウンロードページ](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads)
から、お使いの OS 向けの **Arm GNU Toolchain** をダウンロードします。
`arm-none-eabi` 版を選んでください。自分のパソコン向けではなく、マイコン向けの
コードを生成するのはこちらです。

任意の場所へ展開し、その中の `bin` ディレクトリを `PATH` に追加します。

本コースが動作確認しているバージョンは [`versions.env`](versions.env) に
記載しています。近いバージョンであれば通常は問題ありません。異なる場合は
手順 4 が知らせます。

## 3. シミュレータを取得する

[リリースページ](https://github.com/renode/renode/releases/tag/v1.16.1) から
**Renode** をダウンロードします。インストーラではなく **portable** 版を選んで
ください。展開するだけで実行でき、システムには何も書き込まれません。

| OS | 取得するファイル |
| --- | --- |
| Windows | `renode-1.16.1.windows-portable-dotnet.zip` |
| macOS（Apple シリコン） | `renode-1.16.1-dotnet.osx-arm64-portable.dmg` |
| macOS（Intel） | 下の [Intel Mac](#intel-mac) を参照 |
| Linux | `renode-1.16.1.linux-portable.tar.gz` |

これらはリリースページ上の実際のファイル名です。よく似た名前のファイルが複数
あるので、自分の OS の行だけを見て、他は無視してください。

展開したら、`PATH` に追加するか、その中の `renode` を指す環境変数 `RENODE` を
設定してください。Windows では zip は `renode_1.16.1-dotnet_portable` という
フォルダに展開され、その中の `renode.exe` が本体です。`RENODE` に
`...\renode_1.16.1-dotnet_portable\renode.exe` を設定するのが一番簡単です。

Linux 版は `curl` しか入っていない環境で動作確認済みです。Mono も .NET も
追加のライブラリも不要でした。

**このバージョンを使ってください。** ボード定義は Renode に同梱されている
ファイルを土台にしているため、バージョンが違うと、コードを一切変えていなくても
ボードの挙動が変わることがあります。

## 4. 動作を確認する

**Windows**

```
powershell -ExecutionPolicy Bypass -File tools\check-environment.ps1
```

**macOS / Linux**

```
./tools/check-environment.sh
```

各ツールを探してバージョンを表示したうえで、小さな自己テストをビルドして
シミュレータ上で実行します。2 つが「組み合わせて動く」ことまで確認するためです。

問題がなければ次の行で終わります。

```
Ready. Your machine builds and runs this board correctly.
```

## 5. 最初の課題に取りかかる

[`exercises/README.ja.md`](exercises/README.ja.md) へ進んでください。また、
書いたコードが実機でも動くと考える前に
[`DIVERGENCES.ja.md`](DIVERGENCES.ja.md) を読んでください。

---

## Intel Mac

**この手順は Intel Mac では使えません。** Renode は Intel Mac 向けのビルドを
公開していません。本コースが使う 1.16.1 には `osx-arm64` 版しかなく、Intel macOS 版があったのは 1.16.0 までです。Rosetta も
助けになりません。Rosetta は Intel 向けのソフトウェアを Apple シリコン上で
動かすもので、その逆はできないためです。

コンテナの手順（[`SETUP.ja.md`](SETUP.ja.md)）を使ってください。

どちらの Mac かは次のコマンドで確認できます。

```
uname -m
```

`arm64` なら Apple シリコンで、この手順が使えます。`x86_64` なら Intel で、
使えません。

## うまくいかないとき

**コンパイラを展開したのに「見つからない」と言われる。** `bin` ディレクトリが
`PATH` に入っていない可能性が高いです。`PATH` を変更したらターミナルを開き
直してください。開いたままのターミナルは古い値を保持しています。

**シミュレータが「見つからない」と言われる。** `PATH` に頼らず、展開した
フォルダの中にある `renode` のフルパスを環境変数 `RENODE` に設定してください。

**Renode のバージョンが違うと警告された。** そのままでも動作します。ボードの
挙動がおかしい場合は、まずここを疑ってください。

**チェックはすべて通るのに、自分のプログラムがうまく動かない。** その場合、
原因はセットアップではなくコードの側にあります。それを切り分けることが、この
チェックの目的です。
