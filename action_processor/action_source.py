from enum import Enum


class ActionSource(str, Enum):
    ENTRY_CHECKER = "entry_checker"
    REARM_CHECKER = "rearm_checker"
    PARTIAL_EXIT_CROSS = "partial_exit_cross"
    PARTIAL_EXIT_BBW = "partial_exit_bbw"
    EXTERNAL_COMMAND = "external_command"