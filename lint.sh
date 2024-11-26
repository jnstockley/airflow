#!/usr/bin/env bash

# Run linter
flake8 --config flake8.ini
black --check .