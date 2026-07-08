#!/usr/bin/env python3
"""Pull all free public API data sources."""

import json

from ingest.pull_free import pull_all_free_data


def main() -> None:
    result = pull_all_free_data()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
