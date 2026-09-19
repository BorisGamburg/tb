#!/bin/bash
exec ~/venvs/stack_gui_test/bin/python \
    "$(dirname "$0")/test_chart.py" \
    "$@"