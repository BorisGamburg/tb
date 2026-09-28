from rich.text import Text

from action_resolver.grid_mtf_strategy.entry_checker import EntryCheckResult
from action_resolver.grid_mtf_strategy.rearm_manager import RearmCheckResult
from action_resolver.grid_mtf_strategy.partial_exit_bbw import BBWCheckResult
from action_processor.action_guard import GuardResult


class StatusLine:

    def build(
        self,
        price: float,
        check_result: EntryCheckResult | None = None,
        rearm_check_result: RearmCheckResult | None = None,
        bbw_check_result: BBWCheckResult | None = None,
        guard_result: GuardResult | None = None,
    ) -> Text:

        text = Text()
        text.append(f"PRICE: {price:.6f}  ", style="cyan")
        text.append(self._build_entry_status(check_result))
        text.append(self._build_exit_status(
            rearm_check_result,
            bbw_check_result,
        ))
        text.append(self._build_guard_status(guard_result))

        return text

    def _build_entry_status(
        self,
        check_result: EntryCheckResult | None = None,
    ) -> Text:

        text = Text()

        text.append("\nENTRY | HA: ", style="cyan")
        if check_result is not None:
            ha = check_result.ha
            text.append(
                f"({ha.tf}m) [{ha.prev}→{ha.curr}]"
            )
            text.append(
                " ●",
                style="bold green" if ha.signal else "bold red",
            )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        text.append(" | RSI: ", style="cyan")
        if check_result is not None:
            rsi = check_result.rsi

            tf_th = (
                f"{rsi.threshold:.0f}"
                if rsi.threshold is not None
                else "N/A"
            )

            tf_v = (
                f"{rsi.value:.1f}"
                if rsi.value is not None
                else "N/A"
            )

            text.append(
                f"({tf_v}/{tf_th})"
                f" TF:{rsi.tf}"
            )
            text.append(
                " ●",
                style="bold green" if rsi.ok else "bold red",
            )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        text.append(" | BB: ", style="cyan")
        if check_result is not None:
            bb = check_result.bb

            text.append(
                f"({bb.value:.6f}/{bb.mid:.6f})"
                f" TF:{bb.tf}"
            )
            text.append(
                " ●",
                style="bold green" if bb.ok else "bold red",
            )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        text.append(" | DIST_THRES: ", style="cyan")
        if check_result is not None:
            distance = check_result.distance

            if distance.threshold is not None:
                text.append(
                    f"{distance.threshold:.6f}"
                )
                text.append(
                    " ●",
                    style=(
                        "bold green"
                        if distance.ok
                        else "bold red"
                    ),
                )
            else:
                text.append(
                    "N/A",
                    style="dim",
                )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        return text

    def _build_exit_status(
        self,
        rearm_check_result: RearmCheckResult | None = None,
        bbw_check_result: BBWCheckResult | None = None,
    ) -> Text:

        text = Text()

        text.append("\nEXIT  | RSI: ", style="cyan")
        if rearm_check_result is not None:
            text.append(
                f"({rearm_check_result.rsi:.1f}/"
                f"{rearm_check_result.rsi_threshold:.0f})"
            )
            text.append(
                " ●",
                style=(
                    "bold green"
                    if rearm_check_result.rsi_ok
                    else "bold red"
                ),
            )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        text.append(" | BBW: ", style="cyan")
        if bbw_check_result is not None:
            if not bbw_check_result.has_position:
                text.append(
                    "NO_POS",
                    style="dim",
                )
            elif (
                bbw_check_result.bb_cross_tp is not None
                and bbw_check_result.bb_width_tp is not None
            ):
                text.append(
                    f"[cross={bbw_check_result.bb_cross_tp:.6f} "
                    f"width={bbw_check_result.bb_width_tp:.6f}]"
                )
            else:
                text.append(
                    "N/A",
                    style="dim",
                )
        else:
            text.append(
                "N/A",
                style="dim",
            )

        return text

    def _build_guard_status(
        self,
        guard_result: GuardResult | None = None,
    ) -> Text:

        text = Text()

        if guard_result is not None:
            text.append("\nGUARD: ", style="cyan")
            text.append(
                "●",
                style=(
                    "bold green"
                    if guard_result.allowed
                    else "bold red"
                ),
            )

        return text