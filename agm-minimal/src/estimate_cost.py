# src/estimate_cost.py
"""Print a transparent maximum-budget estimate from experiment.yaml."""
from __future__ import annotations
import argparse
from pathlib import Path
import yaml


def estimate(config_path: str = "experiment.yaml", retries: int = 0) -> dict[str, float]:
    if retries < 0:
        raise ValueError("retries must be >= 0")
    with Path(config_path).open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cost = cfg["cost"]
    price = cost["pricing_usd_per_million_tokens"]
    inp_rate = float(price["input"]) / 1_000_000
    out_rate = float(price["output"]) / 1_000_000
    task_calls = (
        int(cfg["qualification"]["failure_opportunities"])
        + int(cfg["qualification"]["clean_controls"])
        + int(cfg["holdout"]["matched_trials"])
        + int(cfg["holdout"]["shifted_trials"])
    )
    input_tokens = (
        (int(cfg["qualification"]["failure_opportunities"])
         + int(cfg["qualification"]["clean_controls"])
         + int(cfg["holdout"]["matched_trials"]))
        * int(cost["estimated_input_tokens_per_matched_trial"])
        + int(cfg["holdout"]["shifted_trials"])
        * int(cost["estimated_input_tokens_per_shifted_trial"])
    )
    output_tokens = task_calls * int(cost["estimated_output_tokens_per_trial"])
    canary_calls = int(cfg["canary"]["prompts"]) * int(cfg["canary"]["repetitions_per_prompt"]) * int(cfg["canary"]["batches"])
    canary_input = canary_calls * int(cost["canary_input_tokens"])
    canary_output = canary_calls * int(cost["canary_output_tokens"])
    smoke_calls = int(cost.get("smoke_model_calls_allowance", 0))
    smoke_input = smoke_calls * int(cost["smoke_input_tokens"])
    smoke_output = smoke_calls * int(cost["smoke_output_tokens"])
    multiplier = retries + 1
    task_cost = (input_tokens * multiplier * inp_rate) + (output_tokens * multiplier * out_rate)
    canary_cost = canary_input * inp_rate + canary_output * out_rate
    smoke_cost = smoke_input * inp_rate + smoke_output * out_rate
    total = task_cost + canary_cost + smoke_cost
    return {
        "task_calls_including_retries": float(task_calls * multiplier),
        "canary_calls": float(canary_calls),
        "smoke_model_calls_allowance": float(smoke_calls),
        "task_cost_usd": task_cost,
        "canary_cost_usd": canary_cost,
        "smoke_cost_usd": smoke_cost,
        "total_cost_usd": total,
        "total_with_20pct_reserve_usd": total * 1.2,
        "cap_usd": float(cost["cap_usd"]),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="experiment.yaml")
    parser.add_argument("--retries", type=int, default=0, help="Retries per task, excluding first attempt")
    args = parser.parse_args()
    for key, value in estimate(args.config, args.retries).items():
        print(f"{key}: {value:.4f}")
