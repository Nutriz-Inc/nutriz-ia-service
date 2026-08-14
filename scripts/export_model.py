"""Exporta o paraphrase-multilingual-MiniLM-L12-v2 fp32 ORIGINAL para ONNX
(model_fp32.onnx + tokenizer.json). Passo 1 de 2 da geracao do artefato de
embeddings; o passo 2 (poda de vocabulario) esta em prune_vocab.py.

Roda FORA do build do Docker (precisa de torch/transformers). A imagem final
carrega so o model.onnx PODADO. Ver docs/otimizacao-memoria.md.

Uso: python scripts/export_model.py <out_dir>
"""
import sys
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    tokenizer.save_pretrained(out)  # tokenizer.json (fast)

    model = AutoModel.from_pretrained(MODEL)
    model.eval()

    dummy = tokenizer(["texto de exemplo para o trace"], return_tensors="pt", padding=True)
    torch.onnx.export(
        model,
        (dummy["input_ids"], dummy["attention_mask"], dummy["token_type_ids"]),
        str(out / "model_fp32.onnx"),
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "seq"},
            "attention_mask": {0: "batch", 1: "seq"},
            "token_type_ids": {0: "batch", 1: "seq"},
            "last_hidden_state": {0: "batch", 1: "seq"},
        },
        opset_version=14,
        do_constant_folding=True,
        dynamo=False,
    )
    print(f"fp32 ONNX + tokenizer exportados em {out}")
    print("Passo 2: python scripts/prune_vocab.py", out, "models 50000")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build")
