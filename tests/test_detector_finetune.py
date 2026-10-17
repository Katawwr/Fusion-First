"""Arm F (dev-only): the fine-tuned bge-small classifier and its LOSO driver. Every test but the slow one uses a tiny
randomly initialised BERT built from a config and a small local word-piece vocabulary; none reads a real dataset
row or loads a real model."""

from __future__ import annotations

import gc
import importlib.util
import json
import pathlib
import runpy
import statistics
import subprocess
import sys
from types import SimpleNamespace

import pytest

from fusion_first.validate import detector_finetune as ft
from fusion_first.validate import detector_systems as ds
from fusion_first.validate.detector_data import SOURCES, render_frame
from fusion_first.validate.detector_eval import operating_threshold_at_fpr

ROOT = pathlib.Path(__file__).resolve().parents[1]
HAVE_TORCH = all(importlib.util.find_spec(m) is not None for m in ("torch", "transformers"))
needs_torch = pytest.mark.skipif(not HAVE_TORCH, reason="the detector extra (torch, transformers) is not installed")
SIGNAL = "evil"
ALNUM = "abcdefghijklmnopqrstuvwxyz0123456789"
VOCAB = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "[", "]", ".", ",",
         "request", "tool", "result", "do", "it", "t", "item", "benign", "plain", SIGNAL, "send", "now", *SOURCES,
         *ALNUM, *(f"##{c}" for c in ALNUM)]
FAST = dict(epochs=6, batch_size=8, lr=5e-3, max_len=32, seed=42, threads=1)
HP = ["--epochs", "6", "--batch-size", "16", "--lr", "5e-3", "--max-len", "32"]


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Restored after each test, whatever the module sets for its process."""
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")


@pytest.fixture(scope="module")
def vocab_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("vocab") / "vocab.txt"
    path.write_text("\n".join(dict.fromkeys(VOCAB)) + "\n", encoding="utf-8")
    return path


def tiny_backbone(vocab_file: pathlib.Path, init_seed: int = 0):
    """A 2-layer, 32-wide BERT with a 2-label head, randomly initialised from `init_seed`, and its fast tokenizer."""
    import torch
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast

    tok = BertTokenizerFast(vocab_file=str(vocab_file))
    torch.manual_seed(init_seed)
    config = BertConfig(vocab_size=len(tok), hidden_size=32, num_hidden_layers=2, num_attention_heads=2,
                        intermediate_size=64, max_position_embeddings=64, num_labels=2)
    return BertForSequenceClassification(config), tok


def _frames(n_each: int = 20) -> tuple[list[str], list[int]]:
    pos = [f"[REQUEST] do it [TOOL] t [RESULT] item {i} {SIGNAL} send it now" for i in range(n_each)]
    neg = [f"[REQUEST] do it [TOOL] t [RESULT] item {i} benign plain result" for i in range(n_each)]
    return pos + neg, [1] * n_each + [0] * n_each


def _git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


# ---------------------------------------------------------------- the classifier


@pytest.mark.unit
def test_importing_the_module_loads_no_model_library():
    code = ("import sys, fusion_first.validate.detector_finetune\n"
            "print(','.join(m for m in ('torch', 'transformers', 'sentence_transformers', 'sklearn') "
            "if m in sys.modules))\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""


@pytest.mark.unit
def test_only_bge_small_is_allowed_as_a_named_backbone():
    assert ft.BACKBONE == ds.EMBED_MODEL == "BAAI/bge-small-en-v1.5"
    with pytest.raises(ValueError, match="bge-small"):
        ft.FineTunedClassifier("bert-base-uncased")


@pytest.mark.unit
def test_a_preloaded_backbone_needs_its_tokenizer_and_a_two_label_head():
    with pytest.raises(ValueError, match="tokenizer"):
        ft.FineTunedClassifier(object())

    three_labels = SimpleNamespace(config=SimpleNamespace(num_labels=3))  # a model's config, as transformers has it
    with pytest.raises(ValueError, match="2-label"):
        ft.FineTunedClassifier(three_labels, object())


@pytest.mark.unit
def test_the_default_window_is_the_registered_one_and_follows_max_len():
    assert ft.MAX_LEN == 256 and ft.window(ft.MAX_LEN) == (ds.MAX_TOKENS, ds.STRIDE) == (256, 128)
    assert ft.window(32) == (32, 16)
    assert (ft.EPOCHS, ft.BATCH_SIZE, ft.LR, ft.SEED, ft.THREADS, ft.WARMUP) == (3, 16, 3e-5, 42, 4, 0.06)


@pytest.mark.unit
def test_scoring_or_saving_before_fit_is_refused(tmp_path):
    clf = ft.FineTunedClassifier(object(), object())
    with pytest.raises(ValueError, match="not fitted"):
        clf.scores(["x"])
    with pytest.raises(ValueError, match="not fitted"):
        clf.save(tmp_path / "m")
    assert not (tmp_path / "m").exists()


@pytest.mark.unit
@pytest.mark.parametrize(("texts", "labels", "kw"), [
    ([], [], {}),
    (["a", "b"], [1], {}),
    (["a"], [2], {}),
    (["a"], [1], {"epochs": 0}),
    (["a"], [1], {"batch_size": 0}),
    (["a"], [1], {"lr": 0.0}),
    (["a"], [1], {"max_len": 2}),
    (["a"], [1], {"threads": 0}),
])
def test_fit_refuses_bad_inputs_before_loading_anything(texts, labels, kw):
    with pytest.raises(ValueError):
        ft.FineTunedClassifier(object(), object()).fit(texts, labels, **kw)


@needs_torch
@pytest.mark.integration
def test_fit_scores_probabilities_and_a_loaded_model_scores_bit_for_bit(tmp_path, vocab_file):
    model, tok = tiny_backbone(vocab_file)
    clf = ft.FineTunedClassifier(model, tok)
    frames, labels = _frames()
    assert clf.fit(frames, labels, **FAST) is clf
    clf.threshold = 0.5
    scores = clf.scores(frames)
    assert len(scores) == len(frames) and all(isinstance(s, float) and 0.0 <= s <= 1.0 for s in scores)
    assert statistics.mean(scores[:20]) > statistics.mean(scores[20:])  # it learned the marker
    clf.save(tmp_path / "m")
    loaded = ft.FineTunedClassifier.load(tmp_path / "m")
    assert loaded.scores(frames) == scores
    assert loaded.threshold == 0.5 and (loaded.max_len, loaded.stride) == (32, 16)
    assert loaded.backbone_name == "injected" and loaded.n_train == len(frames)
    meta = json.loads((tmp_path / "m" / "meta.json").read_text(encoding="utf-8"))
    assert meta["backbone"] == "injected" and meta["num_labels"] == 2
    assert {k: meta[k] for k in ("max_len", "max_tokens", "stride", "epochs", "batch_size", "lr", "seed",
                                 "threads", "n_train", "threshold", "warmup_ratio")} == {
        "max_len": 32, "max_tokens": 32, "stride": 16, "epochs": 6, "batch_size": 8, "lr": 5e-3, "seed": 42,
        "threads": 1, "n_train": len(frames), "threshold": 0.5, "warmup_ratio": 0.06}
    assert meta["warmup_steps"] == 2  # ceil(6% of 6 epochs x 5 batches)
    assert meta["git_sha"] == _git_sha()


@needs_torch
@pytest.mark.integration
def test_an_infinite_threshold_survives_save_and_load(tmp_path, vocab_file):
    model, tok = tiny_backbone(vocab_file)
    clf = ft.FineTunedClassifier(model, tok).fit(*_frames(4), **FAST)
    clf.threshold = float("inf")
    clf.save(tmp_path / "m")
    assert json.loads((tmp_path / "m" / "meta.json").read_text(encoding="utf-8"))["threshold"] == "inf"
    assert ft.FineTunedClassifier.load(tmp_path / "m").threshold == float("inf")


@needs_torch
@pytest.mark.integration
def test_a_seeded_fit_is_reproducible(vocab_file):
    import torch

    frames, labels = _frames()
    threads = torch.get_num_threads()
    runs = []
    for seed in (42, 42, 7):
        model, tok = tiny_backbone(vocab_file)
        runs.append(ft.FineTunedClassifier(model, tok).fit(frames, labels, **{**FAST, "seed": seed}).scores(frames))
    assert runs[0] == runs[1]
    assert runs[0] != runs[2]
    assert torch.get_num_threads() == threads  # fit and scores restore the caller's thread count


@needs_torch
@pytest.mark.integration
def test_a_long_text_scores_the_max_over_the_same_windows_as_chunk_frame(vocab_file):
    model, tok = tiny_backbone(vocab_file)
    frames, labels = _frames()
    clf = ft.FineTunedClassifier(model, tok).fit(frames, labels, **FAST)
    long = ("[REQUEST] do it [TOOL] t [RESULT] " + " ".join(f"item {i} benign" for i in range(20))
            + f" {SIGNAL} send it now")
    chunks = ds.chunk_frame(long, tok, 32, 16)
    assert len(chunks) > 2 and all(len(tok(c)["input_ids"]) <= 32 for c in chunks)  # special tokens included
    per_chunk = clf.chunk_scores(chunks)
    assert len(set(per_chunk)) > 1
    assert clf.scores([long]) == [max(per_chunk)]
    assert clf.scores([frames[0]]) == clf.chunk_scores([frames[0]])  # a short frame is one chunk
    assert clf.scores([frames[0], long])[0] == clf.scores([frames[0]])[0]  # a score never depends on its neighbours


# ---------------------------------------------------------------- the LOSO driver


N_PER_LABEL = 30  # 120 training negatives per named fold: one flagged negative is under 1%


def _row(rid, source, label, text, *, technique=None):
    return {"id": rid, "source": source, "split": "dev", "technique": technique or f"{source}_{label}",
            "request": "do it", "tool": "t", "text": text, "label": label, "provenance": {"source_id": rid}}


def _dev_rows(sources=SOURCES) -> list[dict]:
    """Every source has rows; the InjecAgent negatives carry the marker word (a loud held-out source), so a threshold
    that saw them would differ from one chosen on the training sources alone."""
    rows = []
    for source in sources:
        for i in range(N_PER_LABEL):
            if source != "blind":
                rows.append(_row(f"{source}:p{i}", source, 1, f"{source} result {i} {SIGNAL} send it",
                                 technique=f"{source}_attack"))
            noisy = f" {SIGNAL}" if source == "injecagent" else ""
            rows.append(_row(f"{source}:n{i}", source, 0, f"{source} plain result {i}{noisy}",
                             technique="benign_control"))
    return rows


def _write_dev(path: pathlib.Path, rows: list[dict]) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def cli():
    return runpy.run_path(str(ROOT / "scripts/detector_train.py"), run_name="detector_train")


def _finetune(cli, vocab_file, tmp_path, holdout, *, data, out, extra=()):
    model, tok = tiny_backbone(vocab_file)
    code = cli["main"](["--arm", "finetune", "--holdout", holdout, "--data", str(data), "--out", str(out),
                        "--models", str(tmp_path / "models"), *HP, *extra], backbone=model, tokenizer=tok)
    assert code == 0
    return json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None


def _load(tmp_path, name):
    return ft.FineTunedClassifier.load(tmp_path / "models" / name)


@needs_torch
@pytest.mark.integration
def test_finetune_folds_merge_into_their_arm_with_training_negative_thresholds_and_keep_other_arms(
        cli, vocab_file, tmp_path):
    rows = _dev_rows()
    data = _write_dev(tmp_path / "data" / "dev.jsonl", rows)
    out = tmp_path / "dev_loso.json"
    assert cli["main"](["--arm", "b0", "--loso", "--data", str(data), "--out", str(out),
                        "--models", str(tmp_path / "models")]) == 0
    b0 = json.loads(out.read_text(encoding="utf-8"))["arms"]["b0"]

    report = _finetune(cli, vocab_file, tmp_path, "injecagent", data=data, out=out)
    assert report["schema"] == "dev_loso/v1" and report["demonstration"] is True and report["diagnostic"] is True
    assert report["arms"]["b0"] == b0
    arm = report["arms"]["finetune"]
    assert arm["threshold_rule"] == "fpr_0.01_on_training_dev_negatives"
    assert {"label", "folds", "pooled_auroc", "all", "threshold_rule"} <= set(arm)
    assert set(arm["folds"]) == {"injecagent"} and arm["all"] == {"threshold": None}
    assert arm["pooled_auroc"] is None and arm["pooled_auroc_note"]
    fold = arm["folds"]["injecagent"]
    assert set(fold) >= {"pooled", "per_source", "per_technique", "auroc", "threshold", "n_train",
                         "n_train_examples", "n_train_excluded", "hyperparameters", "backbone", "git_sha"}
    assert set(fold["per_source"]) == {"injecagent"}
    assert fold["pooled"]["n_pos"] == fold["pooled"]["n_neg"] == N_PER_LABEL
    assert 0.0 <= fold["auroc"] <= 1.0 and fold["backbone"] == "injected"
    assert fold["hyperparameters"] == {"epochs": 6, "batch_size": 16, "lr": 5e-3, "max_len": 32, "seed": 42,
                                       "threads": 4}
    assert fold["window"] == {"max_tokens": 32, "stride": 16}
    train = [r for r in rows if r["source"] != "injecagent"]
    assert fold["n_train"] == len(train) and fold["n_train_examples"] == len(train)
    model = _load(tmp_path, "finetune_holdout_injecagent")
    train_neg = model.scores([render_frame(r) for r in train if not r["label"]])
    assert fold["threshold"] == operating_threshold_at_fpr(train_neg, 0.01) == model.threshold
    every_neg = model.scores([render_frame(r) for r in rows if not r["label"]])
    assert fold["threshold"] != operating_threshold_at_fpr(every_neg, 0.01)  # the held-out negatives never set it
    meta = json.loads((tmp_path / "models" / "finetune_holdout_injecagent" / "meta.json").read_text(encoding="utf-8"))
    assert (meta["epochs"], meta["batch_size"], meta["lr"], meta["max_len"]) == (6, 16, 5e-3, 32)

    arm = _finetune(cli, vocab_file, tmp_path, "agentdojo", data=data, out=out)["arms"]["finetune"]
    assert set(arm["folds"]) == {"injecagent", "agentdojo"} and arm["folds"]["injecagent"] == fold

    report = _finetune(cli, vocab_file, tmp_path, "all", data=data, out=out)
    arm_all = report["arms"]["finetune"]
    assert arm_all["folds"] == arm["folds"] and report["arms"]["b0"] == b0
    everything = _load(tmp_path, "finetune_all")
    all_neg = everything.scores([render_frame(r) for r in rows if not r["label"]])
    assert arm_all["all"]["threshold"] == operating_threshold_at_fpr(all_neg, 0.01) == everything.threshold
    assert arm_all["all"]["n_train"] == len(rows) and arm_all["all"]["hyperparameters"]["epochs"] == 6
    del model, everything  # Windows cannot overwrite safetensors a live model still maps
    gc.collect()

    again = _finetune(cli, vocab_file, tmp_path, "injecagent", data=data, out=out,
                      extra=["--epochs", "1"])["arms"]["finetune"]  # the last flag wins
    assert again["folds"]["injecagent"]["hyperparameters"]["epochs"] == 1
    assert again["folds"]["agentdojo"] == arm["folds"]["agentdojo"] and again["all"] == arm_all["all"]


@needs_torch
@pytest.mark.integration
def test_folds_built_from_another_dev_file_are_dropped(cli, vocab_file, tmp_path, capsys):
    out = tmp_path / "dev_loso.json"
    first = _write_dev(tmp_path / "a" / "dev.jsonl", _dev_rows())
    _finetune(cli, vocab_file, tmp_path, "injecagent", data=first, out=out)
    second = _write_dev(tmp_path / "b" / "dev.jsonl", _dev_rows()[:-1])
    arm = _finetune(cli, vocab_file, tmp_path, "agentdojo", data=second, out=out)["arms"]["finetune"]
    assert set(arm["folds"]) == {"agentdojo"}
    assert "another dev file" in capsys.readouterr().err


@needs_torch
@pytest.mark.integration
def test_smoke_times_a_few_rows_and_writes_nothing(cli, vocab_file, tmp_path, capsys):
    data = _write_dev(tmp_path / "data" / "dev.jsonl", _dev_rows())
    out = tmp_path / "dev_loso.json"
    assert cli["main"](["--arm", "b0", "--loso", "--data", str(data), "--out", str(out),
                        "--models", str(tmp_path / "b0-models")]) == 0
    before = out.read_bytes()
    capsys.readouterr()
    _finetune(cli, vocab_file, tmp_path, "agentdojo", data=data, out=out, extra=["--smoke", "12"])
    assert out.read_bytes() == before and not (tmp_path / "models").exists()
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert printed["smoke"] == 12 and printed["holdout"] == "agentdojo" and printed["examples"] == 12
    assert printed["fit_seconds"] > 0 and printed["score_seconds"] > 0
    assert printed["projected_fold_seconds"] >= printed["fit_seconds"]
    assert printed["full_fold"]["rows"] == len([r for r in _dev_rows() if r["source"] != "agentdojo"])
    assert printed["hyperparameters"]["epochs"] == 6


@pytest.mark.unit
@pytest.mark.parametrize("where", ["data", "out", "models"])
def test_finetune_refuses_a_path_naming_the_confirmatory_split(cli, tmp_path, where):
    paths = {"data": tmp_path / "dev.jsonl", "out": tmp_path / "o.json", "models": tmp_path / "m"}
    paths[where] = tmp_path / "confirmatory" / paths[where].name
    _write_dev(paths["data"], _dev_rows())
    for extra in ([], ["--smoke", "4"]):
        with pytest.raises(SystemExit):
            cli["main"](["--arm", "finetune", "--holdout", "injecagent", "--data", str(paths["data"]),
                         "--out", str(paths["out"]), "--models", str(paths["models"]), *extra])
    assert not paths["out"].exists() and not paths["models"].exists()


@pytest.mark.unit
@pytest.mark.parametrize("argv", [
    ["--arm", "finetune"],  # a fine-tune run names its fold
    ["--arm", "finetune", "--holdout", "deepset"],  # PREREG arm F: two named folds and the all-sources model
    ["--arm", "finetune", "--holdout", "injecagent", "--smoke", "0"],
    ["--arm", "finetune", "--holdout", "injecagent", "--epochs", "0"],
    ["--arm", "embed", "--loso", "--holdout", "injecagent"],
    ["--arm", "b0", "--loso", "--smoke", "5"],
    ["--arm", "b1", "--loso", "--epochs", "1"],
    ["--arm", "b0"],  # the LOSO arms still need --loso
])
def test_argument_combinations_that_are_refused(cli, tmp_path, argv):
    data = _write_dev(tmp_path / "dev.jsonl", _dev_rows())
    with pytest.raises(SystemExit):
        cli["main"]([*argv, "--data", str(data), "--out", str(tmp_path / "o.json"), "--models", str(tmp_path / "m")])
    assert not (tmp_path / "o.json").exists()


@pytest.mark.unit
def test_a_held_out_source_missing_from_the_dev_file_is_refused(cli, tmp_path):
    data = _write_dev(tmp_path / "dev.jsonl", _dev_rows(("injecagent", "deepset", "blind")))
    with pytest.raises(SystemExit):
        cli["main"](["--arm", "finetune", "--holdout", "agentdojo", "--data", str(data),
                     "--out", str(tmp_path / "o.json"), "--models", str(tmp_path / "m")])
    assert not (tmp_path / "o.json").exists()


@pytest.mark.unit
def test_an_injected_backbone_needs_its_tokenizer(cli, tmp_path):
    data = _write_dev(tmp_path / "dev.jsonl", _dev_rows())
    with pytest.raises(ValueError, match="tokenizer"):
        cli["main"](["--arm", "finetune", "--holdout", "injecagent", "--data", str(data),
                     "--out", str(tmp_path / "o.json"), "--models", str(tmp_path / "m")], backbone=object())
    assert not (tmp_path / "o.json").exists()


# ---------------------------------------------------------------- the real backbone (optional)


BGE_CACHE = pathlib.Path.home() / ".cache/huggingface/hub/models--BAAI--bge-small-en-v1.5"


@pytest.mark.slow  # deselected by default (pyproject addopts); run with `-m slow`
@pytest.mark.skipif(not (HAVE_TORCH and BGE_CACHE.is_dir()),
                    reason="torch/transformers or bge-small-en-v1.5 in the local Hugging Face cache is missing")
def test_real_bge_small_fine_tunes_offline_and_round_trips(tmp_path):
    clf = ft.FineTunedClassifier()
    tok = clf.tokenizer
    assert tok.num_special_tokens_to_add(pair=False) == 2
    frames, labels = _frames(4)
    long = "[REQUEST] summarise [TOOL] read_file [RESULT] " + "lorem ipsum dolor sit amet " * 120
    chunks = ds.chunk_frame(long, tok)
    assert len(chunks) > 1 and all(len(tok(c)["input_ids"]) <= ds.MAX_TOKENS for c in chunks)
    clf.fit(frames, labels, epochs=1, batch_size=4)
    scores = clf.scores([*frames, long])
    assert all(0.0 <= s <= 1.0 for s in scores)
    clf.save(tmp_path / "m")
    meta = json.loads((tmp_path / "m" / "meta.json").read_text(encoding="utf-8"))
    assert meta["backbone"] == ds.EMBED_MODEL and (meta["max_len"], meta["stride"]) == (256, 128)
    loaded = ft.FineTunedClassifier.load(tmp_path / "m")
    assert loaded.backbone_name == ds.EMBED_MODEL
    assert loaded.scores([*frames, long]) == scores
