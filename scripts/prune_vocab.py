"""Poda o vocabulario do modelo ONNX fp32 + tokenizer para ~50k tokens de
portugues, cortando a matriz de embeddings (82% do modelo) para caber no free
tier. Ver docs/otimizacao-memoria.md.

Mantem:
  1) os tokens especiais nos IDs ORIGINAIS (<s>=0, <pad>=1, </s>=2, <unk>=3) —
     preserva o calculo de posicao do XLM-R (padding_idx=1) e o post_processor;
  2) TODOS os tokens do dominio (protocolos + perguntas reais) — obrigatorio;
  3) preenchimento com os tokens de maior score de script latino (PT) ate TARGET.

O par (model.onnx podado, tokenizer.json remapeado) e escrito JUNTO em OUT: se
descasarem, os IDs viram lixo silenciosamente. Regerar ambos sempre juntos.

Uso: python scripts/prune_vocab.py <dir_fp32> <out_dir> [target=50000]
  <dir_fp32> precisa ter model_fp32.onnx + tokenizer.json (ver export_model.py).
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import onnx
from onnx import numpy_helper
from tokenizers import Tokenizer

PROTO_DIR = Path("docs/protocolos")
CHUNK_WORDS, OVERLAP = 400, 50

# Perguntas reais do dominio, para garantir cobertura do vocabulario de consulta.
DOMAIN_QUESTIONS = [
    "Como faco a ordenha?", "Posso doar leite congelado?", "Quais criterios para ser doadora?",
    "Meu bebe tem 4 meses posso doar?", "Como higienizar os frascos?",
    "Qual a temperatura para armazenar o leite?", "Estou tomando remedio posso amamentar?",
    "Onde fica o banco de leite mais proximo?", "Como agendar a coleta?",
    "Quero me cadastrar na plataforma", "Preciso de exames para doar?",
    "Meu leite empedrou o que fazer?", "Como aumentar a producao de leite?",
    "Doacao de leite ajuda bebes prematuros na UTI neonatal", "Quero falar com uma enfermeira",
]

# Scripts nao-latinos (CJK, Hangul, Cirilico, Arabe, Hebraico, Tailandes,
# Devanagari, Kana, formas de largura total): excluidos do preenchimento para
# priorizar tokens de portugues/latino.
NON_LATIN = re.compile(
    "[　-鿿가-힯Ѐ-ӿ؀-ۿ֐-׿"
    "฀-๿ऀ-ॿ぀-ヿ＀-￯]"
)


def _chunks(text: str) -> list[str]:
    w = text.split()
    if len(w) <= CHUNK_WORDS:
        return [text] if text.strip() else []
    out, s = [], 0
    while s < len(w):
        e = s + CHUNK_WORDS
        out.append(" ".join(w[s:e]))
        if e >= len(w):
            break
        s = e - OVERLAP
    return out


def main(src_dir: str, out_dir: str, target: int) -> None:
    src, out = Path(src_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    tj = json.load(open(src / "tokenizer.json", encoding="utf-8"))
    vocab = tj["model"]["vocab"]  # [[token, score], ...]; id = indice
    n_old = len(vocab)
    special_ids = [0, 1, 2, 3]  # <s>, <pad>, </s>, <unk> — ficam nos ids originais
    mask_old = next(a["id"] for a in tj["added_tokens"] if a["content"] == "<mask>")

    # Tokens do dominio (sem truncar), dos protocolos + perguntas.
    tok = Tokenizer.from_file(str(src / "tokenizer.json"))
    tok.no_truncation()
    domain: set[int] = set()
    for f in sorted(PROTO_DIR.glob("*.md")):
        words = f.read_text(encoding="utf-8").split()
        for i in range(0, len(words), 80):
            domain.update(tok.encode(" ".join(words[i:i + 80])).ids)
    for q in DOMAIN_QUESTIONS:
        domain.update(tok.encode(q).ids)
    domain -= set(special_ids) | {mask_old}

    kept_old = list(special_ids)
    seen = set(kept_old) | {mask_old}
    for oid in sorted(domain):
        kept_old.append(oid)
        seen.add(oid)
    for oid in sorted(range(n_old), key=lambda i: -vocab[i][1]):  # maior score primeiro
        if len(kept_old) >= target - 1:  # -1: reserva o slot do <mask>
            break
        if oid in seen or not _is_latin(vocab[oid][0]):
            continue
        kept_old.append(oid)
        seen.add(oid)
    kept_old.append(mask_old)
    new_mask_id = len(kept_old) - 1
    print(f"vocab: {n_old} -> {len(kept_old)} | dominio={len(domain)} | mask_new_id={new_mask_id}")

    model = onnx.load(str(src / "model_fp32.onnx"))
    emb_init = next(i for i in model.graph.initializer if "word_embeddings" in i.name)
    emb = numpy_helper.to_array(emb_init)
    new_emb = emb[np.array(kept_old, dtype=np.int64)]
    emb_init.CopyFrom(numpy_helper.from_array(new_emb, emb_init.name))
    onnx.save(model, str(out / "model.onnx"))

    tj["model"]["vocab"] = [vocab[oid] for oid in kept_old]
    tj["model"]["unk_id"] = 3
    for a in tj["added_tokens"]:
        if a["content"] == "<mask>":
            a["id"] = new_mask_id
    json.dump(tj, open(out / "tokenizer.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("OK poda em", out, "| embeddings:", new_emb.shape)


def _is_latin(tok: str) -> bool:
    return NON_LATIN.search(tok) is None


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 50000)
