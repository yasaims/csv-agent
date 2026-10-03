from csv_agent.retriever import Retriever, tokenize


def test_tokenize_lowercases_ascii_words() -> None:
    assert tokenize("USB-C Hub") == ["usb", "c", "hub"]


def test_tokenize_splits_japanese_into_character_bigrams() -> None:
    assert tokenize("無線マウス") == ["無線", "線マ", "マウ", "ウス"]


def test_tokenize_keeps_single_japanese_character() -> None:
    assert tokenize("青 軸") == ["青", "軸"]


def test_tokenize_normalizes_fullwidth_characters() -> None:
    assert tokenize("ＵＳＢ１") == ["usb1"]


DOCS = [
    "name: ワイヤレスマウス | category: 周辺機器",
    "name: 4Kモニター | category: ディスプレイ",
    "name: ヘッドホン | category: オーディオ",
    "name: USB-Cハブ | category: 周辺機器",
]


def test_search_ranks_matching_document_first() -> None:
    retriever = Retriever(DOCS)

    assert retriever.search("モニター", k=2)[0] == 1


def test_search_returns_at_most_k_indices() -> None:
    retriever = Retriever(DOCS)

    assert len(retriever.search("周辺機器 マウス ハブ", k=1)) == 1


def test_search_excludes_documents_without_matching_terms() -> None:
    retriever = Retriever(DOCS)

    assert retriever.search("キーボード", k=4) == []
