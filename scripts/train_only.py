#!/usr/bin/env python3
"""Train ML model and rescore all signals."""

from __future__ import annotations

import logging

from processor.train import rescore_all, train_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
  logger.info("Training LightGBM model...")
  metrics = train_model()
  logger.info("Train metrics: %s", metrics)
  logger.info("Rescoring all signals...")
  updated = rescore_all()
  logger.info("Rescored %s signals.", updated)


if __name__ == "__main__":
  main()
